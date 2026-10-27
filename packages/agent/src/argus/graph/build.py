"""Sequential LangGraph orchestration for the contract-defined QA roles."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import (
    AppGraph,
    BugReport,
    ElementCatalogEntry,
    Evidence,
    Finding,
    GateResult,
    QAState,
    RunEvent,
    Spec,
    TestCase,
    TestResult,
    VerificationResult,
)

PHASES = (
    ("parse_spec", "spec_parser"),
    ("explore", "explorer"),
    ("generate_tests", "playbook"),
    ("bind", "binder"),
    ("test", "tester"),
    ("oracles", "oracle"),
    ("gate", "gate"),
    ("red_team", "red_team"),
    ("dedupe", "deduplicator"),
    ("report", "reporter"),
    ("export", "exporter"),
)

# Every persisted state field has exactly one phase owner. This mirrors the
# single-writer contract in issues.md §2.6 and prevents later graph expansion
# from silently allowing two phases to overwrite one another.
STATE_WRITERS = {
    "spec": "parse_spec",
    "app_graph": "explore",
    "discovered_elements": "explore",
    "generated_test_cases": "generate_tests",
    "test_cases": "bind",
    "binding_results": "bind",
    "test_results": "test",
    "findings": "oracles",
    "evidence_by_finding": "oracles",
    "gates": "gate",
    "gated_evidence_by_finding": "gate",
    "accepted_finding_ids": "gate",
    "rejected_finding_ids": "gate",
    "verifications": "red_team",
    "verified_finding_ids": "red_team",
    "deduplicated_findings": "dedupe",
    "bugs_found": "report",
    "exports": "export",
}


class SupervisorState(TypedDict, total=False):
    """JSON-serializable graph state; each phase owns its result fields."""

    run_id: str
    target_url: str
    spec_description: str
    output_dir: str
    explicit_journeys: list[dict[str, Any]]
    spec: dict[str, Any]
    app_graph: dict[str, Any]
    discovered_elements: list[dict[str, Any]]
    generated_test_cases: list[dict[str, Any]]
    test_cases: list[dict[str, Any]]
    binding_results: list[dict[str, Any]]
    test_results: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    deduplicated_findings: list[dict[str, Any]]
    evidence_by_finding: dict[str, dict[str, Any]]
    gated_evidence_by_finding: dict[str, dict[str, Any]]
    gates: list[dict[str, Any]]
    accepted_finding_ids: list[str]
    rejected_finding_ids: list[str]
    verifications: list[dict[str, Any]]
    verified_finding_ids: list[str]
    bugs_found: list[dict[str, Any]]
    exports: list[str]


def build_supervisor_graph(components: Mapping[str, Any], layout: RunArtifactLayout, *, checkpointer=None):
    """Build a sequential, single-writer graph around role Protocol instances.

    The registry is resolved before graph construction. A graph therefore has a
    stable component set for its lifetime, while each state field is written by
    exactly one phase as specified by the QAState ownership table.
    """
    from langgraph.graph import END, START, StateGraph

    required = {role for _, role in PHASES if role != "deduplicator"} | {"event_bus"}
    missing = required - components.keys()
    if missing:
        raise ValueError(f"Missing graph component(s): {', '.join(sorted(missing))}")

    def emit(state: SupervisorState, event_type: str, *, agent: str, payload: dict[str, Any]) -> None:
        event = RunEvent(
            id=uuid4().hex,
            run_id=state["run_id"],
            agent=agent,
            correlation_id=state["run_id"],
            type=event_type,
            payload=payload,
        )
        components["event_bus"].emit(event)

    def phase_node(phase: str, role: str, operation):
        def invoke(state: SupervisorState) -> dict[str, Any]:
            from argus.cancellation import raise_if_cancelled

            raise_if_cancelled(layout.run_dir.name)
            emit(state, "phase_changed", agent="supervisor", payload={"phase": phase})
            emit(state, "agent_active", agent=role, payload={"agent": role, "phase": phase})
            updates = operation(state)
            unexpected = {
                key for key in updates
                if key not in STATE_WRITERS or STATE_WRITERS[key] != phase
            }
            if unexpected:
                raise RuntimeError(
                    f"Phase {phase!r} attempted to write state outside its ownership: "
                    f"{', '.join(sorted(unexpected))}"
                )
            emit(state, "phase_changed", agent="supervisor", payload={"phase": phase, "status": "completed"})
            return updates

        return invoke

    def parse(state: SupervisorState) -> dict[str, Any]:
        spec = components["spec_parser"].parse(state["spec_description"])
        if state.get("explicit_journeys"):
            spec = spec.model_copy(update={
                "journeys": [TestCase.model_validate(item) for item in state["explicit_journeys"]],
            })
        return {"spec": spec.model_dump(mode="json")}

    def explore(state: SupervisorState) -> dict[str, Any]:
        graph, elements = components["explorer"].explore(state["target_url"])
        emit(state, "page_discovered", agent="explorer", payload={
            "url": state["target_url"], "page_count": len(graph.nodes), "element_count": len(elements),
        })
        return {
            "app_graph": graph.model_dump(mode="json"),
            "discovered_elements": [item.model_dump(mode="json") for item in elements],
        }

    def generate(state: SupervisorState) -> dict[str, Any]:
        spec = Spec.model_validate(state["spec"])
        generator = components["playbook"]
        set_elements = getattr(generator, "set_elements", None)
        if callable(set_elements):
            set_elements([ElementCatalogEntry.model_validate(item) for item in state["discovered_elements"]])
        cases = list(spec.journeys) + list(generator.generate(spec))
        return {"generated_test_cases": [item.model_dump(mode="json") for item in cases]}

    def bind(state: SupervisorState) -> dict[str, Any]:
        cases = [TestCase.model_validate(item) for item in state["generated_test_cases"]]
        elements = [ElementCatalogEntry.model_validate(item) for item in state["discovered_elements"]]
        bound = components["binder"].bind(cases, elements)
        updates = {"test_cases": [item.model_dump(mode="json") for item in bound]}
        binding_results = getattr(components["binder"], "last_results", None)
        if binding_results is not None:
            updates["binding_results"] = [item.model_dump(mode="json") for item in binding_results]
        return updates

    def test(state: SupervisorState) -> dict[str, Any]:
        cases = [TestCase.model_validate(item) for item in state["test_cases"]]
        set_binding_results = getattr(components["tester"], "set_binding_results", None)
        if callable(set_binding_results):
            set_binding_results(state.get("binding_results", []))
        results = components["tester"].run(cases, state["target_url"])
        covered = sum(item.verdict != "INCONCLUSIVE" for item in results)
        emit(state, "coverage_update", agent="tester", payload={
            "covered": covered,
            "total": len(cases),
            "ratio": covered / len(cases) if cases else 0.0,
            "executed": len(results),
            "planned": len(cases),
        })
        return {"test_results": [item.model_dump(mode="json") for item in results]}

    def oracles(state: SupervisorState) -> dict[str, Any]:
        results = [TestResult.model_validate(item) for item in state["test_results"]]
        by_case = {item.id: item for item in (TestCase.model_validate(row) for row in state["test_cases"])}
        set_context = getattr(components["oracle"], "set_context", None)
        if callable(set_context):
            set_context(list(by_case.values()))
        findings: list[Finding] = []
        evidence: dict[str, Evidence] = {}
        # The live tester streams findings as cases finish; don't announce them twice.
        already_emitted = set(getattr(components["tester"], "emitted_finding_ids", ()))
        for result in results:
            for finding in components["oracle"].evaluate(result):
                case = by_case.get(result.test_id)
                if case is not None:
                    finding = finding.model_copy(update={"steps": case.steps})
                findings.append(finding)
                evidence[finding.id] = result.evidence.model_copy(update={"finding_id": finding.id})
                if finding.id not in already_emitted:
                    emit(state, "finding_created", agent="oracle", payload=finding.model_dump(mode="json"))
        return {
            "findings": [item.model_dump(mode="json") for item in findings],
            "evidence_by_finding": {key: value.model_dump(mode="json") for key, value in evidence.items()},
        }

    def gate(state: SupervisorState) -> dict[str, Any]:
        findings = [Finding.model_validate(item) for item in state["findings"]]
        evidence = {key: Evidence.model_validate(item) for key, item in state["evidence_by_finding"].items()}
        evaluate_many = getattr(components["gate"], "evaluate_many", None)
        if callable(evaluate_many):
            results = evaluate_many(findings)
        else:
            results = [components["gate"].evaluate(item, evidence[item.id]) for item in findings]
        reproductions = getattr(components["gate"], "reproduction", {})
        for finding_id, reproduction in reproductions.items():
            if finding_id in evidence:
                evidence[finding_id] = evidence[finding_id].model_copy(update={"reproduction": reproduction})
        if not getattr(components["gate"], "published_live", False):
            for result in results:
                emit(state, "gate_result", agent="gate", payload=result.model_dump(mode="json"))
        return {
            "gates": [item.model_dump(mode="json") for item in results],
            "gated_evidence_by_finding": {key: value.model_dump(mode="json") for key, value in evidence.items()},
            "accepted_finding_ids": [item.finding_id for item in results if item.verdict == "ACCEPTED"],
            "rejected_finding_ids": [item.finding_id for item in results if item.verdict != "ACCEPTED"],
        }

    def red_team(state: SupervisorState) -> dict[str, Any]:
        spec = Spec.model_validate(state["spec"])
        findings = [Finding.model_validate(item) for item in state["findings"]]
        evidence = {key: Evidence.model_validate(item) for key, item in state["gated_evidence_by_finding"].items()}
        results = [components["red_team"].verify(item, spec, evidence[item.id]) for item in findings]
        for result in results:
            emit(state, "verification_result", agent="red_team", payload=result.model_dump(mode="json"))
        return {
            "verifications": [item.model_dump(mode="json") for item in results],
            "verified_finding_ids": [item.finding_id for item in results if item.verdict == "CONFIRMED"],
        }

    def dedupe(state: SupervisorState) -> dict[str, Any]:
        from argus.reporter.deduplicator import deduplicate_findings

        findings = [Finding.model_validate(item) for item in state["findings"]]
        accepted = set(state.get("accepted_finding_ids", []))
        # Represent each group with a gate-accepted member when one exists, so the
        # reporter does not silently drop a real bug because group[0] was flaky.
        unique = [next((item for item in group if item.id in accepted), group[0])
                  for group in deduplicate_findings(findings)]
        return {"deduplicated_findings": [item.model_dump(mode="json") for item in unique]}

    def report(state: SupervisorState) -> dict[str, Any]:
        findings = [Finding.model_validate(item) for item in state["deduplicated_findings"]]
        gates = [GateResult.model_validate(item) for item in state["gates"]]
        verifications = [VerificationResult.model_validate(item) for item in state["verifications"]]
        evidence = {key: Evidence.model_validate(item) for key, item in state["gated_evidence_by_finding"].items()}
        reports = components["reporter"].build(findings, gates, verifications, evidence)
        for item in reports:
            emit(state, "bug_reported", agent="reporter", payload=item.model_dump(mode="json"))
        return {"bugs_found": [item.model_dump(mode="json") for item in reports]}

    def export(state: SupervisorState) -> dict[str, Any]:
        passed = {item["test_id"] for item in state.get("test_results", []) if item.get("verdict") == "PASS"}
        cases = [TestCase.model_validate(item) for item in state["test_cases"]]
        if state.get("test_results"):
            cases = [case for case in cases if case.id in passed]
        paths = components["exporter"].export(cases, layout.tests_dir)
        return {"exports": [str(path) for path in paths]}

    operations = {
        "parse_spec": parse,
        "explore": explore,
        "generate_tests": generate,
        "bind": bind,
        "test": test,
        "oracles": oracles,
        "gate": gate,
        "red_team": red_team,
        "dedupe": dedupe,
        "report": report,
        "export": export,
    }
    builder = StateGraph(SupervisorState)
    for phase, role in PHASES:
        builder.add_node(phase, phase_node(phase, role, operations[phase]))
    builder.add_edge(START, PHASES[0][0])
    for (phase, _), (next_phase, _) in pairwise(PHASES):
        builder.add_edge(phase, next_phase)
    builder.add_edge(PHASES[-1][0], END)
    return builder.compile(checkpointer=checkpointer)


def run_supervisor(
    components: Mapping[str, Any],
    *,
    target_url: str,
    spec_description: str,
    output_dir: str | Path,
    run_id: str,
    resume: bool = False,
    journeys: list[TestCase] | None = None,
) -> dict[str, Any]:
    """Invoke or resume one graph run using its per-run SQLite checkpoint DB."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    root = Path(output_dir)
    layout = RunArtifactLayout(root / "runs", run_id).initialize()
    metadata_path = layout.run_dir / "run.json"
    if resume:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        target_url = metadata["target_url"]
        spec_description = metadata["spec_description"]
        if layout.state_path.is_file():
            saved_state = json.loads(layout.state_path.read_text(encoding="utf-8"))
            if saved_state.get("complete") is True:
                raise ValueError(f"Run {run_id} is already complete")
        _repair_event_tail(layout.events_path)
        initial_state = None
    else:
        if layout.events_path.exists():
            raise FileExistsError(f"Run already exists: {run_id}; use resume=True to continue it")
        metadata_path.write_text(json.dumps({
            "run_id": run_id,
            "target_url": target_url,
            "spec_description": spec_description,
        }, indent=2) + "\n", encoding="utf-8")
        initial_state = {
            "run_id": run_id,
            "target_url": target_url,
            "spec_description": spec_description,
            "output_dir": str(root),
            "explicit_journeys": [case.model_dump(mode="json") for case in (journeys or [])],
        }
        components["event_bus"].emit(RunEvent(
            id=uuid4().hex, run_id=run_id, agent="supervisor", correlation_id=run_id,
            type="run_started", payload={"target_url": target_url, "spec": spec_description},
        ))

    checkpointer_path = layout.run_dir / "checkpoints.sqlite3"
    with SqliteSaver.from_conn_string(str(checkpointer_path)) as checkpointer:
        graph = build_supervisor_graph(components, layout, checkpointer=checkpointer)
        try:
            result = graph.invoke(initial_state, {"configurable": {"thread_id": run_id}})
        except Exception as exc:
            components["event_bus"].emit(RunEvent(
                id=uuid4().hex, run_id=run_id, agent="supervisor", correlation_id=run_id,
                type="error", payload={"message": f"{type(exc).__name__}: {exc}"},
            ))
            raise

    parsed_spec = Spec.model_validate(result["spec"])
    findings = [Finding.model_validate(item) for item in result.get("findings", [])]
    accepted_ids = set(result.get("accepted_finding_ids", []))
    rejected_ids = set(result.get("rejected_finding_ids", []))
    verified_ids = set(result.get("verified_finding_ids", []))
    state = QAState(
        target_url=target_url,
        spec=parsed_spec,
        app_graph=AppGraph.model_validate(result.get("app_graph", {})),
        discovered_elements=[ElementCatalogEntry.model_validate(item) for item in result.get("discovered_elements", [])],
        test_cases=[TestCase.model_validate(item) for item in result.get("test_cases", [])],
        test_results=[TestResult.model_validate(item) for item in result.get("test_results", [])],
        findings=findings,
        accepted_findings=[item for item in findings if item.id in accepted_ids],
        verified_findings=[item for item in findings if item.id in verified_ids],
        rejected_findings=[item for item in findings if item.id in rejected_ids],
        bugs_found=[BugReport.model_validate(item) for item in result.get("bugs_found", [])],
        coverage={
            "journeys": sum(
                item.verdict != "INCONCLUSIVE"
                for item in (TestResult.model_validate(row) for row in result.get("test_results", []))
            ) / max(1, len(result.get("test_cases", [])))
        },
        metrics={
            "journeys": len(result.get("test_results", [])),
            "passed": sum(
                item.verdict == "PASS"
                for item in (TestResult.model_validate(row) for row in result.get("test_results", []))
            ),
            "failed": sum(
                item.verdict == "FAIL"
                for item in (TestResult.model_validate(row) for row in result.get("test_results", []))
            ),
            "raw_findings": len(findings),
            "exported_tests": len(result.get("exports", [])),
        },
        iteration=1,
        complete=True,
    )
    layout.write_state(state.model_dump(mode="json"))
    (layout.reports_dir / "bug_reports.json").write_text(json.dumps(
        [item.model_dump(mode="json") for item in state.bugs_found], indent=2,
    ) + "\n", encoding="utf-8")
    try:
        from argus.reporter.document import write_report_documents

        write_report_documents(list(state.bugs_found), layout.reports_dir,
                               target_url=target_url, run_id=run_id)
    except Exception:
        logging.getLogger(__name__).exception("Could not render the bug report document")
    components["event_bus"].emit(RunEvent(
        id=uuid4().hex, run_id=run_id, agent="supervisor", correlation_id=run_id,
        type="run_completed", payload={"status": "completed", "finding_count": len(findings)},
    ))
    return {"run_id": run_id, "artifact_dir": str(layout.run_dir), "state": state,
            "exports": result.get("exports", []), "reports": state.bugs_found}


def _repair_event_tail(events_path: Path) -> None:
    """Discard only an unterminated last record left by a hard process stop."""
    if not events_path.is_file():
        return
    content = events_path.read_bytes()
    if content and not content.endswith(b"\n"):
        last_record_end = content.rfind(b"\n") + 1
        events_path.write_bytes(content[:last_record_end])

