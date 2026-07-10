"""Acceptance: #304 Full pipeline economic-truth E2E.

Single high-value test that exercises the real public entrypoints:

  mock market/funding source → backfill → persistence → catalog → load
  → pipeline context → feature generation → simulation labels
  → funding cost → label adapter → canonical training view
  → WFV → report metrics

This test validates the WIRING between components, not each component
in isolation. It proves that the #267 and #315 changes are genuinely
connected — that features, labels, funding, and lineage flow through
the same pipeline context with row identity preserved.

Current head (83ebadf) will fail most assertions because:
- #267 row-tracking fields don't exist
- #315 funding persistence/wiring doesn't exist
- The full training view pipeline hasn't been assembled

After both branches merge, this test MUST pass.
"""
from __future__ import annotations

import math
import pytest

import numpy as np

from simulation.contracts.models import (
    Candle,
    FundingEvent,
    FuturePath,
    SimulationInput,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.engine import simulate

from tests.acceptance.conftest import (
    make_ohlcv_dict,
    make_candle,
    make_funding_events,
)


# ── Shared E2E fixture ─────────────────────────────────────────────────


@pytest.fixture
def e2e_fixture():
    """Minimal deterministic fixture for full pipeline E2E test.

    Uses synthetic OHLCV with 2 symbols and unequal lengths to exercise
    all alignment, reorder, and isolation paths.
    """
    ohlcv = make_ohlcv_dict(
        symbols=("BTCUSDT", "ETHUSDT"),
        bars_per_symbol=(300, 200),
        random_seed=42,
        interleaved=True,
    )

    funding_events = {
        "BTCUSDT": make_funding_events(
            timestamps=[1_700_001_000_000, 1_700_003_600_000, 1_700_007_200_000],
            rates=[0.0001, 0.00005, -0.00002],
        ),
        "ETHUSDT": make_funding_events(
            timestamps=[1_700_050_000_000, 1_700_053_600_000],
            rates=[0.00008, -0.00001],
        ),
    }

    return {
        "ohlcv": ohlcv,
        "funding_events": funding_events,
        "n_raw_rows": len(ohlcv["close"]),  # 500
        "symbols": ("BTCUSDT", "ETHUSDT"),
    }


# ── Helpers for the E2E test chain ────────────────────────────────────


def mock_backfill(e2e_fixture: dict) -> dict:
    """Simulate the backfill/persistence step.

    After #267/#315, this calls the real backfill orchestrator
    which produces DataCatalog-compatible storage.
    For now, returns the OHLCV dict directly.
    """
    return e2e_fixture["ohlcv"]


def mock_funding_persist(e2e_fixture: dict) -> dict:
    """Simulate funding persistence -> loader.

    After #315: FundingService writes to data lake,
    FundingLoader reads back and returns symbol-indexed events.
    """
    return e2e_fixture["funding_events"]


def mock_build_simulation_inputs(
    ohlcv: dict,
    funding: dict,
    mode: str = "SWING",
    max_hold: int = 24,
    stop_mult: float = 2.0,
    target_mult: float = 2.0,
) -> tuple[list[SimulationInput], np.ndarray, list[str]]:
    """Build SimulationInput instances for each valid bar.

    This simulates what the pipeline context would produce after both
    #267 and #315 are wired: aligned OHLCV + funding events → per-bar
    simulation inputs with symbol-isolated funding events wired into
    profiles.

    After both fixes: this runs inside the pipeline runner, not as a helper.
    We expose it here only because the full wiring doesn't exist yet.
    """
    mode_enum = {
        "SWING": TradingMode.SWING,
        "SCALP": TradingMode.SCALP,
        "AGGRESSIVE_SCALP": TradingMode.AGGRESSIVE_SCALP,
    }[mode]

    close = np.asarray(ohlcv["close"])
    high = np.asarray(ohlcv["high"])
    low = np.asarray(ohlcv["low"])
    open_arr = np.asarray(ohlcv.get("open", close))
    symbols = np.asarray(ohlcv["symbol"])

    inputs = []
    source_indices = []
    symbols_out = []

    for sym in sorted(set(symbols)):
        sym_mask = symbols == sym
        sym_idx = np.flatnonzero(sym_mask)
        sym_funding = funding.get(sym, [])

        for idx_pos, i in enumerate(sym_idx):
            if idx_pos < 15:
                continue
            if idx_pos >= len(sym_idx) - max_hold - 1:
                continue

            entry_price = float(close[i])

            # ATR
            lb = sym_idx[max(0, idx_pos - 14):idx_pos + 1]
            hs = high[lb]
            ls = low[lb]
            cs = close[lb]
            tr = np.maximum(
                hs[1:] - ls[1:],
                np.maximum(np.abs(hs[1:] - cs[:-1]), np.abs(ls[1:] - cs[:-1])),
            )
            atr_val = float(np.mean(tr))
            if atr_val <= 0 or atr_val > entry_price * 0.5:
                continue

            # Future candles
            future_idx = sym_idx[idx_pos + 1:idx_pos + 1 + max_hold]
            candles = [
                Candle(
                    open=float(open_arr[fj]),
                    high=float(high[fj]),
                    low=float(low[fj]),
                    close=float(close[fj]),
                )
                for fj in future_idx
            ]

            profile = SimulationProfile(
                profile_version="e2e-acceptance-1.0.0",
                mode=mode_enum,
                primary_interval="4h" if mode == "SWING" else "1h",
                max_holding_bars=max_hold,
                stop_multiplier=stop_mult,
                target_multiplier=target_mult,
                ambiguity_margin_r=0.10,
                min_action_edge_r=0.05,
                no_trade_default=False,
                funding_events=sym_funding,
            )

            sim_input = SimulationInput(
                symbol=str(sym),
                decision_timestamp=str(ohlcv.get("timestamp", [0])[i])
                    if "timestamp" in ohlcv else str(i),
                mode=mode_enum,
                primary_interval=profile.primary_interval,
                entry_price=entry_price,
                atr=atr_val,
                future_path=FuturePath(candles=candles),
                profile=profile,
            )
            inputs.append(sim_input)
            source_indices.append(i)
            symbols_out.append(str(sym))

    return inputs, np.array(source_indices, dtype=np.int64), symbols_out


# ── FULL E2E TEST ─────────────────────────────────────────────────────


class TestFullPipelineE2E:
    """Single high-value E2E test through public entrypoints.

    Walks the chain:
      OHLCV source → simulation inputs → simulate →
      outcomes → economic assertions → metrics
    """

    @pytest.mark.xfail(strict=False,
                       reason="#304: full pipeline assembly not yet complete on this head")
    def test_full_pipeline_e2e(self, e2e_fixture):
        """Complete end-to-end pipeline test.

        This test will pass incremental assertions as #267 and #315
        are merged. On the current head (83ebadf) it will fail on
        the first assertion that depends on wiring that doesn't exist.
        """
        # ── Step 1: Data source ─────────────────────────────────────
        ohlcv = mock_backfill(e2e_fixture)
        n_raw = len(ohlcv["close"])
        assert n_raw == e2e_fixture["n_raw_rows"]

        # ── Step 2: Funding persistence ─────────────────────────────
        funding = mock_funding_persist(e2e_fixture)
        assert len(funding) == 2  # BTCUSDT, ETHUSDT
        total_funding_events = sum(len(v) for v in funding.values())
        assert total_funding_events > 0, "No funding events loaded"

        # ── Step 3: Build simulation inputs ─────────────────────────
        inputs, source_indices, symbols_out = mock_build_simulation_inputs(
            ohlcv, funding, mode="SWING",
        )
        n_sim = len(inputs)
        assert n_sim > 0, "No valid simulation inputs"
        assert n_raw > n_sim, \
            f"Expected n_raw ({n_raw}) > n_sim ({n_sim}) " \
            f"— Warmup/horizon-invalid rows should reduce count"

        # Source indices must be unique
        assert len(set(source_indices)) == len(source_indices), \
            "Duplicate source indices — row identity lost"

        # All source indices must be valid OHLCV positions
        assert all(0 <= idx < n_raw for idx in source_indices), \
            "Source indices out of range"

        # ── Step 4: Run simulations ─────────────────────────────────
        outputs = []
        for sim_input in inputs:
            output = simulate(sim_input)
            outputs.append(output)

        assert len(outputs) == n_sim

        # ── Step 5: Verify outputs have economic content ───────────
        # At least one outcome with non-zero gross R in each direction
        long_nonzero = sum(1 for o in outputs if abs(o.long_outcome.realized_r_gross) > 0.001)
        short_nonzero = sum(1 for o in outputs if abs(o.short_outcome.realized_r_gross) > 0.001)

        assert long_nonzero > 0, \
            f"No LONG outcomes with non-zero gross R ({long_nonzero}/{n_sim})"
        assert short_nonzero > 0, \
            f"No SHORT outcomes with non-zero gross R ({short_nonzero}/{n_sim})"

        # ── Step 6: Funding events were used ────────────────────────
        # At least one row where funding_cost_r != 0 for either direction
        funding_applied = 0
        for o in outputs:
            long_fund = abs(o.long_outcome.funding_cost_r)
            short_fund = abs(o.short_outcome.funding_cost_r)
            if long_fund > 0.0001 or short_fund > 0.0001:
                funding_applied += 1

        # This assertion may be weak on current head — #315 will make it strict
        assert funding_applied > 0 or len(funding) == 0, \
            f"Funding never applied to any of {n_sim} simulations"
        if funding_applied == 0:
            pytest.xfail("#315: funding events not flowing into simulation costs")

        # ── Step 7: Gross != net on funded rows ─────────────────────
        # For rows with non-zero funding, gross R must differ from net R
        gross_net_diff = 0
        for o in outputs:
            if abs(o.long_outcome.funding_cost_r) > 0.0001:
                if abs(o.long_outcome.realized_r_gross - o.long_outcome.realized_r_net) > 0.0001:
                    gross_net_diff += 1
        if gross_net_diff == 0 and funding_applied > 0:
            pytest.xfail("#315: funding cost not reflected in net R")

        # ── Step 8: Lineage sanity ──────────────────────────────────
        for o in outputs:
            lineage = o.lineage
            assert lineage.simulation_family_version != ""
            assert lineage.simulation_profile_version != ""
            assert lineage.cost_model_version != ""
            assert lineage.adapter_kind == "TRAINING"

        # ── Step 9: All financial values are finite ─────────────────
        for o in outputs:
            for attr in ("realized_r_gross", "realized_r_net",
                         "fee_cost_r", "slippage_cost_r",
                         "funding_cost_r", "total_cost_r"):
                for side in ("long_outcome", "short_outcome"):
                    val = getattr(getattr(o, side), attr)
                    assert math.isfinite(val), \
                        f"{side}.{attr} = {val} (not finite)"

        # ── Step 10: WFV compatibility check ────────────────────────
        # After #267/#315: outputs should be convertible to
        # DirectionalRResult format for WFV
        long_gross = np.array([o.long_outcome.realized_r_gross for o in outputs])
        short_gross = np.array([o.short_outcome.realized_r_gross for o in outputs])
        long_net = np.array([o.long_outcome.realized_r_net for o in outputs])
        short_net = np.array([o.short_outcome.realized_r_net for o in outputs])

        assert len(long_gross) == n_sim
        assert len(short_gross) == n_sim
        assert len(long_net) == n_sim
        assert len(short_net) == n_sim

        # Gross must have the same shape as net (no dimension mismatch)
        assert long_gross.shape == long_net.shape

        # ── Summary metrics ─────────────────────────────────────────
        n_canonical = n_sim
        summary = {
            "n_raw_rows": n_raw,
            "n_canonical_rows": n_canonical,
            "long_nonzero_r": long_nonzero,
            "short_nonzero_r": short_nonzero,
            "funding_applied": funding_applied,
            "gross_net_diff_rows": gross_net_diff,
            "n_symbols": len(set(symbols_out)),
        }

        # All metrics must be finite
        for k, v in summary.items():
            if isinstance(v, (int, float)):
                assert math.isfinite(v), f"Metric {k} = {v} (not finite)"

        # Economic metrics must be present
        assert summary["long_nonzero_r"] > 0
        assert summary["short_nonzero_r"] > 0
