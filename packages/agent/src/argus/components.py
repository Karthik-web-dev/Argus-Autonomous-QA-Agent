"""Role registry for fixture and replaceable walking-skeleton components."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from argus.interfaces import (
    Binder,
    EventBus,
    Explorer,
    Exporter,
    Gate,
    Oracle,
    PlaybookGenerator,
    RedTeam,
    Reporter,
    SpecParser,
    Tester,
)

RoleName = str
ComponentFactory = Callable[[], Any]

ROLE_PROTOCOLS: dict[RoleName, type] = {
    "explorer": Explorer,
    "spec_parser": SpecParser,
    "playbook": PlaybookGenerator,
    "binder": Binder,
    "tester": Tester,
    "oracle": Oracle,
    "gate": Gate,
    "red_team": RedTeam,
    "reporter": Reporter,
    "exporter": Exporter,
    "event_bus": EventBus,
}


class ComponentRegistry:
    """Build a complete role set, allowing selected roles to be replaced.

    Fixture factories provide the offline baseline. A real factory can be
    registered independently for any role; callers can then select only those
    roles while leaving all other fixture components in place.
    """

    def __init__(self) -> None:
        self._fixture_factories: dict[RoleName, ComponentFactory] = {}
        self._real_factories: dict[RoleName, ComponentFactory] = {}

    def register_fixture(self, role: RoleName, factory: ComponentFactory) -> None:
        self._register(self._fixture_factories, role, factory)

    def register_real(self, role: RoleName, factory: ComponentFactory) -> None:
        self._register(self._real_factories, role, factory)

    @staticmethod
    def _register(
        registry: dict[RoleName, ComponentFactory], role: RoleName, factory: ComponentFactory
    ) -> None:
        if role not in ROLE_PROTOCOLS:
            raise ValueError(f"Unknown component role: {role}")
        registry[role] = factory

    def build(self, real_roles: Iterable[RoleName] = ()) -> dict[RoleName, Any]:
        selected = set(real_roles)
        unknown = selected - ROLE_PROTOCOLS.keys()
        if unknown:
            raise ValueError(f"Unknown component role(s): {', '.join(sorted(unknown))}")

        missing_fixtures = ROLE_PROTOCOLS.keys() - self._fixture_factories.keys()
        if missing_fixtures:
            raise ValueError(f"Missing fixture component(s): {', '.join(sorted(missing_fixtures))}")
        missing_real = selected - self._real_factories.keys()
        if missing_real:
            raise ValueError(f"No real component registered for: {', '.join(sorted(missing_real))}")

        components = {
            role: (self._real_factories[role] if role in selected else factory)()
            for role, factory in self._fixture_factories.items()
        }
        for role, component in components.items():
            if not isinstance(component, ROLE_PROTOCOLS[role]):
                raise TypeError(f"Component for {role!r} does not satisfy {ROLE_PROTOCOLS[role].__name__}")
        return components


class DemoExplorer:
    """Contract-compatible deterministic replacement used to demo role swaps."""

    def __init__(self, delegate: Explorer) -> None:
        self.delegate = delegate
        self.calls = 0

    def explore(self, target_url: str):
        if not target_url:
            raise ValueError("target_url must be provided")
        self.calls += 1
        return self.delegate.explore(target_url)


class DemoTester:
    """Contract-compatible deterministic replacement used to demo role swaps."""

    def __init__(self, delegate: Tester) -> None:
        self.delegate = delegate
        self.calls = 0

    def run(self, test_cases, target_url):
        self.calls += 1
        return self.delegate.run(test_cases, target_url)
