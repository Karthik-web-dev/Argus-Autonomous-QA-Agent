"""Per-execution synthetic data and optional application reset hooks."""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from uuid import uuid4

from argus_contracts.models import TestCase

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}", re.IGNORECASE)

ResetHook = Callable[
    [TestCase, Mapping[str, str]],
    None | Awaitable[None],
]


@dataclass(frozen=True)
class PreparedTestCase:
    """A case with isolated synthetic values ready for one execution."""

    test_case: TestCase
    values: Mapping[str, str]
    synthetic_values: tuple[str, ...]
    execution_token: str


class TestDataFactory:
    """Expand explicit data placeholders into collision-resistant values.

    Supported placeholders are ``{{unique}}``, ``{{token}}``, ``{{email}}``,
    ``{{username}}`` and ``{{display_name}}``. Fixed boundary-test payloads are
    left untouched. An optional reset hook runs once per prepared case and may
    be synchronous or asynchronous.
    """

    __test__ = False

    def __init__(self, reset_hook: ResetHook | None = None) -> None:
        self.reset_hook = reset_hook

    def prepare(self, case: TestCase) -> PreparedTestCase:
        token = uuid4().hex
        values = {
            "unique": token,
            "token": token,
            "email": f"argus+{token}@example.test",
            "username": f"argus-{token}",
            "display_name": f"Argus {token}",
        }

        def expand(value: str | None) -> str | None:
            if value is None:
                return None

            def replace(match: re.Match[str]) -> str:
                key = match.group(1).casefold()
                if key not in values:
                    raise ValueError(f"unknown test-data placeholder: {key}")
                return values[key]

            return _PLACEHOLDER.sub(replace, value)

        steps = [
            step.model_copy(update={"value": expand(step.value)})
            for step in case.steps
        ]
        prepared = case.model_copy(update={
            "steps": steps,
            "expected": expand(case.expected) or "",
        })
        used = {
            match.group(1).casefold()
            for step in case.steps
            for match in _PLACEHOLDER.finditer(step.value or "")
        }
        if _PLACEHOLDER.search(case.expected):
            used.update(match.group(1).casefold() for match in _PLACEHOLDER.finditer(case.expected))
        synthetic_values = tuple(dict.fromkeys(values[name] for name in sorted(used)))
        return PreparedTestCase(prepared, values, synthetic_values, token)

    async def reset(self, prepared: PreparedTestCase) -> None:
        """Run the configured state-reset hook before the case begins."""
        if self.reset_hook is None:
            return
        result = self.reset_hook(prepared.test_case, prepared.values)
        if inspect.isawaitable(result):
            await result
