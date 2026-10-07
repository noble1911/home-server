"""Tests for the ebook-convert sidecar's guards (no Calibre needed).

Run with: pytest butler/ebook_convert/test_server.py -v
The real conversions are exercised by building the image and calling /convert.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import server


@pytest.fixture
def library(tmp_path: Path) -> Path:
    (tmp_path / "Weir").mkdir()
    (tmp_path / "Weir" / "Martian.azw3").write_bytes(b"azw3")
    (tmp_path / "cover.jpg").write_bytes(b"jpg")
    (tmp_path.parent / "secret.mobi").write_bytes(b"outside")
    return tmp_path


class TestResolveBook:
    def test_finds_a_library_book(self, library):
        assert server.resolve_book("Weir/Martian.azw3", library) == (library / "Weir" / "Martian.azw3").resolve()

    @pytest.mark.parametrize("path,status", [
        ("../secret.mobi", 403),
        ("Weir/../../secret.mobi", 403),
        ("/etc/passwd", 400),
        ("", 400),
        ("Weir/missing.epub", 404),
        ("cover.jpg", 415),
    ])
    def test_refusals(self, library, path, status):
        with pytest.raises(server.ConvertError) as e:
            server.resolve_book(path, library)
        assert e.value.status == status

    def test_symlink_out_of_the_library_is_refused(self, library):
        (library / "escape.mobi").symlink_to(library.parent / "secret.mobi")
        with pytest.raises(server.ConvertError) as e:
            server.resolve_book("escape.mobi", library)
        assert e.value.status == 403

    def test_too_large(self, library):
        with patch.object(server, "MAX_INPUT_BYTES", 2), pytest.raises(server.ConvertError) as e:
            server.resolve_book("Weir/Martian.azw3", library)
        assert e.value.status == 413


class TestConvert:
    def test_runs_ebook_convert_headless_and_returns_the_output(self, library):
        def fake_run(cmd, **kwargs):
            Path(cmd[2]).write_bytes(b"PK-epub")
            assert cmd[0] == "ebook-convert" and cmd[2].endswith(".epub")
            assert kwargs["env"]["QT_QPA_PLATFORM"] == "offscreen"
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch.object(server.subprocess, "run", side_effect=fake_run):
            assert server.convert(library / "Weir" / "Martian.azw3") == b"PK-epub"

    def test_drm_is_explained(self, library):
        failed = subprocess.CompletedProcess([], 1, "", "Traceback...\ncalibre.ebooks.DRMError: This file is locked with DRM")
        with patch.object(server.subprocess, "run", return_value=failed), pytest.raises(server.ConvertError) as e:
            server.convert(library / "Weir" / "Martian.azw3")
        assert e.value.status == 422 and "DRM-protected" in str(e.value)

    def test_timeout(self, library):
        with patch.object(server.subprocess, "run", side_effect=subprocess.TimeoutExpired("ebook-convert", 1)), \
             pytest.raises(server.ConvertError) as e:
            server.convert(library / "Weir" / "Martian.azw3")
        assert e.value.status == 504

    def test_unsupported_output(self, library):
        with pytest.raises(server.ConvertError) as e:
            server.convert(library / "Weir" / "Martian.azw3", "mobi")
        assert e.value.status == 400
