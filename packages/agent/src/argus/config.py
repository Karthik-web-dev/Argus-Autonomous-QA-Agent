from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Repository root: CodeApex/.env
PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    artifact_dir: Path = Path(os.getenv("ARGUS_ARTIFACT_DIR", "artifacts"))
    api_token: str = os.getenv("ARGUS_API_TOKEN", "")
    allowed_domains: tuple[str, ...] = tuple(
        domain.strip().lower()
        for domain in os.getenv(
            "ARGUS_ALLOWED_DOMAINS", "localhost,127.0.0.1"
        ).split(",")
        if domain.strip()
    )
    browser: str = os.getenv("ARGUS_BROWSER", "chromium")
    # Live-run budget: keeps a demo run to a few minutes instead of hundreds of cases.
    playbook_max_cases: int = int(os.getenv("ARGUS_PLAYBOOK_MAX_CASES", "30"))
    playbook_max_targets_per_check: int = int(os.getenv("ARGUS_PLAYBOOK_MAX_TARGETS_PER_CHECK", "2"))
    test_concurrency: int = max(1, int(os.getenv("ARGUS_TEST_CONCURRENCY", "4")))
    # Delay before each step of the case shown in the live view, so humans can follow it.
    demo_step_delay_ms: int = int(os.getenv("ARGUS_DEMO_STEP_DELAY_MS", "350"))


settings = Settings()
