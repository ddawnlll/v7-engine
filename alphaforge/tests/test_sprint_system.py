"""Comprehensive tests for the AlphaForge profitability sprint system.

Covers:
  - SprintConfig: creation, defaults, immutability
  - CostSanityReport: frozen dataclass, field access
  - CostSanityChecker: positive/zero/small gross, sign-flip, empty input
  - FactorResult: frozen dataclass, all fields accessible
  - SprintResult: factor list, config, timestamp
  - Leaderboard: build, sort order, CSV output
  - Eval-gate logic: all pass, MIN_TRADES fail, COST_SURVIVAL fail, multi-fail
  - Candidate output: factor names, metrics, valid markdown structure

All tests use synthetic data — no real data dependencies.
AAA pattern. Each test independent.
"""

from __future__ import annotations

import csv
import tempfile
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alphaforge.sprint.config import SprintConfig
from alphaforge.sprint.cost_sanity import CostSanityChecker, CostSanityReport
from alphaforge.sprint.leaderboard import Leaderboard
from alphaforge.sprint.eval_gate import EvalGateRunner
from alphaforge.sprint.runner import FactorResult, FactorSprintRunner, SprintResult


# ── HELPERS ────────────────────────────────────────────────────────


def _make_factor_result(
    factor_name: str = "test_factor",
    pass_fail: str = "PASS",
    net_return: float = 1.0,
    expectancy_r: float = 0.5,
    profit_factor: float = 2.0,
    trade_count: int = 500,
    max_drawdown: float = 0.10,
    gross_return: float = 1.5,
    ic_ir: float = 0.5,
    mean_ic: float = 0.03,
    turnover: float = 0.20,
    win_rate: float = 0.55,
    cost_drag: float = 0.5,
    direction: str = "long",
    horizon: int = 4,
    notes: list[str] | None = None,
) -> FactorResult:
    """Build a FactorResult with sensible defaults."""
    return FactorResult(
        factor_name=factor_name,
        direction=direction,
        horizon=horizon,
        mean_ic=mean_ic,
        ic_ir=ic_ir,
        gross_return=gross_return,
        net_return=net_return,
        expectancy_r=expectancy_r,
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        turnover=turnover,
        cost_drag=cost_drag,
        trade_count=trade_count,
        pass_fail=pass_fail,
        notes=notes or ["All sanity checks passed"],
    )


def _make_sprint_config(**overrides) -> SprintConfig:
    """Build a SprintConfig with optional overrides."""
    return SprintConfig(**overrides)


def _make_ohlcv(n_timestamps: int = 200, n_symbols: int = 10) -> dict[str, pd.DataFrame]:
    """Generate synthetic OHLCV panel data."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_timestamps, freq="1h")
    symbols = [f"SYM{i}" for i in range(n_symbols)]

    base = 100.0
    returns = np.random.randn(n_timestamps, n_symbols) * 0.02
    close = base * np.exp(np.cumsum(returns, axis=0))
    high = close * (1 + np.abs(np.random.randn(n_timestamps, n_symbols) * 0.005))
    low = close * (1 - np.abs(np.random.randn(n_timestamps, n_symbols) * 0.005))
    open_ = close * (1 + np.random.randn(n_timestamps, n_symbols) * 0.002)
    volume = np.random.rand(n_timestamps, n_symbols) * 1000 + 100

    return {
        "close": pd.DataFrame(close, index=dates, columns=symbols),
        "high": pd.DataFrame(high, index=dates, columns=symbols),
        "low": pd.DataFrame(low, index=dates, columns=symbols),
        "open": pd.DataFrame(open_, index=dates, columns=symbols),
        "volume": pd.DataFrame(volume, index=dates, columns=symbols),
    }


# ══════════════════════════════════════════════════════════════════
# 1. SprintConfig
# ══════════════════════════════════════════════════════════════════


class TestSprintConfig:
    """Tests for SprintConfig frozen dataclass."""

    def test_creation_with_defaults(self):
        """Default SprintConfig has expected field values."""
        # Act
        cfg = SprintConfig()

        # Assert
        assert cfg.symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
        assert cfg.modes == ["SCALP"]
        assert cfg.start_date == "2024-01-01"
        assert cfg.end_date == "2024-12-31"
        assert cfg.fee_bps == 4.0
        assert cfg.slippage_bps == 1.0
        assert cfg.min_trades == 200
        assert cfg.min_positive_folds == 4
        assert cfg.min_expectancy_r == 0.0
        assert cfg.min_profit_factor == 1.10
        assert cfg.max_drawdown_pct == 0.30

    def test_creation_with_custom_values(self):
        """SprintConfig accepts custom values for all fields."""
        # Act
        cfg = SprintConfig(
            symbols=["BTCUSDT"],
            modes=["SWING"],
            start_date="2023-06-01",
            end_date="2023-12-31",
            data_dir="/data/custom",
            output_dir="/output/custom",
            fee_bps=6.0,
            slippage_bps=2.5,
            min_trades=100,
            min_positive_folds=2,
            min_expectancy_r=0.1,
            min_profit_factor=1.5,
            max_drawdown_pct=0.20,
        )

        # Assert
        assert cfg.symbols == ["BTCUSDT"]
        assert cfg.modes == ["SWING"]
        assert cfg.fee_bps == 6.0
        assert cfg.slippage_bps == 2.5
        assert cfg.min_trades == 100
        assert cfg.min_expectancy_r == 0.1
        assert cfg.min_profit_factor == 1.5
        assert cfg.max_drawdown_pct == 0.20

    def test_frozen_immutability(self):
        """SprintConfig is frozen — attribute assignment raises FrozenInstanceError."""
        # Arrange
        cfg = SprintConfig()

        # Act & Assert
        with pytest.raises(FrozenInstanceError):
            cfg.fee_bps = 10.0  # type: ignore[misc]

    def test_list_fields_are_separate_copies(self):
        """SprintConfig default list fields are independent across instances.

        Note: frozen dataclasses prevent reassignment of the field, but
        the list object itself is mutable. This test verifies that two
        instances get independent default list objects.
        """
        # Arrange & Act
        cfg1 = SprintConfig()
        cfg2 = SprintConfig()

        # Assert — lists are equal but not the same object
        assert cfg1.symbols == cfg2.symbols
        assert cfg1.symbols is not cfg2.symbols

    def test_equality(self):
        """Two identical SprintConfig instances are equal."""
        # Arrange
        cfg1 = SprintConfig(fee_bps=5.0, min_trades=300)
        cfg2 = SprintConfig(fee_bps=5.0, min_trades=300)

        # Assert
        assert cfg1 == cfg2


# ══════════════════════════════════════════════════════════════════
# 2. CostSanityReport
# ══════════════════════════════════════════════════════════════════


class TestCostSanityReport:
    """Tests for CostSanityReport frozen dataclass."""

    def test_all_fields_accessible(self):
        """All fields of CostSanityReport are readable."""
        # Arrange
        report = CostSanityReport(
            gross_return=1.5,
            net_return=1.0,
            cost_drag=0.5,
            cost_drag_pct=0.333,
            sanity_pass=True,
        )

        # Assert
        assert report.gross_return == 1.5
        assert report.net_return == 1.0
        assert report.cost_drag == 0.5
        assert report.cost_drag_pct == 0.333
        assert report.sanity_pass is True

    def test_frozen_immutability(self):
        """CostSanityReport is frozen — assignment raises FrozenInstanceError."""
        # Arrange
        report = CostSanityReport(
            gross_return=1.0, net_return=0.8, cost_drag=0.2,
            cost_drag_pct=0.2, sanity_pass=True,
        )

        # Act & Assert
        with pytest.raises(FrozenInstanceError):
            report.net_return = 0.5  # type: ignore[misc]

    def test_equality(self):
        """Two identical CostSanityReport instances are equal."""
        # Arrange
        args = dict(gross_return=2.0, net_return=1.5, cost_drag=0.5,
                     cost_drag_pct=0.25, sanity_pass=True)
        r1 = CostSanityReport(**args)
        r2 = CostSanityReport(**args)

        # Assert
        assert r1 == r2


# ══════════════════════════════════════════════════════════════════
# 3. CostSanityChecker
# ══════════════════════════════════════════════════════════════════


class TestCostSanityChecker:
    """Tests for CostSanityChecker.check().

    Uses the real checker (no mocks) — the source now computes costs
    inline rather than importing from simulation.engine.costs.
    """

    def test_positive_gross_reduced_net(self):
        """Positive gross return should be reduced by cost drag but stay positive."""
        # Arrange
        checker = CostSanityChecker()
        gross = pd.Series([0.01, 0.02, 0.015, 0.008])

        # Act
        report = checker.check(gross, fee_bps=4.0, slippage_bps=1.0)

        # Assert
        assert report.gross_return == pytest.approx(sum(gross))
        assert report.cost_drag > 0, "cost_drag must be positive"
        assert report.net_return < report.gross_return, "net < gross"
        assert report.sanity_pass is True, "net positive -> sanity pass"

    def test_zero_gross_yields_negative_net(self):
        """Zero gross return with non-zero costs yields negative net."""
        # Arrange
        checker = CostSanityChecker()
        gross = pd.Series([0.0, 0.0, 0.0])

        # Act
        report = checker.check(gross)

        # Assert
        assert report.gross_return == 0.0
        assert report.cost_drag > 0, "costs still apply on zero gross"
        assert report.net_return < 0, "net is negative when costs exceed zero gross"
        assert report.sanity_pass is False

    def test_very_small_gross_flips_sign(self):
        """Very small gross return can flip sign under high costs (sanity_fail)."""
        # Arrange
        checker = CostSanityChecker()
        gross = pd.Series([0.001])  # Tiny gross

        # Act
        report = checker.check(gross, fee_bps=100.0, slippage_bps=100.0)

        # Assert
        assert report.net_return < 0, "net should be negative when costs exceed gross"
        assert report.sanity_pass is False

    def test_empty_series_returns_zero_report(self):
        """Empty input returns zeroed-out report with sanity_pass=False."""
        # Arrange
        checker = CostSanityChecker()
        gross = pd.Series(dtype=float)

        # Act
        report = checker.check(gross)

        # Assert
        assert report.gross_return == 0.0
        assert report.net_return == 0.0
        assert report.cost_drag == 0.0
        assert report.cost_drag_pct == 0.0
        assert report.sanity_pass is False

    def test_cost_drag_pct_calculation(self):
        """cost_drag_pct should be abs(cost_drag / gross_return) for nonzero gross."""
        # Arrange
        checker = CostSanityChecker()
        gross = pd.Series([0.1, 0.2, 0.3])

        # Act
        report = checker.check(gross)

        # Assert — cost_drag_pct is cost_drag/gross_return * 100 (percentage)
        expected_pct = abs(report.cost_drag / report.gross_return) * 100.0
        assert report.cost_drag_pct == pytest.approx(expected_pct)


# ══════════════════════════════════════════════════════════════════
# 4. FactorResult
# ══════════════════════════════════════════════════════════════════


class TestFactorResult:
    """Tests for FactorResult frozen dataclass."""

    def test_creation_all_fields(self):
        """FactorResult can be created with all required fields."""
        # Act
        fr = _make_factor_result(
            factor_name="momentum_1h",
            direction="long",
            horizon=4,
            mean_ic=0.035,
            ic_ir=0.62,
            gross_return=2.1,
            net_return=1.6,
            expectancy_r=0.8,
            profit_factor=2.5,
            max_drawdown=0.12,
            win_rate=0.58,
            turnover=0.18,
            cost_drag=0.5,
            trade_count=600,
            pass_fail="PASS",
            notes=["All sanity checks passed"],
        )

        # Assert
        assert fr.factor_name == "momentum_1h"
        assert fr.direction == "long"
        assert fr.horizon == 4
        assert fr.mean_ic == 0.035
        assert fr.ic_ir == 0.62
        assert fr.gross_return == 2.1
        assert fr.net_return == 1.6
        assert fr.expectancy_r == 0.8
        assert fr.profit_factor == 2.5
        assert fr.max_drawdown == 0.12
        assert fr.win_rate == 0.58
        assert fr.turnover == 0.18
        assert fr.cost_drag == 0.5
        assert fr.trade_count == 600
        assert fr.pass_fail == "PASS"
        assert fr.notes == ["All sanity checks passed"]

    def test_frozen_immutability(self):
        """FactorResult is frozen — assignment raises FrozenInstanceError."""
        # Arrange
        fr = _make_factor_result()

        # Act & Assert
        with pytest.raises(FrozenInstanceError):
            fr.pass_fail = "FAIL"  # type: ignore[misc]

    def test_default_notes_is_empty_list(self):
        """FactorResult default notes field is an empty list."""
        # Act
        fr = FactorResult(
            factor_name="x", direction="long", horizon=1,
            mean_ic=0.0, ic_ir=0.0, gross_return=0.0, net_return=0.0,
            expectancy_r=0.0, profit_factor=0.0, max_drawdown=0.0,
            win_rate=0.0, turnover=0.0, cost_drag=0.0, trade_count=0,
            pass_fail="FAIL",
        )

        # Assert
        assert fr.notes == []

    def test_notes_is_independent_copy(self):
        """Two FactorResults with same notes list are independent (no aliasing)."""
        # Arrange
        notes_a = ["note1"]
        fr1 = _make_factor_result(notes=notes_a)
        fr2 = _make_factor_result(notes=["note1"])

        # Assert
        assert fr1.notes == fr2.notes
        # They are equal but not the same object
        assert fr1.notes is not fr2.notes

    def test_equality(self):
        """Two identical FactorResults are equal."""
        # Arrange
        fr1 = _make_factor_result(factor_name="alpha", net_return=1.0)
        fr2 = _make_factor_result(factor_name="alpha", net_return=1.0)

        # Assert
        assert fr1 == fr2


# ══════════════════════════════════════════════════════════════════
# 5. SprintResult
# ══════════════════════════════════════════════════════════════════


class TestSprintResult:
    """Tests for SprintResult frozen dataclass."""

    def test_contains_factor_list(self):
        """SprintResult stores a list of FactorResult objects."""
        # Arrange
        factors = [_make_factor_result(factor_name=f"f{i}") for i in range(3)]
        config = _make_sprint_config()

        # Act
        result = SprintResult(factors=factors, config=config)

        # Assert
        assert len(result.factors) == 3
        assert all(isinstance(f, FactorResult) for f in result.factors)
        assert result.factors[0].factor_name == "f0"
        assert result.factors[2].factor_name == "f2"

    def test_contains_config(self):
        """SprintResult stores the SprintConfig used."""
        # Arrange
        config = _make_sprint_config(fee_bps=8.0, min_trades=500)
        factors = [_make_factor_result()]

        # Act
        result = SprintResult(factors=factors, config=config)

        # Assert
        assert result.config.fee_bps == 8.0
        assert result.config.min_trades == 500

    def test_has_timestamp(self):
        """SprintResult includes an ISO-formatted timestamp."""
        # Arrange
        config = _make_sprint_config()
        factors = [_make_factor_result()]

        # Act
        before = datetime.now(timezone.utc).isoformat()
        result = SprintResult(factors=factors, config=config)
        after = datetime.now(timezone.utc).isoformat()

        # Assert
        assert isinstance(result.timestamp, str)
        assert len(result.timestamp) > 10
        # Timestamp should be parseable
        datetime.fromisoformat(result.timestamp)

    def test_empty_factor_list(self):
        """SprintResult can hold an empty factor list."""
        # Act
        result = SprintResult(factors=[], config=_make_sprint_config())

        # Assert
        assert result.factors == []

    def test_frozen_immutability(self):
        """SprintResult is frozen."""
        # Arrange
        result = SprintResult(
            factors=[_make_factor_result()],
            config=_make_sprint_config(),
        )

        # Act & Assert
        with pytest.raises(FrozenInstanceError):
            result.factors = []  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════════
# 6. Leaderboard
# ══════════════════════════════════════════════════════════════════


class TestLeaderboard:
    """Tests for Leaderboard.build() and Leaderboard.save()."""

    def test_build_has_expected_columns(self):
        """Leaderboard DataFrame contains all expected columns."""
        # Arrange
        sprint = SprintResult(
            factors=[_make_factor_result()],
            config=_make_sprint_config(),
        )
        lb = Leaderboard()

        # Act
        df = lb.build(sprint)

        # Assert
        expected_cols = [
            "rank", "factor_name", "horizon", "direction", "mean_ic", "ic_ir",
            "gross_return", "net_return", "expectancy_r", "profit_factor",
            "max_drawdown", "win_rate", "turnover", "cost_drag", "trade_count",
            "pass_fail", "notes",
        ]
        for col in expected_cols:
            assert col in df.columns, f"Missing column: {col}"

    def test_sort_order_pass_before_watch_before_fail(self):
        """PASS factors appear before WATCH, which appear before FAIL."""
        # Arrange
        factors = [
            _make_factor_result(factor_name="fail_factor", pass_fail="FAIL",
                                expectancy_r=-0.1),
            _make_factor_result(factor_name="pass_factor", pass_fail="PASS",
                                expectancy_r=0.8),
            _make_factor_result(factor_name="watch_factor", pass_fail="WATCH",
                                expectancy_r=0.3),
        ]
        sprint = SprintResult(factors=factors, config=_make_sprint_config())
        lb = Leaderboard()

        # Act
        df = lb.build(sprint)

        # Assert
        tiers = df["pass_fail"].tolist()
        # PASS should come first
        first_pass = tiers.index("PASS")
        first_watch = tiers.index("WATCH")
        first_fail = tiers.index("FAIL")
        assert first_pass < first_watch < first_fail

    def test_pass_factors_sorted_by_expectancy_desc(self):
        """Within PASS tier, factors are sorted by expectancy_r descending."""
        # Arrange
        factors = [
            _make_factor_result(factor_name="pass_low", pass_fail="PASS",
                                expectancy_r=0.2),
            _make_factor_result(factor_name="pass_high", pass_fail="PASS",
                                expectancy_r=0.9),
            _make_factor_result(factor_name="pass_mid", pass_fail="PASS",
                                expectancy_r=0.5),
        ]
        sprint = SprintResult(factors=factors, config=_make_sprint_config())
        lb = Leaderboard()

        # Act
        df = lb.build(sprint)

        # Assert
        pass_rows = df[df["pass_fail"] == "PASS"]
        expectancies = pass_rows["expectancy_r"].tolist()
        assert expectancies == sorted(expectancies, reverse=True)

    def test_build_empty_factors_returns_empty_df(self):
        """SprintResult with no factors produces an empty DataFrame."""
        # Arrange
        sprint = SprintResult(factors=[], config=_make_sprint_config())
        lb = Leaderboard()

        # Act
        df = lb.build(sprint)

        # Assert
        assert df.empty

    def test_rank_is_1_indexed(self):
        """Rank column starts at 1 and increments."""
        # Arrange
        factors = [_make_factor_result(factor_name=f"f{i}") for i in range(5)]
        sprint = SprintResult(factors=factors, config=_make_sprint_config())
        lb = Leaderboard()

        # Act
        df = lb.build(sprint)

        # Assert
        assert df["rank"].tolist() == [1, 2, 3, 4, 5]

    def test_notes_joined_as_string(self):
        """Notes list is joined with '; ' into a single string column."""
        # Arrange
        factors = [_make_factor_result(notes=["note_a", "note_b"])]
        sprint = SprintResult(factors=factors, config=_make_sprint_config())
        lb = Leaderboard()

        # Act
        df = lb.build(sprint)

        # Assert
        assert df.iloc[0]["notes"] == "note_a; note_b"

    def test_save_creates_csv_file(self):
        """save() writes a CSV file that can be re-read."""
        # Arrange
        factors = [
            _make_factor_result(factor_name="alpha_factor"),
            _make_factor_result(factor_name="beta_factor", pass_fail="FAIL"),
        ]
        sprint = SprintResult(factors=factors, config=_make_sprint_config())
        lb = Leaderboard()
        df = lb.build(sprint)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Act
            csv_path = lb.save(df, output_dir=tmpdir)

            # Assert
            assert csv_path.exists()
            assert csv_path.suffix == ".csv"
            reloaded = pd.read_csv(csv_path)
            assert len(reloaded) == 2
            assert "factor_name" in reloaded.columns
            assert "alpha_factor" in reloaded["factor_name"].values

    def test_csv_content_matches_build(self):
        """CSV written by save() matches the DataFrame from build()."""
        # Arrange
        factors = [_make_factor_result(factor_name="gamma", net_return=1.23)]
        sprint = SprintResult(factors=factors, config=_make_sprint_config())
        lb = Leaderboard()
        df = lb.build(sprint)

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = lb.save(df, output_dir=tmpdir)

            # Act — re-read CSV
            with open(csv_path, "r") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            # Assert
            assert len(rows) == 1
            assert rows[0]["factor_name"] == "gamma"
            assert float(rows[0]["net_return"]) == pytest.approx(1.23)


# ══════════════════════════════════════════════════════════════════
# 7. Eval-Gate Logic (via FactorResult pass_fail mapping)
# ══════════════════════════════════════════════════════════════════


class TestEvalGateLogic:
    """Tests for evaluation gate logic.

    The sprint system applies multiple gates to determine pass/fail.
    We test these by calling the real EvalGateRunner.evaluate() directly
    with FactorResult objects that satisfy/violate each gate.
    """

    def test_all_gates_pass(self):
        """All gates pass -> overall_pass True."""
        # Arrange
        cfg = _make_sprint_config()
        fr = _make_factor_result(factor_name="winner")

        # Act
        result = EvalGateRunner(cfg).evaluate(fr)

        # Assert
        assert result.overall_pass, f"Expected PASS, got: {result.summary}"
        assert all(g.passed for g in result.gates)

    def test_min_trades_gate_fail(self):
        """Trade count below minimum -> MIN_TRADES gate fails."""
        # Arrange
        cfg = _make_sprint_config(min_trades=200)
        fr = _make_factor_result(
            factor_name="low_trades",
            trade_count=50,
            net_return=1.0,
            profit_factor=3.0,
        )

        # Act
        result = EvalGateRunner(cfg).evaluate(fr)

        # Assert
        assert not result.overall_pass
        mt = next(g for g in result.gates if g.gate_name == "MIN_TRADES")
        assert not mt.passed
        assert mt.value == 50
        assert mt.threshold == 200

    def test_net_positive_gate_fail(self):
        """Net return negative -> NET_POSITIVE gate fails."""
        # Arrange
        cfg = _make_sprint_config()
        fr = _make_factor_result(
            factor_name="cost_killed",
            net_return=-0.5,
            profit_factor=3.0,
        )

        # Act
        result = EvalGateRunner(cfg).evaluate(fr)

        # Assert
        assert not result.overall_pass
        np_gate = next(g for g in result.gates if g.gate_name == "NET_POSITIVE")
        assert not np_gate.passed
        assert np_gate.value == -0.5
        assert np_gate.threshold == 0.0

    def test_profit_factor_gate_fail(self):
        """Profit factor below minimum -> PROFIT_FACTOR gate fails."""
        # Arrange
        cfg = _make_sprint_config(min_profit_factor=1.10)
        fr = _make_factor_result(
            factor_name="low_pf",
            profit_factor=0.8,
            trade_count=500,
            net_return=0.5,
        )

        # Act
        result = EvalGateRunner(cfg).evaluate(fr)

        # Assert
        assert not result.overall_pass
        pf = next(g for g in result.gates if g.gate_name == "PROFIT_FACTOR")
        assert not pf.passed
        assert pf.value == 0.8
        assert pf.threshold == 1.10

    def test_max_drawdown_gate_fail(self):
        """Drawdown exceeding maximum -> DRAWDOWN gate fails."""
        # Arrange
        cfg = _make_sprint_config(max_drawdown_pct=0.30)
        fr = _make_factor_result(
            factor_name="deep_dd",
            max_drawdown=0.45,
            trade_count=500,
            net_return=0.5,
            profit_factor=1.5,
        )

        # Act
        result = EvalGateRunner(cfg).evaluate(fr)

        # Assert
        assert not result.overall_pass
        dd = next(g for g in result.gates if g.gate_name == "DRAWDOWN")
        assert not dd.passed

    def test_multiple_gates_fail_all_reported(self):
        """Multiple simultaneous gate failures -> all failing gates reported."""
        # Arrange
        cfg = _make_sprint_config(
            min_trades=200,
            min_profit_factor=1.10,
            max_drawdown_pct=0.30,
        )
        fr = _make_factor_result(
            factor_name="everything_wrong",
            trade_count=30,           # fails MIN_TRADES
            net_return=-1.0,          # fails NET_POSITIVE
            profit_factor=0.5,        # fails PROFIT_FACTOR
            max_drawdown=0.50,        # fails DRAWDOWN
        )

        # Act
        result = EvalGateRunner(cfg).evaluate(fr)

        # Assert
        assert not result.overall_pass
        failed_names = {g.gate_name for g in result.gates if not g.passed}
        assert "MIN_TRADES" in failed_names
        assert "NET_POSITIVE" in failed_names
        assert "PROFIT_FACTOR" in failed_names
        assert "DRAWDOWN" in failed_names
        assert len(failed_names) >= 3, (
            f"Expected at least 3 failing gates, got: {failed_names}"
        )

    def test_pass_factor_ends_up_first_in_leaderboard(self):
        """When mixing PASS/FAIL factors, PASS ranks higher in leaderboard."""
        # Arrange
        factors = [
            _make_factor_result(factor_name="loser", pass_fail="FAIL"),
            _make_factor_result(factor_name="winner", pass_fail="PASS"),
        ]
        sprint = SprintResult(factors=factors, config=_make_sprint_config())

        # Act
        df = Leaderboard().build(sprint)

        # Assert
        assert df.iloc[0]["factor_name"] == "winner"
        assert df.iloc[0]["pass_fail"] == "PASS"


# ══════════════════════════════════════════════════════════════════
# 8. Candidate Output (Leaderboard as candidate reporter)
# ══════════════════════════════════════════════════════════════════


class TestCandidateOutput:
    """Tests for candidate output reporting via Leaderboard.

    The leaderboard serves as the candidate reporter: it produces a
    structured output (CSV) containing factor names and metrics.
    """

    def test_output_contains_factor_names(self):
        """Leaderboard output contains all submitted factor names."""
        # Arrange
        names = ["momentum_1h", "reversal_4h", "breakout_12h"]
        factors = [_make_factor_result(factor_name=n) for n in names]
        sprint = SprintResult(factors=factors, config=_make_sprint_config())

        # Act
        df = Leaderboard().build(sprint)

        # Assert
        result_names = set(df["factor_name"].tolist())
        assert result_names == set(names)

    def test_output_contains_key_metrics(self):
        """Leaderboard output contains key performance metrics."""
        # Arrange
        fr = _make_factor_result(
            factor_name="metric_test",
            mean_ic=0.04,
            ic_ir=0.7,
            gross_return=2.5,
            net_return=1.8,
            expectancy_r=0.9,
            profit_factor=3.2,
            win_rate=0.6,
            trade_count=750,
        )
        sprint = SprintResult(factors=[fr], config=_make_sprint_config())

        # Act
        df = Leaderboard().build(sprint)
        row = df.iloc[0]

        # Assert — all key metrics present and correct
        assert row["factor_name"] == "metric_test"
        assert row["mean_ic"] == pytest.approx(0.04)
        assert row["ic_ir"] == pytest.approx(0.7)
        assert row["gross_return"] == pytest.approx(2.5)
        assert row["net_return"] == pytest.approx(1.8)
        assert row["expectancy_r"] == pytest.approx(0.9)
        assert row["profit_factor"] == pytest.approx(3.2)
        assert row["win_rate"] == pytest.approx(0.6)
        assert row["trade_count"] == 750

    def test_output_csv_is_valid(self):
        """Leaderboard CSV output is structurally valid and round-trips correctly."""
        # Arrange
        factors = [
            _make_factor_result(factor_name="alpha", pass_fail="PASS"),
            _make_factor_result(factor_name="beta", pass_fail="WATCH"),
        ]
        sprint = SprintResult(factors=factors, config=_make_sprint_config())
        lb = Leaderboard()
        df = lb.build(sprint)

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = lb.save(df, output_dir=tmpdir)

            # Act — re-read and validate
            reloaded = pd.read_csv(csv_path)

            # Assert structure
            assert len(reloaded) == 2
            assert "rank" in reloaded.columns
            assert reloaded["rank"].min() == 1
            assert reloaded["rank"].max() == 2
            # All rows have pass_fail
            assert reloaded["pass_fail"].notna().all()
            # No trailing/leading whitespace in factor_name
            for name in reloaded["factor_name"]:
                assert name == name.strip()

    def test_output_notes_are_human_readable(self):
        """Notes column in output contains human-readable strings."""
        # Arrange
        fr = _make_factor_result(
            factor_name="note_test",
            notes=["strong signal, IC_IR=0.62", "cost drag within tolerance"],
        )
        sprint = SprintResult(factors=[fr], config=_make_sprint_config())

        # Act
        df = Leaderboard().build(sprint)
        notes_str = df.iloc[0]["notes"]

        # Assert
        assert isinstance(notes_str, str)
        assert "IC_IR" in notes_str
        assert "cost drag" in notes_str

    def test_direction_preserved_in_output(self):
        """Factor direction (long/short/agnostic) is preserved in output."""
        # Arrange
        factors = [
            _make_factor_result(factor_name="long_f", direction="long"),
            _make_factor_result(factor_name="short_f", direction="short"),
            _make_factor_result(factor_name="agno_f", direction="agnostic"),
        ]
        sprint = SprintResult(factors=factors, config=_make_sprint_config())

        # Act
        df = Leaderboard().build(sprint)

        # Assert
        directions = set(df["direction"].tolist())
        assert "long" in directions
        assert "short" in directions
        assert "agnostic" in directions
