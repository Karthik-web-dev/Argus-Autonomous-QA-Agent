"""Deterministic semantic-step binding with a cached model fallback."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import Any

from argus_contracts.models import BindingResult, ElementCatalogEntry, Step, TestCase

from argus.models import ModelGateway, ModelTier, StructuredModel

INTERACTIVE_ACTIONS = {"click", "double_click", "fill", "type_text", "hover", "press"}
ACTION_ROLES = {
    "click": {"button", "link", "tab", "menuitem", "checkbox", "radio", "switch", "option"},
    "double_click": {"button", "link", "tab", "menuitem", "checkbox", "radio", "switch", "option"},
    "fill": {"textbox", "searchbox", "combobox", "spinbutton"},
    "type_text": {"textbox", "searchbox", "combobox", "spinbutton"},
    "hover": {"button", "link", "tab", "menuitem"},
    "press": {"textbox", "searchbox", "combobox", "spinbutton"},
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).strip()


def _requested_target(step: Step) -> tuple[str | None, str]:
    """Read the role/name form used by the Explorer without accepting selectors."""
    locator = re.sub(r"\s+>> nth=\d+$", "", step.locator.strip())
    match = re.fullmatch(r"role=([\w-]+)(?:\[name=(.+)\])?", locator)
    if match:
        name = match.group(2) or ""
        try:
            name = json.loads(name)
        except json.JSONDecodeError:
            name = name.strip('"\'')
        return match.group(1).casefold(), str(name)
    # Natural-language abstract steps such as "Sign in button" are supported.
    match = re.match(r"^(button|link|textbox|searchbox|combobox|tab|menuitem)\s*[:=-]\s*(.+)$", locator, re.IGNORECASE)
    if match:
        return match.group(1).casefold(), match.group(2).strip()
    return None, locator


def _similarity(left: str, right: str) -> float:
    a, b = _normalize(left), _normalize(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    token_a, token_b = set(a.split()), set(b.split())
    token_score = 2 * len(token_a & token_b) / max(1, len(token_a) + len(token_b))
    sequence_score = SequenceMatcher(None, a, b, autojunk=False).ratio()
    containment = 0.92 if a in b or b in a else 0.0
    return max(sequence_score, token_score * 0.92, containment)


def _action_compatible(step: Step, element: ElementCatalogEntry) -> bool:
    wanted_role, _ = _requested_target(step)
    if element.role.casefold() not in ACTION_ROLES.get(step.action, set()):
        return False
    return not (wanted_role and wanted_role != element.role.casefold())


def _candidate_score(step: Step, element: ElementCatalogEntry) -> float:
    if not _action_compatible(step, element):
        return 0.0
    _, wanted_name = _requested_target(step)
    return _similarity(wanted_name, element.name)


def _is_catalog_locator(locator: str) -> bool:
    """Accept only role/name locators, optionally with Explorer's ordinal."""
    return bool(re.fullmatch(
        r"role=[\w-]+(?:\[name=(?:\"(?:\\.|[^\"\\])*\"|[A-Za-z0-9 _.,'&()!?/-]+)\])?(?: >> nth=\d+)?",
        locator,
    ))


def _unique_semantic_catalog(elements: Sequence[ElementCatalogEntry]) -> dict[str, ElementCatalogEntry]:
    counts: dict[str, int] = {}
    id_counts: dict[str, int] = {}
    for element in elements:
        counts[element.semantic_locator] = counts.get(element.semantic_locator, 0) + 1
        id_counts[element.id] = id_counts.get(element.id, 0) + 1
    return {element.id: element for element in elements
            if element.visible and _is_catalog_locator(element.semantic_locator)
            and counts[element.semantic_locator] == 1 and id_counts[element.id] == 1}


def _schema(step_indexes: list[int], element_ids: list[str]) -> dict[str, Any]:
    return {
        "title": "ArgusTestBindings",
        "type": "object",
        "properties": {
            "bindings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step_index": {"type": "integer", "enum": step_indexes},
                        "element_id": {"type": "string", "enum": element_ids},
                    },
                    "required": ["step_index", "element_id"],
                    "additionalProperties": False,
                },
                "minItems": len(step_indexes),
                "maxItems": len(step_indexes),
            }
        },
        "required": ["bindings"],
        "additionalProperties": False,
    }


async def bind_cases(
    test_cases: Sequence[TestCase],
    elements: Sequence[ElementCatalogEntry],
    *,
    gateway: StructuredModel | None = None,
    run_id: str = "test-bind",
    tier: ModelTier = "cheap",
    deterministic_threshold: float = 0.86,
    ambiguity_margin: float = 0.08,
) -> list[BindingResult]:
    """Bind actions to unique catalog entries; unresolved cases are INCONCLUSIVE.

    Matching uses role and normalized accessible name. The model can select only
    among catalog IDs supplied in its schema, so it cannot invent CSS, XPath, or
    coordinate targets. Ambiguous targets shared across cases are resolved once,
    in a single model call, so binding costs at most one request per run.
    """
    if not 0 <= deterministic_threshold <= 1 or not 0 <= ambiguity_margin <= 1:
        raise ValueError("binding thresholds must be between zero and one")
    model = gateway or ModelGateway()
    unique_elements = _unique_semantic_catalog(elements)
    outcomes: list[BindingResult] = []

    # Pass 1: resolve what we can deterministically and collect ambiguous steps.
    prepared: list[tuple[TestCase, list[Step], list[int], list[int]]] = []
    for case in test_cases:
        steps = list(case.steps)
        deterministic: list[int] = []
        ambiguous: list[int] = []
        for index, step in enumerate(steps):
            if step.action not in INTERACTIVE_ACTIONS:
                continue
            if step.action == "press" and not step.locator:
                # A blank target means page-level keyboard navigation, not an
                # abstract element target; preserve that semantic unchanged.
                deterministic.append(index)
                continue
            exact = [element for element in unique_elements.values()
                     if element.semantic_locator == step.locator and _candidate_score(step, element) > 0]
            if len(exact) == 1:
                deterministic.append(index)
                continue
            ranked = sorted(
                ((_candidate_score(step, element), element)
                 for element in unique_elements.values()),
                key=lambda item: (-item[0], item[1].id),
            )
            best_score = ranked[0][0] if ranked else 0.0
            second_score = ranked[1][0] if len(ranked) > 1 else 0.0
            if (ranked and best_score >= deterministic_threshold
                    and best_score - second_score >= ambiguity_margin):
                steps[index] = step.model_copy(update={"locator": ranked[0][1].semantic_locator})
                deterministic.append(index)
            else:
                ambiguous.append(index)
        prepared.append((case, steps, deterministic, ambiguous))

    # Pass 2: journeys share steps (every journey signs in first, for example),
    # so resolve each distinct (action, target) once in a single model call.
    targets: dict[tuple[str, str], Step] = {}
    target_journeys: dict[tuple[str, str], list[str]] = {}
    for case, steps, _, ambiguous in prepared:
        for index in ambiguous:
            key = (steps[index].action, steps[index].locator)
            if key not in targets:
                targets[key] = steps[index]
                target_journeys[key] = []
            if case.journey not in target_journeys[key]:
                target_journeys[key].append(case.journey)
    target_keys = list(targets)
    compatible_elements = {
        element_id: element for element_id, element in unique_elements.items()
        if any(_action_compatible(step, element) for step in targets.values())
    }
    resolved: dict[tuple[str, str], ElementCatalogEntry] = {}
    model_error = ""
    if target_keys and compatible_elements:
        candidate_rows = [
            {"id": item.id, "role": item.role, "name": item.name, "form_group": item.form_group}
            for item in sorted(compatible_elements.values(), key=lambda entry: entry.id)
        ]
        prompt = json.dumps({
            "steps": [{"step_index": i, "action": targets[key].action,
                       "abstract_target": targets[key].locator,
                       "used_in_journeys": target_journeys[key],
                       "compatible_element_ids": sorted(
                           element_id for element_id, element in compatible_elements.items()
                           if _action_compatible(targets[key], element))}
                      for i, key in enumerate(target_keys)],
            "catalog": candidate_rows,
            "instruction": "Choose the catalog element that best matches each action and journey context. Return each requested step exactly once. Never invent a selector.",
        }, ensure_ascii=False, sort_keys=True)
        try:
            response = await model.generate(
                tier=tier,
                run_id=run_id,
                system="Resolve abstract browser actions to supplied accessible controls. Return only schema-valid bindings.",
                prompt=prompt,
                schema=_schema(list(range(len(target_keys))), list(compatible_elements)),
                max_tokens=min(4096, 64 + 48 * len(target_keys)),
            )
            choices = {item["step_index"]: item["element_id"] for item in response["bindings"]}
            if len(choices) != len(response["bindings"]):
                raise ValueError("model bound a step more than once")
            for i, key in enumerate(target_keys):
                element = compatible_elements.get(choices.get(i, ""))
                if element is not None and _action_compatible(targets[key], element):
                    resolved[key] = element
        except Exception as exc:  # noqa: BLE001 - model failure must degrade to safe fallback
            resolved.clear()
            model_error = f"{type(exc).__name__}: {exc}"

    # Pass 3: apply the shared resolutions to each case.
    for case, steps, deterministic, ambiguous in prepared:
        model_bound: list[int] = []
        fallback_bound: list[int] = []
        failure_reason = ""
        case_compatible = {
            element_id: element for element_id, element in compatible_elements.items()
            if any(_action_compatible(steps[index], element) for index in ambiguous)
        }
        if ambiguous and case_compatible:
            for index in ambiguous:
                element = resolved.get((steps[index].action, steps[index].locator))
                if element is not None:
                    steps[index] = steps[index].model_copy(update={"locator": element.semantic_locator})
                    model_bound.append(index)
                    continue
                # If the model is unavailable or skipped this step, accept only a
                # strong, clearly separated match; ambiguous controls stay unresolved.
                ranked = sorted(
                    ((_candidate_score(steps[index], element), element)
                     for element in case_compatible.values()),
                    key=lambda item: (-item[0], item[1].id),
                )
                if (ranked and ranked[0][0] >= 0.72
                        and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= max(ambiguity_margin, 0.12))):
                    steps[index] = steps[index].model_copy(update={
                        "locator": ranked[0][1].semantic_locator,
                    })
                    fallback_bound.append(index)
            failure_reason = "Ambiguous steps could not be resolved safely: " + (
                model_error or "model did not bind every ambiguous step")
        elif ambiguous:
            failure_reason = "No unique visible semantic locator is available in the element catalog."

        bound_case = case.model_copy(update={"steps": steps})
        all_bound = not ambiguous or len(model_bound) + len(fallback_bound) == len(ambiguous)
        outcomes.append(BindingResult(
            test_case=bound_case,
            verdict="BOUND" if all_bound else "INCONCLUSIVE",
            reason="" if all_bound else failure_reason,
            deterministic_steps=deterministic + fallback_bound,
            model_steps=model_bound,
        ))
    return outcomes


class SemanticTestBinder:
    """Component-registry adapter for the semantic binder."""

    def __init__(self, gateway: StructuredModel | None = None, *, run_id: str = "test-bind") -> None:
        self.gateway = gateway or ModelGateway()
        self.run_id = run_id

    async def bind(
        self, test_cases: Sequence[TestCase], elements: Sequence[ElementCatalogEntry]
    ) -> list[BindingResult]:
        return await bind_cases(test_cases, elements, gateway=self.gateway, run_id=self.run_id)
