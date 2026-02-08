"""Media file management tool for Butler.

Provides safe, scoped read-write access to HomeServer media directories.
Supports listing, searching, renaming, deleting, and quality scanning
of files on the external drive.

Usage:
    The tool is automatically registered when MEDIA_FILES_ENABLED is true.
    Uses the external drive mount at /mnt/external.

Example:
    tool = MediaFilesTool(root_path="/mnt/external")
    result = await tool.execute(action="list", path="Media/Movies")

    # Quality scan
    result = await tool.execute(action="scan_quality", path="Media/Movies")

    # When shutting down (no resources to release)
    await tool.close()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from .base import Tool

logger = logging.getLogger(__name__)

# Directories allowed under the external drive root.
# Everything else (Backups, Documents, Photos) is off-limits.
ALLOWED_ROOTS = ("Media", "Books", "Downloads")

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".ts", ".mov"}

# Limits to prevent overwhelming responses
MAX_SEARCH_RESULTS = 50
MAX_SCAN_FILES = 100
MAX_LIST_DEPTH = 3


def _format_bytes(n: int | float) -> str:
    """Format byte count into a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class MediaFilesTool(Tool):
    """Browse, search, rename, delete, and scan media files on the server.

    All operations are scoped to allowed directories (Media/, Books/,
    Downloads/) under the external drive mount. Path traversal is
    blocked at every entry point.
    """

    def __init__(self, root_path: str = "/mnt/external"):
        self._root = Path(root_path)

    async def close(self) -> None:
        """No resources to release."""

    # -- Tool interface -------------------------------------------------------

    @property
    def name(self) -> str:
        return "media_files"

    @property
    def description(self) -> str:
        return (
            "Manage media files on the home server's external drive. "
            "Can list directories, search by filename, get detailed file info "
            "(including video resolution/codec via ffprobe), rename files, "
            "delete files/folders, and scan for video quality.\n\n"
            "Allowed directories: Media/ (Movies, TV, Anime, Music), "
            "Books/ (eBooks, Audiobooks), Downloads/ (Complete, Incomplete).\n\n"
            "Naming conventions:\n"
            "  Movies: Movie Name (Year)/Movie Name (Year).ext\n"
            "  TV: Show Name/Season XX/Show Name - SXXEXX - Episode Name.ext\n"
            "  Anime: Same as TV\n\n"
            "IMPORTANT: Always confirm with the user before deleting files."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list", "search", "info",
                        "rename", "delete", "scan_quality",
                    ],
                    "description": (
                        "list: List directory contents (path, depth). "
                        "search: Find files by glob pattern (pattern, path). "
                        "info: Detailed file metadata inc. ffprobe for video (path). "
                        "rename: Rename a file or directory (path, new_name). "
                        "delete: Delete a file or directory (path, recursive). "
                        "scan_quality: Batch video quality scan (path, max_resolution)."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path under the media root, e.g. 'Media/Movies' "
                        "or 'Books/eBooks/Brandon Sanderson'."
                    ),
                },
                "depth": {
                    "type": "integer",
                    "description": "Directory listing depth (1-3, default 1).",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern for search, e.g. '*Sanderson*' or '*.mkv'.",
                },
                "new_name": {
                    "type": "string",
                    "description": "New filename for rename (name only, no path separators).",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "For delete: remove directory tree (default false).",
                },
                "max_resolution": {
                    "type": "integer",
                    "description": (
                        "For scan_quality: filter videos below this vertical resolution "
                        "(e.g. 720 to find sub-720p files)."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")

        try:
            if action == "list":
                return await self._list(
                    kwargs.get("path", ""),
                    kwargs.get("depth", 1),
                )
            elif action == "search":
                return await self._search(
                    kwargs.get("pattern", ""),
                    kwargs.get("path", ""),
                )
            elif action == "info":
                return await self._info(kwargs.get("path", ""))
            elif action == "rename":
                return await self._rename(
                    kwargs.get("path", ""),
                    kwargs.get("new_name", ""),
                )
            elif action == "delete":
                return await self._delete(
                    kwargs.get("path", ""),
                    kwargs.get("recursive", False),
                )
            elif action == "scan_quality":
                return await self._scan_quality(
                    kwargs.get("path", ""),
                    kwargs.get("max_resolution"),
                )
            else:
                return f"Error: Unknown action '{action}'."
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.exception("media_files action '%s' failed", action)
            return f"Error: {e}"

    # -- Path safety ----------------------------------------------------------

    def _resolve_safe(self, relative_path: str) -> Path:
        """Resolve a relative path safely within the allowed root.

        Raises ValueError if:
        - The path escapes the root directory
        - The path doesn't start with an allowed subdirectory
        """
        if not relative_path:
            raise ValueError(
                "Path is required. Use one of: Media/, Books/, Downloads/"
            )

        # Normalise and resolve
        full = (self._root / relative_path).resolve()
        root_resolved = self._root.resolve()

        if not str(full).startswith(str(root_resolved) + os.sep) and full != root_resolved:
            raise ValueError("Path is outside the allowed media root.")

        # Check the first directory component is allowed
        try:
            rel = full.relative_to(root_resolved)
        except ValueError:
            raise ValueError("Path is outside the allowed media root.")

        top_dir = rel.parts[0] if rel.parts else ""
        if top_dir not in ALLOWED_ROOTS:
            raise ValueError(
                f"Access denied: '{top_dir}/' is not an allowed directory. "
                f"Allowed: {', '.join(r + '/' for r in ALLOWED_ROOTS)}"
            )

        return full

    # -- Actions --------------------------------------------------------------

    async def _list(self, path: str, depth: int) -> str:
        """List directory contents up to a given depth."""
        safe_path = self._resolve_safe(path)

        if not safe_path.is_dir():
            return f"Error: '{path}' is not a directory."

        depth = max(1, min(depth, MAX_LIST_DEPTH))

        lines: list[str] = [f"Contents of {path}/ (depth={depth}):\n"]
        count = 0

        def _walk(p: Path, current_depth: int, prefix: str) -> None:
            nonlocal count
            if current_depth > depth:
                return

            try:
                entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
            except PermissionError:
                lines.append(f"{prefix}[permission denied]")
                return

            for entry in entries:
                count += 1
                if count > 500:
                    lines.append(f"{prefix}... (truncated at 500 entries)")
                    return

                if entry.is_dir():
                    # Count children for context
                    try:
                        child_count = sum(1 for _ in entry.iterdir())
                    except PermissionError:
                        child_count = "?"
                    lines.append(f"{prefix}{entry.name}/  ({child_count} items)")
                    if current_depth < depth:
                        _walk(entry, current_depth + 1, prefix + "  ")
                else:
                    size = _format_bytes(entry.stat().st_size)
                    lines.append(f"{prefix}{entry.name}  ({size})")

        _walk(safe_path, 1, "  ")

        if count == 0:
            lines.append("  (empty directory)")

        return "\n".join(lines)

    async def _search(self, pattern: str, path: str) -> str:
        """Search for files matching a glob pattern."""
        if not pattern:
            return "Error: 'pattern' is required for search."

        # Default to searching all allowed roots if no path given
        search_roots: list[Path] = []
        if path:
            search_roots.append(self._resolve_safe(path))
        else:
            for root_name in ALLOWED_ROOTS:
                root_dir = (self._root / root_name).resolve()
                if root_dir.is_dir():
                    search_roots.append(root_dir)

        results: list[tuple[str, int, bool]] = []  # (rel_path, size, is_dir)
        root_resolved = self._root.resolve()

        for search_root in search_roots:
            try:
                for match in search_root.rglob(pattern):
                    if len(results) >= MAX_SEARCH_RESULTS:
                        break
                    try:
                        rel = match.relative_to(root_resolved)
                        size = match.stat().st_size if match.is_file() else 0
                        results.append((str(rel), size, match.is_dir()))
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                continue

            if len(results) >= MAX_SEARCH_RESULTS:
                break

        if not results:
            return f"No files matching '{pattern}' found."

        lines = [f"Found {len(results)} result(s) for '{pattern}':\n"]
        for rel_path, size, is_dir in sorted(results):
            if is_dir:
                lines.append(f"  {rel_path}/")
            else:
                lines.append(f"  {rel_path}  ({_format_bytes(size)})")

        if len(results) >= MAX_SEARCH_RESULTS:
            lines.append(f"\n  (limited to {MAX_SEARCH_RESULTS} results)")

        return "\n".join(lines)

    async def _info(self, path: str) -> str:
        """Get detailed info about a file, including ffprobe for video."""
        safe_path = self._resolve_safe(path)

        if not safe_path.exists():
            return f"Error: '{path}' does not exist."

        stat = safe_path.stat()
        lines = [f"File: {path}"]

        if safe_path.is_dir():
            # Count contents
            file_count = 0
            total_size = 0
            for child in safe_path.rglob("*"):
                if child.is_file():
                    file_count += 1
                    try:
                        total_size += child.stat().st_size
                    except OSError:
                        pass
            lines.append(f"Type: Directory")
            lines.append(f"Files: {file_count}")
            lines.append(f"Total size: {_format_bytes(total_size)}")
        else:
            lines.append(f"Type: File")
            lines.append(f"Size: {_format_bytes(stat.st_size)}")
            lines.append(f"Extension: {safe_path.suffix or '(none)'}")

            # Video files: run ffprobe
            if safe_path.suffix.lower() in VIDEO_EXTENSIONS:
                probe = await self._ffprobe(safe_path)
                if probe:
                    lines.append(f"Resolution: {probe.get('width', '?')}x{probe.get('height', '?')}")
                    lines.append(f"Video codec: {probe.get('video_codec', '?')}")
                    if probe.get("audio_codec"):
                        lines.append(f"Audio codec: {probe['audio_codec']}")
                    if probe.get("duration"):
                        dur = float(probe["duration"])
                        h, m, s = int(dur // 3600), int((dur % 3600) // 60), int(dur % 60)
                        lines.append(f"Duration: {h}h {m}m {s}s" if h else f"Duration: {m}m {s}s")
                    if probe.get("bitrate"):
                        br = int(probe["bitrate"]) / 1_000_000
                        lines.append(f"Bitrate: {br:.1f} Mbps")
                else:
                    lines.append("(ffprobe unavailable or failed)")

        return "\n".join(lines)

    async def _rename(self, path: str, new_name: str) -> str:
        """Rename a file or directory (same parent directory)."""
        if not new_name:
            return "Error: 'new_name' is required for rename."

        # Block path separators and traversal in new_name
        if "/" in new_name or "\\" in new_name or ".." in new_name:
            return "Error: new_name must be a simple filename (no '/', '\\', or '..')."

        safe_path = self._resolve_safe(path)

        if not safe_path.exists():
            return f"Error: '{path}' does not exist."

        new_path = safe_path.parent / new_name

        if new_path.exists():
            return f"Error: '{new_name}' already exists in that directory."

        safe_path.rename(new_path)

        old_name = safe_path.name
        return f"Renamed: {old_name} -> {new_name}"

    async def _delete(self, path: str, recursive: bool) -> str:
        """Delete a file or directory."""
        safe_path = self._resolve_safe(path)

        if not safe_path.exists():
            return f"Error: '{path}' does not exist."

        if safe_path.is_file():
            size = safe_path.stat().st_size
            safe_path.unlink()
            return f"Deleted file: {path} (freed {_format_bytes(size)})"

        # Directory
        if not recursive:
            # Only delete if empty
            if any(safe_path.iterdir()):
                return (
                    f"Error: '{path}' is not empty. "
                    "Use recursive=true to delete the entire directory tree."
                )
            safe_path.rmdir()
            return f"Deleted empty directory: {path}"

        # Recursive delete — calculate total size first
        total_size = 0
        file_count = 0
        for child in safe_path.rglob("*"):
            if child.is_file():
                file_count += 1
                try:
                    total_size += child.stat().st_size
                except OSError:
                    pass

        shutil.rmtree(safe_path)
        return (
            f"Deleted directory: {path} "
            f"({file_count} files, freed {_format_bytes(total_size)})"
        )

    async def _scan_quality(self, path: str, max_resolution: int | None) -> str:
        """Scan video files and report quality information."""
        safe_path = self._resolve_safe(path)

        if not safe_path.is_dir():
            return f"Error: '{path}' is not a directory."

        # Collect video files
        video_files: list[Path] = []
        for child in safe_path.rglob("*"):
            if child.is_file() and child.suffix.lower() in VIDEO_EXTENSIONS:
                video_files.append(child)
                if len(video_files) >= MAX_SCAN_FILES:
                    break

        if not video_files:
            return f"No video files found in {path}."

        # Run ffprobe on all files concurrently (bounded)
        sem = asyncio.Semaphore(8)

        async def _probe_with_sem(f: Path) -> tuple[Path, dict | None]:
            async with sem:
                return (f, await self._ffprobe(f))

        tasks = [_probe_with_sem(f) for f in video_files]
        results = await asyncio.gather(*tasks)

        root_resolved = self._root.resolve()
        entries: list[tuple[str, int, str, int]] = []  # (rel_path, height, codec, size)

        for file_path, probe in results:
            if not probe:
                continue
            height = probe.get("height", 0)
            if max_resolution and height >= max_resolution:
                continue
            rel = str(file_path.relative_to(root_resolved))
            codec = probe.get("video_codec", "?")
            size = file_path.stat().st_size
            entries.append((rel, height, codec, size))

        if not entries:
            if max_resolution:
                return f"No video files below {max_resolution}p found in {path}."
            return f"Could not probe any video files in {path}."

        # Sort by resolution ascending
        entries.sort(key=lambda e: e[1])

        header = f"Video quality scan of {path}"
        if max_resolution:
            header += f" (below {max_resolution}p)"
        header += f" — {len(entries)} file(s):\n"

        lines = [header]
        for rel_path, height, codec, size in entries:
            res_label = f"{height}p" if height else "unknown"
            lines.append(f"  {res_label:>8}  {codec:<8}  {_format_bytes(size):>10}  {rel_path}")

        if len(video_files) >= MAX_SCAN_FILES:
            lines.append(f"\n  (limited to {MAX_SCAN_FILES} files)")

        return "\n".join(lines)

    # -- ffprobe helper -------------------------------------------------------

    async def _ffprobe(self, file_path: Path) -> dict | None:
        """Run ffprobe and return video metadata.

        Returns dict with keys: width, height, video_codec, audio_codec,
        duration, bitrate. Returns None on failure.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)

            if proc.returncode != 0:
                return None

            data = json.loads(stdout.decode())
        except (asyncio.TimeoutError, json.JSONDecodeError, FileNotFoundError):
            return None

        result: dict[str, Any] = {}

        # Extract video stream info
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                result["width"] = stream.get("width", 0)
                result["height"] = stream.get("height", 0)
                result["video_codec"] = stream.get("codec_name", "")
                break

        # Extract audio stream info
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "audio":
                result["audio_codec"] = stream.get("codec_name", "")
                break

        # Extract format-level info
        fmt = data.get("format", {})
        result["duration"] = fmt.get("duration")
        result["bitrate"] = fmt.get("bit_rate")

        return result if (result.get("video_codec") or result.get("width")) else None
