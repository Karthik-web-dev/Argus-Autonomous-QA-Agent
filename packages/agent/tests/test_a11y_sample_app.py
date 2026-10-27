"""A-01 acceptance smoke check against the checked-in Workbench sample UI."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from argus.browser.session import BrowserSessionFactory
from argus.perception.a11y import inspect_page

SAMPLE_HTML = Path(__file__).parents[3] / "apps" / "sample-realworld" / "index.html"
SAMPLE_STORIES = [
    {
        "slug": "welcome-to-the-workbench",
        "title": "Welcome to the Workbench",
        "description": "A small place to share what you are building.",
        "body": "Welcome to the sample app.",
        "tagList": ["welcome", "community"],
        "author": "Mira Chen",
        "favoritesCount": 4,
        "favorited": False,
    }
]
ARTICLE_HTML = """<!doctype html>
<html lang="en"><head><title>Welcome to the Workbench</title></head><body>
  <header><a href="/">Workbench</a><nav><a href="/">Home</a>
  <button type="button">Sign in</button></nav></header>
  <main><article><h1>Welcome to the Workbench</h1>
  <p>A small place to share what you are building.</p>
  <p>Welcome to the sample app.</p>
  <button type="button" aria-label="Favorite Welcome to the Workbench">♥ 4</button>
  </article></main>
</body></html>"""


async def test_a01_sample_app_home_login_and_editor(tmp_path: Path):
    """Check catalog coverage, locator uniqueness, stable hashes, and prompt size."""
    html = SAMPLE_HTML.read_text(encoding="utf-8")

    async def serve_sample(route):
        request = route.request
        path = urlsplit(request.url).path
        if path == "/":
            await route.fulfill(status=200, content_type="text/html", body=html)
        elif path == "/articles/welcome-to-the-workbench":
            await route.fulfill(status=200, content_type="text/html", body=ARTICLE_HTML)
        elif path == "/api/stories":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"stories": SAMPLE_STORIES, "currentUser": None, "demoMode": False}
                ),
            )
        elif path == "/api/topics":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"topics": ["community", "welcome"]}),
            )
        elif path in {"/api/auth/session", "/api/stories"} and request.method == "POST":
            await route.fulfill(status=200, content_type="application/json", body="{}")
        else:
            await route.fulfill(status=404, body="not found")

    async with BrowserSessionFactory(artifact_dir=tmp_path) as factory:
        session, _ = await factory.new_context("chromium")
        try:
            page = session.page
            await page.route("http://workbench.test/**", serve_sample)
            await page.goto("http://workbench.test/", wait_until="domcontentloaded")
            await page.get_by_role(
                "heading", name="Welcome to the Workbench"
            ).wait_for()

            async def open_login():
                await page.get_by_role("button", name="Sign in").click()

            async def open_editor():
                await page.get_by_role("button", name="Write a story").click()

            async def open_article():
                await page.goto(
                    "http://workbench.test/articles/welcome-to-the-workbench",
                    wait_until="domcontentloaded",
                )
                await page.get_by_role(
                    "heading", name="Welcome to the Workbench"
                ).wait_for()

            for state_name, prepare in (
                ("home", None),
                ("login", open_login),
                ("editor", open_editor),
                ("article", open_article),
            ):
                if prepare:
                    if state_name in {"editor", "article"}:
                        await page.get_by_role("button", name="Close").click()
                    await prepare()

                first = await inspect_page(page)
                second = await inspect_page(page)
                visible_dom_controls = await page.locator(
                    "a, button, input, textarea, select"
                ).evaluate_all(
                    "els => els.filter(el => { const s=getComputedStyle(el); "
                    "const r=el.getBoundingClientRect(); return r.width>0 && r.height>0 "
                    "&& s.display!=='none' && s.visibility!=='hidden' "
                    "&& Number(s.opacity)>0; }).length"
                )

                visible_catalog_controls = sum(
                    1 for item in first["elements"] if item["visible"]
                )
                assert visible_catalog_controls == visible_dom_controls, state_name
                assert first["visible_strict_mode_resolution_rate"] >= 0.95, state_name
                assert first["compact_token_estimate"] <= 1500, state_name
                assert first["state_signature"] == second["state_signature"], state_name
        finally:
            await session.close()
