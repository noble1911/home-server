"""Readarr integration tool for Butler.

This tool allows the agent to manage books and audiobooks via Readarr's REST API,
enabling voice and text-based book library management.

Usage:
    The tool is automatically registered when READARR_URL is configured.
    Requires READARR_URL and READARR_API_KEY in the application settings.

Example:
    tool = ReadarrTool(base_url="http://readarr:8787", api_key="abc123")
    result = await tool.execute(action="search_book", title="Project Hail Mary")

    # When shutting down
    await tool.close()

API Reference:
    https://readarr.com/docs/api/
"""

from __future__ import annotations

import re
from typing import Any

import aiohttp

from .base import Tool

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 30


class ReadarrTool(Tool):
    """Manage books in Readarr via REST API.

    Supports searching for books by title or author, adding them to the library,
    checking library status, deleting books, and viewing the download queue.

    The tool reuses HTTP sessions for better performance and
    caches quality profiles, metadata profiles, and root folders to minimise API calls.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize the Readarr tool.

        Args:
            base_url: Readarr URL (e.g. http://readarr:8787)
            api_key: Readarr API key (Settings > General > Security)
            timeout: HTTP request timeout in seconds (default: 30)
        """
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        # Cached config for auto-detection
        self._quality_profiles: list[dict] | None = None
        self._metadata_profiles: list[dict] | None = None
        self._root_folders: list[dict] | None = None
        # Cache last search results so add_book can skip the slow edition lookup
        self._last_search_results: dict[str, dict] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"X-Api-Key": self.api_key},
                timeout=self.timeout,
            )
        return self._session

    async def close(self) -> None:
        """Close the HTTP session.

        Should be called when shutting down to cleanly release connections.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "readarr"

    @property
    def description(self) -> str:
        return (
            "Manage books in Readarr. Search for books by title or author, "
            "add them to your library, check if a book exists and its download "
            "status, view active downloads, or delete books from your collection."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "search_book",
                        "add_book",
                        "check_library",
                        "delete_book",
                        "get_queue",
                    ],
                    "description": (
                        "search_book: Find books by title or author. "
                        "add_book: Add a book (needs book_foreign_id from search). "
                        "check_library: Check if a book exists and its status. "
                        "delete_book: Remove a book (needs book_id from check). "
                        "get_queue: Show active downloads with progress."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": (
                        "Book title or author name to search for. "
                        "Used by search_book and check_library."
                    ),
                },
                "book_foreign_id": {
                    "type": "string",
                    "description": (
                        "GoodReads book ID from search results. "
                        "Required for add_book."
                    ),
                },
                "book_id": {
                    "type": "integer",
                    "description": (
                        "Readarr book ID from check_library results. "
                        "Required for delete_book."
                    ),
                },
                "delete_files": {
                    "type": "boolean",
                    "description": (
                        "Also delete book files from disk (default: false). "
                        "Only used with delete_book."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]

        if not self.base_url or not self.api_key:
            return "Error: READARR_URL and READARR_API_KEY must be configured."

        try:
            if action == "search_book":
                return await self._search_book(kwargs.get("title", ""))
            elif action == "add_book":
                return await self._add_book(
                    book_foreign_id=kwargs.get("book_foreign_id"),
                    title=kwargs.get("title", ""),
                )
            elif action == "check_library":
                return await self._check_library(kwargs.get("title", ""))
            elif action == "delete_book":
                return await self._delete_book(
                    book_id=kwargs.get("book_id"),
                    delete_files=kwargs.get("delete_files", False),
                )
            elif action == "get_queue":
                return await self._get_queue()
            else:
                return f"Error: Unknown action '{action}'"
        except aiohttp.ClientError as e:
            return f"Error connecting to Readarr: {e}"
        except TimeoutError:
            return (
                "Error: Readarr metadata lookup timed out. "
                "This can happen with certain search terms. "
                "Try a shorter or simpler search query (e.g. just the book title without author)."
            )
        except Exception as e:
            return f"Error: {e}"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _search_book(self, title: str) -> str:
        """Search for books via Readarr's lookup endpoint."""
        if not title:
            return "Error: title is required for search_book"

        session = await self._get_session()
        url = f"{self.base_url}/api/v1/book/lookup"

        async with session.get(url, params={"term": title}) as resp:
            if resp.status == 401:
                return "Error: Invalid Readarr API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            results = await resp.json()
            if not results or not isinstance(results, list):
                return f"No books found for '{title}'"

            # Cache results so add_book can skip the slow edition lookup
            self._last_search_results = {
                b.get("foreignBookId", ""): b
                for b in results[:5]
                if b.get("foreignBookId")
            }

            return self._format_search_results(results[:5], title)

    async def _add_book(
        self,
        book_foreign_id: str | None,
        title: str,
    ) -> str:
        """Add a book to Readarr using its GoodReads foreign ID."""
        if not book_foreign_id:
            return "Error: book_foreign_id is required for add_book (get it from search_book)"

        session = await self._get_session()

        # Use cached search result (the edition lookup hangs on many books
        # due to an upstream Bookshelf/api.bookinfo.pro bug)
        book_data = self._last_search_results.get(book_foreign_id)
        if not book_data:
            return (
                "Error: Book data not found in cache. "
                "Please search_book first, then use the ID from the results."
            )

        # Auto-detect quality profile, metadata profile, and root folder
        quality_profile_id = await self._get_default_quality_profile_id()
        if quality_profile_id is None:
            return "Error: No quality profiles configured in Readarr."

        metadata_profile_id = await self._get_default_metadata_profile_id()
        if metadata_profile_id is None:
            return "Error: No metadata profiles configured in Readarr."

        root_folder_path = await self._get_default_root_folder()
        if root_folder_path is None:
            return "Error: No root folders configured in Readarr."

        # Resolve author data — search results return an empty author object,
        # so we scrape the GoodReads book page for the author's foreign ID
        # and parse the author name from the authorTitle field.
        author = book_data.get("author") or {}
        if not author.get("foreignAuthorId"):
            author_gr_id = await self._resolve_author_id(book_data)
            author_name = self._parse_author_name(book_data)
            author = {
                "foreignAuthorId": author_gr_id,
                "authorName": author_name,
            }

        author["qualityProfileId"] = quality_profile_id
        author["metadataProfileId"] = metadata_profile_id
        author["rootFolderPath"] = root_folder_path
        author["monitored"] = True

        # Ensure editions list exists (search results return editions=null)
        editions = book_data.get("editions")
        if not editions:
            editions = [{
                "foreignEditionId": book_data.get("foreignEditionId"),
                "title": book_data.get("title"),
                "monitored": True,
                "images": book_data.get("images", []),
                "links": book_data.get("links", []),
                "ratings": book_data.get("ratings", {}),
                "pageCount": book_data.get("pageCount", 0),
            }]

        # Build payload
        payload = {
            **book_data,
            "author": author,
            "editions": editions,
            "monitored": True,
            "addOptions": {"searchForNewBook": True},
        }

        async with session.post(
            f"{self.base_url}/api/v1/book", json=payload
        ) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                book_title = result.get("title", title or "Book")
                result_author = result.get("author", {}).get(
                    "authorName", author.get("authorName", "Unknown")
                )
                return f"Added '{book_title}' by {result_author} to Readarr. Searching for releases now."
            elif resp.status == 400:
                error = await resp.text()
                if "already" in error.lower():
                    return f"'{title or 'This book'}' is already in your library."
                return f"Error adding book: {error}"
            else:
                return f"Error: HTTP {resp.status}"

    async def _check_library(self, title: str) -> str:
        """Check if a book exists in the Readarr library."""
        if not title:
            return "Error: title is required for check_library"

        session = await self._get_session()

        async with session.get(f"{self.base_url}/api/v1/book") as resp:
            if resp.status == 401:
                return "Error: Invalid Readarr API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            books = await resp.json()

        # Case-insensitive partial match on title or author name
        title_lower = title.lower()
        matches = [
            b
            for b in books
            if title_lower in b.get("title", "").lower()
            or title_lower
            in b.get("author", {}).get("authorName", "").lower()
        ]

        if not matches:
            return f"'{title}' not found in library."

        return self._format_library_results(matches[:5])

    async def _delete_book(
        self,
        book_id: int | None,
        delete_files: bool,
    ) -> str:
        """Delete a book from Readarr."""
        if not book_id:
            return "Error: book_id is required for delete_book (get it from check_library)"

        session = await self._get_session()
        url = f"{self.base_url}/api/v1/book/{book_id}"
        params = {"deleteFiles": str(delete_files).lower()}

        async with session.delete(url, params=params) as resp:
            if resp.status in (200, 204):
                files_note = " and deleted files from disk" if delete_files else ""
                return f"Removed book (ID {book_id}) from Readarr{files_note}."
            elif resp.status == 404:
                return f"Error: Book ID {book_id} not found in Readarr."
            else:
                return f"Error: HTTP {resp.status}"

    async def _get_queue(self) -> str:
        """Get active downloads from the Readarr queue."""
        session = await self._get_session()

        async with session.get(f"{self.base_url}/api/v1/queue") as resp:
            if resp.status == 401:
                return "Error: Invalid Readarr API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            data = await resp.json()

        records = data.get("records", [])
        if not records:
            return "Download queue is empty."

        return self._format_queue(records)

    # ------------------------------------------------------------------
    # Auto-detection helpers (cached)
    # ------------------------------------------------------------------

    async def _get_default_quality_profile_id(self) -> int | None:
        """Return the first quality profile ID, caching after first call."""
        if self._quality_profiles is None:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/v1/qualityprofile"
            ) as resp:
                if resp.status != 200:
                    return None
                self._quality_profiles = await resp.json()

        if self._quality_profiles:
            return self._quality_profiles[0].get("id")
        return None

    async def _get_default_metadata_profile_id(self) -> int | None:
        """Return the first metadata profile ID, caching after first call."""
        if self._metadata_profiles is None:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/v1/metadataprofile"
            ) as resp:
                if resp.status != 200:
                    return None
                self._metadata_profiles = await resp.json()

        if self._metadata_profiles:
            return self._metadata_profiles[0].get("id")
        return None

    async def _get_default_root_folder(self) -> str | None:
        """Return the first root folder path, caching after first call."""
        if self._root_folders is None:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/v1/rootfolder"
            ) as resp:
                if resp.status != 200:
                    return None
                self._root_folders = await resp.json()

        if self._root_folders:
            return self._root_folders[0].get("path")
        return None

    # ------------------------------------------------------------------
    # Author resolution helpers
    # ------------------------------------------------------------------

    async def _resolve_author_id(self, book_data: dict) -> str | None:
        """Get the GoodReads author ID from the book's GoodReads page."""
        gr_url = next(
            (
                link["url"]
                for link in book_data.get("links", [])
                if "goodreads.com/book" in link.get("url", "")
            ),
            None,
        )
        if not gr_url:
            return None

        try:
            short_timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=short_timeout) as s:
                async with s.get(gr_url) as resp:
                    if resp.status != 200:
                        return None
                    html = await resp.text()
                    matches = re.findall(r"/author/show/(\d+)", html)
                    return matches[0] if matches else None
        except Exception:
            return None

    @staticmethod
    def _parse_author_name(book_data: dict) -> str:
        """Parse author name from Readarr's authorTitle field.

        The field format is "lastname, firstname BookTitle",
        e.g. "herbert, frank Dune" -> "Frank Herbert".
        """
        author_title = book_data.get("authorTitle", "")
        if "," not in author_title:
            return "Unknown"
        comma_idx = author_title.index(",")
        last = author_title[:comma_idx].strip().title()
        rest = author_title[comma_idx + 1 :].strip()
        first = rest.split()[0].title() if rest else ""
        return f"{first} {last}".strip() or "Unknown"

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_search_results(self, results: list[dict], query: str) -> str:
        """Format book search results for LLM consumption."""
        lines = [f"Found {len(results)} result(s) for '{query}':\n"]
        for i, book in enumerate(results, 1):
            title = book.get("title", "Unknown")
            author_name = book.get("author", {}).get("authorName")
            if not author_name:
                author_name = self._parse_author_name(book)
            foreign_id = book.get("foreignBookId", "?")
            overview = book.get("overview", "")
            # Truncate overview to keep response concise
            if len(overview) > 100:
                overview = overview[:100] + "..."

            lines.append(f"{i}. {title} by {author_name} [ID: {foreign_id}]")
            if overview:
                lines.append(f"   {overview}")
        return "\n".join(lines)

    def _format_library_results(self, books: list[dict]) -> str:
        """Format library matches for LLM consumption."""
        lines = []
        for book in books:
            title = book.get("title", "Unknown")
            author_name = book.get("author", {}).get("authorName", "Unknown")
            book_id = book.get("id", "?")
            monitored = "Monitored" if book.get("monitored") else "Unmonitored"

            book_files = book.get("bookFiles", [])
            has_file = len(book_files) > 0

            if has_file:
                book_file = book_files[0]
                quality_name = (
                    book_file.get("quality", {})
                    .get("quality", {})
                    .get("name", "Unknown")
                )
                size_bytes = book_file.get("size") or 0
                size_mb = size_bytes / (1024**2)
                lines.append(f"{title} by {author_name} [ID: {book_id}]")
                lines.append(
                    f"  Status: Downloaded - {quality_name} ({size_mb:.1f} MB)"
                )
            else:
                lines.append(f"{title} by {author_name} [ID: {book_id}]")
                lines.append("  Status: Missing")

            lines.append(f"  {monitored}")
            lines.append("")

        return "\n".join(lines).rstrip()

    def _format_queue(self, records: list[dict]) -> str:
        """Format download queue for LLM consumption."""
        lines = [f"Active downloads ({len(records)}):\n"]
        for item in records:
            title = item.get("title", "Unknown")
            status = item.get("status", "unknown")
            size = item.get("size") or 0
            size_left = item.get("sizeleft") or 0
            time_left = item.get("timeleft", "unknown")

            if size > 0:
                progress_pct = ((size - size_left) / size) * 100
            else:
                progress_pct = 0.0

            lines.append(f"- {title}")
            lines.append(
                f"  {status} - {progress_pct:.1f}% complete (ETA: {time_left})"
            )
        return "\n".join(lines)
