"""Background Audiobookshelf metadata sync.

Periodically checks for library items missing descriptions and triggers
a metadata match. Providers are tried in order until one matches: Open Library
then Google Books for ebooks, Audible (UK) then Open Library for audiobooks.
Google Books alone was rate-limiting the server (HTTP 429 on every request),
so nothing ever matched. Items that can't be matched aren't retried for a day,
and items whose files are missing are skipped.

Started/stopped via the FastAPI lifespan in deps.py.
"""

from __future__ import annotations

import asyncio
import logging
import time

import aiohttp

logger = logging.getLogger(__name__)

_INTERVAL_SECONDS = 10 * 60  # 10 minutes
_MATCH_DELAY_SECONDS = 2  # pause between match calls to avoid rate limits
_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)
_RETRY_AFTER_SECONDS = 24 * 60 * 60  # don't re-query an unmatchable item every 10 minutes

EBOOK_PROVIDERS = ["openlibrary", "google"]
AUDIOBOOK_PROVIDERS = ["audible.uk", "openlibrary"]

_sync_task: asyncio.Task | None = None
_last_attempt: dict[str, float] = {}  # item id -> time of the last failed match


def _providers_for(item: dict) -> list[str]:
    media = item.get("media", {})
    has_audio = media.get("numAudioFiles") or media.get("audioFiles") or media.get("numTracks")
    return AUDIOBOOK_PROVIDERS if has_audio else EBOOK_PROVIDERS


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
                # Skip items that already have a description, or whose files are gone
                description = (
                    item.get("media", {})
                    .get("metadata", {})
                    .get("description")
                )
                if description or item.get("isMissing") or item.get("isInvalid"):
                    continue

                item_id = item["id"]
                title = item.get("media", {}).get("metadata", {}).get("title", "?")
                if time.monotonic() - _last_attempt.get(item_id, -_RETRY_AFTER_SECONDS) < _RETRY_AFTER_SECONDS:
                    continue

                if await _match(session, base_url, headers, item_id, title, _providers_for(item)):
                    matched += 1
                    _last_attempt.pop(item_id, None)
                else:
                    _last_attempt[item_id] = time.monotonic()

    return matched


async def _match(session, base_url: str, headers: dict, item_id: str, title: str, providers: list[str]) -> bool:
    """Try each provider in turn; True once one updates the item."""
    for provider in providers:
        async with session.post(
            f"{base_url}/api/items/{item_id}/match",
            headers=headers,
            json={"provider": provider},
        ) as match_resp:
            if match_resp.status == 200 and (await match_resp.json()).get("updated"):
                logger.info("Matched metadata for '%s' from %s", title, provider)
                return True
            if match_resp.status != 200:
                logger.warning("Failed to match '%s' via %s: HTTP %d", title, provider, match_resp.status)
        await asyncio.sleep(_MATCH_DELAY_SECONDS)
    logger.info("No metadata match for '%s' (tried %s); retrying in a day", title, ", ".join(providers))
    return False


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
