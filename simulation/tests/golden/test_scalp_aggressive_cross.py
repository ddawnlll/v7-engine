"""
Golden tests for SCALP, AGGRESSIVE_SCALP, and cross-mode invariants.

Deterministic: known input candles → expected exit reason and
directionally correct realized R.

Evidence ref: simulation/docs/profiles.md, simulation/docs/contracts.md
"""

import pytest
from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.engine import simulate


# ── Profile Builders ─────────────────────────────────────────────────────

def _scalp_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="scalp_profile-1.0.0",
        mode=TradingMode.SCALP,
        primary_interval="1h",
        max_holding_bars=12,
        stop_multiplier=1.5,
        target_multiplier=1.5,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.15,
        no_trade_default=True,
        context_intervals=["4h", "15m"],
        refinement_intervals=["15m"],
        stop_method="atr_medium",
        target_method="atr_medium",
        mae_penalty_weight=2.0,
        cost_penalty_weight=2.0,
        time_penalty_weight=1.5,
    )


def _aggressive_scalp_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="aggressive_scalp_profile-1.0.0",
        mode=TradingMode.AGGRESSIVE_SCALP,
        primary_interval="15m",
        max_holding_bars=5,
        stop_multiplier=1.0,
        target_multiplier=1.0,
        ambiguity_margin_r=0.05,
        min_action_edge_r=0.08,
        no_trade_default=True,
        context_intervals=["1h", "5m"],
        refinement_intervals=["5m"],
        stop_method="atr_tight",
        target_method="atr_tight",
        mae_penalty_weight=3.0,
        cost_penalty_weight=3.0,
        time_penalty_weight=2.5,
    )


def _swing_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="swing_profile-1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=30,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.20,
        min_action_edge_r=0.35,
        no_trade_default=False,
        context_intervals=["1d", "1h"],
        refinement_intervals=["1h"],
        stop_method="atr_wide",
        target_method="atr_wide",
        mae_penalty_weight=1.0,
        cost_penalty_weight=1.0,
        time_penalty_weight=0.3,
    )


# ── Input Builders ───────────────────────────────────────────────────────

def _make_input(
    entry_price: float,
    atr: float,
    candles: list[Candle],
    profile: SimulationProfile,
) -> SimulationInput:
    return SimulationInput(
        symbol="BTCUSDT",
        decision_timestamp="2026-06-01T12:00:00Z",
        mode=profile.mode,
        primary_interval=profile.primary_interval,
        entry_price=entry_price,
        atr=atr,
        future_path=FuturePath(candles=candles),
        profile=profile,
    )


def _costs_reduce(result, direction: str) -> None:
    """Assert that costs reduce net R vs gross R for a direction."""
    outcome = result.long_outcome if direction == "long" else result.short_outcome
    assert outcome.total_cost_r > 0, f"{direction}: costs must be positive"
    assert outcome.realized_r_net < outcome.realized_r_gross, \
        f"{direction}: net must be less than gross (costs reduce)"


# ═══════════════════════════════════════════════════════════════════════════
# SCALP Tests  (1h, 12 max bars, 1.5 stop, 1.5 target)
# ═══════════════════════════════════════════════════════════════════════════

# ── SCALP Test 1: TARGET_HIT (bullish) ──────────────────────────────────

def test_scalp_long_target_hit():
    """LONG hits target before stop in a clear uptrend.

    SCALP: 1h bars, 12 max, 1.5 stop/target.
    Entry: 50000, ATR: 1000
    Stop:  50000 - 1500 = 48500
    Target: 50000 + 1500 = 51500

    Path: two-bar uptrend, target hit on bar 1.
    """
    candles = [
        Candle(open=50200, high=50700, low=50100, close=50500),
        Candle(open=50500, high=51700, low=50400, close=51500),  # high >= 51500
    ]
    entry_price = 50000.0
    atr = 1000.0

    inp = _make_input(entry_price, atr, candles, _scalp_profile())
    result = simulate(inp)

    # LONG hits target (51600 >= 51500)
    assert result.long_outcome.exit_reason == "TARGET_HIT"
    assert abs(result.long_outcome.realized_r_gross - 1.0) < 0.01
    assert result.long_outcome.realized_r_net > 0
    _costs_reduce(result, "long")

    # SHORT hits stop in same bar (51700 >= 51500)
    assert result.short_outcome.exit_reason == "STOP_HIT"
    assert result.short_outcome.realized_r_gross < 0
    _costs_reduce(result, "short")

    # Best action should be LONG_NOW (unambiguous)
    assert result.best_action == "LONG_NOW"
    assert not result.is_ambiguous


# ── SCALP Test 2: SHORT wins (downtrend) ─────────────────────────────────

def test_scalp_short_target_hit():
    """SHORT hits target in a clear downtrend.

    Entry: 50000, ATR: 1000
    Stop:  48500, Target: 51500

    Path: two-bar downtrend — SHORT target (48500) hit at bar 1.
    Bar 0 high stays above entry so SHORT MAE tracking stays non-negative.
    """
    candles = [
        Candle(open=50100, high=50300, low=49600, close=49700),
        Candle(open=49700, high=49800, low=48300, close=48500),  # low <= 48500
    ]
    entry_price = 50000.0
    atr = 1000.0

    inp = _make_input(entry_price, atr, candles, _scalp_profile())
    result = simulate(inp)

    # SHORT hits target (low=48300 <= 48500)
    assert result.short_outcome.exit_reason == "TARGET_HIT"
    assert abs(result.short_outcome.realized_r_gross - 1.0) < 0.01
    assert result.short_outcome.realized_r_net > 0
    _costs_reduce(result, "short")

    # LONG hits stop (same bar, low <= 48500)
    assert result.long_outcome.exit_reason == "STOP_HIT"
    assert result.long_outcome.realized_r_gross < 0
    _costs_reduce(result, "long")

    assert result.best_action == "SHORT_NOW"
    assert not result.is_ambiguous


# ── SCALP Test 3: TIME_EXIT (range-bound) ────────────────────────────────

def test_scalp_long_time_exit():
    """Neither stop nor target hit within holding period → TIME_EXIT.

    Entry: 50000, ATR: 300
    Stop:  49550, Target: 50450

    Path: tight range, no extreme moves, 12 bars exhausted.
    """
    candles = [
        Candle(open=49950, high=50100, low=49800, close=50000 + i * 10)
        for i in range(12)
    ]
    entry_price = 50000.0
    atr = 300.0

    inp = _make_input(entry_price, atr, candles, _scalp_profile())
    result = simulate(inp)

    # Both directions TIME_EXIT (neither stop nor target hit)
    assert result.long_outcome.exit_reason == "TIME_EXIT"
    assert result.short_outcome.exit_reason == "TIME_EXIT"

    # LONG slightly positive (gentle drift up), SHORT slightly negative
    assert result.long_outcome.realized_r_gross >= 0
    assert result.short_outcome.realized_r_gross <= 0

    # Costs reduce net vs gross for both
    _costs_reduce(result, "long")
    _costs_reduce(result, "short")


# ── SCALP Test 4: NO_TRADE (tight range, both lose) ──────────────────────

def test_scalp_no_trade():
    """Both directions lose after costs → NO_TRADE saves loss.

    ATR=300, stop=49550, target=50450.
    Path returns to entry exactly — both directions negative after costs.
    """
    candles = [
        Candle(open=49900, high=50100, low=49800, close=50000)
        for _ in range(5)
    ]
    entry_price = 50000.0
    atr = 300.0

    inp = _make_input(entry_price, atr, candles, _scalp_profile())
    result = simulate(inp)

    # Both directions TIME_EXIT (range never hits stop/target)
    assert result.long_outcome.exit_reason == "TIME_EXIT"
    assert result.short_outcome.exit_reason == "TIME_EXIT"

    # Both net R negative after costs
    assert result.long_outcome.realized_r_net < 0
    assert result.short_outcome.realized_r_net < 0
    _costs_reduce(result, "long")
    _costs_reduce(result, "short")

    # NO_TRADE should be best (both directions lose, no-trade saves the loss)
    assert result.best_action == "NO_TRADE"
    assert result.no_trade_outcome.no_trade_quality in (
        "SAVED_LOSS", "CORRECT_NO_TRADE",
    )


# ═══════════════════════════════════════════════════════════════════════════
# AGGRESSIVE_SCALP Tests  (15m, 5 max bars, 1.0 stop, 1.0 target)
# ═══════════════════════════════════════════════════════════════════════════

# ── AGGRESSIVE_SCALP Test 5: LONG stop hit (sharp reversal) ─────────────

def test_aggressive_scalp_long_stop_hit():
    """LONG hits stop in a sharp reversal.

    AGGRESSIVE_SCALP: 15m bars, 5 max, 1.0 stop/target.
    Entry: 50000, ATR: 1000
    Stop:  49000, Target: 51000

    Path: sharp drop below LONG stop in bar 0.
    """
    candles = [
        Candle(open=49500, high=49800, low=48800, close=49000),  # low <= 49000
    ]
    entry_price = 50000.0
    atr = 1000.0

    inp = _make_input(entry_price, atr, candles, _aggressive_scalp_profile())
    result = simulate(inp)

    # LONG stops (48800 <= 49000)
    assert result.long_outcome.exit_reason == "STOP_HIT"
    assert abs(result.long_outcome.realized_r_gross - (-1.0)) < 0.01
    assert result.long_outcome.realized_r_net < 0
    _costs_reduce(result, "long")

    # SHORT hits target (same bar, 48800 <= 49000 = SHORT target)
    assert result.short_outcome.exit_reason == "TARGET_HIT"
    assert abs(result.short_outcome.realized_r_gross - 1.0) < 0.01
    assert result.short_outcome.realized_r_net > 0
    _costs_reduce(result, "short")

    # Best action: SHORT wins
    assert result.best_action == "SHORT_NOW"
    assert not result.is_ambiguous


# ── AGGRESSIVE_SCALP Test 6: SHORT target hit (sharp drop) ──────────────

def test_aggressive_scalp_short_target_hit():
    """SHORT hits target in a sharp drop.

    Entry: 50000, ATR: 1000
    Stop:  49000, Target: 51000 (LONG levels)
    SHORT stop: 51000, SHORT target: 49000

    Path: sharp drop, SHORT target hit on bar 0.
    """
    candles = [
        Candle(open=49200, high=49400, low=48600, close=48800),  # low <= 49000
    ]
    entry_price = 50000.0
    atr = 1000.0

    inp = _make_input(entry_price, atr, candles, _aggressive_scalp_profile())
    result = simulate(inp)

    # SHORT hits target (48600 <= 49000)
    assert result.short_outcome.exit_reason == "TARGET_HIT"
    assert abs(result.short_outcome.realized_r_gross - 1.0) < 0.01
    assert result.short_outcome.realized_r_net > 0
    _costs_reduce(result, "short")

    # LONG hits stop (same bar, 48600 <= 49000)
    assert result.long_outcome.exit_reason == "STOP_HIT"
    assert result.long_outcome.realized_r_gross < 0
    _costs_reduce(result, "long")

    assert result.best_action == "SHORT_NOW"
    assert not result.is_ambiguous


# ── AGGRESSIVE_SCALP Test 7: TIME_EXIT (range, 5 bars expired) ──────────

def test_aggressive_scalp_time_exit():
    """Neither stop nor target hit within 5 bars → TIME_EXIT.

    Entry: 50000, ATR: 300
    Stop:  49700, Target: 50300

    Path: tight range, 5 bars exhausted, close near entry.
    """
    candles = [
        Candle(open=49900, high=50100, low=49800, close=50000)
        for _ in range(5)
    ]
    entry_price = 50000.0
    atr = 300.0

    inp = _make_input(entry_price, atr, candles, _aggressive_scalp_profile())
    result = simulate(inp)

    # Both TIME_EXIT
    assert result.long_outcome.exit_reason == "TIME_EXIT"
    assert result.short_outcome.exit_reason == "TIME_EXIT"

    # Flat range: both close to breakeven
    _costs_reduce(result, "long")
    _costs_reduce(result, "short")


# ═══════════════════════════════════════════════════════════════════════════
# Cross-Mode Behavioral Invariants
# ═══════════════════════════════════════════════════════════════════════════

# ── Cross-Mode Test 8: Same-candle ambiguity (stop-first wins) ──────────

def test_same_candle_ambiguity():
    """Both stop and target in one candle; stop-first conservative rule wins.

    SCALP: entry=50000, ATR=1000, stop=48500, target=51500.
    One candle with low <= stop AND high >= target.
    Stop is checked first → STOP_HIT for both directions.
    """
    candles = [
        Candle(open=49000, high=52000, low=48000, close=50000),
    ]
    entry_price = 50000.0
    atr = 1000.0

    inp = _make_input(entry_price, atr, candles, _scalp_profile())
    result = simulate(inp)

    # Both directions stopped (stop-first rule)
    assert result.long_outcome.exit_reason == "STOP_HIT"
    assert result.short_outcome.exit_reason == "STOP_HIT"

    # Same-candle ambiguity flag set on both
    assert result.long_outcome.same_candle_ambiguity
    assert result.short_outcome.same_candle_ambiguity

    # Both lose, NO_TRADE wins
    assert result.long_outcome.realized_r_net < 0
    assert result.short_outcome.realized_r_net < 0
    assert result.no_trade_outcome.no_trade_quality in ("SAVED_LOSS",)


# ── Cross-Mode Test 9: NO_TRADE SAVED_LOSS ─────────────────────────────

def test_no_trade_saved_loss():
    """Both directions lose → NO_TRADE saved loss.

    SCALP: entry=50000, ATR=300, stop=49550, target=50450.
    Range-bound path; both TIME_EXIT with negative net R.
    """
    candles = [
        Candle(open=49900, high=50100, low=49800, close=49950),
        Candle(open=49950, high=50050, low=49850, close=49900),
        Candle(open=49900, high=50100, low=49800, close=50000),
    ]
    entry_price = 50000.0
    atr = 300.0

    inp = _make_input(entry_price, atr, candles, _scalp_profile())
    result = simulate(inp)

    # Both TIME_EXIT
    assert result.long_outcome.exit_reason == "TIME_EXIT"
    assert result.short_outcome.exit_reason == "TIME_EXIT"

    # Both net R negative (costs eat the small/no profit)
    assert result.long_outcome.realized_r_net < 0
    assert result.short_outcome.realized_r_net < 0
    _costs_reduce(result, "long")
    _costs_reduce(result, "short")

    # NO_TRADE saved loss
    assert result.best_action == "NO_TRADE"
    assert result.no_trade_outcome.no_trade_quality in (
        "SAVED_LOSS", "CORRECT_NO_TRADE",
    )
    assert result.no_trade_outcome.saved_loss_r > 0


# ── Cross-Mode Test 10: NO_TRADE MISSED_OPPORTUNITY ────────────────────

def test_no_trade_missed_opportunity():
    """One direction wins with high MAE → NO_TRADE missed opportunity.

    SWING (asymmetric stop/target): entry=50000, ATR=1500,
    stop_mult=2.0, target_mult=2.5.
    LONG stop=47000, target=53750.
    SHORT stop=53000, target=46250.

    Higher ATR reduces costs as fraction of R, widening the gap between
    missed_opportunity_r and saved_loss_r beyond the 0.20 ambiguity margin.

    Path: sharp dip near LONG stop then rally to target.
    LONG wins (R=1.25) but MAE penalty crushes utility.
    SHORT stops at -1.0R.
    """
    candles = [
        Candle(open=49000, high=52000, low=47100, close=50500),
        Candle(open=50500, high=54000, low=50000, close=53500),
    ]
    entry_price = 50000.0
    atr = 1500.0

    inp = _make_input(entry_price, atr, candles, _swing_profile())
    result = simulate(inp)

    # LONG hits target (MAE penalty from near-stop dip crushes utility)
    assert result.long_outcome.exit_reason == "TARGET_HIT"
    assert abs(result.long_outcome.realized_r_gross - 1.25) < 0.01
    assert result.long_outcome.realized_r_net > 0
    _costs_reduce(result, "long")

    # SHORT hits stop
    assert result.short_outcome.exit_reason == "STOP_HIT"
    assert result.short_outcome.realized_r_gross < 0
    _costs_reduce(result, "short")

    # MAE_R should reflect the near-stop excursion
    assert result.long_outcome.path_metrics.mae_r < 0

    # No-trade: MISSED_OPPORTUNITY (missed > saved beyond margin)
    # SWING asymmetry: TARGET_HIT gives R=1.25, STOP_HIT gives R=-1.0
    # Higher ATR (1500) reduces cost_R proportion, widening gap > 0.20
    gap = result.no_trade_outcome.missed_opportunity_r - result.no_trade_outcome.saved_loss_r
    assert gap > 0.20, f"gap={gap:.4f} must exceed ambig margin 0.20"
    assert result.no_trade_outcome.no_trade_quality == "MISSED_OPPORTUNITY"
    assert result.no_trade_outcome.missed_opportunity_r > 0
    assert result.no_trade_outcome.saved_loss_r > 0
    assert not result.no_trade_outcome.was_correct_skip
