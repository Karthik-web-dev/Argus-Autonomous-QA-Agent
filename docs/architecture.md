# Architecture

Argus separates browser observations, deterministic execution, decision rules, and report generation. The browser is treated as an untrusted target: target page text is evidence, never agent instructions.

## Supervisor flow

The CLI and the API's real-run path use a sequential LangGraph pipeline: parse spec → explore → generate tests → bind → test → oracles → evidence gate → Red Team → deduplicate → report → export. Each phase is a separate checkpointed node, emits `phase_changed` and `agent_active`, and owns its state outputs. SQLite checkpoints are stored at `runs/<run_id>/checkpoints.sqlite3`; CLI runs can resume with `argus resume <run_id>`. The component registry supplies fixture or live role implementations. The API forwards tester actions and CDP frames to its SSE and WebSocket clients.

Browser execution records console, HTTP, DOM, screenshot, and trace evidence in isolated contexts. The Red Team adapter remains inconclusive until an independent model reviewer is configured, so the Reporter will not claim a finding is Red-Team-confirmed in its absence. Fixture API runs replay the checked-in golden run; real API runs invoke the LangGraph pipeline.

## Packages

`packages/agent` owns runtime behavior. `packages/shared/schemas` publishes JSON Schema for consumers. `packages/ui` consumes API run events for live findings and agent activity, and can replay the golden event fixture. Sample apps and the benchmark harness are kept outside the runtime package so benchmark truth can be managed independently.

## Trust boundaries

The target application and its DOM are untrusted. Actions are bounded by a supplied test journey; no arbitrary page-provided instruction is executed. Domain allowlists are configurable. Never point the runner at production workflows that can delete, purchase, or send real data.
