"""Base classes for Nanobot tools.

This module provides the Tool base class that all Butler tools inherit from.
It defines the interface that Nanobot expects for tool registration.
"""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Base class for Nanobot tools.

    All tools must implement:
    - name: Unique identifier for the tool
    - description: What the tool does (shown to the LLM)
    - parameters: JSON Schema for tool arguments
    - execute: The actual implementation

    Example:
        class MyTool(Tool):
            @property
            def name(self) -> str:
                return "my_tool"

            @property
            def description(self) -> str:
                return "Does something useful"

            @property
            def parameters(self) -> dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {"arg": {"type": "string"}},
                    "required": ["arg"]
                }

            async def execute(self, **kwargs) -> str:
                return f"Result: {kwargs['arg']}"
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this tool."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what this tool does (shown to LLM)."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool with given parameters.

        Args:
            **kwargs: Tool parameters matching the schema

        Returns:
            String result to show to the LLM
        """
        ...

    def to_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function schema format.

        Returns:
            Dict in OpenAI function calling format
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
