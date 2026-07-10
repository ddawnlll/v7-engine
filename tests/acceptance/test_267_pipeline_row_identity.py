"""Acceptance: #267 Pipeline row identity and canonical alignment.

Tests that the walk-forward validation pipeline preserves row identity
through all transformations: NaN filtering, chronological reorder,
and feature/label alignment.

Current head (83ebadf) has known alignment bugs:
- Row identity not tracked (no source_row_indices)
- label_valid_mask absent → invalid rows silently merged
- Chronological reorder not propagated to all arrays
- AGGRESSIVE_SCALP profile values may deviate

These tests use xfail(strict=True) until #267 production commits are merged.
"""
from __future__ import annotations

import numpy as np
import pytest

from alphaforge.validation.walk_forward_runner import (
    generate_directional_r_from_ohlcv,
    generate_walk_forward_ohlcv,
    validate_aligned_lengths,
    DirectionalRResult,
)
from simulation.contracts.models import TradingMode, FundingEvent

from tests.acceptance.conftest import make_ohlcv_dict


# ── Test 1: Dataset arrays have equal length ───────────────────────────


class TestRowIdentity:
    """Row identity preservation through the WFV pipeline."""

    def test_ohlcv_arrays_equal_length(self):
        """All OHLCV arrays in the data dict must have equal length.

        This is a precondition for any pipeline alignment claim.
        """
        data = make_ohlcv_dict()
        n = len(data["close"])
        assert len(data["open"]) == n
        assert len(data["high"]) == n
        assert len(data["low"]) == n
        assert len(data["volume"]) == n
        assert len(data["timestamp"]) == n
        assert len(data["symbol"]) == n

    @pytest.mark.xfail(strict=True, reason="#267: source_row_indices not yet tracked")
    def test_current_head_missing_row_indices(self):
        """The current head does NOT expose source_row_indices.

        After #267, generate_directional_r_from_ohlcv should return
        source_row_indices mapping each output row to its original
        OHLCV position.
        """
        data = make_ohlcv_dict(bars_per_symbol=200)
        result = generate_directional_r_from_ohlcv(data, mode="SWING")

        # The DirectionalRResult should have source_row_indices
        assert hasattr(result, "source_row_indices"), \
            "Missing source_row_indices — #267 must add this"
        assert len(result.source_row_indices) == len(result.long_gross_r)

    @pytest.mark.xfail(strict=True, reason="#267: row identity scrambled by NaN mask")
    def test_row_identity_preserved_through_nan_filter(self):
        """Output rows must map back to unique original input rows.

        Feature warmup causes NaN rows at the start of each symbol.
        After NaN filtering, each surviving row's source index must
        point to its original OHLCV position, proving no intra-symbol
        shift or reorder beyond the NaN drop.
        """
        data = make_ohlcv_dict(symbols=("BTCUSDT", "ETHUSDT"), bars_per_symbol=(150, 200))
        result = generate_directional_r_from_ohlcv(data, mode="SWING")

        # Simulate what source_row_indices would look like after #267
        # Current: no such field — test expected to fail
        try:
            indices = result.source_row_indices  # type: ignore[attr-defined]
        except AttributeError:
            pytest.xfail("#267: source_row_indices not yet implemented")

        # Every index must be unique (no duplicate source rows)
        assert len(set(indices)) == len(indices), \
            "Duplicate source_row_indices — row identity lost"
        # All indices must be valid OHLCV positions
        assert all(0 <= idx < len(data["close"]) for idx in indices), \
            "source_row_indices out of range"

    @pytest.mark.xfail(strict=True,
                       reason="#267: WFV output labels length != source rows")
    def test_labels_aligned_with_wfv_output(self):
        """After #267: WFV output arrays must align with source OHLCV
        in terms of row identity, not just length. This test proves the
        current WFV output loses row count parity with input.

        generate_directional_r_from_ohlcv only processes bars with enough
        lookback+future room, so its output is shorter than input. After
        #267, the output must carry source_row_indices proving which
        source rows survived.
        """
        data = make_ohlcv_dict(bars_per_symbol=100)
        n_source = len(data["close"])

        result = generate_directional_r_from_ohlcv(data, mode="SWING")
        n_output = len(result.long_gross_r)

        # Current: output is shorter (good) but no row tracking (bad)
        assert n_output < n_source, \
            "Expected fewer output rows than input (lookback/horizon drop)"
        assert hasattr(result, "source_row_indices"), \
            "Missing source_row_indices — cannot prove row identity"


# ── Test 2: Canonical mask composition ──────────────────────────────────


class TestCanonicalMask:
    """Feature and label valid masks combine into a single canonical mask."""

    @pytest.mark.xfail(strict=True, reason="#267: label_valid_mask not yet implemented")
    def test_label_valid_mask_present(self):
        """label_valid_mask must be exposed by the pipeline.

        This mask flags rows with valid label computation results.
        """
        data = make_ohlcv_dict(bars_per_symbol=100)
        result = generate_directional_r_from_ohlcv(data, mode="SWING")

        assert hasattr(result, "label_valid_mask"), \
            "Missing label_valid_mask — #267 must add this"

    @pytest.mark.xfail(strict=True, reason="#267: label_valid_mask not yet implemented")
    def test_label_status_present(self):
        """label_status must indicate why rows are valid/invalid.

        Values: 'VALID', 'LOOKBACK_INVALID', 'HORIZON_INVALID',
        'FEATURE_NAN', 'SIMULATION_ERROR', 'NO_TRADE'.
        """
        data = make_ohlcv_dict(bars_per_symbol=100)
        result = generate_directional_r_from_ohlcv(data, mode="SWING")

        assert hasattr(result, "label_status"), \
            "Missing label_status — #267 must add this"
        statuses = result.label_status  # type: ignore[attr-defined]
        assert len(statuses) == len(result.long_gross_r)
        valid_statuses = {"VALID", "LOOKBACK_INVALID", "HORIZON_INVALID",
                          "SIMULATION_ERROR", "NO_TRADE"}
        invalid = set(statuses) - valid_statuses
        assert not invalid, f"Unexpected status values: {invalid}"

    @pytest.mark.xfail(strict=True, reason="#267: feature warmup NaN rows not tracked in mask")
    def test_feature_nan_rows_masked_not_silently_skipped(self):
        """Feature warmup NaN rows must be tracked, not silently dropped.

        After #267: the first bars of each symbol (feature warmup) cause
        NaN features, but these rows must still be present in output
        arrays with FEATURE_NAN status — not silently removed from the
        compact representation.
        """
        data = make_ohlcv_dict(symbols=("BTCUSDT",), bars_per_symbol=50)
        result = generate_directional_r_from_ohlcv(data, mode="SWING")

        # If rows were silently dropped (current): len < total bars
        # After #267: all rows present, some with FEATURE_NAN status
        assert hasattr(result, "feature_valid_mask"), \
            "Missing feature_valid_mask — #267 must add this"
        fv_mask = result.feature_valid_mask  # type: ignore[attr-defined]
        lv_mask = getattr(result, "label_valid_mask",
                          np.ones_like(fv_mask, dtype=bool))

        # Canonical mask = both valid
        canonical = fv_mask & lv_mask
        assert len(canonical) == len(data["close"]), \
            "Canonical mask length must match source"


# ── Test 3: Chronological reorder ──────────────────────────────────────


class TestChronologicalReorder:
    """All aligned arrays must share the same chronological permutation."""

    @pytest.mark.xfail(strict=True, reason="#267: chronological reorder not propagated")
    def test_reorder_preserves_columnar_alignment(self):
        """After chronological reorder, all per-row fields must share the
        same permutation, preserving the (feature, label, timestamp, symbol,
        gross_r, net_r) tuple identity.
        """
        data = make_ohlcv_dict(
            symbols=("BTCUSDT", "ETHUSDT"),
            bars_per_symbol=(100, 120),
            interleaved=True,
        )
        result = generate_directional_r_from_ohlcv(data, mode="SWING")

        # After #267: the WFV runner must return arrays that are all
        # sorted by (timestamp, symbol) in lockstep, not independently.
        # On this head, labels and features may get different orderings.

        # The reorder indicator would be a sort_index or similar
        assert hasattr(result, "sort_index"), \
            "Missing sort_index — chronological reorder tracking absent"

    @pytest.mark.xfail(strict=True, reason="#267: symbol/timestamp reorder not tracked")
    def test_symbol_timestamp_pairs_well_formed(self):
        """Every output row must have a canonical (symbol, timestamp) pair
        that maps back to exactly one input row.

        Chronological reorder must preserve (timestamp, symbol, feature, label)
        tuples as atomic units — not sort symbols and timestamps independently.
        """
        data = make_ohlcv_dict(
            symbols=("BTCUSDT",),
            bars_per_symbol=200,
            interleaved=False,  # all same timestamp → stable order
        )
        result = generate_directional_r_from_ohlcv(data, mode="SWING")

        # Without row identity: no way to verify atomicity
        assert hasattr(result, "source_row_indices"), (
            "Cannot verify reorder atomicity without source_row_indices"
        )


# ── Test 4: Multi-symbol with unequal lengths ───────────────────────────


class TestMultiSymbolAlignment:
    """Unequal symbol lengths must be supported."""

    def test_unequal_symbol_lengths_produce_output(self):
        """The engine must not crash when symbols have different bar counts."""
        data = make_ohlcv_dict(
            symbols=("BTCUSDT", "ETHUSDT"),
            bars_per_symbol=(200, 150),
        )
        result = generate_directional_r_from_ohlcv(data, mode="SWING")

        assert isinstance(result, DirectionalRResult)
        assert len(result.long_gross_r) > 0
        assert len(result.short_gross_r) > 0

    @pytest.mark.xfail(strict=True, reason="#267: symbol filter not tracked in output")
    def test_output_contains_correct_symbol_mapping(self):
        """Each output row must be traceable to its original symbol.

        After #267: the result must contain a 'symbol' array aligned
        with all other output arrays so we can verify cross-symbol
        isolation.
        """
        data = make_ohlcv_dict(
            symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
            bars_per_symbol=(100, 150, 80),
        )
        result = generate_directional_r_from_ohlcv(data, mode="SWING")

        assert hasattr(result, "symbol"), \
            "Missing output symbol array — #267 must add this"
        symbols_arr = result.symbol  # type: ignore[attr-defined]
        assert len(symbols_arr) == len(result.long_gross_r)
        # All three symbols must be represented
        assert "BTCUSDT" in symbols_arr
        assert "ETHUSDT" in symbols_arr
        assert "SOLUSDT" in symbols_arr

    @pytest.mark.xfail(strict=True, reason="#267: label arrays not length-tracked per symbol")
    def test_label_valid_mask_respects_symbol_boundaries(self):
        """Label validity must respect per-symbol lookback/horizon.

        The first N bars of each symbol are lookback-invalid, and the
        last M bars are horizon-invalid. These invalid ranges must be
        per-symbol, not global — a shorter symbol's valid region differs
        from a longer symbol's valid region.
        """
        data = make_ohlcv_dict(
            symbols=("BTCUSDT", "ETHUSDT"),
            bars_per_symbol=(200, 50),  # ETH only 50 bars total
        )
        result = generate_directional_r_from_ohlcv(data, mode="SWING")

        # After #267: each symbol's valid range is determined independently
        assert hasattr(result, "label_valid_mask"), \
            "Missing label_valid_mask — cannot verify per-symbol boundaries"


# ── Test 5: AGGRESSIVE_SCALP profile authority ─────────────────────────


class TestAggressiveScalpProfile:
    """AGGRESSIVE_SCALP mode must use correct authority values.

    Expected:
        primary_interval = "15m"
        max_holding_bars = 5
        stop_multiplier = 1.25
        target_multiplier = 1.25
        no_trade_default = True
    """

    def test_aggressive_scalp_profile_fixture_values(self, aggressive_scalp_profile):
        """Fixture must carry the correct authority values."""
        profile = aggressive_scalp_profile
        assert profile.primary_interval == "15m", \
            f"Expected 15m, got {profile.primary_interval}"
        assert profile.max_holding_bars == 5, \
            f"Expected 5, got {profile.max_holding_bars}"
        assert profile.stop_multiplier == 1.25, \
            f"Expected 1.25, got {profile.stop_multiplier}"
        assert profile.target_multiplier == 1.25, \
            f"Expected 1.25, got {profile.target_multiplier}"
        assert profile.no_trade_default is True, \
            f"Expected True, got {profile.no_trade_default}"

    @pytest.mark.xfail(strict=True, reason="#267: WFV runner may use wrong AGGRESSIVE_SCALP params")
    def test_wfv_runner_aggressive_scalp_params(self):
        """generate_directional_r_from_ohlcv must use correct AGGRESSIVE_SCALP
        parameters: max_hold=5, stop_mult=1.25, target_mult=1.25.
        """
        from alphaforge.validation.walk_forward_runner import MODE_RUNNER_TRIPLE_BARRIER

        params = MODE_RUNNER_TRIPLE_BARRIER.get("AGGRESSIVE_SCALP", {})
        assert params.get("max_hold") == 5, \
            f"max_hold: expected 5, got {params.get('max_hold')}"
        assert params.get("stop_mult") == 1.25, \
            f"stop_mult: expected 1.25, got {params.get('stop_mult')}"
        assert params.get("target_mult") == 1.25, \
            f"target_mult: expected 1.25, got {params.get('target_mult')}"
        assert params.get("no_trade_default", False) is True, \
            f"no_trade_default: expected True, got {params.get('no_trade_default')}"

    @pytest.mark.xfail(strict=True,
                       reason="#315: funding_events not wired into SimulationProfile from pipeline")
    def test_aggressive_scalp_wires_funding_events(self):
        """AGGRESSIVE_SCALP profile must wire funding_events from the
        data lake into SimulationProfile.funding_events so that the
        engine uses event-based funding (not scalar approximation).

        This test PROVES the wiring is broken: it passes funding_events
        to the engine but the engine does not respect them because
        the pipeline context (which wires funding data into profiles)
        does not exist yet.
        """
        from simulation.engine.engine import simulate
        from simulation.contracts.models import SimulationProfile, TradingMode, \
            SimulationInput, FuturePath
        from tests.acceptance.conftest import make_candle

        profile = SimulationProfile(
            profile_version="test",
            mode=TradingMode.AGGRESSIVE_SCALP,
            primary_interval="15m",
            max_holding_bars=5,
            stop_multiplier=1.25,
            target_multiplier=1.25,
            ambiguity_margin_r=0.05,
            min_action_edge_r=0.08,
            no_trade_default=True,
            funding_events=[FundingEvent(1_700_001_000_000, 0.0001)],
            funding_rate=0.0,
        )
        candles = [make_candle(101, 105, 99, 103) for _ in range(5)]
        inp = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.AGGRESSIVE_SCALP,
            primary_interval="15m",
            entry_price=100,
            atr=2.0,
            future_path=FuturePath(candles=candles),
            profile=profile,
        )
        result = simulate(inp)

        # With a funding event present and non-zero rate inside the exit
        # window, funding_cost_r should be non-zero for at least one side.
        # On current head: the engine may not use funding_events at all
        # because _build_action_outcome has decision_timestamp=0 in some paths
        # or the exit timestamp calculation is broken.
        long_cost = result.long_outcome.funding_cost_r
        short_cost = result.short_outcome.funding_cost_r
        assert long_cost != 0.0 or short_cost != 0.0, \
            f"Funding events present but cost=0 (long={long_cost}, short={short_cost})"


# ── Test 6: Current-head known breakage characterization ────────────────


class TestCurrentHeadFailures:
    """Characterize known bugs on 83ebadf that #267 must fix."""

    @pytest.mark.xfail(strict=True, reason="#267: R bundle validation error")
    def test_synthetic_wfv_directional_r_bundle_validation(self):
        """Current head has strict bundle validation issues with
        synthetic WFV data. DirectionalRResult may fail validation
        when long_gross_r, short_gross_r arrays are not properly aligned
        with labels.

        See fix(#267): 'preserve aligned labels, chronological reorder,
        strict bundle validation'
        """
        data = make_ohlcv_dict(symbols=("BTCUSDT",), bars_per_symbol=500)
        from alphaforge.validation.walk_forward_runner import run_walk_forward

        # This should fail on current head due to bundle validation
        with pytest.raises((ValueError, AssertionError)):
            run_walk_forward(
                ohlcv_data=data,
                mode="SWING",
                n_folds=2,
            )

    @pytest.mark.xfail(strict=True,
                       reason="#267: WFV output drops lookback-invalid rows without tracking")
    def test_compact_labels_preserve_invalid_row_count(self):
        """WFV output must either keep lookback/horizon-invalid rows in
        output arrays (with status flags) or provide source_row_indices
        proving which source rows survived.

        Currently, generate_directional_r_from_ohlcv silently skips
        bars without enough lookback/future room, producing fewer output
        rows than source rows — without any tracking of the gap.
        """
        data = make_ohlcv_dict(symbols=("BTCUSDT", "ETHUSDT"),
                               bars_per_symbol=(200, 200))
        result = generate_directional_r_from_ohlcv(data, mode="SWING")

        n_output = len(result.long_gross_r)
        n_source = len(data["close"])

        # Output is shorter — acceptable due to lookback/horizon.
        # But #267 must add source_row_indices so the gap is traceable.
        assert hasattr(result, "source_row_indices"), \
            "Missing source_row_indices — cannot trace which source rows survived"
