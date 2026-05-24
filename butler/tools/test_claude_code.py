"""Tests for the Claude Code delegation tool.

Run with: pytest butler/tools/test_claude_code.py -v

These tests mock the shim's HTTP/SSE responses — no real shim required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from .claude_code import ClaudeCodeTool


def _sse(*lines: str) -> list[bytes]:
    """Encode SSE lines as the byte chunks aiohttp yields from resp.content."""
    return [(line + "\n").encode() for line in lines]


async def _byte_lines(chunks: list[bytes]):
    """Async generator standing in for aiohttp's StreamReader (resp.content)."""
    for chunk in chunks:
        yield chunk


def _make_cm(resp):
    """Wrap a mock response in an async context manager (like session.post)."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _response(status: int, sse_chunks: list[bytes] | None = None, text: str = ""):
    resp = MagicMock()
    resp.status = status
    resp.content = _byte_lines(sse_chunks or [])
    resp.text = AsyncMock(return_value=text)
    return resp


def _tool_with_session(resp=None, post_side_effect=None, shim_token=None):
    """Build a ClaudeCodeTool whose session.post is mocked."""
    tool = ClaudeCodeTool(shim_url="http://shim:7100/", shim_token=shim_token)
    session = MagicMock()
    session.closed = False
    if post_side_effect is not None:
        session.post = MagicMock(side_effect=post_side_effect)
    else:
        session.post = MagicMock(return_value=_make_cm(resp))
    tool._session = session
    return tool, session


@pytest.mark.asyncio
async def test_missing_task_returns_error():
    tool = ClaudeCodeTool(shim_url="http://shim:7100")
    result = await tool.execute(task="   ")
    assert "required" in result.lower()


@pytest.mark.asyncio
async def test_successful_delegation_accumulates_text():
    resp = _response(200, _sse(
        'data: {"type":"tool_start","tool":"claude_code"}',
        'data: {"type":"text_delta","delta":"Restarted "}',
        ': keepalive',
        'data: {"type":"text_delta","delta":"sonarr."}',
        'data: [DONE]',
    ))
    tool, _ = _tool_with_session(resp)
    result = await tool.execute(task="restart sonarr")
    assert result == "Restarted sonarr."


@pytest.mark.asyncio
async def test_auth_header_sent_when_token_set():
    resp = _response(200, _sse('data: {"type":"text_delta","delta":"ok"}', 'data: [DONE]'))
    tool, session = _tool_with_session(resp, shim_token="s3cr3t")
    await tool.execute(task="do a thing")
    _, kwargs = session.post.call_args
    assert kwargs["headers"]["X-Shim-Token"] == "s3cr3t"


@pytest.mark.asyncio
async def test_no_auth_header_when_token_unset():
    resp = _response(200, _sse('data: {"type":"text_delta","delta":"ok"}', 'data: [DONE]'))
    tool, session = _tool_with_session(resp, shim_token=None)
    await tool.execute(task="do a thing")
    _, kwargs = session.post.call_args
    assert "X-Shim-Token" not in kwargs["headers"]


@pytest.mark.asyncio
async def test_401_returns_auth_error():
    tool, _ = _tool_with_session(_response(401))
    result = await tool.execute(task="x")
    assert "authentication failed" in result.lower()


@pytest.mark.asyncio
async def test_non_200_returns_error_with_body():
    tool, _ = _tool_with_session(_response(500, text="boom"))
    result = await tool.execute(task="x")
    assert "500" in result and "boom" in result


@pytest.mark.asyncio
async def test_connection_error_is_friendly():
    err = aiohttp.ClientConnectorError(MagicMock(), OSError("refused"))
    tool, _ = _tool_with_session(post_side_effect=err)
    result = await tool.execute(task="x")
    assert "cannot reach" in result.lower()


@pytest.mark.asyncio
async def test_timeout_is_reported():
    tool, _ = _tool_with_session(post_side_effect=TimeoutError())
    result = await tool.execute(task="x")
    assert "timed out" in result.lower()


@pytest.mark.asyncio
async def test_empty_output_message():
    tool, _ = _tool_with_session(_response(200, _sse('data: [DONE]')))
    result = await tool.execute(task="x")
    assert "no output" in result.lower()


@pytest.mark.asyncio
async def test_long_output_truncated():
    long_delta = "A" * 20000
    resp = _response(200, _sse(
        'data: {"type":"text_delta","delta":"' + long_delta + '"}',
        'data: [DONE]',
    ))
    tool, _ = _tool_with_session(resp)
    result = await tool.execute(task="x")
    assert result.endswith("…(output truncated)")
    assert len(result) < 20000


@pytest.mark.asyncio
async def test_tool_metadata():
    tool = ClaudeCodeTool(shim_url="http://shim:7100")
    assert tool.name == "run_claude_code"
    assert "task" in tool.parameters["required"]
    assert "shell" in tool.description.lower()
