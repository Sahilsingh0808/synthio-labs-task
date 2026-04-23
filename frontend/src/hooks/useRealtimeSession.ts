import { useCallback, useEffect, useMemo, useRef } from "react";
import { deckPdfUrl, wsUrlForDeck } from "../lib/api";
import { usePresentationStore } from "../store/usePresentationStore";
import { useAudioStream } from "./useAudioStream";
import type { CursorTarget } from "../types";

export interface RealtimeSessionHandle {
  start: () => Promise<void>;
  stop: () => void;
  sendEvent: (event: Record<string, unknown>) => void;
  getAnalyser: () => AnalyserNode | null;
}

export function useRealtimeSession(deckId: string | null): RealtimeSessionHandle {
  const wsRef = useRef<WebSocket | null>(null);
  const startingRef = useRef(false);
  const pendingEndRef = useRef(false);

  const setAgentStatus = usePresentationStore((s) => s.setAgentStatus);
  const setActiveSlide = usePresentationStore((s) => s.setActiveSlide);
  const setCursorTarget = usePresentationStore((s) => s.setCursorTarget);
  const setConnected = usePresentationStore((s) => s.setConnected);
  const setMicActive = usePresentationStore((s) => s.setMicActive);
  const setError = usePresentationStore((s) => s.setError);
  const addTranscript = usePresentationStore((s) => s.addTranscript);
  const appendTranscript = usePresentationStore((s) => s.appendTranscript);
  const beginUserTurn = usePresentationStore((s) => s.beginUserTurn);
  const completeUserTurn = usePresentationStore((s) => s.completeUserTurn);

  const sendAudioRef = useRef<(buffer: ArrayBuffer) => void>(() => {});

  const audio = useAudioStream((buffer) => {
    sendAudioRef.current(buffer);
  });

  const stop = useCallback(() => {
    pendingEndRef.current = false;
    try {
      wsRef.current?.close();
    } catch {
      // ignore
    }
    wsRef.current = null;
    audio.stopRecording();
    audio.stopPlayback();
    setConnected(false);
    setMicActive(false);
    setAgentStatus("idle");
  }, [audio, setConnected, setMicActive, setAgentStatus]);

  const triggerDownload = useCallback(() => {
    if (!deckId) return;
    const a = document.createElement("a");
    a.href = deckPdfUrl(deckId);
    a.rel = "noopener";
    a.target = "_blank";
    a.download = "";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }, [deckId]);

  const handleEvent = useCallback(
    (raw: string) => {
      let event: Record<string, unknown>;
      try {
        event = JSON.parse(raw);
      } catch {
        return;
      }
      const type = event.type as string | undefined;
      if (!type) return;

      switch (type) {
        case "slide_change": {
          const newIndex = event.new_index as number;
          setActiveSlide(newIndex);
          break;
        }
        case "cursor_move": {
          setCursorTarget(event.target as CursorTarget);
          break;
        }
        case "download_deck": {
          triggerDownload();
          break;
        }
        case "end_session": {
          // Mark the session as pending-close so we can stop cleanly AFTER
          // the agent's farewell audio has finished playing.
          pendingEndRef.current = true;
          break;
        }
        case "response.audio.delta": {
          audio.playChunk(event.delta as string);
          setAgentStatus("speaking");
          break;
        }
        case "response.audio.done":
        case "response.done": {
          setAgentStatus("listening");
          if (pendingEndRef.current) {
            pendingEndRef.current = false;
            window.setTimeout(() => stop(), 400);
          }
          break;
        }
        case "response.created": {
          setAgentStatus("processing");
          break;
        }
        case "input_audio_buffer.speech_started": {
          audio.stopPlayback();
          setAgentStatus("listening");
          beginUserTurn();
          // User interrupted — cancel any pending end-session.
          pendingEndRef.current = false;
          break;
        }
        case "input_audio_buffer.speech_stopped": {
          setAgentStatus("processing");
          break;
        }
        case "response.audio_transcript.delta": {
          appendTranscript("AI", (event.delta as string) ?? "");
          break;
        }
        case "conversation.item.input_audio_transcription.completed": {
          completeUserTurn((event.transcript as string) ?? "");
          break;
        }
        case "conversation.item.input_audio_transcription.failed": {
          completeUserTurn("");
          break;
        }
        case "error": {
          const msg =
            (event.error as { message?: string } | undefined)?.message ||
            "Realtime error";
          setError(msg);
          break;
        }
        default:
          break;
      }
    },
    [
      audio,
      setActiveSlide,
      setAgentStatus,
      setCursorTarget,
      addTranscript,
      appendTranscript,
      beginUserTurn,
      completeUserTurn,
      setError,
      triggerDownload,
      stop,
    ],
  );

  const sendEvent = useCallback((event: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(event));
    }
  }, []);

  sendAudioRef.current = (buffer: ArrayBuffer) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(buffer);
    }
  };

  const start = useCallback(async () => {
    if (!deckId) throw new Error("No deck");
    if (startingRef.current || wsRef.current) return;
    startingRef.current = true;

    try {
      setAgentStatus("connecting");
      setError(null);
      pendingEndRef.current = false;

      await audio.startRecording();
      setMicActive(true);

      const ws = new WebSocket(wsUrlForDeck(deckId));
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setAgentStatus("listening");
        ws.send(
          JSON.stringify({
            type: "conversation.item.create",
            item: {
              type: "message",
              role: "user",
              content: [
                {
                  type: "input_text",
                  text:
                    "The presentation is starting now. Follow your per-slide sequence exactly: for every slide, " +
                    "point_at('title') with a one-sentence framing, then walk through EVERY bullet in order starting " +
                    "with bullet_0 — each bullet gets its own point_at call and 1-2 sentences of narration. " +
                    "Only after the last bullet of a slide do you call point_at('next_button') and change_slide('next'). " +
                    "Never skip bullet_0. Never stop mid-slide. Do not pause between slides unless I interrupt you.",
                },
              ],
            },
          }),
        );
        ws.send(JSON.stringify({ type: "response.create" }));
      };

      ws.onmessage = (ev) => {
        if (typeof ev.data === "string") handleEvent(ev.data);
      };

      ws.onerror = () => {
        setError("Realtime connection error");
      };

      ws.onclose = () => {
        wsRef.current = null;
        setConnected(false);
        setMicActive(false);
        setAgentStatus("idle");
        audio.stopRecording();
        audio.stopPlayback();
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      stop();
    } finally {
      startingRef.current = false;
    }
  }, [
    deckId,
    audio,
    handleEvent,
    setAgentStatus,
    setConnected,
    setError,
    setMicActive,
    stop,
  ]);

  useEffect(() => {
    return () => {
      try {
        wsRef.current?.close();
      } catch {
        // ignore
      }
      wsRef.current = null;
    };
  }, []);

  const getAnalyser = audio.getAnalyser;

  return useMemo(
    () => ({ start, stop, sendEvent, getAnalyser }),
    [start, stop, sendEvent, getAnalyser],
  );
}
