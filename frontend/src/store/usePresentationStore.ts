import { create } from "zustand";
import type { AgentStatus, CursorTarget, Deck, TranscriptEntry } from "../types";

interface State {
  deck: Deck | null;
  activeSlide: number;
  agentStatus: AgentStatus;
  cursorTarget: CursorTarget;
  transcript: TranscriptEntry[];
  isConnected: boolean;
  isMicActive: boolean;
  error: string | null;
}

interface Actions {
  setDeck: (deck: Deck | null) => void;
  setActiveSlide: (index: number) => void;
  setAgentStatus: (status: AgentStatus) => void;
  setCursorTarget: (target: CursorTarget) => void;
  addTranscript: (speaker: "AI" | "User", text: string) => void;
  appendTranscript: (speaker: "AI" | "User", delta: string) => void;
  beginUserTurn: () => void;
  completeUserTurn: (text: string) => void;
  setConnected: (connected: boolean) => void;
  setMicActive: (active: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const makeId = () =>
  `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

const initial: State = {
  deck: null,
  activeSlide: 0,
  agentStatus: "idle",
  cursorTarget: "title",
  transcript: [],
  isConnected: false,
  isMicActive: false,
  error: null,
};

export const usePresentationStore = create<State & Actions>((set, get) => ({
  ...initial,

  setDeck: (deck) =>
    set({
      deck,
      activeSlide: 0,
      cursorTarget: "title",
      transcript: [],
      error: null,
    }),

  setActiveSlide: (index) =>
    set({ activeSlide: index, cursorTarget: "title" }),

  setAgentStatus: (agentStatus) => set({ agentStatus }),

  setCursorTarget: (cursorTarget) => set({ cursorTarget }),

  addTranscript: (speaker, text) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    set({
      transcript: [
        ...get().transcript,
        { id: makeId(), speaker, text: trimmed },
      ],
    });
  },

  appendTranscript: (speaker, delta) => {
    if (!delta) return;
    const entries = get().transcript;
    const last = entries[entries.length - 1];
    if (last && last.speaker === speaker && last.text !== "") {
      const updated = [...entries];
      updated[updated.length - 1] = { ...last, text: last.text + delta };
      set({ transcript: updated });
    } else {
      set({
        transcript: [
          ...entries,
          { id: makeId(), speaker, text: delta },
        ],
      });
    }
  },

  beginUserTurn: () => {
    const entries = get().transcript;
    const last = entries[entries.length - 1];
    if (last && last.speaker === "User" && last.text === "") return;
    set({
      transcript: [
        ...entries,
        { id: makeId(), speaker: "User", text: "" },
      ],
    });
  },

  completeUserTurn: (text) => {
    const trimmed = text.trim();
    const entries = get().transcript;
    for (let i = entries.length - 1; i >= 0; i--) {
      if (entries[i].speaker === "User" && entries[i].text === "") {
        const updated = [...entries];
        if (trimmed) {
          updated[i] = { ...updated[i], text: trimmed };
          set({ transcript: updated });
        } else {
          updated.splice(i, 1);
          set({ transcript: updated });
        }
        return;
      }
    }
    if (trimmed) {
      set({
        transcript: [
          ...entries,
          { id: makeId(), speaker: "User", text: trimmed },
        ],
      });
    }
  },

  setConnected: (isConnected) => set({ isConnected }),
  setMicActive: (isMicActive) => set({ isMicActive }),
  setError: (error) => set({ error }),

  reset: () => set({ ...initial }),
}));
