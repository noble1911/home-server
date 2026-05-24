"""display_on_device tool — render a structured card on the user's ESP32 screen.

Like display_in_chat, execute() is a deliberate no-op: the streaming pipeline in
llm.py intercepts the tool call and emits a ``device_card`` SSE event, which the
esp-gateway forwards to the device to render with LVGL. The card schema is
documented in claude-esp/PROTOCOL.md.
"""

from typing import Any

from .base import Tool


class DisplayOnDeviceTool(Tool):
    @property
    def name(self) -> str:
        return "display_on_device"

    @property
    def description(self) -> str:
        return (
            "Display a structured card on the user's physical device screen (a small "
            "ESP32 touchscreen) during a voice conversation. Use this for glanceable "
            "info that's easier to see than hear — weather, a short list, a status, a "
            "confirmation, or a single value/meter. Keep it concise: a short title and "
            "up to ~6 short rows. Always also give a brief spoken summary in your reply."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "op": {
                    "type": "string",
                    "enum": ["card", "text", "toast", "clear"],
                    "description": (
                        "Card type. 'card' = title + rows; 'text' = title + body "
                        "paragraph; 'toast' = transient banner; 'clear' = clear the screen."
                    ),
                },
                "title": {"type": "string", "description": "Short title (<= ~24 chars)."},
                "subtitle": {"type": "string", "description": "Optional subtitle."},
                "rows": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Up to ~6 short lines (for op='card').",
                },
                "body": {"type": "string", "description": "Paragraph text (for op='text')."},
                "message": {"type": "string", "description": "Banner text (for op='toast')."},
                "icon": {
                    "type": "string",
                    "description": (
                        "Optional icon name: cloud, clock, check, warning, info, music, "
                        "home, media, calendar, mail."
                    ),
                },
                "accent": {
                    "type": "string",
                    "description": "Optional accent color as hex, e.g. #3b82f6.",
                },
                "meter": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "value": {"type": "number"},
                    },
                    "description": "Optional progress meter; value is 0..1.",
                },
                "ttl_ms": {
                    "type": "integer",
                    "description": "Auto-dismiss after this many ms; 0 or omit = persist.",
                },
            },
            "required": ["op"],
        }

    async def execute(self, **kwargs: Any) -> str:
        return "Card displayed on device."
