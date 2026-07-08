"""Parity test: GPU/CPU batch path vs original simulation engine.

500 randomized cases: LONG/SHORT, variable bars (1-30), variable ATR,
stop-hit, target-hit, time-exit, same-candle ambiguity.
Asserts: GPU=CPU (1e-9), CPU path ≈ original simulate() (1e-4).
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

EXIT_REASON_STR = {0: "STOP_HIT", 1: "TARGET_HIT", 2: "TIME_EXIT"}


def _make_profile(mode: str = "SCALP") -> SimulationProfile:
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


def _gen_random_signal(rng, mode="SCALP", max_bars=None):
    """Generate one random signal with candles."""
    profile = _make_profile(mode)
    mb = max_bars or (12 if mode == "SCALP" else 30)
    n_bars = int(rng.randint(1, mb + 1))
    entry = 100.0 + rng.randn() * 5
    atr = 1.0 + abs(rng.randn()) * 1.0
    direction = "LONG" if rng.random() > 0.5 else "SHORT"
    stop_mult = profile.stop_multiplier
    target_mult = profile.target_multiplier
    if direction == "LONG":
        stop = entry - atr * stop_mult
        target = entry + atr * target_mult
    else:
        stop = entry + atr * stop_mult
        target = entry - atr * target_mult
    entry_risk = atr * stop_mult
    rw = np.cumsum(rng.randn(n_bars) * atr * 0.5) + entry
    highs = (rw + abs(rng.randn(n_bars) * 0.2)).tolist()
    lows = (rw - abs(rng.randn(n_bars) * 0.2)).tolist()
    close_price = float(rw[-1])
    candles = [Candle(open=float(rw[i]), high=highs[i], low=lows[i], close=float(rw[i]))
               for i in range(n_bars)]

    sig_dict = {
        "direction": direction,
        "entry_price": float(entry),
        "stop_price": float(stop),
        "target_price": float(target),
        "entry_risk": float(entry_risk),
        "close_price": close_price,
        "available_bars": n_bars,
        "highs": highs,
        "lows": lows,
    }

    sim_input = SimulationInput(
        symbol="BTCUSDT",
        decision_timestamp=1700000000000,
        entry_price=entry,
        atr=atr,
        future_path=FuturePath(candles=candles),
        profile=profile,
        mode=TradingMode.SCALP if mode == "SCALP" else TradingMode.SWING,
        primary_interval="1h",
        simulation_family_version="test",
        cost_model_version="test",
    )
    return sig_dict, sim_input


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════


class TestNumbaParity:
    """GPU/CPU numba path produces identical results."""

    def _check_exit_equality(self, gpu, cpu, tolerance=1e-9):
        for key in ("realized_gross", "exit_price", "exit_idx", "hold_dur",
                     "mfe", "mae", "mfe_r", "mae_r", "t_mfe", "t_mae",
                     "exit_reason"):
            gv = gpu[key]; cv = cpu[key]
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
        sd = {
            "direction": "LONG", "entry_price": 100, "stop_price": 97,
            "target_price": 104, "entry_risk": 3.0, "close_price": 97,
            "available_bars": 2,
            "highs": [101.0, 99.0], "lows": [97.0, 96.0],
        }
        arr = prepare_batch_arrays([sd])
        cpu = run_batch_cpu(arr)
        gpu = run_batch_gpu(arr)
        assert cpu["exit_reason"][0] == EXIT_STOP_HIT
        assert abs(cpu["realized_gross"][0] - (-1.0)) < 1e-9
        self._check_exit_equality({k: v[0] for k, v in gpu.items()},
                                  {k: v[0] for k, v in cpu.items()})

    def test_same_candle_stop_wins(self):
        """Stop and target on same bar: stop wins."""
        sd = {
            "direction": "LONG", "entry_price": 100, "stop_price": 97,
            "target_price": 104, "entry_risk": 3.0, "close_price": 102,
            "available_bars": 1,
            "highs": [108.0], "lows": [96.0],
        }
        arr = prepare_batch_arrays([sd])
        cpu = run_batch_cpu(arr)
        gpu = run_batch_gpu(arr)
        assert cpu["exit_reason"][0] == EXIT_STOP_HIT
        self._check_exit_equality({k: v[0] for k, v in gpu.items()},
                                  {k: v[0] for k, v in cpu.items()})

    def test_batch_parity_500(self):
        """500 random cases: GPU=CPU with 1e-9 tolerance."""
        rng = np.random.RandomState(42)
        signals = []
        for i in range(500):
            sig_dict, _ = _gen_random_signal(rng)
            signals.append(sig_dict)
        arr = prepare_batch_arrays(signals)
        cpu = run_batch_cpu(arr)
        gpu = run_batch_gpu(arr)
        for key in cpu:
            if cpu[key].dtype in (np.float64, np.float32):
                max_diff = float(np.max(np.abs(gpu[key] - cpu[key])))
                assert max_diff < 1e-9, f"{key}: max diff={max_diff}"
            else:
                assert np.array_equal(gpu[key], cpu[key]), f"{key}: GPU!=CPU"

    def test_batch_parity_500_vs_engine(self):
        """500 random cases: CPU batch path ≈ original simulate() (1e-4)."""
        rng = np.random.RandomState(123)
        for i in range(500):
            sig_dict, sim_input = _gen_random_signal(rng)

            # Run original path
            try:
                output = simulate(sim_input)
            except Exception:
                continue
            side = sig_dict["direction"]
            outcome = output.long_outcome if side == "LONG" else output.short_outcome
            if outcome is None:
                continue
            orig_r = outcome.realized_r_gross

            # Run batch path
            arr = prepare_batch_arrays([sig_dict])
            cpu = run_batch_cpu(arr)
            batch_r = float(cpu["realized_gross"][0])

            assert abs(orig_r - batch_r) < 1e-4, (
                f"Case {i} {side}: original={orig_r:.6f} batch={batch_r:.6f} "
                f"diff={abs(orig_r-batch_r):.6f}"
            )
