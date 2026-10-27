"""Compatibility imports; canonical contracts live in ``argus_contracts``."""

from argus_contracts.models import (
    ConsoleEvent,
    Evidence,
    NetworkEvent,
    ReproductionResult,
)

__all__ = ["ConsoleEvent", "Evidence", "NetworkEvent", "ReproductionResult"]
