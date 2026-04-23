import { ChevronLeft, ChevronRight, Mic, MicOff } from "lucide-react";
import type { AgentStatus } from "../types";

interface Props {
  agentStatus: AgentStatus;
  isConnected: boolean;
  isMicActive: boolean;
  onMicToggle: () => void;
  onPrev: () => void;
  onNext: () => void;
  canPrev: boolean;
  canNext: boolean;
  slideIndex: number;
  totalSlides: number;
}

const STATUS_LABEL: Record<AgentStatus, string> = {
  idle: "Idle",
  connecting: "Connecting",
  listening: "Listening",
  processing: "Thinking",
  speaking: "Speaking",
};

const STATUS_DOT: Record<AgentStatus, string> = {
  idle: "bg-ink-300",
  connecting: "bg-amber-500 animate-pulse",
  listening: "bg-emerald-500",
  processing: "bg-amber-500 animate-pulse",
  speaking: "bg-ink-950 animate-pulse",
};

export function Controls(props: Props) {
  const {
    agentStatus,
    isConnected,
    isMicActive,
    onMicToggle,
    onPrev,
    onNext,
    canPrev,
    canNext,
    slideIndex,
    totalSlides,
  } = props;

  return (
    <div className="flex items-center justify-between gap-4 px-6 py-4 bg-white/80 backdrop-blur border-t border-ink-200">
      <div className="flex items-center gap-4 min-w-0">
        <div className="flex items-center gap-2">
          <span
            className={"w-1.5 h-1.5 rounded-full " + (isConnected ? "bg-emerald-500" : "bg-ink-300")}
          />
          <span className="text-xs text-ink-500">
            {isConnected ? "Live" : "Offline"}
          </span>
        </div>
        <div className="hidden md:flex items-center gap-2">
          <span className={"w-1.5 h-1.5 rounded-full " + STATUS_DOT[agentStatus]} />
          <span className="text-xs text-ink-500">{STATUS_LABEL[agentStatus]}</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onPrev}
          disabled={!canPrev}
          aria-label="Previous slide"
          data-cursor-target="prev_button"
          className="w-9 h-9 rounded-full grid place-items-center border border-ink-200 text-ink-700 bg-white hover:border-ink-900 hover:text-ink-950 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronLeft size={16} />
        </button>

        <button
          type="button"
          onClick={onMicToggle}
          aria-label={isMicActive ? "Stop microphone" : "Start microphone"}
          aria-pressed={isMicActive}
          className={
            "w-12 h-12 rounded-full grid place-items-center text-ink-50 transition-all duration-200 " +
            (isMicActive
              ? "bg-ink-950 pulse-ring"
              : "bg-ink-800 hover:bg-ink-950")
          }
        >
          {isMicActive ? <MicOff size={18} /> : <Mic size={18} />}
        </button>

        <button
          type="button"
          onClick={onNext}
          disabled={!canNext}
          aria-label="Next slide"
          data-cursor-target="next_button"
          className="w-9 h-9 rounded-full grid place-items-center border border-ink-200 text-ink-700 bg-white hover:border-ink-900 hover:text-ink-950 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronRight size={16} />
        </button>
      </div>

      <div className="flex items-center min-w-0 justify-end">
        <span className="text-xs tabular-nums text-ink-500">
          {slideIndex + 1} <span className="text-ink-300">/</span> {totalSlides}
        </span>
      </div>
    </div>
  );
}
