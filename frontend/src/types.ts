export type AgentStatus = "idle" | "connecting" | "listening" | "processing" | "speaking";

export type TextAmount = "brief" | "medium" | "detailed" | "extensive";

export interface Bullet {
  headline: string;
  detail: string;
}

export interface Stat {
  value: string;
  label: string;
}

export interface Slide {
  id: number;
  title: string;
  subtitle?: string;
  bullets: Bullet[];
  steps?: string[];
  stats?: Stat[];
  key_takeaway?: string;
  speaker_note: string;
}

export interface Deck {
  id: string;
  topic: string;
  text_amount: TextAmount;
  slides: Slide[];
}

export interface TranscriptEntry {
  id: string;
  speaker: "AI" | "User";
  text: string;
}

export type CursorTarget =
  | "title"
  | "next_button"
  | "prev_button"
  | `bullet_${number}`;
