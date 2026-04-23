import { create } from "zustand";

const STORAGE_KEY = "voiceslide:auth:v1";

const CONFIGURED_USERNAME = (import.meta.env.VITE_AUTH_USERNAME ?? "").trim();
const CONFIGURED_PASSWORD = import.meta.env.VITE_AUTH_PASSWORD ?? "";

/** Whether the build was configured with credentials at all. If not, the
 *  app runs open (no login page). */
export const AUTH_ENABLED: boolean =
  CONFIGURED_USERNAME.length > 0 && CONFIGURED_PASSWORD.length > 0;

interface PersistedAuth {
  username: string;
  loggedInAt: number;
}

function loadPersisted(): PersistedAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PersistedAuth>;
    if (typeof parsed?.username !== "string" || !parsed.username) return null;
    // If the build's configured username changed, invalidate the stored
    // session so an old login can't resurrect itself.
    if (parsed.username !== CONFIGURED_USERNAME) return null;
    return {
      username: parsed.username,
      loggedInAt: typeof parsed.loggedInAt === "number" ? parsed.loggedInAt : Date.now(),
    };
  } catch {
    return null;
  }
}

function persist(state: PersistedAuth | null) {
  try {
    if (state) localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore quota / private-mode issues
  }
}

interface AuthState {
  authed: boolean;
  username: string | null;
}

interface AuthActions {
  /** Returns ``true`` on success, ``false`` on mismatch. */
  login: (username: string, password: string) => boolean;
  logout: () => void;
}

const persisted = AUTH_ENABLED ? loadPersisted() : null;

export const useAuthStore = create<AuthState & AuthActions>((set) => ({
  // If no credentials configured at build time, everybody is "authed".
  authed: !AUTH_ENABLED || !!persisted,
  username: persisted?.username ?? (!AUTH_ENABLED ? null : null),

  login: (username, password) => {
    if (!AUTH_ENABLED) {
      set({ authed: true, username: null });
      return true;
    }
    const u = username.trim();
    const p = password;
    if (u === CONFIGURED_USERNAME && p === CONFIGURED_PASSWORD) {
      persist({ username: u, loggedInAt: Date.now() });
      set({ authed: true, username: u });
      return true;
    }
    return false;
  },

  logout: () => {
    persist(null);
    set({ authed: !AUTH_ENABLED, username: null });
  },
}));
