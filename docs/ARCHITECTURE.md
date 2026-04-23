# VoiceSlide — Architecture & Workflow

A deep walkthrough of **what happens end-to-end**, **why each decision was made**, and **every contract between the moving parts**. Read the root `README.md` first for the 60-second pitch; this document is the engineering companion.

---

## Table of contents

1. [Problem framing](#1-problem-framing)
2. [System overview](#2-system-overview)
3. [Provider strategy — Azure vs OpenAI, V1 models, routing](#3-provider-strategy)
4. [Rich slide schema and text-amount densities](#4-rich-slide-schema-and-text-amount-densities)
5. [Workflow A — Generate a deck from a prompt](#5-workflow-a--generate-a-deck-from-a-prompt)
6. [Workflow B — Generate a deck from an uploaded file](#6-workflow-b--generate-a-deck-from-an-uploaded-file)
7. [Workflow C — Run a live voice presentation](#7-workflow-c--run-a-live-voice-presentation)
8. [The five function tools](#8-the-five-function-tools)
9. [The agent cursor — how the AI "points" at the slide](#9-the-agent-cursor)
10. [The 16:9 canvas and auto-fit scaling](#10-the-169-canvas-and-auto-fit-scaling)
11. [Audio pipeline (capture, playback, interruption)](#11-audio-pipeline)
12. [Transcript ordering and auto-scroll](#12-transcript-ordering-and-auto-scroll)
13. [State machine and store shape](#13-state-machine-and-store-shape)
14. [Manual-nav sync protocol](#14-manual-nav-sync-protocol)
15. [PDF export](#15-pdf-export)
16. [Voice-controlled actions (download, end)](#16-voice-controlled-actions)
17. [Event catalog (every WebSocket message)](#17-event-catalog)
18. [Error handling and observability](#18-error-handling-and-observability)
19. [Security model](#19-security-model)
20. [Trade-offs and production migration paths](#20-trade-offs-and-production-migration-paths)
21. [Glossary](#21-glossary)

---

## 1. Problem framing

The brief asks for an AI voice application that presents 5-6 slides, navigates automatically in response to user questions, and can be interrupted. To this I added five things that make it feel real rather than canned:

- **Author your own deck.** A static deck about HCI is a demo, not a product. Letting the presenter supply a prompt — *or* upload an existing slide — turns the prototype into something a working professional could actually put in front of a client the same afternoon.
- **A density dial.** The same topic has very different information needs depending on audience. A Text Amount selector (Brief / Medium / Detailed / Extensive) controls bullet count, detail length, and whether stats/takeaways/steps are included.
- **Make the agent visible on the slide.** Voice alone is a thin channel. If the agent says "the second bullet" there is no visual referent — the audience has to do the mapping. A virtual cursor the agent drives via a function call closes that gap.
- **Continuous delivery by default.** The agent walks the deck end-to-end like a keynote speaker. It only stops when interrupted or when the user wraps up.
- **Take something home.** The generated deck can be downloaded as a printable 16:9 PDF — either by clicking the download button or by asking the agent *"download this deck"*.

These additions shape every other decision below.

---

## 2. System overview

Three layers, with the middle layer doing all the work:

```
┌───────────────────────────────────────────────────────────┐
│                    Browser (React + Vite)                 │
│                                                           │
│  SetupScreen ───▶ PresentationView                        │
│    ├── 16:9 slide canvas (container queries)              │
│    │   └── AutoFitSlide    (scales content to fit)        │
│    │       └── SlideView   (title, bullets, stats, …)     │
│    ├── AgentCursor         (animated pointer)             │
│    ├── TranscriptPanel     (sticky-to-bottom scroll)      │
│    └── Controls + Download PDF button                     │
│                                                           │
│  Zustand store  ◀──▶  useRealtimeSession                  │
│                         └─ useAudioStream (PCM16 in/out)  │
└───────────────────┬───────────────────────────────────────┘
                    │  REST  (/api/decks/*)
                    │  WS    (/ws/{deck_id})
                    ▼
┌───────────────────────────────────────────────────────────┐
│                 FastAPI backend (Python)                  │
│                                                           │
│  REST endpoints                                           │
│    POST /api/decks/generate     chat completions (JSON)   │
│    POST /api/decks/from-file    extract + generate        │
│    GET  /api/decks/{id}         hydrate                   │
│    GET  /api/decks/{id}/pdf     reportlab A4 landscape    │
│                                                           │
│  WebSocket /ws/{deck_id}  ──▶  RealtimeRelay              │
│    • session.update  (deck embedded in instructions)      │
│    • forwards audio + events                              │
│    • intercepts response.function_call_arguments.done     │
│      ├── change_slide / go_to_slide ▶ slide_change        │
│      ├── point_at                   ▶ cursor_move         │
│      ├── download_deck              ▶ download_deck       │
│      └── end_session                ▶ end_session         │
│    • intercepts client.manual_slide ▶ narration hint      │
└─────┬───────────────────────────────────────┬─────────────┘
      │                                       │
      │  Chat (via OpenAI SDK + base_url)     │  wss:// realtime
      ▼                                       ▼
  ┌─────────────────────────────┐    Azure OpenAI Realtime (default)
  │ Azure OpenAI chat deployment │       or OpenAI Realtime (fallback)
  │  routed based on model name  │
  │  (Foundry vs V1 resource)    │
  └─────────────────────────────┘
```

**Keystone decision:** the backend is a **relay**, not a passthrough and not a full server. It lives on the hot path because four things have to happen in the middle:

1. The provider API key must never touch the browser (security).
2. `function_call` events from the model have to be translated into UI-native events so the frontend stays declarative.
3. Per-session state (current slide index, deck contents) has to live somewhere that both the model and the browser can reach.
4. Model-aware routing picks different Azure endpoints + keys based on which chat deployment is active.

Everything else downstream of these four requirements is derived.

---

## 3. Provider strategy

Two different model surfaces are involved, and they have different constraints:


| Surface              | Purpose                                 | Latency budget                  | Shape                                              |
| -------------------- | --------------------------------------- | ------------------------------- | -------------------------------------------------- |
| **Chat completions** | Generate deck JSON from a prompt / file | ~15-40 s (one-shot, background) | HTTP request/response, strict JSON schema          |
| **Realtime**         | Live voice narration + Q&A              | < 300 ms per turn               | Persistent WebSocket, bidirectional audio + events |


### Chat: Azure OpenAI via the OpenAI SDK, with model-aware routing

The chat surface uses a v1-compatibility pattern: point `OpenAI(base_url=…)` at the Azure endpoint with `/openai/v1/` appended, and treat the deployment name as the model name. Three practical benefits:

- **One SDK, one mental model.** The same OpenAI SDK works against both Azure and OpenAI; swapping is one env var.
- **GPT-5 / o-series compatibility.** `azure_client.token_kwargs()` swaps between `max_tokens` and `max_completion_tokens` automatically.
- **Graceful schema fallback.** Not every deployment supports `response_format={"type": "json_schema"}`. `slide_generator.py` tries strict schema first and falls back to `{"type": "json_object"}` with an explicit schema sketch.

#### The V1 model routing

`backend/config.py::AZURE_V1_MODELS` holds the set of chat deployment names that route to the realtime resource:

```python
AZURE_V1_MODELS = {"gpt-5.2-chat", "gpt-5.3-chat", "gpt-5.4-mini"}
```

When `AZURE_OPENAI_CHAT_DEPLOYMENT` matches, `azure_chat_config()` routes chat requests to:

- **Endpoint** — the realtime host with `/openai/v1/` appended (derived via `_resource_base` from `AZURE_OPENAI_REALTIME_ENDPOINT`).
- **Key** — `AZURE_OPENAI_REALTIME_API_KEY` if set, else falls back to `AZURE_OPENAI_API_KEY`.

Otherwise, chat uses the Foundry/classic chat resource via `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_API_KEY`, normalized with `_normalize_chat_endpoint` (appends `/openai/v1/` unless already present).

#### The `/openai/v1/` endpoint trick

The v1 **compatibility** path accepts OpenAI-SDK requests with the deployment name as `model` and rejects a manual `api-version` query parameter (it derives it from the URL). This avoids the usual "API version not supported" dance when Foundry and OpenAI APIs have diverged.

### Realtime: Azure if configured, OpenAI otherwise

`backend/config.py::realtime_config()` inspects the environment and returns a `RealtimeConfig` with four fields:

- `url` — either `wss://<resource>.cognitiveservices.azure.com/openai/realtime?api-version=…&deployment=…` or `wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview`. The helper `_build_azure_ws_url` preserves any query params already baked into the env var (you can paste the exact URL from the Azure portal).
- `api_key` — prefers `AZURE_OPENAI_REALTIME_API_KEY`, falls back to `AZURE_OPENAI_API_KEY`.
- `auth_header` — `**api-key`** for Azure, `**Authorization: Bearer**` for OpenAI.
- `provider` — `"azure"` or `"openai"`, used for logging.

The relay's only branch on provider is in `_headers()`. Everything else — session config, audio format, function-call event names — is identical because the Azure Realtime surface is protocol-compatible with OpenAI's.

The `websockets` library we pin (13.1) routes `websockets.connect()` to its legacy asyncio client, which expects `extra_headers=…` (not `additional_headers`, which is the newer `websockets.asyncio.client` API).

### Why not Whisper + chat + TTS?

Three sequential HTTP calls (STT → LLM → TTS) put turn latency at 2-4s. Can't interrupt canned TTS without brittle client-side VAD. Can't make function-call nav reactive. Realtime API is the only surface where sub-300ms + server VAD + function calling coexist on one connection.

---

## 4. Rich slide schema and text-amount densities

Slides carry more than a title + bullets list. The backend model emits a strict JSON object:

```ts
interface Slide {
  id: number;
  title: string;
  subtitle?: string;                      // muted one-liner framing
  bullets: { headline: string; detail: string }[];
  steps?: string[];                       // ordered process list
  stats?: { value: string; label: string }[];
  key_takeaway?: string;                  // synthesizing footer
  speaker_note: string;                   // agent-only narration context
}
```

Every optional field has a clear purpose:

- `**subtitle**` — one-line framing under the title. Reserved for slides where the topic needs sub-scoping ("how it works in practice," etc.).
- `**bullets[].detail**` — a 1-3 sentence body under each bullet headline. This is what makes slides actually informative. It typically includes a named example, a specific number, or a mechanism.
- `**steps[]**` — ordered, numbered process. Used when the slide describes a procedure (migration plan, algorithm, protocol). Rendered with numbered circles.
- `**stats[]**` — metric cards above the bullets (`value` + `label`). Used when numeric anchors strengthen the content.
- `**key_takeaway**` — one-sentence synthesis, rendered with a horizontal rule and `TAKEAWAY` label. Used on concluding slides.
- `**speaker_note**` — rich narration prompt for the agent. Embedded in the system prompt, never shown to the user.

### The `text_amount` dial

`SetupScreen` exposes four densities via chip selectors. These feed both the JSON schema's `minItems`/`maxItems` on `bullets` and the system prompt. Configured in `backend/slide_generator.py::_DENSITY`:


| Mode          | Bullets | Detail length | Speaker note  | Token budget | Stats/Takeaway                        | Feel                |
| ------------- | ------- | ------------- | ------------- | ------------ | ------------------------------------- | ------------------- |
| **Brief**     | 3-4     | ~18-30 words  | 45-70 words   | 3 500        | Takeaway only                         | Executive summary   |
| **Medium**    | 4-5     | ~30-50 words  | 70-110 words  | 5 000        | Both encouraged                       | Standard keynote    |
| **Detailed**  | 5-6     | ~45-75 words  | 110-170 words | 7 500        | Both, with steps when procedural      | Rich briefing       |
| **Extensive** | 5-7     | ~60-100 words | 170-260 words | 10 000       | Both mandatory, steps when applicable | Technical deep-dive |


The user-facing prompt is also hardened with a banned-phrase list ("generally," "various," "important to note") and a requirement for named examples / specific numbers in every detail. This is what moves the generator from "generic slide filler" to "presentation-ready content" — particularly at Detailed and above.

---

## 5. Workflow A — Generate a deck from a prompt

```
Browser                         Backend                         Azure OpenAI (chat)
  │                               │                                       │
  │  POST /api/decks/generate     │                                       │
  │  { prompt, count, text_amount}│                                       │
  ├──────────────────────────────▶│                                       │
  │                               │  resolve density → schema + prompt    │
  │                               │  chat.completions.create              │
  │                               │    response_format=json_schema        │
  │                               ├──────────────────────────────────────▶│
  │                               │  ◀──── { topic, slides: [...] }      │
  │                               │                                       │
  │                               │  coerce_slide(): clamp, normalize,    │
  │                               │     drop empty bullets                │
  │                               │  slide_store.create_deck()→ deck_id   │
  │  ◀──── Deck JSON ─────────────┤                                       │
  │                                                                       │
  │  store.setDeck(deck) ─▶ App renders PresentationView                  │
```

### Step-by-step

1. **Frontend validation.** `SetupScreen.onSubmit` requires `prompt.trim().length >= 3`. Slide count is clamped client-side (chip options 4-8), server re-clamps to 3-12.
2. **Density resolution.** The `text_amount` string becomes the key into `_DENSITY`, which provides the bullet range, detail word count, token budget, and free-form density description appended to the system prompt.
3. **Schema enforcement.** `response_format={"type": "json_schema", ...}` with `strict: true` is tried first. The schema declares `minItems`/`maxItems` on bullets based on density so the model physically cannot return too few.
4. **Graceful fallback.** On `TypeError` (Azure deployment rejects json_schema), retries with `{"type": "json_object"}` plus an inline schema sketch.
5. **Post-processing** in `_coerce_slide`:
  - Headline clamped to 140 chars, detail to 600, takeaway to 280.
  - Bullets with blank headlines dropped.
  - Optional fields only set when non-empty.
  - Stats capped at 4, steps at 8, bullets at 7.
6. **Persistence.** `slide_store.create_deck(topic, text_amount, slides)` mints a 12-hex `deck_id` and stores in a locked `dict`. Swap-in for Redis/Postgres.

### Why embed the deck in the system prompt (later, in workflow C)?

Six to 12 slides at ~150 tokens each sits well under 2 kT. Embedding in `instructions` at `session.update` time means:

- No retrieval step at turn-time; navigation-by-topic is a single model hop.
- The model can cross-reference slides freely ("this connects to slide 5") without any tool call.
- `go_to_slide(index)` becomes trivially correct: the model already knows what lives at each index.

For decks of ~30+ slides this breaks down; the migration is a `get_slide(index)` tool + vector store over bullets.

---

## 6. Workflow B — Generate a deck from an uploaded file

```
Browser                         Backend                         Azure OpenAI
  │                               │                                       │
  │  POST /api/decks/from-file    │                                       │
  │  multipart: file, count,      │                                       │
  │             text_amount,      │                                       │
  │             extra_prompt      │                                       │
  ├──────────────────────────────▶│                                       │
  │                               │  file_analyzer.extract_text()         │
  │                               │    ├── .pdf  → pypdf                  │
  │                               │    ├── .pptx → python-pptx            │
  │                               │    ├── image → chat (vision) ─────────▶│
  │                               │    └── text  → utf-8 decode           │
  │                               │                                       │
  │                               │  (extra_prompt + "\n---\n" + text)    │
  │                               │  generate_deck(..., kind='source')    │
  │  ◀──── Deck JSON ─────────────┤                                       │
```

Supported formats, per-format path, and rationale unchanged from v1. The one density-aware addition: `text_amount` flows through the form field and controls the final generation stage identically to Workflow A.

The two-stage pipeline (extract → generate) is deliberate — the failure modes are different. Extraction fails with HTTP 415 (unsupported type), 422 (empty extraction), or 502 (library bug). Generation fails with 502 (schema/quota). Keeping them separate makes failures diagnosable.

Cap of 20 000 chars on extracted text prevents unbounded spend on very long PDFs. The honest-scope migration path is map-reduce chunking.

---

## 7. Workflow C — Run a live voice presentation

Four sub-flows:

1. **Session open** — mic on, WS open, session configured, first narration arrives.
2. **Continuous narration** — agent walks the deck end-to-end, calling `change_slide('next')` between slides.
3. **AI-driven navigation** — user asks about a topic on another slide; model jumps there.
4. **Interruption** — user speaks mid-narration; playback flushed; user's question handled.
5. **Voice-controlled actions** — user says "download this" or "end chat"; agent invokes the matching tool.
6. **Manual navigation** — user presses `→`; backend stays in sync.

### 7.1 Session open

```
User clicks mic
     │
     ▼
useRealtimeSession.start()
  ├─ setAgentStatus('connecting')
  ├─ useAudioStream.startRecording()
  ├─ new WebSocket(ws://…/ws/{deck_id})
  │    └─ .onopen:
  │         ├─ setConnected(true)
  │         ├─ setAgentStatus('listening')
  │         └─ send: kickoff conversation.item.create + response.create
  │              "The presentation is starting now. Begin delivering the
  │               full deck end-to-end per your instructions: briefly
  │               introduce yourself, then walk through every slide in order,
  │               calling point_at as you go and change_slide('next') after
  │               finishing each slide. Do not pause between slides unless
  │               I interrupt you."
  │
Backend: /ws/{deck_id}
  ├─ slide_store.get_deck(deck_id)  (404 if unknown)
  ├─ RealtimeRelay(deck, realtime_config()).relay(ws):
  │    ├─ websockets.connect(provider_url, extra_headers=…)
  │    ├─ send session.update:
  │    │    { voice, input/output_audio_format: pcm16,
  │    │      input_audio_transcription: { model: 'gpt-4o-mini-transcribe' },
  │    │      turn_detection: server_vad,
  │    │      tools: [change_slide, go_to_slide, point_at,
  │    │              download_deck, end_session],
  │    │      instructions: _BASE_INSTRUCTIONS + _deck_context(slides) }
  │    ├─ spawn browser→provider task
  │    └─ spawn provider→browser task
```

Three invariants:

- **Mic starts before the WS opens.** `getUserMedia` permission prompt takes hundreds of ms; starting first means by the time audio starts streaming back, the user can interrupt immediately.
- **Kickoff uses an explicit continuous-flow instruction.** If it said "narrate slide 1" the agent would stop after. Saying "Do not pause between slides unless I interrupt you" gets the end-to-end walk.
- `**session.update` goes before the pumps bridge.** If you bridge first, the provider sends audio before it has been told the voice/format/tools.

### 7.2 Continuous narration

The `_BASE_INSTRUCTIONS` in `session_config.py` specify a **flow**, not a turn structure:

> 1. When the session begins, `point_at('title')` and briefly introduce yourself and the topic in one sentence, then narrate slide 0.
> 2. For each slide, 4-7 short conversational sentences total. Expand each bullet briefly with an example, connection, or implication. Never read bullets verbatim.
> 3. Call `point_at('title')` on introduction, then `point_at('bullet_N')` for each bullet.
> 4. When finished narrating a slide, immediately `point_at('next_button')` then `change_slide('next')`. Keep flowing.
> 5. On the final slide, wrap up with one synthesizing sentence and invite questions. Do NOT call `change_slide` after the final slide.
> 6. Interruption handling overrides the default flow — `go_to_slide` if the question is off-slide, answer, then resume.

This is the difference between "narrate slide then stop" (the old behavior) and "walk the deck continuously" (the current behavior). It's achieved entirely through the prompt — the relay logic didn't change.

### 7.3 AI-driven navigation

User: *"Actually, tell me about touch interfaces."* Slide 1 is currently visible; the deck has "Touch & Mobile" on slide 3.

```
Browser                    Relay                  Provider
   │                         │                        │
   │ PCM16 audio frames ────▶│ base64 → append ──────▶│
   │                         │ ◀ speech_started ──────│
   │ stopPlayback()          │                        │
   │ beginUserTurn()         │                        │
   │                         │ ◀ speech_stopped ──────│
   │                         │ ◀ response.created ────│
   │                         │ ◀ point_at('next')     │
   │ ◀ cursor_move ──────────│                        │
   │                         │ function_call_output ─▶│
   │                         │ response.create ──────▶│
   │                         │ ◀ go_to_slide(2)       │
   │                         │ slide_change           │
   │ ◀ slide_change ─────────│                        │
   │                         │ function_call_output ─▶│
   │                         │ response.create ──────▶│
   │                         │ ◀ audio.delta (×N)     │
   │ ◀ audio deltas ─────────│                        │
   │                         │ ◀ response.done ───────│
```

The `point_at('next_button')` → `change_slide('next')` / `go_to_slide(N)` sequence is what makes the advance feel intentional on-screen. Without the first `point_at`, the slide would just jump.

### 7.4 Interruption

```
AI is speaking.
audioStream has ~1s of PCM16 scheduled on AudioBufferSourceNodes.
User begins speaking.
Provider's server VAD emits input_audio_buffer.speech_started.
Relay forwards verbatim.
Browser: case 'input_audio_buffer.speech_started':
  audio.stopPlayback()    # iterate activeSourcesRef, .stop() each, reset nextPlayTime
  beginUserTurn()         # insert empty User entry NOW so order is locked in
  pendingEndRef = false   # cancel any pending session close
  setAgentStatus('listening')
```

The agent's own response generation truncates on speech_started (the provider handles that), and the client cancels its scheduled buffers. Time-to-silence is ~30 ms.

### 7.5 Manual navigation

See §14.

---

## 8. The five function tools

Defined in `backend/slide_functions.py::functions_schema(max_bullets)` and bound in every session.


| Tool            | Signature          | Purpose                                                 |
| --------------- | ------------------ | ------------------------------------------------------- |
| `change_slide`  | `direction: 'next' | 'prev'`                                                 |
| `go_to_slide`   | `index: integer`   | Direct jump by 0-based index.                           |
| `point_at`      | `target: enum`     | Move agent cursor (§9).                                 |
| `download_deck` | `()`               | Trigger a browser-side PDF download (§16).              |
| `end_session`   | `()`               | End the presentation gracefully after a farewell (§16). |


### Why these five?

- `**change_slide` vs `go_to_slide**` — separate so the model can pick "step one" vs "jump to N" without arithmetic. Makes the prompt simpler.
- `**point_at**` — schema-constrained enum (`title`, `bullet_0..bullet_{N-1}`, `next_button`, `prev_button`) per-deck. Model can't hallucinate a target the frontend would drop. Out-of-range targets (current slide has 3 bullets, model calls `bullet_4`) are harmless — the frontend `querySelector` returns null and cursor stays put.
- `**download_deck` / `end_session**` — parameterless. The model's job is understanding when the user wants them. The browser handles the actual effect.

### Why not parse narration instead of `point_at`?

Language is ambiguous ("the second bullet" → which? "as I mentioned earlier" → nothing). Transcript arrives *after* audio so would always lag. The model already has the attention signal — forcing it to emit that as a function call is cheaper and more accurate.

---

## 9. The agent cursor

End-to-end trace from tool call to pixel:

```
Provider
  └─ response.function_call_arguments.done
        name: 'point_at', arguments: '{"target":"bullet_1"}'

Relay (backend/realtime_relay.py::_handle_function_call)
  └─ handle_function_call(name, arguments, navigator)
        returns { browser_event: {type:'cursor_move', target:'bullet_1'},
                  tool_output:  {success:true, target:'bullet_1'} }
  └─ browser_ws.send_text(cursor_move event)
  └─ provider.send(function_call_output + response.create)

Browser (useRealtimeSession)
  └─ case 'cursor_move': setCursorTarget(event.target as CursorTarget)

AgentCursor
  └─ useLayoutEffect (deps: [target, containerRef])
        const el = container.querySelector(`[data-cursor-target="bullet_1"]`)
        compute position relative to container
        setPosition({ x, y })
  └─ useEffect triggers click animation if target is next_button/prev_button
  └─ render absolutely-positioned pointer with
        transform: translate3d(x-6, y-6, 0)
        transition: 'transform 480ms cubic-bezier(0.22, 1, 0.36, 1)'
```

### DOM contract

Every targetable element has a `data-cursor-target="…"` attribute, hand-placed in `SlideView.tsx` (`title`, `bullet_0..N`) and `Controls.tsx` (`prev_button`, `next_button`). `AgentCursor` doesn't know what these elements look like; it just queries by attribute.

### Why DOM targets instead of computed coordinates?

- **Responsive.** `getBoundingClientRect` at effect-run time → correct at any viewport. `ResizeObserver` on the container re-measures on resize.
- **Layout-robust.** Bullet N becomes multi-line, wraps differently on mobile — cursor still lands on it.
- **Works through the scale transform.** The cursor lives outside the auto-fit-scaled subtree (sibling of `AutoFitSlide`), so its own size stays constant. It queries elements inside the scaled subtree; their `getBoundingClientRect` returns visually-scaled positions. The difference (cursor container rect vs target rect) is always in viewport pixels relative to `slideRef` — correct regardless of scale.

### Timing

- **480 ms ease-out-quart** on movement — longer than a snap, shorter than a stroll. Most motion in the first half so it "arrives early," matching the vocal cadence.
- **240 ms click animation** (`scale 1 → 0.82 → 1`) when target is a nav button. Fires before the actual slide change, which lands on the next tool call a few hundred ms later.
- **Opacity 0 when not connected** — the cursor represents agent presence, not a decoration.

---

## 10. The 16:9 canvas and auto-fit scaling

Slides render at a fixed 16:9 aspect ratio, like PowerPoint / Keynote. The canvas dimensions are derived via CSS container queries — no JavaScript measurement required.

### Sizing

```tsx
<section style={{ containerType: "size" }}>          {/* establishes container */}
  <div style={{
    aspectRatio: "16 / 9",
    width: "min(100cqw, 100cqh * 16 / 9)",            /* pick the limiting dim */
    maxWidth: "100%",
    maxHeight: "100%",
  }}>
    <AutoFitSlide>
      <SlideView ... />
    </AutoFitSlide>
    <AgentCursor ... />
  </div>
</section>
```

`100cqw` = full container width; `100cqh * 16/9` = height-derived equivalent. `min(...)` picks the smaller so the 16:9 card always fits without overflow and always respects aspect ratio. Works in Chrome 105+, Firefox 110+, Safari 16+.

### Auto-fit scaling

`AutoFitSlide` (`frontend/src/components/AutoFitSlide.tsx`) scales the inner content uniformly to fit within the 16:9 canvas:

```tsx
useLayoutEffect(() => {
  const outer = outerRef.current;
  const content = contentRef.current;
  const fit = () => {
    const s = Math.max(
      minScale,
      Math.min(1,
        outer.clientHeight / content.offsetHeight,
        outer.clientWidth  / content.offsetWidth
      )
    );
    setScale(prev => Math.abs(prev - s) > 0.005 ? s : prev);
  };
  fit();
  const ro = new ResizeObserver(fit);
  ro.observe(outer);
  ro.observe(content);
  return () => ro.disconnect();
}, [minScale]);
```

Key trick: `offsetHeight` / `offsetWidth` are **layout** dimensions, unaffected by CSS transforms. So reading them in a layout effect after applying a `transform: scale(...)` doesn't create a measure → scale → re-measure loop. `ResizeObserver` reports content/border-box sizes (also unaffected by transform) — safe to observe both refs.

The `Math.abs(prev - s) > 0.005` guard makes it doubly safe and prevents thrashing from sub-pixel float drift.

`minScale: 0.45` prevents text from shrinking below legibility. If content at Extensive density + short viewport can't fit even at 0.45, the content clips at the container bottom — but this is rare; typical presentations stay in the 0.7-1.0 range.

### Content layout inside the canvas

Because 16:9 is landscape, bullets flow in a **2-column grid** on medium+ viewports (`md:grid-cols-2`), matching how a designer would fill horizontal space:

- `grid-cols-1 md:grid-cols-2` on bullets (via `SlideView`)
- `md:grid-cols-[repeat(auto-fit,minmax(180px,1fr))]` on stats
- `grid-cols-1 md:grid-cols-2` on process steps

The PDF export matches this rule (§15).

---

## 11. Audio pipeline

### Capture

```
getUserMedia({ audio: { sampleRate: 24000, channelCount: 1,
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true } })
  │
  ▼
AudioContext({ sampleRate: 24000 })
  ├─ AnalyserNode (fftSize: 256)
  └─ ScriptProcessorNode (bufferSize: 4096, mono)
       onaudioprocess: float32 → clamp → PCM16 → WS binary frame
```

Three specific choices:

- **24 kHz mono PCM16.** Realtime API spec. Explicit sample rate on `AudioContext` means no resampling client-side.
- **Browser AEC/NS/AGC enabled.** Essential — without echo cancellation, the mic picks up playback, VAD thinks user is interrupting, agent cuts itself off, loop becomes unusable.
- `**ScriptProcessorNode`** over `AudioWorklet`. Deprecated but works on localhost without worker files or HTTPS. Production migration is to Worklet.

### Playback

Base64 PCM16 → Float32 → `AudioBuffer` → scheduled `AudioBufferSourceNode` with continuous `nextPlayTime` tracking. Active sources go into `activeSourcesRef` for cancellation on interrupt.

### Transcription model

`session.update` specifies `input_audio_transcription.model = "gpt-4o-mini-transcribe"` — dramatically more accurate than the legacy `whisper-1`. `gpt-4o-mini-transcribe` handles disfluencies, short utterances, and domain jargon vastly better. The user's API version (`2026-02-23`) supports it natively.

---

## 12. Transcript ordering and auto-scroll

Two subtle UX problems solved by dedicated actions in the store.

### Problem: ordering

Whisper/transcribe emits user-transcription events *after* the agent has already started replying. The naïve "add User entry when transcription completes" approach puts user text **after** the agent's reply to it — confusing.

### Fix: begin/complete pattern

Two store actions:

- `**beginUserTurn()*`* — on `input_audio_buffer.speech_started`, insert an empty `"User"` entry NOW. Idempotent (won't create duplicates if VAD flaps).
- `**completeUserTurn(text)**` — on `…transcription.completed`, find the most recent empty user entry and fill it in. On `…failed`, drop it.

Order becomes:

```
USER:   [placeholder] ← inserted on speech_started
AGENT:  [reply streams while transcription resolves]
USER:   [transcribed text fills in later]
AGENT:  [continues]
```

`TranscriptPanel` renders empty user entries as three animated dots with "Listening" — the user never sees an empty bubble, and it's visually obvious the transcription is in flight.

### Auto-scroll

The old effect depended on `entries.length` so streaming AI deltas (which only change the last entry's text) didn't trigger scroll. Fixed:

- Effect depends on `entries` — the store creates a new array reference on every `appendTranscript` delta, so it fires on every text change.
- Direct `scrollTop = scrollHeight` — reliable at high frequency.
- **Sticky-to-bottom via ref** (no re-renders): if user scrolls up > 80 px from the bottom, auto-scroll pauses. Scroll back down and it resumes.

---

## 13. State machine and store shape

```ts
interface State {
  deck: Deck | null;
  activeSlide: number;
  agentStatus: AgentStatus;      // 'idle'|'connecting'|'listening'|'processing'|'speaking'
  cursorTarget: CursorTarget;    // 'title'|`bullet_${N}`|'next_button'|'prev_button'
  transcript: TranscriptEntry[];
  isConnected: boolean;
  isMicActive: boolean;
  error: string | null;
}
```

### Agent-status transitions

```
                 mic click
   idle ───────────────────────▶ connecting
                                    │
                   WS.onopen        │
   idle ◀──────── WS.onclose        │
                                    ▼
     ┌────────────────────────── listening ◀──────────────┐
     │                              │                      │
     │                   VAD speech_started               │
     │                              │                      │
     │                              ▼                      │
     │                         processing                  │
     │                              │                      │
     │                   response.audio.delta              │
     │                              │                      │
     │                              ▼                      │
     │                          speaking ──────────────────┤
     │                              │                      │
     │                   response.done                      │
     │                              │                      │
     └──────────────────────────────┘                      │
                                                           │
                    VAD speech_started (interrupt)         │
                  ─────────────────────────────────────────┘
```

---

## 14. Manual-nav sync protocol

The problem: user clicks "next" in the browser → backend's `SlideNavigator` still thinks the current slide is N. Next AI-driven nav is off-by-one.

The solution: a tiny application-level protocol on the existing WS.

```json
{ "type": "client.manual_slide", "index": 3 }
```

Any message whose `type` starts with `client.` is a control event, not forwarded to the provider. The relay:

1. Updates the navigator state first.
2. Sends `slide_change` to the browser (same shape as AI-driven nav — UI doesn't care which produced it).
3. Injects a narration hint `conversation.item.create` to the provider: *"The user manually navigated to slide X. Narrate this slide, then continue the presentation flow per your instructions."* — preserves continuous flow after manual nav.
4. `response.create` triggers narration.

---

## 15. PDF export

`GET /api/decks/{deck_id}/pdf` streams a `Content-Disposition: attachment` PDF with filename derived from the topic. Generation is synchronous and pure-Python via `reportlab` (`backend/pdf_export.py`).

### Layout

- **A4 landscape** (842 × 595 pt) — matches the 16:9-ish slide aspect.
- **Header** — `SLIDE 1 OF N` tracked caps on the left, progress bar on the right.
- **Title** (Helvetica-Bold 26) and optional subtitle (Helvetica 12.5).
- **Stats row** — up to 4 metric cards, auto-sized to fill `inner_w`.
- **Bullets** — **single column for ≤3, 2-column snake-fill for 4+**, matching the web UI's landscape layout. Each column is `(inner_w - 28) / 2 ≈ 353pt` wide; wrap width per column is `col_w - 23 = 330pt`. Row heights are measured per-bullet so left/right stay aligned.
- **Steps** — numbered circles with step text, 2-column-aware.
- **Takeaway** — horizontal rule + `TAKEAWAY` label + bold sentence.
- **Footer** — `VoiceSlide` on left, `n / total` on right.

### Typography

Helvetica throughout (no external font deps). Headlines 10.5 pt, details 9 pt with 11.5 pt leading — tight enough that Detailed / Extensive decks fit. When remaining vertical space is short, `_draw_bullets` automatically truncates detail lines to respect the bottom margin rather than overflowing.

### Character cleaning

`_clean()` normalizes Unicode to the subset Helvetica's default WinAnsi encoding supports:

- Smart quotes → straight quotes
- En/em dashes → hyphens
- Accented chars (`ū`, `é`, `ö`) → ASCII via NFKD decomposition + combining-mark strip
- Any char outside Latin-1 supplement becomes `?`

Result: no "tombstone" glyphs in the rendered PDF, regardless of what the model generated.

### Trigger paths

Two entry points:

- **Download button** (`PresentationView` header) — a standard `<a href={deckPdfUrl(deck.id)} download>` anchor.
- **Voice command** — see §16.

---

## 16. Voice-controlled actions

Two parameterless tools in `session.update.tools` handle actions the model can invoke based on natural language:

### `download_deck()`

Triggered by *"download this,"* *"save the deck,"* *"can I get a copy?"* The model's prompt guidance: *"Acknowledge in one short sentence, then call the tool."*

Relay emits `{ type: "download_deck" }` to the browser. The client handler constructs a transient `<a href={deckPdfUrl(deckId)} download>` and clicks it programmatically:

```ts
case "download_deck": {
  const a = document.createElement("a");
  a.href = deckPdfUrl(deckId);
  a.target = "_blank";
  a.download = "";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  break;
}
```

Download happens during the agent's acknowledgement audio — no perceptible delay.

### `end_session()`

Triggered by *"end chat,"* *"we're done,"* *"that's all,"* *"goodbye."* The prompt guidance: *"Say a brief, warm farewell sentence FIRST, then call the tool as the last action — the audio will finish before the connection closes."*

This requires a graceful-close pattern: cutting the WS immediately would clip the agent's farewell audio. The client sets a ref flag instead:

```ts
case "end_session": {
  pendingEndRef.current = true;     // mark pending
  break;
}

case "response.done": {
  setAgentStatus("listening");
  if (pendingEndRef.current) {
    pendingEndRef.current = false;
    window.setTimeout(() => stop(), 400);   // let farewell audio finish
  }
  break;
}
```

And for resilience:

```ts
case "input_audio_buffer.speech_started": {
  ...
  pendingEndRef.current = false;    // user interrupted — cancel the close
}
```

So a user who says *"goodbye"* then immediately adds *"wait, one more question"* isn't cut off.

---

## 17. Event catalog

### Browser → Backend (`/ws/{deck_id}`)


| Frame type | Payload                                             | Meaning                                                                                          |
| ---------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Binary     | `ArrayBuffer` of PCM16 (LE, 24 kHz, mono)           | Mic audio chunk, ~85 ms at 4096 samples. Forwarded as base64 `input_audio_buffer.append`.        |
| Text       | `{ "type": "client.manual_slide", "index": N }`     | Manual nav sync. Consumed by relay, not forwarded.                                               |
| Text       | Any other JSON (`type` not starting with `client.`) | Forwarded verbatim to provider. Used for kickoff `conversation.item.create` + `response.create`. |


### Provider → Backend (relayed to browser unless intercepted)


| `type`                                                  | Handled         | Frontend reaction                                                                                  |
| ------------------------------------------------------- | --------------- | -------------------------------------------------------------------------------------------------- |
| `session.created`, `session.updated`                    | forwarded       | ignored                                                                                            |
| `input_audio_buffer.speech_started`                     | forwarded       | `audio.stopPlayback()`, `setAgentStatus('listening')`, `**beginUserTurn()*`*, cancel pending close |
| `input_audio_buffer.speech_stopped`                     | forwarded       | `setAgentStatus('processing')`                                                                     |
| `conversation.item.input_audio_transcription.completed` | forwarded       | `**completeUserTurn(transcript)**`                                                                 |
| `conversation.item.input_audio_transcription.failed`    | forwarded       | `**completeUserTurn("")**` (drops placeholder)                                                     |
| `response.created`                                      | forwarded       | `setAgentStatus('processing')`                                                                     |
| `response.audio.delta`                                  | forwarded       | `audio.playChunk(delta)`, `setAgentStatus('speaking')`                                             |
| `response.audio.done` / `response.done`                 | forwarded       | `setAgentStatus('listening')`; if `pendingEndRef`, schedule `stop()` after 400 ms                  |
| `response.audio_transcript.delta`                       | forwarded       | `appendTranscript('AI', delta)`                                                                    |
| `**response.function_call_arguments.done**`             | **intercepted** | See below.                                                                                         |
| `error`                                                 | forwarded       | `setError(event.error.message)`                                                                    |


### Synthesized by relay → Browser


| `type`          | Payload                | Source                                               | Frontend reaction                                                     |
| --------------- | ---------------------- | ---------------------------------------------------- | --------------------------------------------------------------------- |
| `slide_change`  | `{ new_index, slide }` | `change_slide`, `go_to_slide`, `client.manual_slide` | `setActiveSlide(new_index)` (also resets `cursorTarget` to `'title'`) |
| `cursor_move`   | `{ target }`           | `point_at`                                           | `setCursorTarget(target)`                                             |
| `download_deck` | `{}`                   | `download_deck`                                      | Trigger anchor-click download                                         |
| `end_session`   | `{}`                   | `end_session`                                        | Set `pendingEndRef = true`                                            |


---

## 18. Error handling and observability

Same as v1, with two additions:

- **Transcription failure** — `…failed` events drop the pending User placeholder so the UI doesn't show a stuck "Listening…" forever.
- **PDF export failure** — `/pdf` endpoint returns 502 with exception message. Download button shows a browser-level error; voice `download_deck` tool output carries `success: false` back to the model.

---

## 19. Security model

Unchanged from v1. API key isolation, CORS scoping, signed-token migration path for WS, input validation, MAX_CHARS cap on uploads. The new V1-model routing uses whichever key is appropriate (`AZURE_OPENAI_REALTIME_API_KEY` → realtime resource → GPT-5.x chat); both keys remain server-side.

---

## 20. Trade-offs and production migration paths

Summary table of the prototype-vs-production choices. For the full engineering RFC — priority tiers, effort estimates per item, concrete implementation approaches, a 14-day migration sequence, and per-user cost estimates — see [**`PRODUCTION_MIGRATION.md`**](PRODUCTION_MIGRATION.md).

| Trade-off made                          | Why now                                                       | Production path                                                                        |
| --------------------------------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `ScriptProcessorNode` for audio capture | Works on localhost without worker file or HTTPS               | `AudioWorklet` off the main thread                                                     |
| In-memory deck store                    | Zero infra                                                    | Redis session state, Postgres for user-owned decks                                     |
| Deck embedded in system prompt          | Decks are small (≤12 slides × ~150 tokens), no retrieval step | Tool-callable `get_slide(index)` + vector search for long decks                        |
| HTTP Basic Auth at nginx                | Soft gate for the demo                                        | Real user accounts + OAuth + JWT + one-time signed WS tickets                          |
| No auth on `/ws/{deck_id}`              | Unguessable 96-bit deck IDs suffice locally                   | Signed short-lived tokens on `/api/decks/generate`, verified on upgrade                |
| PDF length cap at 20 000 chars          | Predictable spend                                             | Map-reduce chunking for long documents                                                 |
| Helvetica-only PDF fonts                | Zero external font deps                                       | Register Inter TTF for stricter visual parity with UI                                  |
| Single-presenter process                | Prototype doesn't need multi-tenancy                          | Per-WS session IDs, rate limits, horizontal scaling                                    |
| No slide thumbnails / rail              | Keeps the demo focused on the single slide                    | Left rail thumbnails; agent cursor could retarget to them                              |
| No reconnect in `useRealtimeSession`    | Session-scoped                                                | Exponential backoff with state replay, only when the session wasn't explicitly stopped |
| Continuous flow baked into prompt       | Simple, reliable                                              | Optional "stop after each slide" mode toggled via session param                        |
| Deck voice fixed per env                | One voice is enough to evaluate                               | Per-deck voice selection via `session.update`                                          |
| Synchronous deck generation             | 15-40 s on the request path is acceptable for a demo          | Background jobs (ARQ / Celery) + streaming result via SSE or WS                        |
| No rate limiting                        | Single-user demo                                              | Per-user quotas + token bucket (critical — realtime spend is unbounded)                |
| Unstructured logs via `docker logs`     | Easy to tail                                                  | JSON logs + Prometheus + OpenTelemetry + Sentry                                        |
| No tests                                | Prototype velocity                                            | pytest (backend) + Vitest (frontend) + Playwright (E2E), CI gating                     |


---

## 21. Glossary

- **Deck** — the generated presentation: topic string, `text_amount`, ordered `slides`. Immutable for the session.
- **Slide** — `{ id, title, subtitle?, bullets, steps?, stats?, key_takeaway?, speaker_note }`. `speaker_note` is embedded in the model prompt as narration context; never rendered.
- **Bullet** — `{ headline, detail }`. Headline is punchy (~4-10 words, rendered bold); detail is a 1-3 sentence prose body with a specific example / number / mechanism.
- **Text amount** — `brief | medium | detailed | extensive`. Controls bullet count, detail length, token budget, and whether stats/takeaways/steps appear.
- **Relay** — the FastAPI process. Proxies audio both directions, injects session config, intercepts function calls, handles `client.*` control events.
- **VAD** — Voice Activity Detection, server-side via `turn_detection: server_vad`. Threshold 0.5, silence 700 ms.
- **Turn** — one exchange. `server_vad` decides when a turn ends.
- **Function call** — the model's side-effect mechanism. Here, one of five tools; arguments validated against JSON schema.
- **Tool output** — server's response to a function call, sent back to the model as a `conversation.item.create` of type `function_call_output`. Required so the model can see its action succeeded.
- `**data-cursor-target`** — DOM attribute anchoring the agent cursor. Present on slide title, each bullet, and the two nav buttons.
- `**client.*` event** — browser→backend control messages not forwarded to the provider.
- **V1 models** — chat deployments (`gpt-5.2-chat`, `gpt-5.3-chat`, `gpt-5.4-mini`) that live on the Azure realtime resource instead of the Foundry project. Route selection in `config.py::AZURE_V1_MODELS`.
- `**/openai/v1/`** — Azure's v1 compatibility path that accepts OpenAI-SDK requests with the deployment name as `model`; rejects a manual `api-version` query parameter.
- **AutoFitSlide** — component that uniformly scales its content to fit a 16:9 container, using a `ResizeObserver` and a scale-guard to avoid feedback loops.
- **Sticky-to-bottom** — transcript scroll pattern that follows new messages until the user scrolls up; pauses auto-scroll in that case.
- **PCM16** — 16-bit signed LE linear PCM. Wire format for input/output audio.
- `**AudioBufferSourceNode`** — Web Audio API node that plays a one-shot buffer at a scheduled start time. Queued end-to-end for continuous playback; cancelled on interruption.

