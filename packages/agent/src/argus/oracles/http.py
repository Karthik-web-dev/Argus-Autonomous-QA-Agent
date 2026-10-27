"""HTTP status oracle for requests attributed to user actions."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from argus_contracts.models import Finding

from .common import Execution, is_ignored_resource, make_finding, normalize_endpoint

_USER_ACTIONS = {"click", "double_click", "fill", "type_text", "press", "assert_keyboard_submit"}
_EXPECTED_STATUS = re.compile(r"\b([45]\d\d)\b")
_NEGATIVE_EXPECTATION = re.compile(
    r"\b(invalid|reject(?:ed|ion)?|unauthori[sz]ed|forbidden|denied|must fail|should fail|not found)\b",
    re.IGNORECASE,
)


def _status_is_expected(expected: str, status: int) -> bool:
    declared = {int(value) for value in _EXPECTED_STATUS.findall(expected)}
    if status in declared:
        return True
    if any(code // 100 == status // 100 for code in declared):
        return True
    return bool(_NEGATIVE_EXPECTATION.search(expected) and 400 <= status < 500)


class HttpOracle:
    """Report unexpected 4xx/5xx responses caused during interactive steps."""

    oracle_id = "http-status"

    def evaluate(self, execution: Execution) -> list[Finding]:
        evidence = execution.result.evidence
        expected = evidence.expected or execution.test_case.expected
        findings: list[Finding] = []
        seen: set[str] = set()
        for event in evidence.network:
            if event.status is None or event.status < 400 or event.step_index is None:
                continue
            if event.step_index >= len(evidence.steps):
                continue
            if evidence.steps[event.step_index].action not in _USER_ACTIONS:
                continue
            if is_ignored_resource(event.url) or _status_is_expected(expected, event.status):
                continue
            endpoint = normalize_endpoint(event.url)
            signature_key = f"{event.method.upper()} {endpoint} {event.step_index}"
            if signature_key in seen:
                continue
            seen.add(signature_key)
            path = urlsplit(event.url).path or "/"
            findings.append(make_finding(
                execution,
                oracle_id=self.oracle_id,
                normalized_signal=f"{event.method.upper()} {endpoint}",
                step_index=event.step_index,
                expected=expected,
                actual=f"{event.method.upper()} {endpoint} returned HTTP {event.status}.",
                affected_path=path,
            ))
        return findings
