from __future__ import annotations

import asyncio

from argus.agents.tester import execute_case
from argus.browser.session import BrowserSessionFactory
from argus.spec.data_factory import TestDataFactory
from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import Step, TestCase


def _case(*steps: Step, expected: str = "The welcome message is visible.") -> TestCase:
    return TestCase(
        id="login", journey="Log in", description="Log in with valid credentials",
        steps=list(steps), expected=expected,
    )


def test_login_passes_on_clean_page_and_assertion_fails_on_planted_bug(tmp_path):
    async def scenario():
        async with BrowserSessionFactory(artifact_dir=tmp_path / "browser") as factory:
            clean, _ = await factory.new_context("chromium")
            await clean.page.set_content("""
                <label>Email <input aria-label="Email"></label>
                <label>Password <input aria-label="Password" type="password"></label>
                <button>Log in</button><p id="result"></p>
                <script>document.querySelector('button').onclick = () => {
                  document.querySelector('#result').textContent = 'Welcome';
                }</script>
            """)
            case = _case(
                Step(action="fill", locator='role=textbox[name="Email"]', value="{{email}}"),
                Step(action="fill", locator='role=textbox[name="Password"]', value="fixed-test-password"),
                Step(action="click", locator='role=button[name="Log in"]'),
                Step(action="assert", value="Welcome", timeout_ms=150),
            )
            reset_cases = []

            async def reset_hook(test_case, values):
                reset_cases.append((test_case.id, values["email"]))

            clean_verdict, clean_evidence, _ = await execute_case(
                clean, case, RunArtifactLayout(tmp_path / "runs", "clean-run").initialize(),
                data_factory=TestDataFactory(reset_hook=reset_hook),
            )
            assert clean_verdict == "PASS"
            assert clean_evidence.failure_kind is None
            assert len(reset_cases) == 1
            assert reset_cases[0][0] == "login"

            planted, _ = await factory.new_context("chromium")
            await planted.page.set_content("""
                <label>Email <input aria-label="Email"></label>
                <label>Password <input aria-label="Password" type="password"></label>
                <button>Log in</button><p id="result"></p>
                <script>document.querySelector('button').onclick = () => {
                  document.querySelector('#result').textContent = 'Server error';
                }</script>
            """)
            bug_verdict, bug_evidence, _ = await execute_case(
                planted, case.model_copy(update={"id": "login-planted"}),
                RunArtifactLayout(tmp_path / "runs", "bug-run").initialize(),
            )
            assert bug_verdict == "FAIL"
            assert bug_evidence.failure_kind == "assertion"
            assert bug_evidence.failed_step_index == 3
            assert "not satisfied" in bug_evidence.actual

    asyncio.run(scenario())


def test_step_timeout_is_inconclusive_and_action_events_are_emitted(tmp_path):
    async def scenario():
        async with BrowserSessionFactory(artifact_dir=tmp_path / "browser") as factory:
            session, _ = await factory.new_context("chromium")
            await session.page.set_content("<button>Ready</button>")
            case = _case(Step(
                action="click", locator='role=button[name="Missing"]', timeout_ms=20,
            ))
            layout = RunArtifactLayout(tmp_path / "runs", "timeout-run").initialize()
            verdict, evidence, _ = await execute_case(session, case, layout)
            assert verdict == "INCONCLUSIVE"
            assert evidence.failure_kind == "timeout"
            assert evidence.failed_step_index == 0
            events = [line for line in layout.events_path.read_text(encoding="utf-8").splitlines()]
            assert ["\"type\":\"action\"" in line for line in events] == [True, True]

    asyncio.run(scenario())


def test_data_factory_is_unique_under_four_concurrent_workers_and_resets_each_case():
    reset_cases: list[str] = []

    async def reset(case: TestCase, values):
        await asyncio.sleep(0)
        reset_cases.append(case.id + values["unique"])

    factory = TestDataFactory(reset_hook=reset)
    case = _case(Step(action="fill", value="{{email}}"))

    async def worker(_index: int):
        prepared = await asyncio.to_thread(factory.prepare, case)
        await factory.reset(prepared)
        return prepared

    async def scenario():
        prepared = await asyncio.gather(*(worker(index) for index in range(80)))
        emails = [item.test_case.steps[0].value for item in prepared]
        assert len(set(emails)) == 80
        assert len(reset_cases) == 80
        assert all(item.test_case.steps[0].value in item.synthetic_values for item in prepared)

    asyncio.run(scenario())
