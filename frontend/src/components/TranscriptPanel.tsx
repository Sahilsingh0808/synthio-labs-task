import { useEffect, useRef } from "react";
import type { TranscriptEntry } from "../types";

interface Props {
  entries: TranscriptEntry[];
}

const STICK_THRESHOLD_PX = 80;

export function TranscriptPanel({ entries }: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const stickyRef = useRef(true);

  useEffect(() => {
    if (!stickyRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [entries]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickyRef.current = dist < STICK_THRESHOLD_PX;
  };

  return (
    <aside className="flex flex-col h-full bg-white border-l border-ink-200">
      <div className="px-5 py-4 border-b border-ink-200">
        <div className="text-[10px] font-semibold tracking-[0.18em] uppercase text-ink-400">
          Transcript
        </div>
      </div>
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="flex-1 min-h-0 overflow-y-auto scroll-soft px-5 py-4 space-y-4"
      >
        {entries.length === 0 ? (
          <p className="text-sm text-ink-400 italic mt-2">
            Start the session and begin speaking to see the conversation here.
          </p>
        ) : (
          entries.map((entry) => (
            <div key={entry.id} className="space-y-1">
              <div
                className={
                  "text-[10px] font-semibold tracking-[0.18em] uppercase " +
                  (entry.speaker === "AI" ? "text-ink-500" : "text-ink-700")
                }
              >
                {entry.speaker === "AI" ? "Agent" : "You"}
              </div>
              {entry.text ? (
                <div
                  className={
                    "text-sm leading-relaxed " +
                    (entry.speaker === "AI"
                      ? "text-ink-800"
                      : "text-ink-950 font-medium")
                  }
                >
                  {entry.text}
                </div>
              ) : (
                <div className="text-sm italic text-ink-400 inline-flex items-center gap-1">
                  <span>Listening</span>
                  <span className="inline-flex gap-0.5">
                    <Dot delay={0} />
                    <Dot delay={160} />
                    <Dot delay={320} />
                  </span>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </aside>
  );
}

function Dot({ delay }: { delay: number }) {
  return (
    <span
      className="inline-block w-1 h-1 rounded-full bg-ink-400 animate-pulse"
      style={{ animationDelay: `${delay}ms` }}
    />
  );
}
