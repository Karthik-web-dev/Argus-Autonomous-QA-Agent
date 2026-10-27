import { useEffect, useMemo, useState } from "react";
import type { RunEvent } from "@/lib/generated/contracts";
import "@/lib/panels";
import { getPanel, getPanels } from "@/lib/panels/registry";
import { runStore, useRunStore } from "@/lib/run-store";
import { LiveView } from "@/components/live-view";
import { Scoreboard } from "@/components/scoreboard";
import { FindingsFeed } from "@/components/findings-feed";
import { AgentActivity } from "@/components/agent-activity";
import fixtureText from "../../../fixtures/run_events.ndjson?raw";
import "./styles/replay.css";
import "./styles/d04.css";

interface FixtureLoadState { error: string | null; loaded: boolean }

export default function ReplayPage() {
  const [loadState, setLoadState] = useState<FixtureLoadState>({ error: null, loaded: false });
  const [cursorDemoRun, setCursorDemoRun] = useState(0);
  const runId = useRunStore((state) => state.runId);
  const status = useRunStore((state) => state.status);
  const speed = useRunStore((state) => state.speed);
  const playing = useRunStore((state) => state.playing);
  const currentIndex = useRunStore((state) => state.currentIndex);
  const eventCount = useRunStore((state) => state.events.length);
  const panels = useMemo(() => getPanels(), []);
  const activePanel = getPanel("activity");

  useEffect(() => {
    try {
      const events = fixtureText.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line) as RunEvent);
      runStore.setEvents(events);
      runStore.start();
      setLoadState({ error: null, loaded: true });
    } catch (error: unknown) {
      setLoadState({ error: error instanceof Error ? error.message : "Unable to load fixture events.", loaded: true });
    }
  }, []);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setTimeout(() => runStore.advance(), 650 / speed);
    return () => window.clearTimeout(timer);
  }, [playing, currentIndex, speed]);

  return (
    <main className="replay-shell">
      <header className="replay-topbar">
        <a className="replay-brand" href="/">ARGUS <span>◆</span></a>
        <div className="replay-run-context"><span>Fixture replay</span><b>/</b><code>{runId}</code></div>
        <span className={`replay-status ${status}`}>{status === "idle" ? "READY" : status.toUpperCase()}</span>
        <a className="replay-back" href="/dashboard">Dashboard ↗</a>
      </header>
      <div className="replay-layout">
        <aside className="replay-rail">
          <p className="eyebrow">PANELS</p>
          <nav aria-label="Run panels">
            {panels.map((panel) => <a key={panel.id} className="replay-panel-link active" href={`#${panel.id}`}>{panel.title}</a>)}
          </nav>
          <div className="replay-fixture-note"><span className="replay-dot"/><div><strong>Golden fixture</strong><small>Read from run_events.ndjson</small></div></div>
        </aside>
        <section className="replay-content">
          <div className="replay-heading"><div><p className="eyebrow">STAGE 2 · PANEL SCAFFOLD</p><h1>Run workspace</h1><p>Replay a recorded Argus run and watch panels consume the typed event stream.</p></div><span className="replay-event-count">{currentIndex} <i>/</i> {eventCount} events</span></div>
          <section className="replay-overview" aria-label="Run overview">
            <article><span>Run ID</span><strong>{runId}</strong></article>
            <article><span>Target</span><strong>{targetUrl(runStore.getState().events[0])}</strong></article>
            <article><span>Replay status</span><strong>{status === "complete" ? "Completed" : status === "running" ? "In progress" : "Ready"}</strong></article>
          </section>
          <Scoreboard />
          <LiveView runId={runId} fixtureSrc="/fixtures/fixture-browser-frame.svg" demoCursorRun={cursorDemoRun} />
          <div className="d04-panels">
            <FindingsFeed />
            <AgentActivity />
          </div>
          <section className="replay-controls" aria-label="Fixture replay controls">
            <button onClick={() => setCursorDemoRun((run) => run + 1)}>↗ Play 5s cursor demo</button>
            {!playing ? <button className="replay-primary" onClick={() => status === "idle" || status === "complete" ? runStore.start() : runStore.resume()} disabled={!loadState.loaded || !!loadState.error}>▶ {status === "complete" ? "Replay again" : status === "running" ? "Resume" : "Start replay"}</button> : <button className="replay-primary" onClick={() => runStore.pause()}>Ⅱ Pause</button>}
            <button onClick={() => runStore.reset()} disabled={!eventCount}>↺ Reset</button>
            <label>Playback speed<select value={speed} onChange={(event) => runStore.setSpeed(Number(event.target.value))}><option value={0.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option></select></label>
            <span className="replay-control-hint">{loadState.error ?? (loadState.loaded ? "Events are replayed locally; no browser or API run is started." : "Loading golden fixture…")}</span>
          </section>
          {activePanel && <div id="activity"><activePanel.component runId={runId}/></div>}
        </section>
      </div>
    </main>
  );
}

function targetUrl(firstEvent: RunEvent | undefined): string {
  const url = firstEvent?.payload?.target_url;
  return typeof url === "string" ? url : "—";
}
