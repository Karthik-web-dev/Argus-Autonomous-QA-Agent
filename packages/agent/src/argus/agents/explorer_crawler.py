"""Deterministic, same-origin browser crawler used to build an application graph."""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

from argus_contracts import AppGraph, AppGraphEdge, AppGraphNode, ElementCatalogEntry
from playwright.async_api import BrowserContext, Page, Route
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from argus.browser.screencast import CdpScreencastCapture
from argus.browser.session import BrowserSessionFactory
from argus.config import settings
from argus.perception.a11y import (
    AGENT_INJECTED_SELECTOR,
    capture_accessibility,
    capture_element_catalog,
    resolve_semantic_locator,
    state_signature,
)

AuthBootstrap = Callable[[Page], Awaitable[None]]
NavigationGuard = Callable[[str, str], bool]

# Buttons that commonly navigate to a distinct application view. Exclude actions
# that could submit data, mutate records, or trigger irreversible behavior.
_NAVIGATION_BUTTON = re.compile(
    r"\b(sign in|log in|log out|sign up|register|write|create|edit|back|"
    r"home|dashboard|profile|settings|menu|browse|view|continue|feed|topics|"
    r"articles|explore|search|next|previous|more|close|cancel)\b",
    re.IGNORECASE,
)
_UNSAFE_BUTTON = re.compile(
    r"\b(delete|remove|publish|submit|save|favorite|follow|unfollow|log out|logout|sign out|signout|"
    r"like|comment|purchase|pay|send|confirm|reset)\b",
    re.IGNORECASE,
)


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port == (443 if scheme == "https" else 80):
        port = None
    return scheme, host, port


def _default_navigation_guard(source_url: str, destination_url: str) -> bool:
    """Temporary D-07 seam: permit only same-origin HTTP(S) navigation."""
    return (
        urlsplit(destination_url).scheme in {"http", "https"}
        and _origin(source_url) == _origin(destination_url)
    )


def _canonical_url(url: str) -> str:
    # Hash fragments can be SPA routes, so preserve them while normalizing empties.
    parts = urlsplit(url)
    return parts._replace(fragment=parts.fragment.rstrip("#")).geturl()


class DeterministicCrawler:
    """Crawl reachable same-origin views and persist a validated ``AppGraph``.

    ``auth_bootstrap`` is a code-owned login callback, not an LLM action. When
    supplied, the crawler records browser storage state after logging in and
    performs a second crawl in a fresh authenticated context.
    """

    def __init__(
        self,
        *,
        session_factory: BrowserSessionFactory | None = None,
        browser_type: str = "chromium",
        max_pages: int = 50,
        max_steps: int = 500,
        navigation_guard: NavigationGuard | None = None,
        auth_bootstrap: AuthBootstrap | None = None,
        timeout_ms: int = 8000,
        on_screencast_frame: Callable[[dict[str, Any]], None] | None = None,
        on_action: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if max_pages < 1 or max_steps < 1:
            raise ValueError("max_pages and max_steps must be at least 1")
        if timeout_ms < 1:
            raise ValueError("timeout_ms must be at least 1")
        self.session_factory = session_factory
        self.browser_type = browser_type
        self.max_pages = max_pages
        self.max_steps = max_steps
        self.navigation_guard = navigation_guard or _default_navigation_guard
        self.auth_bootstrap = auth_bootstrap
        self.timeout_ms = timeout_ms
        self.on_screencast_frame = on_screencast_frame
        self.on_action = on_action
        self._graph = AppGraph()
        self._step_count = 0
        self._origin_url = ""

    async def crawl(self, start_url: str, output_path: str | Path) -> AppGraph:
        """Crawl logged-out and, when configured, logged-in views."""
        parts = urlsplit(start_url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("start_url must be an absolute HTTP(S) URL")
        self._origin_url = start_url
        self._graph = AppGraph()
        self._step_count = 0
        owns_factory = self.session_factory is None
        factory = self.session_factory or BrowserSessionFactory(
            artifact_dir=Path(output_path).parent / "browser"
        )
        try:
            if owns_factory:
                await factory.start()
            await self._crawl_context(factory, start_url, authenticated=False)
            if self.auth_bootstrap is not None and self._step_count < self.max_steps:
                auth_session, _ = await factory.new_context(self.browser_type)
                storage_state: dict[str, Any]
                try:
                    await self._install_navigation_guard(auth_session.context)
                    await auth_session.page.goto(
                        start_url, wait_until="domcontentloaded", timeout=self.timeout_ms
                    )
                    await self.auth_bootstrap(auth_session.page)
                    storage_state = await auth_session.context.storage_state()
                finally:
                    await auth_session.close()
                destination = Path(output_path)
                storage_path = destination.parent / "storage_state.json"
                storage_path.parent.mkdir(parents=True, exist_ok=True)
                storage_path.write_text(
                    json.dumps(storage_state, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                await self._crawl_context(
                    factory, start_url, authenticated=True, storage_state=storage_state
                )
        finally:
            if owns_factory:
                await factory.close()
        # Replace link placeholders with signature IDs after every destination is
        # captured. This keeps edges useful when pages are visited breadth-first.
        node_by_url = {
            (node.authenticated, _canonical_url(node.url)): node
            for node in self._graph.nodes
            if node.captured
        }
        placeholder_ids = {
            node.id
            for node in self._graph.nodes
            if not node.captured
        }
        id_remap: dict[str, str] = {}
        for node in self._graph.nodes:
            if node.id in placeholder_ids:
                resolved = node_by_url.get((node.authenticated, _canonical_url(node.url)))
                if resolved is not None:
                    id_remap[node.id] = resolved.id
        resolved_nodes = [node for node in self._graph.nodes if node.id not in id_remap]
        resolved_edges = [
            edge.model_copy(update={
                "source": id_remap.get(edge.source, edge.source),
                "target": id_remap.get(edge.target, edge.target),
            })
            for edge in self._graph.edges
        ]
        urls_by_id = {node.id: node.url for node in resolved_nodes}
        adjacency: dict[str, set[str]] = {node.url: set() for node in resolved_nodes}
        for edge in resolved_edges:
            source_url = urls_by_id.get(edge.source)
            target_url = urls_by_id.get(edge.target)
            if source_url is not None and target_url is not None:
                adjacency.setdefault(source_url, set()).add(target_url)
        self._graph = AppGraph(
            adjacency={url: sorted(targets) for url, targets in sorted(adjacency.items())},
            nodes=sorted(resolved_nodes, key=lambda node: (node.authenticated, node.url, node.id)),
            edges=sorted(
                resolved_edges,
                key=lambda edge: (edge.source, edge.target, edge.action, edge.locator),
            ),
        )
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self._graph.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return AppGraph.model_validate_json(destination.read_text(encoding="utf-8"))

    async def _crawl_context(
        self,
        factory: BrowserSessionFactory,
        start_url: str,
        *,
        authenticated: bool,
        storage_state: dict[str, Any] | None = None,
    ) -> None:
        session, cdp_session = await factory.new_context(
            self.browser_type, storage_state=storage_state
        )
        capture = None
        try:
            if self.on_screencast_frame is not None and cdp_session is not None:
                capture = CdpScreencastCapture(
                    cdp_session, self.on_screencast_frame, page=session.page,
                )
                await capture.start()
            await self._install_navigation_guard(session.context)
            page = session.page
            queue: deque[str] = deque([_canonical_url(start_url)])
            visited_urls: set[str] = set()
            visited_states: set[str] = set()
            while queue and len(visited_urls) < self.max_pages and self._step_count < self.max_steps:
                url = queue.popleft()
                if url in visited_urls:
                    continue
                if not self.navigation_guard(self._origin_url, url):
                    continue
                visited_urls.add(url)
                self._step_count += 1
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                except PlaywrightTimeoutError:
                    # Keep the page if the document committed despite a slow load.
                    if page.url != url:
                        continue
                if not self.navigation_guard(self._origin_url, page.url):
                    continue
                node = await self._capture_node(page, authenticated)
                if node is None:
                    continue
                state_needs_button_scan = node.id not in visited_states
                visited_states.add(node.id)
                links = await self._read_links(page, node.elements)
                for href, locator in links:
                    absolute = _canonical_url(urljoin(page.url, href))
                    if not self.navigation_guard(page.url, absolute):
                        continue
                    self._step_count += 1
                    if absolute not in visited_urls and len(visited_urls) + len(queue) < self.max_pages:
                        queue.append(absolute)
                    self._add_edge(node, absolute, "link", locator, authenticated)
                    if self._step_count >= self.max_steps:
                        break
                if state_needs_button_scan and self._step_count < self.max_steps:
                    await self._inspect_navigation_buttons(
                        page, node, authenticated, visited_states, queue, visited_urls
                    )
        finally:
            if capture is not None:
                await capture.stop()
            await session.close()

    async def _install_navigation_guard(self, context: BrowserContext) -> None:
        async def guard_navigation(route: Route) -> None:
            request = route.request
            if (
                request.is_navigation_request()
                and not self.navigation_guard(self._origin_url, request.url)
            ):
                await route.abort()
            else:
                await route.continue_()

        await context.route("**/*", guard_navigation)

    async def _capture_node(self, page: Page, authenticated: bool) -> AppGraphNode:
        snapshot = await capture_accessibility(page)
        elements = await capture_element_catalog(page)
        signature = state_signature(page.url, snapshot, elements)
        node_id = ("auth-" if authenticated else "") + signature
        existing = next((node for node in self._graph.nodes if node.id == node_id), None)
        if existing is None:
            node = AppGraphNode(
                id=node_id,
                url=page.url,
                signature=signature,
                title=await page.title(),
                accessibility_snapshot=snapshot,
                elements=elements,
                authenticated=authenticated,
            )
            self._graph.nodes.append(node)
            return node
        return existing

    async def _read_links(
        self, page: Page, elements: list[ElementCatalogEntry]
    ) -> list[tuple[str, str]]:
        raw = await page.locator("a[href]").evaluate_all(
            "(nodes, injectedSelector) => nodes.map((node, index) => {"
            "const style = getComputedStyle(node); const rect = node.getBoundingClientRect();"
            "const visible = !!node.getClientRects().length && rect.width > 0 && rect.height > 0 "
            "&& style.display !== 'none' && style.visibility !== 'hidden' "
            "&& Number(style.opacity) > 0 && !node.closest(injectedSelector);"
            "return {href: node.href, name: (node.getAttribute('aria-label') || "
            "node.innerText || node.getAttribute('title') || '').replace(/\\s+/g, ' ').trim(), "
            "index, visible}; }).filter(item => item.visible)",
            AGENT_INJECTED_SELECTOR,
        )
        links: list[tuple[str, str]] = []
        catalog_links = [item for item in elements if item.role == "link" and item.visible]
        used_ids: set[str] = set()
        for item in raw:
            destination = item["href"]
            if not self.navigation_guard(page.url, destination):
                continue
            label = item["name"]
            catalog_entry = next(
                (
                    entry for entry in catalog_links
                    if entry.id not in used_ids and entry.name == label
                ),
                None,
            )
            if catalog_entry is not None:
                used_ids.add(catalog_entry.id)
                semantic_locator = catalog_entry.semantic_locator
            elif label:
                count = await page.get_by_role("link", name=label, exact=True).count()
                ordinal = sum(1 for _, previous in links if previous.startswith(f"role=link[name={json.dumps(label)}]"))
                semantic_locator = f"role=link[name={json.dumps(label, ensure_ascii=False)}]"
                if count > 1:
                    semantic_locator += f" >> nth={ordinal}"
            else:
                semantic_locator = f"css=a[href={json.dumps(destination, ensure_ascii=False)}]"
            links.append((destination, semantic_locator))
        return links

    async def _inspect_navigation_buttons(
        self,
        page: Page,
        source_node: AppGraphNode,
        authenticated: bool,
        visited_states: set[str],
        queue: deque[str],
        visited_urls: set[str],
    ) -> None:
        controls = [
            item for item in source_node.elements
            if item.role == "button" and item.visible and item.enabled
        ]
        for control in controls:
            if self._step_count >= self.max_steps:
                break
            label = control.name.strip()
            if (
                not label
                or control.form_group is not None
                or not (
                    _NAVIGATION_BUTTON.search(label)
                    or any(key in control.state for key in ("expanded", "selected"))
                )
                or _UNSAFE_BUTTON.search(label)
            ):
                continue
            locator = resolve_semantic_locator(page, control.semantic_locator)
            if await locator.count() != 1:
                continue
            self._step_count += 1
            source_url = page.url
            if self.on_action is not None:
                try:
                    box = await locator.first.bounding_box()
                    viewport = await page.evaluate("() => ({width: innerWidth, height: innerHeight})")
                    if box is not None:
                        self.on_action({
                            "action": "click",
                            "locator": control.semantic_locator,
                            "rationale": f"Explore {label} to discover new application states.",
                            "x": box["x"] + box["width"] / 2,
                            "y": box["y"] + box["height"] / 2,
                            "width": box["width"],
                            "height": box["height"],
                            "viewport_width": viewport["width"],
                            "viewport_height": viewport["height"],
                        })
                except PlaywrightError:
                    pass
            try:
                await locator.click(timeout=min(self.timeout_ms, 2500))
                await page.wait_for_timeout(100)
            except PlaywrightError:
                # A failed candidate does not stop exploration of other controls.
                if page.url != source_url and self.navigation_guard(source_url, page.url):
                    await page.goto(source_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                continue
            target_url = page.url
            if not self.navigation_guard(source_url, target_url):
                await page.goto(source_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                continue
            target_node = await self._capture_node(page, authenticated)
            if target_node is not None and target_node.id != source_node.id:
                self._add_edge(source_node, target_url, "button", control.semantic_locator, authenticated, target_node)
                if (
                    target_url != source_url
                    and target_url not in visited_urls
                    and len(visited_urls) + len(queue) < self.max_pages
                    and target_url not in queue
                ):
                    queue.append(target_url)
                for href, link_locator in await self._read_links(page, target_node.elements):
                    destination = _canonical_url(urljoin(page.url, href))
                    if not self.navigation_guard(page.url, destination):
                        continue
                    self._step_count += 1
                    self._add_edge(
                        target_node, destination, "link", link_locator, authenticated
                    )
                    if (
                        destination not in visited_urls
                        and destination not in queue
                        and len(visited_urls) + len(queue) < self.max_pages
                    ):
                        queue.append(destination)
                    if self._step_count >= self.max_steps:
                        break
            if page.url != source_url:
                await page.goto(source_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            else:
                # SPA state may have changed in place. Reload restores a deterministic
                # baseline for the next candidate without carrying modal/menu state.
                await page.reload(wait_until="domcontentloaded", timeout=self.timeout_ms)

    def _add_edge(
        self,
        source_node: AppGraphNode,
        target_url: str,
        action: Literal["link", "button"],
        locator: str,
        authenticated: bool,
        known_target: AppGraphNode | None = None,
    ) -> None:
        target_node = known_target or next(
            (
                node for node in self._graph.nodes
                if node.authenticated == authenticated and node.url == target_url
            ),
            None,
        )
        # Link targets may not have been visited yet; resolve their target id
        # deterministically from URL/auth state. The subsequent page capture uses
        # the same signature-based node id when this URL is visited.
        target_id = target_node.id if target_node else (
            ("auth-url-" if authenticated else "url-")
            + hashlib.sha256(target_url.encode("utf-8")).hexdigest()[:24]
        )
        if not target_node and not any(node.id == target_id for node in self._graph.nodes):
            self._graph.nodes.append(
                AppGraphNode(
                    id=target_id,
                    url=target_url,
                    signature=target_id,
                    authenticated=authenticated,
                    captured=False,
                )
            )
        self._graph.edges.append(
            AppGraphEdge(
                source=source_node.id,
                target=target_id,
                action=action,
                locator=locator,
            )
        )


async def crawl_app(
    start_url: str,
    output_path: str | Path,
    *,
    auth_bootstrap: AuthBootstrap | None = None,
    max_pages: int = 50,
    max_steps: int = 500,
    navigation_guard: NavigationGuard | None = None,
    browser_type: str | None = None,
    on_screencast_frame: Callable[[dict[str, Any]], None] | None = None,
    on_action: Callable[[dict[str, Any]], None] | None = None,
) -> AppGraph:
    """Convenience entry point using the configured browser and crawl limits."""
    crawler = DeterministicCrawler(
        max_pages=max_pages,
        max_steps=max_steps,
        navigation_guard=navigation_guard,
        auth_bootstrap=auth_bootstrap,
        browser_type=browser_type or settings.browser,
        on_screencast_frame=on_screencast_frame,
        on_action=on_action,
    )
    return await crawler.crawl(start_url, output_path)
