import type { RunEvent } from "@/lib/generated/contracts";

export type FindingState = "pending" | "verified" | "rejected";

export interface FindingSummary {
  id: string;
  oracle: string;
  confidence: number | null;
  state: FindingState;
  gate: string | null;
  verification: string | null;
  updatedAt: string | undefined;
}

const payloadString = (event: RunEvent, key: string): string | null => {
  const value = event.payload?.[key];
  return typeof value === "string" ? value : null;
};

const payloadNumber = (event: RunEvent, key: string): number | null => {
  const value = event.payload?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
};

/** Reduce the visible event prefix to one current status per finding. */
export function summarizeFindings(events: RunEvent[]): FindingSummary[] {
  const findings = new Map<string, FindingSummary>();
  for (const event of events) {
    // finding_created carries the Finding itself (key "id"); gate and
    // verification events reference it as "finding_id".
    const id = event.type === "finding_created"
      ? payloadString(event, "id") ?? payloadString(event, "finding_id")
      : payloadString(event, "finding_id");
    if (event.type === "finding_created" && id) {
      const current = findings.get(id);
      findings.set(id, {
        id,
        oracle: payloadString(event, "oracle_id") ?? current?.oracle ?? "Finding",
        confidence: payloadNumber(event, "confidence") ?? current?.confidence ?? null,
        state: current?.state ?? "pending",
        gate: current?.gate ?? null,
        verification: current?.verification ?? null,
        updatedAt: event.ts,
      });
      continue;
    }
    if (!id || (event.type !== "gate_result" && event.type !== "verification_result")) continue;
    const current = findings.get(id) ?? {
      id,
      oracle: "Finding",
      confidence: null,
      state: "pending" as const,
      gate: null,
      verification: null,
      updatedAt: event.ts,
    };
    if (event.type === "gate_result") {
      const verdict = payloadString(event, "verdict")?.toUpperCase() ?? null;
      current.gate = verdict;
      if (verdict === "REJECTED") current.state = "rejected";
    } else {
      const verdict = payloadString(event, "verdict")?.toUpperCase() ?? null;
      current.verification = verdict;
      if (verdict === "CONFIRMED") current.state = "verified";
      if (verdict === "REFUTED") current.state = "rejected";
    }
    current.updatedAt = event.ts;
    findings.set(id, current);
  }
  return [...findings.values()].reverse();
}

export interface ScoreboardSummary {
  found: number;
  total: number | null;
  falsePositives: number;
  inProgress: number;
  coverage: number | null;
}

/** Prefer PR-07 scoreboard events as the source of scoring truth. */
export function summarizeScoreboard(events: RunEvent[]): ScoreboardSummary {
  const findings = summarizeFindings(events);
  const scoreboardEvent = [...events].reverse().find((event) => event.type === "scoreboard_update");
  const coverageEvent = [...events].reverse().find((event) => event.type === "coverage_update");
  const truePositive = scoreboardEvent ? payloadNumber(scoreboardEvent, "true_positive") : null;
  const recall = scoreboardEvent ? payloadNumber(scoreboardEvent, "recall") : null;
  const falsePositive = scoreboardEvent ? payloadNumber(scoreboardEvent, "false_positive") : null;
  const covered = coverageEvent ? payloadNumber(coverageEvent, "covered") : null;
  const totalChecks = coverageEvent ? payloadNumber(coverageEvent, "total") : null;

  return {
    found: truePositive ?? findings.filter((item) => item.state === "verified").length,
    total: truePositive !== null && recall !== null && recall > 0
      ? Math.round(truePositive / recall)
      : null,
    falsePositives: falsePositive ?? findings.filter((item) => item.state === "rejected").length,
    inProgress: findings.filter((item) => item.state === "pending").length,
    coverage: covered !== null && totalChecks !== null && totalChecks > 0
      ? Math.round((covered / totalChecks) * 100)
      : null,
  };
}

export const visibleRunEvents = (events: RunEvent[], currentIndex: number) => events.slice(0, currentIndex);
