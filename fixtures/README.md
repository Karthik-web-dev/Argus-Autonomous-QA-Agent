# Golden fixtures

These fixtures are validated by the F-01 Pydantic models and consumed by the fixture-backed role implementations in `packages/agent/src/argus/stubs.py`.

- `sample_spec.md` is the readable Conduit product description; `spec.json` is its parsed contract.
- `app_graph.json`, `element_catalog.json`, `test_cases.json`, and `test_results.json` seed the exploration and testing roles.
- `findings.json` deliberately includes a confirmed bug, a flaky candidate, and a false positive. Their evidence bundles are under `evidence/`.
- `gate_results.json`, `verification_results.json`, and `bug_reports.json` exercise the review and reporting roles.
- `run_events.ndjson` contains 60 validated events and at least one example of every F-01 event type.

Regenerate deterministic fixture contents with `python scripts/generate_golden_fixtures.py` after editing that script. Tests parse every fixture before a stub run.
