"""Deterministic issue grouping by symptom and affected surface."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from argus_contracts.models import BugReport, Finding


@dataclass(frozen=True)
class DeduplicatedGroup:
    """One representative report with the union of reports' affected paths."""

    report: BugReport | dict[str, Any]
    duplicate_ids: tuple[str, ...]


def deduplicate(
    reports: Iterable[BugReport | Mapping[str, Any]],
    *,
    findings: Mapping[str, Finding] | None = None,
) -> list[DeduplicatedGroup]:
    """Group reports by ``symptom_signature`` and affected surface.

    Pass findings keyed by finding ID to resolve signatures via the evidence
    finding ID. Otherwise legacy reports use their title as a
    compatibility fallback. Paths are merged as an ordered, de-duplicated
    union. The first report remains the representative and receives merged
    paths without mutating its input.
    """
    groups: OrderedDict[tuple[str, str], list[BugReport | dict[str, Any]]] = OrderedDict()
    for value in reports:
        report = value if isinstance(value, BugReport) else dict(value)
        if isinstance(report, BugReport):
            report_evidence = report.evidence.finding_id
        else:
            evidence_data = report.get("evidence")
            report_evidence = evidence_data.get("finding_id") if isinstance(evidence_data, Mapping) else None
        source_finding = (findings or {}).get(report_evidence or "")
        signature = (
            _get(report, "symptom_signature")
            or (source_finding.symptom_signature if source_finding else None)
            or _get(report, "title")
            or ""
        )
        paths = _get(report, "affected_paths", []) or []
        surface = _get(report, "affected_surface") or _surface_from_paths(paths)
        surface_key = _surface_from_paths(paths) or str(surface).casefold().strip()
        groups.setdefault((str(signature).casefold().strip(), surface_key), []).append(report)

    result: list[DeduplicatedGroup] = []
    for group in groups.values():
        representative = group[0]
        paths = list(dict.fromkeys(
            str(path)
            for item in group
            for path in (_get(item, "affected_paths", []) or [])
        ))
        if isinstance(representative, BugReport):
            merged = representative.model_copy(update={"affected_paths": paths})
        else:
            merged = {**representative, "affected_paths": paths}
        ids = tuple(str(_get(item, "id")) for item in group[1:] if _get(item, "id") is not None)
        result.append(DeduplicatedGroup(report=merged, duplicate_ids=ids))
    return result


def deduplicate_findings(findings: Iterable[Finding]) -> list[list[Finding]]:
    """Group findings by their exact symptom signature and affected surface."""
    groups: OrderedDict[tuple[str, str], list[Finding]] = OrderedDict()
    for finding in findings:
        surface = _surface_from_paths(finding.affected_paths)
        groups.setdefault((finding.symptom_signature.casefold().strip(), surface), []).append(finding)
    return list(groups.values())


def _get(report: BugReport | Mapping[str, Any], name: str, default: Any = None) -> Any:
    if isinstance(report, BugReport):
        if name == "symptom_signature":
            return getattr(report, name, None)
        if name == "affected_surface":
            return None
        return getattr(report, name, default)
    return report.get(name, default)


def _surface_from_paths(paths: Iterable[str] | None) -> str:
    """Return a stable surface key, using the first path segment as boundary."""
    normalized = sorted({str(path).strip().casefold().strip("/") for path in (paths or []) if str(path).strip()})
    return "/".join(path.split("/")[0] for path in normalized)
