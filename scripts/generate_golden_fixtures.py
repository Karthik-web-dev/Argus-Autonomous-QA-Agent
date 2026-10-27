from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/shared/src"))

from argus_contracts.models import (  # noqa: E402
    AppGraph, BugReport, ConsoleEvent, ContractModel, ElementCatalogEntry, Evidence, Finding,
    GateResult, NetworkEvent, ReproductionResult, RunEvent, Spec, SpecClaim,
    SpecEntity, Step, TestCase, TestResult, ValidationRule, VerificationResult,
)

FIXTURES = ROOT / "fixtures"
RUN_ID = "run-golden-001"


def write_json(name: str, value) -> None:
    if isinstance(value, ContractModel):
        value = value.model_dump(mode="json", by_alias=True)
    elif isinstance(value, list):
        value = [item.model_dump(mode="json", by_alias=True) if isinstance(item, ContractModel) else item for item in value]
    (FIXTURES / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def evidence_bundle(finding_id: str, steps: list[Step], expected: str, actual: str,
                    network_url: str, network_status: int, screenshot: str,
                    successes: int, attempts: int = 5) -> Evidence:
    return Evidence(
        finding_id=finding_id, steps=steps, expected=expected, actual=actual,
        network=[NetworkEvent(url=network_url, method="POST", status=network_status,
                              timestamp="T+0.8s")],
        console=[ConsoleEvent(level="info", message="Navigation completed", timestamp="T+0.9s")],
        screenshots=[screenshot],
        dom_snapshot_after='<button aria-label="Favorite">Favorite (14)</button>',
        reproduction=ReproductionResult(attempts=attempts, successes=successes,
                                       contexts=["fresh" for _ in range(attempts)]),
        trace_path=f"artifacts/{finding_id}/trace.zip",
    )


def generate() -> None:
    (FIXTURES / "evidence").mkdir(parents=True, exist_ok=True)
    favorite_steps = [Step(action="goto", value="/feed"),
                      Step(action="click", locator="role=button[name=Favorite]")]
    pagination_steps = [Step(action="goto", value="/feed"),
                        Step(action="click", locator="role=button[name=Next page]")]
    article_steps = [Step(action="goto", value="/feed"),
                     Step(action="click", locator="role=button[name=Favorite]")]
    edit_steps = [Step(action="goto", value="/editor/example"),
                  Step(action="fill", locator="role=textbox[name=Article Body]", value="Edited article body"),
                  Step(action="click", locator="role=button[name=Publish Article]")]
    cases = [
        TestCase(id="tc-favorite-double", journey="Favorite an article",
                 description="One favorite action increments the count once.", steps=favorite_steps,
                 expected="The count increases by one.", category="journey", source="spec"),
        TestCase(id="tc-pagination-flaky", journey="Paginate the global feed",
                 description="The next feed page starts with the next unique article.", steps=pagination_steps,
                 expected="Page two does not repeat the final item from page one.",
                 category="edge_case", source="playbook"),
        TestCase(id="tc-analytics-noise", journey="Favorite article analytics",
                 description="A failing analytics beacon must not undo the favorite action.", steps=article_steps,
                 expected="The favorite state is saved even if analytics is unavailable.",
                 category="edge_case", source="spec"),
    ]
    spec = Spec(
        description="Conduit lets visitors browse and favorite articles, while registered users can sign in, publish articles, comment, follow authors, and manage their profile.",
        journeys=[cases[0], cases[2]],
        claims=[
            SpecClaim(id="claim-favorite", statement="Favoriting an article increments its count exactly once.", priority="high"),
            SpecClaim(id="claim-pagination", statement="Feed pagination returns unique articles in order."),
            SpecClaim(id="claim-analytics", statement="Analytics failures do not change the result of a user action."),
        ],
        entities=[SpecEntity(name="Article", fields=["title", "description", "body", "tags"]),
                  SpecEntity(name="User", fields=["email", "username", "bio", "image"])],
        validation_rules=[ValidationRule(field="article.title", rule="required", message="Title is required."),
                           ValidationRule(field="user.email", rule="valid email", message="Enter a valid email.")],
        auth_requirements=["Public visitors may browse articles.", "Only signed-in users may publish or favorite."],
    )
    write_json("spec.json", spec.model_dump(mode="json", by_alias=True))

    graph = AppGraph(adjacency={
        "/": ["/login", "/register", "/feed"], "/login": ["/feed", "/settings"],
        "/register": ["/feed"], "/feed": ["/article/:slug", "/editor", "/profile/:username"],
        "/article/:slug": ["/editor", "/feed"], "/editor": ["/article/:slug", "/feed"],
        "/settings": ["/profile/:username"], "/profile/:username": ["/feed"],
    })
    write_json("app_graph.json", graph.model_dump(mode="json"))

    elements = [
        ElementCatalogEntry(id="nav-home", role="link", name="Home", semantic_locator="role=link[name=Home]", visible=True, enabled=True, in_viewport=True),
        ElementCatalogEntry(id="nav-signin", role="link", name="Sign in", semantic_locator="role=link[name=Sign in]", visible=True, enabled=True, in_viewport=True),
        ElementCatalogEntry(id="favorite", role="button", name="Favorite", state={"disabled": False}, semantic_locator="role=button[name=Favorite]", form_group=None, visible=True, enabled=True, in_viewport=True),
        ElementCatalogEntry(id="next-page", role="button", name="Next page", state={"disabled": False}, semantic_locator="role=button[name=Next page]", form_group=None, visible=True, enabled=True, in_viewport=True),
        ElementCatalogEntry(id="article-title", role="textbox", name="Article Title", semantic_locator="role=textbox[name=Article Title]", form_group="editor", visible=True, enabled=True, in_viewport=True),
        ElementCatalogEntry(id="article-body", role="textbox", name="Article Body", semantic_locator="role=textbox[name=Article Body]", form_group="editor", visible=True, enabled=True, in_viewport=True),
        ElementCatalogEntry(id="publish", role="button", name="Publish Article", semantic_locator="role=button[name=Publish Article]", form_group="editor", visible=True, enabled=True, in_viewport=True),
        ElementCatalogEntry(id="comment", role="textbox", name="Write a comment", semantic_locator="role=textbox[name=Write a comment]", form_group="comment", visible=True, enabled=True, in_viewport=True),
    ]
    write_json("element_catalog.json", [item.model_dump(mode="json") for item in elements])
    write_json("test_cases.json", [item.model_dump(mode="json") for item in cases])

    evidence = [
        evidence_bundle("finding-true", favorite_steps, "Favorite count increases by one.",
                        "The UI count increased by two after a single click.",
                        "/api/articles/argus-fixture/favorite", 200,
                        "artifacts/finding-true/screenshots/after-click.png", 5),
        evidence_bundle("finding-flaky", pagination_steps,
                        "The next page begins with a new article.",
                        "The last article from page one reappeared on page two in one replay.",
                        "/api/articles?offset=10", 200,
                        "artifacts/finding-flaky/screenshots/page-two.png", 1, 3),
        evidence_bundle("finding-false-positive", article_steps,
                        "A failed analytics beacon does not undo a favorite.",
                        "The favorite saved successfully; only the analytics beacon returned 503.",
                        "/api/analytics/events", 503,
                        "artifacts/finding-false-positive/screenshots/favorite-saved.png", 5),
    ]
    evidence_names = ["evidence_bundle.json", "evidence_flaky.json", "evidence_false_positive.json"]
    for name, bundle in zip(evidence_names, evidence, strict=True):
        (FIXTURES / "evidence" / name).write_text(bundle.model_dump_json(indent=2) + "\n", encoding="utf-8")
    edit_evidence = evidence_bundle("finding-edit-tags-sample", edit_steps,
                                    "All article tags remain attached after an edit.",
                                    "The final tag is missing after the update.",
                                    "/api/articles/argus-fixture", 200,
                                    "artifacts/BUG-003/screenshots/article-after-edit.png", 5)
    (FIXTURES / "evidence" / "evidence_edit_tags.json").write_text(edit_evidence.model_dump_json(indent=2) + "\n", encoding="utf-8")

    findings = [
        Finding(id="finding-true", oracle_id="ui-network-correlation", symptom_signature="Favorite count increments twice", confidence=0.97, steps=favorite_steps, evidence_ref="evidence/evidence_bundle.json", expected=evidence[0].expected, actual=evidence[0].actual, affected_paths=["/feed", "/article/:slug"]),
        Finding(id="finding-flaky", oracle_id="pagination-invariant", symptom_signature="Feed pagination may repeat an article", confidence=0.61, steps=pagination_steps, evidence_ref="evidence/evidence_flaky.json", expected=evidence[1].expected, actual=evidence[1].actual, affected_paths=["/feed"]),
        Finding(id="finding-false-positive", oracle_id="http-status", symptom_signature="Favorite action reported as failed", confidence=0.54, steps=article_steps, evidence_ref="evidence/evidence_false_positive.json", expected=evidence[2].expected, actual=evidence[2].actual, affected_paths=["/feed"]),
    ]
    write_json("findings.json", [item.model_dump(mode="json") for item in findings])
    write_json("test_results.json", [item.model_dump(mode="json") for item in [
        TestResult(test_id=cases[0].id, verdict="FAIL", evidence=evidence[0], duration_ms=1240),
        TestResult(test_id=cases[1].id, verdict="INCONCLUSIVE", evidence=evidence[1], duration_ms=2180),
        TestResult(test_id=cases[2].id, verdict="PASS", evidence=evidence[2], duration_ms=890),
    ]])
    write_json("gate_results.json", [
        GateResult(finding_id="finding-true", verdict="ACCEPTED", attempts=3, successes=3, threshold=2/3, evidence_refs=["evidence/evidence_bundle.json"]),
        GateResult(finding_id="finding-flaky", verdict="FLAKY", attempts=3, successes=1, threshold=2/3, evidence_refs=["evidence/evidence_flaky.json"]),
        GateResult(finding_id="finding-false-positive", verdict="ACCEPTED", attempts=3, successes=3, threshold=2/3, evidence_refs=["evidence/evidence_false_positive.json"]),
    ])
    write_json("verification_results.json", [
        VerificationResult(finding_id="finding-true", verdict="CONFIRMED", attempts=5, reason="UI count changes by two while the favorite endpoint is called once."),
        VerificationResult(finding_id="finding-flaky", verdict="INCONCLUSIVE", attempts=5, reason="The duplicate item appeared in only one replay."),
        VerificationResult(finding_id="finding-false-positive", verdict="REFUTED", attempts=5, reason="The favorite action succeeds; the 503 belongs to nonessential analytics."),
    ])

    report_templates = [
        ("BUG-001", "P1", "Favorite action increments the count twice", evidence[0], "functional"),
        ("BUG-002", "P2", "Next feed page repeats the previous article", evidence[1], "functional"),
        ("BUG-003", "P2", "Editing an article removes its final tag", edit_evidence, "state_persistence"),
    ]
    reports = [BugReport(id=report_id, severity=severity, title=title, category=category,
                         steps=bundle.steps, expected=bundle.expected, actual=bundle.actual,
                         evidence=bundle, playwright_repro_path=f"tests/repro/{report_id.lower()}.spec.ts",
                         affected_paths=["/feed"], verified_by="red_team")
               for report_id, severity, title, bundle, category in report_templates]
    write_json("bug_reports.json", [item.model_dump(mode="json") for item in reports])

    event_counts = [
        ("run_started", 1), ("phase_changed", 5), ("agent_active", 11), ("action", 17),
        ("page_discovered", 4), ("test_result", 3), ("finding_created", 3),
        ("gate_result", 3), ("verification_result", 3), ("bug_reported", 1),
        ("coverage_update", 2), ("scoreboard_update", 2), ("budget_update", 1),
        ("llm_call", 2), ("error", 1), ("run_completed", 1),
    ]
    payloads = {
        "run_started": {"target_url": "https://demo.realworld.io", "spec": spec.description},
        "phase_changed": {"phase": "exploration", "previous": "initializing"},
        "agent_active": {"agent": "explorer", "status": "active"},
        "action": {"action": "click", "locator": "role=button[name=Favorite]"},
        "page_discovered": {"url": "/feed", "element_count": len(elements)},
        "test_result": {"test_id": cases[0].id, "verdict": "FAIL", "duration_ms": 1240},
        "finding_created": {"finding_id": findings[0].id, "oracle_id": findings[0].oracle_id, "confidence": findings[0].confidence},
        "gate_result": {"finding_id": findings[0].id, "verdict": "ACCEPTED", "attempts": 3, "successes": 3},
        "verification_result": {"finding_id": findings[0].id, "verdict": "CONFIRMED", "attempts": 5},
        "bug_reported": {"bug_id": reports[0].id, "severity": reports[0].severity, "evidence_ref": "artifacts/finding-true"},
        "coverage_update": {"covered": 1, "total": 25, "ratio": 0.04},
        "scoreboard_update": {"true_positive": 1, "false_positive": 0, "precision": 1.0, "recall": 0.04},
        "budget_update": {"calls_remaining": 8, "estimated_cost_usd": 0.02},
        "llm_call": {"purpose": "spec_parse", "provider": "fixture", "duration_ms": 0},
        "error": {"code": "OPTIONAL_ANALYTICS_503", "message": "Recorded as evidence; user action remained successful."},
        "run_completed": {"status": "completed", "finding_count": 1, "artifact_dir": f"runs/{RUN_ID}"},
    }
    events = []
    sequence = 1
    for event_type, count in event_counts:
        for index in range(count):
            events.append(RunEvent(
                id=f"evt-{sequence:03d}", run_id=RUN_ID,
                ts=datetime(2026, 10, 15, 9, tzinfo=timezone.utc) + timedelta(seconds=sequence * 2),
                agent="supervisor" if event_type in {"run_started", "phase_changed", "run_completed"} else "explorer",
                correlation_id=f"corr-{sequence:03d}", type=event_type,
                payload={**payloads[event_type], "sequence": index + 1} if count > 1 else payloads[event_type],
            ))
            sequence += 1
    (FIXTURES / "run_events.ndjson").write_text("".join(event.model_dump_json() + "\n" for event in events), encoding="utf-8")

    (FIXTURES / "sample_spec.md").write_text(
        "# Conduit sample application\n\n"
        "Conduit is a lightweight blogging app. Visitors can browse and paginate the global feed. "
        "Registered users can sign in, publish articles with a title, description, body, and tags, "
        "favorite articles, comment, follow authors, and update their profile. A favorite click "
        "changes the count exactly once. Paginated feeds must not repeat articles. Article titles "
        "and account email addresses are validated. Optional analytics failures must not undo a "
        "successful user action.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    generate()
