"""Send to Kindle tool for Butler (#213).

Finds a book in the household ebook library (Books/eBooks on the external
drive) and emails it to the user's own Kindle: their saved Send-to-Kindle
address, sent from their own Gmail. Amazon stopped accepting MOBI/AZW by
email in 2022, so other formats are converted to EPUB first by the
``ebook-convert`` sidecar (Calibre; see butler/ebook_convert/).

There is deliberately no recipient parameter: the address always comes from
the user's profile, so the model can't be talked into mailing files anywhere
else. That's also why sends don't need tap-to-approve.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import aiohttp

from .base import Tool

logger = logging.getLogger(__name__)

LIBRARY_SUBDIR = Path("Books") / "eBooks"

# Formats Amazon's Send to Kindle accepts by email, sent as-is.
SENDABLE = {
    ".epub": "application/epub+zip",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".rtf": "application/rtf",
}
# Formats Amazon refuses (or never took) by email: converted to EPUB first.
CONVERTIBLE = {".mobi", ".azw", ".azw3", ".prc", ".pdb", ".fb2", ".lit", ".odt", ".htmlz", ".txtz"}
# Which copy to use when a book is there in several formats.
FORMAT_PREFERENCE = [".epub", ".azw3", ".mobi", ".azw", ".fb2", ".pdf", ".docx", ".rtf", ".txt",
                     ".prc", ".pdb", ".lit", ".odt", ".htmlz", ".txtz"]

# Gmail caps a message at 25 MB *after* base64 (~+37%), so keep the raw file under ~18 MB.
MAX_ATTACHMENT_BYTES = 18 * 1024 * 1024
MAX_SCAN_FILES = 20000
MAX_RESULTS = 10

_WORD_RE = re.compile(r"[a-z0-9]+")

_APPROVED_SENDER_TIP = (
    "If it doesn't arrive within a few minutes, check that {sender} is on the "
    "Approved Personal Document E-mail List in Amazon (Manage Your Content and "
    "Devices > Preferences > Personal Document Settings)."
)


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _title(path: Path) -> str:
    """A readable title from a filename like 'Andy_Weir-Project.Hail.Mary.epub'."""
    return " ".join(re.sub(r"[._]+", " ", path.stem).split()) or path.name


class SendToKindleTool(Tool):
    """Email a library ebook to the user's own Kindle."""

    def __init__(self, db_pool, user_id: str, library_root: str | Path | None = None):
        self._pool = db_pool
        self._user_id = user_id
        self._library_root = Path(library_root) if library_root else None

    @property
    def name(self) -> str:
        return "send_to_kindle"

    @property
    def description(self) -> str:
        return (
            "Send a book from the household ebook library to the user's own Kindle (their saved "
            "Send-to-Kindle address, emailed from their Gmail). First use find with the title or "
            "author to get the book's path, then send with that path. MOBI/AZW3 and other formats "
            "are converted to EPUB automatically. It can only send to the user's own Kindle. If the "
            "book isn't in the library, offer to download it with the books tool first."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["find", "send"],
                    "description": (
                        "find: search the ebook library by title/author words. "
                        "send: email the book at `path` (from find) to the user's Kindle."
                    ),
                },
                "query": {"type": "string", "description": "Title and/or author words for find."},
                "path": {"type": "string", "description": "The book's path exactly as returned by find."},
                "fix_epub": {
                    "type": "boolean",
                    "description": (
                        "send: re-process an EPUB through Calibre before sending. Use only if "
                        "Amazon rejected this book before."
                    ),
                },
            },
            "required": ["action"],
        }

    # -- helpers (methods so tests can override) ------------------------------

    @property
    def library(self) -> Path:
        if self._library_root is not None:
            return self._library_root
        from api.config import settings

        return Path(settings.external_drive_path) / LIBRARY_SUBDIR

    async def _kindle_email(self) -> str | None:
        return await self._pool.pool.fetchval(
            "SELECT kindle_email FROM butler.users WHERE id = $1", self._user_id,
        )

    async def _get_token(self) -> str | None:
        from api.oauth import get_valid_token

        return await get_valid_token(self._pool, self._user_id, "google")

    async def _granted_scopes(self) -> set[str]:
        from api.oauth import get_granted_scopes

        return await get_granted_scopes(self._pool, self._user_id, "google")

    async def _sender(self) -> str:
        from api.oauth import get_account_email

        return await get_account_email(self._pool, self._user_id, "google") or "your Gmail address"

    async def _convert(self, relative: str, fmt: str = "epub") -> bytes:
        """Convert via the ebook-convert sidecar. Raises RuntimeError with a user-facing reason."""
        from api.config import settings

        headers = {"X-Convert-Token": settings.ebook_convert_token} if settings.ebook_convert_token else {}
        timeout = aiohttp.ClientTimeout(total=330)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{settings.ebook_convert_url.rstrip('/')}/convert",
                    json={"path": relative, "to": fmt},
                    headers=headers,
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    try:
                        reason = (await resp.json()).get("error", "")
                    except Exception:
                        reason = ""
                    raise RuntimeError(reason or f"the converter returned {resp.status}")
        except aiohttp.ClientError as e:
            raise RuntimeError(f"the ebook converter isn't reachable ({e})") from e

    # -- actions --------------------------------------------------------------

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "find")
        try:
            if action == "find":
                return self._find(kwargs.get("query", ""))
            if action == "send":
                return await self._send(kwargs.get("path", ""), fix_epub=bool(kwargs.get("fix_epub")))
            return f"Unknown action: {action}. Use 'find' or 'send'."
        except Exception as e:
            logger.exception("send_to_kindle %s failed", action)
            return f"Error: {e}"

    def _find(self, query: str) -> str:
        terms = _words(query)
        if not terms:
            return "Give me some title or author words to search for."
        root = self.library
        if not root.is_dir():
            return "The ebook library isn't available right now (is the drive mounted?)."

        books: dict[tuple[str, str], list[Path]] = {}
        scanned = 0
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                scanned += 1
                path = Path(dirpath) / name
                ext = path.suffix.lower()
                if ext not in SENDABLE and ext not in CONVERTIBLE:
                    continue
                rel = path.relative_to(root)
                haystack = set(_words(str(rel)))
                if all(any(w.startswith(t) for w in haystack) for t in terms):
                    key = (str(rel.parent), " ".join(_words(path.stem)))
                    books.setdefault(key, []).append(path)
            if scanned >= MAX_SCAN_FILES:
                break

        if not books:
            return (
                f"No books matching '{query}' in the library. "
                "The books tool can search for it and download it first."
            )

        lines = []
        for copies in sorted(books.values(), key=lambda c: (len(str(c[0])), str(c[0])))[:MAX_RESULTS]:
            best = _best_copy(copies)
            formats = ", ".join(sorted({p.suffix.lstrip(".").upper() for p in copies}))
            lines.append(
                f"- {_title(best)} [{formats}, {_size(best.stat().st_size)}]\n  path: {best.relative_to(root)}"
            )
        more = f"\n(showing {MAX_RESULTS} of {len(books)})" if len(books) > MAX_RESULTS else ""
        return f"Found {len(books)} book(s):\n" + "\n".join(lines) + more

    def _resolve(self, relative: str) -> Path:
        if not relative:
            raise ValueError("Give the book's path from find.")
        root = self.library.resolve()
        full = (root / relative).resolve()
        if not full.is_relative_to(root):
            raise ValueError("That path is outside the ebook library.")
        if not full.is_file():
            raise ValueError(f"No such book in the library: {relative}. Use find to get the exact path.")
        if full.suffix.lower() not in SENDABLE and full.suffix.lower() not in CONVERTIBLE:
            raise ValueError(f"{full.suffix or 'That file'} isn't an ebook format I can send.")
        return full

    async def _send(self, relative: str, *, fix_epub: bool = False) -> str:
        from api.oauth import GMAIL_SEND_SCOPE

        from .gmail import GmailSendError, build_mime, send_mime

        try:
            path = self._resolve(relative)
        except ValueError as e:
            return str(e)

        kindle = await self._kindle_email()
        if not kindle:
            return (
                "No Kindle address is saved yet. Ask the user to add their Send-to-Kindle address "
                "(…@kindle.com, found in Amazon under Manage Your Content and Devices > Preferences > "
                "Personal Document Settings) in Butler's Settings > Account."
            )
        token = await self._get_token()
        if not token:
            return "Google is not connected. Please connect it in the Settings page of the Butler app."
        if GMAIL_SEND_SCOPE not in await self._granted_scopes():
            return (
                "Sending to Kindle uses the user's Gmail, which needs extra Google permission. "
                "Ask them to tap Reconnect next to Google in Settings, then try again."
            )

        # Prefer a copy Amazon accepts as-is; convert only when there isn't one.
        siblings = [p for p in path.parent.iterdir() if p.is_file() and p.stem == path.stem]
        source = _best_copy(siblings) if path.suffix.lower() in CONVERTIBLE else path
        ext = source.suffix.lower()
        library = self.library.resolve()
        converted = False
        if ext in CONVERTIBLE or (ext == ".epub" and fix_epub):
            try:
                data = await self._convert(str(source.relative_to(library)), "epub")
            except RuntimeError as e:
                return f"Couldn't convert “{_title(source)}” to EPUB: {e}"
            filename, mime, converted = f"{source.stem}.epub", SENDABLE[".epub"], True
        else:
            if source.stat().st_size > MAX_ATTACHMENT_BYTES:
                return _too_big(source.stat().st_size)
            data = source.read_bytes()
            filename, mime = source.name, SENDABLE[ext]

        if len(data) > MAX_ATTACHMENT_BYTES:
            return _too_big(len(data))

        title = _title(source)
        raw = build_mime(
            [kindle], title, "Sent from Butler.",
            attachments=[(_safe_filename(filename), data, mime)],
        )
        try:
            await send_mime(token, raw)
        except GmailSendError as e:
            return f"Gmail didn't send it: {e}"

        how = " (converted to EPUB)" if converted else ""
        size = _size(len(data))
        tip = _APPROVED_SENDER_TIP.format(sender=await self._sender())
        return f"Sent “{title}”{how}, {size}, to {kindle}. {tip}"


def _best_copy(copies: list[Path]) -> Path:
    def rank(p: Path) -> int:
        ext = p.suffix.lower()
        return FORMAT_PREFERENCE.index(ext) if ext in FORMAT_PREFERENCE else len(FORMAT_PREFERENCE)

    usable = [p for p in copies if p.suffix.lower() in SENDABLE or p.suffix.lower() in CONVERTIBLE]
    return min(usable or copies, key=rank)


def _size(n: int) -> str:
    return f"{n / (1024 * 1024):.1f} MB" if n >= 1024 * 1024 else f"{max(1, round(n / 1024))} KB"


def _too_big(size: int) -> str:
    return (
        f"That book is {size / (1024 * 1024):.0f} MB, too large to email (Gmail's limit works out at "
        f"about {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB for the file). Use the Send to Kindle app or "
        "website for this one."
    )


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w.\- ]+", "", name).strip() or "book.epub"
    return cleaned[:120]
