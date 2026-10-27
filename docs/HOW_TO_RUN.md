# How to run Argus

This guide covers the Python CLI, the offline walking skeleton, and the optional UI.

## Requirements

- Python 3.11 or newer
- Node.js 22 and pnpm only if you want to run the UI
- Docker Desktop (or Docker Engine with Compose) only if you want to run the included sample app or full containerized stack
- A target web app running locally or at an allowlisted URL reachable from your machine for browser runs

You do not need Docker for the offline skeleton. The Python CLI and API need the Python setup below; the Vite UI is optional. The commands below assume PowerShell on Windows and a terminal opened at the repository root.

## Install the Python packages

From the repository root, create and activate a virtual environment, then install the local packages and Chromium browser binary:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .\packages\shared
python -m pip install -e ".\packages\agent[dev]"
python -m playwright install chromium
```

On macOS or Linux, activate the environment with `source .venv/bin/activate` and use the same pip commands with forward-slash paths. The `argus` command is installed by the agent package. Keep the virtual environment activated in each terminal where you run it.

The equivalent repository setup shortcut is `make setup`. `make test` runs the Python test suites, and `make lint` runs the Python and UI linters. Pre-commit hooks are configured in `.pre-commit-config.yaml`; after installing `pre-commit`, enable them with `pre-commit install`.

If PowerShell blocks environment activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then activate `.venv` again. This changes the policy only for that terminal session.

## Run the offline walking skeleton

The backwards-compatible top-level skeleton exercises all role interfaces with golden fixtures. It does not start a browser or contact a target application:

```sh
argus --stubs
```

To exercise role replacement, use the deterministic demo implementations for Explorer and Tester while the other roles use fixtures:

```sh
argus --stubs --real explorer,tester
```

These built-in replacements demonstrate the registry and contract boundary; they still delegate to fixture data. The command creates a run under `artifacts/runs/<run_id>/`, including `events.ndjson`, `state.json`, exported tests, and a bug report. From an installed development checkout, `make skeleton` runs the same offline command.

To exercise the LangGraph orchestration with fixtures and optional role swaps, use `argus run --stubs`. This graph mode is also offline and writes a SQLite checkpoint. The bare `argus --stubs` form remains the original walking skeleton.

## Run against a web application

Start your target app, then run Argus with its URL and expected behavior. The live CLI runs the sequential LangGraph pipeline; `--spec` accepts a short description or a Markdown file path:

```sh
argus run http://localhost:3100 --spec spec.md
```

The run creates a unique ID and writes events, state, browser evidence, exported tests, reports, and a SQLite graph checkpoint beneath `artifacts/runs/<run_id>/`. If the process is interrupted, resume the same run with:

```sh
argus resume <run_id>
```

The live spec parser and ambiguous-step binder use the configured `cheap` model route. Set `ARGUS_MODEL_CHEAP_NAME` and `ARGUS_MODEL_CHEAP_BASE_URL` (and `ARGUS_MODEL_CHEAP_API_KEY` when required by your provider) before a live run. Without a model route, use `argus run --stubs` to exercise the full orchestration offline.

To supply explicit journeys, pass a JSON file containing an array of `TestCase` objects. The checked-in golden cases describe Conduit and are intended for that sample app, so use them with the sample app rather than an unrelated site:

```sh
argus --url http://localhost:3100 --spec "Users can sign in and create an article" --journeys fixtures/test_cases.json --output artifacts
```

The original `argus --url ...` syntax remains available as a backwards-compatible shortcut. `argus --help` shows both forms.

Capture one page and write its ARIA snapshot, typed element catalog, state signature, and compact prompt rendering to JSON with:

```powershell
argus snapshot http://localhost:3100
```

The default output is a URL-derived file under `artifacts/snapshots/`. Choose a file and a smaller prompt budget with `--output` and `--max-tokens`:

```powershell
argus snapshot http://localhost:3100 --output artifacts/snapshots/workbench.json --max-tokens 1200
```

The runner writes state, events, and browser evidence beneath `artifacts/runs/<run_id>/` by default. It requires the target app to be reachable and Chromium to be installed. For a first manual CLI run, use the included sample app. Make sure Docker Desktop is running:

```powershell
docker compose up --build sample-app
```

Then, in a second terminal, activate the Python virtual environment and run the CLI command above against `http://localhost:3100`. Stop the sample app with `Ctrl+C` when finished.

### Testing another website

The CLI can navigate to any HTTP(S) URL. The API used by the frontend has an additional host allowlist, which defaults to `localhost,127.0.0.1`. To let the API open a public website, set `ARGUS_ALLOWED_DOMAINS` in the shell before starting the API. Use exact domains you trust; an entry also allows its subdomains.

PowerShell example:

```powershell
$env:ARGUS_ALLOWED_DOMAINS = "localhost,127.0.0.1,example.com"
uvicorn argus.api:app --app-dir packages/agent/src --host 127.0.0.1 --port 8000
```

macOS/Linux example:

```sh
ARGUS_ALLOWED_DOMAINS=localhost,127.0.0.1,example.com uvicorn argus.api:app --app-dir packages/agent/src --host 127.0.0.1 --port 8000
```

With that API running, the frontend can submit `https://example.com`. The CLI does not use this API allowlist; the browser runner itself still has no action guard in this current implementation, so only enter URLs you intend to inspect.

## CLI options

Use `argus --help` for the command list and `argus run --help` for run options:

| Option | Required? | Description |
|---|---:|---|
| `URL` / `--url TEXT` | For a live run | Target web application URL. Not required with `--stubs`. |
| `--spec TEXT` | For a live run | Expected behavior description or path to a Markdown spec file. Not required with `--stubs`. |
| `--output PATH` | No | Directory for run evidence. Defaults to `artifacts`. |
| `--journeys PATH` | No | JSON array of explicit `TestCase` objects to execute. |
| `--stubs` | No | Run against golden fixture data without a browser or network access. |
| `--real ROLES` | No | With `--stubs`, comma-separated role names to replace, such as `explorer,tester`. The currently registered demo replacements are `explorer` and `tester`. |
| `--help` | No | Show command help and exit. |

Examples:

```sh
argus --help
argus run --help
argus run --stubs --output artifacts/demo
argus --stubs --output artifacts/demo
argus run http://localhost:3100 --spec spec.md --output artifacts/login-run
argus resume <run_id> --output artifacts/login-run
```

## Run the frontend and backend API

The frontend form sends runs to the Python API at `http://localhost:8000`. First complete the Python setup above. Install Node.js 22, then enable Corepack (which supplies the repository-pinned pnpm version) if pnpm is not already available:

```powershell
corepack enable
```

Open two terminals from the repository root. Activate `.venv` in the API terminal; the UI terminal does not need Python.

Terminal 1 — API:

```powershell
uvicorn argus.api:app --app-dir packages/agent/src --host 127.0.0.1 --port 8000
```

Terminal 2 — Vite frontend:

```sh
pnpm install
pnpm dev
```

Open `http://localhost:5173`, enter the target app URL and expected behavior, and submit. The default frontend API address is `http://localhost:8000`; set `VITE_ARGUS_API_URL` in the repository-root `.env` file before starting Vite to point elsewhere. The API rejects hosts outside `ARGUS_ALLOWED_DOMAINS` with HTTP 400.

For the included sample app, start `docker compose up --build sample-app` in a third terminal first. The default API allowlist already permits `localhost`, so the form can submit `http://localhost:3100`. For a public website, set `ARGUS_ALLOWED_DOMAINS` in the API terminal as shown above before starting Uvicorn.

The frontend has both a simple run form at `/` and a sample dashboard at `/dashboard`. The dashboard currently displays fixture content; use the form to submit a real API run. You can instead start the sample app, API, and UI with `docker compose up --build`, then open `http://localhost:3000`; the UI form is configured to call the API on host port 8000.

### Run API endpoints

The API starts runs asynchronously and stores run metadata in `artifacts/runs.sqlite3`; detailed state, events, and evidence remain under `artifacts/runs/<run_id>/`. FastAPI serves its OpenAPI page at `http://localhost:8000/docs`.

For a local fixture run, start the API as above and submit:

```powershell
curl.exe -X POST http://localhost:8000/runs?mode=fixture `
  -H "Content-Type: application/json" `
  -d '{"url":"http://localhost:3100","spec":"Exercise the sample app"}'
```

For a real browser run, omit `mode=fixture` and use the target URL and behavior in the JSON body. The response contains a `run_id` and `events_url`. Read the live event stream, list previous runs, and inspect one run with:

```powershell
curl.exe -N http://localhost:8000/runs/<run_id>/events
curl.exe http://localhost:8000/runs
curl.exe http://localhost:8000/runs/<run_id>
```

SSE event IDs are increasing sequence numbers. To resume after event 24, reconnect with `curl.exe -N -H "Last-Event-ID: 24" http://localhost:8000/runs/<run_id>/events`; the stream starts with event 25. Run details list artifact URLs, which can be fetched directly, for example `/runs/<run_id>/artifacts/reports/bug_reports.json`.

For real Chromium runs, the UI shows a live browser panel after submission. The API captures 720p-or-smaller JPEG frames through CDP and streams them over the run's WebSocket endpoint (`/runs/<run_id>/screencast`). The frontend canvas and cursor overlay are outside the target page; action cues include their locator bounds and rationale. The `/replay` route uses a static browser-frame fixture with the recorded event stream and does not browse a site.

Set `ARGUS_API_TOKEN` in the API process environment to protect run and artifact endpoints with `Authorization: Bearer <token>`. `/health` remains public. For local Vite development, set the same value as `VITE_ARGUS_API_TOKEN`; for Docker Compose, provide both variables in the repository-root `.env`. Vite embeds its token in browser code, so this setting is for a local single-tenant demo, not a production secret.

## Run checks

```sh
make skeleton       # offline walking-skeleton smoke run
make check-schemas  # verify generated contract schemas and UI types are current
```

To run the Python test suite from the repository root:

```sh
python -m pytest packages/shared/tests packages/agent/tests
```
