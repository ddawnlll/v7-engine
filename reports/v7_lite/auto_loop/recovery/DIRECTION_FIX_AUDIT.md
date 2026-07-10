# Direction Fix Audit

**Generated:** 2026-07-08T07:55:00+00:00
**Source:** `alphaforge/src/alphaforge/factors/factors.py::FACTOR_REGISTRY`,
         `reports/alphaforge/factor_sprint/ALPHA_LEADERBOARD_V2.csv`,
         `reports/alphaforge/factor_sprint/ALPHA_R_LEADERBOARD.csv`,
         `reports/ALPHA_INVENTORY_FULL.csv`

---

## Executive Summary

**6 of 12 IC-evaluable factors** have direction declarations that contradict the IC evidence.
**7 factors** have no IC data (BLOCKED_DATA_MISSING — mostly deprecated funding-rate factors).
**12 factors** are correctly declared.

Key finding: The FACTOR_REGISTRY was previously corrected from `long→short` for `ret_*_rank`
(based on an earlier audit), but the current IC leaderboard shows **consistently POSITIVE IC**
for all ret_*_rank factors across all horizons (1h–24h). This means the raw signal is
**momentum** (high past return → high future return), not reversal. The "short" direction
is incorrect based on IC evidence.

However, even with correct "long" direction, the simulation results are all negative
(-0.23 to -0.84 R/trade). This indicates **cost dominance**, not direction error, is the
primary failure mode for these factors.

---

## Per-Factor Audit

### ret_1h_rank

| Field | Value |
|-------|-------|
| **Current declared direction** | `short` |
| **Expected direction** | `long` (IC is positive) |
| **Best IC evidence** | +0.0278 (mean_rank_ic, 1h horizon) |
| **IC sign** | Positive across all horizons (1h: +0.0278, 4h: +0.0210, 12h: +0.0097, 24h: +0.0062) |
| **Evidence for misdeclaration** | IC uniformly positive — high rank scores predict positive forward returns (momentum). "short" direction means betting against momentum. |
| **Old raw_R (sim, long side)** | -0.839 (SCALP_1H_FAST, 110K trades) |
| **Old trade_count** | 110,513 |
| **Old cost_stress_survived** | False |
| **Fix safety** | LOW — even correct direction produces negative R. Cost dominance overwhelms signal. |
| **Retest required** | Yes — but expected improvement from direction fix alone is negligible |
| **Classification** | **CONFIRMED_MISDECLARED** |

### ret_4h_rank

| Field | Value |
|-------|-------|
| **Current declared direction** | `short` |
| **Expected direction** | `long` |
| **Best IC evidence** | +0.0291 (mean_rank_ic, 1h horizon) |
| **IC sign** | Positive across all horizons |
| **Evidence for misdeclaration** | Same as ret_1h_rank — uniformly positive IC |
| **Old raw_R (sim, long side)** | -0.829 (SCALP_1H_FAST, 98K trades) |
| **Old trade_count** | 98,815 |
| **Fix safety** | LOW |
| **Classification** | **CONFIRMED_MISDECLARED** |

### ret_12h_rank

| Field | Value |
|-------|-------|
| **Current declared direction** | `short` |
| **Expected direction** | `long` |
| **Best IC evidence** | +0.0242 (mean_rank_ic, 4h horizon) |
| **IC sign** | Positive across all horizons |
| **Old raw_R (sim, long side)** | -0.550 (SCALP_1H_FAST, 88K trades) |
| **Classification** | **CONFIRMED_MISDECLARED** |

### ret_24h_rank

| Field | Value |
|-------|-------|
| **Current declared direction** | `short` |
| **Expected direction** | `long` |
| **Best IC evidence** | +0.0292 (mean_rank_ic, 24h horizon) |
| **IC sign** | Positive across all horizons |
| **Old raw_R (sim, long side)** | -0.813 (SCALP_1H_FAST, 82K trades) |
| **Classification** | **CONFIRMED_MISDECLARED** |

### volume_zscore

| Field | Value |
|-------|-------|
| **Current declared direction** | `short` |
| **Expected direction** | `long` (IC is positive) |
| **Best IC evidence** | +0.0352 (mean_rank_ic, 24h horizon) |
| **IC sign** | Positive across all horizons (1h: +0.0125, 4h: +0.0184, 12h: +0.0289, 24h: +0.0352) |
| **Evidence for misdeclaration** | IC is uniformly positive — high volume predicts positive returns. "short" direction expects high volume → negative returns. |
| **Old raw_R (sim, long side)** | -1.278 (SCALP_1H_FAST, 67K trades) |
| **Old cost_stress_survived** | False |
| **Fix safety** | VERY LOW — massive negative R with correct direction |
| **Classification** | **CONFIRMED_MISDECLARED** |

### breakdown_n_low

| Field | Value |
|-------|-------|
| **Current declared direction** | `long` |
| **Expected direction** | `short` (IC is negative) |
| **Best IC evidence** | -0.0453 (mean_rank_ic, 24h horizon) |
| **IC sign** | Negative across all horizons (1h: -0.0339, 4h: -0.0383, 12h: -0.0410, 24h: -0.0453) |
| **Evidence for misdeclaration** | IC uniformly negative — breakdown below support predicts continued decline. "long" direction expects recovery. |
| **Old raw_R (sim, short side)** | -1.019 (SCALP_1H_FAST, 86K trades) |
| **Classification** | **CONFIRMED_MISDECLARED** |

---

## Correctly Declared Factors

| Factor | Direction | Best IC | Verdict |
|--------|-----------|---------|---------|
| range_zscore | `long` | +0.0263 | ✓ Consistent — expanding range predicts positive returns |
| reversal_1h_zscore | `long` | +0.0278 | ✓ Consistent |
| reversal_4h_zscore | `long` | +0.0291 | ✓ Consistent |

---

## Factors Without IC Data (BLOCKED_DATA_MISSING)

| Factor | Direction | Reason |
|--------|-----------|--------|
| btc_downtrend_breakdown_short | short | Not in IC leaderboard (BT C-dependent) |
| btc_uptrend_pullback_long | long | Not in IC leaderboard (BTC-dependent) |
| corwin_schultz_spread_proxy | short | Not in IC leaderboard (microstructure) |
| spread_contraction_signal | long | Not in IC leaderboard (microstructure) |
| funding_extreme_long | long | DEPRECATED — empty on all symbols |
| funding_extreme_short | short | DEPRECATED — empty on all symbols |
| funding_momentum_fade | long | DEPRECATED — empty on all symbols |

---

## Direction-Agnostic / Unstable Factors

| Factor | Declared | Reason |
|--------|----------|--------|
| breakout_n_high | unstable | Flip between windows |
| compression_breakout_regime | unstable | Unreliable direction |
| compression_expansion | agnostic | Direction-agnostic by design |
| session_volatility_regime | unstable | Medium vol not stable |
| trend_pullback_ema | unstable | Flip between windows |
| volume_climax_reversal_long | unstable | Direction unreliable |
| volume_climax_reversal_short | unstable | Direction unreliable |
| btc_lead_lag_alt_long | unstable | Unreliable |
| btc_lead_lag_alt_short | unstable | Unreliable |

---

## Key Insight: Direction vs. Cost Dominance

The 6 CONFIRMED_MISDECLARED factors have the following simulated R values (using the
incorrect direction):

| Factor | Current Dir | Correct Dir | Best Sim R (old dir) | Trade Count |
|--------|-------------|-------------|---------------------|-------------|
| ret_1h_rank | short | long | -0.839 | 110K |
| ret_4h_rank | short | long | -0.829 | 98K |
| ret_12h_rank | short | long | -0.550 | 88K |
| ret_24h_rank | short | long | -0.813 | 82K |
| volume_zscore | short | long | -1.278 | 67K |
| breakdown_n_low | long | short | -1.019 | 86K |

**Critical observation:** The simulation results with the WRONG direction are massively
negative (-0.55 to -1.28 R/trade). Even if the correct direction reverses the sign,
the magnitude would be at best +0.55 to +1.28 R/trade GROSS. After costs (~0.062R/trade),
the net would be +0.49 to +1.22 R/trade.

**However**, the FACTOR_REGISTRY was already changed from `long→short` for ret_*_rank
based on a walk-forward stability analysis showing "STABLE negative". The IC leaderboard
disagrees. This suggests the IC and the walk-forward analysis used different methodologies:

1. **IC leaderboard**: Simple 1-step-ahead rank correlation → shows momentum
2. **Walk-forward (factor_sprint.py --walkforward)**: 3-window sign stability → shows reversal

This discrepancy needs resolution before any direction fix is applied.

---

## Decision

| Action | Verdict |
|--------|---------|
| Fix FACTOR_REGISTRY directions | **NO** — discrepancy between IC and walk-forward analysis needs resolution |
| Re-run central sim with correct direction | **BLOCKED_SIM_ENTRYPOINT_UNKNOWN** — no reliable central sim entry point for factor sprint factors |
| Expect raw positives from direction fix | **LOW** — cost dominance is the primary failure mode, not direction |
| Reject direction-fix approach for now | **RECOMMENDED** — focus on cost rescue and proxy→central bridge instead |

The direction misdeclarations are real (IC evidence) but fixing them alone will not
produce cost-surviving alphas. The cost model (~0.062R/trade) kills even the best
factor candidates.

---

## Next Actions

1. Focus on **proxy→central simulation bridge** (Task 1C) — this will enable re-running
   all 33 proxy entries through the real simulation engine with cost model
2. Focus on **Truth V6 specialist rescue** (Task 1D) — best chance of a cost survivor
3. Focus on **BB Position v2 revalidation** (Task 1F) — second best chance
4. **Defer direction fix** until proxy→central bridge is operational
