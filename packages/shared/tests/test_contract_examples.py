from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest
from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import (
    AppGraph,
    AppGraphEdge,
    AppGraphNode,
    BugReport,
    ConsoleEvent,
    CreateRunRequest,
    ElementCatalogEntry,
    Evidence,
    Finding,
    GateResult,
    ManifestBug,
    NetworkEvent,
    QAState,
    ReproductionResult,
    RunEvent,
    RunEventType,
    RunMetrics,
    RunSummary,
    Spec,
    SpecClaim,
    SpecEntity,
    Step,
    StepEvidence,
    TestCase,
    TestResult,
    ValidationRule,
    VerificationResult,
)
from pydantic import ValidationError

EXAMPLES = [
    (SpecClaim, {"id": "claim-1", "statement": "Login succeeds", "priority": "high"}, {"id": "", "statement": ""}),
    (SpecEntity, {"name": "Article", "fields": ["title", "body"]}, {"name": ""}),
    (ValidationRule, {"field": "email", "rule": "valid email"}, {"field": "email", "rule": ""}),
    (Step, {"action": "click", "locator": "role=button[name=Save]"}, {"action": "teleport"}),
    (TestCase, {"id": "tc-1", "journey": "login", "description": "User logs in"}, {"id": "", "journey": "", "description": ""}),
    (Spec, {"description": "A user can log in"}, {"description": ""}),
    (ElementCatalogEntry, {"id": "el-1", "role": "button", "semantic_locator": "role=button[name=Save]", "visible": True, "enabled": True, "in_viewport": True}, {"id": "", "role": "", "semantic_locator": "", "visible": True, "enabled": True, "in_viewport": True}),
    (AppGraph, {"adjacency": {"/": ["/login"]}}, {"adjacency": []}),
    (AppGraphNode, {"id": "state-1", "url": "http://example.test/", "signature": "abc123"}, {"id": "", "url": "", "signature": ""}),
    (AppGraphEdge, {"source": "state-1", "target": "state-2", "action": "link", "locator": "link:Login"}, {"source": "state-1", "target": "state-2", "action": "submit", "locator": ""}),
    (NetworkEvent, {"url": "/api/login", "status": 200, "step_index": 2}, {"url": "/api/login", "status": 99, "step_index": -1}),
    (ConsoleEvent, {"level": "error", "message": "Unhandled exception"}, {"level": "fatal", "message": "x"}),
    (ReproductionResult, {"attempts": 3, "successes": 2, "contexts": ["fresh", "fresh", "fresh"]}, {"attempts": -1}),
    (StepEvidence, {"step_index": 0, "screenshot": "screenshots/step-000.png", "dom_snapshot": "button Save"}, {"step_index": -1}),
    (Evidence, {"expected": "Saved", "actual": "Error", "screenshots": ["after.png"]}, {"network": "not-an-array"}),
    (Finding, {"id": "f-1", "oracle_id": "http-500", "symptom_signature": "POST /api/login returned 500", "confidence": 0.9, "evidence_ref": "artifacts/f-1"}, {"id": "f-1", "oracle_id": "http-500", "symptom_signature": "error", "confidence": 2, "evidence_ref": "x"}),
    (GateResult, {"finding_id": "f-1", "verdict": "ACCEPTED", "attempts": 3, "successes": 2, "threshold": 0.66}, {"finding_id": "f-1", "verdict": "MAYBE", "attempts": 3, "successes": 2, "threshold": 0.66}),
    (VerificationResult, {"finding_id": "f-1", "verdict": "CONFIRMED", "attempts": 5}, {"finding_id": "f-1", "verdict": "UNKNOWN"}),
    (BugReport, {"id": "bug-1", "severity": "P1", "title": "Login fails", "category": "functional", "expected": "Login succeeds", "actual": "HTTP 500", "evidence": {}}, {"id": "bug-1", "severity": "P9", "title": "x", "category": "functional", "expected": "x", "actual": "y", "evidence": {}}),
    (ManifestBug, {"id": "N1", "class": "network", "title": "API error behind success toast"}, {"id": "N1", "class": "network", "title": "x", "verified": "sometimes"}),
    (RunEvent, {"id": "e-1", "run_id": "r-1", "agent": "explorer", "correlation_id": "c-1", "type": "run_started", "payload": {"url": "https://example.test"}}, {"id": "e-1", "run_id": "r-1", "agent": "explorer", "correlation_id": "c-1", "type": "unknown_event"}),
    (TestResult, {"test_id": "tc-1", "verdict": "PASS", "evidence": {}, "duration_ms": 120}, {"test_id": "tc-1", "verdict": "PASS", "evidence": {}, "duration_ms": -1}),
    (QAState, {}, {"iteration": -1}),
    (CreateRunRequest, {"url": "https://example.test", "spec": "User can sign in"}, {"url": "file:///etc/passwd", "spec": ""}),
    (RunMetrics, {"journeys": 2, "passed": 1, "failed": 1}, {"journeys": -1}),
    (RunSummary, {"run_id": "run-1", "artifact_dir": "runs/run-1", "target_url": "https://example.test", "spec": "Smoke check"}, {"run_id": "", "artifact_dir": "", "target_url": "not a url", "spec": ""}),
]


@pytest.mark.parametrize("model,valid,invalid", EXAMPLES, ids=[example[0].__name__ for example in EXAMPLES])
def test_each_contract_accepts_valid_and_rejects_invalid_example(model, valid, invalid):
    assert isinstance(model.model_validate(valid), model)
    with pytest.raises(ValidationError):
        model.model_validate(invalid)


def test_artifact_layout_appends_validated_ndjson_event(tmp_path):
    from argus_contracts.models import RunEvent

    layout = RunArtifactLayout(tmp_path / "runs", "run-001").initialize()
    artifact_paths = layout.initialize_finding("finding-001")
    layout.append_event(RunEvent(
        id="event-001", run_id="run-001", agent="explorer", correlation_id="corr-001",
        type="page_discovered", payload={"url": "/login"},
    ))

    assert layout.events_path.read_text(encoding="utf-8").count("\n") == 1
    assert artifact_paths["screenshots"].is_dir()
    assert artifact_paths["trace"].name == "trace.zip"
    assert artifact_paths["network"].name == "network.json"
    with pytest.raises(ValueError):
        layout.finding_dir("../outside")


def test_qastate_fields_match_single_writer_contract_table():
    expected = {
        "target_url", "spec", "app_graph", "discovered_elements", "test_cases",
        "test_results", "findings", "accepted_findings", "verified_findings",
        "rejected_findings", "bugs_found", "coverage", "metrics", "iteration", "complete",
    }
    assert set(QAState.model_fields) == expected


def test_each_run_event_type_has_a_contracts_payload_example():
    contracts = Path(__file__).resolve().parents[3] / "CONTRACTS.md"
    content = contracts.read_text(encoding="utf-8")
    for event_type in get_args(RunEventType):
        assert f"| `{event_type}` |" in content
