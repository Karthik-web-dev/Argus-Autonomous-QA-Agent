from __future__ import annotations

import argparse
import json
from pathlib import Path


def score(manifest: dict, run: dict) -> dict[str, float | int]:
    expected = {bug["id"] for bug in manifest["bugs"] if bug.get("verified", False)}
    reported = {finding.get("bug_id") for finding in run.get("findings", []) if finding.get("bug_id")}
    true_positive = len(expected & reported)
    false_positive = len(reported - expected)
    false_negative = len(expected - reported)
    precision = true_positive / len(reported) if reported else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"true_positive": true_positive, "false_positive": false_positive,
            "false_negative": false_negative, "precision": precision, "recall": recall, "f1": f1}


def main() -> None:
    parser = argparse.ArgumentParser(description="Score an Argus benchmark run against verified ground truth")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).parents[1] / "manifest.json")
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    result = score(json.loads(args.manifest.read_text()), json.loads(args.run.read_text()))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
