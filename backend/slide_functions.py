"""Function-call schemas exposed to the Realtime model.

Three tools:

* ``change_slide(direction)`` — sequential navigation.
* ``go_to_slide(index)`` — jump to a specific 0-based slide.
* ``point_at(target)`` — move the virtual cursor to a UI element on the
  current slide. Targets include ``title``, ``bullet_{N}``, ``next_button``,
  ``prev_button``. This is the mechanic that makes the agent feel embodied —
  it literally gestures at what it is talking about.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from slide_store import get_deck, slide_count

logger = logging.getLogger(__name__)


def functions_schema(max_bullets: int) -> list[dict]:
    bullet_targets = [f"bullet_{i}" for i in range(max_bullets)]
    return [
        {
            "type": "function",
            "name": "change_slide",
            "description": (
                "Move one slide forward or backward. Use for sequential navigation "
                "like 'next slide' or 'go back'. Before calling, first call "
                "point_at with 'next_button' or 'prev_button' so the audience "
                "sees the cursor press the control."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["next", "prev"],
                    }
                },
                "required": ["direction"],
            },
        },
        {
            "type": "function",
            "name": "go_to_slide",
            "description": (
                "Jump directly to a specific slide. The slide_number is "
                "1-BASED to match what the user sees ('Slide 3 of 6' in the UI). "
                "Examples: user says 'go to slide 1' or 'the first slide' → "
                "slide_number=1. User says 'slide 4' → slide_number=4. Never "
                "pass 0 or a larger number than the last slide."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slide_number": {"type": "integer", "minimum": 1},
                },
                "required": ["slide_number"],
            },
        },
        {
            "type": "function",
            "name": "point_at",
            "description": (
                "Move the on-screen cursor to a UI target so the audience sees what "
                "you are referring to. Call this often: when you introduce a slide "
                "point at 'title'; as you explain each bullet point at the matching "
                "'bullet_N'; before navigating, point at 'next_button' or 'prev_button'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "enum": ["title", "next_button", "prev_button", *bullet_targets],
                    }
                },
                "required": ["target"],
            },
        },
        {
            "type": "function",
            "name": "download_deck",
            "description": (
                "Trigger a PDF download of the current deck in the user's browser. "
                "Call this when the user says things like 'download this', "
                "'download the deck', 'save this as a PDF', or 'export the slides'. "
                "Briefly confirm with one sentence before calling."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "type": "function",
            "name": "end_session",
            "description": (
                "End the current presentation and disconnect the voice link. "
                "Call this when the user says things like 'end chat', 'end session', "
                "'we're done', 'that's all', or 'goodbye'. Say a short farewell "
                "sentence FIRST, then call this as the final action — the audio "
                "will finish playing before the session closes."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    ]


class SlideNavigator:
    def __init__(self, deck_id: str) -> None:
        self.deck_id = deck_id
        self.index = 0

    @property
    def last_index(self) -> int:
        return max(0, slide_count(self.deck_id) - 1)

    def next(self) -> int:
        self.index = min(self.index + 1, self.last_index)
        return self.index

    def prev(self) -> int:
        self.index = max(self.index - 1, 0)
        return self.index

    def go_to(self, i: int) -> int:
        self.index = max(0, min(i, self.last_index))
        return self.index

    def current(self) -> dict:
        deck = get_deck(self.deck_id)
        if not deck or not deck["slides"]:
            return {"id": 0, "title": "", "bullets": [], "speaker_note": ""}
        return deck["slides"][self.index]


async def handle_function_call(
    name: str,
    arguments: str,
    navigator: SlideNavigator,
) -> Dict[str, Any]:
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        args = {}

    if name == "change_slide":
        direction = args.get("direction", "next")
        new_index = navigator.next() if direction == "next" else navigator.prev()
        return {
            "browser_event": {
                "type": "slide_change",
                "new_index": new_index,
                "slide": navigator.current(),
            },
            "tool_output": {
                "success": True,
                "new_index": new_index,
                "title": navigator.current().get("title", ""),
            },
        }

    if name == "go_to_slide":
        # Accept both the new 1-based ``slide_number`` and the legacy 0-based
        # ``index`` so old in-flight sessions don't break on deploy.
        if "slide_number" in args:
            target_index = int(args.get("slide_number", 1)) - 1
        else:
            target_index = int(args.get("index", 0))
        new_index = navigator.go_to(target_index)
        return {
            "browser_event": {
                "type": "slide_change",
                "new_index": new_index,
                "slide": navigator.current(),
            },
            "tool_output": {
                "success": True,
                "slide_number": new_index + 1,
                "title": navigator.current().get("title", ""),
            },
        }

    if name == "point_at":
        target = args.get("target", "title")
        return {
            "browser_event": {
                "type": "cursor_move",
                "target": target,
            },
            "tool_output": {"success": True, "target": target},
        }

    if name == "download_deck":
        return {
            "browser_event": {"type": "download_deck"},
            "tool_output": {"success": True, "message": "PDF download started"},
        }

    if name == "end_session":
        return {
            "browser_event": {"type": "end_session"},
            "tool_output": {"success": True, "message": "Session ending"},
        }

    logger.warning("Unknown function call: %s", name)
    return {
        "browser_event": None,
        "tool_output": {"success": False, "error": f"unknown function {name}"},
    }
