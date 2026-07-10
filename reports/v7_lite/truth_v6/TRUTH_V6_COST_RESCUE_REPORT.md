# Truth V6 Cost Rescue Report

**Status:** `PARTIAL` — aggregated data only
**Verdict:** `WATCH`
**Generated:** 2026-07-08

---

## Executive Summary

Truth V6 raw R (+0.0515R) is below the estimated execution cost per trade (~0.062R).
The raw signal does NOT survive costs at the baseline taker model. However, this
conclusion depends entirely on the **aggregated** mean. Without trade-level data, we
cannot determine whether subsets of trades cost-survive.

---

## Cost Scenario Analysis

### Baseline Cost Model (from simulation/docs/cost_model.md)

| Component | Value | Source |
|-----------|-------|--------|
| taker_fee_bps | 4.0 (0.04%) | simulation/docs/cost_model.md |
| maker_fee_bps | 2.0 (0.02%) | simulation/docs/cost_model.md |
| slippage_bps | 1.0 (0.01%) | simulation/docs/cost_model.md |
| round_trip_bps | 10.0 | 4+1 entry, 4+1 exit |
| round_trip_R_cost | ~0.062R | estimated (depends on ATR) |

### Scenario Results

| Scenario | Assumption | Estimated Cost/R | Raw R | Adj R | Survival? |
|----------|-----------|-----------------|-------|-------|-----------|
| **Raw** | No costs | 0.000 | +0.0515 | +0.0515 | Raw only |
| **Base taker** | taker 4bps entry + exit, 1bp slippage each | 0.062R | +0.0515 | **-0.0105** | ❌ FAIL |
| **2x cost stress** | 2× base cost | 0.124R | +0.0515 | **-0.0725** | ❌ FAIL |
| **5x cost stress** | 5× base cost | 0.310R | +0.0515 | **-0.2585** | ❌ FAIL |
| **Maker (best case)** | maker 2bps entry + exit, 0.5bp slippage each | 0.031R | +0.0515 | **+0.0205** | ⚠️ WEAK |
| **Taker (pessimistic)** | taker 5bps entry + exit, 2bp slippage each | 0.093R | +0.0515 | **-0.0415** | ❌ FAIL |

**Note:** These cost/R estimates depend on ATR at entry. If Truth V6 enters during
high-ATR regimes, the per-trade cost in R units is LOWER (same dollar cost ÷ larger ATR).
If it enters during low-ATR regimes, cost in R units is HIGHER. This is why
per-trade data is essential.

---

## Split Rescue Analysis

Without trade-level data, the following rescues **cannot be evaluated**:

| Rescue Strategy | Can Evaluate? | Needed |
|----------------|-------------|--------|
| Top profit_score percentiles | ❌ | Per-trade scores |
| Low spread bucket | ❌ | Per-trade spread data |
| High volume bucket | ❌ | Per-trade volume data |
| Low slippage bucket | ❌ | Per-trade slippage |
| Trend regime | ❌ | Per-trade regime labels |
| Breakout regime | ❌ | Per-trade regime labels |
| Non-chop regime | ❌ | Per-trade regime labels |
| Liquid sessions | ❌ | Per-trade timestamps |
| Long-only | ❌ | Per-trade direction |
| Short-only | ❌ | Per-trade direction |
| Best symbols after concentration | ❌ | Per-trade symbol |

---

## Symbol-Level Analysis (from aggregated data only)

From the ledger, the 4 symbols are: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT.
No individual symbol metrics are available. However, based on other alpha runs
in this repo:

| Symbol | Expectation | Rationale |
|--------|------------|-----------|
| BTCUSDT | Likely positive | Most liquid, lowest spread cost |
| ETHUSDT | Likely neutral | Second most liquid |
| SOLUSDT | Possibly negative | Higher spread, lower liquidity |
| BNBUSDT | Possibly negative | Higher spread, lower liquidity |

The `SWING Control` run (same symbols + 8 more) showed:
- Fee cost: 0.0468R/trade
- Slippage cost: 0.0118R/trade
- Total cost: 0.0586R/trade

---

## Decision

| Label | Criteria | Verdict |
|-------|----------|---------|
| `CAN_CALIBRATE` | One stable segment survives costs at ≥ +0.10R | ❌ No data to evaluate |
| `WATCH` | Raw signal exists but cost-adjusted survival is weak/unstable | ✅ **WATCH** |
| `REJECT` | No segment survives cost or edge is dominated by lucky subset | ❌ Premature without trade data |

### Rationale for WATCH

1. Raw R of +0.0515R is marginally above zero — it is a **candidate for rescue**
2. The maker scenario shows +0.0205R — cost rescue may be feasible if the alpha
   can be executed via limit orders or rebate programs
3. The edge may be concentrated in high-ATR periods where cost/R is lower
4. Win rate near 50% with profit_factor 1.11 is not obviously overfit at the
   aggregate level, though multiple-testing risk (selected from 170) is real

### Path to CAN_CALIBRATE

To move from WATCH to CAN_CALIBRATE, the following is needed:

1. **Recover trade-level data** or re-run the discovery pipeline
2. **Compute per-trade cost** using the simulation cost model
3. **Filter to top-decile profit_score trades** (if score available)
4. **Filter to high-ATR periods** (lower cost/R)
5. **Check symbol-level survival** (likely BTCUSDT + ETHUSDT)
6. **Compute deflated Sharpe** to account for 170-way selection

If after these filters a segment of ≥200 trades survives at ≥+0.10R cost-adjusted,
the alpha can be labeled `CAN_CALIBRATE`.
