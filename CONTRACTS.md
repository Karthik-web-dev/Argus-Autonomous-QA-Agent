# Argus contracts

Pydantic v2 models in `packages/shared/src/argus_contracts/models.py` are the canonical source. `packages/shared/schemas/*.schema.json` and `packages/ui/lib/generated/contracts.ts` are generated outputs; do not edit them by hand.

Run `make schemas` after changing a model. Run `make check-schemas` to verify generated outputs are current. The dashboard's `Finding` in `packages/ui/lib/dashboard-content.ts` is a display-only demo view model and is deliberately not aliased to the backend `Finding` contract.

## Contract ownership

| Contract | Purpose |
|---|---|
| `Spec`, `SpecClaim`, `SpecEntity`, `ValidationRule` | Parsed application expectations |
| `TestCase`, `Step` | Repeatable browser journey instructions |
| `ElementCatalogEntry`, `AppGraph` | Semantic inventory and discovered navigation graph |
| `Finding`, `Evidence`, `NetworkEvent`, `ConsoleEvent`, `ReproductionResult` | Evidence-linked candidate defect |
| `GateResult`, `VerificationResult`, `BugReport`, `ManifestBug` | Acceptance, adversarial verification, report, benchmark truth |
| `RunEvent`, `TestResult`, `QAState` | Runtime event stream, execution outcome, supervisor state |

## Event envelope

Every event has `id`, `run_id`, UTC `ts`, `agent`, `correlation_id`, `type`, and object `payload`. The event type is a closed enum in `RunEvent`. Payloads intentionally remain type-specific JSON objects so consumers can evolve event details while preserving the envelope. Example payloads below are illustrative; their shape is covered by the envelope contract.

| Type | Example payload |
|---|---|
| `run_started` | `{"target_url":"https://demo.example","spec":"Users can sign in"}` |
| `phase_changed` | `{"phase":"exploration","previous":"initializing"}` |
| `agent_active` | `{"agent":"explorer","status":"active"}` |
| `action` | `{"action":"click","locator":"role=button[name=Sign in]"}` |
| `page_discovered` | `{"url":"/login","element_count":4}` |
| `test_result` | `{"test_id":"login-happy-path","verdict":"PASS","duration_ms":842}` |
| `finding_created` | `{"finding_id":"f-001","oracle_id":"http-status","confidence":0.94}` |
| `gate_result` | `{"finding_id":"f-001","verdict":"ACCEPTED","attempts":3,"successes":3}` |
| `verification_result` | `{"finding_id":"f-001","verdict":"CONFIRMED","attempts":5}` |
| `bug_reported` | `{"bug_id":"bug-001","severity":"P1","evidence_ref":"artifacts/f-001"}` |
| `coverage_update` | `{"covered":7,"total":25,"ratio":0.28}` |
| `scoreboard_update` | `{"true_positive":7,"false_positive":1,"precision":0.875,"recall":0.28}` |
| `budget_update` | `{"calls_remaining":12,"estimated_cost_usd":0.04}` |
| `llm_call` | `{"purpose":"spec_parse","provider":"configured-provider","duration_ms":510}` |
| `error` | `{"code":"BROWSER_NAVIGATION_FAILED","message":"Target timed out"}` |
| `run_completed` | `{"status":"completed","finding_count":3,"artifact_dir":"runs/r-001"}` |

## Artifact layout

Each run is rooted at `runs/<run_id>/`:

```text
runs/<run_id>/
├── events.ndjson
├── state.json
├── artifacts/<finding_id>/{trace.zip, screenshots/, network.json, console.json}
├── tests/
└── reports/
```

`RunArtifactLayout` in `argus_contracts.artifacts` resolves safe run/finding paths, initializes directories, appends validated `RunEvent` envelopes to NDJSON, and writes the state snapshot. `initialize_finding(finding_id)` returns the canonical trace, screenshot directory, network, and console paths for an evidence producer.

`Evidence.step_evidence` contains a full screenshot, optional element crop, and accessibility snapshot for each zero-based step index. `NetworkEvent.step_index` associates each request with the active step. `Evidence.trace_path` and optional `video_path` point to requested browser recordings. Credentials and tokens are redacted in textual evidence; values explicitly marked as synthetic test data by the caller are preserved.

## QAState single-writer ownership

The dossier describes single-writer discipline and names Explorer as the writer for `app_graph` and Reporter for `bugs_found`. Other fields use the responsible phase's writer, with the Supervisor applying stage updates serially.

| QAState field | Owner |
|---|---|
| `target_url`, `spec`, `iteration`, `complete` | Supervisor |
| `app_graph`, `discovered_elements` | Explorer |
| `test_cases` | Spec Parser / Test Binder |
| `test_results` | Tester |
| `findings` | Supervisor (ingests oracle/perception events) |
| `accepted_findings`, `rejected_findings` | Evidence Gate |
| `verified_findings` | Red Team |
| `bugs_found` | Reporter |
| `coverage`, `metrics` | Supervisor (after benchmark scoring) |

The same model table is reflected in `QAState`; the Supervisor is the only component that merges stage outputs into shared runtime state.
