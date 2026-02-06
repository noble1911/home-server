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
from .weather import WeatherTool

__all__ = [
    # Base
    "Tool",
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
    # Weather
    "WeatherTool",
]
