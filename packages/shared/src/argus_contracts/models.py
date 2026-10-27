from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)


class Step(ContractModel):
    action: Literal[
        "goto", "click", "fill", "hover", "wait", "assert", "press", "type_text",
        "double_click", "back", "reload", "set_viewport", "set_offline", "throttle_network",
        "assert_no_broken_images", "assert_internal_links", "assert_no_console_errors",
        "assert_invalid", "assert_password_masked", "assert_value_length",
        "assert_numeric_value", "assert_input_value", "assert_no_new_console_errors",
        "assert_no_unsafe_markup", "assert_empty_state", "assert_no_text_overflow",
        "assert_named_control", "assert_pagination_boundaries", "assert_protected_route",
        "assert_idor_isolation", "assert_sort_stability", "assert_numeric_boundary",
        "assert_double_submit", "assert_mobile_layout", "assert_back_mid_flow",
        "assert_refresh_mid_flow", "assert_keyboard_submit",
    ]
    locator: str = ""
    value: str | None = None
    timeout_ms: int = Field(default=10000, gt=0, le=120000)


class TestCase(ContractModel):
    id: str = Field(min_length=1)
    journey: str = Field(min_length=1)
    description: str = Field(min_length=1)
    steps: list[Step] = Field(default_factory=list)
    expected: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    category: Literal["journey", "edge_case"] = "journey"
    source: Literal["spec", "playbook"] = "spec"


class SpecClaim(ContractModel):
    id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    journey_ids: list[str] = Field(default_factory=list)


class SpecEntity(ContractModel):
    name: str = Field(min_length=1)
    description: str = ""
    fields: list[str] = Field(default_factory=list)


class ValidationRule(ContractModel):
    field: str = Field(min_length=1)
    rule: str = Field(min_length=1)
    message: str | None = None


class Spec(ContractModel):
    description: str = Field(min_length=1)
    journeys: list[TestCase] = Field(default_factory=list)
    claims: list[SpecClaim] = Field(default_factory=list)
    entities: list[SpecEntity] = Field(default_factory=list)
    validation_rules: list[ValidationRule] = Field(default_factory=list)
    auth_requirements: list[str] = Field(default_factory=list)


class BindingResult(ContractModel):
    """Case-level result of mapping abstract actions to discovered controls."""

    test_case: TestCase
    verdict: Literal["BOUND", "INCONCLUSIVE"]
    reason: str = ""
    deterministic_steps: list[int] = Field(default_factory=list)
    model_steps: list[int] = Field(default_factory=list)


class ElementCatalogEntry(ContractModel):
    id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    name: str = ""
    state: dict[str, Any] = Field(default_factory=dict)
    semantic_locator: str = Field(min_length=1)
    form_group: str | None = None
    visible: bool
    enabled: bool
    in_viewport: bool


class AppGraphNode(ContractModel):
    """A distinct reachable UI state in a crawled application."""

    id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    signature: str = Field(min_length=1)
    title: str = ""
    accessibility_snapshot: str = ""
    elements: list[ElementCatalogEntry] = Field(default_factory=list)
    authenticated: bool = False
    captured: bool = True


class AppGraphEdge(ContractModel):
    """A user action that transitions between two discovered states."""

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    action: Literal["link", "button"]
    locator: str = Field(min_length=1)


class AppGraph(ContractModel):
    # Keep adjacency required by existing consumers while exposing richer crawl data.
    adjacency: dict[str, list[str]] = Field(default_factory=dict)
    nodes: list[AppGraphNode] = Field(default_factory=list)
    edges: list[AppGraphEdge] = Field(default_factory=list)


class NetworkEvent(ContractModel):
    url: str
    method: str = "GET"
    status: int | None = Field(default=None, ge=100, le=599)
    failed: bool = False
    timestamp: str | None = None
    step_index: int | None = Field(default=None, ge=0)


class ConsoleEvent(ContractModel):
    level: Literal["debug", "info", "warning", "error"]
    message: str
    timestamp: str | None = None
    step_index: int | None = Field(default=None, ge=0)


class ReproductionResult(ContractModel):
    attempts: int = Field(default=0, ge=0)
    successes: int = Field(default=0, ge=0)
    contexts: list[str] = Field(default_factory=list)


class StepEvidence(ContractModel):
    """Per-step browser captures, with zero-based indexing into Evidence.steps."""

    step_index: int = Field(ge=0)
    screenshot: str | None = None
    element_screenshot: str | None = None
    dom_snapshot: str | None = None


class Evidence(ContractModel):
    finding_id: str | None = None
    steps: list[Step] = Field(default_factory=list)
    expected: str = ""
    actual: str = ""
    failure_kind: Literal["assertion", "interaction", "timeout", "setup"] | None = None
    failed_step_index: int | None = Field(default=None, ge=0)
    network: list[NetworkEvent] = Field(default_factory=list)
    console: list[ConsoleEvent] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)
    step_evidence: list[StepEvidence] = Field(default_factory=list)
    dom_snapshot_after: str | None = None
    animation_timeline: list[dict[str, Any]] | None = None
    reproduction: ReproductionResult = Field(default_factory=ReproductionResult)
    trace_path: str | None = None
    video_path: str | None = None


class Finding(ContractModel):
    id: str = Field(min_length=1)
    oracle_id: str = Field(min_length=1)
    symptom_signature: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    steps: list[Step] = Field(default_factory=list)
    evidence_ref: str = Field(min_length=1)
    expected: str = ""
    actual: str = ""
    affected_paths: list[str] = Field(default_factory=list)


class GateResult(ContractModel):
    finding_id: str = Field(min_length=1)
    verdict: Literal["ACCEPTED", "REJECTED", "FLAKY"]
    attempts: int = Field(ge=0)
    successes: int = Field(ge=0)
    threshold: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)


class VerificationResult(ContractModel):
    finding_id: str = Field(min_length=1)
    verdict: Literal["CONFIRMED", "REFUTED", "INCONCLUSIVE"]
    attempts: int = Field(default=0, ge=0)
    reason: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class BugReport(ContractModel):
    id: str = Field(min_length=1)
    severity: Literal["P0", "P1", "P2", "P3"]
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    steps: list[Step] = Field(default_factory=list)
    expected: str
    actual: str
    evidence: Evidence
    playwright_repro_path: str | None = None
    affected_paths: list[str] = Field(default_factory=list)
    verified_by: Literal["red_team", "none"] = "none"


class ManifestBug(ContractModel):
    id: str = Field(min_length=1)
    bug_class: str = Field(alias="class", min_length=1)
    title: str = Field(min_length=1)
    verified: bool = False
    expected_signals: list[str] = Field(default_factory=list)
    affected_journeys: list[str] = Field(default_factory=list)
    severity: Literal["P0", "P1", "P2", "P3"] | None = None


RunEventType = Literal[
    "run_started", "phase_changed", "agent_active", "action", "page_discovered",
    "test_result", "finding_created", "gate_result", "verification_result",
    "bug_reported", "coverage_update", "scoreboard_update", "budget_update",
    "llm_call", "error", "run_completed",
]


class RunEvent(ContractModel):
    id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    type: RunEventType
    payload: dict[str, Any] = Field(default_factory=dict)


class TestResult(ContractModel):
    test_id: str = Field(min_length=1)
    verdict: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    evidence: Evidence
    duration_ms: int = Field(ge=0)


class QAState(ContractModel):
    """Runtime state; the documented writer column defines mutation ownership."""

    target_url: HttpUrl | None = None
    spec: Spec | None = None
    app_graph: AppGraph = Field(default_factory=AppGraph)
    discovered_elements: list[ElementCatalogEntry] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    test_results: list[TestResult] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    accepted_findings: list[Finding] = Field(default_factory=list)
    verified_findings: list[Finding] = Field(default_factory=list)
    rejected_findings: list[Finding] = Field(default_factory=list)
    bugs_found: list[BugReport] = Field(default_factory=list)
    coverage: dict[str, float] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    iteration: int = Field(default=0, ge=0)
    complete: bool = False


class CreateRunRequest(ContractModel):
    url: HttpUrl
    spec: str = Field(min_length=1)


class RunMetrics(ContractModel):
    journeys: int = Field(default=0, ge=0)
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    raw_findings: int = Field(default=0, ge=0)


class RunSummary(ContractModel):
    run_id: str = Field(min_length=1)
    artifact_dir: str = Field(min_length=1)
    target_url: HttpUrl
    spec: str
    accessibility_snapshot: str = ""
    parsed_spec: Spec | None = None
    discovered_elements: list[ElementCatalogEntry] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    test_results: list[TestResult] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    metrics: RunMetrics = Field(default_factory=RunMetrics)
