from __future__ import annotations

import json
from pathlib import Path

from argus.browser.session import BrowserSessionFactory
from argus.cli import app
from argus.perception.a11y import (
    estimate_tokens,
    inspect_page,
    normalize_volatile_text,
    render_compact,
)
from argus_contracts.models import ElementCatalogEntry
from typer.testing import CliRunner


async def test_catalog_is_complete_stable_and_filters_argus_overlay(tmp_path: Path):
    html = """<!doctype html>
    <html><head><title>Catalog fixture</title></head><body>
      <a href="/home">Home</a>
      <form aria-label="Account">
        <label for="email">Email</label><input id="email" type="email" required>
        <label for="note">Note</label><textarea id="note" maxlength="256"></textarea>
        <label for="quantity">Quantity</label><input id="quantity" type="number" min="0" max="100" step="1">
        <button type="submit">Search</button>
      </form>
      <p aria-live="polite"><span id="count">4</span> results</p>
      <button>Save</button><button>Save</button>
      <div data-argus-agent aria-hidden="false"><button>Save</button></div>
    </body></html>"""
    async with BrowserSessionFactory(artifact_dir=tmp_path) as factory:
        session, _ = await factory.new_context("chromium")
        try:
            await session.page.set_content(html)
            first = await inspect_page(session.page, "http://fixture.local/home")
            assert first["title"] == "Catalog fixture"
            assert first["strict_mode_total"] == len(first["elements"])
            assert first["visible_strict_mode_resolved"] == 7
            assert first["visible_strict_mode_resolution_rate"] == 1.0
            assert first["accessibility_snapshot"].count('button "Save"') == 2
            assert all(item["name"] != "Agent overlay" for item in first["elements"])
            email = next(item for item in first["elements"] if item["name"] == "Email")
            note = next(item for item in first["elements"] if item["name"] == "Note")
            quantity = next(item for item in first["elements"] if item["name"] == "Quantity")
            assert email["state"]["field_type"] == "email" and email["state"]["required"] is True
            assert note["state"]["max_length"] == 256
            assert quantity["role"] == "spinbutton" and quantity["state"]["max_value"] == "100"
            assert (
                await session.page.locator("[data-argus-agent]").get_attribute(
                    "aria-hidden"
                )
                == "false"
            )

            duplicates = [item for item in first["elements"] if item["name"] == "Save"]
            assert len(duplicates) == 2
            assert duplicates[0]["semantic_locator"].endswith("nth=0")
            assert duplicates[1]["semantic_locator"].endswith("nth=1")

            await session.page.locator("#count").evaluate("el => el.textContent = '12'")
            second = await inspect_page(session.page, "http://fixture.local/home")
            assert first["state_signature"] == second["state_signature"]
            assert first["compact_token_estimate"] <= 1500
        finally:
            await session.close()


def test_compact_rendering_enforces_budget_and_normalizes_counters():
    assert normalize_volatile_text("4 unread messages") == normalize_volatile_text(
        "27 unread messages"
    )
    snapshot = "\n".join(
        f"- text: long static description number {index}" for index in range(300)
    )
    compact, estimate = render_compact(
        "https://example.test/page",
        "Long page",
        snapshot,
        [],
        max_tokens=80,
    )
    assert estimate_tokens(compact) == estimate
    assert estimate <= 80
    assert "truncated" in compact


def test_snapshot_command_writes_page_catalog(tmp_path: Path, monkeypatch):
    class FakePage:
        url = "http://example.test/"

        async def goto(self, *_args, **_kwargs):
            return None

    class FakeSession:
        page = FakePage()

        async def close(self):
            return None

    class FakeFactory:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def new_context(self, *_args):
            return FakeSession(), None

    async def fake_inspect(_page, *, max_tokens):
        return {
            "url": "http://example.test/",
            "title": "Example",
            "captured_at": "2026-01-01T00:00:00+00:00",
            "state_signature": "signature",
            "accessibility_snapshot": "- heading Example",
            "elements": [
                ElementCatalogEntry(
                    id="element-1",
                    role="button",
                    name="Continue",
                    state={},
                    semantic_locator='role=button[name="Continue"]',
                    form_group=None,
                    visible=True,
                    enabled=True,
                    in_viewport=True,
                ).model_dump(mode="json")
            ],
            "compact": "Page: Example",
            "compact_token_estimate": 3,
            "strict_mode_resolved": 1,
            "strict_mode_total": 1,
            "strict_mode_resolution_rate": 1.0,
            "visible_strict_mode_resolved": 1,
            "visible_strict_mode_resolution_rate": 1.0,
        }

    monkeypatch.setattr("argus.browser.session.BrowserSessionFactory", FakeFactory)
    monkeypatch.setattr("argus.perception.a11y.inspect_page", fake_inspect)
    destination = tmp_path / "page.json"
    result = CliRunner().invoke(
        app,
        [
            "snapshot",
            "http://example.test/",
            "--output",
            str(destination),
            "--max-tokens",
            "1200",
        ],
    )
    assert result.exit_code == 0, result.output
    content = json.loads(destination.read_text(encoding="utf-8"))
    assert content["state_signature"] == "signature"
    assert "Strict-mode locators: 1/1" in result.output
