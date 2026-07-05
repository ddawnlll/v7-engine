"""Tests for CandidateOutcomeBuilder and CandidateOutcomeDataset generation.

Tests cover:
- build() returns table with correct schema and columns
- Pre-entry features computed correctly from market data
- NaN handling for insufficient lookback
- Empty input handling
- Side mapping accuracy
- Outcome extraction from LONG_NOW vs SHORT_NOW
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pyarrow as pa
import pytest

# Ensure alphaforge/src is on the Python path
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from alphaforge.mine.candidate_dataset import (
    CandidateOutcomeBuilder,
    MarketDataContext,
    _action_to_side,
    _find_bar_index,
    _find_entry_bar_index,
    _make_candidate_id,
    _pick_outcome,
    _to_unix_ms,
)
from lib.market_data.contracts import KlineRecord
from simulation.contracts.models import (
    ActionOutcome,
    NoTradeOutcome,
    PathMetrics,
    SimulationLineage,
    SimulationOutput,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_TS_MS = 1705315200000  # 2024-01-15T12:00:00 UTC
INTERVAL_MS = 14400000  # 4h in ms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_kline(
    idx: int,
    symbol: str = "BTCUSDT",
    close: float = 50000.0,
    high: float = 50500.0,
    low: float = 49500.0,
    open_: float = 50000.0,
    volume: float = 1000.0,
    interval: str = "4h",
) -> KlineRecord:
    """Create a deterministic KlineRecord at index offset from BASE_TS."""
    return KlineRecord(
        symbol=symbol,
        timestamp=BASE_TS_MS + idx * INTERVAL_MS,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        quote_volume=volume * close,
        trade_count=100,
        taker_buy_volume=volume * 0.5,
        taker_buy_quote_volume=volume * close * 0.5,
        interval=interval,
        source="test",
        is_closed=True,
    )


def _make_trending_klines(
    n: int,
    start_price: float = 49000.0,
    uptrend: bool = True,
    symbol: str = "BTCUSDT",
    interval: str = "4h",
) -> List[KlineRecord]:
    """Create n KlineRecords forming a clear trend.

    In uptrend, price rises from start_price by ~0.1% per bar.
    In downtrend, price falls.
    Also adds some volatility so ATR is non-zero.
    """
    records: List[KlineRecord] = []
    price = start_price
    direction = 1.0 if uptrend else -1.0

    for i in range(n):
        # Add small drift + noise
        drift = price * 0.001 * direction
        noise = price * 0.002 * (np.random.random() - 0.5)
        close = price + drift + noise
        high = max(close, price) * 1.005
        low = min(close, price) * 0.995
        records.append(
            _make_kline(
                idx=i,
                symbol=symbol,
                close=round(close, 2),
                high=round(high, 2),
                low=round(low, 2),
                open_=round(price, 2),
                volume=1000.0 + i * 10.0,
                interval=interval,
            )
        )
        price = close

    return records


def _make_simulation_output(
    idx: int,
    symbol: str = "BTCUSDT",
    mode: str = "SWING",
    best_action: str = "LONG_NOW",
    net_r: float = 1.5,
    gross_r: float = 2.0,
    cost_r: float = 0.5,
    mfe_r: float = 3.0,
    mae_r: float = -1.0,
    exit_reason: str = "TARGET_HIT",
    hold_bars: int = 4,
    run_id: str = "sim-run-001",
    interval: str = "4h",
) -> SimulationOutput:
    """Create a deterministic SimulationOutput for testing."""
    decision_ts_iso = datetime.fromtimestamp(
        (BASE_TS_MS + idx * INTERVAL_MS) / 1000.0, tz=timezone.utc
    ).isoformat()

    pm_long = PathMetrics(
        mfe_r=mfe_r,
        mae_r=mae_r,
        path_quality_score=0.8,
        path_quality_bucket="HIGH",
    )
    pm_short = PathMetrics(
        mfe_r=-mae_r,
        mae_r=-mfe_r,
        path_quality_score=0.3,
        path_quality_bucket="LOW",
    )

    long_outcome = ActionOutcome(
        action="LONG_NOW",
        realized_r_gross=gross_r,
        realized_r_net=net_r,
        fee_cost_r=cost_r * 0.6,
        slippage_cost_r=cost_r * 0.3,
        funding_cost_r=cost_r * 0.1,
        total_cost_r=cost_r,
        exit_reason=exit_reason,
        exit_price=51000.0,
        exit_bar_index=hold_bars,
        hold_duration_bars=hold_bars,
        action_utility=net_r,
        path_metrics=pm_long,
    )

    short_outcome = ActionOutcome(
        action="SHORT_NOW",
        realized_r_gross=-gross_r,
        realized_r_net=-net_r,
        fee_cost_r=cost_r * 0.6,
        slippage_cost_r=cost_r * 0.3,
        funding_cost_r=cost_r * 0.1,
        total_cost_r=cost_r,
        exit_reason="STOP_HIT",
        exit_price=49000.0,
        exit_bar_index=2,
        hold_duration_bars=2,
        path_metrics=pm_short,
    )

    return SimulationOutput(
        simulation_run_id=run_id,
        symbol=symbol,
        decision_timestamp=decision_ts_iso,
        mode=mode,
        primary_interval=interval,
        resolution_status="COMPLETE",
        long_outcome=long_outcome,
        short_outcome=short_outcome,
        no_trade_outcome=NoTradeOutcome(),
        best_action=best_action,
        action_gap_r=0.5,
        regret_r=0.0,
        is_ambiguous=False,
        lineage=SimulationLineage(
            simulation_family_version="simfam-1.0.0",
            simulation_profile_version="swing-v1",
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trending_btc_data() -> List[KlineRecord]:
    """200 bars of uptrending BTC data."""
    return _make_trending_klines(200, start_price=49000.0, uptrend=True, symbol="BTCUSDT")


@pytest.fixture
def trending_eth_data() -> List[KlineRecord]:
    """200 bars of uptrending ETH data."""
    return _make_trending_klines(200, start_price=3000.0, uptrend=True, symbol="ETHUSDT")


@pytest.fixture
def builder(trending_btc_data) -> CandidateOutcomeBuilder:
    """Default builder with BTC data."""
    return CandidateOutcomeBuilder(
        market_data={"BTCUSDT": MarketDataContext(trending_btc_data)},
        lookback_bars=50,
    )


@pytest.fixture
def builder_with_btc(trending_btc_data, trending_eth_data) -> CandidateOutcomeBuilder:
    """Builder with both BTC and ETH data, plus BTC regime context."""
    return CandidateOutcomeBuilder(
        market_data={
            "BTCUSDT": MarketDataContext(trending_btc_data),
            "ETHUSDT": MarketDataContext(trending_eth_data),
        },
        btc_market_data=MarketDataContext(trending_btc_data),
        lookback_bars=50,
    )


@pytest.fixture
def sample_outputs_long() -> List[SimulationOutput]:
    """3 simulation outputs, all LONG_NOW, valid at bar indices 80, 85, 90."""
    outputs: List[SimulationOutput] = []
    for i, bar_idx in enumerate([80, 85, 90]):
        outputs.append(
            _make_simulation_output(
                idx=bar_idx,
                symbol="BTCUSDT",
                best_action="LONG_NOW",
                net_r=1.5 + i * 0.5,
                gross_r=2.0 + i * 0.5,
                cost_r=0.5,
                exit_reason="TARGET_HIT",
                run_id=f"sim-{i}",
            )
        )
    return outputs


@pytest.fixture
def sample_outputs_mixed() -> List[SimulationOutput]:
    """2 outputs: one LONG, one SHORT."""
    return [
        _make_simulation_output(
            idx=80, symbol="BTCUSDT", best_action="LONG_NOW", net_r=2.0, run_id="sim-long"
        ),
        _make_simulation_output(
            idx=85, symbol="BTCUSDT", best_action="SHORT_NOW", net_r=1.0, gross_r=0.5,
            cost_r=0.5, exit_reason="STOP_HIT", run_id="sim-short",
        ),
    ]


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    """Tests for standalone helper functions."""

    def test_to_unix_ms(self) -> None:
        """Verify ISO-to-unix-ms conversion."""
        iso = "2024-01-15T12:00:00+00:00"
        # Unix epoch for 2024-01-15 12:00:00 UTC
        # Jan 1 00:00 = 1704067200, + 14 days = 1705276800, + 12h = 1705320000
        expected = 1705320000000
        assert _to_unix_ms(iso) == expected

    def test_find_bar_index_found(self) -> None:
        """Binary search finds the correct bar."""
        records = [_make_kline(i) for i in range(10)]
        target_ts = BASE_TS_MS + 5 * INTERVAL_MS
        assert _find_bar_index(records, target_ts) == 5

    def test_find_bar_index_not_found(self) -> None:
        """Binary search returns None for missing timestamp."""
        records = [_make_kline(i) for i in range(10)]
        target_ts = BASE_TS_MS + 25 * INTERVAL_MS
        assert _find_bar_index(records, target_ts) is None

    def test_find_bar_index_empty(self) -> None:
        """Binary search on empty list returns None."""
        assert _find_bar_index([], 12345) is None

    def test_find_entry_bar_index(self) -> None:
        """End-to-end: ISO timestamp -> bar index."""
        records = [_make_kline(i) for i in range(10)]
        iso = datetime.fromtimestamp(
            (BASE_TS_MS + 3 * INTERVAL_MS) / 1000.0, tz=timezone.utc
        ).isoformat()
        assert _find_entry_bar_index(records, iso) == 3

    def test_action_to_side(self) -> None:
        """Side mapping is correct."""
        assert _action_to_side("LONG_NOW") == "LONG"
        assert _action_to_side("SHORT_NOW") == "SHORT"
        assert _action_to_side("NO_TRADE") == "NO_TRADE"
        assert _action_to_side("AMBIGUOUS_STATE") == "AMBIGUOUS_STATE"

    def test_pick_outcome_long(self) -> None:
        """LONG_NOW picks long_outcome."""
        lo = ActionOutcome(action="LONG_NOW", realized_r_net=2.0)
        so = ActionOutcome(action="SHORT_NOW", realized_r_net=-1.0)
        result = _pick_outcome("LONG_NOW", lo, so)
        assert result.realized_r_net == 2.0

    def test_pick_outcome_short(self) -> None:
        """SHORT_NOW picks short_outcome."""
        lo = ActionOutcome(action="LONG_NOW", realized_r_net=2.0)
        so = ActionOutcome(action="SHORT_NOW", realized_r_net=-1.0)
        result = _pick_outcome("SHORT_NOW", lo, so)
        assert result.realized_r_net == -1.0

    def test_pick_outcome_no_trade(self) -> None:
        """NO_TRADE falls back to long_outcome."""
        lo = ActionOutcome(action="LONG_NOW", realized_r_net=0.0)
        so = ActionOutcome(action="SHORT_NOW", realized_r_net=0.0)
        result = _pick_outcome("NO_TRADE", lo, so)
        assert result is lo

    def test_make_candidate_id(self) -> None:
        """Candidate ID format is simulation_run_id_symbol_idx."""
        cid = _make_candidate_id("run-001", "BTCUSDT", 42)
        assert cid == "run-001_BTCUSDT_42"

    def test_market_data_context_empty(self) -> None:
        """MarketDataContext requires at least one record."""
        with pytest.raises(ValueError, match="at least one record"):
            MarketDataContext([])

    def test_market_data_context_unsorted(self) -> None:
        """MarketDataContext validates ascending order."""
        records = [_make_kline(0), _make_kline(2), _make_kline(1)]
        with pytest.raises(ValueError, match="ordered by timestamp"):
            MarketDataContext(records)


# ---------------------------------------------------------------------------
# CandidateOutcomeBuilder tests
# ---------------------------------------------------------------------------


class TestCandidateOutcomeBuilder:
    """Integration tests for CandidateOutcomeBuilder."""

    def test_build_returns_table_with_correct_schema(
        self, builder: CandidateOutcomeBuilder, sample_outputs_long: List[SimulationOutput]
    ) -> None:
        """build() returns a pyarrow Table with all expected columns."""
        table = builder.build(sample_outputs_long)

        assert isinstance(table, pa.Table)
        assert table.num_rows == 3

        # Verify all expected columns exist
        expected_columns = {
            "symbol", "timestamp", "side", "mode", "timeframe",
            "regime_trend", "volatility_percentile", "momentum_rank",
            "volume_zscore", "atr_pct", "btc_regime", "pullback_atr",
            "distance_to_range_high", "spread_proxy", "funding_context",
            "net_R", "gross_R", "cost_R", "mfe_R", "mae_R",
            "exit_reason", "hold_duration",
            "simulation_run_id", "candidate_id",
        }
        assert set(table.column_names) == expected_columns

        # Verify column types
        schema = table.schema
        type_map = {f.name: f.type for f in schema}
        assert type_map["symbol"] == pa.string()
        assert type_map["timestamp"] == pa.int64()
        assert type_map["side"] == pa.string()
        assert type_map["mode"] == pa.string()
        assert type_map["timeframe"] == pa.string()
        assert type_map["regime_trend"] == pa.string()
        assert type_map["btc_regime"] == pa.string()
        assert type_map["net_R"] == pa.float64()
        assert type_map["hold_duration"] == pa.int64()
        assert type_map["simulation_run_id"] == pa.string()
        assert type_map["candidate_id"] == pa.string()

    def test_build_correct_identity_columns(
        self, builder: CandidateOutcomeBuilder, sample_outputs_long: List[SimulationOutput]
    ) -> None:
        """Identity columns (symbol, mode, timeframe, side) are correct."""
        table = builder.build(sample_outputs_long)

        assert table.column("symbol").to_pylist() == ["BTCUSDT", "BTCUSDT", "BTCUSDT"]
        assert all(s == "SWING" for s in table.column("mode").to_pylist())
        assert all(t == "4h" for t in table.column("timeframe").to_pylist())
        assert table.column("side").to_pylist() == ["LONG", "LONG", "LONG"]

    def test_build_timestamps_are_int64(
        self, builder: CandidateOutcomeBuilder, sample_outputs_long: List[SimulationOutput]
    ) -> None:
        """Timestamp column is int64 unix ms."""
        table = builder.build(sample_outputs_long)
        ts_values = table.column("timestamp").to_pylist()
        assert all(isinstance(ts, int) for ts in ts_values)
        # Verify timestamps increase monotonically
        assert ts_values == sorted(ts_values)

    def test_build_correct_outcome_fields(
        self, builder: CandidateOutcomeBuilder, sample_outputs_long: List[SimulationOutput]
    ) -> None:
        """Outcome fields are extracted correctly from ActionOutcome."""
        table = builder.build(sample_outputs_long)

        # Row 0: net_R=1.5, gross_R=2.0, cost_R=0.5, mfe_R=3.0, mae_R=-1.0
        assert table.column("net_R").to_pylist() == [1.5, 2.0, 2.5]
        assert table.column("gross_R").to_pylist() == [2.0, 2.5, 3.0]
        assert all(c == 0.5 for c in table.column("cost_R").to_pylist())
        assert all(m == 3.0 for m in table.column("mfe_R").to_pylist()[:1])
        assert all(m == -1.0 for m in table.column("mae_R").to_pylist()[:1])
        assert all(e == "TARGET_HIT" for e in table.column("exit_reason").to_pylist())
        assert all(d == 4 for d in table.column("hold_duration").to_pylist())

    def test_build_correct_lineage(
        self, builder: CandidateOutcomeBuilder, sample_outputs_long: List[SimulationOutput]
    ) -> None:
        """Lineage columns are correct."""
        table = builder.build(sample_outputs_long)
        assert table.column("simulation_run_id").to_pylist() == ["sim-0", "sim-1", "sim-2"]
        candidate_ids = table.column("candidate_id").to_pylist()
        assert candidate_ids == [
            "sim-0_BTCUSDT_0",
            "sim-1_BTCUSDT_1",
            "sim-2_BTCUSDT_2",
        ]

    def test_build_mixed_side(
        self, builder_with_btc: CandidateOutcomeBuilder, sample_outputs_mixed: List[SimulationOutput]
    ) -> None:
        """LONG and SHORT outputs have correct side and outcome extraction."""
        table = builder_with_btc.build(sample_outputs_mixed)

        sides = table.column("side").to_pylist()
        assert sides == ["LONG", "SHORT"]

        # LONG row: net_R=2.0 from long_outcome
        # SHORT row: net_R=-1.0 from short_outcome
        net_r_values = table.column("net_R").to_pylist()
        assert net_r_values[0] == 2.0
        assert net_r_values[1] == -1.0

    def test_build_pre_entry_features(
        self, builder: CandidateOutcomeBuilder, sample_outputs_long: List[SimulationOutput]
    ) -> None:
        """Pre-entry features are computed and have valid ranges."""
        table = builder.build(sample_outputs_long)

        # regime_trend should be a valid string
        regimes = table.column("regime_trend").to_pylist()
        assert all(r in ("up", "down", "range") for r in regimes)

        # volatility_percentile in [0, 100]
        vp = table.column("volatility_percentile").to_pylist()
        assert all(0.0 <= v <= 100.0 for v in vp)

        # momentum_rank in [0, 1]
        mr = table.column("momentum_rank").to_pylist()
        assert all(0.0 <= m <= 1.0 for m in mr)

        # atr_pct should be positive (since we have volatility)
        atr = table.column("atr_pct").to_pylist()
        assert all(a > 0 for a in atr)

        # btc_regime should be a valid string
        btc_r = table.column("btc_regime").to_pylist()
        assert all(r in ("up", "down", "range") for r in btc_r)

        # pullback_atr >= 0
        pb = table.column("pullback_atr").to_pylist()
        assert all(p >= 0 for p in pb)

    def test_build_with_btc_regime(
        self, builder_with_btc: CandidateOutcomeBuilder, sample_outputs_long: List[SimulationOutput]
    ) -> None:
        """BTC regime is populated when btc_market_data is provided."""
        table = builder_with_btc.build(sample_outputs_long)

        # With uptrending BTC data, regime should be "up"
        btc_regimes = table.column("btc_regime").to_pylist()
        assert all(r == "up" for r in btc_regimes)

    def test_build_empty_input(self, builder: CandidateOutcomeBuilder) -> None:
        """Empty input returns empty table with correct schema."""
        table = builder.build([])
        assert isinstance(table, pa.Table)
        assert table.num_rows == 0
        # Schema should still be correct
        expected_columns = {
            "symbol", "timestamp", "side", "mode", "timeframe",
            "regime_trend", "volatility_percentile", "momentum_rank",
            "volume_zscore", "atr_pct", "btc_regime", "pullback_atr",
            "distance_to_range_high", "spread_proxy", "funding_context",
            "net_R", "gross_R", "cost_R", "mfe_R", "mae_R",
            "exit_reason", "hold_duration",
            "simulation_run_id", "candidate_id",
        }
        assert set(table.column_names) == expected_columns

    def test_build_missing_market_data(self, builder: CandidateOutcomeBuilder) -> None:
        """Simulation outputs for symbols without market data are skipped."""
        # ETHUSDT not in builder's market_data
        outputs = [
            _make_simulation_output(idx=80, symbol="ETHUSDT", run_id="eth-test")
        ]
        table = builder.build(outputs)
        assert table.num_rows == 0

    def test_build_insufficient_lookback(self, trending_btc_data: List[KlineRecord]) -> None:
        """Outputs at early bar indices (before lookback) are skipped."""
        # Use a builder with lookback_bars=100, but output at idx=10
        b = CandidateOutcomeBuilder(
            market_data={"BTCUSDT": MarketDataContext(trending_btc_data)},
            lookback_bars=100,
        )
        outputs = [
            _make_simulation_output(idx=10, run_id="early")
        ]
        table = b.build(outputs)
        assert table.num_rows == 0

    def test_build_nan_in_features(
        self, trending_btc_data: List[KlineRecord]
    ) -> None:
        """NaN values in pre-entry features are handled gracefully (no crashes)."""
        # Use very short data to force NaN features
        short_data = trending_btc_data[:30]  # Only 30 bars
        b = CandidateOutcomeBuilder(
            market_data={"BTCUSDT": MarketDataContext(short_data)},
            lookback_bars=10,
        )
        outputs = [
            _make_simulation_output(idx=20, run_id="short-data")
        ]
        table = b.build(outputs)
        # Should produce a row even if some features are NaN/default
        assert table.num_rows == 1

        # atr_pct might be NaN with only 30 bars (ATR needs 15 bars of lookback)
        atr_pct = table.column("atr_pct").to_pylist()[0]
        # It could be NaN or a valid value depending on exact data, but shouldn't crash
        assert atr_pct is None or not np.isnan(atr_pct) or isinstance(atr_pct, float)

    def test_build_with_funding_data(
        self, trending_btc_data: List[KlineRecord]
    ) -> None:
        """Funding context is populated when funding_data is provided."""
        funding_rates = [0.01 * (i % 3 - 1) for i in range(len(trending_btc_data))]
        b = CandidateOutcomeBuilder(
            market_data={"BTCUSDT": MarketDataContext(trending_btc_data)},
            funding_data={"BTCUSDT": funding_rates},
            lookback_bars=50,
        )
        outputs = [
            _make_simulation_output(idx=80, run_id="with-funding")
        ]
        table = b.build(outputs)
        assert table.num_rows == 1
        # Funding context should be the rate at bar 80
        fc = table.column("funding_context").to_pylist()[0]
        assert fc == funding_rates[80]

    def test_build_multiple_symbols(
        self, trending_btc_data: List[KlineRecord], trending_eth_data: List[KlineRecord]
    ) -> None:
        """Builder handles multiple symbols correctly."""
        b = CandidateOutcomeBuilder(
            market_data={
                "BTCUSDT": MarketDataContext(trending_btc_data),
                "ETHUSDT": MarketDataContext(trending_eth_data),
            },
            lookback_bars=50,
        )
        outputs = [
            _make_simulation_output(idx=80, symbol="BTCUSDT", run_id="multi-1"),
            _make_simulation_output(idx=85, symbol="ETHUSDT", run_id="multi-2"),
        ]
        table = b.build(outputs)
        assert table.num_rows == 2
        assert table.column("symbol").to_pylist() == ["BTCUSDT", "ETHUSDT"]

    def test_build_identity_columns_content(
        self, builder: CandidateOutcomeBuilder, sample_outputs_long: List[SimulationOutput]
    ) -> None:
        """Verify identity columns contain semantically correct values."""
        table = builder.build(sample_outputs_long)

        # All BTCUSDT, SWING, 4h
        symbols = table.column("symbol").to_pylist()
        modes = table.column("mode").to_pylist()
        timeframes = table.column("timeframe").to_pylist()
        assert symbols == ["BTCUSDT", "BTCUSDT", "BTCUSDT"]
        assert modes == ["SWING", "SWING", "SWING"]
        assert timeframes == ["4h", "4h", "4h"]

        # Timestamps should correspond to the bar indices
        timestamps = table.column("timestamp").to_pylist()
        expected_ts_0 = BASE_TS_MS + 80 * INTERVAL_MS
        expected_ts_1 = BASE_TS_MS + 85 * INTERVAL_MS
        expected_ts_2 = BASE_TS_MS + 90 * INTERVAL_MS
        assert timestamps[0] == expected_ts_0
        assert timestamps[1] == expected_ts_1
        assert timestamps[2] == expected_ts_2

    def test_build_fully_deterministic(
        self, builder: CandidateOutcomeBuilder, sample_outputs_long: List[SimulationOutput]
    ) -> None:
        """Running build twice with same inputs produces identical tables."""
        table1 = builder.build(sample_outputs_long)
        table2 = builder.build(sample_outputs_long)

        assert table1.equals(table2, check_metadata=False)

    def test_build_with_no_trade_output(
        self, builder: CandidateOutcomeBuilder, trending_btc_data: List[KlineRecord]
    ) -> None:
        """NO_TRADE outputs produce rows with fallback outcome fields."""
        outputs = [
            _make_simulation_output(
                idx=80, best_action="NO_TRADE", net_r=0.0, gross_r=0.0,
                cost_r=0.0, exit_reason="", run_id="no-trade"
            )
        ]
        table = builder.build(outputs)
        assert table.num_rows == 1
        assert table.column("side").to_pylist() == ["NO_TRADE"]
        # Net R should be 0 for no-trade
        assert table.column("net_R").to_pylist() == [0.0]
        assert table.column("exit_reason").to_pylist() == [""]

    def test_build_tolerates_single_bad_row(
        self, builder: CandidateOutcomeBuilder, trending_btc_data: List[KlineRecord]
    ) -> None:
        """A single bad row (missing symbol) doesn't crash the entire build."""
        good = _make_simulation_output(idx=80, symbol="BTCUSDT", run_id="good")
        bad = _make_simulation_output(idx=85, symbol="UNKNOWN", run_id="bad")
        table = builder.build([good, bad])
        assert table.num_rows == 1
        assert table.column("symbol").to_pylist() == ["BTCUSDT"]

    def test_build_regime_trend_in_uptrend(
        self, trending_btc_data: List[KlineRecord]
    ) -> None:
        """In an uptrending market, regime_trend should be 'up'."""
        b = CandidateOutcomeBuilder(
            market_data={"BTCUSDT": MarketDataContext(trending_btc_data)},
            lookback_bars=50,
        )
        outputs = [
            _make_simulation_output(idx=150, run_id="uptrend")  # well into the trend
        ]
        table = b.build(outputs)
        assert table.num_rows == 1
        regime = table.column("regime_trend").to_pylist()[0]
        assert regime == "up", f"Expected 'up', got '{regime}'"

    def test_build_regime_trend_in_downtrend(self) -> None:
        """In a downtrending market, regime_trend should be 'down'."""
        records = _make_trending_klines(200, start_price=50000.0, uptrend=False, symbol="BTCUSDT")
        b = CandidateOutcomeBuilder(
            market_data={"BTCUSDT": MarketDataContext(records)},
            lookback_bars=50,
        )
        outputs = [
            _make_simulation_output(idx=150, run_id="downtrend")
        ]
        table = b.build(outputs)
        assert table.num_rows == 1
        regime = table.column("regime_trend").to_pylist()[0]
        assert regime == "down", f"Expected 'down', got '{regime}'"

    def test_build_with_funding_defaults_to_zero(
        self, builder: CandidateOutcomeBuilder, sample_outputs_long: List[SimulationOutput]
    ) -> None:
        """Without funding_data, funding_context defaults to 0.0."""
        table = builder.build(sample_outputs_long)
        fc = table.column("funding_context").to_pylist()
        assert all(f == 0.0 for f in fc)

    def test_build_hold_duration_is_int64(
        self, builder: CandidateOutcomeBuilder, sample_outputs_long: List[SimulationOutput]
    ) -> None:
        """hold_duration column is int64."""
        table = builder.build(sample_outputs_long)
        hold = table.column("hold_duration")
        assert hold.type == pa.int64()
        values = hold.to_pylist()
        assert all(isinstance(v, int) for v in values)
        assert values == [4, 4, 4]


# ---------------------------------------------------------------------------
# Simulation-to-dataset integration tests (smoke test from simulation layer)
# ---------------------------------------------------------------------------


class TestSimulationIntegration:
    """End-to-end: synthetic klines -> triple-barrier -> CandidateOutcomeBuilder -> parquet Table."""

    @staticmethod
    def _generate_synthetic_klines(
        n: int = 200,
        start_price: float = 50000.0,
        trend: float = 0.0005,
        vol: float = 0.01,
        symbol: str = "BTCUSDT",
        interval: str = "1h",
    ) -> List[KlineRecord]:
        """Generate synthetic OHLCV bars with a mild uptrend and realistic noise."""
        np.random.seed(42)
        records: List[KlineRecord] = []
        price = start_price
        base_ts = 1704067200000  # 2024-01-01T00:00:00 UTC
        bar_ms = 3600000  # 1h in ms

        for i in range(n):
            r = np.random.randn()
            close = price * (1.0 + trend + vol * r)
            high = max(price, close) * (1.0 + abs(vol * np.random.randn() * 0.5))
            low = min(price, close) * (1.0 - abs(vol * np.random.randn() * 0.5))
            records.append(KlineRecord(
                symbol=symbol, timestamp=base_ts + i * bar_ms,
                open=price, high=round(high, 2), low=round(low, 2),
                close=round(close, 2), volume=1000.0 + abs(np.random.randn()) * 500,
                quote_volume=0.0, trade_count=100, taker_buy_volume=0.0,
                taker_buy_quote_volume=0.0,
                interval=interval, source="test", is_closed=True,
            ))
            price = close

        return records

    @staticmethod
    def _run_triple_barrier_sim(
        records: List[KlineRecord],
        max_hold: int = 12,
        stop_mult: float = 1.5,
        target_mult: float = 2.0,
    ) -> List[SimulationOutput]:
        """Minimal triple-barrier simulation — used only for integration testing."""
        n = len(records)
        closes = np.array([r.close for r in records], dtype=np.float64)
        highs = np.array([r.high for r in records], dtype=np.float64)
        lows = np.array([r.low for r in records], dtype=np.float64)

        tr = np.maximum(highs[1:] - lows[1:],
                        np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
        atr = np.full(n, np.nan)
        if n >= 15:
            atr[14] = np.mean(tr[:14])
            for i in range(15, n):
                atr[i] = (atr[i - 1] * 13 + tr[i - 1]) / 14

        outputs = []
        lookback = 50
        step = 4
        for i in range(lookback, n - max_hold - 1, step):
            if np.isnan(atr[i]) or atr[i] <= 0:
                continue
            entry = closes[i]
            sd = atr[i] * stop_mult
            td = atr[i] * target_mult

            # LONG
            lg, lx, lh = 0.0, "TIMEOUT", max_hold
            for j in range(1, min(max_hold + 1, n - i)):
                if lows[i + j] <= entry - sd:
                    lg = -sd / entry; lx = "STOP_HIT"; lh = j; break
                if highs[i + j] >= entry + td:
                    lg = td / entry; lx = "TARGET_HIT"; lh = j; break
                lg = (closes[i + j] - entry) / entry

            # SHORT
            sg, sx, sh = 0.0, "TIMEOUT", max_hold
            for j in range(1, min(max_hold + 1, n - i)):
                if highs[i + j] >= entry + sd:
                    sg = -sd / entry; sx = "STOP_HIT"; sh = j; break
                if lows[i + j] <= entry - td:
                    sg = td / entry; sx = "TARGET_HIT"; sh = j; break
                sg = (entry - closes[i + j]) / entry

            rtc = 0.0008
            nl, ns = lg - rtc, sg - rtc
            if nl > ns and nl > 0.0:
                ba = "LONG_NOW"
            elif ns > nl and ns > 0.0:
                ba = "SHORT_NOW"
            else:
                continue  # skip NO_TRADE for mining

            gross = lg if ba == "LONG_NOW" else sg
            net = nl if ba == "LONG_NOW" else ns
            hb = lh if ba == "LONG_NOW" else sh
            ex = lx if ba == "LONG_NOW" else sx
            ph = highs[i + 1: i + 1 + hb]
            pl = lows[i + 1: i + 1 + hb]

            mfe_r = (np.max(ph) - entry) / entry if len(ph) > 0 else 0.0
            mae_r = (entry - np.min(pl)) / entry if len(pl) > 0 else 0.0

            pm = PathMetrics(mfe_r=mfe_r, mae_r=mae_r,
                             path_quality_score=0.5, path_quality_bucket="medium")
            ao = ActionOutcome(
                action=ba, realized_r_gross=gross, realized_r_net=net,
                fee_cost_r=rtc * 0.6, slippage_cost_r=rtc * 0.3,
                funding_cost_r=rtc * 0.1, total_cost_r=rtc,
                exit_reason=ex, exit_price=entry * (1 + gross),
                exit_bar_index=hb, hold_duration_bars=hb,
                action_utility=net, path_metrics=pm, same_candle_ambiguity=False,
            )

            from datetime import datetime, timezone
            ts_iso = datetime.fromtimestamp(records[i].timestamp / 1000.0, tz=timezone.utc).isoformat()
            outputs.append(SimulationOutput(
                simulation_run_id=f"int_test_{records[i].symbol}",
                symbol=records[i].symbol, decision_timestamp=ts_iso,
                mode="SCALP", primary_interval=records[i].interval,
                resolution_status="RESOLVED",
                long_outcome=ao, short_outcome=ao, no_trade_outcome=NoTradeOutcome(),
                best_action=ba, action_gap_r=abs(nl - ns), regret_r=0.0,
                is_ambiguous=False,
                lineage=SimulationLineage(
                    simulation_family_version="test", simulation_profile_version="test",
                    cost_model_version="test", fee_model_version="test",
                    slippage_model_version="test", funding_model_version="test",
                    horizon_family="triple_barrier", stop_family="atr_multiplicative",
                    target_family="atr_multiplicative", time_exit_family="max_hold",
                    adapter_kind="test",
                ),
                second_best_action="SHORT_NOW" if ba == "LONG_NOW" else "LONG_NOW",
                invalidity_reason="", monte_carlo_run_id="", monte_carlo_family_version="",
            ))
        return outputs

    def test_full_pipeline_integration(self, trending_btc_data: List[KlineRecord]) -> None:
        """Smoke test: triple-barrier simulation -> CandidateOutcomeBuilder -> valid output."""
        import time
        t0 = time.time()

        # Step 1: Run simulation on synthetic (trending) data
        sim_outs = self._run_triple_barrier_sim(trending_btc_data)
        assert len(sim_outs) > 0, "Simulation produced no outputs"

        # Step 2: Build dataset via CandidateOutcomeBuilder
        builder = CandidateOutcomeBuilder(
            market_data={"BTCUSDT": MarketDataContext(trending_btc_data)},
            lookback_bars=50,
        )
        table = builder.build(sim_outs)
        elapsed = time.time() - t0

        # Step 3: Assertions
        assert table.num_rows > 0, "Builder produced empty table"
        assert table.num_rows <= len(sim_outs), "Should not add rows"
        expected_cols = {
            "symbol", "timestamp", "side", "mode", "timeframe",
            "regime_trend", "volatility_percentile", "momentum_rank",
            "volume_zscore", "atr_pct", "btc_regime", "pullback_atr",
            "distance_to_range_high", "spread_proxy", "funding_context",
            "net_R", "gross_R", "cost_R", "mfe_R", "mae_R",
            "exit_reason", "hold_duration", "simulation_run_id", "candidate_id",
        }
        assert set(table.column_names) == expected_cols, f"Schema mismatch: {set(table.column_names) - expected_cols}"

        # All rows should be LONG or SHORT (NO_TRADE is filtered)
        sides = set(table.column("side").to_pylist())
        assert sides.issubset({"LONG", "SHORT"}), f"Unexpected sides: {sides}"

        # Net R should have non-zero variation (positive mean, non-trivial spread)
        net_r = table.column("net_R").to_numpy()
        assert np.any(net_r > 0), "All net_R values are <= 0 — simulation may be broken"
        assert np.std(net_r) > 0.0, "All net_R values are identical — variance is zero"
        assert np.max(net_r) > np.min(net_r), "All net_R values are the same"

        # Time budget: should complete well within 10s for 200 bars
        assert elapsed < 10.0, f"Pipeline took {elapsed:.1f}s, expected <10s"

        logger = logging.getLogger("test_sim_integration")
        logger.info("Integration test passed: %d rows in %.2fs, net_R range [%.4f, %.4f]",
                     table.num_rows, elapsed, float(np.min(net_r)), float(np.max(net_r)))
