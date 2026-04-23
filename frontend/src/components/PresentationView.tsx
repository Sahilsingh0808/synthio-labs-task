import { useCallback, useEffect, useMemo, useRef } from "react";
import { ArrowLeft, Download } from "lucide-react";
import { AgentCursor } from "./AgentCursor";
import { AutoFitSlide } from "./AutoFitSlide";
import { Controls } from "./Controls";
import { SlideView } from "./SlideView";
import { TranscriptPanel } from "./TranscriptPanel";
import { useRealtimeSession } from "../hooks/useRealtimeSession";
import { usePresentationStore } from "../store/usePresentationStore";
import { deckPdfUrl } from "../lib/api";

export function PresentationView() {
  const deck = usePresentationStore((s) => s.deck);
  const activeSlide = usePresentationStore((s) => s.activeSlide);
  const agentStatus = usePresentationStore((s) => s.agentStatus);
  const transcript = usePresentationStore((s) => s.transcript);
  const isConnected = usePresentationStore((s) => s.isConnected);
  const isMicActive = usePresentationStore((s) => s.isMicActive);
  const cursorTarget = usePresentationStore((s) => s.cursorTarget);
  const error = usePresentationStore((s) => s.error);
  const setActiveSlide = usePresentationStore((s) => s.setActiveSlide);
  const reset = usePresentationStore((s) => s.reset);

  const session = useRealtimeSession(deck?.id ?? null);

  const slideRef = useRef<HTMLDivElement | null>(null);

  const currentSlide = useMemo(() => {
    if (!deck) return null;
    return deck.slides[activeSlide] ?? deck.slides[0];
  }, [deck, activeSlide]);

  const totalSlides = deck?.slides.length ?? 0;

  const handleMicToggle = useCallback(() => {
    if (isMicActive) {
      session.stop();
    } else {
      void session.start();
    }
  }, [isMicActive, session]);

  const navigateManually = useCallback(
    (newIndex: number) => {
      setActiveSlide(newIndex);
      if (isConnected) {
        session.sendEvent({ type: "client.manual_slide", index: newIndex });
      }
    },
    [isConnected, session, setActiveSlide],
  );

  const handlePrev = useCallback(() => {
    if (activeSlide > 0) navigateManually(activeSlide - 1);
  }, [activeSlide, navigateManually]);

  const handleNext = useCallback(() => {
    if (activeSlide < totalSlides - 1) navigateManually(activeSlide + 1);
  }, [activeSlide, totalSlides, navigateManually]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement) {
        const tag = e.target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return;
      }
      if (e.key === "ArrowRight") handleNext();
      if (e.key === "ArrowLeft") handlePrev();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleNext, handlePrev]);

  const highlightedBullet = useMemo(() => {
    if (!cursorTarget.startsWith("bullet_")) return null;
    const n = Number(cursorTarget.slice("bullet_".length));
    return Number.isFinite(n) ? n : null;
  }, [cursorTarget]);

  if (!deck || !currentSlide) return null;

  return (
    <div className="h-screen flex flex-col bg-ink-50">
      <header className="flex items-center justify-between gap-4 px-6 py-3 border-b border-ink-200 bg-white/80 backdrop-blur flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <button
            type="button"
            onClick={() => {
              session.stop();
              reset();
            }}
            className="inline-flex items-center gap-1.5 text-sm text-ink-600 hover:text-ink-950 transition-colors"
          >
            <ArrowLeft size={14} />
            <span>New deck</span>
          </button>
          <span className="h-4 w-px bg-ink-200" />
          <span className="text-sm font-medium tracking-tight text-ink-900 truncate">
            {deck.topic}
          </span>
        </div>
        <a
          href={deckPdfUrl(deck.id)}
          download
          className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-ink-200 bg-white text-xs font-medium text-ink-700 hover:border-ink-900 hover:text-ink-950 transition-colors"
          aria-label="Download deck as PDF"
        >
          <Download size={13} />
          <span>PDF</span>
        </a>
      </header>

      <main className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-[1fr_320px]">
        <section
          className="relative flex-1 min-h-0 px-6 py-6 md:px-10 md:py-8 flex items-center justify-center overflow-hidden"
          style={{ containerType: "size" }}
        >
          <div
            ref={slideRef}
            className="relative"
            style={{
              aspectRatio: "16 / 9",
              width: "min(100cqw, 100cqh * 16 / 9)",
              maxWidth: "100%",
              maxHeight: "100%",
            }}
          >
            <AutoFitSlide>
              <SlideView
                slide={currentSlide}
                slideIndex={activeSlide}
                totalSlides={totalSlides}
                highlightedBullet={highlightedBullet}
              />
            </AutoFitSlide>
            <AgentCursor
              target={cursorTarget}
              containerRef={slideRef}
              visible={isConnected}
            />
          </div>
        </section>
        <div className="hidden md:flex min-h-0">
          <TranscriptPanel entries={transcript} />
        </div>
      </main>

      {error && (
        <div className="px-6 py-2 bg-red-50 border-t border-red-200 text-xs text-red-700">
          {error}
        </div>
      )}

      <footer className="flex-shrink-0">
        <Controls
          agentStatus={agentStatus}
          isConnected={isConnected}
          isMicActive={isMicActive}
          onMicToggle={handleMicToggle}
          onPrev={handlePrev}
          onNext={handleNext}
          canPrev={activeSlide > 0}
          canNext={activeSlide < totalSlides - 1}
          slideIndex={activeSlide}
          totalSlides={totalSlides}
        />
      </footer>
    </div>
  );
}
