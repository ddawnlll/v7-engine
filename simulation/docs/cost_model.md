# Cost Model — Fee, Slippage & Net R Semantics

## Purpose

This document defines the cost model used by the `/simulation` engine. Every simulated path (`LONG_NOW`, `SHORT_NOW`) applies identical fee and slippage semantics. There is no separate cost model for labels vs evaluation vs paper trading.

## Core Formula

```
realized_r_gross = (exit_price - entry_price) / (atr * stop_multiplier)  [for LONG]
realized_r_gross = (entry_price - exit_price) / (atr * stop_multiplier)  [for SHORT]

fee_cost_r = (entry_fee + exit_fee) / (atr * stop_multiplier)
slippage_cost_r = (entry_slippage + exit_slippage) / (atr * stop_multiplier)
total_cost_r = fee_cost_r + slippage_cost_r

realized_r_net = realized_r_gross - total_cost_r
```

Where:
- `atr` is the ATR value at decision time (from canonical state)
- `stop_multiplier` is the mode-specific ATR stop multiplier (see profiles)
- `(atr * stop_multiplier)` is the entry risk in price terms (1R)

## Fee Model

| Parameter | Default | Notes |
|---|---|---|
| `maker_fee_bps` | `2.0` | 2 basis points (0.02%) for limit orders |
| `taker_fee_bps` | `4.0` | 4 basis points (0.04%) for market orders |
| `minimum_fee_quote` | `0.0` | Minimum fee in quote currency (exchange-dependent) |
| `use_taker_for_simulation` | `true` | Assume taker fees for conservative simulation |

### Fee Computation

```
entry_fee = entry_price * position_size * (taker_fee_bps / 10000)
exit_fee  = exit_price  * position_size * (taker_fee_bps / 10000)
fee_cost_r = (entry_fee + exit_fee) / entry_risk_price
```

The conservative default uses taker fees for both entry and exit. This can be configured.

## Slippage Model

| Parameter | Default | Notes |
|---|---|---|
| `slippage_bps` | `1.0` | 1 basis point (0.01%) base slippage |
| `slippage_volatility_adjust` | `true` | Scale slippage with volatility |
| `slippage_volatility_multiplier` | `1.0` | How much volatility amplifies slippage |

### Slippage Computation

```
base_slippage = entry_price * (slippage_bps / 10000)

if slippage_volatility_adjust:
    volatility_adjustment = atr / entry_price  # ATR as fraction of price
    adjusted_slippage = base_slippage * (1.0 + volatility_adjustment * slippage_volatility_multiplier)
else:
    adjusted_slippage = base_slippage

entry_slippage = adjusted_slippage
exit_slippage  = adjusted_slippage  # applied at exit too (conservative)
slippage_cost_r = (entry_slippage + exit_slippage) / entry_risk_price
```

## Why One Cost Model Across All Consumers

| Consumer | Uses Cost Model For | Must Match |
|---|---|---|
| AlphaForge labels | Computing `long_R_net`, `short_R_net` labels | Training truth |
| AlphaForge evaluation | Computing realized R in walk-forward folds | Evaluation truth |
| V7 paper forward | Projecting paper trade outcomes | Paper truth |
| V7 live outcome normalization | Computing `TradeOutcome.realized_r` | Live truth |
| V7 historical replay | Determining replay projected outcomes | Replay truth |

If any of these used a different cost model, the system would become economically untrustworthy:
- Labels would train on one cost assumption
- Evaluation would judge on another
- Paper would project on a third
- Live outcomes would normalize on a fourth

This is why `/simulation` must be the single authority.

## Cost Model Versioning

Cost model changes bump `cost_model_version`:

| Change | Example | Bump |
|---|---|---|
| Fee rate changes | Binance changes maker fee from 2bp to 1bp | Minor |
| Slippage model logic changes | From fixed bps to volatility-adjusted | Major |
| New cost component added | Adding spread cost, funding cost | Major |
| Cost family restructured | Renaming fields, changing formula | Major |

Old datasets remain traceable to the `cost_model_version` that produced their labels.

## Relationship to `lib/costs/`

`lib/costs/` provides basic cost primitives (fee percentage formulas, simple slippage calculation). `/simulation` wraps and versions these primitives into the authoritative cost model. `lib/` stays primitive; `/simulation` owns the composite semantics and versioning.

## Example: Net R Computation

```
Given:
  entry_price = 50000
  exit_price  = 51000
  atr = 1000
  stop_multiplier = 2.0
  taker_fee_bps = 4.0

Step 1 — Entry risk (1R):
  1R = 1000 * 2.0 = 2000

Step 2 — Gross R (LONG):
  gross_R = (51000 - 50000) / 2000 = 1000 / 2000 = 0.50

Step 3 — Fee cost:
  entry_fee = 50000 * 0.0004 = 20.0
  exit_fee  = 51000 * 0.0004 = 20.4
  total_fee = 40.4
  fee_cost_R = 40.4 / 2000 = 0.0202

Step 4 — Slippage cost:
  slippage = 50000 * 0.0001 = 5.0 (per side, conservative)
  total_slippage = 10.0
  slippage_cost_R = 10.0 / 2000 = 0.005

Step 5 — Net R:
  net_R = 0.50 - 0.0202 - 0.005 = 0.4748
```

The trade produced ~0.47R net, despite a 0.50R gross return. At the SCALP scale, costs are proportionally more impactful (which is why SCALP profile has higher cost_penalty_weight).

---

## Document Authority

**Canonical hub:** [ai_summary.md](ai_summary.md) — read this first for the full system synthesis and table of contents.

**Related docs for this topic:**

| [contracts.md](contracts.md) | CostModelRef in SimulationInput |
| [profiles.md](profiles.md) | Mode profiles that use cost parameters |
| [exits_and_horizons.md](exits_and_horizons.md) | How costs apply at exit |
| [lineage_and_versioning.md](lineage_and_versioning.md) | cost_model_version, fee_model_version, slippage_model_version |
    
**Parent:** [../README.md](../README.md) — authority overview and ownership diagram.

**For implementation:** See [phases/](phases/) for v4.1.1 phase plans S0–S6.

**For validation:** See [validation.md](validation.md) for required test gates.

