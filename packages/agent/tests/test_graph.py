from __future__ import annotations

import json
from pathlib import Path

import pytest
from argus.graph.build import PHASES, run_supervisor
from argus.stubs import GoldenFixtures, build_demo_registry
from argus_contracts.artifacts import RunArtifactLayout


class _CountedParser:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.calls = 0

    def parse(self, description):
        self.calls += 1
        return self.delegate.parse(description)


class _FailOnceExporter:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.calls = 0

    def export(self, test_cases, destination):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("simulated interruption during export")
        return self.delegate.export(test_cases, destination)


def _fixture_components(output: Path, run_id: str, *, fail_export_once: bool = False):
    layout = RunArtifactLayout(output / "runs", run_id).initialize()
    fixtures = GoldenFixtures()
    components = build_demo_registry(fixtures, layout).build()
    parser = _CountedParser(components["spec_parser"])
    exporter = _FailOnceExporter(components["exporter"]) if fail_export_once else components["exporter"]
    components["spec_parser"] = parser
    components["exporter"] = exporter
    return layout, components, parser, exporter, fixtures


def test_fixture_graph_runs_each_role_and_writes_full_event_trace(tmp_path):
    run_id = "fixture-graph"
    layout, components, _parser, _exporter, fixtures = _fixture_components(tmp_path, run_id)

    result = run_supervisor(
        components,
        target_url="http://localhost:3100",
        spec_description=fixtures.spec.description,
        output_dir=tmp_path,
        run_id=run_id,
    )

    events = [json.loads(line) for line in layout.events_path.read_text(encoding="utf-8").splitlines()]
    active_phases = {event["payload"]["phase"] for event in events if event["type"] == "agent_active"}
    completed_phases = {
        event["payload"]["phase"]
        for event in events
        if event["type"] == "phase_changed" and event["payload"].get("status") == "completed"
    }
    assert active_phases == {phase for phase, _role in PHASES}
    assert completed_phases == {phase for phase, _role in PHASES}
    assert events[0]["type"] == "run_started"
    assert events[-1]["type"] == "run_completed"
    assert result["state"].complete
    assert result["state"].test_results
    assert result["exports"]
    assert json.loads(layout.state_path.read_text(encoding="utf-8"))["complete"] is True


def test_resume_continues_from_last_sqlite_checkpoint_without_repeating_phases(tmp_path):
    run_id = "resume-graph"
    layout, components, parser, exporter, fixtures = _fixture_components(
        tmp_path, run_id, fail_export_once=True,
    )
    args = {
        "target_url": "http://localhost:3100",
        "spec_description": fixtures.spec.description,
        "output_dir": tmp_path,
        "run_id": run_id,
    }

    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_supervisor(components, **args)
    assert parser.calls == 1
    assert exporter.calls == 1

    result = run_supervisor(components, **args, resume=True)

    assert parser.calls == 1
    assert exporter.calls == 2
    assert result["state"].complete
    events = [json.loads(line) for line in layout.events_path.read_text(encoding="utf-8").splitlines()]
    assert sum(event["type"] == "run_completed" for event in events) == 1
    assert any(event["type"] == "error" for event in events)

