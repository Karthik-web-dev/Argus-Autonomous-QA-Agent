from __future__ import annotations

import asyncio
import json

from argus.supervisor import loop as supervisor
from argus_contracts.models import (
    BindingResult,
    Evidence,
    Finding,
    Step,
)
from argus_contracts.models import (
    TestCase as ContractTestCase,
)


def test_supervisor_records_oracle_findings_in_events_and_run_summary(tmp_path, monkeypatch):
    case = ContractTestCase(
        id="server-error", journey="Submit form", description="Submit valid form data",
        steps=[Step(action="click", locator='role=button[name="Submit"]')],
    )

    class FakePage:
        url = "https://example.test"

        async def goto(self, *args, **kwargs):
            return None

    class FakeSession:
        def __init__(self):
            self.page = FakePage()

        async def close(self):
            return None

    class FakeBrowserFactory:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def new_context(self, *args, **kwargs):
            return FakeSession(), None

    class FakeGateway:
        pass

    async def fake_explore(page):
        return "snapshot", []

    def fake_playbook(spec, elements):
        return []

    async def fake_bind(cases, elements, *, gateway, run_id):
        return [BindingResult(test_case=case, verdict="BOUND") for case in cases]

    async def fake_execute(session, test_case, layout, *, initial_url, data_factory=None, on_action=None):
        return "FAIL", Evidence(
            steps=test_case.steps, expected="The request succeeds.",
            actual="POST /api/items returned HTTP 500.",
        ), 8

    def fake_oracles(execution):
        return [Finding(
            id="finding-test",
            oracle_id="http-status",
            symptom_signature="stable-signature",
            confidence=0.95,
            steps=execution.result.evidence.steps,
            evidence_ref="test-results/server-error",
            expected=execution.result.evidence.expected,
            actual=execution.result.evidence.actual,
            affected_paths=["/api/items"],
        )]

    monkeypatch.setattr(supervisor, "BrowserSessionFactory", FakeBrowserFactory)
    monkeypatch.setattr(supervisor, "ModelGateway", FakeGateway)
    monkeypatch.setattr(supervisor, "explore", fake_explore)
    monkeypatch.setattr(supervisor, "generate_playbook", fake_playbook)
    monkeypatch.setattr(supervisor, "bind_cases", fake_bind)
    monkeypatch.setattr(supervisor, "execute_case", fake_execute)
    monkeypatch.setattr(supervisor, "evaluate_oracles", fake_oracles)

    async def scenario():
        return await supervisor.run_qa(
            "https://example.test", "A sample app", journeys=[case], output_dir=tmp_path,
        )

    summary = asyncio.run(scenario())

    assert summary["metrics"]["raw_findings"] == 1
    assert [finding["oracle_id"] for finding in summary["findings"]] == ["http-status"]
    events_path = tmp_path / "runs" / summary["run_id"] / "events.ndjson"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    finding_events = [event for event in events if event["type"] == "finding_created"]
    result_events = [event for event in events if event["type"] == "test_result"]
    completed = next(event for event in events if event["type"] == "run_completed")
    assert finding_events[0]["payload"]["symptom_signature"] == "stable-signature"
    assert result_events[0]["payload"]["finding_count"] == 1
    assert completed["payload"]["finding_count"] == 1
