from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import (
    Evidence,
    Finding,
    RunEvent,
    RunMetrics,
    RunSummary,
    Spec,
    TestResult,
)
from playwright.async_api import Error as PlaywrightError

from argus.agents.explorer import explore
from argus.agents.tester import execute_case
from argus.browser.screencast import CdpScreencastCapture
from argus.browser.session import BrowserSessionFactory
from argus.config import settings
from argus.models import ModelGateway
from argus.oracles import Execution
from argus.oracles import evaluate as evaluate_oracles
from argus.perception.a11y import resolve_semantic_locator
from argus.spec.binder import bind_cases
from argus.spec.data_factory import TestDataFactory
from argus.spec.parser import parse_spec
from argus.spec.playbook import generate as generate_playbook
from argus.state.test_case import TestCase


async def run_qa(target_url: str, spec: str, journeys: list[TestCase] | None = None,
                 output_dir: Path | None = None, *, record_video: bool = False,
                 spec_context: dict[str, str] | None = None,
                 run_id: str | None = None,
                 data_factory: TestDataFactory | None = None,
                 on_screencast_frame: Callable[[dict[str, Any]], None] | None = None,
                 on_action: Callable[[dict[str, Any]], None] | None = None) -> dict:
    output_dir = output_dir or settings.artifact_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or uuid4().hex
    model_gateway = ModelGateway()
    layout = RunArtifactLayout(output_dir / "runs", run_id).initialize()
    layout.append_event(RunEvent(id=uuid4().hex, run_id=run_id, agent="supervisor",
                                 correlation_id=run_id, type="run_started",
                                 payload={"target_url": target_url, "spec": spec}))
    async with BrowserSessionFactory(artifact_dir=layout.artifacts_dir) as browser_factory:
        exploration_session, cdp_session = await browser_factory.new_context(settings.browser)
        page = exploration_session.page
        capture = None
        if on_screencast_frame is not None and cdp_session is not None:
            capture = CdpScreencastCapture(cdp_session, on_screencast_frame, page=page)
            await capture.start()
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            snapshot, inventory = await explore(page)
            # A normal UI run currently has no generated test journeys. Move the
            # real Playwright mouse to the first visible control so D-03 still
            # has a truthful action cue to render during initial exploration.
            for element in inventory:
                if not (element.visible and element.enabled and element.in_viewport):
                    continue
                try:
                    locator = resolve_semantic_locator(page, element.semantic_locator)
                    box = await locator.first.bounding_box()
                    if box is None:
                        continue
                    viewport = await page.evaluate(
                        "() => ({width: innerWidth, height: innerHeight})"
                    )
                    x = box["x"] + box["width"] / 2
                    y = box["y"] + box["height"] / 2
                    await page.mouse.move(x, y)
                    action = {
                        "action": "inspect",
                        "locator": element.semantic_locator,
                        "x": x,
                        "y": y,
                        "width": box["width"],
                        "height": box["height"],
                        "viewport_width": viewport["width"],
                        "viewport_height": viewport["height"],
                        "rationale": f"Inspect the visible {element.role} {element.name!r} during page exploration.",
                    }
                    layout.append_event(RunEvent(
                        id=uuid4().hex,
                        run_id=run_id,
                        agent="explorer",
                        correlation_id=run_id,
                        type="action",
                        payload=action,
                    ))
                    if on_action is not None:
                        on_action(action)
                    break
                except (PlaywrightError, ValueError):
                    # A stale or unusual catalog locator must not fail page inspection.
                    continue
            layout.append_event(RunEvent(id=uuid4().hex, run_id=run_id, agent="explorer",
                                         correlation_id=run_id, type="page_discovered",
                                         payload={"url": page.url, "element_count": len(inventory)}))
        finally:
            if capture is not None:
                await capture.stop()
            await exploration_session.close()
        data_factory = data_factory or TestDataFactory()
        parsed_spec = None
        if journeys is None:
            parsed_spec = await parse_spec(
                spec, context=spec_context, gateway=model_gateway, run_id=run_id,
            )
            candidate_cases = list(parsed_spec.journeys)
        else:
            candidate_cases = list(journeys)
        playbook_spec = parsed_spec or Spec(description=spec)
        candidate_cases.extend(generate_playbook(playbook_spec, inventory))
        bindings = await bind_cases(
            candidate_cases, inventory, gateway=model_gateway, run_id=run_id,
        )

        async def execute_binding(binding):
            case = binding.test_case
            case_findings: list[Finding] = []
            if binding.verdict == "INCONCLUSIVE":
                result = TestResult(
                    test_id=case.id,
                    verdict="INCONCLUSIVE",
                    evidence=Evidence(steps=case.steps, expected=case.expected,
                                      actual=binding.reason),
                    duration_ms=0,
                )
                duration = 0
                verdict = "INCONCLUSIVE"
            else:
                case_session, case_cdp = await browser_factory.new_context(
                    settings.browser,
                    record={"trace": True, "video": record_video},
                    artifact_id="case-" + uuid4().hex[:24],
                )
                case_capture = None
                if on_screencast_frame is not None and case_cdp is not None:
                    case_capture = CdpScreencastCapture(
                        case_cdp, on_screencast_frame, page=case_session.page,
                    )
                    await case_capture.start()
                try:
                    verdict, evidence, duration = await execute_case(
                        case_session, case, layout, initial_url=target_url,
                        data_factory=data_factory, on_action=on_action,
                    )
                finally:
                    if case_capture is not None:
                        await case_capture.stop()
                    await case_session.close()
                result = TestResult(test_id=case.id, verdict=verdict,
                                    evidence=evidence, duration_ms=duration)
            case_findings = evaluate_oracles(Execution(
                test_case=case,
                result=result,
                target_url=target_url,
            ))
            for finding in case_findings:
                layout.append_event(RunEvent(
                    id=uuid4().hex,
                    run_id=run_id,
                    agent="oracle",
                    correlation_id=case.id,
                    type="finding_created",
                    payload=finding.model_dump(mode="json"),
                ))
            layout.append_event(RunEvent(id=uuid4().hex, run_id=run_id, agent="tester",
                                         correlation_id=case.id, type="test_result",
                                         payload={"test_id": case.id, "verdict": verdict,
                                                  "duration_ms": duration,
                                                  "finding_count": len(case_findings)}))
            return result, case_findings

        # BrowserSessionFactory bounds active contexts; gather uses the pool while
        # keeping each test case in its own browser context.
        completed = await asyncio.gather(*(execute_binding(binding) for binding in bindings))
        results = [result for result, _ in completed]
        findings = [finding for _, case_findings in completed for finding in case_findings]
    summary = RunSummary(
        run_id=run_id, artifact_dir=str(layout.run_dir), target_url=target_url,
        spec=spec, parsed_spec=parsed_spec, test_cases=candidate_cases,
        accessibility_snapshot=snapshot,
        discovered_elements=inventory, test_results=results,
        findings=findings,
        metrics=RunMetrics(journeys=len(results),
                           passed=sum(r.verdict == "PASS" for r in results),
                           failed=sum(r.verdict == "FAIL" for r in results),
                           raw_findings=len(findings)),
    )
    result = summary.model_dump(mode="json")
    layout.write_state(result)
    layout.append_event(RunEvent(id=uuid4().hex, run_id=run_id, agent="supervisor",
                                 correlation_id=run_id, type="run_completed",
                                 payload={"status": "completed", "finding_count": len(findings),
                                          "artifact_dir": str(layout.run_dir)}))
    return result
