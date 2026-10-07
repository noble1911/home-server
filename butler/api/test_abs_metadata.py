"""Tests for the Audiobookshelf metadata sync's provider fallback.

Run with: pytest butler/api/test_abs_metadata.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from . import abs_metadata


def _resp(status=200, updated=False, body=None):
    r = MagicMock()
    r.status = status
    r.json = AsyncMock(return_value=body if body is not None else {"updated": updated})
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=r)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _item(id_, desc=None, audio=0, missing=False):
    return {"id": id_, "isMissing": missing,
            "media": {"metadata": {"title": id_, "description": desc}, "numAudioFiles": audio}}


@pytest.fixture(autouse=True)
def fresh_state():
    abs_metadata._last_attempt.clear()
    with patch.object(abs_metadata, "_MATCH_DELAY_SECONDS", 0):
        yield


def test_providers_by_media():
    assert abs_metadata._providers_for(_item("a", audio=3))[0] == "audible.uk"
    assert abs_metadata._providers_for(_item("b"))[0] == "openlibrary"


@pytest.mark.asyncio
async def test_falls_back_to_the_next_provider():
    session = MagicMock()
    session.post = MagicMock(side_effect=[_resp(updated=False), _resp(updated=True)])
    ok = await abs_metadata._match(session, "http://abs", {}, "i1", "Book", ["openlibrary", "google"])
    assert ok is True
    assert [c.kwargs["json"]["provider"] for c in session.post.call_args_list] == ["openlibrary", "google"]


@pytest.mark.asyncio
async def test_sync_skips_described_missing_and_recently_failed_items():
    items = [_item("described", desc="x"), _item("gone", missing=True), _item("new"), _item("tried")]
    abs_metadata._last_attempt["tried"] = abs_metadata.time.monotonic()
    session = MagicMock()
    session.get = MagicMock(side_effect=[_resp(body={"libraries": [{"id": "L"}]}), _resp(body={"results": items})])
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    with patch.object(abs_metadata.aiohttp, "ClientSession", return_value=session), \
         patch.object(abs_metadata, "_match", AsyncMock(return_value=False)) as match:
        assert await abs_metadata._match_unmatched_items("http://abs", "tok") == 0
    assert [c.args[3] for c in match.call_args_list] == ["new"]
    assert "new" in abs_metadata._last_attempt  # won't be retried for a day
