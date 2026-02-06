"""Entrypoint for `python -m api`."""

import uvicorn

from .config import settings

uvicorn.run("api.server:app", host="0.0.0.0", port=settings.port, log_level="info")
