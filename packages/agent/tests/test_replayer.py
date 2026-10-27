from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from argus.browser.session import BrowserSessionFactory
from argus.replay import ReplayVariation, replay
from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import Finding, Step


class _ReplayHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"""<!doctype html><html><body><script>
          const count = Number(localStorage.getItem('attempt-count') || '0') + 1;
          localStorage.setItem('attempt-count', String(count));
          console.info(`attempt-count:${count}`);
        </script>Replay fixture</body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture(scope="module")
def replay_origin():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ReplayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _finding(signature: str = "attempt-count:1") -> Finding:
    return Finding(
        id="fixture-finding", oracle_id="console", symptom_signature=signature,
        confidence=0.9, evidence_ref="artifacts/fixture-finding",
        steps=[Step(action="goto", value="{{destination}}")],
        expected="The fixture page loads.",
    )


async def test_replays_five_times_with_traces_and_isolated_storage(tmp_path: Path, replay_origin: str):
    layout = RunArtifactLayout(tmp_path / "runs", "replay-run").initialize()
    reset_calls: list[int] = []
    values: list[str] = []

    def make_destination(name: str, attempt_index: int) -> str:
        assert name == "destination"
        destination = f"{replay_origin}?attempt={attempt_index}"
        values.append(destination)
        return destination

    async def reset(attempt_index: int):
        reset_calls.append(attempt_index)

    async with BrowserSessionFactory(artifact_dir=layout.artifacts_dir) as factory:
        result = await replay(
            _finding(), 5, target_url=replay_origin, browser_factory=factory,
            layout=layout, value_factory=make_destination, reset_hook=reset,
        )

    assert result.successes == 5
    assert result.reproduced
    assert reset_calls == list(range(5))
    assert values == [f"{replay_origin}?attempt={index}" for index in range(5)]
    assert len(result.attempts) == 5
    for attempt in result.attempts:
        assert attempt.matched
        assert attempt.evidence.trace_path
        assert Path(attempt.evidence.trace_path).is_file()
        assert attempt.evidence.steps[0].value == values[attempt.index - 1]
        assert any(event.message == "attempt-count:1" for event in attempt.evidence.console)
        assert (layout.artifacts_dir / f"fixture-finding-replay-{attempt.index:03d}" / "network.json").is_file()


async def test_replay_applies_red_team_variation_and_returns_partial_matches(
    tmp_path: Path, replay_origin: str,
):
    layout = RunArtifactLayout(tmp_path / "runs", "variation-run").initialize()
    variation = ReplayVariation(viewport={"width": 390, "height": 844}, clear_storage=True)
    async with BrowserSessionFactory(artifact_dir=layout.artifacts_dir) as factory:
        result = await replay(
            _finding("not-present"), 2, target_url=replay_origin,
            browser_factory=factory, layout=layout, variations=[variation],
            value_factory=lambda _name, index: f"{replay_origin}?attempt={index}",
        )
    assert result.successes == 0
    assert not result.reproduced
    assert all(attempt.variation == variation for attempt in result.attempts)
    assert all(not attempt.matched for attempt in result.attempts)


async def test_replay_preserves_partial_reproduction_rate(tmp_path: Path, replay_origin: str):
    layout = RunArtifactLayout(tmp_path / "runs", "partial-run").initialize()
    seen = 0

    def flaky_matcher(_finding, _evidence):
        nonlocal seen
        seen += 1
        return seen % 2 == 1

    async with BrowserSessionFactory(artifact_dir=layout.artifacts_dir) as factory:
        result = await replay(
            _finding(), 5, target_url=replay_origin, browser_factory=factory,
            layout=layout, symptom_matcher=flaky_matcher,
            value_factory=lambda _name, index: f"{replay_origin}?attempt={index}",
        )
    assert result.successes == 3
    assert result.reproduced


async def test_parameter_values_are_fresh_and_require_a_factory(tmp_path: Path, replay_origin: str):
    layout = RunArtifactLayout(tmp_path / "runs", "values-run").initialize()
    finding = _finding("attempt-count:1")
    finding.steps = [Step(action="fill", locator="css=#missing", value="{{email}}")]
    async with BrowserSessionFactory(artifact_dir=layout.artifacts_dir) as factory:
        with pytest.raises(ValueError, match="value_factory"):
            await replay(finding, 1, target_url=replay_origin, browser_factory=factory, layout=layout)
