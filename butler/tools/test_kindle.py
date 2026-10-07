"""Tests for Send to Kindle (#213). Uses a temp library; no network, no OAuth.

Run with: pytest butler/tools/test_kindle.py -v
"""

from __future__ import annotations

import email
from email import policy
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .gmail import GmailSendError
from .kindle import SendToKindleTool

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
KINDLE = "ron_123@kindle.com"


@pytest.fixture
def library(tmp_path: Path) -> Path:
    weir = tmp_path / "Andy Weir"
    weir.mkdir()
    (weir / "Project_Hail_Mary.epub").write_bytes(b"PK-epub-hail-mary")
    (weir / "Project_Hail_Mary.mobi").write_bytes(b"mobi-hail-mary")
    (weir / "The.Martian.azw3").write_bytes(b"azw3-martian")
    (tmp_path / "Dune - Frank Herbert.pdf").write_bytes(b"%PDF-dune")
    (tmp_path / "cover.jpg").write_bytes(b"jpg")
    return tmp_path


def _tool(library: Path, *, kindle=KINDLE, scopes=(SEND_SCOPE,), token="tok"):
    t = SendToKindleTool(db_pool=MagicMock(), user_id="ron", library_root=library)
    t._kindle_email = AsyncMock(return_value=kindle)
    t._granted_scopes = AsyncMock(return_value=set(scopes))
    t._get_token = AsyncMock(return_value=token)
    t._sender = AsyncMock(return_value="ron@gmail.com")
    t._convert = AsyncMock(return_value=b"PK-converted-epub")
    return t


def _sent_message(send_mock) -> email.message.EmailMessage:
    raw = send_mock.call_args.args[1]
    return email.message_from_bytes(raw, policy=policy.default)


class TestSchema:
    def test_there_is_no_recipient_parameter(self, library):
        props = _tool(library).parameters["properties"]
        assert set(props) == {"action", "query", "path", "fix_epub"}


class TestFind:
    @pytest.mark.asyncio
    async def test_groups_formats_and_points_at_the_best_copy(self, library):
        out = await _tool(library).execute(action="find", query="hail mary")
        assert "Found 1 book(s)" in out
        assert "[EPUB, MOBI" in out
        assert "path: Andy Weir/Project_Hail_Mary.epub" in out

    @pytest.mark.asyncio
    async def test_matches_author_folder_and_word_prefixes(self, library):
        out = await _tool(library).execute(action="find", query="weir mart")
        assert "path: Andy Weir/The.Martian.azw3" in out

    @pytest.mark.asyncio
    async def test_no_match_suggests_downloading(self, library):
        out = await _tool(library).execute(action="find", query="wuthering heights")
        assert "No books matching" in out and "download" in out

    @pytest.mark.asyncio
    async def test_ignores_non_ebooks(self, library):
        assert "No books matching" in await _tool(library).execute(action="find", query="cover")

    @pytest.mark.asyncio
    async def test_missing_library(self, tmp_path):
        out = await _tool(tmp_path / "nope").execute(action="find", query="dune")
        assert "isn't available" in out


class TestSend:
    @pytest.mark.asyncio
    async def test_epub_goes_as_is_to_the_saved_kindle_address_only(self, library):
        t = _tool(library)
        with patch("tools.gmail.send_mime", AsyncMock(return_value={"id": "s1"})) as send:
            out = await t.execute(action="send", path="Andy Weir/Project_Hail_Mary.epub")
        assert out.startswith("Sent “Project Hail Mary”") and KINDLE in out and "ron@gmail.com" in out
        t._convert.assert_not_awaited()
        msg = _sent_message(send)
        assert msg["To"] == KINDLE and msg["Cc"] is None and msg["Bcc"] is None
        att = next(msg.iter_attachments())
        assert att.get_filename() == "Project_Hail_Mary.epub"
        assert att.get_content_type() == "application/epub+zip"
        assert att.get_content() == b"PK-epub-hail-mary"

    @pytest.mark.asyncio
    async def test_mobi_with_an_epub_alongside_sends_the_epub(self, library):
        t = _tool(library)
        with patch("tools.gmail.send_mime", AsyncMock(return_value={})) as send:
            await t.execute(action="send", path="Andy Weir/Project_Hail_Mary.mobi")
        t._convert.assert_not_awaited()
        assert next(_sent_message(send).iter_attachments()).get_filename() == "Project_Hail_Mary.epub"

    @pytest.mark.asyncio
    async def test_azw3_is_converted_to_epub(self, library):
        t = _tool(library)
        with patch("tools.gmail.send_mime", AsyncMock(return_value={})) as send:
            out = await t.execute(action="send", path="Andy Weir/The.Martian.azw3")
        t._convert.assert_awaited_once_with("Andy Weir/The.Martian.azw3", "epub")
        att = next(_sent_message(send).iter_attachments())
        assert att.get_filename() == "The.Martian.epub" and att.get_content() == b"PK-converted-epub"
        assert "(converted to EPUB)" in out

    @pytest.mark.asyncio
    async def test_fix_epub_reprocesses_through_calibre(self, library):
        t = _tool(library)
        with patch("tools.gmail.send_mime", AsyncMock(return_value={})):
            await t.execute(action="send", path="Andy Weir/Project_Hail_Mary.epub", fix_epub=True)
        t._convert.assert_awaited_once_with("Andy Weir/Project_Hail_Mary.epub", "epub")

    @pytest.mark.asyncio
    async def test_pdf_goes_as_is(self, library):
        t = _tool(library)
        with patch("tools.gmail.send_mime", AsyncMock(return_value={})) as send:
            await t.execute(action="send", path="Dune - Frank Herbert.pdf")
        assert next(_sent_message(send).iter_attachments()).get_content_type() == "application/pdf"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,needle", [
        ("../../etc/passwd", "outside the ebook library"),
        ("/etc/passwd", "outside the ebook library"),
        ("cover.jpg", "isn't an ebook format"),
        ("Missing.epub", "No such book"),
        ("", "Give the book's path"),
    ])
    async def test_refuses_anything_but_library_ebooks(self, library, path, needle):
        t = _tool(library)
        with patch("tools.gmail.send_mime", AsyncMock()) as send:
            out = await t.execute(action="send", path=path)
        assert needle in out
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_kindle_address_saved(self, library):
        t = _tool(library, kindle=None)
        with patch("tools.gmail.send_mime", AsyncMock()) as send:
            out = await t.execute(action="send", path="Dune - Frank Herbert.pdf")
        assert "No Kindle address" in out and "Settings > Account" in out
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_needs_gmail_send_scope(self, library):
        t = _tool(library, scopes=())
        out = await t.execute(action="send", path="Dune - Frank Herbert.pdf")
        assert "Reconnect" in out

    @pytest.mark.asyncio
    async def test_too_big_for_gmail(self, library):
        t = _tool(library)
        with patch("tools.kindle.MAX_ATTACHMENT_BYTES", 4), \
             patch("tools.gmail.send_mime", AsyncMock()) as send:
            out = await t.execute(action="send", path="Dune - Frank Herbert.pdf")
        assert "too large to email" in out
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_conversion_failure_is_explained(self, library):
        t = _tool(library)
        t._convert = AsyncMock(side_effect=RuntimeError("This book is DRM-protected, so it can't be converted."))
        out = await t.execute(action="send", path="Andy Weir/The.Martian.azw3")
        assert "Couldn't convert" in out and "DRM" in out

    @pytest.mark.asyncio
    async def test_gmail_refusal_is_explained(self, library):
        t = _tool(library)
        with patch("tools.gmail.send_mime", AsyncMock(side_effect=GmailSendError("too large"))):
            out = await t.execute(action="send", path="Dune - Frank Herbert.pdf")
        assert "Gmail didn't send it: too large" == out


class TestConverterClient:
    @pytest.mark.asyncio
    async def test_posts_path_and_token(self, library):
        t = SendToKindleTool(db_pool=MagicMock(), user_id="ron", library_root=library)
        resp = MagicMock(status=200)
        resp.read = AsyncMock(return_value=b"EPUB")
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=resp)
        ctx.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=ctx)
        cls = MagicMock()
        cls.return_value.__aenter__ = AsyncMock(return_value=session)
        cls.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("tools.kindle.aiohttp.ClientSession", cls), \
             patch("api.config.settings.ebook_convert_url", "http://ebook-convert:8080"), \
             patch("api.config.settings.ebook_convert_token", "s3cret"):
            assert await t._convert("Andy Weir/The.Martian.azw3") == b"EPUB"
        assert session.post.call_args.args[0] == "http://ebook-convert:8080/convert"
        assert session.post.call_args.kwargs["json"] == {"path": "Andy Weir/The.Martian.azw3", "to": "epub"}
        assert session.post.call_args.kwargs["headers"] == {"X-Convert-Token": "s3cret"}

    @pytest.mark.asyncio
    async def test_converter_error_message_is_passed_on(self, library):
        t = SendToKindleTool(db_pool=MagicMock(), user_id="ron", library_root=library)
        resp = MagicMock(status=422)
        resp.json = AsyncMock(return_value={"error": "This book is DRM-protected, so it can't be converted."})
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=resp)
        ctx.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=ctx)
        cls = MagicMock()
        cls.return_value.__aenter__ = AsyncMock(return_value=session)
        cls.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("tools.kindle.aiohttp.ClientSession", cls), pytest.raises(RuntimeError, match="DRM"):
            await t._convert("x.azw3")
