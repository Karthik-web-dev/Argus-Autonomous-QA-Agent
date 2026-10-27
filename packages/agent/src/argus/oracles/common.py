"""Shared execution context and stable finding construction."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from argus_contracts.models import Finding, TestCase, TestResult

_UUID = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b")
_LONG_HEX = re.compile(r"(?i)\b[0-9a-f]{16,}\b")
_NUMBER_SEGMENT = re.compile(r"(?<=/)\d+(?=/|$)")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Execution:
    """The case, result, and artifact reference presented to an oracle."""

    test_case: TestCase
    result: TestResult
    target_url: str = ""
    evidence_ref: str = ""


def normalize_endpoint(url: str) -> str:
    """Normalize an endpoint while excluding volatile query strings and IDs."""
    parsed = urlsplit(url)
    host = parsed.netloc.casefold()
    path = _UUID.sub(":id", parsed.path)
    path = _LONG_HEX.sub(":id", path)
    path = _NUMBER_SEGMENT.sub(":id", path)
    path = str(PurePosixPath(path or "/"))
    if path != "/":
        path = path.rstrip("/")
    return f"{host}{path}" if host else path


def normalize_message(message: str) -> str:
    """Normalize dynamic values but preserve the error's diagnostic wording."""
    value = _UUID.sub(":id", message)
    value = _LONG_HEX.sub(":id", value)
    value = re.sub(r"https?://[^\s'\"]+", lambda match: normalize_endpoint(match.group(0)), value)
    value = re.sub(r"\b\d+\b", ":n", value)
    return _SPACE.sub(" ", value).strip().casefold()


def is_ignored_resource(url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.netloc.casefold().split(":", 1)[0]
    path = parsed.path.casefold()
    if path.rsplit("/", 1)[-1] in {"favicon.ico", "favicon.png", "favicon.svg"}:
        return True
    if any(host == domain or host.endswith("." + domain) for domain in (
        "google-analytics.com", "googletagmanager.com", "segment.io", "segment.com",
        "hotjar.com", "doubleclick.net", "amplitude.com",
    )):
        return True
    return any(part in path for part in ("/analytics", "/telemetry", "/tracking", "/collect"))


def make_finding(
    execution: Execution,
    *,
    oracle_id: str,
    normalized_signal: str,
    step_index: int | None,
    expected: str,
    actual: str,
    affected_path: str | None = None,
    confidence: float = 0.95,
) -> Finding:
    """Create a schema-valid finding with a deterministic symptom signature."""
    signature_payload = json.dumps(
        [oracle_id, normalized_signal, step_index],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    signature = hashlib.sha256(signature_payload.encode("utf-8")).hexdigest()
    evidence_ref = (
        execution.evidence_ref
        or execution.result.evidence.trace_path
        or f"test-results/{execution.result.test_id}"
    )
    return Finding(
        id=f"finding-{signature[:24]}",
        oracle_id=oracle_id,
        symptom_signature=signature,
        confidence=confidence,
        steps=execution.result.evidence.steps,
        evidence_ref=evidence_ref,
        expected=expected,
        actual=actual,
        affected_paths=[affected_path] if affected_path else [],
    )
