# Benchmark protocol

The benchmark tracks seeded bugs independently from agent findings. `benchmarks/manifest.json` is the source of truth for bug IDs, expected signals, affected journeys, and severity. Keep expected labels out of the agent prompt and runtime inputs.

Record each run as JSON under `benchmarks/runs/`, then score precision, recall, F1, reproducibility, and generated-test pass rate with `benchmarks/scripts/score.py`. A bug counts as found only when a reported finding maps to its manifest ID and passes the configured evidence gate. Do not report benchmark figures until runs have been reviewed against ground truth.

The starter manifest contains 25 reserved entries; replace each placeholder with a verified planted defect before using it to claim coverage.
