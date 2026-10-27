from __future__ import annotations

from pathlib import Path

import pytest

from argus.browser.session import BrowserSessionFactory
from argus.evidence.recorder import EvidenceRedactor
from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import Step, TestCase
from argus.agents.tester import execute_case


def test_redactor_masks_credentials_and_keeps_factory_values():
    redactor = EvidenceRedactor(
        secret_values=["RealPass-123"],
        synthetic_values=["FixtureToken-456"],
    )
    assert redactor.redact_text("password=RealPass-123") == "password=***"
    assert redactor.redact_text("token=FixtureToken-456") == "token=FixtureToken-456"
    assert redactor.redact_text("Authorization: Bearer abc.def.ghi") == "Authorization: ***"


async def test_three_step_flow_returns_valid_evidence_and_writes_layout(tmp_path: Path):
    layout = RunArtifactLayout(tmp_path / "runs", "run-evidence").initialize()
    factory = BrowserSessionFactory(artifact_dir=layout.artifacts_dir)
    session, _ = await factory.new_context("chromium", record={"trace": True}, artifact_id="auth-flow")
    try:
        async def serve(route):
            await route.fulfill(
                status=200,
                content_type="text/html",
                body="""<!doctype html><html><body>
                  <form><label>PIN<input type="password" id="field-one"
                    oninput="console.info('password='+this.value)"></label>
                    <label>Access token<input type="text" id="token"
                    oninput="console.info('token='+this.value)"></label>
                    <button type="button" onclick="fetch('/submit',{method:'POST'}).then(() => {
                      document.querySelector('#result').textContent='Saved';
                    })">Save</button></form><p id="result"></p>
                  </body></html>""",
            )

        await session.page.route("**/*", serve)
        await session.page.goto("https://evidence.test/")
        case = TestCase(
            id="auth-flow",
            journey="sign in and save token",
            description="Fill credentials and save.",
            steps=[
                Step(action="fill", locator="css=#field-one", value="RealPass-123"),
                Step(action="fill", locator="label=Access token", value="FixtureToken-456"),
                Step(action="click", locator="role=button[name=Save]"),
            ],
            expected="Saved",
        )
        verdict, evidence, _ = await execute_case(
            session, case, layout, synthetic_values=("FixtureToken-456",),
        )
        assert verdict == "PASS"
        assert len(evidence.step_evidence) == 3
        assert all(item.dom_snapshot for item in evidence.step_evidence)
        assert evidence.steps[0].value == "***"
        assert evidence.steps[1].value == "FixtureToken-456"
        assert evidence.trace_path and Path(evidence.trace_path).is_file()
        assert len(evidence.screenshots) >= 3
        assert all(Path(path).is_file() for path in evidence.screenshots)
        assert evidence.network and all(event.step_index is not None for event in evidence.network)
        assert any(event.step_index == 2 and event.url.endswith("/submit") for event in evidence.network)
        assert all("RealPass-123" not in event.message for event in evidence.console)
        assert any("FixtureToken-456" in event.message for event in evidence.console)
        artifact_paths = layout.initialize_finding(case.id)
        assert Path(artifact_paths["trace"]).is_file()
        assert Path(artifact_paths["network"]).is_file()
        assert Path(artifact_paths["console"]).is_file()
        assert Path(artifact_paths["screenshots"]).is_dir()
    finally:
        await factory.close()
