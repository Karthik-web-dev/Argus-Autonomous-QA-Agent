"""Deterministic plugin-based edge-case generation."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Sequence
from pathlib import Path

from argus_contracts.models import ElementCatalogEntry, Spec, TestCase

from . import checks
from .checks.common import Check


def registered_checks() -> tuple[Check, ...]:
    """Load each check module once in stable order and reject duplicate IDs."""
    loaded: list[Check] = []
    for module_info in sorted(pkgutil.iter_modules(checks.__path__), key=lambda item: item.name):
        if module_info.name.startswith("_") or module_info.name == "common":
            continue
        module = importlib.import_module(f"{checks.__name__}.{module_info.name}")
        check = getattr(module, "CHECK", None)
        if not isinstance(check, Check):
            raise TypeError(f"{module.__name__} must export a Check as CHECK")
        loaded.append(check)
    ids = [check.id for check in loaded]
    if len(ids) != len(set(ids)):
        raise ValueError("playbook check IDs must be unique")
    return tuple(loaded)


def _fixture_catalog() -> list[ElementCatalogEntry]:
    import json

    path = Path(__file__).resolve().parents[4] / "fixtures" / "element_catalog.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [ElementCatalogEntry.model_validate(row) for row in rows]


def generate(spec: Spec, elements: Sequence[ElementCatalogEntry] | None = None) -> list[TestCase]:
    """Generate schema-valid cases for checks applicable to the element catalog.

    ``elements`` should be the current Explorer catalog. It defaults to the
    checked-in Conduit catalog to support offline use and reproducible demos.
    """
    del spec  # The current check predicates are catalog-driven and deterministic.
    catalog = list(elements) if elements is not None else _fixture_catalog()
    generated: list[TestCase] = []
    for check in registered_checks():
        if not check.condition(catalog):
            continue
        for target in check.targets(catalog):
            generated.append(check.build(catalog, target))
    return generated


class HeuristicPlaybookGenerator:
    """Component-registry adapter for the deterministic check catalog."""

    def generate(
        self, spec: Spec, elements: Sequence[ElementCatalogEntry] | None = None
    ) -> list[TestCase]:
        return generate(spec, elements)
