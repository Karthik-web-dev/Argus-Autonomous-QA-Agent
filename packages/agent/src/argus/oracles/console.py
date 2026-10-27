"""Console and failed-resource oracle with a narrow development-noise allowlist."""

from __future__ import annotations

import re

from argus_contracts.models import Finding

from .common import (
    Execution,
    is_ignored_resource,
    make_finding,
    normalize_endpoint,
    normalize_message,
)

_FRAMEWORK_ERROR = re.compile(
    r"\b(uncaught|uncaught exception|error boundary|react.*error|vue.*error|angular.*error|hydration failed)\b",
    re.IGNORECASE,
)
_NOISE = re.compile(
    r"(download the react devtools|resizeobserver loop limit exceeded|"
    r"third.party cookie will be blocked|was preloaded using link preload but not used|"
    r"net::err_aborted)",
    re.IGNORECASE,
)


class ConsoleOracle:
    """Report uncaught/framework errors and failed non-telemetry resources."""

    oracle_id = "console-error"

    def evaluate(self, execution: Execution) -> list[Finding]:
        evidence = execution.result.evidence
        findings: list[Finding] = []
        seen: set[str] = set()
        for event in evidence.console:
            message = event.message.strip()
            if _NOISE.search(message):
                continue
            if event.level != "error" and not (
                event.level == "warning" and _FRAMEWORK_ERROR.search(message)
            ):
                continue
            normalized = normalize_message(message)
            dedupe_key = f"{normalized}:{event.step_index}"
            if not normalized or dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            findings.append(make_finding(
                execution,
                oracle_id=self.oracle_id,
                normalized_signal=normalized,
                step_index=event.step_index,
                expected=evidence.expected,
                actual=message,
            ))

        for event in evidence.network:
            if not event.failed or event.status is not None or is_ignored_resource(event.url):
                continue
            endpoint = normalize_endpoint(event.url)
            normalized = f"failed resource load {event.method.upper()} {endpoint}"
            dedupe_key = f"{normalized}:{event.step_index}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            findings.append(make_finding(
                execution,
                oracle_id=self.oracle_id,
                normalized_signal=normalized,
                step_index=event.step_index,
                expected=evidence.expected,
                actual=f"Failed resource load: {event.method.upper()} {endpoint}.",
                affected_path=endpoint,
            ))
        return findings
