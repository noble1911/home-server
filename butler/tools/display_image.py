"""display_image tool — render a fully custom image on the user's ESP32 screen.

Claude writes an SVG; execute() is a deliberate no-op. The streaming pipeline in
llm.py intercepts the call and emits a ``device_image`` SSE event, which the
esp-gateway rasterizes (SVG -> PNG) and forwards to the device to blit full-card.
Complements display_on_device (structured cards) — use this when the visual design
matters. See claude-esp/PROTOCOL.md.
"""

from typing import Any

from .base import Tool


class DisplayImageTool(Tool):
    @property
    def name(self) -> str:
        return "display_image"

    @property
    def description(self) -> str:
        return (
            "Render a fully custom image on the user's physical device screen by writing "
            "an SVG. Use this when the visual design matters and a structured card can't "
            "express it — small charts/graphs, diagrams, a styled layout, a big headline "
            "number, custom graphics. Write a COMPLETE SVG sized exactly "
            "352x280 px: <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"352\" "
            "height=\"280\">...</svg>. A dark background (#0b0f17 or #111827) with light "
            "text (#ffffff / #d1d5db) and accent colours reads best on the AMOLED. Use "
            "system sans-serif fonts and keep text >=14px. Prefer display_on_device for "
            "simple glanceable cards; use display_image for richer visuals. Always also "
            "give a brief spoken summary of what's on screen."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "svg": {
                    "type": "string",
                    "description": (
                        "A complete, self-contained SVG document, 352x280 px, to rasterize "
                        "and display. No external references (fonts/images/URLs)."
                    ),
                },
            },
            "required": ["svg"],
        }

    async def execute(self, **kwargs: Any) -> str:
        return "Image displayed on device."
