"""Shared fixtures for AlphaForge dataset tests.

Provides deterministic DataFrames, specs, and a sample assembled dataset
for use across assembler, lineage, writer, and integration tests.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import pytest

# Ensure alphaforge/src is on the Python path so "from alphaforge.dataset..."
# resolves correctly under the src/ layout pattern.
# Remove any stale import first to prevent namespace-package shadowing.
_src = Path(__file__).resolve().parent.parent / "src"
_src_str = str(_src)

if "alphaforge" in sys.modules:
    del sys.modules["alphaforge"]

# Remove any existing entries for this path so we can place it at front
while _src_str in sys.path:
    sys.path.remove(_src_str)

sys.path.insert(0, _src_str)

from alphaforge.dataset.assembler import DefaultAssembler
from alphaforge.dataset.contracts import (
    JoinAuditTrail,
    LabeledDataset,
    LineageProvenance,
)
from alphaforge.dataset.lineage import LineageTracker
from alphaforge.dataset.writer import DefaultWriter

# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

BASE_TS = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def ts(offset_hours: int) -> str:
    """Return ISO 8601 timestamp offset from BASE_TS by hours."""
    return (BASE_TS + timedelta(hours=offset_hours)).isoformat()


# ---------------------------------------------------------------------------
# Sample feature DataFrame (20 rows, 3 symbols, SWING mode)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_feature_df() -> pd.DataFrame:
    """20-row feature DataFrame with 3 symbols and SWING-mode features.

    Symbols: BTCUSDT, ETHUSDT, SOLUSDT
    Timestamps: T-5 to T-1 (features always before labels for purge safety)
    """
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    rows: List[Dict[str, Any]] = []

    for i in range(20):
        sym = symbols[i % 3]
        t = i // 3  # 0,0,0,1,1,1,...
        rows.append({
            "symbol": sym,
            "timestamp": ts(-10 + t),  # T-10 to T-4 (features)
            "feature_set_id": "swing_v1_features",
            "log_return_4h": 0.001 * (i + 1),
            "rsi_4h": 50.0 + i * 2.0,
            "atr_pct_4h": 0.005 + i * 0.001,
            "volume_ratio_4h": 1.0 + i * 0.05,
            "momentum_4h": -0.01 + i * 0.005,
            "volatility_4h": 0.02 + i * 0.002,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sample label DataFrame (20 rows, 3 symbols, mixed validity)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_label_df() -> pd.DataFrame:
    """20-row label DataFrame with mixed label_validity.

    14 VALID, 3 INVALID, 2 AMBIGUOUS, 1 empty-string validity.
    Timestamps: T-5 to T+1 (labels may overlap feature timestamps).
    """
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    rows: List[Dict[str, Any]] = []

    for i in range(20):
        sym = symbols[i % 3]
        t = i // 3  # 0,0,0,1,1,1,...

        # Determine validity
        if i < 4:
            validity = "VALID"
        elif i < 7:
            validity = "INVALID"
        elif i < 9:
            validity = "AMBIGUOUS"
        elif i == 9:
            validity = ""  # empty string (not VALID)
        else:
            validity = "VALID"

        label_checksum = _compute_row_checksum(i, sym, validity)

        rows.append({
            "symbol": sym,
            "timestamp": ts(-5 + t),  # T-5 to T+1 (labels)
            "label_dataset_id": "swing_v1_labels",
            "label_checksum": label_checksum,
            "best_action_label": (
                "LONG_NOW" if i % 3 == 0 else "SHORT_NOW" if i % 3 == 1 else "NO_TRADE"
            ),
            "label_validity": validity,
            "long_R_net": 0.5 + i * 0.05,
            "short_R_net": -0.2 - i * 0.03,
            "no_trade_quality": (
                "CORRECT_NO_TRADE" if i % 4 == 0 else "SAVED_LOSS" if i % 4 == 1 else "MISSED_OPPORTUNITY"
            ),
            "cost_impact_long": 0.01 + i * 0.001,
            "cost_impact_short": 0.01 + i * 0.001,
        })

    return pd.DataFrame(rows)


def _compute_row_checksum(i: int, sym: str, validity: str) -> str:
    """Deterministic checksum for a label row."""
    data = {
        "index": i,
        "symbol": sym,
        "validity": validity,
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Feature and label specs
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_feature_spec() -> Dict[str, Any]:
    """SWING-mode FeatureSetSpec for testing."""
    return {
        "feature_set_id": "swing_v1_features",
        "mode": "SWING",
        "timeframe_stack": {"primary": "4h", "context": "1d", "refinement": "1h"},
        "feature_groups": ["returns", "momentum", "volatility", "atr", "volume"],
        "leakage_policy": {
            "purge_window_bars": 4,
            "embargo_policy": "strict_causal",
        },
        "source_dataset_refs": ["norm_btcusdt_4h", "norm_ethusdt_4h", "norm_solusdt_4h"],
    }


@pytest.fixture
def sample_label_spec() -> Dict[str, Any]:
    """SWING-mode LabelDatasetSpec for testing."""
    return {
        "label_dataset_id": "swing_v1_labels",
        "mode": "SWING",
        "simulation_profile_id": "swing_baseline_v1",
        "label_source": "simulation_output",
        "label_fields": [
            "long_R_net", "short_R_net", "best_action_label",
            "label_validity", "no_trade_quality", "cost_impact_long",
            "cost_impact_short",
        ],
        "cost_model_ref": "cost_model_v1",
        "funding_status": "DEFERRED",
    }


# ---------------------------------------------------------------------------
# Sample manifest ID
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_manifest_id() -> str:
    return "manifest_swing_v1_run_001"


# ---------------------------------------------------------------------------
# Sample assembled dataset (for writer tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_assembled_dataset(
    sample_feature_df: pd.DataFrame,
    sample_label_df: pd.DataFrame,
    sample_feature_spec: Dict[str, Any],
    sample_label_spec: Dict[str, Any],
    sample_manifest_id: str,
) -> List[LabeledDataset]:
    """Pre-assembled dataset for writer/integration tests."""
    assembler = DefaultAssembler()
    dataset, _ = assembler.assemble(
        feature_df=sample_feature_df,
        label_df=sample_label_df,
        feature_spec=sample_feature_spec,
        label_spec=sample_label_spec,
        manifest_id=sample_manifest_id,
    )
    return dataset


# ---------------------------------------------------------------------------
# Scoped fixtures: blank DataFrames
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_feature_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["symbol", "timestamp", "feature_set_id"])


@pytest.fixture
def empty_label_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["symbol", "timestamp", "label_validity", "label_dataset_id"])


# ---------------------------------------------------------------------------
# Assembler instance
# ---------------------------------------------------------------------------


@pytest.fixture
def assembler() -> DefaultAssembler:
    return DefaultAssembler()


@pytest.fixture
def writer() -> DefaultWriter:
    return DefaultWriter()


# ---------------------------------------------------------------------------
# Lineage tracker instance
# ---------------------------------------------------------------------------


@pytest.fixture
def tracker() -> LineageTracker:
    return LineageTracker()


# ============================================================================
# Validation fixtures (WS-06: walk-forward validation tests)
# ============================================================================

from dataclasses import dataclass


@dataclass
class _ValidationRow:
    """Minimal row for validation tests — only feature_timestamp and symbol.

    WalkForwardValidator only accesses these two fields during split().
    The full LabeledDataset is not needed for structural fold testing.
    """

    feature_timestamp: str
    symbol: str = "BTCUSDT"


def _make_chrono_dataset(
    n_bars: int,
    rows_per_bar: int = 1,
    symbols: tuple = ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
    base_hour: int = 0,
) -> list:
    """Build a chronologically sorted dataset of _ValidationRow objects.

    Every bar has exactly rows_per_bar rows (one per symbol, cycling).
    Produces n_bars * rows_per_bar total rows with n_bars distinct timestamps.

    Timestamps are ISO 8601 strings produced by adding hours to a base datetime.
    This ensures proper chronological sorting even with large bar counts.

    Args:
        n_bars: Number of distinct timestamps (bars).
        rows_per_bar: Number of rows per bar (cycles through symbols).
        symbols: Symbols to cycle through at each bar.
        base_hour: Starting hour offset for timestamps.
    """
    from datetime import datetime, timedelta, timezone as _tz

    base = datetime(2025, 1, 1, tzinfo=_tz.utc)
    rows: list = []
    for bar_idx in range(n_bars):
        for row_i in range(rows_per_bar):
            sym = symbols[row_i % len(symbols)]
            dt = base + timedelta(hours=base_hour + bar_idx)
            ts = dt.isoformat()
            rows.append(_ValidationRow(feature_timestamp=ts, symbol=sym))
    return rows


@pytest.fixture
def chrono_dataset() -> list:
    """Chronologically sorted dataset for SWING tests: 1200 bars, 3 symbols.

    1200 bars * 3 rows/bar = 3600 rows.
    Enough bars to produce 6+ folds with test window configs.
    """
    return _make_chrono_dataset(n_bars=1200, rows_per_bar=3)


@pytest.fixture
def unsorted_dataset(chrono_dataset: list) -> list:
    """Same data as chrono_dataset but shuffled — should fail validation."""
    import random as _random
    ds = list(chrono_dataset)
    _random.seed(42)
    _random.shuffle(ds)
    return ds


@pytest.fixture
def short_dataset() -> list:
    """30 bars, 1 row/bar — too few bars for 6 SWING folds."""
    return _make_chrono_dataset(n_bars=30, rows_per_bar=1)


@pytest.fixture
def leaky_dataset() -> list:
    """100 bars, 1 row/bar — for purge/embargo testing."""
    return _make_chrono_dataset(n_bars=100, rows_per_bar=1)


@pytest.fixture
def chrono_dataset_scalp() -> list:
    """Dataset large enough for SCALP mode tests.

    SCALP needs at least train_window + test_window + 5*(test_window+purge) bars.
    With 4000/800/100 windows: 4000+800+5*(800+100) = 9300 bars needed.
    We provide 12000 bars.
    """
    return _make_chrono_dataset(n_bars=12000, rows_per_bar=1)


@pytest.fixture
def chrono_dataset_aggressive_scalp() -> list:
    """Dataset large enough for AGGRESSIVE_SCALP mode tests.

    With 4000/800/200: 4000+800+5*(800+200) = 9800 bars needed.
    We provide 13000 bars.
    """
    return _make_chrono_dataset(n_bars=13000, rows_per_bar=1)


@pytest.fixture
def insufficient_dataset_scalp() -> list:
    """Dataset insufficient for SCALP — only 5000 bars."""
    return _make_chrono_dataset(n_bars=5000, rows_per_bar=1)


@pytest.fixture
def insufficient_dataset_aggressive_scalp() -> list:
    """Dataset insufficient for AGGRESSIVE_SCALP — only 6000 bars."""
    return _make_chrono_dataset(n_bars=6000, rows_per_bar=1)


@pytest.fixture
def insufficient_dataset_swing() -> list:
    """Dataset insufficient for SWING — only 200 bars.

    SWING anchored with 2000/500: 2000+500+5*(500+20) = 5100 bars minimum.
    200 bars is far below.
    """
    return _make_chrono_dataset(n_bars=200, rows_per_bar=1)


@pytest.fixture
def embargo_violation_dataset() -> list:
    """Dataset with only 50 bars — too tight for proper separation."""
    return _make_chrono_dataset(n_bars=50, rows_per_bar=3)
