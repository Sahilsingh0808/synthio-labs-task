import { useCallback, useState } from "react";
import { ArrowRight, Lock, Presentation } from "lucide-react";
import { useAuthStore } from "../store/useAuthStore";

export function LoginScreen() {
  const login = useAuthStore((s) => s.login);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      setSubmitting(true);
      // Wrapped in a microtask so the UI gets a chance to show pending state
      // even though the check is synchronous.
      queueMicrotask(() => {
        const ok = login(username, password);
        if (!ok) setError("Incorrect username or password.");
        setSubmitting(false);
      });
    },
    [login, username, password],
  );

  return (
    <div className="min-h-screen flex items-center justify-center px-6 py-12 bg-ink-50">
      <div className="w-full max-w-md">
        <header className="flex items-center gap-2 mb-10">
          <div className="w-8 h-8 rounded-md bg-ink-950 text-ink-50 grid place-items-center">
            <Presentation size={16} strokeWidth={2} />
          </div>
          <span className="text-sm font-medium tracking-tight text-ink-900">
            VoiceSlide
          </span>
        </header>

        <div className="mb-8">
          <div className="inline-flex items-center gap-2 rounded-full bg-ink-100 px-3 h-7 text-[11px] font-medium tracking-wide uppercase text-ink-600 mb-5">
            <Lock size={12} strokeWidth={2.25} />
            <span>Private</span>
          </div>
          <h1 className="text-3xl md:text-4xl font-semibold tracking-tight text-ink-950 leading-[1.1]">
            Sign in to continue.
          </h1>
          <p className="mt-3 text-ink-600 text-[15px] leading-relaxed">
            This VoiceSlide instance is restricted. Enter the credentials
            shared with you to access the deck builder and presentation
            agent.
          </p>
        </div>

        <form
          onSubmit={onSubmit}
          className="bg-white rounded-2xl border border-ink-200 shadow-card p-6 md:p-7 space-y-5"
        >
          <div>
            <label
              htmlFor="username"
              className="block text-xs font-medium tracking-wide uppercase text-ink-500 mb-2"
            >
              Username
            </label>
            <input
              id="username"
              name="username"
              type="text"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full h-10 rounded-lg border border-ink-200 bg-ink-50/50 px-4 text-ink-900 placeholder:text-ink-400 focus:outline-none focus:border-ink-900 transition-colors"
              placeholder="your-username"
              required
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-xs font-medium tracking-wide uppercase text-ink-500 mb-2"
            >
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full h-10 rounded-lg border border-ink-200 bg-ink-50/50 px-4 text-ink-900 placeholder:text-ink-400 focus:outline-none focus:border-ink-900 transition-colors"
              placeholder="••••••••"
              required
            />
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 text-red-700 text-sm px-4 py-3">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !username || !password}
            className="group w-full inline-flex items-center justify-center gap-2 h-10 px-5 rounded-md bg-ink-950 text-ink-50 text-sm font-medium hover:bg-ink-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <span>Sign in</span>
            <ArrowRight
              size={14}
              className="transition-transform group-hover:translate-x-0.5"
            />
          </button>
        </form>

        <footer className="mt-8 text-xs text-ink-400">
          Azure OpenAI · Realtime API · FastAPI · React
        </footer>
      </div>
    </div>
  );
}
