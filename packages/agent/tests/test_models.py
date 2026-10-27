from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from argus.models import (
    BudgetExceeded,
    MalformedModelResponse,
    ModelConfigurationError,
    ModelGateway,
    ModelRoute,
    ModelSettings,
    TIERS,
)


SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def settings(tmp_path: Path, *, mode: str = "live", max_calls: int = 10,
             max_tokens: int = 100) -> ModelSettings:
    routes = {tier: ModelRoute("test", f"{tier}-model", "https://unused.invalid") for tier in TIERS}
    return ModelSettings(routes=routes, mode=mode, cassette_dir=tmp_path,
                         max_calls_per_run=max_calls, max_tokens_per_run=max_tokens,
                         max_tokens_per_call=10)


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def generate(self, **kwargs):
        self.calls += 1
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value, 3


def test_structured_call_uses_gateway_and_recorded_cassette(tmp_path):
    async def scenario():
        provider = FakeProvider([{"answer": "ok"}])
        config = settings(tmp_path, mode="record")
        gateway = ModelGateway(config, provider=provider)
        result = await gateway.generate(tier="cheap", run_id="r1", system="s", prompt="p", schema=SCHEMA)
        assert result == {"answer": "ok"}
        assert provider.calls == 1
        assert (await gateway.budget.snapshot("r1")) == {"calls": 1, "tokens": 3}
        cassette_files = list(tmp_path.glob("*.json"))
        assert len(cassette_files) == 1

        replay = ModelGateway(settings(tmp_path, mode="replay"), provider=FakeProvider([]))
        assert await replay.generate(tier="cheap", run_id="r2", system="s", prompt="p", schema=SCHEMA) == result

    asyncio.run(scenario())


def test_malformed_response_retries_once_then_fails_closed(tmp_path):
    async def scenario():
        provider = FakeProvider([{"wrong": True}, {"answer": 4}])
        gateway = ModelGateway(settings(tmp_path), provider=provider)
        with pytest.raises(MalformedModelResponse):
            await gateway.generate(tier="strong", run_id="r1", system="s", prompt="p", schema=SCHEMA)
        assert provider.calls == 2

    asyncio.run(scenario())


def test_budget_exceeded_prevents_provider_call(tmp_path):
    async def scenario():
        provider = FakeProvider([{"answer": "ok"}])
        gateway = ModelGateway(settings(tmp_path, max_tokens=9), provider=provider)
        with pytest.raises(BudgetExceeded):
            await gateway.generate(tier="cheap", run_id="r1", system="s", prompt="p", schema=SCHEMA)
        assert provider.calls == 0

    asyncio.run(scenario())


def test_red_team_model_must_differ_from_explorer(tmp_path):
    config = settings(tmp_path)
    config.routes["strong_alt"] = config.routes["cheap"]
    with pytest.raises(ModelConfigurationError, match="must resolve to different"):
        ModelGateway(config)


def test_model_swap_is_configuration_only(tmp_path):
    config = settings(tmp_path)
    config.routes["cheap"] = ModelRoute("other-compatible", "new-model", "https://provider.example/v1")
    gateway = ModelGateway(config, provider=FakeProvider([{"answer": "ok"}]))
    assert gateway.settings.routes["cheap"].model == "new-model"


def test_replay_missing_cassette_fails_without_provider(tmp_path):
    async def scenario():
        provider = FakeProvider([])
        gateway = ModelGateway(settings(tmp_path, mode="replay"), provider=provider)
        with pytest.raises(FileNotFoundError):
            await gateway.generate(tier="vlm", run_id="r1", system="s", prompt="p", schema=SCHEMA)
        assert provider.calls == 0

    asyncio.run(scenario())


def test_groq_route_properties_and_env_defaults(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test12345")
    monkeypatch.setenv("ARGUS_MODEL_CHEAP_PROVIDER", "groq")
    monkeypatch.setenv("ARGUS_MODEL_CHEAP_NAME", "llama-3.3-70b-versatile")
    monkeypatch.delenv("ARGUS_MODEL_CHEAP_BASE_URL", raising=False)
    monkeypatch.delenv("ARGUS_MODEL_CHEAP_API_KEY", raising=False)
    monkeypatch.delenv("ARGUS_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("ARGUS_MODEL_API_KEY", raising=False)

    settings = ModelSettings.from_env()
    cheap = settings.routes["cheap"]
    assert cheap.is_groq is True
    assert cheap.is_openrouter is False
    assert cheap.base_url == "https://api.groq.com/openai/v1"
    assert cheap.api_key == "gsk-test12345"
    assert cheap.model == "llama-3.3-70b-versatile"

