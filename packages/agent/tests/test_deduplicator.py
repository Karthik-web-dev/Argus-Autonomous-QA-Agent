from __future__ import annotations

from argus.reporter.deduplicator import deduplicate, deduplicate_findings
from argus.reporter.severity import apply_severity, confidence_score, severity_for
from argus_contracts.models import (
    BugReport,
    Evidence,
    Finding,
    GateResult,
    VerificationResult,
)


def _finding(finding_id: str, signature: str, paths: list[str], confidence: float = 0.8) -> Finding:
    return Finding(
        id=finding_id, oracle_id="http-status", symptom_signature=signature,
        confidence=confidence, evidence_ref=f"evidence/{finding_id}", affected_paths=paths,
    )


def _report(report_id: str, finding_id: str, title: str, paths: list[str]) -> BugReport:
    return BugReport(
        id=report_id, severity="P2", title=title, category="functional",
        expected="Expected", actual="Actual", evidence=Evidence(finding_id=finding_id),
        affected_paths=paths,
    )


def test_ten_duplicate_500_findings_merge_all_paths_into_one_group():
    findings = [
        _finding(f"finding-{index}", "POST /orders returned 500", [f"/orders/{index}"])
        for index in range(10)
    ]
    reports = [
        _report(f"BUG-{index}", finding.id, f"500 on request {index}", finding.affected_paths)
        for index, finding in enumerate(findings)
    ]

    groups = deduplicate(reports, findings={finding.id: finding for finding in findings})

    assert len(groups) == 1
    assert len(groups[0].report.affected_paths) == 10
    assert len(groups[0].duplicate_ids) == 9


def test_same_signature_on_different_surfaces_is_not_merged():
    findings = [
        _finding("one", "500", ["/orders/1"]),
        _finding("two", "500", ["/profiles/1"]),
    ]
    groups = deduplicate_findings(findings)
    assert len(groups) == 2


def test_fixture_category_severity_is_deterministic_and_override_wins():
    assert [severity_for(category) for category in (
        "security", "data_loss", "state_persistence", "functional", "cosmetic", "unknown",
    )] == ["P1", "P1", "P1", "P1", "P3", "P1"]
    assert severity_for("core_journey") == "P0"
    assert severity_for("edge_case") == "P2"
    assert severity_for("security", manual_override="P3") == "P3"


def test_confidence_combines_oracle_gate_and_red_team_verdict():
    finding = _finding("x", "symptom", ["/x"], confidence=0.8)
    gate = GateResult(
        finding_id="x", verdict="ACCEPTED", attempts=3, successes=2,
        threshold=2 / 3,
    )
    verification = VerificationResult(
        finding_id="x", verdict="CONFIRMED", attempts=1,
    )
    assert confidence_score(finding, gate, verification) == 0.8

    report = _report("r", "x", "failure", ["/x"])
    revised = apply_severity(
        report, finding=finding, gate=gate, verification=verification,
        manual_override="P1",
    )
    assert revised.severity == "P1"
    assert report.severity == "P2"
