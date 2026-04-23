import { useLayoutEffect, useRef, useState } from "react";

interface Props {
  children: React.ReactNode;
  minScale?: number;
}

export function AutoFitSlide({ children, minScale = 0.45 }: Props) {
  const outerRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const [scale, setScale] = useState(1);

  useLayoutEffect(() => {
    const outer = outerRef.current;
    const content = contentRef.current;
    if (!outer || !content) return;

    const fit = () => {
      const outerH = outer.clientHeight;
      const outerW = outer.clientWidth;
      // offsetHeight/offsetWidth are layout dims — unaffected by CSS transform,
      // so reading them here does not create a measure→scale→remeasure loop.
      const contentH = content.offsetHeight;
      const contentW = content.offsetWidth;
      if (!outerH || !outerW || !contentH || !contentW) return;

      const next = Math.max(
        minScale,
        Math.min(1, outerH / contentH, outerW / contentW),
      );
      setScale((prev) => (Math.abs(prev - next) > 0.005 ? next : prev));
    };

    fit();

    const ro = new ResizeObserver(fit);
    ro.observe(outer);
    ro.observe(content);
    return () => ro.disconnect();
  }, [minScale]);

  return (
    <div
      ref={outerRef}
      className="relative w-full h-full bg-white rounded-2xl border border-ink-200 shadow-card overflow-hidden flex items-center justify-center"
    >
      <div
        ref={contentRef}
        className="w-full"
        style={{
          transform: `scale(${scale})`,
          transformOrigin: "center center",
          transition: "transform 180ms ease-out",
        }}
      >
        {children}
      </div>
    </div>
  );
}
