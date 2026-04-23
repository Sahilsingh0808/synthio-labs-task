# VoiceSlide

> A voice-driven presentation prototype. Describe a topic (or upload a slide), and an AI agent builds a structured deck, narrates it end-to-end, answers questions on any slide, and navigates the deck in real time — with a virtual cursor that gestures at what it's talking about and voice commands like _"download this deck"_ or _"end chat"_.

Built as an interview take-home for Synthio Labs.

> **For the deep dive — every workflow, every event, every design decision — read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).** This README is the 60-second version.

---

## What it does

1. **Setup** — prompt _or_ upload a source file (PDF / PPTX / image / text). Pick slide count (4-8) and **Text Amount** (Brief / Medium / Detailed / Extensive).
2. **Generation** — Azure OpenAI returns a strict-JSON deck where each slide carries a title, optional subtitle, rich bullets (`{ headline, detail }`), optional stats cards, optional numbered steps, optional key takeaway, and a conversational speaker note.
3. **Presentation (16:9 canvas)** — open a bi-directional audio session with the Realtime API. The agent:
   - Walks the **entire deck end-to-end** by default, like a keynote speaker — only stops on interruption or at the final slide.
   - Narrates each slide conversationally, expanding bullet details with examples and implications.
   - Can be **interrupted mid-sentence** (server-side VAD, ~30 ms to silence).
   - Navigates automatically via function calls (`change_slide`, `go_to_slide`) when the user asks about a different topic.
   - Drives an on-screen **agent cursor** via `point_at(target)` — points at the bullet it's explaining, "clicks" the nav buttons before advancing.
   - Responds to voice commands:
     - _"download this deck"_ → PDF download triggers.
     - _"end chat"_ / _"goodbye"_ → agent says a farewell, then the session closes.
4. **Manual controls** — keyboard `← →`, prev/next buttons, and a **Download PDF** button in the header stay in sync with the agent.
5. **Export** — printable **A4 landscape PDF** with the same layout as on-screen (2-column bullets, stats cards, takeaway footer).

---

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│                    Browser (React + Vite)                 │
│                                                           │
│  SetupScreen ───▶ PresentationView                        │
│    ├── 16:9 slide canvas (CSS container queries)          │
│    │   └── AutoFitSlide   (uniform scale-to-fit)          │
│    │       └── SlideView  (title, bullets, stats, steps,  │
│    │                       takeaway, 2-col on landscape)  │
│    ├── AgentCursor     (animated pointer by DOM target)   │
│    ├── TranscriptPanel (sticky-to-bottom, "Listening…")   │
│    └── Controls + Download PDF button                     │
│                                                           │
│  Zustand store  ◀──▶  useRealtimeSession                  │
│                         └─ useAudioStream (PCM16 in/out)  │
└───────────────────┬───────────────────────────────────────┘
                    │  REST  (/api/decks/*, /pdf)
                    │  WS    (/ws/{deck_id})
                    ▼
┌───────────────────────────────────────────────────────────┐
│                 FastAPI backend (Python)                  │
│                                                           │
│  REST endpoints                                           │
│    POST /api/decks/generate    chat JSON (density-aware)  │
│    POST /api/decks/from-file   extract + generate         │
│    GET  /api/decks/{id}        hydrate                    │
│    GET  /api/decks/{id}/pdf    reportlab landscape PDF    │
│                                                           │
│  WebSocket /ws/{deck_id}  ──▶  RealtimeRelay              │
│    • session.update (deck embedded in instructions)       │
│    • forwards audio + events                              │
│    • intercepts response.function_call_arguments.done:    │
│      ├── change_slide / go_to_slide ▶ slide_change        │
│      ├── point_at                   ▶ cursor_move         │
│      ├── download_deck              ▶ download_deck       │
│      └── end_session                ▶ end_session         │
│    • intercepts client.manual_slide ▶ narration hint      │
└─────┬───────────────────────────────────────┬─────────────┘
      │                                       │
      │  Chat (OpenAI SDK + base_url,         │  wss:// realtime
      │        model-aware routing)           │
      ▼                                       ▼
  Foundry project OR V1 resource        Azure OpenAI Realtime (default)
  (routed per chat deployment)            or OpenAI Realtime (fallback)
```

### Why a server-side relay?

- **Security** — the API key never reaches the browser.
- **Interception** — `function_call` events translate into UI-native `slide_change` / `cursor_move` / `download_deck` / `end_session` events.
- **Control** — centralized logging, per-deck session state, and `client.*` control events for manual navigation.
- **Model-aware routing** — different Azure deployments live on different resources with different keys; the config layer picks the right one transparently.

### Why `point_at`?

Voice alone is a thin channel. When the agent says _"and on the second bullet…"_, the audience has to do the mapping. A virtual cursor the agent drives via a function call closes that loop. Targets are DOM-static (`title`, `bullet_N`, `next_button`, `prev_button`), each marked with `data-cursor-target="…"` in React. The `AgentCursor` component looks up the element by attribute and eases to its position with a 480 ms cubic bezier.

### Why Azure OpenAI via `OpenAI(base_url=…)`?

The OpenAI Python SDK works against Azure if you point `base_url` at the v1 compatibility endpoint (`…/openai/v1/`). No manual `api-version` handling. The config layer supports **GPT-5.x chat deployments routed to the realtime resource** — configured via `AZURE_V1_MODELS` in `config.py`.

---

## Getting started

### Prerequisites

- Python 3.11+ (3.9 works too)
- Node.js 18+
- Azure OpenAI resources with a chat deployment + a Realtime deployment — or OpenAI API key with Realtime access for the fallback path.

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your Azure (or OpenAI) credentials
uvicorn main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/healthz` → active realtime provider.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env   # optional; defaults point at localhost:8000
npm run dev
```

Open `http://localhost:5173`, grant mic permission, and click **Build deck**.

### Environment variables (backend)

| Variable                             | Required                 | Notes |
| ------------------------------------ | ------------------------ | ----- |
| `AZURE_OPENAI_ENDPOINT`              | ✓                        | Foundry project or classic Azure OpenAI. Any shape — normalized to `/openai/v1/`. |
| `AZURE_OPENAI_API_KEY`               | ✓                        | Chat key. Also used as realtime fallback. |
| `AZURE_OPENAI_CHAT_DEPLOYMENT`       | optional (`gpt-5-mini`)  | If this matches one of the **V1 models** (`gpt-5.2-chat`, `gpt-5.3-chat`, `gpt-5.4-mini`), chat traffic is routed to the realtime resource using `AZURE_OPENAI_REALTIME_API_KEY` instead. |
| `AZURE_OPENAI_REALTIME_ENDPOINT`     | optional                 | Realtime host. Accepts `https://` or `wss://`, with or without `?api-version=…&deployment=…` baked in. |
| `AZURE_OPENAI_REALTIME_API_KEY`      | optional                 | Dedicated realtime key. Recommended when realtime lives on a different Azure resource than chat. Falls back to `AZURE_OPENAI_API_KEY`. |
| `AZURE_OPENAI_REALTIME_DEPLOYMENT`   | optional                 | Realtime deployment name. Skipped if already in endpoint URL. |
| `AZURE_OPENAI_REALTIME_API_VERSION`  | optional (`2024-10-01-preview`) | Same — skipped if endpoint already has `api-version=…`. |
| `OPENAI_API_KEY`                     | required if Azure realtime not set | Realtime fallback. |
| `VOICE`                              | optional (`alloy`)       | |
| `ALLOWED_ORIGIN`                     | optional                 | CORS origin for frontend (default `http://localhost:5173`). |

---

## Project layout

```
synthio-labs-task/
├── README.md                         ← you are here
├── docs/ARCHITECTURE.md              ← deep architecture walkthrough
├── backend/
│   ├── main.py                       FastAPI app + endpoints
│   ├── config.py                     env loader, V1 routing, URL normalization
│   ├── azure_client.py               OpenAI SDK with Azure base_url
│   ├── slide_generator.py            prompt/source → density-aware JSON
│   ├── file_analyzer.py              PDF / PPTX / image / text → text
│   ├── slide_store.py                in-memory per-session deck store
│   ├── slide_functions.py            5 tool schemas + handle_function_call
│   ├── session_config.py             session.update payload builder
│   ├── realtime_relay.py             browser ⇄ provider relay
│   ├── pdf_export.py                 reportlab A4 landscape renderer
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── src/
    │   ├── App.tsx
    │   ├── types.ts
    │   ├── lib/api.ts
    │   ├── store/usePresentationStore.ts
    │   ├── hooks/
    │   │   ├── useAudioStream.ts
    │   │   └── useRealtimeSession.ts
    │   └── components/
    │       ├── SetupScreen.tsx       prompt + upload + density chips + examples
    │       ├── PresentationView.tsx  16:9 layout + keyboard + session wiring
    │       ├── AutoFitSlide.tsx      scale-to-fit inside the 16:9 canvas
    │       ├── SlideView.tsx         rich-content renderer (bullets, stats, …)
    │       ├── AgentCursor.tsx       animated pointer driven by DOM target
    │       ├── Controls.tsx          mic, prev/next, status
    │       └── TranscriptPanel.tsx   sticky-to-bottom with "Listening…"
    └── package.json
```

---

## Design decisions (highlights)

- **Five tools, not three.** `change_slide` / `go_to_slide` (nav), `point_at` (cursor), `download_deck` / `end_session` (voice actions).
- **Rich slide schema.** Bullets are `{ headline, detail }` pairs; optional subtitle / stats / steps / takeaway. Lets `SlideView` render like a designed slide.
- **Text-amount densities.** Brief / Medium / Detailed / Extensive control bullet count, detail length, token budget, and whether stats/takeaways/steps appear.
- **16:9 canvas + auto-fit.** CSS container queries size the card, JS uniformly scales the inner content to fit.
- **2-column bullets on landscape** in both UI and PDF — fills the wider aspect gracefully.
- **Continuous flow by default.** Prompt explicitly says _"Do not pause between slides unless interrupted."_
- **Begin/complete user-turn pattern.** Placeholder on `speech_started`, text fills in on `…transcription.completed` — preserves conversational order.
- **`gpt-4o-mini-transcribe`** over `whisper-1` — much better transcription accuracy.
- **Deck embedded in system prompt.** Small enough, lets the model pick slide indices directly.
- **Manual nav is a first-class event.** `client.manual_slide` keeps backend in sync; model narrates new slide and continues the flow.
- **Interruption flushes playback.** Scheduled `AudioBufferSourceNode`s get `.stop()`; ~30 ms to silence.
- **Zustand over Redux.** Single store file, zero boilerplate.
- **PDF via reportlab.** Pure-Python, deterministic, no browser dependency. Character normalization (NFKD + WinAnsi subset) prevents tombstones.
- **ScriptProcessorNode over AudioWorklet.** Worklet is the production path; SPN works on localhost without worker files or HTTPS.
- **Swiss-spa UI.** Warm-neutral ink palette, Inter, generous whitespace, Lucide icons (never emojis), hairline borders, one accent interaction (agent cursor).

---

## Known limitations

| Limitation | Production path |
| --- | --- |
| `ScriptProcessorNode` is deprecated | Migrate to `AudioWorklet` off the main thread |
| No auth on `/ws` | Signed deck tokens, short-lived, bound to session |
| In-memory deck store | Redis / Postgres for persistence and horizontal scaling |
| Single presenter | Per-connection session IDs, rate limit per deck |
| PDF length cap at 20 000 chars | Chunk + map-reduce summarization |
| No slide preview sidebar | Thumbnail rail + manual jump (cursor could retarget to rail items) |
| Helvetica-only PDF fonts | Register Inter TTF for stricter visual parity |
| Continuous flow baked in prompt | Optional "stop after each slide" session flag |

---

## Further reading

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — full architecture and workflow walkthrough: every event, every design decision, every trade-off.
- [`backend/README.md`](backend/README.md) — backend module map and endpoint contract.
- [`frontend/README.md`](frontend/README.md) — frontend module map and audio pipeline.

## Acknowledgements

The Realtime relay + PCM16 pipeline pattern is adapted from the reference prototype in the interview brief. The rich slide schema, agent cursor, 16:9 canvas with auto-fit scaling, voice-controlled download / end-session, PDF export, model-aware Azure routing, density dial, and manual-sync navigation are original to this submission.
