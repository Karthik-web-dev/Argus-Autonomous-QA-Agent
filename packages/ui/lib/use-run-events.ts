import { useEffect, useState } from "react";
import type { RunEvent, RunMetrics } from "@/lib/generated/contracts";
import { argusApiUrl } from "@/lib/api";

export type RunEventStreamStatus =
  | "idle"
  | "connecting"
  | "streaming"
  | "completed"
  | "failed"
  | "error";

export interface RunEventStream {
  events: RunEvent[];
  lastEventId: string | null;
  status: RunEventStreamStatus;
  error: string | null;
  metrics: RunMetrics | null;
}

const initialStream: RunEventStream = {
  events: [],
  lastEventId: null,
  status: "idle",
  error: null,
  metrics: null,
};

const eventTypes = new Set<RunEvent["type"]>([
  "run_started",
  "phase_changed",
  "agent_active",
  "action",
  "page_discovered",
  "test_result",
  "finding_created",
  "gate_result",
  "verification_result",
  "bug_reported",
  "coverage_update",
  "scoreboard_update",
  "budget_update",
  "llm_call",
  "error",
  "run_completed",
]);

function apiHeaders(lastEventId?: string | null): Headers {
  const headers = new Headers();
  const token = import.meta.env.VITE_ARGUS_API_TOKEN;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (lastEventId) headers.set("Last-Event-ID", lastEventId);
  return headers;
}

function parseRunEvent(data: string): RunEvent {
  const value: unknown = JSON.parse(data);
  if (
    typeof value !== "object" || value === null ||
    !("id" in value) || typeof value.id !== "string" ||
    !("run_id" in value) || typeof value.run_id !== "string" ||
    !("agent" in value) || typeof value.agent !== "string" ||
    !("correlation_id" in value) || typeof value.correlation_id !== "string" ||
    !("type" in value) || typeof value.type !== "string" ||
    !eventTypes.has(value.type as RunEvent["type"])
  ) {
    throw new Error("The API sent an invalid RunEvent.");
  }
  return value as RunEvent;
}

function waitForReconnect(signal: AbortSignal, delayMs: number): Promise<void> {
  return new Promise((resolve) => {
    const finish = () => {
      signal.removeEventListener("abort", finish);
      resolve();
    };
    const timer = window.setTimeout(finish, delayMs);
    signal.addEventListener("abort", () => {
      window.clearTimeout(timer);
      finish();
    }, { once: true });
  });
}

/** Consume a run's resumable SSE stream and validate each message as F-01 RunEvent. */
export function useRunEvents(runId: string | null): RunEventStream {
  const [stream, setStream] = useState<RunEventStream>(initialStream);

  useEffect(() => {
    if (!runId) {
      setStream(initialStream);
      return;
    }

    const controller = new AbortController();
    const { signal } = controller;
    let lastEventId: string | null = null;
    let reconnectDelay = 500;
    setStream({ ...initialStream, status: "connecting" });

    async function consume(): Promise<void> {
      while (!signal.aborted) {
        let response: Response;
        try {
          response = await fetch(`${argusApiUrl}/runs/${runId}/events`, {
            headers: apiHeaders(lastEventId),
            signal,
          });
        } catch (error) {
          if (signal.aborted) return;
          setStream((current) => ({
            ...current,
            status: "connecting",
            error: error instanceof Error ? error.message : "Event stream interrupted; reconnecting.",
          }));
          await waitForReconnect(signal, reconnectDelay);
          reconnectDelay = Math.min(reconnectDelay * 2, 4000);
          continue;
        }

        if (!response.ok) {
          setStream((current) => ({
            ...current,
            status: "error",
            error: `Unable to read run events (${response.status}).`,
          }));
          return;
        }
        if (!response.body) {
          setStream((current) => ({ ...current, status: "error", error: "The API did not open an event stream." }));
          return;
        }

        setStream((current) => ({ ...current, status: "streaming", error: null }));
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        try {
          while (!signal.aborted) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
            let boundary = buffer.indexOf("\n\n");
            while (boundary >= 0) {
              const frame = buffer.slice(0, boundary);
              buffer = buffer.slice(boundary + 2);
              boundary = buffer.indexOf("\n\n");
              const lines = frame.split("\n");
              const idLine = lines.find((line) => line.startsWith("id:"));
              if (idLine) lastEventId = idLine.slice(3).trim();
              const data = lines.filter((line) => line.startsWith("data:"))
                .map((line) => line.slice(5).trimStart()).join("\n");
              if (!data) continue;
              const event = parseRunEvent(data);
              setStream((current) => ({
                ...current,
                events: [...current.events, event],
                lastEventId,
                status: "streaming",
                error: null,
              }));
            }
          }
        } catch (error) {
          if (signal.aborted) return;
          setStream((current) => ({
            ...current,
            status: "connecting",
            error: error instanceof Error ? `${error.message} Reconnecting…` : "Event stream interrupted; reconnecting.",
          }));
        } finally {
          reader.releaseLock();
        }
        if (signal.aborted) return;

        try {
          const detailResponse = await fetch(`${argusApiUrl}/runs/${runId}`, {
            headers: apiHeaders(),
            signal,
          });
          if (!detailResponse.ok) throw new Error(`Unable to read run details (${detailResponse.status}).`);
          const detail = await detailResponse.json() as {
            status: string;
            error?: string | null;
            summary?: { metrics?: RunMetrics } | null;
          };
          if (detail.status === "completed") {
            setStream((current) => ({ ...current, status: "completed", error: null, metrics: detail.summary?.metrics ?? null }));
            return;
          }
          if (detail.status === "failed") {
            setStream((current) => ({ ...current, status: "failed", error: detail.error ?? "The run failed." }));
            return;
          }
          if (detail.status === "cancelled") {
            setStream((current) => ({ ...current, status: "failed", error: "Run stopped by user." }));
            return;
          }
        } catch (error) {
          if (signal.aborted) return;
          setStream((current) => ({
            ...current,
            status: "connecting",
            error: error instanceof Error ? error.message : "Run status unavailable; reconnecting.",
          }));
        }

        await waitForReconnect(signal, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 4000);
      }
    }

    void consume();
    return () => controller.abort();
  }, [runId]);

  return stream;
}
