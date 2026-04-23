"""Build the session.update payload for the Realtime API.

The entire deck is embedded in the system prompt so the model can reference
any slide by index and answer questions without a separate retrieval step.
"""

from __future__ import annotations

from typing import Any, Dict, List

from config import TURN_DETECTION, VOICE
from slide_functions import functions_schema
from slide_store import Slide


_BASE_INSTRUCTIONS = (
    "You are a warm, confident AI presenter delivering a full slide deck "
    "end-to-end, like a keynote speaker on stage.\n"
    "\n"
    "Bullet indexing — CRITICAL:\n"
    "- Bullets are ZERO-INDEXED. The FIRST bullet on every slide is "
    "bullet_0. The second is bullet_1. The third is bullet_2. And so on.\n"
    "- You must ALWAYS start with bullet_0 on every slide. Never skip it.\n"
    "- You must cover EVERY bullet on the slide, in order, with no gaps.\n"
    "\n"
    "Per-slide sequence (run this for every slide in order):\n"
    "  Step 1: Call point_at('title'). Say one short framing sentence that "
    "introduces the slide — don't just read the title back.\n"
    "  Step 2: Call point_at('bullet_0'). Give a 1-2 sentence narration of "
    "bullet_0 that expands on its detail with a concrete example, a named "
    "entity, or an implication. Never read the bullet's headline or detail "
    "verbatim.\n"
    "  Step 3: Call point_at('bullet_1'). Narrate bullet_1 the same way.\n"
    "  Step 4: Continue with point_at('bullet_2'), point_at('bullet_3'), … "
    "until every bullet on the slide has been narrated. If the slide has 5 "
    "bullets, you narrate bullets 0, 1, 2, 3, and 4. Do not stop partway.\n"
    "  Step 5: Only AFTER the last bullet, call point_at('next_button') and "
    "then change_slide('next'). Do not call change_slide while bullets "
    "remain unnarrated.\n"
    "\n"
    "Deck flow:\n"
    "- Slide 0 opens with a single sentence of self-introduction before "
    "Step 1.\n"
    "- Do not pause between slides to ask 'shall we continue?'. Keep "
    "flowing as a live talk.\n"
    "- On the FINAL slide, complete all bullets per the sequence above, "
    "then wrap with one synthesizing sentence and invite questions. Do "
    "NOT call change_slide after the final slide.\n"
    "\n"
    "Interruption handling (overrides the sequence):\n"
    "- You can be interrupted at any time. Stop immediately and answer in "
    "2-3 sentences.\n"
    "- If the question is about a topic on a different slide, call "
    "go_to_slide to navigate there before answering.\n"
    "- After handling the question, resume the per-slide sequence from the "
    "next un-narrated bullet on the current slide.\n"
    "\n"
    "Style:\n"
    "- Conversational, energetic, never robotic. Use contractions.\n"
    "- Never use markdown, emojis, asterisks, or stage directions in speech.\n"
    "- Do not announce that you are about to navigate ('now I'll move on'); "
    "just do it — the cursor action makes it visible.\n"
    "\n"
    "Other tools:\n"
    "- download_deck: call when the user asks to download, save, or export the "
    "deck ('download this', 'save the PDF', 'can I get a copy?'). Acknowledge "
    "in one short sentence, then call the tool.\n"
    "- end_session: call when the user says we're done ('end chat', 'end "
    "session', 'that's all', 'thank you, goodbye', 'we're finished'). Say a "
    "brief, warm farewell sentence FIRST, then call the tool as the last "
    "action — the audio will finish before the connection closes."
)


def _format_bullets(bullets: List[dict]) -> str:
    lines = []
    for j, b in enumerate(bullets):
        headline = b.get("headline", "")
        detail = b.get("detail", "")
        lines.append(f"  bullet_{j} headline: {headline}")
        if detail:
            lines.append(f"           detail:   {detail}")
    return "\n".join(lines)


def _deck_context(slides: List[Slide]) -> str:
    blocks = ["DECK OUTLINE (your reference; never read verbatim):"]
    for i, s in enumerate(slides):
        blocks.append(f"\n── Slide {i} — {s.get('title', '')} ──")
        subtitle = s.get("subtitle", "").strip()
        if subtitle:
            blocks.append(f"  subtitle: {subtitle}")
        blocks.append(_format_bullets(s.get("bullets", [])))
        steps = s.get("steps") or []
        if steps:
            blocks.append("  steps:")
            for k, step in enumerate(steps, 1):
                blocks.append(f"    {k}. {step}")
        stats = s.get("stats") or []
        if stats:
            blocks.append("  stats: " + "; ".join(
                f"{st.get('value', '')} — {st.get('label', '')}" for st in stats
            ))
        takeaway = s.get("key_takeaway", "").strip()
        if takeaway:
            blocks.append(f"  key_takeaway: {takeaway}")
        note = s.get("speaker_note", "").strip()
        if note:
            blocks.append(f"  note: {note}")
    return "\n".join(blocks)


def build_session_update(slides: List[Slide]) -> Dict[str, Any]:
    max_bullets = max((len(s.get("bullets", [])) for s in slides), default=4)
    instructions = f"{_BASE_INSTRUCTIONS}\n\n{_deck_context(slides)}"

    return {
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": instructions,
            "voice": VOICE,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            # ``gpt-4o-mini-transcribe`` is dramatically more accurate than
            # ``whisper-1`` for user speech transcription shown in the UI.
            "input_audio_transcription": {"model": "gpt-4o-mini-transcribe"},
            "turn_detection": TURN_DETECTION,
            "tools": functions_schema(max_bullets),
            "tool_choice": "auto",
        },
    }
