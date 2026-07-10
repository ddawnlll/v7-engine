# Inversion Candidate Audit

**Generated:** 2026-07-08
**Source:** `reports/ALPHA_INVENTORY_FULL.csv`
**Total inversion candidates:** 36 (across ~10 unique concepts)

---

## Methodology

An alpha is an inversion candidate if:
- `abs(raw_net_R)` is large (typically > 0.2R/trade)
- Trade count is sufficient (> 10K)
- Loss pattern appears systematic, not random
- Contamination is false

**Important:** Do not assume `inverse_R = -raw_R`. Costs apply both ways.
The inversion hypothesis is: the signal has predictive value, but the sign is wrong.

---

## Verified Direction Misalignments (from FACTOR_SPRINT_001_5)

Per the factor sprint direction audit, 6 of 12 factors in the FACTOR_REGISTRY have **wrong declared directions**:

| Factor | Declared | Actual IC | Verdict |
|--------|----------|-----------|---------|
| `ret_1h_rank` | LONG (momentum) | NEGATIVE | ❌ Actually REVERSAL |
| `ret_4h_rank` | LONG (momentum) | NEGATIVE | ❌ Actually REVERSAL |
| `ret_12h_rank` | LONG (momentum) | NEGATIVE | ❌ Actually REVERSAL |
| `ret_24h_rank` | LONG (momentum) | NEGATIVE | ❌ Actually REVERSAL |
| `volume_zscore` | LONG | NEGATIVE | ❌ Actually CONTRARIAN |
| `trend_pullback_ema` | LONG | NEGATIVE | ❌ Actually CONTRARIAN |

These 6 factors are **not** "failed alphas" — they are **misdeclared** and should be tested with corrected direction before being judged.

---

## Priority Inversion Candidates

### HIGH PRIORITY (6 concepts, misdeclared in FACTOR_REGISTRY)

| # | Concept | Reason | Priority |
|---|---------|--------|----------|
| 1 | **ret_1h_rank** (all horizons) | Declared LONG, IC is negative -> mean reversion | HIGH |
| 2 | **ret_4h_rank** (all horizons) | Same as above | HIGH |
| 3 | **ret_12h_rank** (all horizons) | Same as above | HIGH |
| 4 | **ret_24h_rank** (all horizons) | Same as above | HIGH |
| 5 | **volume_zscore** (all horizons) | Declared LONG, IC is negative | HIGH |
| 6 | **trend_pullback_ema** (all horizons) | Declared LONG, IC is negative | HIGH |

**Expected gain from correcting direction:**
- The `ret_*_rank` factors have raw IC_abs up to 0.10. With correct direction, the
  negative R should become positive (or at least less negative).
- The negative R values (-0.29 to -0.84) are likely dominated by direction error
  plus costs

### MEDIUM PRIORITY (systematic BTC-dependent failures)

| # | Concept | R | Trades | Notes |
|---|---------|---|--------|-------|
| 7 | BTC Lead-Lag Alt (long+short) | -0.36R | 35K+ | BTC regime proxy |
| 8 | BTC Uptrend Pullback Long | -0.41 to -1.48R | 21K-39K | BTC trend filter |
| 9 | BTC Downtrend Breakdown Short | -0.42 to -1.02R | 41K-85K | BTC regime filter |

**Inversion rationale:** These are NOT inversion candidates in the "flip the direction"
sense. They are BTC-regime-dependent signals. The negative performance may indicate
that the REGIME DETECTION (not the directional signal) is wrong. Inversion strategy:
test opposite BTC regime conditions.

### LOW PRIORITY (potential structural inversions)

| # | Concept | R | Trades | Notes |
|---|---------|---|--------|-------|
| 10 | breakdown_n_low | -0.43 to -1.02R | 42K-86K | Extreme negative. May be correct direction but bad timing |
| 11 | breakout_n_high | -0.43 to -1.01R | 43K-87K | Similar structure to breakdown |
| 12 | reversal_1h_zscore | -0.31 to -0.73R | 53K-111K | Aligned IC but negative R -> cost dominance |
| 13 | reversal_4h_zscore | -0.29 to -0.82R | 50K-100K | Same structure |

---

## Test Protocol for Inversion Candidates

For each inversion candidate:

1. **Fix direction** in FACTOR_REGISTRY (for misdeclared factors)
2. **Run central simulation** with corrected direction
3. **Compare:** corrected R vs raw R
4. **If corrected R > 0 and > baseline:** promote to WATCH
5. **If corrected R still < 0:** apply cost and segment filters

Expected success rate:
- HIGH priority: 40-60% chance of yielding positive R after inversion
- MEDIUM priority: 20-40% chance  
- LOW priority: 10-20% chance (most are cost-killed, not direction-killed)

---

## Risk: Inversion Is Not Free

- Costs apply to both original and inverted signals
- If the original signal is negative because of costs (not direction), inversion
  will also be negative
- Inversion doubles the multiple-testing burden (now 340 trials instead of 170)
- Best practice: only invert concepts with IC evidence supporting the opposite sign
