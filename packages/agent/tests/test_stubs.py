from __future__ import annotations

from pathlib import Path
from typing import get_args
from typer.testing import CliRunner

from argus.interfaces import (
    Binder, EventBus, Explorer, Exporter, Gate, Oracle, PlaybookGenerator,
    RedTeam, Reporter, SpecParser, Tester,
)
from argus.cli import app
from argus.stubs import (
    FixtureBinder, FixtureEventBus, FixtureExplorer, FixtureExporter,
    FixtureGate, FixtureOracle, FixturePlaybookGenerator, FixtureRedTeam,
    FixtureReporter, FixtureSpecParser, FixtureTester, GoldenFixtures,
    run_stub_demo,
)
from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import (
    AppGraph, BugReport, ElementCatalogEntry, Evidence, Finding, GateResult,
    QAState, RunEvent, RunEventType, Spec, TestCase, TestResult, VerificationResult,
)


def test_all_golden_fixtures_parse_under_f01_models():
    fixtures = GoldenFixtures()
    assert isinstance(fixtures.spec, Spec)
    assert isinstance(fixtures.app_graph, AppGraph)
    assert all(isinstance(item, ElementCatalogEntry) for item in fixtures.elements)
    assert all(isinstance(item, TestCase) for item in fixtures.test_cases)
    assert all(isinstance(item, TestResult) for item in fixtures.test_results)
    assert all(isinstance(item, Finding) for item in fixtures.findings)
    assert all(isinstance(item, Evidence) for item in fixtures.evidence.values())
    assert all(isinstance(item, BugReport) for item in fixtures.bug_reports)
    assert all(isinstance(item, GateResult) for item in fixtures.gates)
    assert all(isinstance(item, VerificationResult) for item in fixtures.verifications)
    assert len(fixtures.run_events) == 60
    assert all(isinstance(item, RunEvent) for item in fixtures.run_events)
    assert {item.type for item in fixtures.run_events} == set(get_args(RunEventType))
    parsed_markdown = FixtureSpecParser(fixtures).parse(
        (fixtures.root / "sample_spec.md").read_text(encoding="utf-8")
    )
    assert isinstance(parsed_markdown, Spec)


def test_every_fixture_implementation_satisfies_its_protocol():
    fixtures = GoldenFixtures()
    pairs = [
        (FixtureExplorer(fixtures), Explorer), (FixtureSpecParser(fixtures), SpecParser),
        (FixturePlaybookGenerator(fixtures), PlaybookGenerator), (FixtureBinder(), Binder),
        (FixtureTester(fixtures), Tester), (FixtureOracle(fixtures), Oracle),
        (FixtureGate(fixtures), Gate), (FixtureRedTeam(fixtures), RedTeam),
        (FixtureReporter(), Reporter), (FixtureExporter(), Exporter),
        (FixtureEventBus(RunArtifactLayout(Path("runs"), "protocol-check")), EventBus),
    ]
    assert all(isinstance(instance, protocol) for instance, protocol in pairs)


def test_stub_run_assembles_roles_and_writes_contract_artifacts(tmp_path):
    result = run_stub_demo(tmp_path)
    state = QAState.model_validate_json((result["state"].model_dump_json()))
    artifact_dir = tmp_path / "runs" / result["run_id"]

    assert state.complete is True
    assert len(state.findings) == 3
    assert len(state.bugs_found) == 1  # flaky and refuted findings are not filed
    assert result["event_count"] >= 50
    assert len((artifact_dir / "events.ndjson").read_text(encoding="utf-8").splitlines()) == result["event_count"]
    assert len(list((artifact_dir / "tests").glob("*.spec.ts"))) == 3
    assert len(__import__("json").loads((artifact_dir / "reports" / "bug_reports.json").read_text(encoding="utf-8"))) == 1


def test_argus_run_stubs_cli_is_offline_and_runnable(tmp_path):
    result = CliRunner().invoke(app, ["run", "--stubs", "--output", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "60" in result.output and "events" in result.output

    legacy_result = CliRunner().invoke(app, ["--stubs", "--output", str(tmp_path / "legacy")])
    assert legacy_result.exit_code == 0, legacy_result.output
    assert "Walking skeleton complete" in legacy_result.output
