"""Tests for API rate limiting.

Run with: pytest butler/api/test_ratelimit.py -v

Unit tests for SlidingWindowStore + integration tests using a minimal
Starlette app with the RateLimitMiddleware.
"""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from .ratelimit import RateLimitConfig, RateLimitMiddleware, SlidingWindowStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> RateLimitConfig:
    defaults = dict(
        enabled=True,
        rate_limit_auth=2,
        rate_limit_chat=3,
        rate_limit_voice=3,
        rate_limit_default=5,
        internal_api_key="test-internal-key",
    )
    defaults.update(overrides)
    return RateLimitConfig(**defaults)


def _make_app(config: RateLimitConfig | None = None) -> tuple[TestClient, SlidingWindowStore]:
    """Create a minimal Starlette app with rate limiting for testing."""
    async def ok(_request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[
            Route("/health", ok),
            Route("/api/auth/redeem-invite", ok, methods=["POST"]),
            Route("/api/chat", ok, methods=["POST"]),
            Route("/api/voice/process", ok, methods=["POST"]),
            Route("/api/user/profile", ok),
        ],
    )

    store = SlidingWindowStore()
    cfg = config or _make_config()
    app.add_middleware(RateLimitMiddleware, store=store, config=cfg)
    return TestClient(app, raise_server_exceptions=False), store


# ---------------------------------------------------------------------------
# SlidingWindowStore unit tests
# ---------------------------------------------------------------------------

class TestSlidingWindowStore:
    def test_allows_requests_within_limit(self):
        store = SlidingWindowStore()
        for i in range(5):
            allowed, remaining, _ = store.check("k", 5, 60)
            assert allowed is True
            assert remaining == 4 - i

    def test_blocks_when_limit_exceeded(self):
        store = SlidingWindowStore()
        for _ in range(5):
            store.check("k", 5, 60)
        allowed, remaining, retry_after = store.check("k", 5, 60)
        assert allowed is False
        assert remaining == 0
        assert retry_after >= 1

    def test_window_expires_and_resets(self):
        store = SlidingWindowStore()
        # Fill up the limit
        for _ in range(3):
            store.check("k", 3, 60)

        # Simulate time passing by back-dating all bucket entries
        bucket = store._buckets["k"]
        old_entries = [t - 61 for t in bucket]
        bucket.clear()
        bucket.extend(old_entries)

        # Now the entries are >60s old, so they should be evicted
        allowed, remaining, _ = store.check("k", 3, 60)
        assert allowed is True
        assert remaining == 2

    def test_retry_after_is_positive(self):
        store = SlidingWindowStore()
        for _ in range(2):
            store.check("k", 2, 60)
        _, _, retry_after = store.check("k", 2, 60)
        assert retry_after >= 1

    def test_independent_keys(self):
        store = SlidingWindowStore()
        for _ in range(3):
            store.check("a", 3, 60)
        # Key "a" is full, but "b" should still be allowed
        allowed, _, _ = store.check("b", 3, 60)
        assert allowed is True

    def test_cleanup_removes_empty_buckets(self):
        store = SlidingWindowStore()
        # Create a bucket then manually clear it to simulate expiry
        store.check("k", 5, 60)
        store._buckets["k"].clear()

        removed = store.cleanup()
        assert removed == 1
        assert "k" not in store._buckets

    def test_cleanup_preserves_active_buckets(self):
        store = SlidingWindowStore()
        store.check("active", 5, 60)
        removed = store.cleanup()
        assert removed == 0
        assert "active" in store._buckets


# ---------------------------------------------------------------------------
# RateLimitMiddleware integration tests
# ---------------------------------------------------------------------------

class TestRateLimitMiddleware:
    def test_allows_requests_within_limit(self):
        client, _ = _make_app()
        for _ in range(3):
            resp = client.post("/api/chat")
            assert resp.status_code == 200

    def test_returns_429_when_exceeded(self):
        client, _ = _make_app()
        # chat limit is 3
        for _ in range(3):
            client.post("/api/chat")
        resp = client.post("/api/chat")
        assert resp.status_code == 429

    def test_429_includes_retry_after_header(self):
        client, _ = _make_app()
        for _ in range(3):
            client.post("/api/chat")
        resp = client.post("/api/chat")
        assert "Retry-After" in resp.headers
        assert int(resp.headers["Retry-After"]) >= 1

    def test_429_includes_ratelimit_headers(self):
        client, _ = _make_app()
        for _ in range(3):
            client.post("/api/chat")
        resp = client.post("/api/chat")
        assert resp.headers["X-RateLimit-Limit"] == "3"
        assert resp.headers["X-RateLimit-Remaining"] == "0"

    def test_429_response_body(self):
        client, _ = _make_app()
        for _ in range(3):
            client.post("/api/chat")
        resp = client.post("/api/chat")
        body = resp.json()
        assert "Rate limit exceeded" in body["detail"]

    def test_different_categories_are_independent(self):
        client, _ = _make_app()
        # Exhaust auth limit (2)
        for _ in range(2):
            client.post("/api/auth/redeem-invite")
        resp = client.post("/api/auth/redeem-invite")
        assert resp.status_code == 429

        # Chat should still work (different category)
        resp = client.post("/api/chat")
        assert resp.status_code == 200

    def test_disabled_allows_all(self):
        client, _ = _make_app(_make_config(enabled=False))
        # Should not hit any limit even with many requests
        for _ in range(20):
            resp = client.post("/api/chat")
            assert resp.status_code == 200

    def test_internal_api_key_bypasses_limit(self):
        client, _ = _make_app()
        headers = {"X-API-Key": "test-internal-key"}
        # Exceed voice limit (3) — should all pass with internal key
        for _ in range(10):
            resp = client.post("/api/voice/process", headers=headers)
            assert resp.status_code == 200

    def test_wrong_internal_key_does_not_bypass(self):
        client, _ = _make_app()
        headers = {"X-API-Key": "wrong-key"}
        for _ in range(3):
            client.post("/api/voice/process", headers=headers)
        resp = client.post("/api/voice/process", headers=headers)
        assert resp.status_code == 429

    def test_different_ips_are_independent(self):
        """Unauthenticated requests fall back to IP-based rate limiting."""
        client, store = _make_app()
        # Exhaust limit for the default testclient IP
        for _ in range(2):
            client.post("/api/auth/redeem-invite")
        resp = client.post("/api/auth/redeem-invite")
        assert resp.status_code == 429

        # Simulate a different IP by directly checking the store
        allowed, _, _ = store.check("ip:10.0.0.99:auth", 2, 60)
        assert allowed is True

    def test_health_endpoint_uses_default_limit(self):
        client, _ = _make_app()
        # default limit is 5
        for _ in range(5):
            resp = client.get("/health")
            assert resp.status_code == 200
        resp = client.get("/health")
        assert resp.status_code == 429

    def test_options_requests_bypass_rate_limit(self):
        """CORS preflight (OPTIONS) requests are never rate-limited."""
        client, _ = _make_app()
        for _ in range(10):
            resp = client.options("/api/chat")
            assert resp.status_code != 429

    def test_logs_warning_on_rate_limit(self, caplog):
        client, _ = _make_app()
        import logging

        with caplog.at_level(logging.WARNING, logger="api.ratelimit"):
            for _ in range(3):
                client.post("/api/chat")
            client.post("/api/chat")

        assert any("Rate limit exceeded" in r.message for r in caplog.records)
