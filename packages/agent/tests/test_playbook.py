from __future__ import annotations

import json
from pathlib import Path

from argus.spec.playbook import generate, registered_checks
from argus_contracts.models import ElementCatalogEntry
from argus_contracts.models import Spec as ProductSpec
from argus_contracts.models import TestCase as ContractTestCase

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures"


def test_playbook_emits_over_forty_schema_valid_cases_from_catalog():
    spec = ProductSpec.model_validate(json.loads((FIXTURES / "spec.json").read_text(encoding="utf-8")))
    elements = [
        ElementCatalogEntry.model_validate(item)
        for item in json.loads((FIXTURES / "element_catalog.json").read_text(encoding="utf-8"))
    ]

    cases = generate(spec, elements)

    assert len(cases) >= 40
    assert len({case.id for case in cases}) == len(cases)
    assert all(ContractTestCase.model_validate(case.model_dump()) == case for case in cases)


def test_every_check_is_a_documented_plugin_with_a_unique_id():
    checks = registered_checks()
    documentation = (ROOT / "docs" / "playbook.md").read_text(encoding="utf-8")

    ids = [check.id for check in checks]
    assert len(checks) >= 40
    assert len(ids) == len(set(ids))
    assert all(f"`{check_id}`" in documentation for check_id in ids)
