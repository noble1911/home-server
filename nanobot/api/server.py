"""FastAPI application with CORS, lifespan, and route mounting."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .deps import cleanup_resources, get_db_pool, init_resources
from .ratelimit import RateLimitConfig, RateLimitMiddleware, SlidingWindowStore
from .routes import admin, auth, chat, oauth, push, system, tasks, users, voice, webhooks

logger = logging.getLogger(__name__)

# Shared in-memory store — passed to middleware and cleanup task
rate_limit_store = SlidingWindowStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init db pool + tools. Shutdown: release resources."""
    await init_resources()

    # One-shot cleanup of stale tool usage logs (bridge until Issue #75 scheduler)
    try:
        from .audit import cleanup_tool_usage_logs

        pool = get_db_pool()
        await cleanup_tool_usage_logs(pool)
    except Exception:
        logger.debug("Tool usage cleanup skipped (table may not exist yet)")

    yield
    await cleanup_resources()


app = FastAPI(title="Butler API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cloudflare Tunnel handles access control
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    RateLimitMiddleware,
    store=rate_limit_store,
    config=RateLimitConfig(
        enabled=settings.rate_limit_enabled,
        rate_limit_auth=settings.rate_limit_auth,
        rate_limit_chat=settings.rate_limit_chat,
        rate_limit_voice=settings.rate_limit_voice,
        rate_limit_default=settings.rate_limit_default,
        internal_api_key=settings.internal_api_key,
    ),
)

# Route mounting — prefixes match what the PWA expects at /api/*
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(users.router, prefix="/api", tags=["users"])
app.include_router(tasks.router, prefix="/api", tags=["tasks"])
app.include_router(oauth.router, prefix="/api/oauth", tags=["oauth"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(system.router, prefix="/api", tags=["system"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])
app.include_router(push.router, prefix="/api/push", tags=["push"])


@app.get("/health")
async def health():
    return {"status": "ok"}
