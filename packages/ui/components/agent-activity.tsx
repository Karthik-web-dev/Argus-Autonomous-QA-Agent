import { useMemo } from "react";
import type { RunEvent } from "@/lib/generated/contracts";
import { useRunStore } from "@/lib/run-store";
import { visibleRunEvents } from "@/lib/run-event-summary";

const roles = [
  { id: "explorer", label: "Explorer" },
  { id: "tester", label: "Tester" },
  { id: "oracle", label: "Oracle" },
  { id: "gate", aliases: ["evidence_gate", "evidence-gate"], label: "Evidence Gate" },
  { id: "red_team", aliases: ["red-team"], label: "Red Team" },
  { id: "reporter", label: "Reporter" },
];

function agentName(event: RunEvent): string {
  const fromPayload = event.payload?.agent;
  return (typeof fromPayload === "string" ? fromPayload : event.agent).toLowerCase();
}

export function AgentActivity({ events: suppliedEvents, currentIndex: suppliedIndex }: {
  events?: RunEvent[];
  currentIndex?: number;
} = {}) {
  const storeEvents = useRunStore((state) => state.events);
  const storeIndex = useRunStore((state) => state.currentIndex);
  const events = suppliedEvents ?? storeEvents;
  const currentIndex = suppliedIndex ?? storeIndex;
  const visibleEvents = useMemo(() => visibleRunEvents(events, currentIndex), [events, currentIndex]);
  const activity = useMemo(() => {
    const activeEvents = visibleEvents.filter((event) => event.type === "agent_active");
    const latest = activeEvents.at(-1);
    const latestAgent = latest ? agentName(latest) : null;
    const completed = visibleEvents.some((event) => event.type === "run_completed");
    return roles.map((role) => {
      const names = [role.id, ...(role.aliases ?? [])];
      const wasActive = activeEvents.some((event) => names.includes(agentName(event)));
      const state = completed ? (wasActive ? "done" : "idle")
        : latestAgent && names.includes(latestAgent) ? "active"
          : wasActive ? "done" : "idle";
      return { ...role, state };
    });
  }, [visibleEvents]);

  return (
    <section className="d04-panel d04-agent-activity" aria-label="Agent activity" aria-live="polite">
      <header className="d04-panel-heading"><div><p className="eyebrow">ORCHESTRATION</p><h2>Agent activity</h2></div><span>{activity.filter((role) => role.state === "active").length} / {roles.length} active</span></header>
      <ol className="d04-role-list">
        {activity.map((role) => <li key={role.id} className={`d04-role ${role.state}`}>
          <span className={`d04-state-dot ${role.state}`} aria-hidden="true" />
          <span>{role.label}</span><small>{role.state === "active" ? "Working" : role.state === "done" ? "Complete" : "Queued"}</small>
        </li>)}
      </ol>
    </section>
  );
}
