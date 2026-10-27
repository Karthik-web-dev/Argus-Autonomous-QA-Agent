from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Argus against the configured benchmark target")
    parser.add_argument("--url", default=os.getenv("ARGUS_BENCHMARK_URL"), required=os.getenv("ARGUS_BENCHMARK_URL") is None)
    parser.add_argument("--spec", default="Exercise the sample application's documented main journeys.")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/runs/latest"))
    args = parser.parse_args()
    command = [sys.executable, "-m", "argus.cli", "run", "--url", args.url,
               "--spec", args.spec, "--output", str(args.output)]
    subprocess.run(command, check=True)
    print(json.dumps({"output": str(args.output), "runs": str(args.output / "runs")}, indent=2))


if __name__ == "__main__":
    main()
