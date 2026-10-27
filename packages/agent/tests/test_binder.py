from __future__ import annotations

import asyncio
import json
from pathlib import Path

from argus.spec.binder import bind_cases
from argus_contracts.models import ElementCatalogEntry, Step
from argus_contracts.models import TestCase as ContractTestCase

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures"


class FakeGateway:
    def __init__(self, response):
        self.response = response
        self.requests = []

    async def generate(self, **request):
        self.requests.append(request)
        return self.response


def _element(element_id: str, role: str, name: str, locator: str) -> ElementCatalogEntry:
    return ElementCatalogEntry(
        id=element_id,
        role=role,
        name=name,
        semantic_locator=locator,
        visible=True,
        enabled=True,
        in_viewport=True,
    )


def _case(*steps: Step) -> ContractTestCase:
    return ContractTestCase(
        id="binder-case",
        journey="Account setup",
        description="Complete the registration form.",
        steps=list(steps),
    )


def test_unique_semantic_match_is_deterministic_and_skips_model():
    async def scenario():
        elements = [_element("continue", "button", "Continue", 'role=button[name="Continue"]')]
        gateway = FakeGateway({})
        case = _case(Step(action="click", locator="role=button[name=Continue]"))

        result = (await bind_cases([case], elements, gateway=gateway))[0]

        assert result.verdict == "BOUND"
        assert result.deterministic_steps == [0]
        assert result.model_steps == []
        assert result.test_case.steps[0].locator == elements[0].semantic_locator
        assert gateway.requests == []

    asyncio.run(scenario())


def test_ambiguous_match_uses_one_catalog_constrained_call():
    async def scenario():
        elements = [
            _element("favorite-a", "button", "Favorite", 'role=button[name="Favorite"] >> nth=0'),
            _element("favorite-b", "button", "Favorite", 'role=button[name="Favorite"] >> nth=1'),
        ]
        gateway = FakeGateway({"bindings": [{"step_index": 0, "element_id": "favorite-b"}]})
        case = _case(Step(action="click", locator="role=button[name=Favorite]"))

        result = (await bind_cases([case], elements, gateway=gateway))[0]

        assert result.verdict == "BOUND"
        assert result.model_steps == [0]
        assert len(gateway.requests) == 1
        assert gateway.requests[0]["tier"] == "cheap"
        assert "favorite-b" in gateway.requests[0]["schema"]["properties"]["bindings"]["items"]["properties"]["element_id"]["enum"]
        locator = result.test_case.steps[0].locator
        assert locator == elements[1].semantic_locator
        assert "xpath" not in locator.casefold()

    asyncio.run(scenario())


def test_unresolvable_target_is_inconclusive_not_guessed():
    async def scenario():
        elements = [_element("continue", "button", "Continue", 'role=button[name="Continue"]')]
        gateway = FakeGateway({"bindings": []})
        case = _case(Step(action="click", locator="role=button[name=Delete account]"))

        result = (await bind_cases([case], elements, gateway=gateway))[0]

        assert result.verdict == "INCONCLUSIVE"
        assert result.reason
        assert result.test_case.steps[0].locator == "role=button[name=Delete account]"
        assert len(gateway.requests) == 1

    asyncio.run(scenario())


def test_fixture_journeys_bind_at_least_ninety_percent_without_model_calls():
    async def scenario():
        elements = [
            ElementCatalogEntry.model_validate(item)
            for item in json.loads((FIXTURES / "element_catalog.json").read_text(encoding="utf-8"))
        ]
        cases = [
            ContractTestCase.model_validate(item)
            for item in json.loads((FIXTURES / "test_cases.json").read_text(encoding="utf-8"))
        ]
        gateway = FakeGateway({})

        results = await bind_cases(cases, elements, gateway=gateway)

        interactive_steps = [
            step for case in cases for step in case.steps
            if step.action in {"click", "double_click", "fill", "type_text", "hover", "press"}
        ]
        deterministic = sum(len(result.deterministic_steps) for result in results)
        assert deterministic / len(interactive_steps) >= 0.9
        assert all(result.verdict == "BOUND" for result in results)
        assert gateway.requests == []

    asyncio.run(scenario())


def test_shared_ambiguous_steps_across_cases_use_one_model_call():
    async def scenario():
        elements = [
            _element("favorite-a", "button", "Favorite", 'role=button[name="Favorite"] >> nth=0'),
            _element("favorite-b", "button", "Favorite", 'role=button[name="Favorite"] >> nth=1'),
        ]
        gateway = FakeGateway({"bindings": [{"step_index": 0, "element_id": "favorite-a"}]})
        step = Step(action="click", locator="role=button[name=Favorite]")
        cases = [_case(step), _case(Step(action="goto", locator="/"), step)]

        results = await bind_cases(cases, elements, gateway=gateway)

        assert len(gateway.requests) == 1
        assert [r.verdict for r in results] == ["BOUND", "BOUND"]
        assert results[0].model_steps == [0]
        assert results[1].model_steps == [1]
        assert results[1].test_case.steps[1].locator == elements[0].semantic_locator

    asyncio.run(scenario())
