# Agent role interfaces

`argus.interfaces` defines the stable, implementation-independent boundary for each Stage 2 vertical. Methods exchange the Pydantic v2 contracts from `argus_contracts`; the checked-in fixture implementations in `argus.stubs` make every role usable before a live component is ready.

## Implement a role

```python
from argus.interfaces import Explorer
from argus_contracts.models import AppGraph, ElementCatalogEntry

class MyExplorer(Explorer):
    def explore(self, target_url: str) -> tuple[AppGraph, list[ElementCatalogEntry]]:
        # Return validated contract models; do not return untyped dictionaries.
        return AppGraph(adjacency={"/": ["/login"]}), []
```

## Protocols

```text
Explorer.explore(url) -> (AppGraph, list[ElementCatalogEntry])
SpecParser.parse(description) -> Spec
PlaybookGenerator.generate(spec) -> list[TestCase]
Binder.bind(test_cases, elements) -> list[TestCase]
Tester.run(test_cases, url) -> list[TestResult]
Oracle.evaluate(test_result) -> list[Finding]
Gate.evaluate(finding, evidence) -> GateResult
RedTeam.verify(finding, spec, evidence) -> VerificationResult
Reporter.build(findings, gates, verifications, evidence_by_finding) -> list[BugReport]
Exporter.export(test_cases, destination) -> list[Path]
EventBus.emit(run_event) -> None
```

All fixture roles implement these same methods. Add a production implementation by satisfying the relevant Protocol and injecting it into the supervisor; do not change the shared model shapes to accommodate a stub.

## Offline demo

From the repository root, install both local Python packages, then run:

```sh
argus --stubs
```

The walking skeleton runs roles sequentially through `ComponentRegistry`, validates role implementations against their Protocols, exports the golden journeys, writes `QAState` and one `BugReport`, and emits the checked-in event trace under `artifacts/runs/<run_id>/`. The smoke command is `make skeleton`; it does not launch a browser or contact the Conduit URL.

Replace selected roles with deterministic contract-compatible demo components using:

```sh
argus --stubs --real explorer,tester
```

The built-in replacements exercise component selection and the same role contracts while delegating to golden fixture data. Register browser-backed implementations with `ComponentRegistry.register_real()` when their verticals are ready; other roles remain fixture-backed.

## Accessibility snapshot and element catalog

Capture a page with Playwright and write the accessibility tree, typed interactive-element catalog, stable state signature, and token-bounded prompt view to JSON:

```sh
argus snapshot http://localhost:3100
```

Use `--output path.json` to choose the output file and `--max-tokens 1200` to reduce the compact-rendering budget. The command reports how many visible controls resolve to a single strict-mode locator. Duplicate accessible names receive a deterministic `nth` suffix; catalog IDs are derived from each control's role, name, and form group.

Argus-owned DOM overlays must be marked with `data-argus-agent`, `data-argus-injected`, or `data-argus-overlay` (or use `#argus-agent-overlay`). The snapshot/catalog boundary excludes these marked roots.

## Deterministic application crawl

Build a same-origin route/state graph without calling an LLM:

```sh
argus crawl http://localhost:3100 --output artifacts/app_graph.json
```

The crawler defaults to 50 pages and 500 navigation/click steps. `AppGraph` keeps
its original `adjacency` mapping and adds `nodes` (URL, A-01 signature, snapshot,
and element catalog) and `edges` (action and semantic locator). External links are
ignored by the temporary same-origin guard; D-07 can be connected through the
injectable `navigation_guard` callback.

For a logged-in pass, provide a code-owned login callback. The crawler runs it
once, saves Playwright `storage_state.json` beside the graph, then creates a fresh
authenticated context and crawls again:

```python
import asyncio
from argus.agents.explorer_crawler import crawl_app

async def login(page):
    await page.get_by_label("Email").fill("qa@example.test")
    await page.get_by_label("Password").fill("test-password")
    await page.get_by_role("button", name="Sign in").click()

asyncio.run(crawl_app(
    "http://localhost:3100",
    "artifacts/app_graph.json",
    auth_bootstrap=login,
))
```

The login callback is regular Python and is not sent to a model. Keep real
credentials out of checked-in scripts and use environment-backed test secrets.

## Model gateway

`argus.models.ModelGateway` is the sole provider boundary for structured LLM and VLM calls. It validates each response with JSON Schema and supports `cheap`, `strong`, `strong_alt`, and `vlm` tiers. The default Explorer tier is `cheap`; Red Team uses `strong_alt` and startup validation rejects identical provider/model pairs.

Set `ARGUS_MODEL_BASE_URL` and `ARGUS_MODEL_API_KEY`, then set `ARGUS_MODEL_CHEAP_NAME`, `ARGUS_MODEL_STRONG_NAME`, `ARGUS_MODEL_STRONG_ALT_NAME`, and `ARGUS_MODEL_VLM_NAME`. A tier can override the shared endpoint and key with `ARGUS_MODEL_<TIER>_BASE_URL` and `ARGUS_MODEL_<TIER>_API_KEY`. Endpoints use the OpenAI-compatible `/chat/completions` API; changing compatible providers or model names requires configuration changes only.

`ARGUS_MODEL_MODE=record` calls the configured provider and saves deterministic JSON cassettes in `ARGUS_MODEL_CASSETTE_DIR`. `ARGUS_MODEL_MODE=replay` reads those cassettes and fails without making a network request when a cassette is missing. `live` makes provider calls without writing cassettes. All modes enforce the shared rate limiter and per-run budgets. For image input on the `vlm` tier, pass the provider's multimodal user content blocks as `prompt` rather than a string.

Callers provide a JSON Schema and run identifier:

```python
result = await gateway.generate(
    tier="strong", run_id=run_id, system="Return a concise assessment.",
    prompt="Evaluate this finding.", schema=Assessment.model_json_schema(),
)
```

The gateway retries malformed structured output once, then raises `MalformedModelResponse`. `BudgetExceeded` prevents requests that exceed the configured call or token limits. Provider errors are surfaced directly and are not retried as schema errors.

## Browser sessions

Use `argus.browser.session.BrowserSessionFactory` for every browser context. It lazily launches and reuses Chromium, Firefox, and WebKit processes while giving each caller a fresh context. Contexts do not share cookies, localStorage, or IndexedDB unless a caller explicitly supplies a `storage_state`.

```python
async with BrowserSessionFactory(artifact_dir="artifacts/browser", concurrency_cap=4) as factory:
    session, cdp = await factory.new_context(
        "chromium", viewport={"width": 1440, "height": 900},
        record={"trace": True, "video": True, "har": True},
        init_scripts=["globalThis.__argusRunId = 'run-123';"],
    )
    try:
        await session.page.goto("http://localhost:3000")
        print(session.requests, session.responses, session.console)
    finally:
        await session.close()
```

`new_context` returns the wrapper and the CDP session handle as a tuple. CDP is available for Chromium and is `None` for Firefox and WebKit. `BrowserSession.close()` stops tracing and writes `trace.zip` when requested, flushes HAR/video output, closes the context, and frees its concurrency slot. Use `init_scripts` for JavaScript source that should run before page scripts; this slot does not provide DOM or stylesheet injection helpers.

Playwright Python is pinned to **1.63.0** in `pyproject.toml`. Install all matching browser binaries with:

```sh
python -m playwright install --with-deps chromium firefox webkit
```

The agent Docker image and CI install the same three browser engines. The browser-session integration tests cover ten isolated contexts, the default concurrency cap, all three launchers, telemetry, init scripts, and trace output.

## Evidence recorder

`argus.evidence.recorder.EvidenceRecorder` is used by the tester to capture the same bundle for every journey. It records each step's full-page screenshot, an element crop when a step targets an element, and an accessibility snapshot. Network requests carry a zero-based `step_index`; console output and network logs are written to `artifacts/<test_id>/console.json` and `network.json` under the run layout. The recorder finalizes the BrowserSession so `trace.zip` and requested video are flushed before it returns the validated `Evidence` model.

Password/token fields in fill steps are detected from their semantic locator and redacted in textual evidence. Pass factory-provenance values through `synthetic_values` to preserve them in evidence while redacting actual credentials.
