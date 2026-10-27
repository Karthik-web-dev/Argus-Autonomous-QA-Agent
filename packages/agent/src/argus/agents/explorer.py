from __future__ import annotations

from argus_contracts.models import ElementCatalogEntry
from playwright.async_api import Page

from argus.perception.a11y import capture_accessibility, capture_element_catalog


async def explore(page: Page) -> tuple[str, list[ElementCatalogEntry]]:
    """Capture the a11y snapshot and a typed semantic control catalog."""
    snapshot = await capture_accessibility(page)
    return snapshot, await capture_element_catalog(page)
