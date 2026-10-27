"""Deterministic plain-English wording for bug reports (no LLM call).

Turns oracle output and semantic locators into text a non-technical reader can
follow, e.g. ``role=button[name="Add Oat Milk to basket"]`` becomes
``the "Add Oat Milk to basket" button``.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from argus_contracts.models import Step

_ROLE_NOUNS = {
    "button": "button", "link": "link", "textbox": "field", "searchbox": "search box",
    "combobox": "drop-down", "checkbox": "checkbox", "radio": "option", "tab": "tab",
    "menuitem": "menu item", "spinbutton": "number field", "switch": "switch", "option": "option",
}
_ROLE_LOCATOR = re.compile(r"^role=([\w-]+)(?:\[name=(.+?)\])?(?:\s*>>\s*nth=(\d+))?$")
_HREF_LOCATOR = re.compile(r"""^css=a\[href=(["']?)(.+?)\1\]$""")

# Playbook checks, phrased as what a careful tester would do by hand.
_CHECK_PHRASES = {
    "assert_no_broken_images": "Look at every image on the page and confirm each one loads",
    "assert_internal_links": "Open each link on the page and confirm none leads to an error page",
    "assert_no_console_errors": "Use the page and confirm no error occurs in the browser",
    "assert_no_new_console_errors": "Confirm no error occurs in the browser",
    "assert_empty_state": 'Confirm the page tells you nothing matched (for example "No results found")',
    "assert_no_unsafe_markup": "Confirm the text you typed is shown as plain text and nothing pops up",
    "assert_named_control": "Confirm every button and field has a readable name for screen readers",
    "assert_pagination_boundaries": 'Go to the first and last page and confirm "Previous"/"Next" are disabled there',
    "assert_protected_route": "Confirm the page asks you to sign in",
    "assert_keyboard_submit": "Submit the form using only the keyboard",
    "assert_double_submit": "Click it twice quickly and confirm it is only submitted once",
    "assert_mobile_layout": "Confirm nothing is cut off on a phone-sized screen",
}


def _name(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        value = raw.strip("'\"")
    return str(value)


def describe_target(locator: str) -> str:
    """Name the on-screen control a locator points at."""
    locator = (locator or "").strip()
    match = _ROLE_LOCATOR.match(locator)
    if match:
        role, name = match.group(1).casefold(), _name(match.group(2))
        noun = _ROLE_NOUNS.get(role, role)
        ordinal = f" (number {int(match.group(3)) + 1})" if match.group(3) else ""
        return f'the "{name}" {noun}{ordinal}' if name else f"the {noun}{ordinal}"
    match = _HREF_LOCATOR.match(locator)
    if match:
        return f'the link to {urlsplit(match.group(2)).path or match.group(2)}'
    if locator.startswith("text="):
        return f'the text "{locator.removeprefix("text=").strip(chr(39) + chr(34))}"'
    return f'the element "{locator}"' if locator else "the page"


def _page_name(path: str, base_url: str = "") -> str:
    path = path or "/"
    if path in {"/", ""}:
        return f"the home page ({base_url})" if base_url else "the home page"
    return f"{base_url.rstrip('/')}{path}" if base_url and path.startswith("/") else path


def describe_step(step: Step, base_url: str = "") -> str:
    """One numbered reproduction step, in words a non-technical reader can follow."""
    target = describe_target(step.locator)
    value = step.value or ""
    shown = value if len(value) <= 60 else f"{value[:57]}… ({len(value)} characters)"
    if step.action == "goto":
        return f"Open {_page_name(step.value or step.locator, base_url)}"
    if step.action == "click":
        return f"Click {target}"
    if step.action == "double_click":
        return f"Double-click {target}"
    if step.action == "hover":
        return f"Move the mouse over {target}"
    if step.action in {"fill", "type_text"}:
        if not value.strip():
            return f"Leave {target} empty"
        return f'Type "{shown}" into {target}'
    if step.action == "press":
        key = value or "Enter"
        return f"Press {key}" + (f" in {target}" if step.locator else "")
    if step.action == "wait":
        return "Wait a moment for the page to update"
    if step.action == "assert":
        if value:
            return f'Check that the page shows "{value}"'
        return f"Check that {target} is visible"
    if step.action in _CHECK_PHRASES:
        phrase = _CHECK_PHRASES[step.action]
        return f"{phrase} ({target})" if step.locator and step.action == "assert_double_submit" else phrase
    if step.action == "set_viewport":
        return f"Resize the window to {value or 'a phone screen'}"
    return f"{step.action.replace('_', ' ').capitalize()} {target}".strip()


_HEX_TITLE = re.compile(r"^[0-9a-f]{32,}$", re.IGNORECASE)


def human_title(oracle_id: str, actual: str, steps: list[Step] | None = None) -> str:
    """A short readable title for a finding, derived from what was observed."""
    actual = (actual or "").strip()
    match = re.search(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(\S+?)\s+returned HTTP (\d{3})", actual)
    if match:
        method, endpoint, status = match.groups()
        path = "/" + endpoint.split("/", 1)[1] if "/" in endpoint else endpoint
        filename = path.rstrip("/").rsplit("/", 1)[-1]
        if method == "GET" and re.search(r"\.(png|jpe?g|gif|svg|webp|ico|css|js|woff2?)$", filename, re.IGNORECASE):
            return f"A file is missing (HTTP {status}): {filename}"
        kind = "Server error" if status.startswith("5") else "Request rejected"
        doing = {"GET": "loading", "POST": "submitting to", "PUT": "saving to",
                 "PATCH": "updating", "DELETE": "deleting"}[method]
        return f"{kind} (HTTP {status}) when {doing} {path}"
    match = re.search(r"Failed resource load: \w+ (\S+?)\.?$", actual)
    if match:
        return f"A file failed to load: {match.group(1).rsplit('/', 1)[-1]}"
    match = re.search(r"expected text ['\"](.+)['\"] was not visible", actual)
    if match:
        return f'Expected "{match.group(1)}" did not appear'
    match = re.search(r"Broken images found: (\S+)", actual)
    if match:
        return f"Broken image: {match.group(1).rsplit('/', 1)[-1]}"
    match = re.search(r"Internal links failed \(\d+\): (\S+?): HTTP (\d{3})", actual)
    if match:
        return f"Broken link: {urlsplit(match.group(1)).path or match.group(1)} returns HTTP {match.group(2)}"
    match = re.search(r"Expected (role=\S.*?) to be invalid", actual)
    if match:
        return f"{describe_target(match.group(1)).capitalize()} accepts empty input"
    if "duplicate" in actual.casefold() and "request" in actual.casefold():
        return "Double-clicking submits the same action twice"
    if "No recognizable empty-state message" in actual:
        return 'Searching with no matches shows no "nothing found" message'
    if "executable script or image markup" in actual:
        return "Typed text is run as code (cross-site scripting risk)"
    if "Password input is not masked" in actual:
        return "Password is shown on screen"
    if "no accessible name" in actual:
        return "A control has no readable name for screen-reader users"
    if "protected route" in actual:
        return "A private page opens without signing in"
    if "Previous-page control remains enabled" in actual:
        return '"Previous" stays clickable on the first page'
    match = re.search(r"Failed to load resource: the server responded with a status of (\d{3})", actual)
    if match:
        return f"Something on the page failed to load (HTTP {match.group(1)})"
    message = re.sub(r"^(AssertionError|TypeError|Error):\s*", "", actual)
    if oracle_id == "console-error" and message:
        return f"Browser error: {message[:80]}"
    if message and not _HEX_TITLE.match(message):
        return message[:90].rstrip(".")
    return "Application defect"


_CORE_PATH = re.compile(r"order|checkout|cart|basket|payment|pay\b|login|log-in|sign|session|auth|register|ticket", re.IGNORECASE)


def infer_severity(oracle_id: str, actual: str) -> str | None:
    """Map what was observed onto the P0-P3 rubric; None when there is no signal."""
    actual = actual or ""
    lowered = actual.casefold()
    status = re.search(r"returned HTTP (\d{3})", actual)
    if status:
        code = int(status.group(1))
        if code >= 500:
            return "P0" if _CORE_PATH.search(actual) else "P1"
        return "P2"
    if any(marker in lowered for marker in ("executable script", "protected route", "password input is not masked")):
        return "P1"  # Security or privacy exposure.
    if "was not satisfied" in lowered and "expected text" in lowered:
        return "P1"  # A documented journey outcome did not happen.
    if any(marker in lowered for marker in ("broken images", "internal links failed", "failed resource load")):
        return "P2"
    if any(marker in lowered for marker in ("duplicate", "to be invalid", "empty-state", "no accessible name",
                                            "previous-page control", "console error", "browser error")):
        return "P2"
    if oracle_id == "console-error":
        return "P2"
    return None


def is_unreadable_title(title: str) -> bool:
    return bool(_HEX_TITLE.match((title or "").strip()))
