"""Display-in-chat tool for voice sessions.

When Butler is responding via voice, this tool lets the AI push rich visual
content (images, tables, formatted lists, links) to the PWA chat panel.
The execute() is a no-op — the actual display happens when the SSE pipeline
intercepts the tool call and forwards it through the LiveKit data channel.
"""

from typing import Any

from .base import Tool


class DisplayInChatTool(Tool):
    @property
    def name(self) -> str:
        return "display_in_chat"

    @property
    def description(self) -> str:
        return (
            "Display rich visual content in the user's chat panel during a voice "
            "session. Use this when a response benefits from visual formatting that "
            "can't be conveyed well through speech — for example images, tables, "
            "lists of links, formatted data, or any content that's easier to read "
            "than listen to. The content is rendered as markdown. Meanwhile, provide "
            "a brief spoken summary via your normal text response."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": (
                        "Markdown-formatted content to display. Supports tables, "
                        "images (![alt](url)), links, lists, headings, and code blocks."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "Optional title displayed above the content.",
                },
            },
            "required": ["content"],
        }

    async def execute(self, **kwargs: Any) -> str:
        return "Content displayed in chat."
