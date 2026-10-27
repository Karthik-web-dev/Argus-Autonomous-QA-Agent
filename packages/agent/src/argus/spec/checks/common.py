"""Small shared factory; individual checks live in their own modules."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from argus_contracts.models import ElementCatalogEntry, Step, TestCase


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    category: str
    family: str
    action: str
    value: str | None
    expected: str
    flow: str | None
    condition: Callable[[Sequence[ElementCatalogEntry]], bool]
    targets: Callable[[Sequence[ElementCatalogEntry]], list[ElementCatalogEntry]]
    build: Callable[[Sequence[ElementCatalogEntry], ElementCatalogEntry], TestCase]


_ROLES = {
    "form": {"textbox", "searchbox"},
    "required": {"textbox", "searchbox"},
    "email": {"textbox", "searchbox"},
    "password": {"textbox"},
    "numeric": {"spinbutton"},
    "submit": {"button"},
    "list": {"button", "link", "option"},
    "any": None,
}
_NON_FILLABLE_TYPES = {"button", "checkbox", "color", "file", "hidden", "image", "radio", "range", "reset", "select", "submit"}
_PAGE_CHECKS = {"assert_no_broken_images", "assert_internal_links", "assert_no_console_errors",
                "assert_empty_state", "assert_no_text_overflow", "assert_pagination_boundaries",
                "assert_protected_route", "assert_idor_isolation"}


def define_check(
    *, id: str, title: str, category: str, family: str,
    action: str, value: str | None, expected: str, flow: str | None = None,
) -> Check:
    if family not in _ROLES:
        raise ValueError(f"unknown check element family: {family}")

    def candidates(elements: Sequence[ElementCatalogEntry]) -> list[ElementCatalogEntry]:
        allowed = _ROLES[family]
        return sorted(
            (element for element in elements if element.visible and element.enabled and
             (allowed is None or element.role.casefold() in allowed
              or (family == "numeric" and element.state.get("field_type") == "number")) and
             (family not in {"form", "required", "email", "password"}
              or element.state.get("field_type") not in _NON_FILLABLE_TYPES) and
             (family != "required" or element.state.get("required") is True) and
             (family != "email" or element.state.get("field_type") == "email") and
             (family != "password" or element.state.get("field_type") == "password") and
             (family != "numeric" or element.role.casefold() == "spinbutton"
              or element.state.get("field_type") == "number") and
             (id not in {"form-negative-number", "form-negative-zero"}
              or _number(element.state.get("min_value")) is not None
              and _number(element.state.get("min_value")) >= 0) and
             (id != "form-decimal-integer"
              or element.state.get("field_type") == "number"
              and element.state.get("step_value", "1") == "1") and
             (id != "list-sort-stability" or element.state.get("sort_control") is True) and
             (family != "submit" or any(word in element.name.casefold()
                                        for word in ("submit", "save", "create", "publish", "register", "comment", "post"))) and
             (flow not in {"throttled", "offline"} or any(
                 control.visible and control.enabled and control.role.casefold() == "button"
                 and control.form_group == element.form_group
                 and any(word in control.name.casefold()
                         for word in ("submit", "save", "create", "publish", "register", "comment", "post"))
                 for control in elements))),
            key=lambda item: (item.form_group or "", item.role, item.name.casefold(), item.id),
        )

    def condition(elements: Sequence[ElementCatalogEntry]) -> bool:
        if id == "list-pagination-boundary":
            names = [element.name.casefold() for element in elements if element.visible and element.enabled]
            has_first = any("first" in name for name in names)
            has_last = any("last" in name for name in names)
            return has_first and has_last and bool(candidates(elements))
        return bool(candidates(elements))

    def targets(elements: Sequence[ElementCatalogEntry]) -> list[ElementCatalogEntry]:
        found = candidates(elements)
        if action in _PAGE_CHECKS or action == "assert_named_control":
            return found[:1]
        return found

    def build(elements: Sequence[ElementCatalogEntry], target: ElementCatalogEntry) -> TestCase:
        if target not in candidates(elements):
            raise ValueError(f"{target.id!r} does not satisfy check {id!r}")
        step_value = value if action in {"fill", "goto", "assert", "press"} else None
        locator = "" if action in _PAGE_CHECKS else target.semantic_locator
        steps = [Step(action=action, locator=locator, value=step_value)]
        if flow == "protected_route":
            steps = [Step(action="goto", value=value or "/account"),
                     Step(action="wait", timeout_ms=250), Step(action="assert_protected_route")]
        elif flow == "sort_stability":
            steps = [Step(action="assert_sort_stability", locator=target.semantic_locator)]
        elif flow == "filter_zero":
            steps = [Step(action="fill", locator=target.semantic_locator, value=value or ""),
                     Step(action="press", locator=target.semantic_locator, value="Enter"),
                     Step(action="wait", timeout_ms=250), Step(action="assert_empty_state")]
        elif flow in {"malformed_filter", "whitespace_filter"}:
            steps = [Step(action="fill", locator=target.semantic_locator, value=value or ""),
                     Step(action="press", locator=target.semantic_locator, value="Enter"),
                     Step(action="wait", timeout_ms=250), Step(action="assert_no_new_console_errors")]
        elif flow == "invalid":
            steps = [Step(action="fill", locator=target.semantic_locator, value=value or "")]
            submit = next((element for element in elements
                           if element.visible and element.enabled and element.role.casefold() == "button"
                           and element.form_group == target.form_group
                           and any(word in element.name.casefold()
                                   for word in ("submit", "save", "create", "publish", "register", "comment", "post"))), None)
            if submit is not None:
                steps.append(Step(action="click", locator=submit.semantic_locator))
            steps.append(Step(action="assert_invalid", locator=target.semantic_locator))
        elif flow == "password":
            steps = [Step(action="fill", locator=target.semantic_locator, value=value or ""),
                     Step(action="assert_password_masked", locator=target.semantic_locator)]
        elif flow == "length":
            raw_length = len(value or "")
            max_length = target.state.get("max_length")
            expected_length = min(raw_length, max_length) if isinstance(max_length, int) and max_length >= 0 else raw_length
            steps = [Step(action="type_text", locator=target.semantic_locator, value=value or ""),
                     Step(action="assert_value_length", locator=target.semantic_locator,
                          value=str(expected_length))]
        elif flow == "preserve":
            steps = [Step(action="fill", locator=target.semantic_locator, value=value or ""),
                     Step(action="assert_input_value", locator=target.semantic_locator, value=value or "")]
        elif flow == "payload":
            steps = [Step(action="fill", locator=target.semantic_locator, value=value or ""),
                     Step(action="press", locator=target.semantic_locator, value="Enter"),
                     Step(action="wait", timeout_ms=250),
                     Step(action="assert_no_new_console_errors")]
            if "xss" in id:
                steps.append(Step(action="assert_no_unsafe_markup"))
        elif flow == "zero_equivalence":
            steps = [Step(action="fill", locator=target.semantic_locator, value="-0"),
                     Step(action="assert_numeric_value", locator=target.semantic_locator, value="0"),
                     Step(action="fill", locator=target.semantic_locator, value="0"),
                     Step(action="assert_numeric_value", locator=target.semantic_locator, value="0")]
        elif flow == "numeric_value":
            steps = [Step(action="fill", locator=target.semantic_locator, value=value or "0"),
                     Step(action="assert_numeric_value", locator=target.semantic_locator, value=value or "0")]
        elif flow == "numeric_boundary":
            steps = [Step(action="fill", locator=target.semantic_locator, value=value or "0"),
                     Step(action="assert_numeric_boundary", locator=target.semantic_locator),
                     Step(action="assert_no_new_console_errors")]
        elif flow == "double_submit":
            steps = [Step(action="assert_double_submit", locator=target.semantic_locator)]
        elif flow in {"back", "refresh", "keyboard"}:
            steps = [Step(action="fill", locator=target.semantic_locator, value="Argus test input")]
            if flow == "back":
                steps.append(Step(action="assert_back_mid_flow", locator=target.semantic_locator,
                                   value="Argus test input"))
            elif flow == "refresh":
                submit = next((element for element in elements
                               if element.visible and element.enabled and element.role.casefold() == "button"
                               and element.form_group == target.form_group
                               and any(word in element.name.casefold()
                                       for word in ("submit", "save", "create", "publish", "register", "comment", "post"))), None)
                if submit is not None:
                    steps.append(Step(action="click", locator=submit.semantic_locator))
                steps.append(Step(action="assert_refresh_mid_flow", locator=target.semantic_locator))
            else:
                group_controls = [element for element in elements
                                  if element.visible and element.form_group == target.form_group]
                steps.extend(Step(action="press", value="Tab") for _ in group_controls)
                steps.append(Step(action="press", value="Enter"))
                steps.append(Step(action="assert_keyboard_submit"))
        elif flow == "mobile":
            steps = [Step(action="set_viewport", value="375x667"),
                     Step(action="fill", locator=target.semantic_locator, value="Argus mobile test input"),
                     Step(action="assert_mobile_layout", locator=target.semantic_locator)]
        elif flow in {"throttled", "offline"}:
            submit = next((element for element in elements
                           if element.visible and element.enabled and element.role.casefold() == "button"
                           and element.form_group == target.form_group
                           and any(word in element.name.casefold()
                                   for word in ("submit", "save", "create", "publish", "register", "comment", "post"))), None)
            if submit is not None:
                setup = Step(action="throttle_network", value="3g") if flow == "throttled" else Step(action="set_offline", value="true")
                steps = [Step(action="fill", locator=target.semantic_locator, value="Argus test input")]
                if flow == "throttled":
                    steps.extend((setup, Step(action="click", locator=submit.semantic_locator)))
                else:
                    steps.extend((setup, Step(action="click", locator=submit.semantic_locator),
                                  Step(action="wait", timeout_ms=1000)))
                if flow == "offline":
                    steps.append(Step(action="set_offline", value="false"))
        return TestCase(
            id=f"playbook-{id}-{target.id}",
            journey=title,
            description=f"Check {title.lower()} for {target.role} {target.name!r}.",
            steps=steps,
            expected=expected,
            category="edge_case",
            source="playbook",
        )

    return Check(id, title, category, family, action, value, expected, flow,
                 condition, targets, build)


def _number(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
