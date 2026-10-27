from __future__ import annotations

import asyncio

from argus.supervisor import loop as supervisor
from argus_contracts.models import BindingResult, Evidence
from argus_contracts.models import TestCase as ContractTestCase


def test_supervisor_runs_twenty_cases_in_isolated_contexts_with_four_workers(tmp_path, monkeypatch):
    state = {"active": 0, "max_active": 0, "executed_sessions": [], "factories": []}

    class FakePage:
        url = "https://example.test"

        async def goto(self, *args, **kwargs):
            return None

    class FakeSession:
        def __init__(self, factory):
            self.factory = factory
            self.page = FakePage()
            self.closed = False

        async def close(self):
            if not self.closed:
                self.closed = True
                state["active"] -= 1
                self.factory.semaphore.release()

    class FakeBrowserFactory:
        def __init__(self, **kwargs):
            self.semaphore = asyncio.Semaphore(4)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def new_context(self, *args, **kwargs):
            await self.semaphore.acquire()
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            return FakeSession(self), None

    class FakeGateway:
        pass

    cases = [
        ContractTestCase(id=f"case-{index:02d}", journey=f"Journey {index}",
                         description=f"Run isolated case {index}")
        for index in range(20)
    ]

    async def fake_explore(page):
        return "snapshot", []

    def fake_playbook(spec, elements):
        return []

    async def fake_bind(test_cases, elements, *, gateway, run_id):
        return [BindingResult(test_case=case, verdict="BOUND") for case in test_cases]

    async def fake_execute(session, case, layout, *, initial_url, data_factory=None, on_action=None):
        state["executed_sessions"].append(session)
        state["factories"].append(data_factory)
        await asyncio.sleep(0.01)
        return "PASS", Evidence(steps=case.steps, actual="ok"), 10

    monkeypatch.setattr(supervisor, "BrowserSessionFactory", FakeBrowserFactory)
    monkeypatch.setattr(supervisor, "ModelGateway", FakeGateway)
    monkeypatch.setattr(supervisor, "explore", fake_explore)
    monkeypatch.setattr(supervisor, "generate_playbook", fake_playbook)
    monkeypatch.setattr(supervisor, "bind_cases", fake_bind)
    monkeypatch.setattr(supervisor, "execute_case", fake_execute)

    async def scenario():
        return await supervisor.run_qa(
            "https://example.test", "A sample app", journeys=cases, output_dir=tmp_path,
        )

    summary = asyncio.run(scenario())

    assert len(summary["test_results"]) == 20
    assert len(state["executed_sessions"]) == 20
    assert len({id(session) for session in state["executed_sessions"]}) == 20
    assert state["max_active"] == 4
    assert len({id(factory) for factory in state["factories"]}) == 1
    assert all(result["verdict"] == "PASS" for result in summary["test_results"])
