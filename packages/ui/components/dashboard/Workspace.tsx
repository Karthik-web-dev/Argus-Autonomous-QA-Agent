
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { activityRoles, demoFindings, evidenceFiles, type Finding } from "@/lib/dashboard-content";
import { argusApiUrl } from "@/lib/api";
import { useRunEvents } from "@/lib/use-run-events";
import { LiveView } from "@/components/live-view";

interface DashboardRun { id: string; name: string; score: string; time: string; status: string; coverage: string; url: string; spec: string }
interface ApiRun { run_id: string; target_url: string; spec: string; status: string; created_at: string }
interface ApiBug { id: string; severity: "P0" | Finding["severity"]; title: string; expected: string; actual: string; steps?: Array<{action: string; locator?: string; value?: string}>; evidence?: {network?: Array<{url: string; method?: string; status?: number | null}>; console?: Array<{message: string}>; reproduction?: {attempts: number; successes: number}}; verified_by?: "red_team" | "none" }
interface ApiTestCase { id: string; journey: string; category?: string }
interface ApiTestResult { test_id: string; verdict: "PASS" | "FAIL" | "INCONCLUSIVE"; duration_ms: number }
interface ApiArtifact { path: string; url: string }
interface ApiRunDetail extends ApiRun { artifacts?: ApiArtifact[]; summary?: { metrics?: Record<string, number>; test_cases?: ApiTestCase[]; test_results?: ApiTestResult[]; bugs_found?: ApiBug[]; findings?: ApiBug[]; coverage?: Record<string, number> } | null }
const emptyFinding: Finding = { id: "none", severity: "P3", title: "No findings yet", status: "pending", time: "—", detail: "Findings from this run will appear here.", steps: [], expected: "—", actual: "—", network: { method: "—", path: "—", status: "—", duration: "—" }, console: "—" };

function apiHeaders(json = false): Headers {
  const headers = new Headers();
  if (json) headers.set("Content-Type", "application/json");
  const token = import.meta.env.VITE_ARGUS_API_TOKEN;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

function asRun(run: ApiRun): DashboardRun {
  return { id: run.run_id, name: new URL(run.target_url).hostname, score: "—", time: new Date(run.created_at).toLocaleString(), status: run.status, coverage: "—", url: run.target_url, spec: run.spec };
}

function enrichRun(run: ApiRunDetail): DashboardRun {
  const coverage = Object.values(run.summary?.coverage ?? {});
  const coveragePercent = coverage.length ? Math.round(coverage.reduce((sum, value) => sum + (value <= 1 ? value * 100 : value), 0) / coverage.length) : null;
  const findings = run.summary?.bugs_found?.length ?? 0;
  const journeys = run.summary?.test_cases?.length ?? 0;
  return { ...asRun(run), score: journeys ? `${findings}/${journeys}` : String(findings), coverage: coveragePercent == null ? "—" : `${coveragePercent}%` };
}

interface LiveFindingPayload { id: string; oracle_id?: string; expected?: string; actual?: string; steps?: ApiBug["steps"] }

/** Severity for an unreported finding, inferred from the oracle that raised it. */
function liveSeverity(payload: LiveFindingPayload): Finding["severity"] {
  if (payload.oracle_id === "http-status") return /HTTP 5\d\d/.test(payload.actual ?? "") ? "P1" : "P2";
  return payload.oracle_id === "spec-assertion" ? "P2" : "P3";
}

/** Map a streamed finding_created payload (a Finding, not yet a BugReport) for display. */
function asLiveFinding(payload: LiveFindingPayload, gate: string | undefined, time: string): Finding {
  const oracle = payload.oracle_id ?? "finding";
  const actual = payload.actual || "See evidence";
  return {
    id: payload.id, severity: liveSeverity(payload), title: actual.slice(0, 90),
    status: gate === "ACCEPTED" ? "verified" : gate === "REJECTED" || gate === "FLAKY" ? "rejected" : "pending",
    time, detail: actual, verifiedBy: "none",
    repro: gate === "ACCEPTED" ? "Reproduced by the Evidence Gate" : gate ? `Evidence Gate: ${gate.toLowerCase()}` : "Waiting for the Evidence Gate",
    steps: (payload.steps ?? []).map((step) => `${step.action}${step.locator ? ` ${step.locator}` : ""}${step.value ? `: ${step.value}` : ""}`),
    expected: payload.expected || "—", actual,
    network: { method: "—", path: oracle, status: "—", duration: "—" },
    console: oracle === "console-error" ? actual : "",
  };
}

function asFinding(bug: ApiBug): Finding {
  const network = bug.evidence?.network?.[0];
  const reproduction = bug.evidence?.reproduction;
  return { id: bug.id, severity: bug.severity, title: bug.title, status: "verified", time: "Live run",
    verifiedBy: bug.verified_by ?? "none",
    repro: reproduction?.attempts ? `Reproduced ${reproduction.successes}/${reproduction.attempts} in fresh contexts` : "Accepted by the Evidence Gate", detail: bug.actual || bug.title,
    steps: (bug.steps ?? []).map((step) => `${step.action}${step.locator ? ` ${step.locator}` : ""}${step.value ? `: ${step.value}` : ""}`),
    expected: bug.expected, actual: bug.actual, network: { method: network?.method ?? "—", path: network ? new URL(network.url, window.location.href).pathname : "No network evidence", status: network?.status == null ? "—" : String(network.status), duration: "—" }, console: bug.evidence?.console?.map((item) => item.message).join("\n") || "No console errors recorded." };
}

function BackendRunOutput({ detail }: { detail: ApiRunDetail | null }) {
  const coverage = Object.entries(detail?.summary?.coverage ?? {});
  const cases = detail?.summary?.test_cases ?? [];
  const results = detail?.summary?.test_results ?? [];
  const resultById = new Map(results.map((result) => [result.test_id, result]));
  const artifacts = detail?.artifacts ?? [];
  return <div className="workspace-bottom">
    <section className="coverage-panel"><div className="panel-heading"><div><span className="panel-icon coverage-icon">⌘</span><strong>Run coverage</strong><span className="sample-tag">Backend data</span></div></div><div className="coverage-legend backend-coverage">{coverage.length ? coverage.map(([name, value]) => <p key={name}><i className="legend-dot done"/>{name}<b>{Math.round((value <= 1 ? value * 100 : value))}%</b></p>) : <p>Coverage will appear when the run reports it.</p>}</div></section>
    <section className="tests-panel"><div className="panel-heading"><div><span className="panel-icon tests-icon">⌘</span><strong>Tests & artifacts</strong><span className="sample-tag">Backend data</span></div></div><div className="tests-body"><div className="test-file-list">{cases.length ? cases.map((testCase) => { const result = resultById.get(testCase.id); return <div className="test-file" key={testCase.id}><span className="test-kind">{testCase.category ?? "Test"}</span><strong>{testCase.journey}</strong><span className={`test-result ${(result?.verdict ?? "INCONCLUSIVE").toLowerCase()}`}>{result?.verdict ?? "PENDING"}</span></div>; }) : <p>Generated tests will appear here when available.</p>}</div><div className="tests-summary"><div><span>Tests</span><strong>{cases.length}</strong></div><div><span>Run artifacts</span><strong>{artifacts.length}</strong></div>{artifacts.slice(0, 4).map((artifact) => <a key={artifact.path} href={`${argusApiUrl}${artifact.url}`} target="_blank" rel="noreferrer">{artifact.path.split("/").pop()} ↗</a>)}</div></div></section>
  </div>;
}

type Screen = "history" | "entry" | "parsing" | "running" | "results";
type Divider = "vertical" | "horizontal";

function StatusDot({ tone = "green" }: { tone?: "green" | "amber" | "gray" }) { return <i className={`dash-dot ${tone}`} aria-hidden="true" />; }

function Metric({ label, value, caption, tone = "" }: { label: string; value: string; caption?: string; tone?: string }) {
  return <article className="metric-card"><span>{label}</span><strong className={tone}>{value}</strong>{caption && <small>{caption}</small>}</article>;
}

function FindingRow({ finding, active, onClick }: { finding: Finding; active: boolean; onClick: () => void }) {
  const state = finding.status === "verified" ? "Verified" : finding.status === "pending" ? "Verifying" : "Rejected";
  return <button className={`finding-row ${active ? "selected" : ""}`} onClick={onClick}>
    <span className={`severity ${finding.severity.toLowerCase()}`}>{finding.severity}</span>
    <span className="finding-copy"><strong>{finding.title}</strong><small><span className={`finding-state ${finding.status}`}>{state}</span><span>{finding.time}</span></small></span>
    <span className="finding-chevron" aria-hidden="true">›</span>
  </button>;
}

function Brand() { return <a className="dashboard-brand" href="/" aria-label="Argus home"><span className="brand-symbol">A</span><span>ARGUS</span></a>; }

export function Workspace() {
  const [screen, setScreen] = useState<Screen>("history");
  const [runs, setRuns] = useState<DashboardRun[]>([]);
  const [runMenu, setRunMenu] = useState<{ id: string; confirming: boolean } | null>(null);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [selectedRun, setSelectedRun] = useState<DashboardRun | null>(null);
  const [selectedFinding, setSelectedFinding] = useState<Finding>(emptyFinding);
  const [url, setUrl] = useState("");
  const [spec, setSpec] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [fullScreen, setFullScreen] = useState(false);
  const [scoreOpen, setScoreOpen] = useState(false);
  const [browserSplit, setBrowserSplit] = useState(60);
  const [topSplit, setTopSplit] = useState(70);
  const [dragging, setDragging] = useState<Divider | null>(null);
  const [copied, setCopied] = useState(false);
  const [apiError, setApiError] = useState("");
  const [runMode, setRunMode] = useState<"real" | "fixture">("real");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<ApiRunDetail | null>(null);
  const stream = useRunEvents(activeRunId);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const splitRef = useRef<HTMLDivElement>(null);
  const running = screen === "running";
  // Findings streamed during the run, updated with Evidence Gate verdicts as they arrive.
  const liveFindings = useMemo(() => {
    const gates = new Map<string, string>();
    const created = new Map<string, { payload: LiveFindingPayload; ts?: string }>();
    for (const event of stream.events) {
      const payload = event.payload ?? {};
      if (event.type === "finding_created" && typeof payload.id === "string") {
        created.set(payload.id, { payload: payload as unknown as LiveFindingPayload, ts: event.ts });
      } else if (event.type === "gate_result" && typeof payload.finding_id === "string" && typeof payload.verdict === "string") {
        gates.set(payload.finding_id, payload.verdict.toUpperCase());
      }
    }
    return [...created.values()].reverse().map(({ payload, ts }) =>
      asLiveFinding(payload, gates.get(payload.id), ts ? new Date(ts).toLocaleTimeString() : "Live run"));
  }, [stream.events]);
  const visibleFindings = useMemo(() => {
    // Filed bug reports win; otherwise show the streamed findings so a run is never blank.
    const bugs = runDetail?.summary?.bugs_found ?? [];
    if (bugs.length) return bugs.map(asFinding);
    if (liveFindings.length) return liveFindings;
    return activeRunId ? [] : demoFindings;
  }, [runDetail, activeRunId, liveFindings]);
  const findingArtifacts = selectedFinding.id === "f-01" ? evidenceFiles : [`${selectedFinding.id}-replay.png`, `${selectedFinding.id}-network.json`, `${selectedFinding.id}-console.txt`, `${selectedFinding.id}-repro.spec.ts`];

  const refreshRuns = useCallback(async () => {
    try {
      const response = await fetch(`${argusApiUrl}/runs?limit=50`, { headers: apiHeaders() });
      if (!response.ok) throw new Error(`Run history unavailable (${response.status}).`);
      const data = await response.json() as { items: ApiRun[] };
      setRuns(data.items.map(asRun));
      setApiError("");
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Unable to reach Argus API.");
    }
  }, []);

  useEffect(() => { void refreshRuns(); }, [refreshRuns]);

  useEffect(() => {
    if (!activeRunId) return;
    const load = async () => {
      try {
        const response = await fetch(`${argusApiUrl}/runs/${encodeURIComponent(activeRunId)}`, { headers: apiHeaders() });
        if (response.ok) {
          const detail = await response.json() as ApiRunDetail;
          setRunDetail(detail);
          const run = enrichRun(detail);
          setSelectedRun(run);
          setRuns((current) => current.map((item) => item.id === run.id ? run : item));
        }
      } catch { /* event stream below remains the run status source */ }
    };
    void load();
    const interval = window.setInterval(() => { void load(); }, 2500);
    return () => window.clearInterval(interval);
  }, [activeRunId, stream.status]);

  useEffect(() => {
    if (runDetail?.status === "completed" || runDetail?.status === "failed" || runDetail?.status === "cancelled") {
      setStopping(false);
      setScreen("results");
      void refreshRuns();
    }
  }, [runDetail?.status, refreshRuns]);

  useEffect(() => {
    if (activeRunId && selectedFinding.id === "none" && visibleFindings.length) setSelectedFinding(visibleFindings[0]);
  }, [activeRunId, selectedFinding.id, visibleFindings]);

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  useEffect(() => {
    if (!dragging) return;
    const move = (event: PointerEvent) => {
      if (dragging === "vertical" && splitRef.current) {
        const rect = splitRef.current.getBoundingClientRect();
        setBrowserSplit(Math.max(30, Math.min(85, ((event.clientX - rect.left) / rect.width) * 100)));
      }
      if (dragging === "horizontal" && workspaceRef.current) {
        const rect = workspaceRef.current.getBoundingClientRect();
        setTopSplit(Math.max(42, Math.min(82, ((event.clientY - rect.top) / rect.height) * 100)));
      }
    };
    const end = () => setDragging(null);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end, { once: true });
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", end); };
  }, [dragging]);

  async function startRun(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setApiError(""); setElapsed(0); setRunDetail(null); setActiveRunId(null); setSelectedFinding(emptyFinding);
    setScreen("parsing");
    try {
      const response = await fetch(`${argusApiUrl}/runs?mode=${runMode}`, { method: "POST", headers: apiHeaders(true), body: JSON.stringify({ url, spec }) });
      const data = await response.json() as { run_id?: string; detail?: string };
      if (!response.ok || !data.run_id) throw new Error(data.detail ?? `Unable to start run (${response.status}).`);
      setActiveRunId(data.run_id);
      const run: DashboardRun = { id: data.run_id, name: new URL(url).hostname, score: "—", time: "just now", status: "running", coverage: "—", url, spec };
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      setSelectedRun(run); setScreen("running");
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Unable to reach Argus API.");
      setScreen("entry");
    }
  }

  useEffect(() => {
    if (!runMenu) return;
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent && event.key !== "Escape") return;
      if (event.target instanceof Element && event.target.closest(".run-menu, .run-more")) return;
      setRunMenu(null);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [runMenu]);

  async function stopRun() {
    if (!activeRunId || stopping) return;
    setStopping(true);
    try {
      const response = await fetch(`${argusApiUrl}/runs/${encodeURIComponent(activeRunId)}/cancel`, { method: "POST", headers: apiHeaders() });
      if (!response.ok) throw new Error(`Could not stop the run (${response.status}).`);
    } catch (error) {
      setStopping(false);
      setApiError(error instanceof Error ? error.message : "Unable to stop this run.");
    }
  }

  async function deleteRun(run: DashboardRun) {
    setDeletingRunId(run.id);
    try {
      const response = await fetch(`${argusApiUrl}/runs/${encodeURIComponent(run.id)}`, { method: "DELETE", headers: apiHeaders() });
      if (!response.ok && response.status !== 404) throw new Error(`Could not delete run (${response.status}).`);
      setRuns((current) => current.filter((item) => item.id !== run.id));
      if (selectedRun?.id === run.id || activeRunId === run.id) {
        setSelectedRun(null);
        setActiveRunId(null);
        setRunDetail(null);
        setScreen("history");
      }
      setRunMenu(null);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Unable to delete this run.");
    } finally {
      setDeletingRunId(null);
    }
  }

  async function chooseRun(run: DashboardRun) {
    setSelectedRun(run);
    setActiveRunId(run.id);
    try {
      const response = await fetch(`${argusApiUrl}/runs/${encodeURIComponent(run.id)}`, { headers: apiHeaders() });
      if (!response.ok) throw new Error(`Run details unavailable (${response.status}).`);
      const detail = await response.json() as ApiRunDetail;
      setRunDetail(detail);
      setSelectedRun(enrichRun(detail));
      const bugs = detail.summary?.bugs_found ?? detail.summary?.findings ?? [];
      setSelectedFinding(bugs.length ? asFinding(bugs[0]) : emptyFinding);
      setScreen(detail.status === "running" || detail.status === "queued" ? "running" : "results");
    } catch (error) { setApiError(error instanceof Error ? error.message : "Unable to load this run."); }
  }

  function handleSplitKey(event: React.KeyboardEvent<HTMLDivElement>, axis: Divider) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    const delta = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -3 : 3;
    if (axis === "vertical") setBrowserSplit((value) => Math.max(30, Math.min(85, value + delta)));
    else setTopSplit((value) => Math.max(42, Math.min(82, value + delta)));
  }

  const [downloading, setDownloading] = useState(false);

  async function downloadReport() {
    if (!activeRunId) { void copyReport(); return; }
    setDownloading(true);
    try {
      const response = await fetch(`${argusApiUrl}/runs/${encodeURIComponent(activeRunId)}/report.pdf`, { headers: apiHeaders() });
      if (!response.ok) throw new Error(response.status === 409 ? "The bug report is not ready yet." : `Could not download the report (${response.status}).`);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `argus-bug-report-${activeRunId.slice(0, 8)}.pdf`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Unable to download the report.");
    } finally {
      setDownloading(false);
    }
  }

  async function copyReport() {
    const report = `${selectedFinding.severity} ${selectedFinding.title}\n\n${selectedFinding.detail}\n\nExpected: ${selectedFinding.expected}\nActual: ${selectedFinding.actual}`;
    try { await navigator.clipboard.writeText(report); setCopied(true); window.setTimeout(() => setCopied(false), 1800); }
    catch { setCopied(false); }
  }

  const isLive = screen === "running";
  const isResults = screen === "results";

  return <main className={`dashboard-shell ${fullScreen ? "dashboard-fullscreen" : ""}`}>
    <header className="dashboard-topbar"><Brand/><div className="topbar-run-context">
      {screen === "history" && <span className="topbar-muted">Workspace <b>/</b> Runs</span>}
      {screen === "entry" && <span className="topbar-muted">Workspace <b>/</b> New run</span>}
      {(isLive || isResults) && <><button className="spec-toggle" onClick={() => setScreen("entry")} title="Edit run specification">{isLive ? "Spec: " + (selectedRun?.spec || spec).slice(0, 36) : `${selectedRun?.name ?? "Run"} · ${selectedRun?.time ?? ""}`} <span>⌄</span></button><span className={`run-state ${isLive ? "is-running" : "is-complete"}`}><StatusDot tone={isLive ? "amber" : "green"}/>{isLive ? stream.status === "failed" ? (stream.error === "Run stopped by user." ? "STOPPED" : "FAILED") : stream.status === "completed" ? "COMPLETE" : "RUNNING" : "COMPLETE"}</span><span className="run-timer">{isLive ? `00:${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}` : ""}</span></>}
    </div><div className="topbar-actions">
      {isLive && activeRunId && stream.status !== "completed" && stream.status !== "failed" && <button className="button button-stop button-small" onClick={() => void stopRun()} disabled={stopping} title="Stop the run at its next checkpoint">{stopping ? "Stopping…" : "■ Stop run"}</button>}
      {isLive && <button className="button button-outline button-small" onClick={() => { setFullScreen(false); setScreen("results"); }}>View report</button>}
      {isResults && <><button className="button button-outline button-small" onClick={() => setScreen("entry")}>↻ Re-run</button><button className="button button-cream button-small" onClick={() => void downloadReport()} disabled={downloading}>{activeRunId ? (downloading ? "Preparing PDF…" : "↓ Bug report (PDF)") : `↓ ${copied ? "Copied" : "Export"}`}</button></>}
      <a className="topbar-home" href="/">Landing page <span>↗</span></a>
    </div></header>

    <aside className="dashboard-rail">
      <button className={`new-run-button ${screen === "entry" ? "active" : ""}`} onClick={() => setScreen("entry")}><span>＋</span> New Run <kbd>N</kbd></button>
      <div className="rail-label">Recent runs <span>{runs.length}</span></div>
      <div className="run-list">{runs.map((run) => {
        const menuOpen = runMenu?.id === run.id;
        return <div key={run.id} className={`run-list-row ${menuOpen ? "menu-open" : ""}`}>
          <button className={`run-list-item ${selectedRun?.id === run.id && (isResults || isLive) ? "active" : ""}`} onClick={() => void chooseRun(run)}><span className="run-item-top"><StatusDot tone={run.status === "failed" ? "amber" : "green"}/><strong>{run.name}</strong></span><span className="run-item-score">{run.status}</span><span className="run-item-time">{run.time}</span></button>
          <button className="run-more" aria-label={`Options for ${run.name}`} aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setRunMenu(menuOpen ? null : { id: run.id, confirming: false })}>···</button>
          {menuOpen && <div className="run-menu" role="menu">
            {runMenu.confirming
              ? <><p>Delete this run and its artifacts?</p><div className="run-menu-actions"><button onClick={() => setRunMenu({ id: run.id, confirming: false })}>Cancel</button><button className="danger" disabled={deletingRunId === run.id} onClick={() => void deleteRun(run)}>{deletingRunId === run.id ? "Deleting…" : "Delete"}</button></div></>
              : <button role="menuitem" className="danger" onClick={() => setRunMenu({ id: run.id, confirming: true })}>Delete run</button>}
          </div>}
        </div>;
      })}</div>
      <div className="rail-bottom"><span className="avatar-small">P</span><span><strong>Parth</strong><small>Personal workspace</small></span><button aria-label="Workspace settings">⌄</button></div>
    </aside>

    <section className="dashboard-main">
      {screen === "history" && <div className="history-empty"><div className="empty-mark">◉</div><p className="eyebrow">YOUR QA RUNS</p><h1>{apiError ? "Connect to the Argus API" : runs.length ? "Select a run to view" : "No runs yet"}<br/>{!apiError && runs.length ? "its evidence" : ""}</h1><p className="empty-description">{apiError || (runs.length ? "Open a previous report from the sidebar, or start a new run to explore an app and find issues worth fixing." : "Start a run and your real backend results will appear here.")}</p><button className="button button-cream" onClick={() => setScreen("entry")}>＋ Start a new run <span>→</span></button><div className="history-hint"><span>⌘</span><span>Run history is loaded from the Argus API.</span></div></div>}

      {screen === "entry" && <div className="entry-layout"><div className="entry-heading"><p className="eyebrow">NEW QA RUN</p><h1>Test your web app<br/>like a careful human would.</h1><p>Connect to the Argus API to run a real browser session or the backend fixture demo.</p>{apiError && <p className="status" role="alert">{apiError}</p>}</div><form className="run-form" onSubmit={startRun}><label className="field-label" htmlFor="app-url">Application URL</label><div className="url-field"><span>↗</span><input id="app-url" type="url" placeholder="http://localhost:3100" value={url} onChange={(event) => setUrl(event.target.value)} required/><span className="field-secure">⌑ HTTP(S)</span></div><label className="field-label" htmlFor="app-spec">What should the app do?</label><textarea id="app-spec" placeholder={'Describe the key journeys and rules you want Argus to check…\n\nExample: Users can sign up with email and password, log in, create articles, favorite them, and comment. Titles are required.'} value={spec} onChange={(event) => setSpec(event.target.value)} required rows={7}/><div className="field-footer"><span>Be specific about expected behavior and edge cases.</span><span>{spec.length} / 2,000</span></div><label className="field-label" htmlFor="run-mode">Run mode</label><select id="run-mode" value={runMode} onChange={(event) => setRunMode(event.target.value as "real" | "fixture")}><option value="real">Live browser run</option><option value="fixture">Backend fixture demo</option></select><div className="form-actions"><span><StatusDot tone="green"/> {runMode === "real" ? "Runs against the URL above" : "Uses backend fixture results"}</span><button className="button button-cream" type="submit">Run Agent <span>→</span></button></div></form><div className="entry-footnote"><span>01</span><span>One URL</span><i/><span>02</span><span>Your requirements</span><i/><span>03</span><span>Evidence-backed report</span></div></div>}

      {(isLive || isResults) && <>
        <div className="run-overview"><div className="overview-title"><div><p className="eyebrow">{isLive ? "RUN IN PROGRESS" : "RUN REPORT"}</p><h1>{isLive ? "Exploring your app" : `${selectedRun?.name ?? "Run"} report`} <span className="sample-pill">{activeRunId ? "Backend run" : "Sample report"}</span></h1></div><span className="overview-url">◉ {selectedRun?.url ?? url}</span></div>
          <div className="metrics-row">{isLive ? <><Metric label="EVENTS" value={String(stream.events.length)}/><Metric label="FINDINGS" value={String(visibleFindings.length)}/><Metric label="STATUS" value={stream.status.toUpperCase()}/><Metric label="COVERAGE" value={selectedRun?.coverage ?? "—"}/></> : <><Metric label="FINDINGS" value={String(visibleFindings.length)} caption="reported by backend"/><Metric label="JOURNEYS" value={String(runDetail?.summary?.test_cases?.length ?? "—")}/><Metric label="PASSED" value={String(runDetail?.summary?.test_results?.filter((result) => result.verdict === "PASS").length ?? "—")}/><Metric label="FAILED" value={String(runDetail?.summary?.test_results?.filter((result) => result.verdict === "FAIL").length ?? "—")}/><Metric label="COVERAGE" value={selectedRun?.coverage ?? "—"}/></>}</div>
        </div>

        <div ref={workspaceRef} className={`workspace-layout ${isResults ? "results-layout" : ""}`} style={{ gridTemplateRows: fullScreen ? "minmax(0, 1fr)" : `${topSplit}fr 10px ${100 - topSplit}fr` }}>
          <div ref={splitRef} className={`workspace-top ${fullScreen ? "is-fullscreen" : ""}`} style={{ gridTemplateColumns: fullScreen ? "1fr" : `${browserSplit}fr 10px ${100 - browserSplit}fr` }}>
            {isLive ? <section className="browser-panel"><div className="panel-heading"><div><span className="panel-icon">◉</span><strong>Live browser</strong><span className="live-label"><StatusDot tone={stream.status === "failed" ? "gray" : stream.status === "completed" ? "green" : "amber"}/> {stream.status === "failed" ? "Run failed" : stream.status === "completed" ? "Run complete" : "Agent is working"}</span></div><div className="panel-controls"><button onClick={() => setFullScreen((value) => !value)} title={fullScreen ? "Exit fullscreen" : "Fullscreen browser"}>{fullScreen ? "⊠" : "⛶"}</button>{fullScreen && <button onClick={() => setFullScreen(false)} title="Exit fullscreen">×</button>}</div></div><div className="browser-frame-live"><LiveView runId={activeRunId ?? ""} fixtureSrc={runMode === "fixture" ? "/fixtures/fixture-browser-frame.svg" : undefined} /></div><div className="browser-actions"><button className="text-action" onClick={() => setFullScreen(true)}>⛶ Expand browser</button><button className="text-action" onClick={() => setScreen("results")}>View report →</button></div>{fullScreen && <div className="floating-score-wrap" onMouseEnter={() => setScoreOpen(true)} onMouseLeave={() => setScoreOpen(false)}><button className="floating-score" aria-expanded={scoreOpen} aria-label="Open findings and scoreboard" onClick={() => setScoreOpen((value) => !value)}><strong>{visibleFindings.length}</strong><span>findings</span><b>{stream.events.length} events</b><i>{runDetail?.summary?.coverage ? `${Math.round(Object.values(runDetail.summary.coverage).reduce((a, b) => a + b, 0) / Object.keys(runDetail.summary.coverage).length * 100)}%` : "—"}</i></button>{scoreOpen && <div className="floating-findings"><div className="subpanel-heading"><strong>Findings feed</strong><span>{visibleFindings.length} findings · {stream.events.length} events</span></div><div className="finding-list">{visibleFindings.slice(0, 4).map((finding) => <FindingRow key={finding.id} finding={finding} active={selectedFinding.id === finding.id} onClick={() => setSelectedFinding(finding)}/>)}</div><button className="text-action" onClick={() => { setFullScreen(false); setScreen("results"); }}>Open full report →</button></div>}</div>}</section> : <section className="evidence-panel"><div className="panel-heading"><div><span className="panel-icon evidence-icon">✦</span><strong>Evidence</strong><span className="sample-tag">Selected finding</span></div><button className="panel-more" onClick={() => void copyReport()}>{copied ? "Copied ✓" : "⋯"}</button></div><div className="evidence-content"><div className="evidence-kicker"><span className={`severity ${selectedFinding.severity.toLowerCase()}`}>{selectedFinding.severity}</span><span>{selectedFinding.status === "verified" ? (selectedFinding.verifiedBy === "none" ? "REPRODUCED FINDING" : "VERIFIED FINDING") : selectedFinding.status === "pending" ? "PENDING REVIEW" : "REJECTED REPORT"}</span><span className="evidence-time">{selectedFinding.time}</span></div><h2>{selectedFinding.detail}</h2><p className="repro-count"><StatusDot tone={selectedFinding.status === "verified" ? "green" : selectedFinding.status === "pending" ? "amber" : "gray"}/> {selectedFinding.status === "verified" ? (selectedFinding.repro ?? "Reproduced 5/5 in fresh contexts") : selectedFinding.status === "pending" ? "Replaying in fresh contexts" : "Rejected after fresh replay"}</p><div className="evidence-section"><h3>STEPS TO REPRODUCE</h3><ol>{selectedFinding.steps.map((step, i) => <li key={step}><span>{String(i + 1).padStart(2, "0")}</span>{step}</li>)}</ol></div><div className="expected-actual"><div><h3>EXPECTED</h3><p>{selectedFinding.expected}</p></div><div><h3>ACTUAL</h3><p>{selectedFinding.actual}</p></div></div><div className="evidence-section trace-section"><h3>NETWORK TRACE <span>{selectedFinding.network.method} {selectedFinding.network.path}</span></h3><div className="trace-line"><code>{selectedFinding.network.method}</code><span>{selectedFinding.network.path}</span><b className={selectedFinding.network.status.startsWith("5") ? "trace-error" : "trace-ok"}>{selectedFinding.network.status}</b><small>{selectedFinding.network.duration}</small></div><h3>CONSOLE</h3><pre>{selectedFinding.console}</pre></div><div className="artifact-row"><h3>ARTIFACTS</h3>{findingArtifacts.map((file, i) => <button key={file} onClick={() => setCopied(true)}><span>{["▧", "⌁", "≋", "‹›"][i]}</span>{file}<i>↗</i></button>)}</div><div className="evidence-actions"><button className="button button-outline button-small" onClick={() => void copyReport()}>{copied ? "Copied ✓" : "Copy report"}</button><button className="button button-cream button-small" onClick={() => setScreen("entry")}>Start new run →</button></div></div></section>}
            {!fullScreen && <div className="split-handle vertical" role="separator" aria-orientation="vertical" aria-label="Resize browser and findings panels" tabIndex={0} onPointerDown={() => setDragging("vertical")} onDoubleClick={() => setBrowserSplit(60)} onKeyDown={(event) => handleSplitKey(event, "vertical")}><span/></div>}
            {!fullScreen && <section className="findings-panel"><div className="panel-heading"><div><span className="panel-icon findings-icon">≋</span><strong>{isLive ? "Findings feed" : "Findings"}</strong><span className="panel-count">{visibleFindings.length} found</span></div><button className="panel-more" aria-label="Findings options">⋯</button></div><div className="finding-list">{visibleFindings.slice(0, isLive ? 4 : 6).map((finding) => <FindingRow key={finding.id} finding={finding} active={selectedFinding.id === finding.id} onClick={() => setSelectedFinding(finding)}/>)}</div>{isLive && <div className="activity-box"><div className="subpanel-heading"><strong>Agent activity</strong><span>{new Set(stream.events.map((event) => event.agent)).size} active</span></div>{(activeRunId ? Array.from(new Set(stream.events.map((event) => event.agent))) : activityRoles).map((role, i) => <div className="activity-row" key={role}><StatusDot tone={i < 3 ? (i === 1 ? "amber" : "green") : "gray"}/><span>{role}</span><div className={`activity-meter role-${i}`}><i/></div><small>{i < 3 ? (i === 1 ? "checking" : "active") : "idle"}</small></div>)}</div>}</section>}
          </div>
          {!fullScreen && <div className="split-handle horizontal" role="separator" aria-orientation="horizontal" aria-label="Resize coverage and tests panels" tabIndex={0} onPointerDown={() => setDragging("horizontal")} onDoubleClick={() => setTopSplit(70)} onKeyDown={(event) => handleSplitKey(event, "horizontal")}><span/></div>}
          {!fullScreen && (activeRunId ? <BackendRunOutput detail={runDetail}/> : <div className="workspace-bottom"><section className="coverage-panel"><div className="panel-heading"><div><span className="panel-icon coverage-icon">⌘</span><strong>Coverage map</strong><span className="sample-tag">Sample data</span></div><button className="panel-more">↗</button></div><div className="coverage-body"><div className="coverage-graph"><svg className="coverage-lines" viewBox="0 0 480 190" preserveAspectRatio="none" aria-hidden="true"><path d="M75 42H202M202 42H356M202 42V111M75 42V111M202 111H356M202 111V164M356 42V111"/><path className="line-done" d="M75 42H202M202 42V111M75 42V111"/></svg>{[["Home", "done"], ["Login", "done"], ["Profile", "partial"], ["Feed", "done"], ["Editor", "partial"], ["Settings", "todo"], ["Article", "partial"]].map(([name, state], i) => <div key={name} className={`coverage-node node-${i} ${state}`}><span>{state === "done" ? "✓" : state === "partial" ? "◐" : "○"}</span>{name}</div>)}</div><div className="coverage-legend"><p><i className="legend-dot done"/> Tested <b>28 / 30</b></p><p><i className="legend-dot partial"/> Journeys <b>5 / 6</b></p><p><i className="legend-dot todo"/> Elements <b>87 / 120</b></p><div className="coverage-bar"><i style={{ width: isLive ? `${Math.min(72 + elapsed, 91)}%` : "72%" }}/></div><small>{isLive ? `${Math.min(72 + elapsed, 91)}%` : "72%"} covered</small></div></div></section>
            <section className="tests-panel"><div className="panel-heading"><div><span className="panel-icon tests-icon">⌘</span><strong>Tests & exports</strong><span className="sample-tag">12 generated</span></div><button className="panel-more" onClick={() => setScreen("results")}>View report →</button></div><div className="tests-body"><div className="test-file-list">{[["Journey", "sign-up", "PASS"], ["Journey", "login", "PASS"], ["Edge", "empty-email", "PASS"], ["Edge", "long-title", "FAIL"], ["Security", "IDOR-check", "PASS"]].map(([kind, name, result]) => <div className="test-file" key={name}><span className="test-kind">{kind}</span><strong>{name}</strong><span className={`test-result ${result.toLowerCase()}`}>{result === "PASS" ? "✓" : "×"} {result}</span></div>)}</div><div className="tests-summary"><div><span>Exported Playwright tests</span><strong>12</strong></div><div><span>Repro tests generated</span><strong>5</strong></div><button onClick={() => setScreen("results")}>Open test suite <span>↗</span></button></div></div></section></div>)}
        </div>
      </>}
    </section>

    {screen === "parsing" && <div className="parsing-overlay"><div className="parsing-card"><div className="parsing-spinner"/><p className="eyebrow">ARGUS SPEC PARSER</p><h2>Understanding your app…</h2><div className="parse-progress"><span><i/> 6 journeys identified</span><span><i/> 24 claims extracted</span><span><i/> 3 validation rules detected</span></div><div className="parsing-footer"><span>Preparing a sample run</span><b>DEMO MODE</b></div></div></div>}
    {dragging && <div className={`resize-cursor ${dragging}`} aria-hidden="true"/>}
  </main>;
}
