"""Adapters that connect the merged A/B/C implementations to role Protocols."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import (
    AppGraph,
    ElementCatalogEntry,
    Evidence,
    Finding,
    GateResult,
    ReproductionResult,
    RunEvent,
    Spec,
    TestCase,
    TestResult,
    VerificationResult,
)

from argus.browser.screencast import CdpScreencastCapture
from argus.models import ModelGateway

logger = logging.getLogger(__name__)


class LiveEventBus:
    def __init__(self, layout: RunArtifactLayout) -> None:
        self.layout = layout

    def emit(self, event: RunEvent) -> None:
        self.layout.append_event(event)


class LiveSpecParser:
    def __init__(
        self,
        run_id: str,
        gateway: ModelGateway,
        *,
        target_url: str | None = None,
        layout: RunArtifactLayout | None = None,
        on_screencast_frame: Callable[[dict], None] | None = None,
    ) -> None:
        self.run_id = run_id
        self.gateway = gateway
        self.target_url = target_url
        self.layout = layout
        self.on_screencast_frame = on_screencast_frame

    def parse(self, description: str) -> Spec:
        from argus.spec.parser import parse_spec

        async def parse_with_preview() -> Spec:
            spec_task = asyncio.create_task(
                parse_spec(description, gateway=self.gateway, run_id=self.run_id)
            )
            if not (self.target_url and self.layout and self.on_screencast_frame):
                return await spec_task

            from playwright.async_api import Error as PlaywrightError

            from argus.browser.session import BrowserSessionFactory

            factory = BrowserSessionFactory(artifact_dir=self.layout.artifacts_dir)
            session = None
            capture = None
            try:
                try:
                    await factory.start()
                    session, cdp_session = await factory.new_context("chromium")
                    if cdp_session is not None:
                        capture = CdpScreencastCapture(
                            cdp_session, self.on_screencast_frame, page=session.page,
                        )
                        await capture.start()
                    try:
                        await session.page.goto(
                            self.target_url,
                            wait_until="domcontentloaded",
                            timeout=15_000,
                        )
                    except PlaywrightError as exc:
                        logger.warning("Browser preview navigation failed: %s", exc)
                except Exception:
                    # A preview must not prevent a run from testing a target if
                    # its browser cannot launch. The live run will report its
                    # own browser/setup failure at the testing phase.
                    logger.exception("Unable to start browser preview for run %s", self.run_id)

                # Keep the preview context alive while the model call is in
                # flight so the UI receives frames instead of waiting through
                # the spec parser's potentially slow response.
                return await spec_task
            finally:
                try:
                    if capture is not None:
                        await capture.stop()
                finally:
                    try:
                        if session is not None:
                            await session.close()
                    finally:
                        await factory.close()

        return asyncio.run(parse_with_preview())


class LiveExplorer:
    def __init__(
        self,
        layout: RunArtifactLayout,
        *,
        on_screencast_frame: Callable[[dict], None] | None = None,
        on_action: Callable[[dict], None] | None = None,
    ) -> None:
        self.layout = layout
        self.on_screencast_frame = on_screencast_frame
        self.on_action = on_action

    def explore(self, target_url: str) -> tuple[AppGraph, list[ElementCatalogEntry]]:
        from argus.agents.explorer_crawler import crawl_app

        graph_path = self.layout.run_dir / "app_graph.json"
        graph = asyncio.run(
            crawl_app(
                target_url,
                graph_path,
                on_screencast_frame=self.on_screencast_frame,
                on_action=self.on_action,
            )
        )
        # The graph can contain multiple captures of a control in different
        # states. Keep a stable first-seen catalog for the binder.
        elements: dict[str, ElementCatalogEntry] = {}
        for node in graph.nodes:
            if not node.captured:
                continue
            for element in node.elements:
                elements.setdefault(element.id, element)
        return graph, list(elements.values())


class LivePlaybook:
    def __init__(self) -> None:
        self.elements: Sequence[ElementCatalogEntry] = ()

    def set_elements(self, elements: Sequence[ElementCatalogEntry]) -> None:
        self.elements = elements

    # Slow (typing 1k-10k characters, network emulation) or always-inconclusive
    # checks are skipped in live runs; they stay available to offline benchmarks.
    SKIPPED_IN_LIVE: ClassVar[frozenset[str]] = frozenset({
        "form-max-length-1024", "form-max-length-10000", "form-throttled-network",
        "form-offline-toggle", "security-idor",
        # Tabs a fixed count and presses Enter with other required fields empty, so a
        # correctly validating form "fails"; a reproducible false positive.
        "form-keyboard-submit",
    })
    # Page-level checks first: one run each, and they find the most real bugs.
    PRIORITY: ClassVar[tuple[str, ...]] = (
        "list-broken-images", "list-broken-links", "list-console-errors", "list-accessible-names",
        "security-logged-out-protected", "list-pagination-boundary", "list-zero-result-filter",
        "form-empty-required", "form-xss-payload", "security-reflected-xss", "form-double-submit",
        "form-password-masking", "form-max-length",
    )

    def generate(self, spec: Spec) -> list[TestCase]:
        from argus.config import settings
        from argus.spec.playbook import generate

        per_check: dict[str, list[TestCase]] = {}
        for case in generate(spec, self.elements):
            check_id = case.id.removeprefix("playbook-").rsplit("-element-", 1)[0]
            if check_id in self.SKIPPED_IN_LIVE:
                continue
            bucket = per_check.setdefault(check_id, [])
            if len(bucket) < settings.playbook_max_targets_per_check:
                bucket.append(case)
        rank = {check_id: index for index, check_id in enumerate(self.PRIORITY)}
        ordered = sorted(per_check, key=lambda check_id: (rank.get(check_id, len(rank)), check_id))
        cases = [case for check_id in ordered for case in per_check[check_id]]
        return cases[:settings.playbook_max_cases]


class LiveBinder:
    def __init__(self, run_id: str, gateway: ModelGateway) -> None:
        self.run_id = run_id
        self.gateway = gateway
        self.last_results = []

    def bind(self, test_cases: Sequence[TestCase], elements: Sequence[ElementCatalogEntry]) -> list[TestCase]:
        from argus.spec.binder import bind_cases

        self.last_results = asyncio.run(bind_cases(
            test_cases, elements, gateway=self.gateway, run_id=self.run_id,
        ))
        return [item.test_case for item in self.last_results]


class LiveTester:
    def __init__(
        self,
        layout: RunArtifactLayout,
        *,
        on_screencast_frame: Callable[[dict], None] | None = None,
        on_action: Callable[[dict], None] | None = None,
        finding_cases: dict[str, TestCase] | None = None,
    ) -> None:
        self.layout = layout
        self.on_screencast_frame = on_screencast_frame
        self.on_action = on_action
        self.binding_results: dict[str, dict] = {}
        # finding id -> the test case that produced it, so the gate can replay it.
        self.finding_cases: dict[str, TestCase] = finding_cases if finding_cases is not None else {}

    def set_binding_results(self, results: list[dict]) -> None:
        self.binding_results = {item["test_case"]["id"]: item for item in results}

    def run(self, test_cases: Sequence[TestCase], target_url: str) -> list[TestResult]:
        from argus.agents.tester import execute_case
        from argus.browser.session import BrowserSessionFactory
        from argus.config import settings
        from argus.oracles import Execution, evaluate

        self.emitted_finding_ids: set[str] = set()
        viewer = {"busy": False}

        def emit(event_type: str, correlation_id: str, payload: dict) -> None:
            self.layout.append_event(RunEvent(
                id=uuid4().hex, run_id=self.layout.run_dir.name, agent="tester",
                correlation_id=correlation_id, type=event_type, payload=payload,
            ))

        async def run_case(case: TestCase, factory, semaphore: asyncio.Semaphore) -> TestResult:
            binding = self.binding_results.get(case.id)
            if binding and binding["verdict"] == "INCONCLUSIVE":
                evidence = Evidence(
                    steps=case.steps,
                    expected=case.expected,
                    actual=binding.get("reason") or "Semantic binding was inconclusive.",
                )
                return TestResult(test_id=case.id, verdict="INCONCLUSIVE", evidence=evidence, duration_ms=0)
            async with semaphore:
                from argus.cancellation import is_cancelled

                if is_cancelled(self.layout.run_dir.name):
                    return TestResult(test_id=case.id, verdict="INCONCLUSIVE", duration_ms=0, evidence=Evidence(
                        steps=case.steps, expected=case.expected, actual="Run stopped by user."))
                # Only one case at a time owns the live view (screencast + cursor),
                # paced so a viewer can follow it; the rest run headless in parallel.
                foreground = not viewer["busy"] and self.on_screencast_frame is not None
                if foreground:
                    viewer["busy"] = True
                session, cdp_session = await factory.new_context(
                    settings.browser,
                    record={"trace": True},
                    artifact_id="case-" + re.sub(r"[^A-Za-z0-9._-]", "_", case.id)[:100],
                )
                screencast = (
                    CdpScreencastCapture(cdp_session, self.on_screencast_frame, page=session.page)
                    if foreground and cdp_session is not None else None
                )
                try:
                    if screencast is not None:
                        await screencast.start()
                    verdict, evidence, duration = await execute_case(
                        session,
                        case,
                        self.layout,
                        initial_url=target_url,
                        on_action=self.on_action if foreground else None,
                        step_delay_ms=settings.demo_step_delay_ms if foreground else 0,
                    )
                finally:
                    if screencast is not None:
                        await screencast.stop()
                    await session.close()
                    if foreground:
                        viewer["busy"] = False
            return TestResult(test_id=case.id, verdict=verdict, evidence=evidence, duration_ms=duration)

        async def execute() -> list[TestResult]:
            semaphore = asyncio.Semaphore(settings.test_concurrency)
            async with BrowserSessionFactory(artifact_dir=self.layout.artifacts_dir) as factory:

                async def run_and_report(case: TestCase) -> TestResult:
                    result = await run_case(case, factory, semaphore)
                    emit("test_result", case.id,
                         {"test_id": case.id, "verdict": result.verdict, "duration_ms": result.duration_ms})
                    # Stream findings as soon as a case finishes instead of after the
                    # whole test phase; IDs are deterministic, so the oracle phase
                    # later skips re-emitting them.
                    for finding in evaluate(Execution(test_case=case, result=result, target_url=target_url)):
                        finding = finding.model_copy(update={"steps": case.steps})
                        self.finding_cases.setdefault(finding.id, case)
                        if finding.id not in self.emitted_finding_ids:
                            self.emitted_finding_ids.add(finding.id)
                            emit("finding_created", case.id, finding.model_dump(mode="json"))
                    return result

                return list(await asyncio.gather(*(run_and_report(case) for case in test_cases)))

        return asyncio.run(execute())


class LiveOracle:
    def __init__(self, target_url: str) -> None:
        self.target_url = target_url
        self.test_cases: dict[str, TestCase] = {}

    def set_context(self, test_cases: Sequence[TestCase]) -> None:
        self.test_cases = {case.id: case for case in test_cases}

    def evaluate(self, result: TestResult) -> list[Finding]:
        from argus.oracles import Execution, evaluate

        case = self.test_cases.get(result.test_id)
        if case is None:
            return []
        return evaluate(Execution(test_case=case, result=result, target_url=self.target_url))


class LiveGate:
    def __init__(self, target_url: str, layout: RunArtifactLayout,
                 finding_cases: dict[str, TestCase] | None = None, *,
                 on_screencast_frame: Callable[[dict], None] | None = None,
                 on_action: Callable[[dict], None] | None = None) -> None:
        self.target_url = target_url
        self.layout = layout
        self.on_screencast_frame = on_screencast_frame
        self.on_action = on_action
        self.reproduction = {}
        self.finding_cases = finding_cases

    def evaluate(self, finding: Finding, evidence: Evidence) -> GateResult:
        from argus.agents.evidence_gate import gate_findings
        from argus.browser.session import BrowserSessionFactory

        async def gate() -> list:
            async with BrowserSessionFactory(artifact_dir=self.layout.artifacts_dir) as factory:
                return await gate_findings(
                    [finding], target_url=self.target_url, browser_factory=factory, layout=self.layout,
                )

        decisions = asyncio.run(gate())
        if not decisions:
            return GateResult(
                finding_id=finding.id, verdict="FLAKY", attempts=0, successes=0, threshold=2 / 3,
            )
        decision = decisions[0]
        self.reproduction[finding.id] = decision.reproduction
        return decision.result

    REPLAY_ATTEMPTS = 3

    def evaluate_many(self, findings: Sequence[Finding]) -> list[GateResult]:
        """Replay each distinct symptom by re-running the test case that found it.

        A replay counts as a reproduction when the same oracles, run on the fresh
        result, raise a finding with the identical symptom signature. Duplicate
        symptoms share one set of replays; every finding still gets a result.
        """
        from argus.agents.tester import execute_case
        from argus.browser.session import BrowserSessionFactory
        from argus.cancellation import is_cancelled
        from argus.config import settings
        from argus.oracles import Execution, evaluate

        groups: dict[str, list[Finding]] = {}
        for finding in findings:
            # The oracle phase lists a finding once per result that raised it.
            group = groups.setdefault(finding.symptom_signature, [])
            if all(item.id != finding.id for item in group):
                group.append(finding)
        case_for = self.finding_cases or {}
        attempts = self.REPLAY_ATTEMPTS
        threshold = 2 / 3

        viewer = {"busy": False}

        async def gate_all() -> list[tuple[list[Finding], int, int]]:
            semaphore = asyncio.Semaphore(settings.test_concurrency)
            async with BrowserSessionFactory(artifact_dir=self.layout.artifacts_dir) as factory:
                async def replay_group(group: list[Finding]) -> tuple[list[Finding], int, int]:
                    representative = group[0]
                    case = next((case_for[item.id] for item in group if item.id in case_for), None)
                    if case is None:
                        return group, 0, 0
                    successes = completed = 0
                    async with semaphore:
                        for attempt in range(attempts):
                            if is_cancelled(self.layout.run_dir.name):
                                break
                            # Stop once the verdict cannot change: 2 reproductions
                            # accept, 2 misses reject (or leave it flaky).
                            if successes >= 2 or completed - successes >= 2:
                                break
                            session, cdp_session = await factory.new_context(
                                settings.browser,
                                artifact_id=f"gate-{representative.id[:32]}-{attempt + 1}",
                            )
                            # One replay at a time is shown in the live view so the
                            # verification phase is visibly working, not frozen.
                            foreground = (not viewer["busy"] and cdp_session is not None
                                          and self.on_screencast_frame is not None)
                            screencast = None
                            if foreground:
                                viewer["busy"] = True
                                screencast = CdpScreencastCapture(cdp_session, self.on_screencast_frame,
                                                                  page=session.page)
                            try:
                                if screencast is not None:
                                    await screencast.start()
                                verdict, evidence, duration = await execute_case(
                                    session, case, self.layout, initial_url=self.target_url,
                                    on_action=self.on_action if foreground else None,
                                )
                            finally:
                                if screencast is not None:
                                    await screencast.stop()
                                await session.close()
                                if foreground:
                                    viewer["busy"] = False
                            completed += 1
                            result = TestResult(test_id=case.id, verdict=verdict, evidence=evidence,
                                                duration_ms=duration)
                            replayed = evaluate(Execution(test_case=case, result=result,
                                                          target_url=self.target_url))
                            if any(item.symptom_signature == representative.symptom_signature
                                   for item in replayed):
                                successes += 1
                    publish(group, completed, successes)
                    return group, completed, successes

                return await asyncio.gather(*(replay_group(group) for group in groups.values()))

        def decide(completed: int, successes: int) -> str:
            if successes >= 2:
                return "ACCEPTED"
            if completed - successes >= 2:
                return "REJECTED" if successes == 0 else "FLAKY"
            return "FLAKY"  # Not enough observations to decide either way.

        def gate_results(group: list[Finding], completed: int, successes: int) -> list[GateResult]:
            return [GateResult(finding_id=finding.id, verdict=decide(completed, successes),
                               attempts=completed, successes=successes, threshold=threshold)
                    for finding in group]

        def publish(group: list[Finding], completed: int, successes: int) -> None:
            # Stream verdicts as each symptom finishes so the UI never sits on "Verifying…".
            for result in gate_results(group, completed, successes):
                self.layout.append_event(RunEvent(
                    id=uuid4().hex, run_id=self.layout.run_dir.name, agent="gate",
                    correlation_id=result.finding_id, type="gate_result",
                    payload=result.model_dump(mode="json"),
                ))
            self.published_live = True

        results: list[GateResult] = []
        for group, completed, successes in asyncio.run(gate_all()):
            reproduction = ReproductionResult(attempts=completed, successes=successes,
                                              contexts=["fresh"] * completed)
            for finding in group:
                self.reproduction[finding.id] = reproduction
            results.extend(gate_results(group, completed, successes))
        return results


class LiveRedTeam:
    """Placeholder adapter until C-07 supplies the adversarial reviewer."""
    def verify(self, finding: Finding, spec: Spec, evidence: Evidence) -> VerificationResult:
        del spec, evidence
        return VerificationResult(
            finding_id=finding.id,
            verdict="INCONCLUSIVE",
            reason="Red Team review is not configured; implement it in C-07.",
        )


class LiveReporter:
    def build(self, findings, gates, verifications, evidence_by_finding):
        from argus.agents.reporter import build_report

        gate_by_id = {item.finding_id: item for item in gates}
        verification_by_id = {item.finding_id: item for item in verifications}

        async def build_all():
            reports = []
            for finding in findings:
                gate = gate_by_id.get(finding.id)
                verification = verification_by_id.get(finding.id)
                evidence = evidence_by_finding.get(finding.id)
                if not gate or not verification or evidence is None:
                    continue
                if gate.verdict != "ACCEPTED" or verification.verdict == "REFUTED":
                    continue
                # The report's numbered steps must be the ones actually executed
                # (test-data placeholders filled in), i.e. the evidence's steps.
                finding = finding.model_copy(update={"steps": list(evidence.steps)})
                try:
                    document = await build_report(
                        finding, evidence, gate=gate, verification=verification,
                    )
                except Exception:
                    logger.exception("Skipping report for %s", finding.id)
                    continue
                reports.append(document.report)
            return reports

        return asyncio.run(build_all())


class LiveExporter:
    def __init__(self, target_url: str = "") -> None:
        self.target_url = target_url

    def export(self, test_cases: Sequence[TestCase], destination: Path) -> list[Path]:
        # The supervisor passes only passing journeys: the reusable suite must be green.
        from argus.reporter.playwright_export import export_test

        return [export_test(case, destination / f"{case.id}.spec.ts", base_url=self.target_url or None)
                for case in test_cases]


def build_live_components(
    *,
    run_id: str,
    target_url: str,
    layout: RunArtifactLayout,
    on_screencast_frame: Callable[[dict], None] | None = None,
    on_action: Callable[[dict], None] | None = None,
) -> dict:
    """Return runtime roles for the actual browser pipeline."""
    from argus.components import ROLE_PROTOCOLS
    from argus.stubs import GoldenFixtures, build_demo_registry

    gateway = ModelGateway()
    # Shared between tester (writer) and gate (reader) so findings replay their own case.
    finding_cases: dict[str, TestCase] = {}
    fixtures = GoldenFixtures()
    registry = build_demo_registry(fixtures, layout)
    factories = {
        "spec_parser": lambda: LiveSpecParser(
            run_id,
            gateway,
            target_url=target_url,
            layout=layout,
            on_screencast_frame=on_screencast_frame,
        ),
        "explorer": lambda: LiveExplorer(
            layout,
            on_screencast_frame=on_screencast_frame,
            on_action=on_action,
        ),
        "playbook": LivePlaybook,
        "binder": lambda: LiveBinder(run_id, gateway),
        "tester": lambda: LiveTester(
            layout,
            on_screencast_frame=on_screencast_frame,
            on_action=on_action,
            finding_cases=finding_cases,
        ),
        "oracle": lambda: LiveOracle(target_url),
        "gate": lambda: LiveGate(
            target_url, layout, finding_cases,
            on_screencast_frame=on_screencast_frame,
            on_action=on_action,
        ),
        "red_team": LiveRedTeam,
        "reporter": LiveReporter,
        "exporter": lambda: LiveExporter(target_url),
        "event_bus": lambda: LiveEventBus(layout),
    }
    for role, factory in factories.items():
        registry.register_real(role, factory)
    return registry.build(real_roles=ROLE_PROTOCOLS.keys())
