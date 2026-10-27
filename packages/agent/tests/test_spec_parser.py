from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from argus.models import (
    TIERS,
    MalformedModelResponse,
    ModelGateway,
    ModelRoute,
    ModelSettings,
)
from argus.spec.parser import claim_id, parse_spec


class FakeProvider:
    def __init__(self, response):
        self.responses = list(response)
        self.calls = 0
        self.requests = []

    async def generate(self, **request):
        self.calls += 1
        self.requests.append(request)
        return self.responses.pop(0), 5


def _gateway(tmp_path: Path, provider: FakeProvider, mode: str = "live") -> ModelGateway:
    routes = {tier: ModelRoute("test", f"{tier}-model", "https://unused.invalid") for tier in TIERS}
    settings = ModelSettings(
        routes=routes, mode=mode, cassette_dir=tmp_path,
        max_tokens_per_call=4096, max_tokens_per_run=10000,
    )
    return ModelGateway(settings, provider=provider)


def _response() -> dict:
    titles = [
        "Sign up", "Log in", "Create an article", "Favorite an article",
        "Comment on an article", "Update a profile",
    ]
    return {
        "description": "model description",
        "journeys": [
            {
                "id": f"journey-{index:02d}",
                "journey": title,
                "description": f"Verify {title.lower()}.",
                "steps": [{"action": "goto", "value": "/"}],
                "expected": "The journey succeeds.",
            }
            for index, title in enumerate(titles, 1)
        ],
        "claims": [
            {
                "id": "model-id",
                "statement": "Favorite count changes once.",
                "journey_ids": ["journey-01", "unknown-journey"],
            },
            {
                "id": "duplicate-model-id",
                "statement": " favorite   count changes once. ",
                "journey_ids": ["journey-02"],
            },
        ],
        "entities": [],
        "validation_rules": [],
        "auth_requirements": [],
    }


def test_conduit_spec_has_six_journeys_stable_claim_links_and_cassette_replay(tmp_path):
    async def scenario():
        provider = FakeProvider([_response()])
        gateway = _gateway(tmp_path, provider, mode="record")
        description = "Conduit lets people sign up, log in, and publish articles."
        parsed = await parse_spec(
            description,
            context={"README.md": "Visitors can browse the public feed."},
            gateway=gateway,
            run_id="parser-test",
        )

        assert len(parsed.journeys) == 6
        assert {"Sign up", "Log in", "Create an article"} <= {
            journey.journey for journey in parsed.journeys
        }
        assert len(parsed.claims) == 1
        claim = parsed.claims[0]
        assert claim.id == claim_id(claim.statement)
        assert claim.journey_ids == ["journey-01", "journey-02"]
        assert parsed.journeys[0].claim_ids == [claim.id]
        assert parsed.journeys[1].claim_ids == [claim.id]
        assert parsed.description == description
        assert "Visitors can browse the public feed." in provider.requests[0]["prompt"]
        schema = provider.requests[0]["schema"]
        assert schema["properties"]["journeys"]["minItems"] == 6
        assert "assert_idor_isolation" not in json.dumps(schema)
        # Conduit requests 5000 tokens; the per-call cap (4096 above) bounds it.
        assert provider.requests[0]["max_tokens"] == 4096
        assert provider.calls == 1

        replay_provider = FakeProvider([])
        replay = await parse_spec(
            description,
            context={"README.md": "Visitors can browse the public feed."},
            gateway=_gateway(tmp_path, replay_provider, mode="replay"),
            run_id="parser-test",
        )
        assert replay == parsed
        assert replay_provider.calls == 0

        again = await parse_spec(description, gateway=_gateway(tmp_path, FakeProvider([_response()])))
        assert [item.id for item in again.claims] == [claim.id]

    asyncio.run(scenario())


def test_empty_spec_description_is_rejected_before_model_call(tmp_path):
    async def scenario():
        provider = FakeProvider([_response()])
        gateway = _gateway(tmp_path, provider)
        try:
            await parse_spec("  ", gateway=gateway)
        except ValueError as error:
            assert "cannot be empty" in str(error)
        else:
            raise AssertionError("empty description was accepted")
        assert provider.calls == 0

    asyncio.run(scenario())


def test_invalid_structured_output_retries_once_then_fails_cleanly(tmp_path):
    async def scenario():
        provider = FakeProvider([{"not_a_spec": True}, {"still_not_a_spec": True}])
        with pytest.raises(MalformedModelResponse):
            await parse_spec("A product description.", gateway=_gateway(tmp_path, provider))
        assert provider.calls == 2

    asyncio.run(scenario())
