"""Background Audiobookshelf metadata sync.

Periodically checks for library items missing descriptions and triggers
a metadata match from the configured provider (Google Books by default).

Started/stopped via the FastAPI lifespan in deps.py.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)

_INTERVAL_SECONDS = 10 * 60  # 10 minutes
_MATCH_DELAY_SECONDS = 2  # pause between match calls to avoid rate limits
_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)

_sync_task: asyncio.Task | None = None


async def _match_unmatched_items(base_url: str, token: str) -> int:
    """Find library items without descriptions and match them. Returns count."""
    headers = {"Authorization": f"Bearer {token}"}
    matched = 0

    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        # Get all libraries
        async with session.get(
            f"{base_url}/api/libraries", headers=headers
        ) as resp:
            if resp.status != 200:
                logger.warning("ABS libraries request failed: HTTP %d", resp.status)
                return 0
            data = await resp.json()

        libraries = data.get("libraries", [])

        for library in libraries:
            lib_id = library["id"]

            # Fetch all items in the library
            async with session.get(
                f"{base_url}/api/libraries/{lib_id}/items",
                headers=headers,
                params={"limit": 0},  # 0 = return all
            ) as resp:
                if resp.status != 200:
                    continue
                lib_data = await resp.json()

            for item in lib_data.get("results", []):
                # Skip items that already have a description
                description = (
                    item.get("media", {})
                    .get("metadata", {})
                    .get("description")
                )
                if description:
                    continue

                item_id = item["id"]
                title = item.get("media", {}).get("metadata", {}).get("title", "?")

                # Trigger metadata match
                async with session.post(
                    f"{base_url}/api/items/{item_id}/match",
                    headers=headers,
                    json={"provider": "google"},
                ) as match_resp:
                    if match_resp.status == 200:
                        result = await match_resp.json()
                        if result.get("updated"):
                            matched += 1
                            logger.info("Matched metadata for '%s'", title)
                    else:
                        logger.warning(
                            "Failed to match '%s': HTTP %d", title, match_resp.status
                        )

                await asyncio.sleep(_MATCH_DELAY_SECONDS)

    return matched


async def _sync_loop(base_url: str, token: str) -> None:
    """Infinite loop that syncs metadata periodically."""
    while True:
        try:
            matched = await _match_unmatched_items(base_url, token)
            if matched:
                logger.info("ABS metadata sync: matched %d book(s)", matched)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ABS metadata sync error")
        await asyncio.sleep(_INTERVAL_SECONDS)


def start_abs_metadata_sync(base_url: str, token: str) -> None:
    """Spawn the background ABS metadata sync task."""
    global _sync_task
    _sync_task = asyncio.create_task(
        _sync_loop(base_url, token),
        name="butler-abs-metadata-sync",
    )
    logger.info(
        "ABS metadata sync started (interval=%dm)", _INTERVAL_SECONDS // 60
    )


async def stop_abs_metadata_sync() -> None:
    """Cancel the background ABS metadata sync task if running."""
    global _sync_task
    if _sync_task is not None:
        _sync_task.cancel()
        try:
            await _sync_task
        except asyncio.CancelledError:
            pass
        _sync_task = None
        logger.info("ABS metadata sync stopped")
