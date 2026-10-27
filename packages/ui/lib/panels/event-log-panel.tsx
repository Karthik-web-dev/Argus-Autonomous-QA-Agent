import type { RunEvent } from "@/lib/generated/contracts";
import { registerPanel, type PanelProps } from "./registry";
import { useRunStore } from "@/lib/run-store";

export function EventLogPanel({ runId }: PanelProps) {
  const events = useRunStore((state) => state.events);
  const currentIndex = useRunStore((state) => state.currentIndex);
  const visibleEvents = events.slice(0, currentIndex);
  return (
    <section className="replay-event-panel" aria-label="Run event activity">
      <header><div><p className="eyebrow">FIXTURE EVENT STREAM</p><h2>Run activity</h2><small>{runId}</small></div><span>{events.length} events</span></header>
      <ol className="replay-event-list" aria-live="polite">
        {visibleEvents.map((event: RunEvent) => (
          <li key={event.id} className={`event-${event.type}`}>
            <time dateTime={event.ts}>{event.ts ? new Date(event.ts).toLocaleTimeString() : "--:--:--"}</time>
            <span className="replay-event-type">{event.type.replaceAll("_", " ")}</span>
            <span className="replay-event-agent">{event.agent}</span>
            <p>{eventSummary(event)}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

registerPanel({ id: "activity", title: "Run activity", component: EventLogPanel });

function eventSummary(event: RunEvent): string {
  const payload = event.payload ?? {};
  const primary = payload.message ?? payload.phase ?? payload.status ?? payload.url ?? payload.finding_id;
  if (typeof primary === "string") return primary;
  if (event.type === "run_started" && typeof payload.spec === "string") return payload.spec;
  if (event.type === "run_completed" && typeof payload.finding_count === "number") {
    return `${payload.finding_count} finding(s) recorded`;
  }
  return "Event recorded";
}
