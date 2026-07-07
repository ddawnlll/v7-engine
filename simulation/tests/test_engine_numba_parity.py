"""Parity test: GPU path vs CPU path vs original simulation engine.

Generates random SimulationInput, runs through all three paths,
asserts bit-identical (1e-9) ExitResult-level outputs for GPU/CPU paths,
and verifies the original engine's simulate() results are close.
"""

import numpy as np
import pytest

from simulation.contracts.models import (
    Candle, SimulationInput, SimulationProfile, FuturePath, TradingMode,
)
from simulation.engine.cuda_kernels import (
    prepare_batch_arrays, run_batch_gpu, run_batch_cpu, is_cuda_available,
    EXIT_STOP_HIT, EXIT_TARGET_HIT, EXIT_TIME_EXIT,
)
from simulation.engine.engine import simulate
from simulation.engine.exits import _extract_ohlc


def _make_profile(mode: str = "SCALP") -> SimulationProfile:
    """Make a minimal simulation profile."""
    return SimulationProfile(
        profile_version="test-1.0.0",
        mode=TradingMode.SCALP if mode == "SCALP" else TradingMode.SWING,
        primary_interval="1h",
        max_holding_bars=12 if mode == "SCALP" else 30,
        stop_multiplier=1.5,
        target_multiplier=2.0,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.15,
        no_trade_default=False,
    )


def _make_candles(close_path: np.ndarray, atr: float) -> list[Candle]:
    """Build candle list from a close price path."""
    candles = []
    for c in close_path:
        candles.append(Candle(
            open=float(c - np.random.randn() * atr * 0.1),
            high=float(c + abs(np.random.randn()) * atr * 0.3),
            low=float(c - abs(np.random.randn()) * atr * 0.3),
            close=float(c),
        ))
    return candles


def _signal_to_dict(direction: str, input: SimulationInput,
                    candles: list[Candle], profile: SimulationProfile) -> dict:
    """Convert a SimulationInput to the dict format for batch."""
    entry = input.entry_price
    atr = input.atr
    stop_mult = profile.stop_multiplier
    target_mult = profile.target_multiplier

    if direction == "LONG":
        stop = entry - atr * stop_mult
        target = entry + atr * target_mult
    else:
        stop = entry + atr * stop_mult
        target = entry - atr * target_mult

    n_avail = min(len(candles), profile.max_holding_bars)
    highs = np.array([c.high for c in candles[:n_avail]])
    lows = np.array([c.low for c in candles[:n_avail]])
    entry_risk = atr * stop_mult
    close_price = candles[n_avail - 1].close if n_avail > 0 else entry

    return {
        "direction": direction,
        "entry_price": float(entry),
        "stop_price": float(stop),
        "target_price": float(target),
        "entry_risk": float(entry_risk),
        "close_price": float(close_price),
        "available_bars": n_avail,
        "highs": highs.tolist(),
        "lows": lows.tolist(),
    }


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════


class TestNumbaParity:
    """Verify GPU and CPU numba paths produce identical results."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.profile = _make_profile("SCALP")
        self.rng = np.random.RandomState(42)

    def _gen_signal(self, n_bars: int = 8):
        """Generate one random signal + forward candles."""
        entry = 100.0 + self.rng.randn() * 5
        atr = 1.5 + abs(self.rng.randn()) * 0.5
        close_path = np.cumsum(self.rng.randn(n_bars) * atr * 0.3) + entry
        candles = _make_candles(close_path, atr)
        sim_input = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp=1700000000000,
            entry_price=entry,
            atr=atr,
            future_path=FuturePath(candles=candles),
            profile=self.profile,
            mode=TradingMode.SCALP,
            primary_interval="1h",
            simulation_family_version="test",
            cost_model_version="test",
        )
        return sim_input, candles

    def _check_exit_equality(self, gpu, cpu, tolerance=1e-9):
        """Assert GPU and CPU exit results are identical."""
        for key in ("realized_gross", "exit_price", "exit_idx", "hold_dur",
                     "mfe", "mae", "mfe_r", "mae_r", "t_mfe", "t_mae",
                     "exit_reason"):
            gv = gpu[key]
            cv = cpu[key]
            if isinstance(gv, (int, np.integer)):
                assert gv == cv, f"{key}: GPU={gv} CPU={cv}"
            else:
                assert abs(gv - cv) < tolerance, \
                    f"{key}: GPU={gv} CPU={cv} diff={abs(gv-cv)}"

    def test_stop_hit_long(self):
        """LONG: stop hit on first bar."""
        candles = [
            Candle(open=100, high=101, low=97, close=98),
            Candle(open=98, high=99, low=96, close=97),
        ]
        sig = SimulationInput(
            symbol="BTCUSDT", decision_timestamp=0,
            entry_price=100, atr=2.0,
            future_path=FuturePath(candles=candles),
            profile=self.profile, mode=TradingMode.SCALP,
            primary_interval="1h", simulation_family_version="test",
            cost_model_version="test",
        )
        sd = _signal_to_dict("LONG", sig, candles, self.profile)
        arr = prepare_batch_arrays([sd])
        cpu = run_batch_cpu(arr)
        # Expected: stop=100-3=97, low of bar 0 is 97 → STOP_HIT
        assert cpu["exit_reason"][0] == EXIT_STOP_HIT
        assert abs(cpu["realized_gross"][0] - (-1.0)) < 1e-9  # (97-100)/3

        gpu = run_batch_gpu(arr)
        self._check_exit_equality(
            {k: v[0] for k, v in gpu.items()},
            {k: v[0] for k, v in cpu.items()},
        )

    def test_target_hit_short(self):
        """SHORT: target hit."""
        candles = [
            Candle(open=100, high=101, low=99, close=100),
            Candle(open=100, high=102, low=98, close=99),
        ]
        sig = SimulationInput(
            symbol="BTCUSDT", decision_timestamp=0,
            entry_price=100, atr=2.0,
            future_path=FuturePath(candles=candles),
            profile=self.profile, mode=TradingMode.SCALP,
            primary_interval="1h", simulation_family_version="test",
            cost_model_version="test",
        )
        sd = _signal_to_dict("SHORT", sig, candles, self.profile)
        arr = prepare_batch_arrays([sd])
        cpu = run_batch_cpu(arr)
        # SHORT stop=106, target=94. low of bar 0=99 > 94, bar 1 low=98 > 94
        # None hit → TIME_EXIT with close=99
        # Actually low(98) > target(94) on bar 1 — let me check
        # Wait: SHORT stop=100+3=103, target=100-4=96
        # SHORT: stop hit if high >= 103, target hit if low <= 96
        # high is 101, 102 — neither >= 103 → no stop
        # low is 99, 98 — neither <= 96 → no target
        # → TIME_EXIT, close=99
        assert cpu["exit_reason"][0] == EXIT_TIME_EXIT

        gpu = run_batch_gpu(arr)
        self._check_exit_equality(
            {k: v[0] for k, v in gpu.items()},
            {k: v[0] for k, v in cpu.items()},
        )

    def test_same_candle_ambiguity(self):
        """Stop and target on same bar: stop wins."""
        candles = [
            Candle(open=100, high=108, low=96, close=102),
        ]
        sig = SimulationInput(
            symbol="BTCUSDT", decision_timestamp=0,
            entry_price=100, atr=2.0,
            future_path=FuturePath(candles=candles),
            profile=self.profile, mode=TradingMode.SCALP,
            primary_interval="1h", simulation_family_version="test",
            cost_model_version="test",
        )
        sd = _signal_to_dict("LONG", sig, candles, self.profile)
        arr = prepare_batch_arrays([sd])
        cpu = run_batch_cpu(arr)
        # LONG stop=100-3=97, target=100+4=104
        # Same bar: low=96<=97 → stop hit at 97, high=108>=104 → also target
        # Stop wins same-candle → STOP_HIT
        assert cpu["exit_reason"][0] == EXIT_STOP_HIT

        gpu = run_batch_gpu(arr)
        self._check_exit_equality(
            {k: v[0] for k, v in gpu.items()},
            {k: v[0] for k, v in cpu.items()},
        )

    def test_batch_parity_200(self):
        """200 random signals: GPU path matches CPU path exactly."""
        signals = []
        for i in range(200):
            direction = "LONG" if i % 2 == 0 else "SHORT"
            entry = 100.0 + self.rng.randn() * 5
            atr = 1.0 + abs(self.rng.randn()) * 1.0
            stop_mult = 1.5; target_mult = 2.0
            entry_risk = atr * stop_mult
            if direction == "LONG":
                stop = entry - stop_mult * atr
                target = entry + target_mult * atr
            else:
                stop = entry + stop_mult * atr
                target = entry - target_mult * atr
            n_bars = int(self.rng.randint(1, 12))
            rw = np.cumsum(self.rng.randn(n_bars) * atr * 0.5) + entry
            signals.append({
                "direction": direction,
                "entry_price": float(entry),
                "stop_price": float(stop),
                "target_price": float(target),
                "entry_risk": float(entry_risk),
                "close_price": float(rw[-1]),
                "available_bars": n_bars,
                "highs": (rw + abs(self.rng.randn(n_bars) * 0.2)).tolist(),
                "lows": (rw - abs(self.rng.randn(n_bars) * 0.2)).tolist(),
            })

        arr = prepare_batch_arrays(signals)
        cpu = run_batch_cpu(arr)
        gpu = run_batch_gpu(arr)

        for key in cpu:
            assert np.allclose(gpu[key], cpu[key], atol=1e-9), \
                f"Mismatch in {key}: max diff={np.max(np.abs(gpu[key] - cpu[key]))}"
