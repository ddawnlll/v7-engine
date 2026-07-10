"""Shared fixtures for acceptance tests.

All fixtures are small, deterministic, and offline.
"""
from __future__ import annotations

import numpy as np
import pytest

from simulation.contracts.models import (
    Candle,
    FundingEvent,
    FuturePath,
    SimulationInput,
    SimulationProfile,
    TradingMode,
)


# ── Synthetic OHLCV helpers ─────────────────────────────────────────────


def make_ohlcv_dict(
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
    bars_per_symbol: int = 500,
    random_seed: int = 42,
    timestamp_start: int = 1_700_000_000_000,
    interleaved: bool = True,
) -> dict:
    """Deterministic synthetic OHLCV dict matching the pipeline convention.

    Produces interleaved multi-symbol data with unequal row counts when
    bars_per_symbol is a tuple of different lengths.

    Returns dict with keys: open, high, low, close, volume, timestamp, symbol.
    All arrays have the same length (sum of bars_per_symbol).
    """
    if isinstance(bars_per_symbol, int):
        bars_per_symbol = (bars_per_symbol,) * len(symbols)
    assert len(bars_per_symbol) == len(symbols)

    rng = np.random.RandomState(random_seed)
    all_open, all_high, all_low, all_close, all_volume = [], [], [], [], []
    all_ts, all_sym = [], []
    ts = timestamp_start

    for sym, n_bars in zip(symbols, bars_per_symbol):
        returns = rng.randn(n_bars) * 0.02
        close = 100.0 * np.exp(np.cumsum(returns))
        close = np.maximum(close, 0.01)
        noise = rng.randn(n_bars) * 0.005
        open_arr = close * (1.0 + noise * 0.5)
        high_noise = rng.uniform(0.0, 0.02, n_bars)
        low_noise = rng.uniform(0.0, 0.02, n_bars)
        high = np.maximum(open_arr, close) * (1.0 + high_noise)
        low = np.minimum(open_arr, close) * (1.0 - low_noise)
        low = np.minimum(low, np.minimum(open_arr, close))
        high = np.maximum(high, np.maximum(open_arr, close))
        volume = rng.lognormal(mean=10.0, sigma=1.0, size=n_bars)

        if interleaved:
            step_ms = 3_600_000  # 1h bars
            timestamps = np.arange(ts, ts + n_bars * step_ms, step_ms, dtype=np.int64)
        else:
            timestamps = np.full(n_bars, ts, dtype=np.int64)

        all_open.append(open_arr)
        all_high.append(high)
        all_low.append(low)
        all_close.append(close)
        all_volume.append(volume)
        all_ts.append(timestamps)
        all_sym.extend([sym] * n_bars)
        ts += 100_000_000  # offset next symbol to avoid overlap

    return {
        "open": np.concatenate(all_open),
        "high": np.concatenate(all_high),
        "low": np.concatenate(all_low),
        "close": np.concatenate(all_close),
        "volume": np.concatenate(all_volume),
        "timestamp": np.concatenate(all_ts),
        "symbol": all_sym,
    }


def make_candle(open_: float, high: float, low: float, close: float,
                volume: float = 1000.0) -> Candle:
    return Candle(open=open_, high=high, low=low, close=close, volume=volume)


# ── Profile fixtures ───────────────────────────────────────────────────


@pytest.fixture
def swing_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="acceptance-swing-1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=24,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.05,
        no_trade_default=False,
    )


@pytest.fixture
def scalp_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="acceptance-scalp-1.0.0",
        mode=TradingMode.SCALP,
        primary_interval="1h",
        max_holding_bars=12,
        stop_multiplier=1.5,
        target_multiplier=1.8,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.15,
        no_trade_default=True,
    )


@pytest.fixture
def aggressive_scalp_profile() -> SimulationProfile:
    """AGGRESSIVE_SCALP profile as specified in #304 acceptance criteria.

    Expected values:
        primary_interval = "15m"
        max_holding_bars = 5
        stop_multiplier = 1.25
        target_multiplier = 1.25
        no_trade_default = True
    """
    return SimulationProfile(
        profile_version="acceptance-aggressive-scalp-1.0.0",
        mode=TradingMode.AGGRESSIVE_SCALP,
        primary_interval="15m",
        max_holding_bars=5,
        stop_multiplier=1.25,
        target_multiplier=1.25,
        ambiguity_margin_r=0.05,
        min_action_edge_r=0.08,
        no_trade_default=True,
    )


# ── Funding event helpers ─────────────────────────────────────────────


def make_funding_events(
    timestamps: list[int],
    rates: list[float],
) -> list[FundingEvent]:
    """Build a list of FundingEvent from parallel timestamp/rate lists."""
    assert len(timestamps) == len(rates)
    return [FundingEvent(ts, r) for ts, r in zip(timestamps, rates)]


# ── Default funding fixture ────────────────────────────────────────────


@pytest.fixture
def interleaved_funding_events() -> list[FundingEvent]:
    """Funding events with both positive and negative rates, interleaved symbols.

    Returns events for BTCUSDT and ETHUSDT with different timestamps and rates.
    """
    # All timestamps in ms
    return [
        FundingEvent(1_700_000_000_000, 0.0001),   # BTC positive
        FundingEvent(1_700_003_600_000, 0.00005),  # BTC positive
        FundingEvent(1_700_007_200_000, -0.00002), # BTC negative
        FundingEvent(1_700_010_800_000, 0.0001),   # BTC positive
        FundingEvent(1_700_050_000_000, 0.00008),  # ETH positive
        FundingEvent(1_700_053_600_000, -0.00001), # ETH negative
        FundingEvent(1_700_057_200_000, 0.00003),  # ETH positive
        FundingEvent(1_700_060_800_000, 0.00006),  # ETH positive
    ]
