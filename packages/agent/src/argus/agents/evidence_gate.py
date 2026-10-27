"""Deterministic replay gate for candidate findings; this module never calls an LLM."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from functools import partial

from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import (
    Evidence,
    Finding,
    GateResult,
    ReproductionResult,
)

from argus.browser.session import BrowserSessionFactory
from argus.replay.replayer import ReplayResult
from argus.replay.replayer import replay as replay_with_browser

REPLAY_ATTEMPTS = 3
ACCEPTANCE_THRESHOLD = 2 / 3
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.7
logger = logging.getLogger(__name__)

ReplayRunner = Callable[[Finding, int], Awaitable[ReplayResult]]


@dataclass(frozen=True)
class GateDecision:
    """Gate verdict plus replay receipts and routing hints for later stages."""

    result: GateResult
    reproduction: ReproductionResult
    representative_finding_id: str
    duplicate_finding_ids: tuple[str, ...] = ()
    needs_red_team: bool = False
    error: str | None = None


def classify_replay(finding: Finding, replay: ReplayResult) -> GateDecision:
    """Apply the fixed C-02 2-of-3 rule to one representative replay."""
    attempts = len(replay.attempts)
    successes = replay.successes
    if attempts != REPLAY_ATTEMPTS:
        verdict = "FLAKY"
    elif successes >= 2:
        verdict = "ACCEPTED"
    elif successes == 1:
        verdict = "FLAKY"
    else:
        verdict = "REJECTED"

    evidence_refs: list[str] = []
    context_refs: list[str] = []
    for attempt in replay.attempts:
        context_refs.append(f"{finding.id}:replay:{attempt.index}")
        if attempt.evidence.trace_path:
            evidence_refs.append(attempt.evidence.trace_path)
        evidence_refs.extend(attempt.evidence.screenshots)

    result = GateResult(
        finding_id=finding.id,
        verdict=verdict,
        attempts=attempts,
        successes=successes,
        threshold=ACCEPTANCE_THRESHOLD,
        evidence_refs=list(dict.fromkeys(evidence_refs)),
    )
    reproduction = ReproductionResult(
        attempts=attempts,
        successes=successes,
        contexts=context_refs,
    )
    return GateDecision(
        result=result,
        reproduction=reproduction,
        representative_finding_id=finding.id,
        needs_red_team=(verdict == "FLAKY" or finding.confidence < DEFAULT_LOW_CONFIDENCE_THRESHOLD),
    )


async def gate_findings(
    findings: Iterable[Finding],
    *,
    replay_runner: ReplayRunner | None = None,
    target_url: str | None = None,
    browser_factory: BrowserSessionFactory | None = None,
    layout: RunArtifactLayout | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> list[GateDecision]:
    """Gate one finding per ``symptom_signature`` group using three replays.

    Pass ``replay_runner`` for a fixture or custom transport. Otherwise the
    production C-01 replayer is configured from ``target_url``,
    ``browser_factory``, and ``layout``. A timeout or replay infrastructure
    error yields ``FLAKY`` because no complete set of three observations exists.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    if not 0.0 <= low_confidence_threshold <= 1.0:
        raise ValueError("low_confidence_threshold must be between 0 and 1")
    runner = replay_runner
    if runner is None:
        if not target_url or browser_factory is None or layout is None:
            raise ValueError(
                "target_url, browser_factory, and layout are required when replay_runner is omitted"
            )
        runner = partial(
            replay_with_browser,
            target_url=target_url,
            browser_factory=browser_factory,
            layout=layout,
        )

    groups: dict[str, list[Finding]] = {}
    for finding in findings:
        groups.setdefault(finding.symptom_signature, []).append(finding)

    decisions: list[GateDecision] = []
    for group in groups.values():
        representative = group[0]
        error = None
        try:
            replay_result = await asyncio.wait_for(
                runner(representative, REPLAY_ATTEMPTS), timeout=timeout_seconds,
            )
            decision = classify_replay(representative, replay_result)
        except TimeoutError:
            replay_result = ReplayResult(
                finding_id=representative.id,
                symptom_signature=representative.symptom_signature,
            )
            decision = classify_replay(representative, replay_result)
            error = f"Replay exceeded the {timeout_seconds:g}-second Evidence Gate budget"
        except Exception as exc:  # noqa: BLE001 - isolate infra errors and continue other groups
            replay_result = ReplayResult(
                finding_id=representative.id,
                symptom_signature=representative.symptom_signature,
            )
            decision = classify_replay(representative, replay_result)
            error = f"{type(exc).__name__}: {exc}"

        decisions.append(GateDecision(
            result=decision.result,
            reproduction=decision.reproduction,
            representative_finding_id=representative.id,
            duplicate_finding_ids=tuple(item.id for item in group[1:]),
            needs_red_team=(
                decision.result.verdict == "FLAKY"
                or any(item.confidence < low_confidence_threshold for item in group)
            ),
            error=error,
        ))
    return decisions


async def replay_finding(replay: Callable[[], Awaitable[bool]], attempts: int = 3) -> dict:
    """Compatibility wrapper for the earlier boolean callback helper."""
    successes = 0
    count = max(1, attempts)
    for _ in range(count):
        try:
            successes += bool(await replay())
        except Exception as exc:  # noqa: BLE001 - a failed replay counts as a non-reproduction
            logger.warning("Finding replay attempt failed: %s", exc)
            continue
    return {
        "attempts": count,
        "successes": successes,
        "accepted": successes >= (count // 2 + 1),
    }


def attach_reproduction(evidence: Evidence, decision: GateDecision) -> Evidence:
    """Return evidence with the gate's replay summary attached."""
    return evidence.model_copy(update={"reproduction": decision.reproduction})
