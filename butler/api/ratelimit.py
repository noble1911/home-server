"""API rate limiting via pure ASGI middleware.

Uses an in-memory sliding window counter (deques of timestamps) keyed by
user_id (from JWT) or client IP.  Designed as a raw ASGI middleware so
SSE streaming responses (``/api/chat/stream``, ``/api/voice/stream``) pass
through untouched — ``BaseHTTPMiddleware`` would buffer them.

Rate limit categories:
    auth     /api/auth/*    5/min   (brute-force protection, keyed by IP)
    chat     /api/chat/*   20/min   (Claude API cost control, keyed by user)
    voice    /api/voice/*  30/min   (keyed by user)
    default  everything    60/min   (keyed by user or IP)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .auth import decode_user_jwt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RateLimitConfig:
    """Bundle of rate-limit settings passed to the middleware."""

    enabled: bool
    rate_limit_auth: int
    rate_limit_chat: int
    rate_limit_voice: int
    rate_limit_default: int
    internal_api_key: str


# ---------------------------------------------------------------------------
# In-memory sliding window store
# ---------------------------------------------------------------------------

class SlidingWindowStore:
    """Sliding window counter backed by ``collections.deque``.

    Each *key* (e.g. ``"user:abc:chat"``) maps to a deque of
    ``time.monotonic()`` timestamps.  On every ``check()`` call, expired
    entries are evicted from the front of the deque before counting.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def check(
        self, key: str, max_requests: int, window_secs: int
    ) -> tuple[bool, int, int]:
        """Test whether *key* is within its rate limit.

        Returns:
            (allowed, remaining, retry_after_secs)
        """
        now = time.monotonic()
        bucket = self._buckets[key]

        # Evict timestamps outside the window
        cutoff = now - window_secs
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= max_requests:
            retry_after = int(bucket[0] - cutoff) + 1
            return False, 0, retry_after

        bucket.append(now)
        remaining = max_requests - len(bucket)
        return True, remaining, 0

    def cleanup(self) -> int:
        """Remove empty buckets.  Returns the number removed."""
        empty = [k for k, v in self._buckets.items() if not v]
        for k in empty:
            del self._buckets[k]
        return len(empty)


# ---------------------------------------------------------------------------
# Pure ASGI middleware
# ---------------------------------------------------------------------------

_WINDOW_SECS = 60  # all categories use a 1-minute window


class RateLimitMiddleware:
    """Pure ASGI rate-limiting middleware.

    Skips CORS preflight (OPTIONS) requests explicitly so behaviour is
    independent of middleware ordering.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        store: SlidingWindowStore,
        config: RateLimitConfig,
    ) -> None:
        self.app = app
        self.store = store
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not self.config.enabled
            or scope.get("method") == "OPTIONS"
        ):
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        # Service-to-service calls (LiveKit Agents) bypass rate limiting
        if self._is_internal_call(request):
            await self.app(scope, receive, send)
            return

        path = request.url.path
        category = self._category_for_path(path)
        max_requests = self._limit_for_category(category)
        key = self._extract_key(request)
        bucket_key = f"{key}:{category}"

        allowed, remaining, retry_after = self.store.check(
            bucket_key, max_requests, _WINDOW_SECS
        )

        if not allowed:
            logger.warning(
                "Rate limit exceeded: key=%s path=%s category=%s limit=%d/%ds",
                key,
                path,
                category,
                max_requests,
                _WINDOW_SECS,
            )
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Try again in {retry_after} seconds."
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )
            await response(scope, receive, send)
            return

        # Allowed — pass through without touching the response
        await self.app(scope, receive, send)

    # -- helpers ----------------------------------------------------------

    def _is_internal_call(self, request: Request) -> bool:
        api_key = request.headers.get("x-api-key", "")
        return bool(
            api_key
            and self.config.internal_api_key
            and api_key == self.config.internal_api_key
        )

    @staticmethod
    def _category_for_path(path: str) -> str:
        if path.startswith("/api/auth"):
            return "auth"
        if path.startswith("/api/chat"):
            return "chat"
        if path.startswith("/api/voice"):
            return "voice"
        return "default"

    def _limit_for_category(self, category: str) -> int:
        return {
            "auth": self.config.rate_limit_auth,
            "chat": self.config.rate_limit_chat,
            "voice": self.config.rate_limit_voice,
            "default": self.config.rate_limit_default,
        }[category]

    @staticmethod
    def _extract_key(request: Request) -> str:
        """Return ``user:<id>`` from JWT or ``ip:<addr>`` as fallback."""
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                payload = decode_user_jwt(auth_header[7:])
                return f"user:{payload['sub']}"
            except Exception:
                pass  # invalid / expired — fall through to IP
        client = request.client
        host = client.host if client else "unknown"
        return f"ip:{host}"


# ---------------------------------------------------------------------------
# Background cleanup task (follows cleanup.py pattern)
# ---------------------------------------------------------------------------

_CLEANUP_INTERVAL = 300  # 5 minutes
_cleanup_task: asyncio.Task[None] | None = None


async def _cleanup_loop(store: SlidingWindowStore) -> None:
    """Periodically remove empty buckets from the store."""
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        try:
            removed = store.cleanup()
            if removed:
                logger.debug(
                    "Rate limit cleanup: removed %d empty buckets", removed
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Rate limit cleanup failed")


def start_ratelimit_cleanup(store: SlidingWindowStore) -> None:
    """Spawn the background cleanup task."""
    global _cleanup_task
    _cleanup_task = asyncio.create_task(
        _cleanup_loop(store), name="ratelimit-cleanup"
    )
    logger.info("Rate limit cleanup started (interval=%ds)", _CLEANUP_INTERVAL)


async def stop_ratelimit_cleanup() -> None:
    """Cancel the background cleanup task if running."""
    global _cleanup_task
    if _cleanup_task is not None:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        _cleanup_task = None
        logger.info("Rate limit cleanup stopped")
