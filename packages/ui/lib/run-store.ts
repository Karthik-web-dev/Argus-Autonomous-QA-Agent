import { create } from "zustand";
import type { RunEvent } from "@/lib/generated/contracts";

export interface RunState {
  runId: string;
  events: RunEvent[];
  status: "idle" | "running" | "complete";
  speed: number;
  playing: boolean;
  currentIndex: number;
}

interface RunActions {
  setEvents(events: RunEvent[]): void;
  start(): void;
  pause(): void;
  resume(): void;
  reset(): void;
  setSpeed(speed: number): void;
  advance(): void;
}

export const useRunStore = create<RunState & RunActions>((set, get) => ({
  runId: "run-golden-001",
  events: [],
  status: "idle",
  speed: 1,
  playing: false,
  currentIndex: 0,
  setEvents: (events) => set({ events, currentIndex: 0, status: "idle", playing: false }),
  start: () => set({ currentIndex: 0, status: "running", playing: true }),
  pause: () => set({ playing: false }),
  resume: () => {
    if (get().status === "running") set({ playing: true });
  },
  reset: () => set({ currentIndex: 0, status: "idle", playing: false }),
  setSpeed: (speed) => set({ speed }),
  advance: () => {
    const currentIndex = Math.min(get().currentIndex + 1, get().events.length);
    const complete = currentIndex >= get().events.length;
    set({ currentIndex, status: complete ? "complete" : "running", playing: !complete });
  },
}));

export const runStore = {
  getState: useRunStore.getState,
  setEvents: (events: RunEvent[]) => useRunStore.getState().setEvents(events),
  start: () => useRunStore.getState().start(),
  pause: () => useRunStore.getState().pause(),
  resume: () => useRunStore.getState().resume(),
  reset: () => useRunStore.getState().reset(),
  setSpeed: (speed: number) => useRunStore.getState().setSpeed(speed),
  advance: () => useRunStore.getState().advance(),
};
