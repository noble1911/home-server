"""OAuth integration routes for connecting external services.

GET    /api/oauth/google/authorize  — Start OAuth flow (returns redirect URL)
GET    /api/oauth/google/callback   — Handle Google redirect (no JWT auth)
GET    /api/oauth/connections       — List user's connected services
DELETE /api/oauth/{provider}        — Disconnect a service
"""

from __future__ import annotations

import html as html_lib
import json
import logging
from urllib.parse import urlencode

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from tools import DatabasePool

from ..config import settings
from ..deps import get_current_user, get_db_pool
from ..models import OAuthAuthorizeResponse, OAuthConnection, OAuthConnectionsResponse
from ..oauth import (
    build_google_authorize_url,
    create_oauth_state,
    delete_connection,
    exchange_google_code,
    get_google_user_email,
    list_connections,
    store_tokens,
    verify_oauth_state,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/google/authorize", response_model=OAuthAuthorizeResponse)
async def google_authorize(
    user_id: str = Depends(get_current_user),
    origin: str = Query(default=None),
    client: str = Query(default=None, pattern="^app$"),
):
    """Start the Google OAuth flow.

    Returns a URL that the PWA should redirect the browser to.
    The URL points to Google's consent screen.

    The optional `origin` parameter (e.g. "https://butler.noblehaus.uk")
    lets the flow work from any access point (LAN, Cloudflare Tunnel).
    When provided, the redirect_uri and frontend URL are derived from it
    instead of the hardcoded env var defaults.
    """
    if not settings.google_client_id:
        raise HTTPException(503, "Google OAuth is not configured")

    # Derive URLs from the PWA's origin when available
    redirect_uri = None
    frontend_url = None
    if origin:
        origin = origin.rstrip("/")
        redirect_uri = f"{origin}/api/oauth/google/callback"
        frontend_url = origin

    effective_uri = redirect_uri or settings.google_redirect_uri
    logger.info("OAuth authorize: redirect_uri=%s (origin=%s)", effective_uri, origin)

    # client=app: the Android app opens consent in the system browser, which isn't
    # signed in to Butler, so the callback shows "return to the app" instead.
    state = create_oauth_state(user_id, redirect_uri=redirect_uri, frontend_url=frontend_url, client=client)
    authorize_url = build_google_authorize_url(state, redirect_uri=redirect_uri)
    return OAuthAuthorizeResponse(authorizeUrl=authorize_url)


@router.get("/google/callback", response_class=HTMLResponse)
async def google_callback(
    code: str = Query(default=None),
    state: str = Query(default=None),
    error: str = Query(default=None),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Handle Google's OAuth redirect after user consent.

    This endpoint has NO JWT auth — it's called by Google's redirect,
    which is a plain browser GET. The user_id comes from the signed
    state parameter instead.

    On success, redirects the browser back to PWA settings.
    """
    frontend_url = settings.oauth_frontend_url.rstrip("/")

    # Verify state JWT to get user_id and dynamic URLs
    state_data = None
    if state:
        try:
            state_data = verify_oauth_state(state)
        except pyjwt.InvalidTokenError as e:
            logger.warning("Invalid OAuth state: %s", e)
    client = state_data.get("client") if state_data else None
    if state_data and state_data.get("frontend_url"):
        # Use URLs from state if available (set when PWA passed its origin)
        frontend_url = state_data["frontend_url"].rstrip("/")

    def finish(status: str, message: str | None = None) -> HTMLResponse:
        if client == "app":
            return _app_done_html(status == "success", message)
        params = {"oauth": "google", "status": status, **({"message": message} if message else {})}
        return _redirect_html(f"{frontend_url}/settings?{urlencode(params)}")

    # Google may redirect with an error (user denied consent)
    if error:
        return finish("error", error)
    if not code or not state:
        return finish("error", "Missing code or state")
    if state_data is None:
        return finish("error", "Invalid or expired state")
    user_id = state_data["user_id"]

    # Exchange authorization code for tokens (redirect_uri must match authorize request)
    try:
        token_data = await exchange_google_code(code, redirect_uri=state_data.get("redirect_uri"))
    except RuntimeError as e:
        logger.error("Google code exchange failed: %s", e)
        return finish("error", "Token exchange failed")

    # Fetch Google email for display
    email = await get_google_user_email(token_data["access_token"])

    # Store tokens
    await store_tokens(pool, user_id, "google", token_data, account_id=email)

    return finish("success")


@router.get("/connections", response_model=OAuthConnectionsResponse)
async def get_connections(
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """List all OAuth connections for the authenticated user."""
    rows = await list_connections(pool, user_id)
    connections = [
        OAuthConnection(
            provider=row["provider"],
            connected=True,
            accountId=row["account_id"],
            connectedAt=row["created_at"],
            scopes=row["scopes"],
        )
        for row in rows
    ]
    return OAuthConnectionsResponse(connections=connections)


@router.delete("/{provider}", status_code=204)
async def disconnect_provider(
    provider: str,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Disconnect an OAuth service and revoke the token."""
    deleted = await delete_connection(pool, user_id, provider)
    if not deleted:
        raise HTTPException(404, f"No connection found for provider: {provider}")


def _app_done_html(ok: bool, message: str | None = None) -> HTMLResponse:
    """End page for the Android app's flow, shown in the system browser."""
    if ok:
        heading, detail = "Google connected", "You can close this tab and go back to the Butler app."
    else:
        heading = "Couldn't connect Google"
        detail = html_lib.escape(message or "Something went wrong.") + " Go back to the Butler app and try again."
    html = f"""<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Butler</title>
<style>body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;display:flex;
align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center;padding:24px}}
h1{{font-size:1.4rem}}p{{color:#94a3b8}}</style></head>
<body><div><h1>{"✓ " if ok else ""}{heading}</h1><p>{detail}</p></div></body></html>"""
    return HTMLResponse(content=html)


def _redirect_html(url: str) -> HTMLResponse:
    """Return a minimal HTML page that redirects the browser.

    Using an HTML redirect rather than a 302 to ensure the browser
    fully loads the PWA URL (some browsers handle 302 differently
    with SPAs).
    """
    safe_url = html_lib.escape(url, quote=True)
    js_url = json.dumps(url)  # produces a properly quoted/escaped JS string
    html = f"""<!DOCTYPE html>
<html><head>
<meta http-equiv="refresh" content="0;url={safe_url}">
</head><body>
<p>Redirecting...</p>
<script>window.location.href = {js_url};</script>
</body></html>"""
    return HTMLResponse(content=html)
