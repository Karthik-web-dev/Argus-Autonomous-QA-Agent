from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import RunEvent

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class RunArtifactLayout:
    """Resolve and initialize the documented per-run artifact tree."""

    def __init__(self, root: Path, run_id: str):
        if not _SAFE_ID.fullmatch(run_id) or run_id in {".", ".."}:
            raise ValueError("run_id must be a safe path segment")
        self.run_dir = root / run_id
        self.events_path = self.run_dir / "events.ndjson"
        self.state_path = self.run_dir / "state.json"
        self.artifacts_dir = self.run_dir / "artifacts"
        self.tests_dir = self.run_dir / "tests"
        self.reports_dir = self.run_dir / "reports"

    def finding_dir(self, finding_id: str) -> Path:
        if not _SAFE_ID.fullmatch(finding_id) or finding_id in {".", ".."}:
            raise ValueError("finding_id must be a safe path segment")
        return self.artifacts_dir / finding_id

    def initialize_finding(self, finding_id: str) -> dict[str, Path]:
        base = self.finding_dir(finding_id)
        screenshots = base / "screenshots"
        screenshots.mkdir(parents=True, exist_ok=True)
        return {
            "directory": base,
            "trace": base / "trace.zip",
            "screenshots": screenshots,
            "network": base / "network.json",
            "console": base / "console.json",
        }

    def initialize(self) -> RunArtifactLayout:
        for path in (self.run_dir, self.artifacts_dir, self.tests_dir, self.reports_dir):
            path.mkdir(parents=True, exist_ok=True)
        return self

    def append_event(self, event: RunEvent) -> None:
        self.initialize()
        with self.events_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(event.model_dump_json() + "\n")

    def write_state(self, state: dict[str, Any]) -> None:
        self.initialize()
        self.state_path.write_text(json.dumps(state, indent=2, default=str) + "\n", encoding="utf-8")
