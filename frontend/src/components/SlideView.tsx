import { forwardRef } from "react";
import type { Slide } from "../types";

interface Props {
  slide: Slide;
  slideIndex: number;
  totalSlides: number;
  highlightedBullet: number | null;
}

export const SlideView = forwardRef<HTMLDivElement, Props>(function SlideView(
  { slide, slideIndex, totalSlides, highlightedBullet },
  ref,
) {
  const hasStats = !!slide.stats && slide.stats.length > 0;
  const hasSteps = !!slide.steps && slide.steps.length > 0;
  const hasTakeaway = !!slide.key_takeaway && slide.key_takeaway.length > 0;

  return (
    <div
      ref={ref}
      key={slideIndex}
      className="slide-enter px-10 pt-8 pb-8 md:px-16 md:pt-12 md:pb-12"
    >
      <div className="flex items-center justify-between mb-6">
        <span className="text-[11px] font-medium tracking-[0.18em] uppercase text-ink-400">
          Slide {slideIndex + 1} of {totalSlides}
        </span>
        <span className="h-1 w-28 rounded-full bg-ink-100 overflow-hidden">
          <span
            className="block h-full bg-ink-900 transition-all duration-500"
            style={{
              width: `${((slideIndex + 1) / totalSlides) * 100}%`,
            }}
          />
        </span>
      </div>

      <h1
        data-cursor-target="title"
        className="text-[2rem] md:text-[2.5rem] font-semibold tracking-tight text-ink-950 leading-[1.12]"
      >
        {slide.title}
      </h1>

      {slide.subtitle && (
        <p className="mt-3 text-lg text-ink-500 leading-relaxed">
          {slide.subtitle}
        </p>
      )}

      {hasStats && (
        <div className="mt-7 grid grid-cols-2 md:grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
          {slide.stats!.map((stat, i) => (
            <div
              key={i}
              className="rounded-lg border border-ink-200 bg-ink-50/50 px-4 py-3"
            >
              <div className="text-xl md:text-2xl font-semibold tracking-tight text-ink-950 tabular-nums">
                {stat.value}
              </div>
              <div className="mt-0.5 text-[11px] font-medium tracking-wide uppercase text-ink-500">
                {stat.label}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-7 grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-3">
        {slide.bullets.map((bullet, i) => {
          const isActive = highlightedBullet === i;
          return (
            <div
              key={i}
              data-cursor-target={`bullet_${i}`}
              style={{ animationDelay: `${i * 70}ms` }}
              className={
                "bullet-item relative rounded-lg px-3 py-2 -mx-3 transition-colors duration-300 " +
                (isActive ? "bg-ink-100/70" : "bg-transparent")
              }
            >
              <div className="flex items-start gap-3">
                <span
                  className={
                    "mt-2 w-1.5 h-1.5 rounded-full flex-shrink-0 transition-all duration-300 " +
                    (isActive ? "bg-ink-950 scale-125" : "bg-ink-300")
                  }
                />
                <div className="min-w-0 flex-1">
                  <div className="text-[1.05rem] md:text-[1.1rem] font-semibold text-ink-950 leading-snug">
                    {bullet.headline}
                  </div>
                  {bullet.detail && (
                    <p className="mt-1 text-[0.92rem] md:text-[0.95rem] text-ink-600 leading-relaxed">
                      {bullet.detail}
                    </p>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {hasSteps && (
        <div className="mt-7">
          <div className="text-[10px] font-semibold tracking-[0.18em] uppercase text-ink-400 mb-2">
            Process
          </div>
          <ol className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2">
            {slide.steps!.map((step, i) => (
              <li key={i} className="flex items-start gap-3">
                <span className="flex-shrink-0 mt-0.5 w-6 h-6 rounded-full border border-ink-300 text-ink-700 text-xs font-semibold tabular-nums grid place-items-center">
                  {i + 1}
                </span>
                <span className="text-[0.9rem] text-ink-700 leading-relaxed">
                  {step}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {hasTakeaway && (
        <div className="mt-6 pt-4 border-t border-ink-200">
          <div className="flex items-start gap-3">
            <span className="mt-1 text-[10px] font-semibold tracking-[0.18em] uppercase text-ink-400 shrink-0">
              Takeaway
            </span>
            <p className="text-[0.975rem] font-medium text-ink-900 leading-relaxed">
              {slide.key_takeaway}
            </p>
          </div>
        </div>
      )}
    </div>
  );
});
