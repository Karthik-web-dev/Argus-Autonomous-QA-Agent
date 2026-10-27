from __future__ import annotations

from argus.oracles import Execution, evaluate
from argus.oracles.console import ConsoleOracle
from argus.oracles.http import HttpOracle
from argus.oracles.spec import SpecOracle
from argus_contracts.models import (
    ConsoleEvent,
    Evidence,
    NetworkEvent,
    Step,
    TestCase,
    TestResult,
)


def _execution(
    *,
    steps: list[Step] | None = None,
    expected: str = "The action succeeds.",
    verdict: str = "PASS",
    evidence: Evidence | None = None,
) -> Execution:
    case_steps = steps or [Step(action="click", locator='role=button[name="Submit"]')]
    case = TestCase(
        id="login", journey="Log in", description="Submit login", steps=case_steps,
        expected=expected,
    )
    result = TestResult(
        test_id=case.id,
        verdict=verdict,
        duration_ms=12,
        evidence=evidence or Evidence(steps=case.steps, expected=expected),
    )
    return Execution(test_case=case, result=result, target_url="https://app.test")


def test_http_oracle_reports_interactive_server_errors_with_stable_signatures():
    execution = _execution(evidence=Evidence(
        steps=[Step(action="click")], expected="Submitting valid credentials returns 200.",
        network=[NetworkEvent(
            url="https://app.test/api/users/123?requestId=first", method="POST",
            status=500, step_index=0,
        )],
    ))
    first = HttpOracle().evaluate(execution)
    rerun = _execution(evidence=Evidence(
        steps=[Step(action="click")], expected="Submitting valid credentials returns 200.",
        network=[NetworkEvent(
            url="https://app.test/api/users/987?requestId=second", method="POST",
            status=500, step_index=0,
        )],
    ))
    second = HttpOracle().evaluate(rerun)
    assert len(first) == 1
    assert first[0].symptom_signature == second[0].symptom_signature
    assert first[0].oracle_id == "http-status"


def test_http_oracle_respects_negative_status_expectations_and_noise_allowlist():
    negative = _execution(
        expected="Invalid credentials should be rejected with HTTP 401.",
        evidence=Evidence(
            steps=[Step(action="click")], expected="Invalid credentials should be rejected with HTTP 401.",
            network=[NetworkEvent(url="https://app.test/api/login", method="POST", status=401, step_index=0)],
        ),
    )
    assert HttpOracle().evaluate(negative) == []

    noisy = _execution(evidence=Evidence(
        steps=[Step(action="click")], expected="The action succeeds.",
        network=[
            NetworkEvent(url="https://app.test/favicon.ico", status=404, step_index=0),
            NetworkEvent(url="https://www.google-analytics.com/collect", status=500, step_index=0),
            NetworkEvent(url="https://app.test/api/login", status=500, step_index=None),
        ],
    ))
    assert HttpOracle().evaluate(noisy) == []


def test_console_oracle_catches_exceptions_and_failed_resources_but_filters_noise():
    execution = _execution(evidence=Evidence(
        steps=[Step(action="click")],
        console=[
            ConsoleEvent(level="error", message="TypeError: Cannot read property id", step_index=0),
            ConsoleEvent(level="warning", message="Download the React DevTools", step_index=0),
        ],
        network=[
            NetworkEvent(url="https://app.test/assets/chunk.js", failed=True, step_index=0),
            NetworkEvent(url="https://app.test/favicon.ico", failed=True, step_index=0),
        ],
    ))
    findings = ConsoleOracle().evaluate(execution)
    assert len(findings) == 2
    assert {item.oracle_id for item in findings} == {"console-error"}


def test_spec_oracle_only_reports_code_evaluated_assertion_failures():
    failed_assertion = _execution(
        verdict="FAIL",
        evidence=Evidence(
            steps=[Step(action="assert", value="Welcome")],
            expected="User sees Welcome.", actual="AssertionError: text was absent",
            failure_kind="assertion", failed_step_index=0,
        ),
    )
    findings = SpecOracle().evaluate(failed_assertion)
    assert len(findings) == 1
    assert findings[0].oracle_id == "spec-assertion"

    timeout = _execution(
        verdict="INCONCLUSIVE",
        evidence=Evidence(steps=[Step(action="assert")], failure_kind="timeout", failed_step_index=0),
    )
    interaction_failure = _execution(
        verdict="FAIL",
        evidence=Evidence(steps=[Step(action="click")], failure_kind="interaction", failed_step_index=0),
    )
    assert SpecOracle().evaluate(timeout) == []
    assert SpecOracle().evaluate(interaction_failure) == []


def test_oracle_suite_returns_no_findings_for_a_clean_execution():
    assert evaluate(_execution()) == []
