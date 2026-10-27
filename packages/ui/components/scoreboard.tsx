import { useMemo } from "react";
import type { RunEvent } from "@/lib/generated/contracts";
import { useRunStore } from "@/lib/run-store";
import { summarizeScoreboard, visibleRunEvents } from "@/lib/run-event-summary";

/** Fixture/live scoreboard. Values are reduced from events, with PR-07 score events authoritative. */
export function Scoreboard({ events: suppliedEvents, currentIndex: suppliedIndex }: {
  events?: RunEvent[];
  currentIndex?: number;
} = {}) {
  const storeEvents = useRunStore((state) => state.events);
  const storeIndex = useRunStore((state) => state.currentIndex);
  const events = suppliedEvents ?? storeEvents;
  const currentIndex = suppliedIndex ?? storeIndex;
  const summary = useMemo(() => summarizeScoreboard(visibleRunEvents(events, currentIndex)), [events, currentIndex]);
  const found = summary.total === null ? `${summary.found}/—` : `${summary.found}/${summary.total}`;
  const coverage = summary.coverage === null ? "—" : `${summary.coverage}%`;

  return (
    <section className="d04-scoreboard" aria-label="Benchmark scoreboard" aria-live="polite">
      <article className="d04-score-primary"><span>BUGS FOUND</span><strong>{found}</strong></article>
      <article><span>FALSE POSITIVES</span><strong>{summary.falsePositives}</strong></article>
      <article><span>IN PROGRESS</span><strong>{summary.inProgress}</strong></article>
      <article><span>COVERAGE</span><strong>{coverage}</strong></article>
    </section>
  );
}
