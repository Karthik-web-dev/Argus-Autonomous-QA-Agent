from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest
from argus.agents.evidence_gate import gate_findings
from argus.replay.replayer import ReplayAttempt, ReplayResult
from argus_contracts.models import Evidence, Finding


def _finding(finding_id: str, signature: str, confidence: float = 0.9) -> Finding:
    return Finding(
        id=finding_id,
        oracle_id="http-status",
        symptom_signature=signature,
        confidence=confidence,
        evidence_ref=f"artifacts/{finding_id}",
    )


def _replay_result(finding: Finding, successes: int) -> ReplayResult:
    attempts = []
    for index in range(1, 4):
        matched = index <= successes
        evidence = Evidence(
            finding_id=finding.id,
            actual=finding.symptom_signature if matched else "No observed symptom.",
            trace_path=f"artifacts/{finding.id}/replay-{index}/trace.zip",
        )
        attempts.append(ReplayAttempt(index=index, matched=matched, evidence=evidence))
    return ReplayResult(finding.id, finding.symptom_signature, tuple(attempts))


@pytest.mark.parametrize(
    ("successes", "verdict"),
    [(0, "REJECTED"), (1, "FLAKY"), (2, "ACCEPTED"), (3, "ACCEPTED")],
)
async def test_three_replay_thresholds_and_reproduction_receipts(successes: int, verdict: str):
    finding = _finding("finding-1", "POST /api/login returned 500")

    async def runner(candidate: Finding, attempts: int):
        assert candidate.id == finding.id
        assert attempts == 3
        return _replay_result(candidate, successes)

    decision = (await gate_findings([finding], replay_runner=runner))[0]

    assert decision.result.verdict == verdict
    assert decision.result.attempts == 3
    assert decision.result.successes == successes
    assert decision.result.threshold == pytest.approx(2 / 3)
    assert len(decision.result.evidence_refs) == 3
    assert decision.reproduction.attempts == 3
    assert decision.reproduction.successes == successes
    assert len(decision.reproduction.contexts) == 3
    assert decision.needs_red_team is (verdict == "FLAKY")


async def test_duplicate_signatures_are_replayed_once_per_group():
    first = _finding("finding-1", "same symptom")
    duplicate = _finding("finding-2", "same symptom", confidence=0.4)
    other = _finding("finding-3", "other symptom")
    calls: list[str] = []

    async def runner(candidate: Finding, attempts: int):
        calls.append(candidate.id)
        assert attempts == 3
        return _replay_result(candidate, 2)

    decisions = await gate_findings([first, duplicate, other], replay_runner=runner)

    assert calls == ["finding-1", "finding-3"]
    assert len(decisions) == 2
    assert decisions[0].representative_finding_id == "finding-1"
    assert decisions[0].duplicate_finding_ids == ("finding-2",)
    assert decisions[0].needs_red_team is True
    assert decisions[1].representative_finding_id == "finding-3"


async def test_low_confidence_accepted_finding_is_flagged_for_red_team():
    finding = _finding("finding-low", "low confidence symptom", confidence=0.45)

    async def runner(candidate: Finding, _attempts: int):
        return _replay_result(candidate, 3)

    decision = (await gate_findings([finding], replay_runner=runner))[0]
    assert decision.result.verdict == "ACCEPTED"
    assert decision.needs_red_team


async def test_incomplete_replay_is_flaky_and_records_the_error():
    finding = _finding("finding-slow", "slow symptom")

    async def runner(_candidate: Finding, _attempts: int):
        await asyncio.sleep(0.1)
        return _replay_result(finding, 3)

    decision = (await gate_findings(
        [finding], replay_runner=runner, timeout_seconds=0.01,
    ))[0]
    assert decision.result.verdict == "FLAKY"
    assert decision.result.attempts == 0
    assert decision.needs_red_team
    assert decision.error and "budget" in decision.error


def test_evidence_gate_has_no_model_gateway_import():
    source = Path(__file__).parents[1] / "src" / "argus" / "agents" / "evidence_gate.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imported.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names)
    assert not any(name == "argus.models" or name.startswith("argus.models.") for name in imported)
