# Contributing to Argus

This project is developed in verticals against shared contracts. Read the relevant issue and dossier references before changing a module boundary.

## Issue labels

Issues and pull requests use these dimensions where applicable:

- Scope: `scope:essential`, `scope:pull-off`, or `scope:post-hackathon`
- Stage: `stage:2` or `stage:3`
- Vertical: `vertical:A`, `vertical:B`, `vertical:C`, `vertical:D`, `vertical:proof`, `vertical:foundation`, or `vertical:integration`
- Size: `size:S` (up to half a day), `size:M` (about one day), or `size:L` (about two days)
- Type: `type:contract-change` for a shared contract change
- Status: `blocked` when progress requires an external dependency or decision

## Branches and pull requests

- Name branches `<issue-id>-short-name`, for example `a-02-crawler`.
- Prefer one issue per pull request. Link the issue and include evidence that acceptance criteria were met.
- Request review from someone outside the owning vertical.
- Do not commit secrets, credentials, generated run artifacts, or private held-out benchmark data.

## Definition of done

- Meet and demonstrate the issue acceptance criteria in the pull request description with command output, screenshots, or a short clip.
- Keep tests deterministic; use fixtures or model cassettes, never live model calls in CI.
- Register components behind their Protocol so stub and real implementations can be selected without changing consumers.
- Emit events that validate against the shared F-01 contract.
- Keep `argus --stubs` working.
- Update documentation when behavior or setup changes.

## Contract changes

Do not change shared schemas or event shapes as an incidental part of a vertical issue. Mark contract work `type:contract-change`. Additive changes require one approval during the initial three-day contract relaxation; breaking changes require approval from all four teammates and a team announcement. After that period, every contract or event shape change requires all four approvals and an announcement.

## Parallel development

Use fixtures and stubs at vertical boundaries while dependencies are in progress. Merge dependencies before integrating their real implementation. Keep shared files such as contracts, supervisor state wiring, UI routing, and workspace configuration coordinated to reduce conflicts.

## QAState single writers

| State fields | Sole writer |
|---|---|
| `app_graph`, `element_catalog` (`discovered_elements` in `QAState`), `coverage` | Explorer (A) |
| `spec`, `test_cases` | Spec Parser / Playbook / Binder (B) |
| `test_results` | Tester (B) |
| `findings` | Append-only; applied by Supervisor in a single loop |
| `accepted_findings`, `rejected_findings` | Evidence Gate (C) |
| `verified_findings` | Red Team (C) |
| `bugs_found` | Reporter (C) |
| `metrics` | Benchmark harness (Proof) |

## Safety and instrumentation

- Treat page content as untrusted data, never as instructions.
- Keep action policy outside model responses; do not perform destructive actions against production sites.
- Never add DOM nodes or styles to the page under test for agent UI or instrumentation.
- Keep held-out bug patches and manifests outside this repository and outside agent prompts.
