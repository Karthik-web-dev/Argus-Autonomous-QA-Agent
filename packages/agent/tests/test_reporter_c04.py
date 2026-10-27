from __future__ import annotations

import asyncio
import json

import pytest
from argus.agents.reporter import (
    REPORT_NARRATIVE_SCHEMA,
    ReceiptValidationError,
    build_report,
    validate_receipts,
)
from argus.reporter.formatter import format_markdown
from argus.stubs import GoldenFixtures


class FakeGenerator:
    def __init__(self, result: dict[str, str]):
        self.result = result
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _inputs():
    fixtures = GoldenFixtures()
    finding = next(item for item in fixtures.findings if item.id == "finding-true")
    return (
        finding,
        fixtures.evidence_for(finding),
        next(item for item in fixtures.gates if item.finding_id == finding.id),
        next(item for item in fixtures.verifications if item.finding_id == finding.id),
    )


def test_fixture_finding_renders_dossier_report_with_deterministic_numbered_steps():
    finding, evidence, gate, verification = _inputs()
    document = asyncio.run(build_report(
        finding, evidence, gate=gate, verification=verification,
    ))

    assert document.report.title == finding.symptom_signature
    assert "**Steps to reproduce:**" in document.markdown
    assert "1. Navigate to /feed." in document.markdown
    assert "2. Click role=button[name=Favorite]." in document.markdown
    assert "**Expected:** Favorite count increases by one." in document.markdown
    assert "**Actual:** The UI count increased by two after a single click." in document.markdown
    assert "**Reproduction:** 5/5 in fresh browser contexts" in document.markdown
    validate_receipts(document.report, finding, summary=document.summary)


def test_reporter_makes_one_cheap_structured_call_for_title_and_summary():
    finding, evidence, gate, verification = _inputs()
    generator = FakeGenerator({
        "title": "Favorite count increments twice",
        "summary": "The UI count increased by two after a single click.",
    })

    document = asyncio.run(build_report(
        finding, evidence, gate=gate, verification=verification,
        generator=generator, run_id="fixture-run",
    ))

    assert len(generator.calls) == 1
    assert generator.calls[0]["tier"] == "cheap"
    assert generator.calls[0]["run_id"] == "fixture-run"
    assert generator.calls[0]["schema"] == REPORT_NARRATIVE_SCHEMA
    assert document.report.title == generator.result["title"]


def test_validator_rejects_dangling_actual_claim():
    finding, evidence, gate, verification = _inputs()
    document = asyncio.run(build_report(
        finding, evidence, gate=gate, verification=verification,
    ))
    dangling = document.report.model_copy(update={
        "actual": "Payment data was deleted from every customer account.",
    })

    with pytest.raises(ReceiptValidationError, match="actual behavior"):
        validate_receipts(dangling, finding, summary=document.summary)


def test_validator_rejects_narrative_not_grounded_in_any_receipt():
    finding, evidence, gate, verification = _inputs()
    document = asyncio.run(build_report(
        finding, evidence, gate=gate, verification=verification,
    ))

    with pytest.raises(ReceiptValidationError, match="summary contains a claim"):
        validate_receipts(
            document.report,
            finding,
            summary="All customer payments were silently deleted across the system.",
        )


def test_steps_are_rendered_from_step_objects_not_model_text():
    finding, evidence, gate, verification = _inputs()
    original_steps = json.dumps([step.model_dump() for step in finding.steps])
    document = asyncio.run(build_report(
        finding, evidence, gate=gate, verification=verification,
    ))

    assert original_steps
    assert document.markdown == format_markdown(document.report, summary=document.summary)
    assert document.markdown.index("1. Navigate") < document.markdown.index("2. Click")
