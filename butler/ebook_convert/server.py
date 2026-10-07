"""Tiny HTTP wrapper around Calibre's ebook-convert, for Butler's Send to Kindle (#213).

    POST /convert   {"path": "<relative to the library>", "to": "epub"}
        200 -> the converted file (application/epub+zip)
        4xx/5xx -> {"error": "<user-facing reason>"}
    GET  /healthz   {"ok": true}

The ebook library is mounted read-only; each conversion runs in its own temp
dir, which is removed afterwards. One conversion at a time — Calibre is heavy,
and nobody needs two books on their Kindle in the same second. Standard
library only, so the image is just Debian's calibre package plus this file.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ebook-convert")

BOOKS_DIR = Path(os.environ.get("BOOKS_DIR", "/books"))
TOKEN = os.environ.get("CONVERT_TOKEN", "")
TIMEOUT_S = int(os.environ.get("CONVERT_TIMEOUT", "300"))
MAX_INPUT_BYTES = 200 * 1024 * 1024

INPUT_EXTENSIONS = {
    ".epub", ".mobi", ".azw", ".azw3", ".prc", ".pdb", ".fb2", ".lit",
    ".rtf", ".txt", ".docx", ".odt", ".htmlz", ".txtz",
}
OUTPUTS = {"epub": ("application/epub+zip", ".epub")}

_one_at_a_time = threading.Lock()


class ConvertError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def resolve_book(relative: str, root: Path = BOOKS_DIR) -> Path:
    """The library file for ``relative``, refusing anything outside the library."""
    if not relative or relative.startswith(("/", "\\")):
        raise ConvertError(400, "Give the book's path relative to the library.")
    base = root.resolve()
    full = (base / relative).resolve()
    if not full.is_relative_to(base):
        raise ConvertError(403, "That path is outside the ebook library.")
    if not full.is_file():
        raise ConvertError(404, f"No such book: {relative}")
    if full.suffix.lower() not in INPUT_EXTENSIONS:
        raise ConvertError(415, f"Can't convert {full.suffix or 'files without an extension'}.")
    if full.stat().st_size > MAX_INPUT_BYTES:
        raise ConvertError(413, "That file is too large to convert.")
    return full


def _failure_reason(stderr: str) -> str:
    text = stderr.strip()
    if "DRM" in text:
        return "This book is DRM-protected, so it can't be converted."
    last = text.splitlines()[-1] if text else "no output"
    return f"Calibre couldn't convert this book ({last[:200]})."


def convert(source: Path, fmt: str = "epub") -> bytes:
    if fmt not in OUTPUTS:
        raise ConvertError(400, f"Unsupported output format: {fmt}")
    _, ext = OUTPUTS[fmt]
    with tempfile.TemporaryDirectory(prefix="convert-") as tmp:
        out = Path(tmp) / f"book{ext}"
        env = {**os.environ, "HOME": tmp, "QT_QPA_PLATFORM": "offscreen"}
        with _one_at_a_time:
            log.info("Converting %s -> %s", source.name, fmt)
            try:
                proc = subprocess.run(
                    ["ebook-convert", str(source), str(out)],
                    capture_output=True, text=True, timeout=TIMEOUT_S, env=env,
                )
            except subprocess.TimeoutExpired:
                raise ConvertError(504, "Converting took too long.") from None
        if proc.returncode != 0 or not out.is_file():
            log.warning("ebook-convert failed (%s): %s", proc.returncode, proc.stderr[-500:])
            raise ConvertError(422, _failure_reason(proc.stderr))
        return out.read_bytes()


class Handler(BaseHTTPRequestHandler):
    server_version = "ebook-convert/1"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/convert":
            return self._json(404, {"error": "not found"})
        if TOKEN and not hmac.compare_digest(self.headers.get("X-Convert-Token", ""), TOKEN):
            return self._json(401, {"error": "bad token"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(min(length, 64 * 1024)) or b"{}")
            fmt = req.get("to", "epub")
            data = convert(resolve_book(str(req.get("path", ""))), fmt)
        except ConvertError as e:
            return self._json(e.status, {"error": str(e)})
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "Expected JSON: {\"path\": ..., \"to\": \"epub\"}"})
        except Exception as e:  # keep serving after an unexpected failure
            log.exception("Conversion failed")
            return self._json(500, {"error": f"Conversion failed: {e}"})
        self._send(200, data, OUTPUTS[fmt][0])

    def log_message(self, fmt: str, *args) -> None:
        log.info("%s %s", self.address_string(), fmt % args)


def main() -> None:
    if not TOKEN:
        log.warning("CONVERT_TOKEN is not set: any container on the network can request conversions")
    port = int(os.environ.get("PORT", "8080"))
    log.info("Listening on :%d, library %s", port, BOOKS_DIR)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
