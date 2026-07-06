# Fee Optimization Research — Bedava Para

## Goal

Reduce net fee drag from the current conservative estimate (0.04% taker both
sides = 0.08% round trip) toward exchange reality (as low as 0.028% round trip
at VIP1 maker/taker or 0.014% at VIP2 with BNB discounts).

A 60%+ reduction in fee cost translates to ~6-8% improvement in net R,
directly supporting the Milestone A target of 18-20% net R.

## Exchange Fee Tiers

### Binance USDT-M Futures

| Tier | 30d Volume (BTC) | Maker | Taker | 30d Savings vs Regular |
|------|------------------|-------|-------|----------------------|
| Regular | < 50 | 0.020% | 0.050% | baseline |
| VIP 1 | ≥ 50 | 0.016% | 0.040% | 20% |
| VIP 2 | ≥ 100 | 0.014% | 0.035% | 30% |
| VIP 3 | ≥ 200 | 0.012% | 0.032% | 37% |
| VIP 4 | ≥ 400 | 0.010% | 0.030% | 43% |
| VIP 5 | ≥ 800 | 0.008% | 0.028% | 49% |
| VIP 6 | ≥ 1200 | 0.006% | 0.026% | 55% |
| VIP 7 | ≥ 2000 | 0.004% | 0.024% | 60% |
| VIP 8 | ≥ 4000 | 0.004% | 0.022% | 62% |
| VIP 9 | ≥ 7500 | 0.002% | 0.020% | 67% |

Volume requirement in BTC. At $60k BTC, VIP1 requires $3M/month, VIP2 requires
$6M/month. For a strategy trading 10-50 BTC/month notional, VIP2 is achievable.

### BNB Discount

Binance offers an additional 10% discount on fees when paid in BNB. This
applies to all tiers. Effective rates at VIP1 with BNB:

| | Maker | Taker |
|---|---|---|
| Base | 0.016% | 0.040% |
| BNB 10% discount | 0.0144% | 0.0360% |
| Round trip | **0.0504%** | |

At VIP2 with BNB:

| | Maker | Taker |
|---|---|---|
| Base | 0.014% | 0.035% |
| BNB 10% discount | 0.0126% | 0.0315% |
| Round trip | **0.0441%** | |

### OKX VIP Tiers

| Tier | 30d Volume (USDT) | Maker | Taker | Notes |
|------|-------------------|-------|-------|-------|
| Regular | < 1M | 0.020% | 0.050% | — |
| VIP 1 | ≥ 1M | 0.018% | 0.045% | — |
| VIP 2 | ≥ 10M | 0.016% | 0.040% | 40% rebate available |
| VIP 3 | ≥ 50M | 0.014% | 0.035% | — |
| VIP 4 | ≥ 200M | 0.012% | 0.030% | — |
| VIP 5 | ≥ 500M | 0.010% | 0.028% | — |

OKX offers up to 40% rebate on fees at VIP2+ for qualifying accounts, further
reducing effective fee rates.

### Bybit

| Tier | 30d Volume (USDT) | Maker | Taker |
|------|-------------------|-------|-------|
| Regular | < 1M | 0.020% | 0.050% |
| VIP 1 | ≥ 1M | 0.018% | 0.048% |
| VIP 2 | ≥ 5M | 0.016% | 0.045% |
| VIP 3 | ≥ 25M | 0.014% | 0.040% |

### Fee Rebate Programs

Several exchanges offer rebate programs that effectively reduce net fees:

- **OKX**: Up to 40% rebate on taker fees for VIP2+ accounts
- **Binance**: Referral rebates (~20-40% of fees returned)
- **Bybit**: Maker rebate programs for market makers

Rebates are typically paid in the exchange's native token or as a credit,
and may have lockup or vesting periods.

## Recommended Fee Tier Configuration

For Milestone A simulation, we recommend the following tier scenarios:

### Conservative (Baseline)
```
Scenario: REGULAR_TAKER
  execution_mode: TAKER
  taker_fee_bps: 4.0
  maker_fee_bps: 2.0
  Note: Current default, no optimization
```

### Realistic Minimum (VIP1+BNB)
```
Scenario: VIP1_BNB_MAKER
  execution_mode: MAKER
  taker_fee_bps: 4.0
  maker_fee_bps: 1.44  # VIP1 maker (1.6bp) * 0.9 (BNB discount)
  maker_fill_probability: 0.7
  Note: Achievable at $3M/month volume
```

### Target (VIP2+BNB+HYBRID)
```
Scenario: VIP2_BNB_HYBRID
  execution_mode: HYBRID
  taker_fee_bps: 3.15  # VIP2 taker (3.5bp) * 0.9 (BNB discount)
  maker_fee_bps: 1.26  # VIP2 maker (1.4bp) * 0.9 (BNB discount)
  maker_fill_probability: 0.7
  Note: Achievable at $6M/month volume
```

## Implementation Plan

1. Add `fee_tier` configuration to `SimulationProfile` (or pass via `execution_mode` in cost model)
2. Wire through `total_cost_r()`, `engine.py`, `action_selector.py`
3. Add CLI/config support for selecting fee tier
4. Evaluate net R impact across SWING/SCALP modes with each scenario

## Impact Estimate

| Scenario | Entry Fee | Exit Fee | Round Trip | Net R Impact (vs baseline) |
|----------|-----------|----------|------------|---------------------------|
| Regular Taker | 4.0 bp | 4.0 bp | 8.0 bp | baseline |
| VIP1+BNB Maker (70% fill) | 2.6 bp | 2.6 bp | 5.2 bp | +2.8 bp |
| VIP2+BNB HYBRID | 1.26 bp | 3.15 bp | 4.41 bp | +3.6 bp |
| VIP2+BNB Maker (70% fill) | 1.89 bp | 1.89 bp | 3.78 bp | +4.2 bp |

For SWING mode with typical 1.0R trades, a 4 bp reduction in round-trip fees
translates to approximately +0.04R per trade, or approximately 5-8%
improvement in net R over a sample of 100+ trades.

## Related

- [cost_model.md](cost_model.md) — authoritative cost model documentation
- [profiles.md](profiles.md) — mode-specific simulation profiles
- [cost_model.md#execution-modes](cost_model.md#execution-modes) — execution mode semantics
