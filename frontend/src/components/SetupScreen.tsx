import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  FileUp,
  Loader2,
  LogOut,
  Presentation,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";
import { generateDeck, uploadFileForDeck } from "../lib/api";
import { usePresentationStore } from "../store/usePresentationStore";
import { AUTH_ENABLED, useAuthStore } from "../store/useAuthStore";
import type { TextAmount } from "../types";

type Mode = "prompt" | "upload";

const COUNT_OPTIONS = [4, 5, 6, 7, 8];

const TEXT_AMOUNTS: Array<{ id: TextAmount; label: string; hint: string }> = [
  { id: "brief", label: "Brief", hint: "Tight highlights" },
  { id: "medium", label: "Medium", hint: "Keynote density" },
  { id: "detailed", label: "Detailed", hint: "Richer depth" },
  { id: "extensive", label: "Extensive", hint: "Technical briefing" },
];

const EXAMPLE_PROMPTS: string[] = [
  "The history of typography, from Gutenberg's press in 1440 to Helvetica and the Swiss Style — cover key movements, landmark typefaces, and how printing shaped reading.",
  "How the Transformer architecture works under the hood for a backend engineer: tokens, embeddings, self-attention, multi-head attention, residual streams, and why it scales where RNNs failed.",
  "A kickoff briefing for a 3-week migration from REST to GraphQL: why we're doing it, schema design approach, N+1 mitigations with DataLoader, auth model, and a rollout plan with success metrics.",
  "The science of sleep: circadian rhythms, the four stages of sleep, REM function, the cost of sleep debt on cognition and immunity, and evidence-based practices that actually move the needle.",
  "A pitch for bringing retrieval-augmented generation into a legal document review workflow: the pain today, the proposed architecture, accuracy guardrails, a pilot plan, and the ROI math.",
];

export function SetupScreen() {
  const [mode, setMode] = useState<Mode>("prompt");
  const [prompt, setPrompt] = useState("");
  const [count, setCount] = useState(6);
  const [textAmount, setTextAmount] = useState<TextAmount>("detailed");
  const [file, setFile] = useState<File | null>(null);
  const [extraPrompt, setExtraPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const setDeck = usePresentationStore((s) => s.setDeck);
  const logout = useAuthStore((s) => s.logout);

  const onSubmit = useCallback(async () => {
    setLocalError(null);
    setLoading(true);
    try {
      if (mode === "prompt") {
        if (prompt.trim().length < 3) {
          throw new Error("Please describe your topic (at least a few words).");
        }
        const deck = await generateDeck(prompt.trim(), count, textAmount);
        setDeck(deck);
      } else {
        if (!file) throw new Error("Select a file to analyze.");
        const deck = await uploadFileForDeck(file, count, textAmount, extraPrompt);
        setDeck(deck);
      }
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [mode, prompt, count, textAmount, file, extraPrompt, setDeck]);

  return (
    <div className="min-h-screen flex items-center justify-center px-6 py-12 bg-ink-50">
      <div className="w-full max-w-2xl">
        <header className="flex items-center justify-between mb-10">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-md bg-ink-950 text-ink-50 grid place-items-center">
              <Presentation size={16} strokeWidth={2} />
            </div>
            <span className="text-sm font-medium tracking-tight text-ink-900">
              VoiceSlide
            </span>
          </div>
          {AUTH_ENABLED && (
            <button
              type="button"
              onClick={logout}
              className="inline-flex items-center gap-1.5 text-xs text-ink-500 hover:text-ink-900 transition-colors"
            >
              <LogOut size={12} strokeWidth={2} />
              <span>Sign out</span>
            </button>
          )}
        </header>

        <div>
          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-ink-950 leading-[1.05]">
            Present with a voice agent
            <br />
            <span className="text-ink-400">that knows your deck.</span>
          </h1>
          <p className="mt-5 text-ink-600 text-base max-w-xl leading-relaxed">
            Describe a topic or upload a slide. The agent will build the deck,
            narrate it, answer questions, and navigate in real time.
          </p>
        </div>

        <div className="mt-10 bg-white rounded-2xl border border-ink-200 shadow-card overflow-hidden">
          <div className="flex border-b border-ink-200">
            <TabButton active={mode === "prompt"} onClick={() => setMode("prompt")}>
              <Sparkles size={14} strokeWidth={2} />
              <span>Describe a topic</span>
            </TabButton>
            <TabButton active={mode === "upload"} onClick={() => setMode("upload")}>
              <FileUp size={14} strokeWidth={2} />
              <span>Upload a slide</span>
            </TabButton>
          </div>

          <div className="p-6 md:p-8 space-y-6">
            {mode === "prompt" ? (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-xs font-medium tracking-wide uppercase text-ink-500">
                    Topic
                  </label>
                  <ExamplePromptPicker onPick={setPrompt} />
                </div>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="e.g. How the Transformer architecture works for a backend engineer — tokens, attention, and why it scales"
                  rows={5}
                  className="w-full resize-none rounded-lg border border-ink-200 bg-ink-50/50 px-4 py-3 text-ink-900 placeholder:text-ink-400 focus:outline-none focus:border-ink-900 transition-colors leading-relaxed"
                />
              </div>
            ) : (
              <UploadField
                file={file}
                onFile={setFile}
                inputRef={fileInputRef}
                extraPrompt={extraPrompt}
                onExtraPrompt={setExtraPrompt}
              />
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-xs font-medium tracking-wide uppercase text-ink-500 mb-3">
                  Number of slides
                </label>
                <div className="flex flex-wrap gap-2">
                  {COUNT_OPTIONS.map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setCount(n)}
                      className={
                        "px-3.5 h-9 rounded-md text-sm font-medium transition-colors border " +
                        (count === n
                          ? "bg-ink-950 text-ink-50 border-ink-950"
                          : "bg-white text-ink-700 border-ink-200 hover:border-ink-400")
                      }
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium tracking-wide uppercase text-ink-500 mb-3">
                  Text amount
                </label>
                <div className="flex flex-wrap gap-2">
                  {TEXT_AMOUNTS.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setTextAmount(t.id)}
                      title={t.hint}
                      className={
                        "px-3.5 h-9 rounded-md text-sm font-medium transition-colors border " +
                        (textAmount === t.id
                          ? "bg-ink-950 text-ink-50 border-ink-950"
                          : "bg-white text-ink-700 border-ink-200 hover:border-ink-400")
                      }
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
                <p className="mt-2 text-xs text-ink-500">
                  {TEXT_AMOUNTS.find((t) => t.id === textAmount)?.hint}
                </p>
              </div>
            </div>

            {localError && (
              <div className="rounded-lg border border-red-200 bg-red-50 text-red-700 text-sm px-4 py-3">
                {localError}
              </div>
            )}

            <div className="flex items-center justify-between gap-3 pt-2">
              <p className="text-xs text-ink-500">
                Generation takes ~15-40s depending on density.
              </p>
              <button
                type="button"
                disabled={loading}
                onClick={onSubmit}
                className="group inline-flex items-center gap-2 h-10 px-5 rounded-md bg-ink-950 text-ink-50 text-sm font-medium hover:bg-ink-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Building deck</span>
                  </>
                ) : (
                  <>
                    <span>Build deck</span>
                    <ArrowRight
                      size={14}
                      className="transition-transform group-hover:translate-x-0.5"
                    />
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        <footer className="mt-10 text-xs text-ink-400">
          Azure OpenAI · Realtime API · FastAPI · React
        </footer>
      </div>
    </div>
  );
}

function ExamplePromptPicker({ onPick }: { onPick: (prompt: string) => void }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDocMouseDown = (e: MouseEvent) => {
      if (!wrapRef.current) return;
      if (!wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 text-xs text-ink-500 hover:text-ink-900 transition-colors"
      >
        <Wand2 size={12} strokeWidth={2} />
        <span>Try an example</span>
      </button>
      {open && (
        <div
          className="absolute right-0 top-6 z-20 w-[min(420px,80vw)] max-h-72 overflow-y-auto scroll-soft bg-white border border-ink-200 rounded-lg shadow-card"
          role="listbox"
        >
          {EXAMPLE_PROMPTS.map((p, i) => (
            <button
              key={i}
              type="button"
              onClick={() => {
                onPick(p);
                setOpen(false);
              }}
              className="w-full text-left px-4 py-2.5 text-sm text-ink-700 hover:bg-ink-50 border-b border-ink-100 last:border-0 leading-snug"
            >
              {p}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "flex-1 flex items-center justify-center gap-2 h-11 text-sm font-medium transition-colors " +
        (active
          ? "text-ink-950 bg-white"
          : "text-ink-500 bg-ink-50 hover:text-ink-800")
      }
    >
      {children}
    </button>
  );
}

function UploadField({
  file,
  onFile,
  inputRef,
  extraPrompt,
  onExtraPrompt,
}: {
  file: File | null;
  onFile: (file: File | null) => void;
  inputRef: React.MutableRefObject<HTMLInputElement | null>;
  extraPrompt: string;
  onExtraPrompt: (value: string) => void;
}) {
  const [drag, setDrag] = useState(false);

  return (
    <div className="space-y-4">
      <label className="block text-xs font-medium tracking-wide uppercase text-ink-500 mb-2">
        Source file
      </label>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          const f = e.dataTransfer.files?.[0];
          if (f) onFile(f);
        }}
        className={
          "relative rounded-lg border-2 border-dashed transition-colors px-6 py-8 text-center " +
          (drag
            ? "border-ink-900 bg-ink-50"
            : "border-ink-200 bg-ink-50/40 hover:border-ink-400")
        }
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.pptx,.txt,.md,image/*"
          className="hidden"
          onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        />

        {file ? (
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 text-left min-w-0">
              <div className="w-9 h-9 rounded-md bg-white border border-ink-200 grid place-items-center shrink-0">
                <FileUp size={16} className="text-ink-700" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-ink-900 truncate">
                  {file.name}
                </div>
                <div className="text-xs text-ink-500">
                  {(file.size / 1024).toFixed(1)} KB
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onFile(null)}
              className="p-1.5 rounded-md text-ink-500 hover:text-ink-900 hover:bg-ink-100 transition-colors"
              aria-label="Remove file"
            >
              <X size={16} />
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="w-full flex flex-col items-center gap-2 text-ink-600"
          >
            <div className="w-10 h-10 rounded-full bg-white border border-ink-200 grid place-items-center">
              <FileUp size={18} />
            </div>
            <div className="text-sm font-medium text-ink-900">
              Click to upload or drop a file
            </div>
            <div className="text-xs text-ink-500">PDF, PPTX, image, or text</div>
          </button>
        )}
      </div>

      <div>
        <label className="block text-xs font-medium tracking-wide uppercase text-ink-500 mb-2">
          Optional framing
        </label>
        <input
          type="text"
          value={extraPrompt}
          onChange={(e) => onExtraPrompt(e.target.value)}
          placeholder="e.g. Pitch this to a non-technical audience"
          className="w-full rounded-lg border border-ink-200 bg-ink-50/50 px-4 h-10 text-ink-900 placeholder:text-ink-400 focus:outline-none focus:border-ink-900 transition-colors"
        />
      </div>
    </div>
  );
}
