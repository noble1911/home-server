"""FastAPI application with CORS, lifespan, and route mounting."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .deps import cleanup_resources, get_db_pool, init_resources
from .routes import admin, auth, chat, oauth, system, tasks, users, voice

logger = logging.getLogger(__name__)


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
    allow_origins=["*"],  # Tailscale-only network; tighten if exposed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/health")
async def health():
    return {"status": "ok"}
