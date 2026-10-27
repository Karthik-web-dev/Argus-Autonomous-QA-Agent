"""High-signal deterministic oracles for browser test executions."""

from __future__ import annotations

from collections.abc import Sequence

from argus_contracts.models import Finding

from .common import Execution
from .console import ConsoleOracle
from .http import HttpOracle
from .spec import SpecOracle

_DEFAULT_ORACLES = (SpecOracle(), HttpOracle(), ConsoleOracle())


def evaluate(execution: Execution, *, oracles: Sequence[object] = _DEFAULT_ORACLES) -> list[Finding]:
    """Evaluate one execution and return unique findings in stable order."""
    findings: list[Finding] = []
    seen: set[str] = set()
    for oracle in oracles:
        evaluate_one = getattr(oracle, "evaluate", None)
        if not callable(evaluate_one):
            raise TypeError(f"oracle {oracle!r} does not define evaluate(execution)")
        for finding in evaluate_one(execution):
            if finding.symptom_signature not in seen:
                seen.add(finding.symptom_signature)
                findings.append(finding)
    return findings


__all__ = ["ConsoleOracle", "Execution", "HttpOracle", "SpecOracle", "evaluate"]
