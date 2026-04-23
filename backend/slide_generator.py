"""Generate a slide deck from a free-form prompt or from text extracted from
an uploaded file. Uses Azure OpenAI chat completions with a strict JSON schema.

Each slide carries richer structure than a title + bullets list:

* ``subtitle``     — optional one-line framing under the title
* ``bullets[]``    — objects with ``headline`` (punchy) and ``detail`` (a
                     full sentence or two of supporting content)
* ``steps[]``      — optional ordered process for how-to / procedural slides
* ``stats[]``      — optional metric cards (``value``, ``label``)
* ``key_takeaway`` — optional one-line summary surfaced as a footer
* ``speaker_note`` — conversational prose used by the voice agent for narration

Density is controlled by ``text_amount``: ``brief | medium | detailed | extensive``.
"""

from __future__ import annotations

import json
import logging
from typing import List, Tuple

from azure_client import chat_deployment, get_client, token_kwargs
from slide_store import Slide

logger = logging.getLogger(__name__)


TextAmount = str  # one of: brief | medium | detailed | extensive

_DENSITY: dict[str, dict] = {
    "brief": {
        "bullets": (3, 4),
        "detail_words": (18, 30),
        "note_words": (45, 70),
        "allow_stats": False,
        "allow_takeaway": True,
        "tokens": 3500,
        "description": (
            "Keep it tight but substantive. Each bullet has a short headline "
            "and ~20-word detail that adds one concrete fact, example, or caveat."
        ),
    },
    "medium": {
        "bullets": (4, 5),
        "detail_words": (30, 50),
        "note_words": (70, 110),
        "allow_stats": True,
        "allow_takeaway": True,
        "tokens": 5000,
        "description": (
            "Standard keynote density. Bullets have punchy headlines and "
            "~40-word details with a concrete example, a named entity, or a "
            "specific number. Include stats when they are genuinely informative."
        ),
    },
    "detailed": {
        "bullets": (5, 6),
        "detail_words": (45, 75),
        "note_words": (110, 170),
        "allow_stats": True,
        "allow_takeaway": True,
        "tokens": 7500,
        "description": (
            "In-depth content. Each bullet covers one sub-topic with a 2-sentence "
            "detail that includes a named example AND a supporting fact. Use "
            "subtitles to frame each slide. Include stats and a key_takeaway "
            "whenever the slide discusses quantitative or summative content. "
            "Use ``steps`` for any slide that describes a process or sequence."
        ),
    },
    "extensive": {
        "bullets": (5, 7),
        "detail_words": (60, 100),
        "note_words": (170, 260),
        "allow_stats": True,
        "allow_takeaway": True,
        "tokens": 10000,
        "description": (
            "Technical-briefing density. Every slide should include a subtitle "
            "and a key_takeaway. Bullet details are 2-3 sentences covering a "
            "mechanism, a named example, and a consequence or caveat. Use "
            "``steps`` generously for procedural content. Use ``stats`` where "
            "numbers strengthen the point. Speaker notes are rich enough that a "
            "presenter could read them directly."
        ),
    },
}


_BASE_STYLE = (
    "You are a senior slide-deck architect writing for a presentation that "
    "will be delivered by a voice agent. Output must be information-dense, "
    "concrete, and non-generic. Every slide should teach the audience "
    "something specific.\n\n"
    "Rules:\n"
    "- Bullet headlines are punchy fragments (~4-10 words, no trailing "
    "punctuation, no markdown).\n"
    "- Bullet details are full-sentence prose — specific names, dates, "
    "examples, numbers, mechanisms, or caveats. Never generic platitudes.\n"
    "- speaker_note is written to be spoken aloud: conversational, "
    "energetic, adds context the bullets don't show. Must not simply "
    "restate bullets.\n"
    "- Prefer concrete over abstract; prefer specific over vague.\n"
    "- No markdown, no emojis, no hedging phrases (``generally``, "
    "``various``, ``many``, ``important to note``).\n"
    "- Cover the topic in a logical arc across slides: setup → development → "
    "specifics → implications. First slide introduces, last slide synthesizes."
)


def _make_user_prompt(
    topic_or_source: str,
    count: int,
    kind: str,
    text_amount: str,
) -> str:
    density = _DENSITY[text_amount]
    bmin, bmax = density["bullets"]
    dmin, dmax = density["detail_words"]
    nmin, nmax = density["note_words"]

    header = (
        f"Create exactly {count} slides."
        if kind == "topic"
        else (
            f"Create exactly {count} slides that summarize and expand on the "
            "following source material. Do not paraphrase verbatim — "
            "reorganize and add context."
        )
    )
    label = "Topic" if kind == "topic" else "Source material"

    guidance = (
        f"Density profile: {text_amount.upper()}.\n"
        f"- {density['description']}\n"
        f"- Target {bmin}-{bmax} bullets per slide.\n"
        f"- Each bullet detail should run {dmin}-{dmax} words.\n"
        f"- Each speaker_note should run {nmin}-{nmax} words.\n"
    )
    if density["allow_stats"]:
        guidance += "- Include a ``stats`` array on 1-2 slides where numeric anchors genuinely help.\n"
    if density["allow_takeaway"]:
        guidance += "- Include a ``key_takeaway`` on slides that conclude an argument or synthesize content.\n"

    return f"{header}\n\n{guidance}\n{label}:\n{topic_or_source.strip()}"


def _schema_for(text_amount: str) -> dict:
    density = _DENSITY[text_amount]
    bmin, bmax = density["bullets"]

    return {
        "name": "slide_deck",
        "schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "subtitle": {"type": "string"},
                            "bullets": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "headline": {"type": "string"},
                                        "detail": {"type": "string"},
                                    },
                                    "required": ["headline", "detail"],
                                    "additionalProperties": False,
                                },
                                "minItems": bmin,
                                "maxItems": bmax,
                            },
                            "steps": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "stats": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "value": {"type": "string"},
                                        "label": {"type": "string"},
                                    },
                                    "required": ["value", "label"],
                                    "additionalProperties": False,
                                },
                            },
                            "key_takeaway": {"type": "string"},
                            "speaker_note": {"type": "string"},
                        },
                        "required": ["title", "bullets", "speaker_note"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["topic", "slides"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _coerce_slide(i: int, raw: dict) -> Slide:
    bullets_raw = raw.get("bullets") or []
    bullets: list[dict] = []
    for b in bullets_raw:
        if isinstance(b, dict):
            headline = str(b.get("headline", "")).strip()
            detail = str(b.get("detail", "")).strip()
        else:
            headline = str(b).strip()
            detail = ""
        if headline:
            bullets.append({"headline": headline[:140], "detail": detail[:600]})

    stats_raw = raw.get("stats") or []
    stats: list[dict] = []
    for s in stats_raw:
        if not isinstance(s, dict):
            continue
        value = str(s.get("value", "")).strip()
        label = str(s.get("label", "")).strip()
        if value and label:
            stats.append({"value": value[:40], "label": label[:80]})

    steps_raw = raw.get("steps") or []
    steps = [str(s).strip() for s in steps_raw if str(s).strip()][:8]

    slide: Slide = {
        "id": i + 1,
        "title": str(raw.get("title", f"Slide {i + 1}"))[:140],
        "bullets": bullets[:7],
        "speaker_note": str(raw.get("speaker_note", "")).strip()[:1200],
    }

    subtitle = str(raw.get("subtitle", "")).strip()
    if subtitle:
        slide["subtitle"] = subtitle[:200]

    if stats:
        slide["stats"] = stats[:4]

    if steps:
        slide["steps"] = steps

    takeaway = str(raw.get("key_takeaway", "")).strip()
    if takeaway:
        slide["key_takeaway"] = takeaway[:280]

    return slide


def generate_deck(
    topic_or_source: str,
    count: int,
    kind: str = "topic",
    text_amount: TextAmount = "medium",
) -> Tuple[str, List[Slide]]:
    """Return ``(topic, slides)``. ``kind`` is ``'topic'`` or ``'source'``."""

    if text_amount not in _DENSITY:
        text_amount = "medium"

    count = max(3, min(count, 12))
    client = get_client()
    model = chat_deployment()

    messages = [
        {"role": "system", "content": _BASE_STYLE},
        {
            "role": "user",
            "content": _make_user_prompt(topic_or_source, count, kind, text_amount),
        },
    ]

    token_budget = _DENSITY[text_amount]["tokens"]

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": _schema_for(text_amount)},
            **token_kwargs(token_budget, model),
        )
    except Exception:
        logger.warning("json_schema unsupported on %s, falling back to json_object", model)
        fallback_hint = {
            "role": "system",
            "content": (
                "Return ONLY valid JSON of shape: "
                '{"topic": str, "slides": [{"title": str, "subtitle"?: str, '
                '"bullets": [{"headline": str, "detail": str}], '
                '"steps"?: [str], "stats"?: [{"value": str, "label": str}], '
                '"key_takeaway"?: str, "speaker_note": str}]}'
            ),
        }
        resp = client.chat.completions.create(
            model=model,
            messages=messages + [fallback_hint],
            response_format={"type": "json_object"},
            **token_kwargs(token_budget, model),
        )

    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned invalid JSON: {exc}") from exc

    topic = (data.get("topic") or topic_or_source)[:200]
    raw_slides = data.get("slides") or []
    if not raw_slides:
        raise ValueError("Model produced zero slides")

    slides = [_coerce_slide(i, s) for i, s in enumerate(raw_slides)]
    slides = [s for s in slides if s.get("bullets")]
    if not slides:
        raise ValueError("All slides failed validation (empty bullets)")

    return topic, slides
