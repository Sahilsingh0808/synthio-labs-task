import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CursorTarget } from "../types";

interface Props {
  target: CursorTarget;
  containerRef: React.RefObject<HTMLElement | null>;
  visible: boolean;
}

interface Position {
  x: number;
  y: number;
}

export function AgentCursor({ target, containerRef, visible }: Props) {
  const cursorRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const [clicking, setClicking] = useState(false);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const measure = () => {
      const el = container.querySelector<HTMLElement>(
        `[data-cursor-target="${target}"]`,
      );
      if (!el) return;
      const containerRect = container.getBoundingClientRect();
      const rect = el.getBoundingClientRect();
      const x = rect.left - containerRect.left + rect.width * 0.18;
      const y = rect.top - containerRect.top + rect.height * 0.5;
      setPosition({ x, y });
    };

    measure();

    const ro = new ResizeObserver(measure);
    ro.observe(container);
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [target, containerRef]);

  useEffect(() => {
    if (target === "next_button" || target === "prev_button") {
      setClicking(true);
      const id = window.setTimeout(() => setClicking(false), 260);
      return () => window.clearTimeout(id);
    }
    return undefined;
  }, [target]);

  if (!position) return null;

  return (
    <div
      ref={cursorRef}
      aria-hidden
      className="pointer-events-none absolute z-20"
      style={{
        left: 0,
        top: 0,
        transform: `translate3d(${position.x - 6}px, ${position.y - 6}px, 0)`,
        transition:
          "transform 480ms cubic-bezier(0.22, 1, 0.36, 1), opacity 200ms",
        opacity: visible ? 1 : 0,
      }}
    >
      <div
        className={
          "relative flex items-center gap-2 " + (clicking ? "cursor-click" : "")
        }
      >
        <svg
          width="22"
          height="22"
          viewBox="0 0 22 22"
          className="drop-shadow-[0_2px_6px_rgba(12,10,9,0.35)]"
        >
          <path
            d="M3.5 2.5 L3.5 18.5 L8 14 L11 20 L13.5 19 L10.5 13 L17 13 Z"
            fill="#0c0a09"
            stroke="#fafaf9"
            strokeWidth="1.2"
            strokeLinejoin="round"
          />
        </svg>
        <span className="px-2 py-0.5 rounded-full text-[10px] font-medium tracking-wide uppercase bg-ink-950 text-ink-50 shadow-sleek">
          Agent
        </span>
      </div>
    </div>
  );
}
