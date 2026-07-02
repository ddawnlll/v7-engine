"""Tests for the quick IC diagnostic script.

The tests use a tiny synthetic SimulationOutput CSV set that mimics the
structure produced by the Simulation engine. The data is deliberately
simple so that the expected Rank‑IC values can be calculated by hand.
"""
import pathlib
import pandas as pd
import numpy as np
import subprocess
import sys

# Helper to create a minimal CSV file with the required columns
def _write_csv(path: pathlib.Path, rows: list[dict]):
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)


def test_ic_diagnosis_runs(tmp_path: pathlib.Path):
    # Create two synthetic symbols with a few entries each
    sim_dir = tmp_path / "sim_output"
    sim_dir.mkdir()

    # Symbol A – monotonic positive net_R correlated with momentum_rank
    rows_a_template = {
        "ts": 0,
        "net_R": 0.0,
        "momentum_rank": 0,
        "trend_regime": 1,
        "vol_pct": 0.2,
        "rs_rank": 0,
        "btc_regime": 0,
        "pullback_atr": 0,
        "volume_zscore": 0,
        "spread_proxy": 0,
        "funding_context": 0,
    }
    for i in range(3):
        rows_a = []
        rows_a.append({**rows_a_template, "ts": i, "net_R": i * 0.5, "momentum_rank": i})
        rows_a.append({**rows_a_template, "ts": i + 10, "net_R": (i + 10) * 0.5, "momentum_rank": i + 10})
        _write_csv(sim_dir / f"symbolA_{i}.csv", rows_a)

    # Symbol B – random net_R (no correlation)
    rng = np.random.default_rng(42)
    rows_b = []
    for i in range(6):
        rows_b.append({
            "ts": i,
            "net_R": rng.normal(),
            "momentum_rank": rng.integers(0, 10),
            "trend_regime": rng.integers(0, 2),
            "vol_pct": rng.random(),
            "rs_rank": rng.integers(0, 10),
            "btc_regime": rng.integers(0, 2),
            "pullback_atr": rng.random(),
            "volume_zscore": rng.random(),
            "spread_proxy": rng.random(),
            "funding_context": rng.integers(0, 2),
        })
    _write_csv(sim_dir / "symbolB.csv", rows_b)

    # Run the diagnostic module as a subprocess
    # Run the diagnostic function directly (add repo root to PYTHONPATH)
    import importlib.util, sys, pathlib
    sys.path.append(str(pathlib.Path('.').resolve()))
    ic_mod = importlib.import_module('alphaforge.ic_diagnosis')
    # Capture stdout via context manager
    from io import StringIO
    import contextlib
    stdout = StringIO()
    with contextlib.redirect_stdout(stdout):
        ic_mod.run_diagnosis(str(sim_dir))
    output = stdout.getvalue()
    assert "Rank‑IC per fold" in output
