# Failure-Driven Discovery Run

**Generated:** 2026-07-08T08:08:00+00:00
**Loop Phase:** DISCOVERY
**Based on:** `NEXT_10_ALPHA_DISCOVERY_PLAN.md`, IC leaderboard V2, R leaderboard

---

## Analysis Pre-requisite: Root Cause Diagnosis

Before running any discovery experiments, we must understand WHY the top 10 experiments
are likely to fail. The answer comes from cross-referencing IC and R data.

### IC vs R Discrepancy

| Factor | Mean IC | IC Sign | Sim R (long) | Sim Mode | IC consistent? | R salvageable? |
|--------|---------|---------|-------------|----------|----------------|----------------|
| ret_1h_rank | +0.0278 | Positive | -0.839 | long | Yes (IC says momentum) | No — cost-killed |
| ret_4h_rank | +0.0291 | Positive | -0.829 | long | Yes | No — cost-killed |
| ret_12h_rank | +0.0242 | Positive | -0.550 | long | Yes | No — cost-killed |
| ret_24h_rank | +0.0292 | Positive | -0.813 | long | Yes | No — cost-killed |
| volume_zscore | +0.0352 | Positive | -1.278 | long | Yes | No — cost-killed |
| breakdown_n_low | -0.0453 | Negative | -1.019 | short | Yes (negative IC = short) | No — cost-killed |
| reversal_1h_zscore | +0.0278 | Positive | -0.729 | long | Yes | No — cost-killed |
| trend_pullback_ema | +0.0287 | Positive | -0.150 | long | Unstable | No — cost-killed |

**Critical finding: ALL factors have IC consistent with their correct direction, yet ALL
simulation results are massively negative.** The problem is NOT direction errors — it's
cost dominance (~0.062R/trade) overwhelming the weak IC signal (0.02-0.04).

### Why "Invert Direction" Won't Work

The inversion hypothesis assumes the factor has predictive power but the sign is wrong.
For ret_*_rank, the IC is POSITIVE (momentum). Running with "short" direction would
produce EVEN MORE negative R. Flipping from "short" to "long" would align with the IC
sign, but the existing simulation (already using "long" side) shows -0.84R.

**The factor already had the "correct" direction during simulation.** The simulation
used side=long (which matches the momentum hypothesis). The negative result is not
from direction error but from:
1. Costs (~0.062R/trade)
2. Exit logic (stop/target may not capture momentum well)
3. Market impact (asymmetric tails)

### What the Factor Sprint Audit Actually Found

The FACTOR_SPRINT_001_5 report says "27 of 48 factor/horizon pairs are MISALIGNED."
This refers to the RAW IC sign contradicting the DECLARED direction in FACTOR_REGISTRY
(at the time of the audit). Since then, the registry was updated (ret_*_rank changed
from "long" to "short"). But the IC leaderboard V2 shows these factors have POSITIVE IC,
meaning the correct direction is "long", not "short" — the fix was wrong.

**The registry was incorrectly corrected.** The direction should be "long" (momentum),
not "short" (reversal). But even with the correct direction, the factors are cost-killed.
This is a moot point for practical alpha discovery.

---

## Experiment Results

### Experiment 1: ret_1h_rank — Inverted Direction

| Field | Value |
|-------|-------|
| **ID** | EXP-RET-1H-INVERT |
| **Hypothesis** | Inverted direction will produce positive R |
| **Evidence** | IC = +0.0278 (positive, momentum). Sim already used long side = -0.84R. |
| **Verdict** | **REJECT** — IC shows momentum, not reversal. Inversion would worsen R. |
| **Root cause** | Cost kills the edge, not direction |

### Experiment 2: ret_4h_rank — Inverted Direction

| Field | Value |
|-------|-------|
| **Hypothesis** | Inverted direction will produce positive R |
| **Evidence** | IC = +0.0291 (positive). Sim already long = -0.83R. |
| **Verdict** | **REJECT** — same as ret_1h_rank |

### Experiment 3: ret_12h_rank — Inverted Direction

| Field | Value |
|-------|-------|
| **Hypothesis** | Inverted direction will produce positive R |
| **Evidence** | IC = +0.0242 (positive). Sim already long = -0.55R. |
| **Verdict** | **REJECT** — same pattern |

### Experiment 4: volume_zscore — Inverted Direction

| Field | Value |
|-------|-------|
| **Hypothesis** | Inverted direction produces positive R |
| **Evidence** | IC = +0.0352 (positive). Sim already long = -1.28R. |
| **Verdict** | **REJECT** — same pattern |

### Experiment 5: trend_pullback_ema — Inverted Direction

| Field | Value |
|-------|-------|
| **Hypothesis** | Inverted direction works |
| **Evidence** | IC = +0.0287 (positive). Sim R = -0.15 to -0.77R. Declared "unstable". |
| **Verdict** | **REJECT** — unstable direction, cost-killed |

### Experiment 6: Truth V6 — BTCUSDT × SHORT × Maker

| Field | Value |
|-------|-------|
| **Hypothesis** | BTCUSDT SHORT with maker execution survives costs |
| **Evidence** | Raw edge exists (+0.0515R), BTCUSDT carries 457% of profit |
| **Estimated BTCUSDT SHORT trades** | ~130-200 (below 200 threshold) |
| **Estimated cost-adj R** | ~+0.089R (maker, LOW confidence) |
| **Blocker** | Actual trade data not persisted; proxy data underestimates edge by 60x |
| **Verdict** | **BLOCKED** — needs discovery pipeline re-run with per-trade logging |
| **Reject condition** | cost-adjusted R < 0 or trade count < 200 |

### Experiment 7: Truth V6 — Confidence Percentile Filter

| Field | Value |
|-------|-------|
| **Hypothesis** | Top quartile by confidence survives costs |
| **Evidence** | No per-trade confidence data exists |
| **Blocker** | Trade data not persisted; profit_score not computed |
| **Verdict** | **BLOCKED** — BLOCKED_SCORE_MISSING |

### Experiment 8: BB Position v2 — Corrected Features

| Field | Value |
|-------|-------|
| **Hypothesis** | After fixing convolve bug, mean-reversion edge survives |
| **Evidence** | Pipeline already fixed (verified via code inspection). v1 +0.0043R likely inflated by contamination. |
| **Expected clean R** | ~0.000 to +0.002R |
| **Expected cost-adj R** | ~-0.060R (below cost) |
| **Blocker** | Training pipeline not runnable in this loop |
| **Verdict** | **REJECT** — expected cost-adjusted R is negative even with clean features |

### Experiment 9: Operation SCALP 0.05 — Regime-Gated

| Field | Value |
|-------|-------|
| **Hypothesis** | Regime gate (no LONG in uptrend) improves baseline |
| **Baseline R** | -0.0951R (taker, 12 sym, 4,726 trades) |
| **Estimated improvement** | +0.02 to +0.04R (regime filter removes worst trades) |
| **Blocker** | Central sim not available to re-run with gate |
| **Verdict** | **BLOCKED** — BLOCKED_SIM_ENTRYPOINT_UNKNOWN |

### Experiment 10: Factor Sprint Proxy — Central Simulation Re-run

| Field | Value |
|-------|-------|
| **Hypothesis** | Central sim produces different (better) R than fast_simulator |
| **Evidence** | 33 proxy entries all negative. Central sim bridge not built. |
| **Blocker** | Central simulation bridge adapter not implemented |
| **Verdict** | **BLOCKED** — BLOCKED_SIM_ENTRYPOINT_UNKNOWN |

---

## Summary

| Experiment | Status | Reason |
|-----------|--------|--------|
| 1. ret_1h_rank invert | REJECT | IC already aligned; cost-killed |
| 2. ret_4h_rank invert | REJECT | Same |
| 3. ret_12h_rank invert | REJECT | Same |
| 4. volume_zscore invert | REJECT | Same |
| 5. trend_pullback invert | REJECT | Unstable; cost-killed |
| 6. Truth V6 BTC SHORT | BLOCKED | Trade data not persisted |
| 7. Truth V6 confidence | BLOCKED | Score missing |
| 8. BB Position v2 | REJECT | Expected clean R near zero |
| 9. Op Scalp regime gate | BLOCKED | No sim entry point |
| 10. Central sim re-run | BLOCKED | Bridge not built |

**Raw positive created: 0**
**Cost survivors created: 0**
**Experiments blocked: 4** (6, 7, 9, 10)
**Experiments rejected: 6** (1, 2, 3, 4, 5, 8)

---

## Honest Assessment

ALL 10 experiments are either REJECT or BLOCKED for this run. The primary reason is
not lack of ideas but **structural blockers**:

1. **Cost dominance**: ~0.062R/trade kills every factor with IC < 0.10
2. **No central simulation bridge**: Cannot re-run 33 proxy entries or run factored simulations
3. **Trade data not persisted**: Truth V6's actual trades are lost; only aggregate metrics remain
4. **Pipeline not runnable**: BB Position v2 re-run requires full training pipeline which
   is not set up for execution

**The most actionable path forward is to re-run the Truth V6 discovery pipeline
with complete per-trade logging enabled.** This single action would unlock experiments
6, 7, and potentially produce the first cost-surviving segment.

---

## Next Actions

1. Re-run Truth V6 discovery pipeline with per-trade logging → unlock experiments 6, 7
2. Build central simulation bridge adapter → unlock experiments 9, 10
3. Build BB Position v2 re-run script → test experiment 8 conclusively

**None of these can be completed within this 2-hour loop.** They are infrastructure
tasks requiring 4-8 hours of focused engineering.
