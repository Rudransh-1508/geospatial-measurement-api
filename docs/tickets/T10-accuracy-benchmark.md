# T10 - Accuracy benchmark

**ADRs:** 0003

## Scope
- `scripts/benchmark_accuracy.py` comparing Web Mercator, UTM, local LAEA/AEQD and geodesic across latitudes and feature sizes.
- Writes `docs/accuracy.md` with a table and a chart (`docs/accuracy.png`).

## Acceptance
- Report regenerates deterministically from the script.
