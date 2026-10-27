"""Accessible page snapshots and semantic control catalogs."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

from argus_contracts.models import ElementCatalogEntry
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

AGENT_INJECTED_SELECTOR = "[data-argus-agent], [data-argus-injected], [data-argus-overlay], #argus-agent-overlay"
CONTROL_SELECTOR = (
    "a, button, input, textarea, select, "
    "[role=button], [role=link], [role=textbox], [role=searchbox], "
    "[role=checkbox], [role=radio], [role=switch], [role=combobox], "
    "[role=listbox], [role=slider], [role=spinbutton]"
)
DEFAULT_TOKEN_BUDGET = 1500

_VOLATILE_TEXT = re.compile(
    r"\b(?:just now|a few seconds ago|\d+\s+(?:seconds?|minutes?|hours?|days?|weeks?)\s+ago)\b"
    r"|\b\d{4}-\d{1,2}-\d{1,2}(?:[T ][0-9:.+-]+Z?)?\b"
    r"|\b\d{1,2}:\d{2}(?:\s?[AP]M)?\b"
    r"|(?<![\w])\d[\d,]*(?:\.\d+)?(?![\w])",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)

_CONTROL_METADATA_SCRIPT = r"""(elements, injectedSelector) => {
  const hiddenTypes = new Set(['hidden']);
  const roleFor = el => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit.trim().split(/\s+/)[0];
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return el.hasAttribute('href') ? 'link' : null;
    if (tag === 'button') return 'button';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'select') return el.multiple ? 'listbox' : 'combobox';
    if (tag !== 'input') return null;
    const type = (el.getAttribute('type') || 'text').toLowerCase();
    if (hiddenTypes.has(type)) return null;
    if (['button', 'submit', 'reset', 'image'].includes(type)) return 'button';
    if (type === 'checkbox' || type === 'radio' || type === 'range' || type === 'number') return ({
      checkbox: 'checkbox', radio: 'radio', range: 'slider', number: 'spinbutton'
    })[type];
    if (type === 'search') return 'searchbox';
    return 'textbox';
  };
  const text = el => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const accessibleName = el => {
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const parts = labelledby.split(/\s+/).map(id => document.getElementById(id)).filter(Boolean).map(text);
      if (parts.join(' ').trim()) return parts.join(' ').trim();
    }
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return aria.trim();
    const labels = el.labels ? Array.from(el.labels).map(text).filter(Boolean) : [];
    if (labels.length) return labels.join(' ');
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && ['button', 'submit', 'reset', 'image'].includes(type) && el.value) return el.value;
    if (el.getAttribute('alt')) return el.getAttribute('alt').trim();
    if (['button', 'a'].includes(tag) || el.getAttribute('role') === 'button' || el.getAttribute('role') === 'link') {
      const content = text(el);
      if (content) return content;
    }
    const placeholder = el.getAttribute('placeholder');
    if (placeholder) return placeholder.trim();
    const title = el.getAttribute('title');
    return title ? title.trim() : '';
  };
  const isVisible = el => {
    if (!el.isConnected || !el.getClientRects().length) return false;
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) <= 0) return false;
    }
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const forms = Array.from(document.forms);
  return elements.map((el, index) => {
    if (el.closest(injectedSelector)) return null;
    const role = roleFor(el);
    if (!role) return null;
    const name = accessibleName(el);
    const rect = el.getBoundingClientRect();
    const form = el.closest('form');
    const state = {};
    if ('disabled' in el) state.disabled = !!el.disabled;
    if (el instanceof HTMLInputElement) state.field_type = (el.type || 'text').toLowerCase();
    else if (el instanceof HTMLTextAreaElement) state.field_type = 'textarea';
    else if (el instanceof HTMLSelectElement) state.field_type = 'select';
    if (el.hasAttribute('maxlength')) state.max_length = Number(el.getAttribute('maxlength'));
    if (el.hasAttribute('min')) state.min_value = el.getAttribute('min');
    if (el.hasAttribute('max')) state.max_value = el.getAttribute('max');
    if (el.hasAttribute('step')) state.step_value = el.getAttribute('step');
    const columnHeader = el.closest('th, [role=columnheader]');
    if (columnHeader && (el.matches('button, a, [role=button], [role=link]') || el === columnHeader)) {
      state.sort_control = true;
    }
    if ('checked' in el && ['checkbox', 'radio'].includes((el.type || '').toLowerCase())) state.checked = !!el.checked;
    for (const [attr, key] of [['aria-expanded', 'expanded'], ['aria-pressed', 'pressed'], ['aria-selected', 'selected']]) {
      if (el.hasAttribute(attr)) state[key] = el.getAttribute(attr) === 'true';
    }
    if (el.required || el.getAttribute('aria-required') === 'true') state.required = true;
    if (el.readOnly) state.readonly = true;
    if (el.getAttribute('aria-invalid') === 'true') state.invalid = true;
    const formLabel = form && (form.getAttribute('aria-label') || form.getAttribute('name') || form.id);
    const formGroup = form ? (formLabel || `form-${forms.indexOf(form) + 1}`) : null;
    return {
      index, role, name, state, form_group: formGroup,
      visible: isVisible(el),
      enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
      in_viewport: rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth
    };
  }).filter(Boolean);
}"""


@asynccontextmanager
async def _hide_agent_nodes(page: Page):
    """Temporarily hide marked Argus-owned roots from Playwright queries."""
    roots = page.locator(AGENT_INJECTED_SELECTOR)
    if not await roots.count():
        yield
        return
    prefix = f"data-argus-snapshot-{uuid4().hex}"
    saved = await roots.evaluate_all(
        "(nodes, prefix) => nodes.map((node, index) => {"
        "const key = `${prefix}-${index}`;"
        "node.setAttribute(key, node.hasAttribute('aria-hidden') ? node.getAttribute('aria-hidden') : '__absent__');"
        "node.setAttribute('aria-hidden', 'true'); return key; })",
        prefix,
    )
    try:
        yield
    finally:
        await page.evaluate(
            "keys => keys.forEach(key => {"
            "const node = document.querySelector(`[${key}]`); if (!node) return;"
            "const old = node.getAttribute(key); node.removeAttribute(key);"
            "if (old === '__absent__') node.removeAttribute('aria-hidden'); else node.setAttribute('aria-hidden', old);"
            "})",
            saved,
        )


async def capture_accessibility(page: Page) -> str:
    """Return Playwright's ARIA snapshot, excluding Argus overlays.

    Overlay roots use one of the ``data-argus-*`` markers in
    ``AGENT_INJECTED_SELECTOR``. Their original ``aria-hidden`` values are
    restored immediately after capture.
    """
    async with _hide_agent_nodes(page):
        return await page.locator("body").aria_snapshot()


def normalize_volatile_text(value: str) -> str:
    """Normalize counters and timestamps for deterministic page signatures."""
    return re.sub(r"\s+", " ", _VOLATILE_TEXT.sub(" <volatile> ", value)).strip()


def _semantic_locator(role: str, name: str, ordinal: int, matches: int) -> str:
    locator = f"role={role}"
    if name:
        locator += f"[name={json.dumps(name, ensure_ascii=False)}]"
    if matches > 1:
        locator += f" >> nth={ordinal}"
    return locator


async def capture_element_catalog(page: Page) -> list[ElementCatalogEntry]:
    """Capture interactive controls as validated semantic catalog entries."""
    async with _hide_agent_nodes(page):
        raw_items = await page.locator(CONTROL_SELECTOR).evaluate_all(
            _CONTROL_METADATA_SCRIPT,
            AGENT_INJECTED_SELECTOR,
        )
        pair_ordinals: Counter[tuple[str, str]] = Counter()
        visible_pair_ordinals: Counter[tuple[str, str]] = Counter()
        pair_counts = Counter((item["role"], item["name"]) for item in raw_items)
        role_ordinals: Counter[str] = Counter()
        ids: Counter[str] = Counter()
        entries: list[ElementCatalogEntry] = []
        for item in raw_items:
            role, name = item["role"], item["name"]
            pair = (role, name)
            pair_ordinal = pair_ordinals[pair]
            pair_ordinals[pair] += 1
            visible_pair_ordinal = visible_pair_ordinals[pair]
            if item["visible"]:
                visible_pair_ordinals[pair] += 1
            role_ordinal = role_ordinals[role]
            role_ordinals[role] += 1
            try:
                matching = await page.get_by_role(
                    role,
                    name=name,
                    exact=True,
                ).count()
            except PlaywrightError:
                matching = 0
            if matching == 1:
                semantic_locator = _semantic_locator(role, name, 0, 1)
            elif matching > 1:
                ordinal = visible_pair_ordinal if item["visible"] else pair_ordinal
                semantic_locator = _semantic_locator(role, name, ordinal, matching)
            elif pair_counts[pair] > 1:
                semantic_locator = _semantic_locator(
                    role, name, pair_ordinal, pair_counts[pair]
                )
            else:
                role_matching = await page.get_by_role(role).count()
                semantic_locator = _semantic_locator(
                    role, "", role_ordinal, role_matching
                )
            stable_key = (
                f"{role}|{normalize_volatile_text(name)}|{item['form_group'] or ''}"
            )
            digest = hashlib.sha1(stable_key.encode("utf-8")).hexdigest()[:10]
            ids[digest] += 1
            stable_id = f"element-{digest}" + (
                f"-{ids[digest]}" if ids[digest] > 1 else ""
            )
            entries.append(
                ElementCatalogEntry(
                    id=stable_id,
                    role=role,
                    name=name,
                    state=item["state"],
                    semantic_locator=semantic_locator,
                    form_group=item["form_group"],
                    visible=item["visible"],
                    enabled=item["enabled"],
                    in_viewport=item["in_viewport"],
                )
            )
        return entries


def resolve_semantic_locator(page: Page, expression: str):
    """Resolve the catalog's role/name syntax, including duplicate ordinals."""
    if expression.startswith("role="):
        base, separator, ordinal = expression.partition(" >> nth=")
        role_expression = base[5:]
        role, bracket, name_expression = role_expression.partition("[name=")
        name = None
        if bracket:
            raw_name = name_expression.removesuffix("]")
            if raw_name.startswith('"'):
                name = json.loads(raw_name)
            elif raw_name.startswith("'") and raw_name.endswith("'"):
                name = raw_name[1:-1]
            else:
                name = raw_name
        locator = page.get_by_role(role, name=name, exact=True)
        return locator.nth(int(ordinal)) if separator else locator
    if expression.startswith("text="):
        return page.get_by_text(expression[5:], exact=False)
    if expression.startswith("label="):
        return page.get_by_label(expression[6:])
    if expression.startswith("placeholder="):
        return page.get_by_placeholder(expression[12:])
    if expression.startswith("css="):
        return page.locator(expression[4:])
    return page.get_by_role("button", name=expression)


def state_signature(
    url: str, accessibility_snapshot: str, elements: list[ElementCatalogEntry]
) -> str:
    """Hash stable page structure and control state, ignoring volatile text."""
    path = urlsplit(url).path or "/"
    signature_data = {
        "path": path,
        "accessibility": normalize_volatile_text(accessibility_snapshot),
        "elements": [
            {
                "role": item.role,
                "name": normalize_volatile_text(item.name),
                "state": item.state,
                "form_group": normalize_volatile_text(item.form_group or ""),
                "visible": item.visible,
                "enabled": item.enabled,
                "in_viewport": item.in_viewport,
            }
            for item in elements
        ],
    }
    encoded = json.dumps(
        signature_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """Conservative local estimate used to enforce the prompt rendering cap."""
    return max(len(_TOKEN.findall(text)), math.ceil(len(text) / 3))


def render_compact(
    url: str,
    title: str,
    accessibility_snapshot: str,
    elements: list[ElementCatalogEntry],
    *,
    max_tokens: int = DEFAULT_TOKEN_BUDGET,
) -> tuple[str, int]:
    """Render a bounded, prompt-ready view prioritizing interactive controls."""
    if not 1 <= max_tokens <= DEFAULT_TOKEN_BUDGET:
        raise ValueError(f"max_tokens must be between 1 and {DEFAULT_TOKEN_BUDGET}")
    lines = [f"Page: {title or '(untitled)'}", f"URL: {url}", "Interactive controls:"]
    for item in elements:
        state = ", ".join(f"{key}={value}" for key, value in sorted(item.state.items()))
        details = [
            "visible" if item.visible else "hidden",
            "enabled" if item.enabled else "disabled",
        ]
        details.append("in viewport" if item.in_viewport else "outside viewport")
        if item.form_group:
            details.append(f"form={item.form_group}")
        if state:
            details.append(state)
        name = f' "{item.name}"' if item.name else " (unnamed)"
        lines.append(
            f"- {item.role}{name}; {'; '.join(details)}; locator: {item.semantic_locator}"
        )
    lines.append("Accessibility tree:")
    lines.extend(accessibility_snapshot.splitlines())

    output: list[str] = []
    omitted = 0
    for line in lines:
        candidate = "\n".join(output + [line])
        if estimate_tokens(candidate) <= max_tokens:
            output.append(line)
        else:
            omitted += 1
    if omitted:
        marker = f"[truncated: {omitted} lines omitted]"
        while output and estimate_tokens("\n".join(output + [marker])) > max_tokens:
            output.pop()
            omitted += 1
            marker = f"[truncated: {omitted} lines omitted]"
        if estimate_tokens(marker) <= max_tokens:
            output.append(marker)
    compact = "\n".join(output)
    return compact, estimate_tokens(compact)


async def inspect_page(
    page: Page, url: str | None = None, *, max_tokens: int = DEFAULT_TOKEN_BUDGET
) -> dict:
    """Capture an accessibility snapshot and its JSON-serializable catalog."""
    actual_url = url or page.url
    snapshot = await capture_accessibility(page)
    elements = await capture_element_catalog(page)
    title = await page.title()
    compact, token_estimate = render_compact(
        actual_url,
        title,
        snapshot,
        elements,
        max_tokens=max_tokens,
    )
    resolved_count = 0
    visible_resolved = 0
    visible_elements = [entry for entry in elements if entry.visible]
    async with _hide_agent_nodes(page):
        for entry in elements:
            try:
                if (
                    await resolve_semantic_locator(page, entry.semantic_locator).count()
                    == 1
                ):
                    resolved_count += 1
                    if entry.visible:
                        visible_resolved += 1
            except PlaywrightError:
                continue
    return {
        "url": actual_url,
        "title": title,
        "captured_at": datetime.now(UTC).isoformat(),
        "state_signature": state_signature(actual_url, snapshot, elements),
        "accessibility_snapshot": snapshot,
        "elements": [entry.model_dump(mode="json") for entry in elements],
        "compact": compact,
        "compact_token_estimate": token_estimate,
        "strict_mode_resolved": resolved_count,
        "strict_mode_total": len(elements),
        "strict_mode_resolution_rate": resolved_count / len(elements)
        if elements
        else 1.0,
        "visible_strict_mode_resolved": visible_resolved,
        "visible_strict_mode_resolution_rate": visible_resolved / len(visible_elements)
        if visible_elements
        else 1.0,
    }
