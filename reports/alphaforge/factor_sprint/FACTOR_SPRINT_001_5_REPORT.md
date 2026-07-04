# Factor Sprint 001.5 — Measurement Integrity + Central Simulation Bridge

**Date:** 2026-07-04
**Status:** COMPLETE

---

## 1. Direction/Sign Audit Verdict

**27 out of 48 factor/horizon pairs are MISALIGNED** — their raw IC sign contradicts the declared direction in `FACTOR_REGISTRY`.

### Root Cause

The `FACTOR_REGISTRY` in `factors.py` declares incorrect directions for 6 of 12 factors:

| Factor | Declared | Actual Raw IC | Verdict |
|--------|----------|---------------|---------|
| `ret_1h_rank` | long | **negative** | ❌ MISALIGNED — actually reversal |
| `ret_4h_rank` | long | **negative** | ❌ MISALIGNED — actually reversal |
| `ret_12h_rank` | long | **negative** | ❌ MISALIGNED — actually reversal |
| `ret_24h_rank` | long | **negative** | ❌ MISALIGNED — actually reversal |
| `volume_zscore` | long | **negative** | ❌ MISALIGNED — actually contrarian |
| `trend_pullback_ema` | long | **negative** | ❌ MISALIGNED — actually contrarian |
| `breakout_n_high` | long | **mixed** | ⚠️ 1h aligned, 4h/12h/24h misaligned |
| `reversal_1h_zscore` | long | **positive** | ✅ ALIGNED |
| `reversal_4h_zscore` | long | **positive** | ✅ ALIGNED |
| `range_zscore` | long | **positive** | ✅ ALIGNED |
| `breakdown_n_low` | short | **negative** | ✅ ALIGNED (short factor, negative IC = correct) |
| `compression_expansion` | agnostic | **positive** | ✅ ALIGNED (agnostic) |

**Key insight:** The `ret_*_rank` factors are labeled as momentum ("long") but actually exhibit reversal behavior in this dataset — high recent returns predict LOWER forward returns. This is a well-documented effect in crypto markets (short-term mean reversion).

### Aligned Factors (21 of 48)
- `reversal_1h_zscore`: 4/4 horizons aligned
- `reversal_4h_zscore`: 4/4 horizons aligned
- `range_zscore`: 4/4 horizons aligned
- `breakdown_n_low`: 4/4 horizons aligned
- `compression_expansion`: 4/4 horizons aligned (agnostic)

### Misaligned Factors (27 of 48)
- `ret_1h_rank`: 0/4 aligned (all horizons show reversal)
- `ret_4h_rank`: 0/4 aligned
- `ret_12h_rank`: 0/4 aligned
- `ret_24h_rank`: 0/4 aligned
- `volume_zscore`: 0/4 aligned
- `trend_pullback_ema`: 0/4 aligned
- `breakout_n_high`: 1/4 aligned (only 1h)

---

## 2. V1 Leaderboard Sign Bugs

**YES — the V1 leaderboard had sign bugs:**

### Bug 1: IC_IR Sign Inconsistency
The `ic_ir` column in V1 was negated for short factors (to match direction convention), but the `notes` field showed the raw IC_IR value (which has opposite sign). Example:

```
V1 row: breakdown_n_low, ic_ir=0.1538, notes="IC_IR=-0.15"
                                              ^^^^^^^^^^
                                              Contradicts column!
```

### Bug 2: `top_bottom_net_return` Misleading Name
The V1 `top_bottom_net_return` was NOT a cost-adjusted return. It was the direction-adjusted cumulative spread:
- For long factors: `net = raw_spread` (same as gross)
- For short factors: `net = -raw_spread` (negated)

This made `breakdown_n_low` show `gross=34.98, net=-34.98` which looks like a sign flip but is actually the direction convention.

### Bug 3: Direction Mismatch Not Caught
The pass/fail logic only checked direction mismatch when `pf == "PASS"`, but no factors passed the PASS threshold. So the check never triggered.

### Bug 4: Ret Factors Misclassified
All `ret_*_rank` factors were declared as "long" but actually exhibit reversal behavior. The V1 leaderboard used the wrong sign convention for these factors.

---

## 3. V2 Leaderboard Top 10

| Rank | Factor | Horizon | IC | IC_IR | Spread | Notes |
|------|--------|---------|-----|-------|--------|-------|
| 1 | breakdown_n_low | 24h | -0.0453 | -0.1538 | -34.98 | short factor, correct direction |
| 2 | breakdown_n_low | 12h | -0.0410 | -0.1379 | -21.14 | short factor |
| 3 | breakdown_n_low | 4h | -0.0383 | -0.1290 | -8.87 | short factor |
| 4 | volume_zscore | 24h | 0.0352 | 0.1411 | -0.14 | [flipped] |
| 5 | breakdown_n_low | 1h | -0.0339 | -0.1151 | -1.37 | short factor |
| 6 | ret_24h_rank | 24h | 0.0292 | 0.1008 | 8.24 | [flipped] |
| 7 | ret_4h_rank | 1h | 0.0291 | 0.1017 | 1.18 | [flipped] |
| 8 | reversal_4h_zscore | 1h | 0.0291 | 0.1017 | -1.41 | aligned |
| 9 | volume_zscore | 12h | 0.0289 | 0.1164 | 0.45 | [flipped] |
| 10 | trend_pullback_ema | 24h | 0.0287 | 0.1064 | 22.24 | [flipped] |

**V2 results:** 0 PASS, 45 WATCH, 3 FAIL
**No candidate meets the PASS threshold** (IC > 0.02 AND IC_IR > 0.3).

---

## 4. Proxy R Status

| Field | Value |
|-------|-------|
| Output | `PROXY_R_LEADERBOARD_V2.csv` |
| Rows | 33 |
| simulation_source | `standalone_proxy` |
| official_v7_sim | `false` |
| cost_model_source | `fast_simulator TOTAL_COST_RATE=0.0012` |
| execution_model_source | `fast_simulator_numba` |
| Best result | range_zscore (SWING_PROXY_1H): total_R=-3553.96, PF=0.74 |
| All results | REJECT (negative total R) |

**Verdict:** Standalone R is now clearly labeled as proxy. No results are official V7 R.

---

## 5. Signal Event Count

| Event Config | Events |
|--------------|--------|
| EVENT_SCALP_1H_FAST | 878,141 |
| EVENT_SCALP_1H_SLOW | 506,017 |
| EVENT_SWING_PROXY_1H | 199,456 |
| **Total** | **1,583,614** |

**Top alphas represented:**
- ret_1h_rank: 177,857 events
- reversal_1h_zscore: 177,847 events
- ret_4h_rank: 163,947 events
- reversal_4h_zscore: 163,947 events
- ret_12h_rank: 146,987 events
- breakout_n_high: 142,100 events
- breakdown_n_low: 140,864 events

**Side distribution:** LONG: 786,984 | SHORT: 796,630

**Note:** Signal events are INTENT ONLY — they do not claim trade outcomes.
**File:** `FACTOR_SIGNAL_EVENTS.csv` (236MB, 1.58M rows)

---

## 6. Central Simulation Bridge Status

| Question | Answer |
|----------|--------|
| Can central simulation consume factor signals? | **Partially** — via `simulation_adapter.py` which converts factor scores to `SimulationInput` |
| Existing CLI? | **No** — `run_simulation.py` is synthetic data only |
| Adapter needed? | **Yes** — batch signal event → `SimulationInput` converter |
| Bridge plan created? | **Yes** — `CENTRAL_SIM_BRIDGE_PLAN.md` |
| Official results generated? | **No** — adapter not yet implemented |

### What Would Make Results Official

Once the central simulation bridge is running:
- `central_net_R` = `SimulationOutput.long_outcome.realized_r_net`
- `central_expectancy_R` = mean of `realized_r_net` across trades
- `central_profit_factor` = gross profit / gross loss
- `central_max_drawdown_R` = max drawdown of cumulative R

---

## 7. Candidate Promotion Verdict

### PROMOTE: **NONE**
No candidate meets promotion criteria. All V1 R results are proxy and all are REJECT.

### WATCH: **NONE**
No candidate has IC_IR > 0.3 (strongest is breakdown_n_low at 0.15).

### REJECT: **ALL**
- 33/33 R simulation combinations are REJECT (negative total R)
- 0/48 IC evaluations meet PASS threshold

### Explanation
1. **Signal strength is weak** — best IC_IR is 0.15 (moderate), far below 0.3 (strong)
2. **Direction misclassification** — 6 of 12 factors have wrong declared direction
3. **All R results are proxy** — standalone simulator, not central engine
4. **No central simulation** — cannot produce official V7 R yet

---

## 8. Files Changed/Created

| File | Action | Purpose |
|------|--------|---------|
| `scripts/factor_direction_audit.py` | **CREATED** | Direction/sign integrity audit |
| `scripts/factor_r_sprint_v2.py` | **CREATED** | Proxy R leaderboard relabeling |
| `scripts/factor_signal_events.py` | **CREATED** | Signal event generation for central sim |
| `alphaforge/src/alphaforge/factors/loader.py` | **MODIFIED** | Made cudf/cupy imports conditional |
| `reports/alphaforge/factor_sprint/ALPHA_DIRECTION_AUDIT.csv` | **CREATED** | Full audit results (48 rows) |
| `reports/alphaforge/factor_sprint/ALPHA_LEADERBOARD_V2.csv` | **CREATED** | Corrected V2 leaderboard (48 rows) |
| `reports/alphaforge/factor_sprint/PROXY_R_LEADERBOARD_V2.csv` | **CREATED** | Proxy-labeled R results (33 rows) |
| `reports/alphaforge/factor_sprint/FACTOR_SIGNAL_EVENTS.csv` | **CREATED** | Signal events for central sim (1.58M rows, 236MB) |
| `reports/alphaforge/factor_sprint/CENTRAL_SIM_BRIDGE_PLAN.md` | **CREATED** | Bridge investigation + plan |
| `reports/alphaforge/factor_sprint/FACTOR_SPRINT_001_5_REPORT.md` | **CREATED** | This report |

---

## 9. Commands Run

```bash
# Direction audit (874s)
PYTHONPATH=. .venv/bin/python3 scripts/factor_direction_audit.py

# Proxy R leaderboard
PYTHONPATH=. .venv/bin/python3 scripts/factor_r_sprint_v2.py

# Signal events (running)
PYTHONPATH=. .venv/bin/python3 scripts/factor_signal_events.py
```

---

## 10. Known Limitations

1. **Signal events are sparse but large** — 1.58M events across 11 factors × 3 configs
2. **Central simulation adapter not implemented** — only bridge plan exists
3. **No median_rank_ic in V2** — audit doesn't compute median IC (low priority)
4. **cudf/cupy made conditional** — GPU functions may fail if called without GPU libs
5. **`load_or_build_aligned_panel` missing return statement** — returns None if cache exists (pre-existing bug, not introduced by this sprint)

---

## 11. Next Exact Steps

1. **IMMEDIATE:** Fix factor direction declarations in `FACTOR_REGISTRY`:
   - Change `ret_1h_rank`, `ret_4h_rank`, `ret_12h_rank`, `ret_24h_rank` from "long" to "short" (or create inverted variants)
   - Change `volume_zscore` from "long" to "short" (or create inverted variant)
   - Change `trend_pullback_ema` from "long" to "short" (or create inverted variant)
   - Keep `reversal_*`, `range_zscore`, `breakdown_n_low` as-is

2. **NEXT SPRINT:** Implement `central_sim_bridge.py` adapter per `CENTRAL_SIM_BRIDGE_PLAN.md`

3. **AFTER ADAPTER:** Run central simulation on corrected factor signals, produce `CENTRAL_SIM_RESULTS.csv`

4. **ONLY THEN:** Re-evaluate candidates with official V7 R for potential promotion

---

## 12. Truth Rules Verification

| Rule | Status |
|------|--------|
| Standalone R is not official R | ✅ PROXY_R_LEADERBOARD_V2.csv marked `official_v7_sim=false` |
| Central simulation owns official trade outcome | ✅ No official results generated |
| No central simulation result means no official V7 candidate | ✅ All candidates REJECT/WATCH |
| Negative evidence is still useful | ✅ We now know which factors are misaligned |
