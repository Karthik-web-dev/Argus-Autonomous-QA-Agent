"""Capture per-step browser evidence into the shared run artifact layout."""
from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import (
    ConsoleEvent,
    Evidence,
    NetworkEvent,
    Step,
    StepEvidence,
)
from playwright.async_api import Error as PlaywrightError

if TYPE_CHECKING:
    from playwright.async_api import Locator

    from argus.browser.session import BrowserSession

_SECRET_LOCATOR = re.compile(r"password|passcode|secret|token|api[-_ ]?key|authorization|credential", re.IGNORECASE)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|passcode|secret|access[_-]?token|refresh[_-]?token|token|api[_-]?key|authorization|credential)\b\s*[:=]\s*)(Bearer\s+[^\s&;,]+|\"[^\"]*\"|'[^']*'|[^\s&;,]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")


class EvidenceRedactor:
    """Redact known credentials while preserving explicitly synthetic values."""

    def __init__(self, *, secret_values: Iterable[str] = (), synthetic_values: Iterable[str] = ()) -> None:
        self.synthetic_values = {str(value) for value in synthetic_values if str(value)}
        self.secret_values = {
            str(value) for value in secret_values
            if str(value) and str(value) not in self.synthetic_values
        }

    @classmethod
    def for_steps(cls, steps: Iterable[Step], *, secret_values: Iterable[str] = (),
                  synthetic_values: Iterable[str] = ()) -> EvidenceRedactor:
        synthetic = {str(value) for value in synthetic_values if str(value)}
        secrets = {str(value) for value in secret_values if str(value)}
        for step in steps:
            if (
                step.action == "fill"
                and step.value
                and step.locator
                and _SECRET_LOCATOR.search(step.locator)
                and step.value not in synthetic
            ):
                secrets.add(step.value)
        return cls(secret_values=secrets, synthetic_values=synthetic)

    def redact_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        protected: dict[str, str] = {}
        text = value
        # Protect factory values before generic token heuristics run. This
        # preserves synthetic fixtures even when they are placed in a token field.
        for index, synthetic in enumerate(sorted(self.synthetic_values, key=len, reverse=True)):
            marker = f"\u0000ARGUS_SYNTHETIC_{index}\u0000"
            if synthetic in text:
                text = text.replace(synthetic, marker)
                protected[marker] = synthetic
        for secret in sorted(self.secret_values, key=len, reverse=True):
            if secret:
                text = text.replace(secret, "***")
        def hide_assignment(match: re.Match[str]) -> str:
            captured = match.group(2)
            if any(marker in captured for marker in protected):
                return match.group(0)
            return f"{match.group(1)}***"

        def hide_bearer(match: re.Match[str]) -> str:
            return match.group(0) if any(marker in match.group(0) for marker in protected) else "Bearer ***"

        text = _SECRET_ASSIGNMENT.sub(hide_assignment, text)
        text = _BEARER.sub(hide_bearer, text)
        text = _JWT.sub("***", text)
        for marker, synthetic in protected.items():
            text = text.replace(marker, synthetic)
        return text

    def redact_step(self, step: Step) -> Step:
        values = step.model_dump()
        for key, value in values.items():
            if isinstance(value, str):
                values[key] = self.redact_text(value)
        return Step.model_validate(values)


class EvidenceRecorder:
    """Collect a consistent evidence bundle for one browser journey.

    The associated BrowserSession should have trace recording enabled. Its
    artifact directory is the F-01 ``artifacts/<artifact_id>`` directory.
    ``synthetic_values`` carries provenance from test-data factories so these
    deterministic fixtures are not mistaken for credentials.
    """

    def __init__(self, session: BrowserSession, layout: RunArtifactLayout, artifact_id: str,
                 steps: Iterable[Step], *, expected: str = "", synthetic_values: Iterable[str] = (),
                 secret_values: Iterable[str] = ()) -> None:
        self.session = session
        self.page = session.page
        self.layout = layout
        self.paths = layout.initialize_finding(artifact_id)
        self.steps = list(steps)
        self.expected = expected
        self.redactor = EvidenceRedactor.for_steps(
            self.steps, secret_values=secret_values, synthetic_values=synthetic_values,
        )
        self.current_step_index: int | None = None
        self._network_entries: list[dict[str, Any]] = []
        self._pending_requests: dict[tuple[int, str, str], deque[dict[str, Any]]] = defaultdict(deque)
        self.console: list[ConsoleEvent] = []
        self.step_evidence: list[StepEvidence] = []
        self.screenshots: list[str] = []
        self._sensitive_locators: list[Locator] = []
        self._finished = False
        self.page.on("request", self._on_request)
        self.page.on("response", self._on_response)
        self.page.on("requestfailed", self._on_request_failed)
        self.page.on("console", self._on_console)
        self.page.on("pageerror", self._on_page_error)
        self.page.on("dialog", self._on_dialog)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _request_key(request: Any) -> tuple[int, str, str]:
        # Playwright may create a new public wrapper when accessing
        # response.request; the underlying implementation object is stable.
        implementation = getattr(request, "_impl_obj", request)
        return id(implementation), request.url, request.method

    def _on_request(self, request: Any) -> None:
        entry = {
            "url": self.redactor.redact_text(request.url) or "",
            "method": request.method,
            "status": None,
            "failed": False,
            "timestamp": self._now(),
            "step_index": self.current_step_index,
        }
        self._network_entries.append(entry)
        self._pending_requests[self._request_key(request)].append(entry)

    def _take_request_entry(self, request: Any) -> dict[str, Any] | None:
        queue = self._pending_requests.get(self._request_key(request))
        if not queue:
            return None
        entry = queue.popleft()
        if not queue:
            self._pending_requests.pop(self._request_key(request), None)
        return entry

    def _on_response(self, response: Any) -> None:
        entry = self._take_request_entry(response.request)
        if entry is None:
            return
        entry["status"] = response.status

    def _on_request_failed(self, request: Any) -> None:
        entry = self._take_request_entry(request)
        if entry is not None:
            entry["failed"] = True

    def _on_console(self, message: Any) -> None:
        level = message.type if message.type in {"debug", "info", "warning", "error"} else "info"
        self.console.append(ConsoleEvent(
            level=level,
            message=self.redactor.redact_text(message.text) or "",
            timestamp=self._now(),
            step_index=self.current_step_index,
        ))

    def _on_page_error(self, error: Any) -> None:
        self.console.append(ConsoleEvent(
            level="error",
            message=self.redactor.redact_text(str(error)) or "Uncaught page error",
            timestamp=self._now(),
            step_index=self.current_step_index,
        ))

    def _on_dialog(self, dialog: Any) -> None:
        self.console.append(ConsoleEvent(
            level="error",
            message=self.redactor.redact_text(f"JavaScript dialog: {dialog.type}") or "JavaScript dialog",
            timestamp=self._now(),
            step_index=self.current_step_index,
        ))

    async def begin_step(self, step_index: int, element: Locator | None = None,
                         *, step: Step | None = None, sensitive: bool = False) -> None:
        """Set the network attribution index and capture the target before action."""
        self.current_step_index = step_index
        if element is not None and step is not None and step.action == "fill" and step.value:
            try:
                field_info = await element.first.evaluate(
                    "el => ({type: el.type || '', name: el.name || '', autocomplete: el.autocomplete || '', label: el.labels?.[0]?.innerText || ''})"
                )
                field_name = " ".join(str(value) for value in field_info.values())
                if _SECRET_LOCATOR.search(field_name) and step.value not in self.redactor.synthetic_values:
                    self.redactor.secret_values.add(step.value)
                    sensitive = True
            except PlaywrightError:
                pass
        if element is None:
            return
        if sensitive:
            self._sensitive_locators.append(element.first)
        element_path = self.paths["screenshots"] / f"step-{step_index:03d}-element.png"
        try:
            screenshot_options: dict[str, Any] = {"path": str(element_path), "timeout": 1500}
            if sensitive:
                screenshot_options.update(mask=[element], mask_color="#000000")
            await element.first.screenshot(**screenshot_options)
        except PlaywrightError:
            return

    async def finish_step(self, step_index: int) -> StepEvidence:
        """Capture a full screenshot and an accessibility snapshot after a step."""
        screenshot = self.paths["screenshots"] / f"step-{step_index:03d}.png"
        try:
            await self.page.screenshot(path=str(screenshot), full_page=True,
                                       mask=self._sensitive_locators, mask_color="#000000")
            screenshot_path: str | None = str(screenshot)
            self.screenshots.append(screenshot_path)
        except PlaywrightError:
            screenshot_path = None
        element_path = self.paths["screenshots"] / f"step-{step_index:03d}-element.png"
        element_screenshot = str(element_path) if element_path.is_file() else None
        try:
            dom_snapshot = await self.page.locator("body").aria_snapshot()
        except PlaywrightError:
            dom_snapshot = None
        dom_snapshot = self.redactor.redact_text(dom_snapshot)
        evidence = StepEvidence(
            step_index=step_index,
            screenshot=screenshot_path,
            element_screenshot=element_screenshot,
            dom_snapshot=dom_snapshot,
        )
        self.step_evidence.append(evidence)
        return evidence

    async def finish(
        self,
        *,
        actual: str,
        failure_kind: str | None = None,
        failed_step_index: int | None = None,
    ) -> Evidence:
        """Flush traces, serialize logs, and return an F-01-validated Evidence."""
        if self._finished:
            raise RuntimeError("EvidenceRecorder.finish() can only be called once")
        self._finished = True
        # Retain requests that never received a response/failure callback.
        for queue in self._pending_requests.values():
            for entry in queue:
                entry["failed"] = True
        self._pending_requests.clear()
        await self.session.close()

        network = [NetworkEvent.model_validate(event) for event in self._network_entries]
        console = self.console
        self.paths["network"].write_text(
            json.dumps([event.model_dump(mode="json") for event in network], indent=2) + "\n",
            encoding="utf-8",
        )
        self.paths["console"].write_text(
            json.dumps([event.model_dump(mode="json") for event in console], indent=2) + "\n",
            encoding="utf-8",
        )
        trace_path = None
        if self.session.recording.trace and self.session.trace_path.is_file():
            if self.session.trace_path.resolve() != self.paths["trace"].resolve():
                self.paths["trace"].write_bytes(self.session.trace_path.read_bytes())
            trace_path = str(self.paths["trace"])
        videos = sorted(self.session.video_dir.glob("*.webm")) if self.session.video_dir.exists() else []
        last_snapshot = self.step_evidence[-1].dom_snapshot if self.step_evidence else None
        return Evidence.model_validate({
            "steps": [self.redactor.redact_step(step).model_dump(mode="json") for step in self.steps],
            "expected": self.redactor.redact_text(self.expected) or "",
            "actual": self.redactor.redact_text(actual) or "",
            "failure_kind": failure_kind,
            "failed_step_index": failed_step_index,
            "network": network,
            "console": console,
            "screenshots": self.screenshots + [item.element_screenshot for item in self.step_evidence
                                               if item.element_screenshot],
            "step_evidence": self.step_evidence,
            "dom_snapshot_after": last_snapshot,
            "trace_path": trace_path,
            "video_path": str(videos[0]) if videos else None,
        })
