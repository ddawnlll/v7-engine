# Profitability Calculation — V7 Policy Critic

> **Warning**: All calculations are scenario-based estimates. No profitability is claimed or promised. Shadow evidence is required before any real profit impact can be asserted.

## 1. Core Profitability Formula

```
Expected Net PnL (per period) =
    Number of trades
    × Capital per trade
    × (Expected return per winning trade × Win rate
       - Expected loss per losing trade × (1 - Win rate))
    - Total fees
    - Total slippage
    - Total funding costs
    - Infrastructure costs
```

## 2. Critic Impact Channels

The Policy Critic affects profitability through three channels:

### Channel A: Trade Avoidance (VETO_TO_NO_TRADE)
```
Avoided Loss = N_veto × Capital_per_trade × E[loss | vetoed]
```
The critic recommends NO_TRADE for trades it identifies as negative-expectancy. If those trades would have lost money, the avoided loss is profit preserved.

### Channel B: Confidence Adjustment (DOWNWEIGHT_CONFIDENCE)
```
Sizing Improvement = N_downweight × Capital_per_trade × (1 - adjustment_factor) × E[return | downweighted]
```
By reducing position size on uncertain trades, the critic reduces variance and drawdown without proportionally reducing returns.

### Channel C: Regime-Conditional Edge
```
Regime Edge = Σ_regime N_regime × Capital × (E[return | critic, regime] - E[return | baseline, regime])
```
The critic may learn regime-specific patterns that improve per-regime expectancy.

## 3. Scenario Analysis

### Assumptions (for all scenarios)
- 1000 trades per year
- $1,000 capital per trade
- Baseline: 50% win rate, avg win +1.5R, avg loss -1.0R
- Baseline net expectancy: 0.5 × 1.5 + 0.5 × (-1.0) = +0.25R per trade
- Baseline annual: 1000 × $1000 × 0.25R = +$250,000 (gross, before costs)
- Costs: 5bps fee + 1bps slippage = 6bps per trade = $60/trade × 1000 = $60,000/year
- Baseline net: $250,000 - $60,000 = $190,000/year

### Conservative Scenario (Critic avoids 2% of losing trades)

| Metric | Baseline | With Critic | Delta |
|--------|---------|-------------|-------|
| Trades/year | 1000 | 980 (20 vetoed) | -20 |
| Win rate | 50% | 51% (losers avoided) | +1% |
| Avg win | +1.5R | +1.5R | 0 |
| Avg loss | -1.0R | -1.0R | 0 |
| Gross PnL | +$250,000 | +$250,000 (same gross, fewer trades) | $0 |
| Costs | $60,000 | $58,800 | -$1,200 |
| Net PnL | +$190,000 | +$191,200 | **+$1,200** |

Conservative scenario is essentially cost-neutral. The critic adds value primarily through avoided costs on vetoed trades.

### Base Scenario (Critic avoids 5% of losing trades + sizing improvement)

| Metric | Baseline | With Critic | Delta |
|--------|---------|-------------|-------|
| Trades/year | 1000 | 950 (50 vetoed) | -50 |
| Win rate | 50% | 52% | +2% |
| Avg win (sized trades) | +1.5R | +1.4R (smaller on downweighted) | -0.1R |
| Avg loss (sized trades) | -1.0R | -0.7R (smaller on downweighted) | +0.3R |
| Net expectancy | +0.25R | 0.52×1.4 + 0.48×(-0.7) = +0.392R | +0.142R |
| Gross PnL | +$250,000 | +$372,400 | **+$122,400** |
| Costs | $60,000 | $57,000 | -$3,000 |
| Net PnL | +$190,000 | +$315,400 | **+$125,400** |

Base scenario requires: DSR significant, sustained shadow evidence, no drawdown worsening.

### Aggressive Scenario (Critic avoids 10% + optimal sizing)

| Metric | Baseline | With Critic | Delta |
|--------|---------|-------------|-------|
| Trades/year | 1000 | 900 (100 vetoed) | -100 |
| Win rate | 50% | 54% | +4% |
| Net expectancy | +0.25R | +0.50R | +0.25R |
| Net PnL | +$190,000 | +$440,000 | **+$250,000** |

**DO NOT BUDGET AGAINST THIS.** Aggressive scenario requires near-perfect critic calibration, favorable market regimes, and sustained edge — unlikely to persist.

## 4. Break-Even Analysis

```
Break-even improvement = (Infrastructure cost + Ongoing cost) / (Trades/year × Capital/trade)
```

| Cost Scenario | Annual Cost | Breakeven R improvement |
|--------------|------------|------------------------|
| Minimal (1 engineer, existing infra) | $50,000 | +0.05R |
| Moderate (2 engineers, dedicated infra) | $150,000 | +0.15R |
| Full (3+ engineers, separate training infra) | $300,000 | +0.30R |

## 5. Drawdown Impact Sensitivity

The critic's confidence downweight reduces position size on uncertain trades. This directly impacts drawdown:

```
Max Drawdown Reduction ≈ E[confidence_adjustment | downweighted] × Baseline drawdown contribution of downweighted trades
```

If 20% of trades are downweighted by avg 0.6x and those trades contribute 25% of drawdown:
- Drawdown reduction ≈ 0.4 × 25% = 10% reduction in drawdown from those trades
- Overall drawdown reduction depends on correlation structure

## 6. What Data Is Required Before Real Claims

1. **Shadow comparison**: ≥ 90 days, critic verdicts vs actual outcomes
2. **Statistical significance**: DSR p < 0.05 on net improvement
3. **No overfitting**: PBO < 0.10
4. **Regime robustness**: Per-regime breakdown shows no degradation
5. **Cost analysis**: Total transaction costs do not increase disproportionately
6. **Drawdown profile**: No worsening on any drawdown metric
7. **Live shadow**: OPE estimates approximately equal realized outcomes

## 7. Important Caveats

- **All numbers are illustrative** — actual outcomes depend on market conditions
- **Past performance ≠ future results** — even with DSR/PBO validation
- **Regime shifts can eliminate edge** — a critic trained in one regime may fail in another
- **Costs can exceed edge** — funding, slippage, and spread can consume critic's alpha
- **No live claims without live evidence** — backtest profitability is not live profitability
