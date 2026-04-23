"""In-memory deck store. Decks are keyed by ``deck_id`` and live only for the
lifetime of the process — sufficient for a single-presenter prototype, and the
swap-in point for Redis/Postgres in production.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, TypedDict
from uuid import uuid4


class Bullet(TypedDict, total=False):
    headline: str
    detail: str


class Stat(TypedDict, total=False):
    value: str
    label: str


class Slide(TypedDict, total=False):
    id: int
    title: str
    subtitle: str
    bullets: List[Bullet]
    steps: List[str]
    stats: List[Stat]
    key_takeaway: str
    speaker_note: str


class Deck(TypedDict):
    id: str
    topic: str
    text_amount: str
    slides: List[Slide]


_decks: Dict[str, Deck] = {}
_lock = threading.Lock()


def create_deck(topic: str, text_amount: str, slides: List[Slide]) -> Deck:
    deck_id = uuid4().hex[:12]
    deck: Deck = {
        "id": deck_id,
        "topic": topic,
        "text_amount": text_amount,
        "slides": slides,
    }
    with _lock:
        _decks[deck_id] = deck
    return deck


def get_deck(deck_id: str) -> Optional[Deck]:
    with _lock:
        return _decks.get(deck_id)


def slide_count(deck_id: str) -> int:
    deck = get_deck(deck_id)
    return len(deck["slides"]) if deck else 0
