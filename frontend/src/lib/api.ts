import type { Deck, TextAmount } from "../types";

// If ``VITE_API_BASE`` / ``VITE_WS_BASE`` are empty strings (the production
// nginx-proxy default), fall back to relative URLs — the browser hits the
// same origin the frontend is served from and nginx forwards to the backend.
const API_BASE_ENV = import.meta.env.VITE_API_BASE;
const WS_BASE_ENV = import.meta.env.VITE_WS_BASE;

const API_BASE =
  API_BASE_ENV !== undefined ? API_BASE_ENV : "http://localhost:9001";
const WS_BASE_RAW =
  WS_BASE_ENV !== undefined ? WS_BASE_ENV : "ws://localhost:9001";

function resolveWsBase(): string {
  if (WS_BASE_RAW) return WS_BASE_RAW;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}

export const WS_BASE = WS_BASE_RAW;

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function generateDeck(
  prompt: string,
  count: number,
  textAmount: TextAmount,
): Promise<Deck> {
  const res = await fetch(`${API_BASE}/api/decks/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, count, text_amount: textAmount }),
  });
  return handle<Deck>(res);
}

export async function uploadFileForDeck(
  file: File,
  count: number,
  textAmount: TextAmount,
  extraPrompt = "",
): Promise<Deck> {
  const body = new FormData();
  body.append("file", file);
  body.append("count", String(count));
  body.append("text_amount", textAmount);
  if (extraPrompt) body.append("extra_prompt", extraPrompt);
  const res = await fetch(`${API_BASE}/api/decks/from-file`, {
    method: "POST",
    body,
  });
  return handle<Deck>(res);
}

export function wsUrlForDeck(deckId: string): string {
  return `${resolveWsBase()}/ws/${deckId}`;
}

export function deckPdfUrl(deckId: string): string {
  return `${API_BASE}/api/decks/${deckId}/pdf`;
}
