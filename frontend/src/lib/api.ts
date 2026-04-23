import type { Deck, TextAmount } from "../types";

const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export const WS_BASE =
  (import.meta.env.VITE_WS_BASE as string | undefined) ?? "ws://localhost:8000";

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
  return `${WS_BASE}/ws/${deckId}`;
}

export function deckPdfUrl(deckId: string): string {
  return `${API_BASE}/api/decks/${deckId}/pdf`;
}
