from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from contextlib import suppress
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import Evidence, RunEvent
from playwright.async_api import CDPSession, Page
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from argus.browser.session import BrowserSession
from argus.cancellation import is_cancelled
from argus.evidence.recorder import EvidenceRecorder
from argus.perception.a11y import resolve_semantic_locator
from argus.spec.data_factory import TestDataFactory
from argus.state.test_case import Step, TestCase


class TestStepInconclusive(RuntimeError):
    """The current page lacks the data needed to evaluate a step reliably."""


async def execute_case(session: BrowserSession, case: TestCase, layout: RunArtifactLayout,
                       *, initial_url: str | None = None,
                       synthetic_values: tuple[str, ...] = (),
                       data_factory: TestDataFactory | None = None,
                       on_action: Callable[[dict[str, Any]], None] | None = None,
                       step_delay_ms: int = 0) -> tuple[str, Evidence, int]:
    started = asyncio.get_running_loop().time()
    page = session.page
    # Enforce step timeout bounds wherever the case came from, not only at parse time.
    from argus.spec.parser import _bounded_step

    case = case.model_copy(update={"steps": [_bounded_step(step) for step in case.steps]})
    factory = data_factory or TestDataFactory()
    preparation_error = None
    try:
        prepared = factory.prepare(case)
        case = prepared.test_case
    except ValueError as exc:
        prepared = None
        preparation_error = f"Test data preparation failed: {type(exc).__name__}: {exc}"
    recorder = EvidenceRecorder(
        session, layout, case.id, case.steps, expected=case.expected,
        synthetic_values=(
            *synthetic_values,
            *(prepared.synthetic_values if prepared is not None else ()),
        ),
    )
    actual = "Journey completed."
    verdict = "PASS"
    failure_kind: str | None = None
    failed_step_index: int | None = None
    try:
        if preparation_error:
            raise ValueError(preparation_error)
        assert prepared is not None
        await factory.reset(prepared)
    except Exception as exc:  # noqa: BLE001 - reset hooks are user-provided and failures become setup results.
        verdict = "INCONCLUSIVE"
        failure_kind = "setup"
        actual = (
            preparation_error
            or f"Test data reset failed: {type(exc).__name__}: {exc}"
        )
    if initial_url:
        recorder.current_step_index = None
        if verdict == "PASS":
            try:
                await page.goto(initial_url, wait_until="domcontentloaded", timeout=30000)
            except PlaywrightError as exc:
                verdict, actual = "FAIL", f"{type(exc).__name__}: {exc}"
                failure_kind = "setup"
    console_baseline = len(session.console)
    request_baseline = len(session.requests)
    for step_index, step in enumerate(case.steps):
        if verdict != "PASS":
            break
        if is_cancelled(layout.run_dir.name):
            verdict, actual = "INCONCLUSIVE", "Run stopped by user before this step."
            break
        action_started = asyncio.get_running_loop().time()
        action = await _action_payload(page, step, step_index, case)
        layout.append_event(RunEvent(
            id=uuid4().hex, run_id=layout.run_dir.name, agent="tester",
            correlation_id=case.id, type="action",
            payload={"phase": "started", **action},
        ))
        if on_action is not None:
            on_action(action)
        if step_delay_ms > 0:
            # Demo pacing: let viewers see the cursor land before the action fires.
            await asyncio.sleep(step_delay_ms / 1000)
        await recorder.begin_step(
            step_index, _step_element(page, step),
            step=step,
            sensitive=bool(step.value and step.value in recorder.redactor.secret_values),
        )
        try:
            # A wait step sleeps for its full timeout_ms, so give it a grace
            # period; otherwise it always races its own deadline and fails.
            deadline_ms = step.timeout_ms + (1000 if step.action == "wait" else 0)
            async with asyncio.timeout(deadline_ms / 1000):
                await _run_step(
                    page, step, cdp_session=session.cdp_session, session=session,
                    console_baseline=console_baseline, request_baseline=request_baseline,
                )
        except TestStepInconclusive as exc:
            verdict, actual = "INCONCLUSIVE", str(exc)
            failure_kind, failed_step_index = "setup", step_index
        except (TimeoutError, PlaywrightTimeoutError) as exc:
            failed_step_index = step_index
            if step.action == "assert" or step.action.startswith("assert_"):
                verdict = "FAIL"
                failure_kind = "assertion"
                if step.action == "assert":
                    looked_for = step.value or step.locator
                    actual = (f"Assertion at step {step_index} was not satisfied within {step.timeout_ms} ms: "
                              f"expected text {looked_for!r} was not visible on the page.")
                else:
                    detail = str(exc) or f"{step.action} {step.locator}".strip()
                    actual = f"Assertion at step {step_index} was not satisfied within {step.timeout_ms} ms: {detail}"
            else:
                verdict = "INCONCLUSIVE"
                failure_kind = "timeout"
                detail = str(exc) or f"{step.action} {step.locator}".strip()
                actual = f"Step {step_index} timed out after {step.timeout_ms} ms: {detail}"
        except Exception as exc:  # noqa: BLE001 - action failures must be recorded as test results.
            verdict, actual = "FAIL", f"{type(exc).__name__}: {exc}"
            failure_kind = "assertion" if step.action == "assert" or step.action.startswith("assert_") else "interaction"
            failed_step_index = step_index
        await recorder.finish_step(step_index)
        layout.append_event(RunEvent(
            id=uuid4().hex, run_id=layout.run_dir.name, agent="tester",
            correlation_id=case.id, type="action",
            payload={
                "phase": "completed" if verdict == "PASS" else "failed",
                "step_index": step_index,
                "action": step.action,
                "verdict": verdict,
                "duration_ms": int((asyncio.get_running_loop().time() - action_started) * 1000),
            },
        ))
        if verdict != "PASS":
            break
    # Restore per-case emulation even when an interaction failed partway through.
    if any(step.action == "set_offline" for step in case.steps):
        with suppress(PlaywrightError):
            await page.context.set_offline(False)
    if any(step.action == "throttle_network" for step in case.steps) and session.cdp_session is not None:
        with suppress(PlaywrightError):
            await session.cdp_session.send("Network.emulateNetworkConditions", {
                "offline": False,
                "latency": 0,
                "downloadThroughput": -1,
                "uploadThroughput": -1,
                "connectionType": "none",
            })
    evidence = await recorder.finish(
        actual=actual, failure_kind=failure_kind, failed_step_index=failed_step_index,
    )
    elapsed = int((asyncio.get_running_loop().time() - started) * 1000)
    return verdict, evidence, elapsed


async def _action_payload(page: Page, step: Step, step_index: int, case: TestCase) -> dict[str, Any]:
    locator = step.locator or "target element"
    rationale = {
        "goto": "Open the page required for this journey.",
        "click": f"Activate {locator} to continue the {case.journey} journey.",
        "fill": f"Enter test data into {locator} for the {case.journey} journey.",
        "hover": f"Inspect the controls revealed by {locator}.",
        "wait": "Allow the page to settle before continuing.",
        "assert": f"Check the expected result: {locator}.",
    }.get(step.action, f"Run the {step.action.replace('_', ' ')} check for the {case.journey} journey.")
    payload: dict[str, Any] = {
        "action": step.action,
        "locator": step.locator,
        "step_index": step_index,
        "rationale": rationale,
    }
    element = _step_element(page, step)
    if element is not None:
        try:
            try:
                await element.first.scroll_into_view_if_needed(timeout=500)
            except PlaywrightError:
                pass
            # Overlay only: never wait for an element that may not exist yet
            # (the default 30 s wait made every failing assert stall the run).
            box = await element.first.bounding_box(timeout=750)
            viewport = await page.evaluate("() => ({width: innerWidth, height: innerHeight})")
            if box is not None:
                payload.update({
                    "x": box["x"] + box["width"] / 2,
                    "y": box["y"] + box["height"] / 2,
                    "width": box["width"],
                    "height": box["height"],
                    "viewport_width": viewport["width"],
                    "viewport_height": viewport["height"],
                })
        except PlaywrightError:
            # The action still runs and reports its locator error; the overlay is optional.
            pass
    return payload


def _step_element(page: Page, step: Step):
    if step.action in {"click", "double_click", "assert_double_submit", "assert_mobile_layout", "assert_back_mid_flow", "assert_refresh_mid_flow", "fill", "type_text", "hover", "press", "assert_invalid", "assert_password_masked", "assert_value_length", "assert_numeric_value", "assert_input_value", "assert_sort_stability", "assert_numeric_boundary"} and step.locator:
        return _semantic_locator(page, step.locator)
    if step.action == "assert":
        return _assert_target(page, step)
    return None


_HTML_TAGS = ("a|article|aside|body|button|dialog|div|footer|form|h[1-6]|header|img|input|label|li|main|"
              "nav|ol|p|section|select|span|table|tbody|td|textarea|th|tr|ul")
# role=/css= engines, #id, .class, [attr], or a known tag optionally followed by [attr], .class, #id or :pseudo.
_SELECTOR_SHAPE = re.compile(rf"^(role=|css=|text=|xpath=|//|[#.\[]|(?:{_HTML_TAGS})(?:[\[.#:]|$))", re.IGNORECASE)


def _assert_target(page: Page, step: Step):
    """Visible-text assertion, or element visibility when the target is a selector.

    Models sometimes write ``assert img[src]`` or ``assert body``; searching for
    that literal text can never pass, so treat selector-shaped targets as elements.
    """
    if step.value:
        return page.get_by_text(step.value, exact=False)
    target = step.locator.strip()
    if target.startswith("text="):
        return page.get_by_text(target.removeprefix("text=").strip("'\""), exact=False)
    if " " not in target and _SELECTOR_SHAPE.match(target):
        return _semantic_locator(page, target) if target.startswith("role=") else page.locator(target)
    return page.get_by_text(target, exact=False)


async def _run_step(page: Page, step: Step, *, cdp_session: CDPSession | None = None,
                    session: BrowserSession | None = None, console_baseline: int = 0,
                    request_baseline: int = 0) -> None:
    if step.action == "goto":
        destination = step.value or step.locator
        await page.goto(urljoin(page.url, destination), wait_until="domcontentloaded", timeout=step.timeout_ms)
    elif step.action == "wait":
        await page.wait_for_timeout(min(step.timeout_ms, 10000))
    elif step.action == "assert":
        await _assert_target(page, step).first.wait_for(state="visible", timeout=step.timeout_ms)
    elif step.action == "assert_no_broken_images":
        if await page.locator("img").count() == 0:
            raise TestStepInconclusive("This page has no images to check.")
        broken = await page.locator("img").evaluate_all(
            "images => images.filter(image => image.currentSrc && image.complete && image.naturalWidth === 0)"
            ".map(image => image.currentSrc)"
        )
        if broken:
            raise AssertionError(f"Broken images found: {', '.join(broken[:5])}")
    elif step.action == "assert_internal_links":
        links = await page.locator("a[href]").evaluate_all(
            "links => [...new Set(links.map(link => link.href).filter(href => {"
            "try { return new URL(href).origin === location.origin; } catch { return false; }"
            "}))]"
        )
        if not links:
            raise TestStepInconclusive("This page has no same-origin links to check.")
        semaphore = asyncio.Semaphore(8)

        async def check_link(url: str):
            async with semaphore:
                try:
                    response = await page.context.request.get(url, timeout=step.timeout_ms)
                    return url, response.status, None
                except PlaywrightError as exc:
                    return url, None, exc

        results = await asyncio.gather(*(check_link(url) for url in links[:50]))
        failures = [f"{url}: HTTP {status}" if error is None else
                    f"{url}: request failed ({type(error).__name__})"
                    for url, status, error in results
                    if error is not None or (status is not None and status >= 400)]
        if failures:
            raise AssertionError(f"Internal links failed ({len(failures)}): {'; '.join(failures[:5])}")
    elif step.action == "assert_no_console_errors":
        errors = [event for event in (session.console if session else [])
                  if event.get("type") == "error"]
        if errors:
            message = str(errors[0].get("text", "browser console error"))
            raise AssertionError(f"Browser console errors found: {message[:300]}")
    elif step.action == "assert_invalid":
        locator = _semantic_locator(page, step.locator)
        invalid = await locator.evaluate(
            "element => element.getAttribute('aria-invalid') === 'true' || "
            "(typeof element.checkValidity === 'function' && !element.checkValidity())"
        )
        if not invalid:
            raise AssertionError(f"Expected {step.locator} to be invalid after the attempted input")
    elif step.action == "assert_password_masked":
        locator = _semantic_locator(page, step.locator)
        field_type = await locator.get_attribute("type")
        value = await locator.input_value()
        visible_text = await page.locator("body").inner_text()
        if field_type != "password" or (value and value in visible_text):
            raise AssertionError("Password input is not masked or its value is visible in page text")
    elif step.action == "assert_value_length":
        locator = _semantic_locator(page, step.locator)
        actual_length = len(await locator.input_value())
        try:
            expected_length = int(step.value or "")
        except ValueError as exc:
            raise ValueError("assert_value_length requires an integer value") from exc
        if actual_length != expected_length:
            raise AssertionError(f"Expected input length {expected_length}, found {actual_length}")
    elif step.action == "assert_numeric_value":
        locator = _semantic_locator(page, step.locator)
        actual = await locator.input_value()
        try:
            actual_number = float(actual)
            expected_number = float(step.value or "")
        except ValueError as exc:
            raise AssertionError(f"Expected numeric input {step.value!r}, found {actual!r}") from exc
        if actual_number != expected_number:
            raise AssertionError(f"Expected numeric input {expected_number}, found {actual_number}")
    elif step.action == "assert_numeric_boundary":
        locator = _semantic_locator(page, step.locator)
        state = await locator.evaluate("""element => ({
          type: (element.type || '').toLowerCase(), value: element.value,
          parsedFinite: Number.isFinite(element.valueAsNumber), badInput: !!element.validity?.badInput,
          rangeOverflow: !!element.validity?.rangeOverflow, rangeUnderflow: !!element.validity?.rangeUnderflow,
          valid: typeof element.checkValidity === 'function' ? element.checkValidity() : true
        })""")
        if state["type"] != "number":
            raise TestStepInconclusive("Numeric boundary input is not a native number field.")
        if state["badInput"]:
            raise AssertionError("Numeric boundary input remained in an invalid browser parse state")
        if state["value"] and not state["parsedFinite"]:
            raise AssertionError("Numeric input has no finite browser numeric value")
        if state["value"] and (state["rangeOverflow"] or state["rangeUnderflow"]) and state["valid"]:
            raise AssertionError("Browser reports an out-of-range numeric value as valid")
    elif step.action == "assert_input_value":
        locator = _semantic_locator(page, step.locator)
        actual = await locator.input_value()
        if actual != (step.value or ""):
            raise AssertionError(f"Input value was not preserved: expected {step.value!r}, found {actual!r}")
    elif step.action == "assert_no_new_console_errors":
        errors = [event for event in (session.console[console_baseline:] if session else [])
                  if event.get("type") == "error"]
        if errors:
            raise AssertionError(f"New browser error after test input: {str(errors[0].get('text', ''))[:300]}")
    elif step.action == "assert_no_unsafe_markup":
        unsafe = await page.evaluate("""() => {
          const scripts = [...document.scripts].filter(node => /alert\\s*\\(\\s*1\\s*\\)/i.test(node.textContent || ''));
          const images = [...document.images].filter(node => node.getAttribute('src') === 'x'
            && /alert\\s*\\(\\s*1\\s*\\)/i.test(node.getAttribute('onerror') || ''));
          return scripts.length + images.length;
        }""")
        if unsafe:
            raise AssertionError("Untrusted test payload produced executable script or image markup")
    elif step.action == "assert_empty_state":
        text = (await page.locator("body").inner_text()).casefold()
        markers = ("no results", "no matches", "nothing found", "no articles", "no items")
        if not any(marker in text for marker in markers):
            raise AssertionError("No recognizable empty-state message appeared after the zero-result filter")
    elif step.action == "assert_no_text_overflow":
        overflow = await page.locator("li, [role=listitem], tr, td, th, a").evaluate_all(
            "nodes => nodes.filter(node => node.getClientRects().length && "
            "(node.innerText || node.textContent || '').trim().length >= 80 && "
            "node.scrollWidth > node.clientWidth + 1).map(node => (node.innerText || node.textContent || '').trim().slice(0, 100))"
        )
        if overflow:
            raise AssertionError(f"Long list text overflows its container: {overflow[0]!r}")
        long_items = await page.locator("li, [role=listitem], tr, td, th, a").evaluate_all(
            "nodes => nodes.some(node => node.getClientRects().length && "
            "(node.innerText || node.textContent || '').trim().length >= 80)"
        )
        if not long_items:
            raise TestStepInconclusive("No long list item is present to check for overflow.")
    elif step.action == "assert_named_control":
        missing = await page.locator("a, button, input:not([type=hidden]), textarea, select, [role=button], [role=link]").evaluate_all(
            "nodes => nodes.filter(node => node.getClientRects().length && "
            "!((node.getAttribute('aria-label') || '').trim() || "
            "(node.labels && [...node.labels].map(label => label.innerText.trim()).filter(Boolean).join(' ')) || "
            "(node.getAttribute('aria-labelledby') || '').split(/\\s+/).map(id => document.getElementById(id)?.innerText.trim() || '').filter(Boolean).join(' ') || "
            "(node.innerText || node.textContent || '').trim() || "
            "(['button','submit','reset','image'].includes((node.type || '').toLowerCase()) ? (node.value || '').trim() : '') || "
            "(node.getAttribute('alt') || '').trim() || "
            "(node.getAttribute('placeholder') || '').trim() || (node.getAttribute('title') || '').trim())"
            ").map(node => node.outerHTML.slice(0, 160))"
        )
        if missing:
            raise AssertionError(f"Interactive control has no accessible name: {missing[0]}")
        if await page.locator("a, button, input:not([type=hidden]), textarea, select, [role=button], [role=link]").count() == 0:
            raise TestStepInconclusive("This page has no interactive controls to check for accessible names.")
    elif step.action == "assert_pagination_boundaries":
        first = page.get_by_role("button", name=re.compile(r"\b(first|first page)\b", re.IGNORECASE))
        if await first.count() == 0:
            first = page.get_by_role("link", name=re.compile(r"\b(first|first page)\b", re.IGNORECASE))
        last = page.get_by_role("button", name=re.compile(r"\b(last|last page)\b", re.IGNORECASE))
        if await last.count() == 0:
            last = page.get_by_role("link", name=re.compile(r"\b(last|last page)\b", re.IGNORECASE))
        if await first.count() == 0 or await last.count() == 0:
            raise TestStepInconclusive("Pagination first/last controls are not exposed with semantic names.")
        await first.first.click(timeout=step.timeout_ms)
        previous = page.get_by_role("button", name=re.compile(r"\b(previous|prev)\b", re.IGNORECASE))
        if await previous.count() == 0:
            previous = page.get_by_role("link", name=re.compile(r"\b(previous|prev)\b", re.IGNORECASE))
        if await previous.count() == 0:
            raise TestStepInconclusive("Pagination has no semantic previous-page control.")
        previous_disabled = await previous.first.evaluate(
            "element => element.disabled || element.getAttribute('aria-disabled') === 'true'"
        )
        if not previous_disabled:
            raise AssertionError("Previous-page control remains enabled on the first page")
        await last.first.click(timeout=step.timeout_ms)
        following = page.get_by_role("button", name=re.compile(r"\b(next|following)\b", re.IGNORECASE))
        if await following.count() == 0:
            following = page.get_by_role("link", name=re.compile(r"\b(next|following)\b", re.IGNORECASE))
        if await following.count() == 0:
            raise TestStepInconclusive("Pagination has no semantic next-page control.")
        next_disabled = await following.first.evaluate(
            "element => element.disabled || element.getAttribute('aria-disabled') === 'true'"
        )
        if not next_disabled:
            raise AssertionError("Next-page control remains enabled on the last page")
    elif step.action == "assert_protected_route":
        path = await page.evaluate("location.pathname")
        body = (await page.locator("body").inner_text()).casefold()
        denial_markers = ("sign in", "log in", "login", "unauthorized", "forbidden", "access denied")
        protected_path = bool(re.search(r"/(account|dashboard|settings|profile)(?:/|$)", path, re.IGNORECASE))
        if protected_path and not any(marker in body for marker in denial_markers):
            raise AssertionError(f"Logged-out visitor remained on protected route {path!r} without denial feedback")
    elif step.action == "assert_idor_isolation":
        raise TestStepInconclusive(
            "IDOR needs two authenticated users and a known owned resource ID; this run has no account-pair fixture."
        )
    elif step.action == "assert_keyboard_submit":
        if session is None:
            raise TestStepInconclusive("Request telemetry is unavailable for a keyboard-submit check.")
        mutation_methods = {"POST", "PUT", "PATCH", "DELETE"}
        submissions = [event for event in session.requests[request_baseline:]
                       if event.get("method", "").upper() in mutation_methods]
        if not submissions:
            raise AssertionError("Pressing Enter from the keyboard did not submit the form.")
    elif step.action == "assert_sort_stability":
        locator = _semantic_locator(page, step.locator)

        async def sort_snapshot():
            return await locator.evaluate("""control => {
              const header = control.closest('th, [role=columnheader]');
              const table = header && header.closest('table, [role=table], [role=grid]');
              if (!header || !table) return null;
              const headers = [...table.querySelectorAll('thead th, [role=columnheader]')];
              const column = headers.indexOf(header);
              const rows = [...table.querySelectorAll('tbody tr, [role=row]')]
                .filter(row => !row.querySelector('[role=columnheader]'));
              if (column < 0 || rows.length < 2) return null;
              return {
                direction: header.getAttribute('aria-sort') || '',
                rows: rows.map(row => {
                  const cells = [...row.querySelectorAll('th, td, [role=gridcell], [role=rowheader]')];
                  return { key: (cells[column]?.innerText || '').trim(),
                    identity: cells.map(cell => (cell.innerText || '').trim()).join(' | ') };
                })
              };
            }""")

        await locator.click(timeout=step.timeout_ms)
        first = await sort_snapshot()
        if first is None:
            raise TestStepInconclusive("The sort control has no table column and at least two rows to compare.")
        duplicate_keys = {row["key"] for row in first["rows"]
                          if sum(item["key"] == row["key"] for item in first["rows"]) > 1}
        if not duplicate_keys:
            raise TestStepInconclusive("The current page has no duplicate sort keys for a stability check.")
        await locator.click(timeout=step.timeout_ms)
        await locator.click(timeout=step.timeout_ms)
        third = await sort_snapshot()
        if third is None:
            raise TestStepInconclusive("The table changed shape while cycling its sort control.")
        if first["direction"] and third["direction"] and first["direction"] != third["direction"]:
            raise TestStepInconclusive("The sort control did not return to its initial direction after two toggles.")
        first_order = [row["identity"] for row in first["rows"] if row["key"] in duplicate_keys]
        third_order = [row["identity"] for row in third["rows"] if row["key"] in duplicate_keys]
        if first_order != third_order:
            raise AssertionError("Rows with equal sort keys changed relative order after repeated sorting")
    elif step.action == "assert_double_submit":
        if session is None:
            raise TestStepInconclusive("Request telemetry is unavailable for a duplicate-submit check.")
        before = len(session.requests)
        await _semantic_locator(page, step.locator).dblclick(timeout=step.timeout_ms)
        try:
            await page.wait_for_load_state("networkidle", timeout=min(step.timeout_ms, 2000))
        except PlaywrightTimeoutError:
            await page.wait_for_timeout(250)
        mutations = [event for event in session.requests[before:]
                     if event.get("method", "").upper() in {"POST", "PUT", "PATCH", "DELETE"}]
        if not mutations:
            raise TestStepInconclusive("The submit produced no observed mutation request to count.")
        counts: dict[tuple[str, str], int] = {}
        for event in mutations:
            key = (event.get("method", "").upper(), event.get("url", ""))
            counts[key] = counts.get(key, 0) + 1
        duplicate = next((key for key, count in counts.items() if count > 1), None)
        if duplicate:
            raise AssertionError(f"Double activation sent duplicate {duplicate[0]} requests to {duplicate[1]}")
    elif step.action == "assert_mobile_layout":
        layout = await _semantic_locator(page, step.locator).evaluate("""element => {
          const rect = element.getBoundingClientRect();
          return { width: window.innerWidth, pageWidth: document.documentElement.scrollWidth,
            visible: !!element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden',
            withinViewport: rect.left >= -1 && rect.right <= window.innerWidth + 1 };
        }""")
        if not layout["visible"] or not layout["withinViewport"] or layout["pageWidth"] > layout["width"] + 1:
            raise AssertionError("Form control is clipped or the page overflows horizontally at the mobile viewport")
    elif step.action == "assert_back_mid_flow":
        current_url = page.url
        history_length = await page.evaluate("history.length")
        if history_length < 3:
            raise TestStepInconclusive("A prior in-app page is needed to exercise back navigation mid-flow.")
        await page.go_back(timeout=step.timeout_ms)
        if page.url in {current_url, "about:blank"}:
            raise TestStepInconclusive("Browser back did not reach a previous application page.")
        await page.go_forward(timeout=step.timeout_ms)
        if page.url != current_url:
            raise AssertionError("Browser forward did not return to the in-progress form")
        actual_value = await _semantic_locator(page, step.locator).input_value()
        if actual_value != (step.value or ""):
            raise AssertionError("Form input was not preserved after back/forward navigation")
    elif step.action == "assert_refresh_mid_flow":
        if session is None:
            raise TestStepInconclusive("Request telemetry is unavailable for a refresh-safety check.")
        with suppress(PlaywrightTimeoutError):
            await page.wait_for_load_state("networkidle", timeout=min(step.timeout_ms, 2000))
        mutation_methods = {"POST", "PUT", "PATCH", "DELETE"}
        before = [event for event in session.requests if event.get("method", "").upper() in mutation_methods]
        if not before:
            raise TestStepInconclusive("No mutation request was observed before refresh.")
        last = before[-1]
        key = (last.get("method", "").upper(), last.get("url", ""))
        count_before = sum((event.get("method", "").upper(), event.get("url", "")) == key
                           for event in before)
        await page.reload(wait_until="domcontentloaded", timeout=step.timeout_ms)
        with suppress(PlaywrightTimeoutError):
            await page.wait_for_load_state("networkidle", timeout=min(step.timeout_ms, 2000))
        count_after = sum((event.get("method", "").upper(), event.get("url", "")) == key
                          for event in session.requests)
        if count_after > count_before:
            raise AssertionError(f"Refreshing replayed mutation request {key[0]} {key[1]}")
    elif step.action == "back":
        await page.go_back(timeout=step.timeout_ms)
    elif step.action == "reload":
        await page.reload(wait_until="domcontentloaded", timeout=step.timeout_ms)
    elif step.action == "set_viewport":
        match = re.fullmatch(r"(\d{2,4})x(\d{2,4})", step.value or "")
        if not match:
            raise ValueError("set_viewport value must use WIDTHxHEIGHT, for example 375x667")
        await page.set_viewport_size({"width": int(match.group(1)), "height": int(match.group(2))})
    elif step.action == "set_offline":
        if (step.value or "").casefold() not in {"true", "false"}:
            raise ValueError("set_offline value must be true or false")
        await page.context.set_offline((step.value or "").casefold() == "true")
    elif step.action == "throttle_network":
        if (step.value or "").casefold() != "3g":
            raise ValueError("throttle_network currently supports only the 3g profile")
        if cdp_session is None:
            raise RuntimeError("3g network emulation is available only in Chromium sessions")
        await cdp_session.send("Network.enable")
        await cdp_session.send("Network.emulateNetworkConditions", {
            "offline": False,
            "latency": 400,
            "downloadThroughput": 750 * 1024 / 8,
            "uploadThroughput": 250 * 1024 / 8,
            "connectionType": "cellular3g",
        })
    else:
        if step.action == "press" and not step.locator:
            await page.keyboard.press(step.value or "Enter")
            return
        locator = _semantic_locator(page, step.locator)
        if step.action == "click":
            await locator.click(timeout=step.timeout_ms)
        elif step.action == "double_click":
            await locator.dblclick(timeout=step.timeout_ms)
        elif step.action == "fill":
            await locator.fill(step.value or "", timeout=step.timeout_ms)
        elif step.action == "type_text":
            await locator.press_sequentially(step.value or "", timeout=step.timeout_ms)
        elif step.action == "hover":
            await locator.hover(timeout=step.timeout_ms)
        elif step.action == "press":
            await locator.press(step.value or "Enter", timeout=step.timeout_ms)


def _semantic_locator(page: Page, expression: str):
    """Resolve catalog semantic locators, including duplicate-name ordinals."""
    return resolve_semantic_locator(page, expression)
