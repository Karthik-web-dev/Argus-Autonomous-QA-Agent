import { useEffect, useState } from "react";
import type { CreateRunRequest, RunMetrics } from "@/lib/generated/contracts";
import { argusApiUrl } from "@/lib/api";
import { useRunEvents } from "@/lib/use-run-events";
import { LiveView } from "@/components/live-view";
import { Scoreboard } from "@/components/scoreboard";
import { FindingsFeed } from "@/components/findings-feed";
import { AgentActivity } from "@/components/agent-activity";
import "./styles/d04.css";

interface AcceptedRun {
  run_id: string;
  events_url: string;
}

export default function HomePage() {
  const [url, setUrl] = useState("");
  const [spec, setSpec] = useState("");
  const [status, setStatus] = useState("Runs are executed by the local Argus API.");
  const [metrics, setMetrics] = useState<RunMetrics | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const stream = useRunEvents(activeRunId);

  useEffect(() => {
    if (!activeRunId) return;
    if (stream.status === "completed") {
      setMetrics(stream.metrics);
      setStatus("Run complete. Evidence was saved by the agent.");
    } else if (stream.status === "failed" || stream.status === "error") {
      setStatus(stream.error ?? "Unable to follow the run event stream.");
    } else if (stream.events.length > 0) {
      const latest = stream.events[stream.events.length - 1];
      setStatus(`Run ${activeRunId.slice(0, 8)} · ${latest.type.replaceAll("_", " ")}`);
    } else if (stream.status === "connecting") {
      setStatus(stream.error ?? "Connecting to the run event stream…");
    }
  }, [activeRunId, stream]);

  async function startRun(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setStatus("Starting browser run…"); setMetrics(null); setActiveRunId(null);
    try {
      const request: CreateRunRequest = { url, spec };
      const headers = new Headers();
      if (import.meta.env.VITE_ARGUS_API_TOKEN) {
        headers.set("Authorization", `Bearer ${import.meta.env.VITE_ARGUS_API_TOKEN}`);
      }
      headers.set("Content-Type", "application/json");
      const response = await fetch(`${argusApiUrl}/runs`, {
        method: "POST", headers, body: JSON.stringify(request),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Run failed");
      const run = data as AcceptedRun;
      setStatus(`Run ${run.run_id.slice(0, 8)} queued. Connecting to its event stream…`);
      setActiveRunId(run.run_id);
    } catch (error) { setStatus(error instanceof Error ? error.message : "Unable to reach Argus API."); }
  }
  return <main className="shell">
    <header className="topbar"><a className="brand" href="/">ARGUS<span>◆</span></a><span className="eyebrow">AUTONOMOUS QA ENGINEER</span></header>
    <section><p className="eyebrow">Evidence over assertion</p><h1>Ship with confidence.<br/>See what your users see.</h1>
      <p className="lede">Argus explores web applications, runs repeatable browser journeys, and captures the evidence developers need to reproduce failures.</p></section>
    <section className="grid">
      <div className="panel"><h2>Start a QA run</h2><form className="form" onSubmit={startRun}>
        <label>Application URL<input required type="url" placeholder="http://localhost:3100" value={url} onChange={e => setUrl(e.target.value)}/></label>
        <label>What should the app do?<textarea required placeholder="A user can sign in and publish an article…" value={spec} onChange={e => setSpec(e.target.value)}/></label>
        <button className="button" type="submit">Explore application ↗</button><p className="status" aria-live="polite">{status}</p>
      </form></div>
      {activeRunId ? <div className="panel"><h2>Live browser</h2><LiveView runId={activeRunId}/>
        <Scoreboard events={stream.events} currentIndex={stream.events.length}/>
        <div className="d04-panels"><FindingsFeed events={stream.events} currentIndex={stream.events.length}/><AgentActivity events={stream.events} currentIndex={stream.events.length}/></div>
        <p className="status" aria-live="polite">{status}</p>
      </div> : <div className="panel"><h2>Run scoreboard</h2><div className="stats">
        <div className="stat"><strong>{metrics?.journeys ?? "—"}</strong><small>Journeys</small></div>
        <div className="stat"><strong>{metrics?.passed ?? "—"}</strong><small>Passed</small></div>
        <div className="stat"><strong>{metrics?.failed ?? "—"}</strong><small>Failed</small></div>
        <div className="stat"><strong>—</strong><small>Verified bugs</small></div>
      </div><ul className="list"><li>Semantic browser inventory</li><li>Console and network evidence</li><li>Reproducible journey artifacts</li></ul></div>}
    </section>
    <footer className="eyebrow" style={{ marginTop: 28 }}>LOCAL DEVELOPMENT BUILD · CONFIGURE A MODEL ROUTE FOR LIVE REASONING</footer>
  </main>;
}
