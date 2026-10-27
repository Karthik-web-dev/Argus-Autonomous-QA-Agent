"""Compatibility imports; canonical contracts live in ``argus_contracts``."""

from argus_contracts.models import ElementCatalogEntry, QAState, TestResult

Element = ElementCatalogEntry

__all__ = ["Element", "QAState", "TestResult"]
