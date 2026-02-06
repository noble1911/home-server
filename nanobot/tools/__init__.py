"""Butler custom tools for Nanobot.

These tools extend Nanobot's capabilities with home server integrations.

Usage:
    # For shared connection pool (recommended)
    from nanobot.tools import DatabasePool, RememberFactTool, RecallFactsTool

    pool = await DatabasePool.create()
    remember = RememberFactTool(pool)
    recall = RecallFactsTool(pool)

    # For standalone usage (creates pool internally)
    tool = RememberFactTool()
    await tool.execute(user_id="123", fact="Likes coffee")
    await tool.close()
"""

from .base import Tool
from .embeddings import EmbeddingService
from .memory import (
    DatabasePool,
    DatabaseTool,
    RememberFactTool,
    RecallFactsTool,
    GetUserTool,
    GetConversationsTool,
    UpdateSoulTool,
    VALID_SOUL_KEYS,
)
from .home_assistant import HomeAssistantTool, ListEntitiesByDomainTool
from .gmail import GmailTool
from .google_calendar import GoogleCalendarTool
from .jellyfin import JellyfinTool
from .radarr import RadarrTool
from .readarr import ReadarrTool
from .sonarr import SonarrTool
from .immich import ImmichTool
from .phone_location import PhoneLocationTool
from .weather import WeatherTool
from .alerting import AlertStateManager, NotificationDispatcher
from .server_health import ServerHealthTool
from .storage_monitor import StorageMonitorTool

__all__ = [
    # Base
    "Tool",
    # Embeddings
    "EmbeddingService",
    # Database
    "DatabasePool",
    "DatabaseTool",
    # Memory
    "RememberFactTool",
    "RecallFactsTool",
    "GetUserTool",
    "GetConversationsTool",
    "UpdateSoulTool",
    "VALID_SOUL_KEYS",
    # Home Assistant
    "HomeAssistantTool",
    "ListEntitiesByDomainTool",
    # Gmail
    "GmailTool",
    # Google Calendar
    "GoogleCalendarTool",
    # Jellyfin
    "JellyfinTool",
    # Phone Location
    "PhoneLocationTool",
    # Radarr
    "RadarrTool",
    # Readarr
    "ReadarrTool",
    # Sonarr
    "SonarrTool",
    # Immich
    "ImmichTool",
    # Weather
    "WeatherTool",
    # Alerting
    "AlertStateManager",
    "NotificationDispatcher",
    # Health monitoring
    "ServerHealthTool",
    # Storage monitoring
    "StorageMonitorTool",
]
