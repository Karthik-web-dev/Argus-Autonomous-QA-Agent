"""Render filed bug reports as a shareable HTML document and PDF.

The PDF is the artifact a team forwards: one page per bug with numbered steps,
expected vs actual, the reproduction count, and the screenshot taken at the
failing step, embedded so the file stands on its own.
"""

from __future__ import annotations

import asyncio
import base64
import html
from datetime import UTC, datetime
from pathlib import Path

from argus_contracts.models import BugReport

from argus.reporter.plain_language import (
    describe_step,
    human_title,
    infer_severity,
    is_unreadable_title,
)

_SEVERITY_COLORS = {"P0": "#b42318", "P1": "#c4320a", "P2": "#b54708", "P3": "#475467"}


_SEVERITY_LEGEND = (
    ("P0", "Critical", "A core task is completely broken (for example, customers cannot check out or sign in). Fix immediately."),
    ("P1", "High", "An important feature fails on a normal path, or data or privacy is at risk. Fix before the next release."),
    ("P2", "Medium", "Something fails in a less common case, or an accessibility problem. Schedule a fix soon."),
    ("P3", "Low", "A cosmetic or minor issue that does not stop anyone working. Fix when convenient."),
)


def _observed(report: BugReport) -> str:
    """What actually went wrong, even for reports that stored the journey outcome."""
    actual = report.actual or report.evidence.actual
    if actual.strip().rstrip(".") not in {"Journey completed", "Replay completed"}:
        return actual
    for event in report.evidence.network:
        if event.status is not None and event.status >= 400:
            endpoint = event.url.split("://", 1)[-1]
            return f"{event.method.upper()} {endpoint} returned HTTP {event.status}."
    for event in report.evidence.console:
        if event.level == "error":
            return event.message
    return actual


def _title(report: BugReport) -> str:
    """Readable title, also repairing reports filed before titles were humanized."""
    if is_unreadable_title(report.title):
        return human_title("", _observed(report), list(report.steps))
    return report.title


def _severity(report: BugReport) -> str:
    return infer_severity("", _observed(report)) or report.severity


def _failure_screenshot(report: BugReport) -> Path | None:
    """Prefer the screenshot of the failing step, else the last one captured."""
    evidence = report.evidence
    candidates: list[str] = []
    if evidence.failed_step_index is not None:
        candidates += [item.screenshot for item in evidence.step_evidence
                       if item.step_index == evidence.failed_step_index and item.screenshot]
    candidates += list(reversed(evidence.screenshots))
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def _image_tag(path: Path | None) -> str:
    if path is None:
        return '<p class="muted">No screenshot was captured for this step.</p>'
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<img src="data:image/png;base64,{data}" alt="Screenshot at the failing step">'


def build_report_html(reports: list[BugReport], *, target_url: str, run_id: str) -> str:
    esc = html.escape
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    # Merge reports describing the same problem (e.g. one missing image seen by
    # several tests), then put the most severe first.
    merged: dict[str, BugReport] = {}
    seen_in: dict[str, int] = {}
    for report in reports:
        key = _title(report).casefold()
        merged.setdefault(key, report)
        seen_in[key] = seen_in.get(key, 0) + 1
    reports = sorted(merged.values(), key=lambda r: _severity(r))
    counts = {level: sum(_severity(r) == level for r in reports) for level in ("P0", "P1", "P2", "P3")}
    rows = "".join(
        f'<tr><td><span class="sev" style="background:{_SEVERITY_COLORS[_severity(r)]}">{_severity(r)}</span></td>'
        f"<td>{esc(_title(r))}</td><td>{r.evidence.reproduction.successes}/{r.evidence.reproduction.attempts}</td></tr>"
        for r in reports
    ) or '<tr><td colspan="3" class="muted">No bug passed the Evidence Gate in this run.</td></tr>'

    legend = "".join(
        f'<tr><td><span class="sev" style="background:{_SEVERITY_COLORS[level]}">{level}</span></td>'
        f"<td><b>{name}</b></td><td>{esc(meaning)}</td></tr>"
        for level, name, meaning in _SEVERITY_LEGEND
    )
    sections = []
    for index, report in enumerate(reports, 1):
        evidence = report.evidence
        steps = "".join(f"<li>{esc(describe_step(step, target_url))}</li>" for step in report.steps)
        network = [event for event in evidence.network if event.status is not None and event.status >= 400]
        network_rows = "".join(
            f"<li><code>{esc(event.method)} {esc(event.url)}</code> → HTTP {event.status}</li>" for event in network[:5]
        )
        console = [event for event in evidence.console if event.level == "error"]
        console_rows = "".join(f"<li><code>{esc(event.message[:300])}</code></li>" for event in console[:5])
        reproduction = evidence.reproduction
        verified = ("Independently confirmed by the Red Team" if report.verified_by == "red_team"
                    else "Reproduced by the Evidence Gate (not yet independently reviewed)")
        sections.append(f"""
<section class="bug">
  <div class="bug-head">
    <span class="sev" style="background:{_SEVERITY_COLORS[_severity(report)]}">{_severity(report)}</span>
    <h2>{index}. {esc(_title(report))}</h2>
  </div>
  <p class="meta">{f"Seen in {seen_in[_title(report).casefold()]} separate tests · " if seen_in[_title(report).casefold()] > 1 else ""}Reproduced {reproduction.successes}/{reproduction.attempts}
     in fresh browser contexts · {esc(verified)}</p>
  <h3>Steps to reproduce</h3>
  <ol>{steps}</ol>
  <div class="grid">
    <div><h3>Expected</h3><p>{esc(report.expected or "—")}</p></div>
    <div><h3>Actual</h3><p>{esc(_observed(report) or "—")}</p></div>
  </div>
  {f"<h3>Failed requests</h3><ul>{network_rows}</ul>" if network_rows else ""}
  {f"<h3>Console errors</h3><ul>{console_rows}</ul>" if console_rows else ""}
  <h3>Screenshot</h3>
  {_image_tag(_failure_screenshot(report))}
  <p class="muted">Playwright repro: {esc(report.playwright_repro_path)}</p>
</section>""")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Argus bug report: {esc(target_url)}</title>
<style>
  @page {{ size: A4; margin: 16mm 14mm; }}
  body {{ font-family: "Segoe UI", system-ui, sans-serif; color: #1d2433; font-size: 11pt; line-height: 1.45; }}
  h1 {{ font-size: 20pt; margin: 0 0 4px; }} h2 {{ font-size: 14pt; margin: 0; }}
  h3 {{ font-size: 9pt; text-transform: uppercase; letter-spacing: .06em; color: #667085; margin: 14px 0 4px; }}
  .muted {{ color: #667085; }} .meta {{ color: #475467; font-size: 9.5pt; margin: 6px 0 0; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
  td, th {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #eaecf0; font-size: 10pt; }}
  th {{ color: #667085; font-weight: 600; }}
  .sev {{ display: inline-block; color: #fff; font-weight: 700; font-size: 9pt; padding: 2px 7px; border-radius: 4px; }}
  .summary {{ display: flex; gap: 10px; margin: 14px 0 4px; }}
  .summary div {{ border: 1px solid #eaecf0; border-radius: 6px; padding: 8px 12px; min-width: 70px; }}
  .summary b {{ display: block; font-size: 16pt; }}
  .bug {{ page-break-before: always; }}
  .legend td {{ vertical-align: top; }} .legend td:nth-child(2) {{ white-space: nowrap; }}
  .small {{ font-size: 9pt; }}
  .bug-head {{ display: flex; align-items: center; gap: 10px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .grid p {{ margin: 0; padding: 8px 10px; background: #f9fafb; border-radius: 6px; }}
  ol, ul {{ margin: 0; padding-left: 20px; }} li {{ margin: 2px 0; }}
  code {{ font-family: Consolas, monospace; font-size: 9pt; word-break: break-all; }}
  img {{ max-width: 100%; max-height: 120mm; border: 1px solid #eaecf0; border-radius: 6px; display: block; }}
</style></head><body>
<h1>Bug report</h1>
<p class="muted">Target: {esc(target_url)} · Run {esc(run_id)} · Generated {generated} by Argus</p>
<div class="summary">
  <div><b>{len(reports)}</b>bugs</div>
  {"".join(f'<div><b>{counts[level]}</b>{level}</div>' for level in counts)}
</div>
<table><thead><tr><th>Severity</th><th>Title</th><th>Reproduced</th></tr></thead><tbody>{rows}</tbody></table>
<h3>What the severity levels mean</h3>
<table class="legend"><tbody>{legend}</tbody></table>
<p class="muted small">"Reproduced 3/3" means Argus repeated the steps in 3 fresh browser sessions and saw the problem
each time, so it is not a one-off glitch.</p>
{"".join(sections)}
</body></html>"""


async def render_pdf(html_source: str, destination: Path) -> Path:
    from playwright.async_api import async_playwright

    destination.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html_source, wait_until="load")
            await page.pdf(path=str(destination), format="A4", print_background=True)
        finally:
            await browser.close()
    return destination


def write_report_documents(reports: list[BugReport], reports_dir: Path, *,
                           target_url: str, run_id: str) -> dict[str, Path]:
    """Write bug_report.html and bug_report.pdf; the PDF is best-effort."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    source = build_report_html(reports, target_url=target_url, run_id=run_id)
    html_path = reports_dir / "bug_report.html"
    html_path.write_text(source, encoding="utf-8")
    written = {"html": html_path}
    written["pdf"] = asyncio.run(render_pdf(source, reports_dir / "bug_report.pdf"))
    return written
