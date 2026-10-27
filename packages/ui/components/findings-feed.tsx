import { useMemo } from "react";
import type { RunEvent } from "@/lib/generated/contracts";
import { useRunStore } from "@/lib/run-store";
import { summarizeFindings, visibleRunEvents } from "@/lib/run-event-summary";

const stateLabel = { verified: "Verified", rejected: "Rejected", pending: "Pending" } as const;

export function FindingsFeed({ events: suppliedEvents, currentIndex: suppliedIndex }: {
  events?: RunEvent[];
  currentIndex?: number;
} = {}) {
  const storeEvents = useRunStore((state) => state.events);
  const storeIndex = useRunStore((state) => state.currentIndex);
  const events = suppliedEvents ?? storeEvents;
  const currentIndex = suppliedIndex ?? storeIndex;
  const findings = useMemo(() => summarizeFindings(visibleRunEvents(events, currentIndex)), [events, currentIndex]);

  return (
    <section className="d04-panel d04-findings" aria-label="Live findings feed">
      <header className="d04-panel-heading"><div><p className="eyebrow">LIVE RUN</p><h2>Findings</h2></div><span>{findings.length} discovered</span></header>
      {findings.length ? <ol className="d04-finding-list" aria-live="polite">
        {findings.map((finding) => (
          <li className={`d04-finding ${finding.state}`} key={finding.id}>
            <span className={`d04-state-dot ${finding.state}`} aria-hidden="true" />
            <div className="d04-finding-copy"><strong>{finding.oracle.replaceAll("_", " ")}</strong><small>{finding.id}{finding.confidence === null ? "" : ` · ${Math.round(finding.confidence * 100)}% confidence`}</small></div>
            <span className={`d04-state-label ${finding.state}`}>{stateLabel[finding.state]}</span>
            <small className="d04-gate-detail">{finding.verification ?? finding.gate ?? "Awaiting gate"}</small>
          </li>
        ))}
      </ol> : <p className="d04-empty">Findings appear as the run evaluates results.</p>}
      <footer className="d04-legend"><span><i className="verified"/> Verified</span><span><i className="pending"/> Pending</span><span><i className="rejected"/> Rejected</span></footer>
    </section>
  );
}
