"""Replay a finding in independent browser contexts and preserve each receipt."""
from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import Evidence, Finding, Step

from argus.browser.session import BrowserSessionFactory, BrowserTypeName
from argus.evidence.recorder import EvidenceRecorder

ValueFactory = Callable[..., Any | Awaitable[Any]]
ResetHook = Callable[..., Any | Awaitable[Any]]
SymptomMatcher = Callable[[Finding, Evidence], bool | Awaitable[bool]]


@dataclass(frozen=True)
class ReplayVariation:
    """Optional Red Team conditions for one replay attempt.

    Every attempt already receives a new browser context with empty cookies and
    web storage. ``clear_storage`` additionally clears storage immediately
    before each top-level navigation. ``alternate_steps`` replaces the normal
    journey and should reach the same state by a different route.
    """

    browser_type: BrowserTypeName | None = None
    viewport: Mapping[str, int] | None = None
    clear_storage: bool = False
    alternate_steps: Sequence[Step] | None = None


@dataclass(frozen=True)
class ReplayAttempt:
    index: int
    matched: bool
    evidence: Evidence
    variation: ReplayVariation | None = None
    error: str | None = None


@dataclass(frozen=True)
class ReplayResult:
    finding_id: str
    symptom_signature: str
    attempts: tuple[ReplayAttempt, ...] = field(default_factory=tuple)

    @property
    def successes(self) -> int:
        return sum(attempt.matched for attempt in self.attempts)

    @property
    def reproduced(self) -> bool:
        return self.successes > 0


async def replay(
    finding: Finding,
    n: int,
    *,
    target_url: str,
    browser_factory: BrowserSessionFactory,
    layout: RunArtifactLayout,
    variations: Sequence[ReplayVariation] | None = None,
    value_factory: ValueFactory | Mapping[str, Any] | None = None,
    reset_hook: ResetHook | None = None,
    symptom_matcher: SymptomMatcher | None = None,
    record_video: bool = False,
) -> ReplayResult:
    """Replay ``finding.steps`` ``n`` times, isolating and recording attempts.

    Values written as ``{{name}}`` are regenerated for each attempt from a
    mapping or a callable factory. Factories may accept ``name``,
    ``(name, attempt_index)``, or ``(name, attempt_index, previous_value)``.
    A reset hook is called before every attempt, including the first, so a
    caller can restore external backend state to a known baseline.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    if not target_url:
        raise ValueError("target_url must be non-empty")
    plan = tuple(variations or ())
    attempts: list[ReplayAttempt] = []
    generated_values: dict[str, list[Any]] = {}

    for attempt_index in range(n):
        variation = plan[attempt_index % len(plan)] if plan else None
        if reset_hook is not None:
            await _invoke_hook(reset_hook, attempt_index)

        steps = list(variation.alternate_steps if variation and variation.alternate_steps is not None
                     else finding.steps)
        steps = await _materialize_steps(steps, value_factory, attempt_index, n, generated_values)
        attempt_id = f"{_safe_id(finding.id)}-replay-{attempt_index + 1:03d}"
        evidence = Evidence(finding_id=finding.id, steps=steps,
                            expected=finding.expected, actual="Replay did not complete.")
        error = None
        try:
            session, _ = await browser_factory.new_context(
                browser_type=(variation.browser_type if variation and variation.browser_type else "chromium"),
                viewport=(dict(variation.viewport) if variation and variation.viewport else None),
                record={"trace": True, "video": record_video},
                init_scripts=(
                    ["try { localStorage.clear(); sessionStorage.clear(); } catch (_) {}"]
                    if variation and variation.clear_storage else None
                ),
                artifact_id=attempt_id,
            )
            evidence = await _execute_attempt(
                session, finding, steps, layout, attempt_id, target_url,
            )
        except Exception as exc:  # noqa: BLE001 - isolate a failed attempt and retain its receipt
            error = f"{type(exc).__name__}: {exc}"
            evidence = Evidence(finding_id=finding.id, steps=steps,
                                expected=finding.expected, actual=error)

        try:
            matched = await _matches(symptom_matcher, finding, evidence)
        except Exception as exc:  # noqa: BLE001 - a matcher failure must not abort later attempts
            matched = False
            error = error or f"Symptom matcher {type(exc).__name__}: {exc}"
        attempts.append(ReplayAttempt(
            index=attempt_index + 1, matched=matched, evidence=evidence,
            variation=variation, error=error,
        ))

    return ReplayResult(finding_id=finding.id,
                        symptom_signature=finding.symptom_signature,
                        attempts=tuple(attempts))


async def _execute_attempt(session: Any, finding: Finding, steps: list[Step],
                           layout: RunArtifactLayout, attempt_id: str,
                           target_url: str) -> Evidence:
    """Execute and record a replay, ensuring the browser context always closes."""
    from argus.agents.tester import _run_step, _step_element

    recorder = EvidenceRecorder(session, layout, attempt_id, steps,
                                expected=finding.expected)
    actual = "Replay completed."
    failed = False
    try:
        for step_index, step in enumerate(steps):
            recorder.current_step_index = step_index
            try:
                if step_index == 0 and step.action != "goto":
                    await session.page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                await recorder.begin_step(step_index, _step_element(session.page, step), step=step)
                await _run_step(session.page, step)
            except Exception as exc:  # noqa: BLE001 - browser action failures are replay outcomes
                failed = True
                actual = f"{type(exc).__name__}: {exc}"
            await recorder.finish_step(step_index)
            if failed:
                break
        if not steps:
            await session.page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:  # noqa: BLE001 - preserve navigation failures in attempt evidence
        actual = f"{type(exc).__name__}: {exc}"
    return await recorder.finish(actual=actual)


async def _materialize_steps(steps: list[Step], factory: ValueFactory | Mapping[str, Any] | None,
                             attempt_index: int, total_attempts: int,
                             generated: dict[str, list[Any]]) -> list[Step]:
    token_pattern = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_.-]*)\}\}")
    replacements: dict[str, str] = {}
    for step in steps:
        if not step.value:
            continue
        for name in token_pattern.findall(step.value):
            if name not in replacements:
                value = await _new_value(factory, name, attempt_index, total_attempts, generated)
                value_text = str(value)
                replacements[name] = value_text
                seen = generated.setdefault(name, [])
                if value_text in seen:
                    raise ValueError(f"Value factory for parameter {name!r} reused data across attempts")
                seen.append(value_text)
    materialized = []
    for step in steps:
        data = step.model_dump()
        if data["value"]:
            data["value"] = token_pattern.sub(lambda match: replacements[match.group(1)], data["value"])
        materialized.append(Step.model_validate(data))
    return materialized


async def _new_value(factory: ValueFactory | Mapping[str, Any] | None, name: str,
                     attempt_index: int, total_attempts: int,
                     generated: Mapping[str, list[Any]]) -> Any:
    if factory is None:
        raise ValueError(f"Parameterized step value {{{{{name}}}}} needs a value_factory")
    if isinstance(factory, Mapping):
        if name not in factory:
            raise ValueError(f"No value factory configured for parameter {name!r}")
        configured = factory[name]
        if callable(configured):
            values = generated.get(name, [])
            return await _invoke_factory(configured, name, attempt_index, values[-1] if values else None)
        if isinstance(configured, Sequence) and not isinstance(configured, (str, bytes)):
            if len(configured) < total_attempts:
                raise ValueError(
                    f"Value sequence for parameter {name!r} needs at least {total_attempts} entries"
                )
            return configured[attempt_index]
        raise ValueError(
            f"Value factory for parameter {name!r} must be callable or a non-empty sequence "
            "so each attempt can receive fresh data"
        )
    values = generated.get(name, [])
    return await _invoke_factory(factory, name, attempt_index, values[-1] if values else None)


async def _invoke_factory(factory: Callable[..., Any], name: str,
                          attempt_index: int, previous_value: Any) -> Any:
    try:
        signature = inspect.signature(factory)
        positional = [p for p in signature.parameters.values()
                      if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        has_varargs = any(p.kind == p.VAR_POSITIONAL for p in signature.parameters.values())
    except (TypeError, ValueError):
        positional, has_varargs = [], True
    args = (name, attempt_index, previous_value) if has_varargs or len(positional) >= 3 else (
        (name, attempt_index) if len(positional) == 2 else
        ((name,) if len(positional) == 1 else ())
    )
    result = factory(*args)
    return await result if inspect.isawaitable(result) else result


async def _invoke_hook(hook: ResetHook, attempt_index: int) -> None:
    try:
        signature = inspect.signature(hook)
        accepts_arg = bool(signature.parameters)
    except (TypeError, ValueError):
        accepts_arg = True
    result = hook(attempt_index) if accepts_arg else hook()
    if inspect.isawaitable(result):
        await result


async def _matches(matcher: SymptomMatcher | None, finding: Finding, evidence: Evidence) -> bool:
    if matcher is not None:
        result = matcher(finding, evidence)
        return bool(await result) if inspect.isawaitable(result) else bool(result)
    observed = [evidence.actual, evidence.dom_snapshot_after or ""]
    observed.extend(f"{event.method} {event.url} returned {event.status}"
                    for event in evidence.network if event.status is not None)
    observed.extend(event.message for event in evidence.console)
    signature = _normalize(finding.symptom_signature)
    return bool(signature) and any(signature in _normalize(item) for item in observed)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    if not safe:
        raise ValueError("finding id must contain at least one path-safe character")
    return safe[:70]
