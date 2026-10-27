"""FastAPI interface for starting runs and reading their durable outputs."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote
from uuid import uuid4

from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import CreateRunRequest, RunEvent
from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

from argus.api.screencast import ScreencastHub
from argus.cancellation import RunCancelled
from argus.cancellation import cancel as cancel_run_flag
from argus.cancellation import clear as clear_cancellation
from argus.config import settings
from argus.graph.build import run_supervisor
from argus.run_store import RunStore
from argus.supervisor.live_components import build_live_components

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
logging.getLogger("argus").setLevel(logging.INFO)

app = FastAPI(title="Argus QA API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "Last-Event-ID"],
)


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """Require a bearer token when ARGUS_API_TOKEN is configured."""
    expected = os.environ.get("ARGUS_API_TOKEN", settings.api_token)
    if not expected:
        return
    scheme, separator, supplied = (authorization or "").partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
    ):
        raise HTTPException(
            status_code=401,
            detail="A valid bearer token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )


class RunService:
    """Coordinate asynchronous runs, the SQLite index, and artifact storage."""

    def __init__(self, artifact_root: str | Path):
        self.store = RunStore(artifact_root)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self.screencasts: dict[str, ScreencastHub] = {}

    def start(
        self, request: CreateRunRequest, mode: Literal["real", "fixture"]
    ) -> dict[str, str]:
        run_id = uuid4().hex
        RunArtifactLayout(self.store.runs_root, run_id).initialize()
        self.store.create(run_id, str(request.url), request.spec)
        hub = ScreencastHub(run_id)
        self.screencasts[run_id] = hub
        event_loop = asyncio.get_running_loop()

        def publish_frame(frame: dict[str, Any]) -> None:
            event_loop.call_soon_threadsafe(hub.publish_frame, frame)

        def publish_action(action: dict[str, Any]) -> None:
            event_loop.call_soon_threadsafe(hub.publish_action, action)

        task = asyncio.create_task(
            self._execute(run_id, request, mode, publish_frame, publish_action)
        )
        self._tasks[run_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(run_id, None))
        return {
            "run_id": run_id,
            "status": "queued",
            "events_url": f"/runs/{run_id}/events",
            "screencast_url": f"/runs/{run_id}/screencast",
            "detail_url": f"/runs/{run_id}",
            "artifacts_url": f"/runs/{run_id}/artifacts",
        }

    async def _execute(
        self,
        run_id: str,
        request: CreateRunRequest,
        mode: Literal["real", "fixture"],
        publish_frame: Callable[[dict[str, Any]], None],
        publish_action: Callable[[dict[str, Any]], None],
    ) -> None:
        self.store.update(run_id, status="running")
        try:
            if mode == "fixture":
                from argus.stubs import run_stub_demo

                await asyncio.to_thread(
                    run_stub_demo,
                    self.store.artifact_root,
                    run_id=run_id,
                )
            else:
                target_url = str(request.url)
                layout = RunArtifactLayout(self.store.runs_root, run_id)
                logger.info("Starting live run %s against %s", run_id, target_url)

                def run_graph() -> None:
                    components = build_live_components(
                        run_id=run_id,
                        target_url=target_url,
                        layout=layout,
                        on_screencast_frame=publish_frame,
                        on_action=publish_action,
                    )
                    run_supervisor(
                        components,
                        target_url=target_url,
                        spec_description=request.spec,
                        output_dir=self.store.artifact_root,
                        run_id=run_id,
                    )

                await asyncio.to_thread(
                    run_graph,
                )
            self.store.update(run_id, status="completed")
        except RunCancelled:
            logger.info("Run %s stopped by user", run_id)
            RunArtifactLayout(self.store.runs_root, run_id).append_event(RunEvent(
                id=uuid4().hex, run_id=run_id, agent="api", correlation_id=run_id,
                type="run_cancelled", payload={"message": "Run stopped by user"},
            ))
            self.store.update(run_id, status="cancelled", error="Stopped by user")
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            layout = RunArtifactLayout(self.store.runs_root, run_id)
            layout.append_event(
                RunEvent(
                    id=uuid4().hex,
                    run_id=run_id,
                    agent="api",
                    correlation_id=run_id,
                    type="error",
                    payload={"message": str(exc)},
                )
            )
            self.store.update(run_id, status="failed", error=str(exc))
        finally:
            clear_cancellation(run_id)
            self.screencasts[run_id].close()


run_service = RunService(settings.artifact_dir)


def _public_run(row: dict[str, Any]) -> dict[str, Any]:
    run_id = row["run_id"]
    return {
        "run_id": run_id,
        "target_url": row["target_url"],
        "spec": row["spec"],
        "status": row["status"],
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "events_url": f"/runs/{run_id}/events",
        "screencast_url": f"/runs/{run_id}/screencast",
        "detail_url": f"/runs/{run_id}",
        "artifacts_url": f"/runs/{run_id}/artifacts",
    }


def _artifact_urls(run_id: str) -> list[dict[str, str]]:
    run_dir = (run_service.store.runs_root / run_id).resolve()
    if not run_dir.is_dir():
        return []
    urls = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file():
            relative = path.relative_to(run_dir).as_posix()
            urls.append(
                {
                    "path": relative,
                    "url": f"/runs/{run_id}/artifacts/{quote(relative, safe='/')}",
                }
            )
    return urls


def _validate_target(request: CreateRunRequest) -> None:
    host = (request.url.host or "").lower()
    if request.url.scheme not in {"http", "https"}:
        raise HTTPException(
            status_code=400, detail="Only HTTP(S) targets are supported"
        )
    if settings.allowed_domains and not any(
        host == domain or host.endswith("." + domain)
        for domain in settings.allowed_domains
    ):
        raise HTTPException(
            status_code=400,
            detail="Target host is not in ARGUS_ALLOWED_DOMAINS",
        )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "argus-agent"}


@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    return {"object": "list", "data": []}


@app.post("/runs", status_code=202, dependencies=[Depends(require_api_token)])
async def create_run(
    request: CreateRunRequest,
    mode: Literal["real", "fixture"] = Query(
        default="real",
        description="Run the browser pipeline or the offline golden-fixture pipeline",
    ),
) -> dict[str, str]:
    _validate_target(request)
    return run_service.start(request, mode)


@app.get("/runs", dependencies=[Depends(require_api_token)])
async def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items, total = run_service.store.list(limit=limit, offset=offset)
    return {
        "items": [_public_run(item) for item in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/runs/{run_id}", dependencies=[Depends(require_api_token)])
async def get_run(run_id: str) -> dict[str, Any]:
    row = run_service.store.get(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run_dir = run_service.store.runs_root / run_id
    state_path = run_dir / "state.json"
    try:
        summary = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        summary = None
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500, detail="Run state is invalid JSON"
        ) from exc
    return {**_public_run(row), "summary": summary, "artifacts": _artifact_urls(run_id)}


@app.get("/runs/{run_id}/report.pdf", dependencies=[Depends(require_api_token)])
async def get_report_pdf(run_id: str) -> FileResponse:
    """Serve the run's bug report PDF, rendering it from bug_reports.json if needed."""
    from argus_contracts.models import BugReport

    from argus.reporter.document import build_report_html, render_pdf

    row = run_service.store.get(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    reports_dir = run_service.store.runs_root / run_id / "reports"
    pdf_path = reports_dir / "bug_report.pdf"
    source = reports_dir / "bug_reports.json"
    if not source.is_file():
        raise HTTPException(status_code=409, detail="This run has not filed its reports yet")
    # Re-render on every download (about a second) so report wording improvements
    # also apply to runs that finished earlier.
    reports = [BugReport.model_validate(item) for item in json.loads(source.read_text(encoding="utf-8"))]
    html_source = build_report_html(reports, target_url=row["target_url"], run_id=run_id)
    (reports_dir / "bug_report.html").write_text(html_source, encoding="utf-8")
    await render_pdf(html_source, pdf_path)
    return FileResponse(pdf_path, media_type="application/pdf",
                        filename=f"argus-bug-report-{run_id[:8]}.pdf")


@app.post("/runs/{run_id}/cancel", status_code=202, dependencies=[Depends(require_api_token)])
async def cancel_run(run_id: str) -> dict[str, str]:
    row = run_service.store.get(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if row["status"] not in {"queued", "running"}:
        return {"run_id": run_id, "status": row["status"]}
    # The pipeline stops at its next checkpoint (next step, case or phase).
    cancel_run_flag(run_id)
    return {"run_id": run_id, "status": "cancelling"}


@app.delete("/runs/{run_id}", status_code=204, dependencies=[Depends(require_api_token)])
async def delete_run(run_id: str) -> Response:
    if run_service.store.get(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    task = run_service._tasks.get(run_id)
    if task is not None:
        cancel_run_flag(run_id)
        task.cancel()
    run_service.store.delete(run_id)
    return Response(status_code=204)


@app.get("/runs/{run_id}/artifacts", dependencies=[Depends(require_api_token)])
async def list_artifacts(run_id: str) -> dict[str, Any]:
    if run_service.store.get(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "items": _artifact_urls(run_id)}


@app.get("/runs/{run_id}/events", dependencies=[Depends(require_api_token)])
async def stream_run_events(
    run_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    if run_service.store.get(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        resume_after = int(last_event_id) if last_event_id is not None else -1
        if resume_after < -1:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Last-Event-ID must be an integer"
        ) from exc

    async def events():
        last_sent = resume_after
        last_heartbeat = time.monotonic()
        events_path = run_service.store.runs_root / run_id / "events.ndjson"
        while not await request.is_disconnected():
            lines: list[str] = []
            try:
                with events_path.open(encoding="utf-8") as stream:
                    lines = stream.readlines()
            except FileNotFoundError:
                pass
            for sequence, line in enumerate(lines):
                if sequence <= last_sent or not line.endswith("\n"):
                    continue
                try:
                    event = RunEvent.model_validate_json(line)
                except ValueError:
                    logger.exception(
                        "Skipping invalid event in %s at sequence %s", run_id, sequence
                    )
                    last_sent = sequence
                    continue
                yield f"id: {sequence}\ndata: {event.model_dump_json()}\n\n"
                last_sent = sequence
            row = run_service.store.get(run_id)
            if (
                row
                and RunStore.is_terminal(row["status"])
                and last_sent >= len(lines) - 1
            ):
                break
            if time.monotonic() - last_heartbeat >= 10:
                yield ": keep-alive\n\n"
                last_heartbeat = time.monotonic()
            await asyncio.sleep(0.2)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.websocket("/runs/{run_id}/screencast")
async def stream_screencast(websocket: WebSocket, run_id: str) -> None:
    """Stream CDP frames and action overlays without modifying the target DOM."""
    if run_service.store.get(run_id) is None:
        await websocket.close(code=4404, reason="Run not found")
        return
    hub = run_service.screencasts.get(run_id)
    if hub is None:
        await websocket.close(code=4404, reason="Run has no live screencast")
        return

    await websocket.accept()
    try:
        auth_message = await asyncio.wait_for(websocket.receive_json(), timeout=5)
    except WebSocketDisconnect:
        # The UI may close/reconnect while a run is starting. The peer is
        # already gone, so don't turn that normal disconnect into an ASGI error.
        return
    except (TimeoutError, ValueError):
        try:
            await websocket.close(code=4401, reason="Screencast authentication handshake required")
        except WebSocketDisconnect:
            pass
        return
    expected = os.environ.get("ARGUS_API_TOKEN", settings.api_token)
    supplied = auth_message.get("token", "") if isinstance(auth_message, dict) else ""
    if (
        not isinstance(supplied, str)
        or (expected and not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")))
        or (not isinstance(auth_message, dict) or auth_message.get("type") != "auth")
    ):
        await websocket.close(code=4401, reason="Invalid screencast credentials")
        return

    queue = hub.subscribe()
    try:
        await websocket.send_json({"kind": "ready", "run_id": run_id})
        while True:
            message = await queue.get()
            await websocket.send_json(message)
            if message.get("kind") == "closed":
                break
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(queue)


@app.get(
    "/runs/{run_id}/artifacts/{artifact_path:path}",
    dependencies=[Depends(require_api_token)],
)
async def get_artifact(run_id: str, artifact_path: str) -> FileResponse:
    if run_service.store.get(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run_dir = (run_service.store.runs_root / run_id).resolve()
    candidate = (run_dir / artifact_path).resolve()
    if not candidate.is_relative_to(run_dir) or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(candidate)
