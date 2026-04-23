"""FastAPI entry point.

Endpoints
---------
* ``GET  /healthz``              — liveness probe + active provider
* ``POST /api/decks/generate``   — body ``{ prompt, count }`` → new deck
* ``POST /api/decks/from-file``  — multipart file + optional count → new deck
* ``GET  /api/decks/{deck_id}``  — fetch deck payload (frontend hydration)
* ``WS   /ws/{deck_id}``         — Realtime relay scoped to that deck
"""

from __future__ import annotations

import logging

import uvicorn
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from config import ALLOWED_ORIGINS, realtime_config
from file_analyzer import extract_text
from pdf_export import build_deck_pdf
from realtime_relay import RealtimeRelay
from slide_generator import generate_deck
from slide_store import create_deck, get_deck

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="VoiceSlide AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)
    count: int = Field(6, ge=3, le=12)
    text_amount: str = Field("medium", pattern="^(brief|medium|detailed|extensive)$")


@app.get("/healthz")
async def healthz():
    rt = realtime_config()
    return {"status": "ok", "realtime_provider": rt.provider}


@app.post("/api/decks/generate")
async def decks_generate(req: GenerateRequest):
    try:
        topic, slides = generate_deck(
            req.prompt, req.count, kind="topic", text_amount=req.text_amount
        )
    except Exception as exc:
        logger.exception("generate failed")
        raise HTTPException(status_code=502, detail=f"generation failed: {exc}") from exc
    deck = create_deck(topic, req.text_amount, slides)
    return deck


@app.post("/api/decks/from-file")
async def decks_from_file(
    file: UploadFile = File(...),
    count: int = Form(6),
    extra_prompt: str = Form(""),
    text_amount: str = Form("medium"),
):
    if text_amount not in {"brief", "medium", "detailed", "extensive"}:
        raise HTTPException(status_code=400, detail="invalid text_amount")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        kind, text = extract_text(file.filename or "", file.content_type or "", data)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("extract failed")
        raise HTTPException(status_code=502, detail=f"extraction failed: {exc}") from exc

    if not text.strip():
        raise HTTPException(status_code=422, detail="could not extract any text")

    source = text if not extra_prompt.strip() else f"{extra_prompt.strip()}\n\n---\n{text}"

    try:
        topic, slides = generate_deck(
            source, count, kind="source", text_amount=text_amount
        )
    except Exception as exc:
        logger.exception("generate-from-file failed")
        raise HTTPException(status_code=502, detail=f"generation failed: {exc}") from exc

    deck = create_deck(topic, text_amount, slides)
    logger.info(
        "created deck %s from %s (%s) with %d slides",
        deck["id"], file.filename, kind, len(slides),
    )
    return deck


@app.get("/api/decks/{deck_id}")
async def decks_get(deck_id: str):
    deck = get_deck(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="deck not found")
    return deck


def _safe_filename(topic: str) -> str:
    keep = [c if c.isalnum() or c in (" ", "-", "_") else "-" for c in topic]
    cleaned = "".join(keep).strip().replace("  ", " ").replace(" ", "-")
    return (cleaned[:60] or "deck").lower()


@app.get("/api/decks/{deck_id}/pdf")
async def decks_pdf(deck_id: str):
    deck = get_deck(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="deck not found")
    try:
        pdf_bytes = build_deck_pdf(deck)
    except Exception as exc:
        logger.exception("pdf export failed")
        raise HTTPException(status_code=502, detail=f"pdf export failed: {exc}") from exc

    filename = f"{_safe_filename(deck['topic'])}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.websocket("/ws/{deck_id}")
async def ws_endpoint(websocket: WebSocket, deck_id: str):
    deck = get_deck(deck_id)
    if not deck:
        await websocket.close(code=4404, reason="deck not found")
        return

    await websocket.accept()
    logger.info("browser ws connected for deck %s", deck_id)

    try:
        rt = realtime_config()
        relay = RealtimeRelay(deck, rt)
        await relay.relay(websocket)
    except WebSocketDisconnect:
        logger.info("browser ws disconnected (deck %s)", deck_id)
    except Exception as exc:
        logger.exception("ws endpoint error: %s", exc)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9001, reload=True, log_level="info")
