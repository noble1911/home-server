"""Google connect from the Android app (#214): consent runs in the system browser.

Run with: pytest butler/api/test_oauth_app_flow.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from .oauth import create_oauth_state, verify_oauth_state
from .routes import oauth as oauth_routes


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(oauth_routes.router, prefix="/api/oauth")
    app.dependency_overrides[oauth_routes.get_db_pool] = lambda: MagicMock()
    return TestClient(app)


def test_state_carries_the_client():
    state = create_oauth_state("ron", redirect_uri="https://b/api/oauth/google/callback", client="app")
    assert verify_oauth_state(state)["client"] == "app"
    assert verify_oauth_state(create_oauth_state("ron"))["client"] is None


def test_app_flow_ends_on_a_return_to_the_app_page():
    state = create_oauth_state("ron", redirect_uri="https://b/api/oauth/google/callback",
                               frontend_url="https://b", client="app")
    with patch.object(oauth_routes, "exchange_google_code", AsyncMock(return_value={"access_token": "a"})), \
         patch.object(oauth_routes, "get_google_user_email", AsyncMock(return_value="ron@gmail.com")), \
         patch.object(oauth_routes, "store_tokens", AsyncMock()) as store:
        r = _client().get("/api/oauth/google/callback", params={"code": "c", "state": state})
    assert "Google connected" in r.text and "back to the Butler app" in r.text
    assert "window.location" not in r.text
    store.assert_awaited_once()


def test_app_flow_denied_consent():
    state = create_oauth_state("ron", client="app")
    r = _client().get("/api/oauth/google/callback", params={"error": "access_denied", "state": state})
    assert "Couldn't connect Google" in r.text and "access_denied" in r.text


def test_web_flow_still_redirects_to_settings():
    state = create_oauth_state("ron", frontend_url="https://b")
    r = _client().get("/api/oauth/google/callback", params={"error": "access_denied", "state": state})
    assert "https://b/settings?oauth=google&amp;status=error" in r.text


def test_only_app_is_a_valid_client():
    app = FastAPI()
    app.include_router(oauth_routes.router, prefix="/api/oauth")
    app.dependency_overrides[oauth_routes.get_current_user] = lambda: "ron"
    with patch.object(oauth_routes.settings, "google_client_id", "id"):
        r = TestClient(app).get("/api/oauth/google/authorize", params={"client": "evil"})
    assert r.status_code == 422
