from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import typer
from argus_contracts.artifacts import RunArtifactLayout
from rich import print

from argus.config import settings
from argus.state.test_case import TestCase

app = typer.Typer(
    help="Explore web applications and collect reproducible QA evidence.",
    no_args_is_help=True,
)


def _run(url: str | None, spec: str | None, output: Path,
         journeys: Path | None, stubs: bool, real: str | None, *, orchestrated: bool = False) -> None:
    if stubs:
        if orchestrated:
            from argus.graph.build import run_supervisor
            from argus.stubs import GoldenFixtures, build_demo_registry

            fixtures = GoldenFixtures()
            run_id = uuid4().hex
            layout = RunArtifactLayout(output / "runs", run_id).initialize()
            registry = build_demo_registry(fixtures, layout)
            real_roles = tuple(role.strip() for role in (real or "").split(",") if role.strip())
            try:
                roles = registry.build(real_roles=real_roles)
                result = run_supervisor(
                    roles,
                    target_url="https://demo.realworld.io",
                    spec_description=fixtures.spec.description,
                    output_dir=output,
                    run_id=run_id,
                )
            except (TypeError, ValueError) as exc:
                raise typer.BadParameter(str(exc), param_hint="--real") from exc
            state = result["state"]
            event_count = len(layout.events_path.read_text(encoding="utf-8").splitlines())
            mode = "mixed graph run" if real_roles else "fixture graph run"
            print(f"[green]Walking skeleton complete[/green] ({mode}): "
                  f"{len(state.findings)} findings, {len(state.bugs_found)} report(s), "
                  f"{event_count} events (60-event golden trace fixture)")
            if real_roles:
                print(f"Components swapped in: {', '.join(real_roles)}")
            print(f"Artifacts: {result['artifact_dir']}")
            return

        from argus.stubs import run_stub_demo

        real_roles = tuple(role.strip() for role in (real or "").split(",") if role.strip())
        try:
            result = run_stub_demo(output, real_roles=real_roles)
        except (TypeError, ValueError) as exc:
            raise typer.BadParameter(str(exc), param_hint="--real") from exc
        mode = "mixed run" if real_roles else "stub run"
        print(f"[green]Walking skeleton complete[/green] ({mode}): {len(result['state'].findings)} findings, "
              f"{len(result['state'].bugs_found)} verified report(s), {result['event_count']} events")
        if real_roles:
            print(f"Components swapped in: {', '.join(real_roles)}")
        if result["reports"]:
            from argus.agents.reporter import format_markdown

            print(format_markdown(result["reports"][0]))
        print(f"Artifacts: {result['artifact_dir']}")
        return
    if real:
        raise typer.BadParameter("--real can only be used together with --stubs", param_hint="--real")
    if not url:
        raise typer.BadParameter("--url is required unless --stubs is selected", param_hint="--url")
    if not spec:
        raise typer.BadParameter("--spec is required unless --stubs is selected", param_hint="--spec")
    spec_path = Path(spec)
    if spec_path.is_file():
        spec = spec_path.read_text(encoding="utf-8")
    cases = None
    if journeys:
        raw = json.loads(journeys.read_text(encoding="utf-8"))
        cases = [TestCase.model_validate(item) for item in raw]
    from argus.graph.build import run_supervisor
    from argus.supervisor.live_components import build_live_components

    run_id = uuid4().hex
    layout = RunArtifactLayout(output / "runs", run_id).initialize()
    components = build_live_components(run_id=run_id, target_url=url, layout=layout)
    result = run_supervisor(
        components,
        target_url=url,
        spec_description=spec,
        output_dir=output,
        run_id=run_id,
        journeys=cases,
    )
    state = result["state"]
    print(f"[green]Run complete[/green]: {len(state.test_results)} tests, "
          f"{len(state.findings)} findings, {len(state.bugs_found)} reports")
    print(f"Run ID: {run_id}")
    print(f"Evidence: {result['artifact_dir']}")


@app.callback(invoke_without_command=True)
def default_run(
    ctx: typer.Context,
    url: str | None = typer.Option(None, help="Target web application URL"),
    spec: str | None = typer.Option(None, help="Expected behavior description or path to a Markdown spec file"),
    output: Path = typer.Option(settings.artifact_dir, help="Directory for run evidence"),  # noqa: B008
    journeys: Path | None = typer.Option(None, help="JSON file containing explicit TestCase objects"),  # noqa: B008
    stubs: bool = typer.Option(False, "--stubs", help="Run all role interfaces against golden fixtures; no browser or network required"),
    real: str | None = typer.Option(
        None, "--real", help="Comma-separated roles to replace (for example: explorer,tester)"
    ),
) -> None:
    """Keep the original top-level run syntax as a backwards-compatible shortcut."""
    if ctx.invoked_subcommand is None:
        _run(url, spec, output, journeys, stubs, real)


@app.command()
def run(
    target_url: str | None = typer.Argument(None, help="Target web application URL"),
    url: str | None = typer.Option(None, help="Target web application URL"),
    spec: str | None = typer.Option(None, help="Expected behavior description or path to a Markdown spec file"),
    output: Path = typer.Option(settings.artifact_dir, help="Directory for run evidence"),  # noqa: B008
    journeys: Path | None = typer.Option(None, help="JSON file containing explicit TestCase objects"),  # noqa: B008
    stubs: bool = typer.Option(False, "--stubs", help="Run all role interfaces against golden fixtures; no browser or network required"),
    real: str | None = typer.Option(
        None, "--real", help="Comma-separated roles to replace (for example: explorer,tester)"
    ),
) -> None:
    """Run the fixture skeleton or inspect a target and execute supplied journeys."""
    _run(url or target_url, spec, output, journeys, stubs, real, orchestrated=True)


@app.command()
def resume(
    run_id: str = typer.Argument(..., help="Run ID to resume from its latest SQLite checkpoint"),
    output: Path = typer.Option(settings.artifact_dir, help="Directory containing the run artifacts"),  # noqa: B008
) -> None:
    """Resume an interrupted LangGraph run from its per-run SQLite checkpoint."""
    from argus.graph.build import run_supervisor
    from argus.supervisor.live_components import build_live_components

    layout = RunArtifactLayout(output / "runs", run_id)
    try:
        metadata = json.loads((layout.run_dir / "run.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"No resumable run metadata found for {run_id}") from exc
    components = build_live_components(
        run_id=run_id, target_url=metadata["target_url"], layout=layout.initialize(),
    )
    result = run_supervisor(
        components,
        target_url=metadata["target_url"],
        spec_description=metadata["spec_description"],
        output_dir=output,
        run_id=run_id,
        resume=True,
    )
    print(f"[green]Run resumed[/green]: {run_id}")
    print(f"Evidence: {result['artifact_dir']}")


def _default_snapshot_path(url: str) -> Path:
    parsed = urlsplit(url)
    host = re.sub(r"[^A-Za-z0-9._-]+", "_", parsed.netloc).strip("._-") or "page"
    path = re.sub(r"[^A-Za-z0-9._-]+", "_", parsed.path.strip("/"))
    stem = f"{host}_{path}" if path else f"{host}_index"
    return settings.artifact_dir / "snapshots" / f"{stem[:150]}.json"


@app.command()
def snapshot(
    url: str = typer.Argument(..., help="HTTP(S) page URL to snapshot"),
    output: Path | None = typer.Option(None, "--output", help="JSON output file (default: artifacts/snapshots/<page>.json)"),  # noqa: B008
    max_tokens: int = typer.Option(1500, "--max-tokens", min=1, max=1500,
                                   help="Maximum estimated tokens in the compact prompt rendering"),
) -> None:
    """Write a page ARIA snapshot and semantic element catalog as JSON."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise typer.BadParameter("URL must use http:// or https://", param_hint="url")

    from argus.browser.session import BrowserSessionFactory
    from argus.perception.a11y import inspect_page

    destination = output or _default_snapshot_path(url)

    async def capture() -> dict:
        async with BrowserSessionFactory(artifact_dir=destination.parent / "browser") as factory:
            session, _ = await factory.new_context(settings.browser)
            try:
                await session.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                return await inspect_page(session.page, max_tokens=max_tokens)
            finally:
                await session.close()

    result = asyncio.run(capture())
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    visible_total = sum(1 for item in result["elements"] if item["visible"])
    print(f"[green]Snapshot saved[/green]: {destination}")
    print(f"Page: {result['title'] or '(untitled)'} — {result['url']}")
    print(f"Controls: {len(result['elements'])} total, {visible_total} visible")
    print(f"Strict-mode locators: {result['visible_strict_mode_resolved']}/{visible_total} visible controls "
          f"({result['visible_strict_mode_resolution_rate']:.1%})")
    print(f"Compact rendering: {result['compact_token_estimate']}/{max_tokens} estimated tokens")


@app.command()
def crawl(
    url: str = typer.Argument(..., help="Starting HTTP(S) URL for same-origin crawling"),
    output: Path = typer.Option(  # noqa: B008
        Path("artifacts/app_graph.json"), "--output", help="Validated AppGraph JSON output"
    ),
    max_pages: int = typer.Option(50, "--max-pages", min=1, help="Maximum pages to visit"),
    max_steps: int = typer.Option(500, "--max-steps", min=1, help="Maximum navigation/click steps"),
) -> None:
    """Crawl an application deterministically and write its app graph."""
    from argus.agents.explorer_crawler import crawl_app

    graph = asyncio.run(
        crawl_app(url, output, max_pages=max_pages, max_steps=max_steps)
    )
    print(f"[green]Crawl complete[/green]: {len(graph.nodes)} states, {len(graph.edges)} transitions")
    print(f"App graph: {output}")

