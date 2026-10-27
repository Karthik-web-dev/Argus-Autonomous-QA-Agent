import json
from pathlib import Path

from argus.state.test_case import TestCase


def _js(value: str) -> str:
    """Quote a value as a JavaScript string literal (JSON is valid JS)."""
    return json.dumps(value, ensure_ascii=False)


def export_test(case: TestCase, destination: Path, *, base_url: str | None = None) -> Path:
    """Write a standalone Playwright test for one journey.

    Step locators are the Explorer's semantic selectors (``role=button[name="X"]``,
    ``css=...``, optionally ``>> nth=N``), which ``page.locator`` accepts directly.
    Relative ``goto`` targets resolve against ``BASE_URL`` or the run's target URL.
    """
    actions = []
    for step in case.steps:
        target = f"page.locator({_js(step.locator)})" if step.locator else None
        value = _js(step.value or "")
        if step.action == "goto":
            actions.append(f"  await page.goto({_js(step.value or step.locator or '/')});")
        elif step.action == "click" and target:
            actions.append(f"  await {target}.first().click();")
        elif step.action == "double_click" and target:
            actions.append(f"  await {target}.first().dblclick();")
        elif step.action == "fill" and target:
            actions.append(f"  await {target}.first().fill({value});")
        elif step.action == "type_text" and target:
            actions.append(f"  await {target}.first().pressSequentially({value});")
        elif step.action == "press":
            key = _js(step.value or "Enter")
            actions.append(f"  await {target}.first().press({key});" if target else f"  await page.keyboard.press({key});")
        elif step.action == "hover" and target:
            actions.append(f"  await {target}.first().hover();")
        elif step.action == "assert":
            text = _js(step.value or step.locator)
            actions.append(f"  await expect(page.getByText({text}).first()).toBeVisible({{ timeout: {step.timeout_ms} }});")
        elif step.action == "wait":
            actions.append(f"  await page.waitForTimeout({min(step.timeout_ms, 10000)});")
        else:
            # Playbook-only checks (assert_*) have no Playwright equivalent yet.
            actions.append(f"  // Not exported: {step.action} {step.locator}".rstrip())
    header = "import { test, expect } from '@playwright/test';\n\n"
    if base_url:
        header += f"test.use({{ baseURL: process.env.BASE_URL || {_js(base_url)} }});\n\n"
    source = (header + f"test({_js(case.description or case.journey)}, async ({{ page }}) => {{\n"
              + "\n".join(actions) + "\n});\n")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source, encoding="utf-8")
    return destination
