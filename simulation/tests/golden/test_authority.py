"""
Golden parity test for simulation authority — SCALP only.

THRESHOLD RULE: Eşik (95%) test yazilmadan ONCE belirlenmistir.
95% altindaki sonuc warning degil FAIL verir.
"""

from __future__ import annotations

import numpy as np
import pytest

from simulation.authority import (
    COST_CONSTANTS,
    generate_labels_bulk,
    get_cost_constants,
    get_profile,
    label_via_simulation,
)


ACCEPTANCE_RATE = 0.95  # PRE-set before any run — do NOT change post-hoc


def _synthetic_ohlcv(n_bars: int = 500, seed: int = 42) -> dict[str, np.ndarray]:
    rng = np.random.RandomState(seed)
    returns = rng.randn(n_bars) * 0.02
    close = 100.0 * np.exp(np.cumsum(returns))
    close = np.maximum(close, 0.01)
    noise = rng.randn(n_bars) * 0.005
    open_arr = close * (1.0 + noise * 0.3)
    high_noise = rng.uniform(0.0, 0.015, n_bars)
    low_noise = rng.uniform(0.0, 0.015, n_bars)
    high = np.maximum(open_arr, close) * (1.0 + high_noise)
    low = np.minimum(open_arr, close) * (1.0 - low_noise)
    low = np.minimum(low, np.minimum(open_arr, close))
    high = np.maximum(high, np.maximum(open_arr, close))
    return {
        "close": close.astype(np.float64),
        "high": high.astype(np.float64),
        "low": low.astype(np.float64),
        "open": open_arr.astype(np.float64),
    }


# ── Layer 1: Cost Constant Integrity ────────────────────────────────

class TestCostConstants:

    def test_taker_fee_is_4bps(self):
        assert COST_CONSTANTS["taker_fee_bps"] == 4.0

    def test_slippage_is_1bp(self):
        assert COST_CONSTANTS["slippage_bps"] == 1.0

    def test_total_round_trip_is_10bps(self):
        assert COST_CONSTANTS["total_round_trip_cost_bps"] == 10.0

    def test_constants_immutable(self):
        with pytest.raises(TypeError):
            COST_CONSTANTS["taker_fee_bps"] = 99.0


# ── Layer 2: Profile Integrity ──────────────────────────────────────

class TestProfile:

    def test_scalp_profile_exists(self):
        p = get_profile("SCALP")
        assert p.mode.value == "SCALP"
        assert p.max_holding_bars == 12
        assert p.stop_multiplier == 1.5
        assert p.target_multiplier == 1.5
        assert p.ambiguity_margin_r == 0.10
        assert p.min_action_edge_r == 0.15

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError):
            get_profile("BOGUS")

    def test_ambiguity_less_than_min_edge(self):
        p = get_profile("SCALP")
        assert p.ambiguity_margin_r < p.min_action_edge_r


# ── Layer 3: Label Parity ───────────────────────────────────────────
# THRESHOLD: 95% (pre-set). If bulk & simulation disagree on >5% of rows,
# this test FAILS — the cost model port is incomplete.

class TestLabelParity:

    N_BARS = 500

    @pytest.fixture(scope="class")
    def ohlcv(self):
        return _synthetic_ohlcv(n_bars=self.N_BARS, seed=42)

    def test_bulk_does_not_crash(self, ohlcv):
        close, high, low = ohlcv["close"], ohlcv["high"], ohlcv["low"]
        profile = get_profile("SCALP")
        result = generate_labels_bulk(close, high, low, "SCALP")
        expected = len(close) - profile.max_holding_bars - 1
        assert len(result[0]) == expected

    def test_action_agreement_meets_threshold(self, ohlcv):
        """Bulk vs simulation agreement must meet PRE-SET 95% threshold.
        
        Fails if < 95% — means the cost model port is still incomplete.
        """
        p = get_profile("SCALP")
        max_hold = p.max_holding_bars
        close, high, low = (ohlcv[k] for k in ("close", "high", "low"))

        bulk = generate_labels_bulk(close, high, low, "SCALP")
        bulk_ints = bulk[0]

        n = len(close)
        total, agree = 0, 0
        action_map = {"LONG_NOW": 0, "SHORT_NOW": 1, "NO_TRADE": 2, "AMBIGUOUS_STATE": 2}

        for i in range(n - max_hold - 1):
            entry = float(close[i])
            atr_sum = atr_cnt = 0
            for k in range(max(0, i - 14), i + 1):
                tr = (high[k] - low[k]) if k == 0 else max(
                    high[k] - low[k], abs(high[k] - close[k - 1]), abs(low[k] - close[k - 1]))
                atr_sum += tr
                atr_cnt += 1
            atr_val = atr_sum / max(atr_cnt, 1)

            future = {
                "high": high[i+1:i+1+max_hold].tolist(),
                "low": low[i+1:i+1+max_hold].tolist(),
                "close": close[i+1:i+1+max_hold].tolist(),
            }
            if not future["high"]:
                continue

            sim = label_via_simulation(
                entry, atr_val,
                future_highs=future["high"],
                future_lows=future["low"],
                future_closes=future["close"],
                mode="SCALP",
            )
            sim_int = action_map.get(sim.best_action, 2)
            total += 1
            if sim_int == int(bulk_ints[i]):
                agree += 1

        rate = agree / total if total else 1.0
        assert rate >= ACCEPTANCE_RATE, (
            f"SCALP: action agreement {agree}/{total} = {rate:.1%} "
            f"< {ACCEPTANCE_RATE:.0%} threshold. "
            f"Cost model port incomplete."
        )

    def test_xgboost_cost_not_50x_double_counted(self):
        c = get_cost_constants()
        assert c["taker_fee_bps"] == 4.0
        old_wrong = 0.04
        correct = c["taker_fee_bps"] / 10000.0
        assert old_wrong / correct > 80
        assert correct == 0.0004


# ── Edge Cases ──────────────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_data(self):
        e = np.array([], dtype=np.float64)
        for arr in generate_labels_bulk(e, e, e, "SCALP"):
            assert len(arr) == 0

    def test_too_short_data(self):
        s = np.array([100.0, 101.0], dtype=np.float64)
        for arr in generate_labels_bulk(s, s, s, "SCALP"):
            assert len(arr) == 0
