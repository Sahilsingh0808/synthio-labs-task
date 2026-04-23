# VoiceSlide — backend

FastAPI + OpenAI SDK (Azure-routed) + WebSocket relay + reportlab PDF export.

> For the full architecture, event-level protocol, and every design decision, read [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in credentials
uvicorn main:app --reload --port 8000
```

## Endpoints

| Method | Path                         | Purpose                                      |
| ------ | ---------------------------- | -------------------------------------------- |
| GET    | `/healthz`                   | liveness + active realtime provider          |
| POST   | `/api/decks/generate`        | `{ prompt, count, text_amount }` → deck JSON |
| POST   | `/api/decks/from-file`       | multipart `file`, `count`, `text_amount`, `extra_prompt` |
| GET    | `/api/decks/{deck_id}`       | hydrate a deck                               |
| GET    | `/api/decks/{deck_id}/pdf`   | A4-landscape PDF download                    |
| WS     | `/ws/{deck_id}`              | bidirectional audio + events                 |

## Module map

- `config.py` — env loading. Handles V1 model routing (`AZURE_V1_MODELS`), URL normalization (`_build_azure_ws_url`, `_normalize_chat_endpoint`, `_resource_base`), dedicated realtime key with fallback, provider selection (Azure vs OpenAI) for realtime.
- `azure_client.py` — cached `OpenAI(base_url=..., api_key=...)` + `token_kwargs()` helper for GPT-5 / o-series.
- `slide_generator.py` — prompt → density-aware strict-JSON deck. `_DENSITY` dictates bullet count, detail length, speaker-note length, token budget, and whether stats/takeaway are included per text_amount (brief / medium / detailed / extensive).
- `file_analyzer.py` — PDF (pypdf), PPTX (python-pptx), image (vision chat), text → plain text (20k-char cap).
- `slide_store.py` — in-memory per-session deck store. `TypedDict` schemas for `Slide` / `Bullet` / `Stat` / `Deck`.
- `slide_functions.py` — 5 function-call schemas + stateful `SlideNavigator`. Handlers emit browser events (`slide_change`, `cursor_move`, `download_deck`, `end_session`) + tool output.
- `session_config.py` — builds `session.update` payload. Continuous-flow system prompt, `gpt-4o-mini-transcribe` transcription, deck embedded as `_deck_context`.
- `realtime_relay.py` — browser ⇄ provider relay. Uses `extra_headers` (legacy websockets client). Intercepts `response.function_call_arguments.done` and `client.*` events.
- `pdf_export.py` — reportlab A4-landscape renderer. 2-column bullets for 4+, stats cards, steps, takeaway. `_clean()` NFKD + WinAnsi normalization for non-ASCII.
- `main.py` — FastAPI app wiring. Pydantic validation. `/pdf` returns `Content-Disposition: attachment`.

## Tool contract (exposed to the model)

```text
change_slide(direction: "next" | "prev")
go_to_slide(index: integer)
point_at(target: "title" | "bullet_0" | ... | "bullet_N" | "next_button" | "prev_button")
download_deck()
end_session()
```

`point_at` is frequently-called: the system prompt trains the model to call it on every slide entry and before every bullet. `download_deck` and `end_session` are voice-triggered actions. The relay forwards the target verbatim as a browser event.

## Slide JSON shape

```ts
{
  id: number,
  title: string,
  subtitle?: string,
  bullets: { headline: string, detail: string }[],
  steps?: string[],
  stats?: { value: string, label: string }[],
  key_takeaway?: string,
  speaker_note: string,   // agent-only
}
```

## Env highlights

- `AZURE_OPENAI_CHAT_DEPLOYMENT` — if it matches a V1 model, chat traffic routes to `AZURE_OPENAI_REALTIME_ENDPOINT` resource using `AZURE_OPENAI_REALTIME_API_KEY`.
- `AZURE_OPENAI_REALTIME_ENDPOINT` — can be a full `wss://…?api-version=…&deployment=…` URL or a bare `https://…`; config layer normalizes either.
- See the root [`README.md`](../README.md) for the full env table.
