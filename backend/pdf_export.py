"""Render a generated deck into a printable PDF.

One slide per A4-landscape page, typeset in the same minimalist ink palette
as the web UI: uppercase-tracked slide counter and progress bar at the top,
title + optional subtitle, optional stats row, bullets (headline + detail),
optional numbered process steps, and an optional takeaway rule + text.
"""

from __future__ import annotations

import unicodedata
from io import BytesIO
from typing import Sequence

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas as rl_canvas

from slide_store import Deck, Slide


_CHAR_REPLACEMENTS = {
    "\u2013": "-",   # en dash
    "\u2014": " - ", # em dash (spaced for readability)
    "\u2018": "'",   # left single quote
    "\u2019": "'",   # right single quote
    "\u201c": '"',   # left double quote
    "\u201d": '"',   # right double quote
    "\u2026": "...", # ellipsis
    "\u00a0": " ",   # non-breaking space
    "\u00b7": "-",   # middle dot
    "\u2022": "-",   # bullet
    "\u2192": "->",  # rightwards arrow
    "\u2190": "<-",  # leftwards arrow
    "\u00d7": "x",   # multiplication sign
    "\u2265": ">=",
    "\u2264": "<=",
    "\u2011": "-",   # non-breaking hyphen
    "\u2012": "-",   # figure dash
    "\u2015": "-",   # horizontal bar
    "\u2212": "-",   # minus sign
}


def _clean(text: str) -> str:
    """Normalize Unicode to a form Helvetica's WinAnsi encoding can render.

    1. Replace known punctuation variants with ASCII equivalents.
    2. Decompose remaining accented characters and drop the combining marks
       (``Rikyū`` → ``Rikyu``). Keeps any surviving char in the Latin-1
       supplement range that reportlab's default font supports.
    """

    if not text:
        return ""
    for k, v in _CHAR_REPLACEMENTS.items():
        text = text.replace(k, v)
    decomposed = unicodedata.normalize("NFKD", text)
    out = []
    for ch in decomposed:
        if unicodedata.combining(ch):
            continue
        if ord(ch) < 256:
            out.append(ch)
        else:
            out.append("?")
    return "".join(out)


_INK_950 = (0.047, 0.039, 0.035)
_INK_900 = (0.110, 0.098, 0.090)
_INK_700 = (0.267, 0.251, 0.235)
_INK_500 = (0.471, 0.443, 0.424)
_INK_400 = (0.659, 0.635, 0.616)
_INK_300 = (0.839, 0.827, 0.816)
_INK_200 = (0.906, 0.898, 0.886)
_INK_100 = (0.961, 0.961, 0.953)
_INK_50 = (0.980, 0.980, 0.973)


def build_deck_pdf(deck: Deck) -> bytes:
    buf = BytesIO()
    page_w, page_h = landscape(A4)
    c = rl_canvas.Canvas(buf, pagesize=landscape(A4))
    c.setTitle(deck["topic"])
    c.setAuthor("VoiceSlide")
    c.setSubject("AI-generated deck")

    margin = 54
    slides = deck["slides"]
    total = len(slides)

    for idx, slide in enumerate(slides):
        _draw_slide(c, slide, idx, total, page_w, page_h, margin)
        c.showPage()

    c.save()
    return buf.getvalue()


def _set_fill(c: rl_canvas.Canvas, color: tuple[float, float, float]) -> None:
    c.setFillColorRGB(*color)


def _set_stroke(c: rl_canvas.Canvas, color: tuple[float, float, float]) -> None:
    c.setStrokeColorRGB(*color)


def _draw_tracked_caps(
    c: rl_canvas.Canvas,
    x: float,
    y: float,
    text: str,
    size: float = 7.5,
    tracking: float = 1.8,
) -> None:
    to = c.beginText(x, y)
    to.setFont("Helvetica-Bold", size)
    to.setCharSpace(tracking)
    to.textOut(text.upper())
    c.drawText(to)


def _draw_slide(
    c: rl_canvas.Canvas,
    slide: Slide,
    idx: int,
    total: int,
    page_w: float,
    page_h: float,
    margin: float,
) -> None:
    inner_w = page_w - 2 * margin
    y = page_h - margin

    _set_fill(c, _INK_500)
    _draw_tracked_caps(c, margin, y - 8, f"SLIDE {idx + 1} OF {total}")

    bar_w = 140
    bar_h = 3
    bar_x = page_w - margin - bar_w
    bar_y = y - 6 - bar_h
    _set_fill(c, _INK_200)
    c.roundRect(bar_x, bar_y, bar_w, bar_h, 1.5, fill=1, stroke=0)
    progress = (idx + 1) / max(total, 1)
    _set_fill(c, _INK_900)
    c.roundRect(bar_x, bar_y, bar_w * progress, bar_h, 1.5, fill=1, stroke=0)

    y -= 46

    _set_fill(c, _INK_950)
    title_size = 26
    title_text = _clean(slide.get("title", ""))
    title_lines = simpleSplit(
        title_text, "Helvetica-Bold", title_size, inner_w * 0.82
    )
    c.setFont("Helvetica-Bold", title_size)
    for line in title_lines[:3]:
        c.drawString(margin, y, line)
        y -= title_size * 1.15

    subtitle = _clean((slide.get("subtitle") or "").strip())
    if subtitle:
        y -= 4
        _set_fill(c, _INK_500)
        c.setFont("Helvetica", 12.5)
        sub_lines = simpleSplit(subtitle, "Helvetica", 12.5, inner_w * 0.85)
        for line in sub_lines[:2]:
            c.drawString(margin, y, line)
            y -= 15

    y -= 16

    stats = slide.get("stats") or []
    if stats:
        y = _draw_stats(c, stats, margin, y, inner_w)
        y -= 8

    y = _draw_bullets(c, slide.get("bullets") or [], margin, y, inner_w, page_h, margin)

    steps = slide.get("steps") or []
    if steps and y > margin + 80:
        y = _draw_steps(c, steps, margin, y, inner_w, margin)

    takeaway = (slide.get("key_takeaway") or "").strip()
    if takeaway and y > margin + 50:
        _draw_takeaway(c, takeaway, margin, y, inner_w, page_w)

    _set_fill(c, _INK_400)
    c.setFont("Helvetica", 7)
    c.drawString(margin, margin - 18, "VoiceSlide")
    c.drawRightString(page_w - margin, margin - 18, f"{idx + 1} / {total}")


def _draw_stats(
    c: rl_canvas.Canvas,
    stats: Sequence[dict],
    x: float,
    y: float,
    inner_w: float,
) -> float:
    stats = list(stats)[:4]
    n = len(stats)
    if n == 0:
        return y
    gap = 12
    card_w = (inner_w - (n - 1) * gap) / n
    card_h = 56
    start_y = y - card_h

    for i, st in enumerate(stats):
        cx = x + i * (card_w + gap)
        _set_stroke(c, _INK_200)
        _set_fill(c, _INK_50)
        c.setLineWidth(0.6)
        c.roundRect(cx, start_y, card_w, card_h, 8, fill=1, stroke=1)

        value = _clean(str(st.get("value", "")))
        label = _clean(str(st.get("label", "")))

        _set_fill(c, _INK_950)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(cx + 14, start_y + card_h - 24, value[:18])

        _set_fill(c, _INK_500)
        _draw_tracked_caps(
            c, cx + 14, start_y + 12, label[:48], size=6.5, tracking=1.4
        )

    return start_y - 18


_BULLET_HEAD_SIZE = 10.5
_BULLET_HEAD_LEADING = 13
_BULLET_DETAIL_SIZE = 9
_BULLET_DETAIL_LEADING = 11.5
_BULLET_ROW_GAP = 10
_BULLET_TEXT_INDENT = 17


def _measure_bullet(bullet: dict, wrap_w: float) -> float:
    """Estimate the vertical space the bullet will consume at the given width."""

    headline = _clean(str(bullet.get("headline", "")).strip())
    detail = _clean(str(bullet.get("detail", "")).strip())
    head_lines = min(
        len(simpleSplit(headline, "Helvetica-Bold", _BULLET_HEAD_SIZE, wrap_w)), 3
    )
    detail_lines = (
        len(simpleSplit(detail, "Helvetica", _BULLET_DETAIL_SIZE, wrap_w))
        if detail else 0
    )
    return head_lines * _BULLET_HEAD_LEADING + detail_lines * _BULLET_DETAIL_LEADING + 4


def _draw_one_bullet(
    c: rl_canvas.Canvas,
    bullet: dict,
    x: float,
    y: float,
    wrap_w: float,
    max_detail_lines: int | None = None,
) -> float:
    """Draw a single bullet at ``(x, y)``. Returns final y after drawing."""

    _set_fill(c, _INK_300)
    c.circle(x + 4, y - 5, 2.4, fill=1, stroke=0)

    headline = _clean(str(bullet.get("headline", "")).strip())
    detail = _clean(str(bullet.get("detail", "")).strip())

    text_x = x + _BULLET_TEXT_INDENT
    head_y = y - 3

    _set_fill(c, _INK_950)
    c.setFont("Helvetica-Bold", _BULLET_HEAD_SIZE)
    head_lines = simpleSplit(headline, "Helvetica-Bold", _BULLET_HEAD_SIZE, wrap_w)
    for line in head_lines[:3]:
        c.drawString(text_x, head_y, line)
        head_y -= _BULLET_HEAD_LEADING

    cur_y = head_y

    if detail:
        _set_fill(c, _INK_700)
        c.setFont("Helvetica", _BULLET_DETAIL_SIZE)
        detail_lines = simpleSplit(
            detail, "Helvetica", _BULLET_DETAIL_SIZE, wrap_w
        )
        if max_detail_lines is not None:
            detail_lines = detail_lines[:max_detail_lines]
        for line in detail_lines:
            c.drawString(text_x, cur_y, line)
            cur_y -= _BULLET_DETAIL_LEADING

    return cur_y


def _draw_bullets(
    c: rl_canvas.Canvas,
    bullets: Sequence[dict],
    x: float,
    y: float,
    inner_w: float,
    page_h: float,
    bottom_margin: float,
) -> float:
    """Single column for ≤3 bullets, 2-column grid otherwise (matches UI)."""

    _ = page_h
    bullets = list(bullets)
    if not bullets:
        return y

    use_two_col = len(bullets) >= 4

    if not use_two_col:
        wrap_w = inner_w - _BULLET_TEXT_INDENT - 6
        for bullet in bullets:
            if y < bottom_margin + 50:
                break
            y = _draw_one_bullet(c, bullet, x, y, wrap_w) - _BULLET_ROW_GAP
        return y

    # Two-column snake-fill: row i has bullet[i*2] (left) and bullet[i*2+1] (right)
    col_gap = 28
    col_w = (inner_w - col_gap) / 2
    wrap_w = col_w - _BULLET_TEXT_INDENT - 6
    right_x = x + col_w + col_gap

    rows: list[tuple[dict, dict | None]] = []
    for i in range(0, len(bullets), 2):
        rows.append((bullets[i], bullets[i + 1] if i + 1 < len(bullets) else None))

    for left_b, right_b in rows:
        row_start = y
        if row_start < bottom_margin + 50:
            break

        left_h = _measure_bullet(left_b, wrap_w)
        right_h = _measure_bullet(right_b, wrap_w) if right_b else 0
        row_h = max(left_h, right_h)

        remaining = row_start - (bottom_margin + 30)
        if remaining < row_h:
            # Truncate detail lines to fit remaining height
            per_line = _BULLET_DETAIL_LEADING
            cap = max(1, int((remaining - 2 * _BULLET_HEAD_LEADING) / per_line))
        else:
            cap = None

        _draw_one_bullet(c, left_b, x, row_start, wrap_w, cap)
        if right_b:
            _draw_one_bullet(c, right_b, right_x, row_start, wrap_w, cap)

        y = row_start - row_h - _BULLET_ROW_GAP

    return y


def _draw_steps(
    c: rl_canvas.Canvas,
    steps: Sequence[str],
    x: float,
    y: float,
    inner_w: float,
    bottom_margin: float,
) -> float:
    y -= 4
    _set_fill(c, _INK_400)
    _draw_tracked_caps(c, x, y, "PROCESS", size=6.5, tracking=1.4)
    y -= 14

    for i, step in enumerate(steps, start=1):
        if y < bottom_margin + 40:
            break
        _set_stroke(c, _INK_300)
        _set_fill(c, _INK_50)
        c.setLineWidth(0.6)
        c.circle(x + 8, y - 2, 8, fill=0, stroke=1)
        _set_fill(c, _INK_700)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x + 8, y - 4.5, str(i))

        _set_fill(c, _INK_700)
        c.setFont("Helvetica", 10)
        step_text = _clean(str(step))
        step_lines = simpleSplit(step_text, "Helvetica", 10, inner_w - 30)
        line_y = y - 2
        for line in step_lines[:3]:
            c.drawString(x + 22, line_y, line)
            line_y -= 13
        y = line_y - 4

    return y


def _draw_takeaway(
    c: rl_canvas.Canvas,
    takeaway: str,
    x: float,
    y: float,
    inner_w: float,
    page_w: float,
) -> None:
    y -= 8
    _set_stroke(c, _INK_200)
    c.setLineWidth(0.6)
    c.line(x, y, page_w - x, y)
    y -= 16

    _set_fill(c, _INK_500)
    _draw_tracked_caps(c, x, y, "TAKEAWAY", size=7, tracking=1.6)

    _set_fill(c, _INK_900)
    c.setFont("Helvetica-Bold", 10.5)
    take_lines = simpleSplit(_clean(takeaway), "Helvetica-Bold", 10.5, inner_w - 90)
    for i, line in enumerate(take_lines[:3]):
        c.drawString(x + 80, y - i * 13, line)
