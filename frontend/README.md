# VoiceSlide — frontend

React 18 + Vite + TypeScript + Zustand + Tailwind + Lucide.

> For the full architecture (event catalog, audio pipeline, agent-cursor mechanism, auto-fit scaling, transcript ordering, state machine), read [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

## Run

```bash
npm install
cp .env.example .env     # optional; defaults to localhost:8000
npm run dev
```

Open `http://localhost:5173`.

## Structure

- `src/App.tsx` — switches between `SetupScreen` and `PresentationView` based on deck presence.
- `src/components/SetupScreen.tsx` — prompt/upload tabs, slide-count chips, **Text Amount** chips, example-prompts picker with sticky scroll.
- `src/components/PresentationView.tsx` — 16:9 canvas layout, keyboard nav, realtime session wiring, PDF download button in header.
- `src/components/AutoFitSlide.tsx` — scale-to-fit wrapper. `ResizeObserver` + `offsetHeight` trick (layout metric unaffected by transforms, no feedback loop).
- `src/components/SlideView.tsx` — rich-content renderer: title, optional subtitle, optional stats row, 2-col bullets on landscape, optional numbered steps, optional takeaway. Bullets tagged with `data-cursor-target="bullet_N"`.
- `src/components/AgentCursor.tsx` — DOM-target-driven animated pointer. 480 ms ease-out-quart movement; 240 ms click animation on nav buttons; invisible when disconnected.
- `src/components/Controls.tsx` — mic toggle, prev/next (with cursor targets), status.
- `src/components/TranscriptPanel.tsx` — sticky-to-bottom scroll, "Listening…" placeholder for pending user turns.
- `src/hooks/useAudioStream.ts` — PCM16 capture (24 kHz mono) + scheduled playback with `activeSourcesRef` for interrupt cancellation.
- `src/hooks/useRealtimeSession.ts` — WS lifecycle, event router, continuous-flow kickoff, download handler, graceful end-session via `pendingEndRef`.
- `src/store/usePresentationStore.ts` — Zustand: deck, active slide, agent status, cursor target, transcript (with `beginUserTurn` / `completeUserTurn` for ordering), connection/mic flags, error.
- `src/lib/api.ts` — REST client (`generateDeck`, `uploadFileForDeck`, `deckPdfUrl`, `wsUrlForDeck`).

## Keyboard

- `←` / `→` — previous / next slide (respects input focus).

## Voice commands (agent-interpreted)

- "Next slide" / "go back" → `change_slide`.
- "Tell me about X" → `go_to_slide(index)` + narration.
- "Download this deck" / "save the PDF" → `download_deck` tool → PDF downloads.
- "End chat" / "we're done" / "goodbye" → brief farewell → `end_session` → session closes after the audio finishes.

## Audio pipeline

**Capture**: `getUserMedia` → `AudioContext (24 kHz)` → `ScriptProcessorNode` → PCM16 → WS binary frames.
**Playback**: WS base64 PCM16 → `Float32Array` → `AudioBuffer` → scheduled `AudioBufferSourceNode` chain; `activeSourcesRef` tracks live sources so interruption (`input_audio_buffer.speech_started`) can cancel all pending buffers.

## Layout

- 16:9 canvas sizing via CSS container queries: `width: min(100cqw, 100cqh * 16/9)` + `aspectRatio: 16/9` — fills available space in both axes while preserving ratio.
- `AutoFitSlide` uniformly scales the inner content to fit the canvas (min scale 0.45).
- Bullets use `grid-cols-1 md:grid-cols-2` to match the landscape card's wider aspect.
