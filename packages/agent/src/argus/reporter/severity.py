"""Deterministic severity and confidence scoring for reported findings."""

from __future__ import annotations

from typing import Literal

from argus_contracts.models import BugReport, Finding, GateResult, VerificationResult

Severity = Literal["P0", "P1", "P2", "P3"]
_RANK: dict[Severity, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def severity_for(
    category: str,
    *,
    impact: str | None = None,
    manual_override: Severity | None = None,
) -> Severity:
    """Apply dossier severity rubric, with a caller-supplied severity override.

    P0 means a core journey is broken; P1 a documented path is broken; P2
    covers broken edge cases and accessibility violations; P3 is cosmetic or
    a minor UX issue. ``impact`` may identify a core route or journey.
    """
    if manual_override is not None:
        if manual_override not in _RANK:
            raise ValueError(f"Unsupported severity override: {manual_override!r}")
        return manual_override

    normalized_category = category.casefold().replace("-", "_").replace(" ", "_")
    normalized_impact = (impact or "").casefold().replace("-", "_").replace(" ", "_")
    if normalized_category in {"core_journey", "core_functional", "core_flow"} or normalized_impact in {
        "core", "core_journey", "core_flow",
    }:
        return "P0"
    if normalized_category in {"documented_path", "functional", "state_persistence", "security", "data_loss"} or normalized_impact in {
        "documented", "documented_path",
    }:
        return "P1"
    if normalized_category in {"edge_case", "accessibility", "a11y"}:
        return "P2"
    if normalized_category in {"cosmetic", "visual", "minor_ux"}:
        return "P3"
    return "P1" if normalized_category else "P2"


def confidence_score(
    finding: Finding,
    gate: GateResult,
    verification: VerificationResult,
) -> float:
    """Combine oracle confidence, replay result, and independent review.

    The dossier asks for these signals to contribute but specifies no weights.
    This implementation uses oracle 50%, gate reproduction rate 30%, and Red
    Team verdict 20%. Missing attempts contribute zero.
    """
    if finding.id != gate.finding_id or finding.id != verification.finding_id:
        raise ValueError("finding, gate, and verification must refer to the same finding")
    replay_score = gate.successes / gate.attempts if gate.attempts else 0.0
    review_score = {"CONFIRMED": 1.0, "INCONCLUSIVE": 0.5, "REFUTED": 0.0}[verification.verdict]
    return round(0.5 * finding.confidence + 0.3 * replay_score + 0.2 * review_score, 4)


def apply_severity(
    report: BugReport,
    *,
    finding: Finding,
    gate: GateResult,
    verification: VerificationResult,
    manual_override: Severity | None = None,
) -> BugReport:
    """Return the report's deterministic severity under the existing F-01 contract.

    Call :func:`confidence_score` when a score is needed; the current shared
    BugReport contract has no field for storing it.
    """
    severity = severity_for(
        report.category,
        impact=finding.actual,
        manual_override=manual_override,
    )
    return report.model_copy(update={"severity": severity})
