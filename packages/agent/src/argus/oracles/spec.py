"""Spec-derived oracle for explicit, code-evaluated assertion failures."""

from __future__ import annotations

from argus_contracts.models import Finding

from .common import Execution, make_finding, normalize_message


class SpecOracle:
    """Convert a failed declared assertion into a spec-claim finding."""

    oracle_id = "spec-assertion"

    def evaluate(self, execution: Execution) -> list[Finding]:
        result = execution.result
        evidence = result.evidence
        if (
            result.verdict != "FAIL"
            or evidence.failure_kind != "assertion"
            or evidence.failed_step_index is None
        ):
            return []
        assertion = evidence.steps[evidence.failed_step_index]
        expected = evidence.expected or execution.test_case.expected or assertion.value or "Declared assertion passes."
        actual = evidence.actual or "Declared assertion failed."
        return [make_finding(
            execution,
            oracle_id=self.oracle_id,
            normalized_signal=normalize_message(actual),
            step_index=evidence.failed_step_index,
            expected=expected,
            actual=actual,
        )]
