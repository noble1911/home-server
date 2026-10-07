"""Tests for Gmail drafting/sending (#212). No network, no OAuth.

Run with: pytest butler/tools/test_gmail_send.py -v
"""

from __future__ import annotations

import email
from email import policy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .gmail import (
    GmailSendError,
    GmailTool,
    _address_list,
    build_mime,
    execute_approved,
    send_mime,
)

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def _tool(*, can_read=True, can_send=True, scopes=(SEND_SCOPE,)):
    t = GmailTool(db_pool=MagicMock(), user_id="ron", can_read=can_read, can_send=can_send)
    t._get_token = AsyncMock(return_value="tok")
    t._granted_scopes = AsyncMock(return_value=set(scopes))
    t._account_email = AsyncMock(return_value="ron@gmail.com")
    return t


def _card(action_id="ap1"):
    return {"id": action_id, "kind": "gmail.send", "title": "Send email", "fields": [], "body": "",
            "status": "pending", "createdAt": "", "expiresAt": ""}


def _post_mock(status=200, body='{"id": "sent1"}'):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value={"id": "sent1"})
    resp.text = AsyncMock(return_value=body)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=ctx)
    cls = MagicMock()
    cls.return_value.__aenter__ = AsyncMock(return_value=session)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return cls, session


class TestCapabilities:
    def test_read_only_by_default(self):
        t = GmailTool(db_pool=MagicMock(), user_id="ron")
        assert t.parameters["properties"]["action"]["enum"] == ["list_recent", "search_emails", "read_email"]
        assert "body" not in t.parameters["properties"]

    def test_send_permission_adds_send_actions_and_says_approval(self):
        t = _tool()
        assert t.parameters["properties"]["action"]["enum"][-2:] == ["send_email", "reply_email"]
        assert "approve" in t.description.lower() and "never say it was sent" in t.description

    def test_send_only_user_cannot_read(self):
        t = _tool(can_read=False)
        assert t.parameters["properties"]["action"]["enum"] == ["send_email", "reply_email"]
        assert "query" not in t.parameters["properties"]

    @pytest.mark.asyncio
    async def test_read_only_user_cannot_send(self):
        t = _tool(can_send=False)
        assert "Unknown action" in await t.execute(action="send_email", to=["a@b.com"], body="hi")


class TestDraftSend:
    @pytest.mark.asyncio
    async def test_creates_a_pending_approval_and_sends_nothing(self):
        t = _tool()
        with patch("api.approvals.create_pending_action", AsyncMock(return_value=_card())) as create, \
             patch("tools.gmail.send_mime", AsyncMock()) as send:
            out = await t.execute(action="send_email", to=["Sam <sam@example.com>"], cc="jo@example.com",
                                  subject="Late", body="Running 10 minutes late")
        assert "waiting for the user's approval" in out and "ap1" in out
        send.assert_not_awaited()
        _, user, kind = create.call_args.args
        params, summary = create.call_args.kwargs["params"], create.call_args.kwargs["summary"]
        assert (user, kind) == ("ron", "gmail.send")
        assert params == {"to": ["sam@example.com"], "cc": ["jo@example.com"], "subject": "Late",
                          "body": "Running 10 minutes late"}
        assert summary["fields"][0] == ["To", "sam@example.com"]
        assert summary["body"] == "Running 10 minutes late"

    @pytest.mark.asyncio
    async def test_missing_scope_asks_to_reconnect(self):
        t = _tool(scopes=())
        with patch("api.approvals.create_pending_action", AsyncMock()) as create:
            out = await t.execute(action="send_email", to=["sam@example.com"], body="hi")
        assert "Reconnect" in out
        create.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kwargs,expect", [
        ({"body": "hi"}, "recipient"),
        ({"to": ["sam"], "body": "hi"}, "don't look like email addresses"),
        ({"to": ["sam@example.com"]}, "body"),
    ])
    async def test_validation(self, kwargs, expect):
        t = _tool()
        with patch("api.approvals.create_pending_action", AsyncMock()) as create:
            out = await t.execute(action="send_email", **kwargs)
        assert expect in out
        create.assert_not_awaited()


ORIGINAL = {
    "id": "m1", "threadId": "t1",
    "payload": {"headers": [
        {"name": "From", "value": "Sam <sam@example.com>"},
        {"name": "To", "value": "ron@gmail.com, jo@example.com"},
        {"name": "Cc", "value": "kim@example.com"},
        {"name": "Subject", "value": "Dinner?"},
        {"name": "Message-ID", "value": "<abc@mail.example.com>"},
        {"name": "References", "value": "<prev@mail.example.com>"},
    ]},
}


class TestDraftReply:
    @pytest.mark.asyncio
    async def test_threads_the_reply(self):
        t = _tool()
        t._fetch_message = AsyncMock(return_value=ORIGINAL)
        with patch("api.approvals.create_pending_action", AsyncMock(return_value=_card())) as create:
            await t.execute(action="reply_email", message_id="m1", body="Yes please")
        assert create.call_args.args[2] == "gmail.reply"
        p = create.call_args.kwargs["params"]
        assert p["to"] == ["sam@example.com"] and p["cc"] == []
        assert p["subject"] == "Re: Dinner?"
        assert p["thread_id"] == "t1"
        assert p["in_reply_to"] == "<abc@mail.example.com>"
        assert p["references"] == "<prev@mail.example.com> <abc@mail.example.com>"
        t._fetch_message.assert_awaited_once_with("tok", "m1", fmt="metadata")

    @pytest.mark.asyncio
    async def test_reply_all_includes_others_but_not_me(self):
        t = _tool()
        t._fetch_message = AsyncMock(return_value=ORIGINAL)
        with patch("api.approvals.create_pending_action", AsyncMock(return_value=_card())) as create:
            await t.execute(action="reply_email", message_id="m1", body="Yes", reply_all=True)
        assert create.call_args.kwargs["params"]["cc"] == ["jo@example.com", "kim@example.com"]

    @pytest.mark.asyncio
    async def test_replying_to_my_own_sent_mail_goes_to_its_recipients(self):
        mine = {"id": "m2", "threadId": "t2", "payload": {"headers": [
            {"name": "From", "value": "Ron <ron@gmail.com>"},
            {"name": "To", "value": "sam@example.com"},
            {"name": "Subject", "value": "Re: Dinner?"},
            {"name": "Message-ID", "value": "<x@y>"},
        ]}}
        t = _tool()
        t._fetch_message = AsyncMock(return_value=mine)
        with patch("api.approvals.create_pending_action", AsyncMock(return_value=_card())) as create:
            await t.execute(action="reply_email", message_id="m2", body="Forgot to say")
        p = create.call_args.kwargs["params"]
        assert p["to"] == ["sam@example.com"]
        assert p["subject"] == "Re: Dinner?"  # no "Re: Re:"


class TestMime:
    def test_headers_body_and_crlf(self):
        raw = build_mime(["sam@example.com"], "Late", "Running late", cc=["jo@example.com"],
                         in_reply_to="<abc@x>", references="<abc@x>")
        assert b"\r\n" in raw
        msg = email.message_from_bytes(raw, policy=policy.default)
        assert msg["To"] == "sam@example.com" and msg["Cc"] == "jo@example.com"
        assert msg["In-Reply-To"] == "<abc@x>" and msg["From"] is None
        assert msg.get_content().strip() == "Running late"

    def test_attachment(self):
        raw = build_mime(["me@kindle.com"], "Book", "Here it is",
                         attachments=[("book.epub", b"PK\x03\x04epubdata", "application/epub+zip")])
        msg = email.message_from_bytes(raw, policy=policy.default)
        att = next(msg.iter_attachments())
        assert att.get_filename() == "book.epub"
        assert att.get_content_type() == "application/epub+zip"
        assert att.get_content() == b"PK\x03\x04epubdata"

    def test_address_list(self):
        assert _address_list("a@x.com, B <b@y.com>") == ["a@x.com", "b@y.com"]
        assert _address_list(["a@x.com"]) == ["a@x.com"]
        assert _address_list(None) == []


class TestSendMime:
    @pytest.mark.asyncio
    async def test_multipart_upload_with_thread(self):
        cls, session = _post_mock()
        with patch("tools.gmail.aiohttp.ClientSession", cls):
            await send_mime("tok", b"RAW-MESSAGE", thread_id="t1")
        kwargs = session.post.call_args.kwargs
        assert kwargs["params"] == {"uploadType": "multipart"}
        ctype = kwargs["headers"]["Content-Type"]
        boundary = ctype.split("boundary=")[1]
        assert ctype.startswith("multipart/related")
        data = kwargs["data"]
        assert b'{"threadId": "t1"}' in data and b"Content-Type: message/rfc822\r\n\r\nRAW-MESSAGE" in data
        assert data.endswith(f"--{boundary}--\r\n".encode())

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status,needle", [(401, "expired"), (403, "Reconnect"), (413, "too large"), (500, "500")])
    async def test_errors_are_user_facing(self, status, needle):
        cls, _ = _post_mock(status=status, body="nope")
        with patch("tools.gmail.aiohttp.ClientSession", cls), pytest.raises(GmailSendError, match=needle):
            await send_mime("tok", b"x")


class TestExecuteApproved:
    @pytest.mark.asyncio
    async def test_sends_the_stored_draft(self):
        params = {"to": ["sam@example.com"], "cc": [], "subject": "Late", "body": "Running late"}
        with patch("api.oauth.get_valid_token", AsyncMock(return_value="tok")), \
             patch("tools.gmail.send_mime", AsyncMock(return_value={"id": "s1"})) as send:
            out = await execute_approved(MagicMock(), "ron", "gmail.send", params)
        assert out == "Email sent to sam@example.com."
        raw = send.call_args.args[1]
        assert b"Subject: Late" in raw and send.call_args.kwargs["thread_id"] is None

    @pytest.mark.asyncio
    async def test_gmail_refusal_becomes_approval_error(self):
        from api.approvals import ApprovalError

        params = {"to": ["sam@example.com"], "subject": "x", "body": "y", "thread_id": "t1"}
        with patch("api.oauth.get_valid_token", AsyncMock(return_value="tok")), \
             patch("tools.gmail.send_mime", AsyncMock(side_effect=GmailSendError("Reconnect please"))):
            with pytest.raises(ApprovalError, match="Reconnect please"):
                await execute_approved(MagicMock(), "ron", "gmail.reply", params)

    @pytest.mark.asyncio
    async def test_disconnected_google_is_retryable(self):
        from api.approvals import ApprovalRetryable

        with patch("api.oauth.get_valid_token", AsyncMock(return_value=None)), \
             pytest.raises(ApprovalRetryable, match="Reconnect"):
            await execute_approved(MagicMock(), "ron", "gmail.send", {"to": ["a@b.com"], "body": "x"})

    @pytest.mark.asyncio
    async def test_rejected_before_sending_is_retryable(self):
        from api.approvals import ApprovalRetryable

        with patch("api.oauth.get_valid_token", AsyncMock(return_value="tok")), \
             patch("tools.gmail.send_mime", AsyncMock(side_effect=GmailSendError("Reconnect", retryable=True))), \
             pytest.raises(ApprovalRetryable):
            await execute_approved(MagicMock(), "ron", "gmail.send", {"to": ["a@b.com"], "body": "x"})

    @pytest.mark.asyncio
    async def test_never_connected_is_retryable_but_timeout_is_final(self):
        import aiohttp

        from api.approvals import ApprovalError, ApprovalRetryable

        no_route = aiohttp.ClientConnectorError(MagicMock(), OSError("no route"))
        with patch("api.oauth.get_valid_token", AsyncMock(return_value="tok")), \
             patch("tools.gmail.send_mime", AsyncMock(side_effect=no_route)), \
             pytest.raises(ApprovalRetryable, match="nothing was sent"):
            await execute_approved(MagicMock(), "ron", "gmail.send", {"to": ["a@b.com"], "body": "x"})
        with patch("api.oauth.get_valid_token", AsyncMock(return_value="tok")), \
             patch("tools.gmail.send_mime", AsyncMock(side_effect=aiohttp.ServerTimeoutError("slow"))):
            with pytest.raises(ApprovalError) as exc:
                await execute_approved(MagicMock(), "ron", "gmail.send", {"to": ["a@b.com"], "body": "x"})
            assert not isinstance(exc.value, ApprovalRetryable)


class TestHardening:
    @pytest.mark.asyncio
    async def test_line_breaks_in_subject_are_flattened(self):
        t = _tool()
        with patch("api.approvals.create_pending_action", AsyncMock(return_value=_card())) as create:
            await t.execute(action="send_email", to=["sam@example.com"], subject="Hi\r\nBcc: evil@x.com", body="b")
        subject = create.call_args.kwargs["params"]["subject"]
        assert subject == "Hi Bcc: evil@x.com"
        build_mime(["sam@example.com"], subject, "b")  # would raise on a raw newline

    @pytest.mark.asyncio
    async def test_message_id_is_escaped_in_the_url(self):
        t = _tool()
        resp = MagicMock(status=404)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=resp)
        ctx.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=ctx)
        cls = MagicMock()
        cls.return_value.__aenter__ = AsyncMock(return_value=session)
        cls.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("tools.gmail.aiohttp.ClientSession", cls):
            await t._fetch_message("tok", "../../drafts/x")
        assert session.get.call_args.args[0].endswith("/messages/..%2F..%2Fdrafts%2Fx")
