# Profitability Calculation — V7 Policy Critic

> **Warning**: All calculations are scenario-based estimates. No profitability is claimed or promised. Shadow evidence is required before any real profit impact can be asserted. This document describes what COULD happen IF the critic works as designed — it does not describe what WILL happen.

## 1. Executive Summary

The Policy Critic is an advisory component — it does not trade, execute, or allocate capital. Its value is in **improving trade selection quality** by recommending NO_TRADE for negative-expectancy situations and downweighting confidence on uncertain trades. The expected value is the difference between: (a) the PnL of trades the system would have taken without the critic, and (b) the PnL of trades the system takes with the critic's recommendations enacted. This document models that difference under conservative, base, aggressive, and failure scenarios.

## 2. What Profitability Means for an Advisory Policy Critic

The critic does not generate PnL directly. It changes which trades are taken and at what size. Profitability means:

- **Fewer losing trades** (correct vetoes)
- **Smaller positions on uncertain trades** (correct downweights)
- **NOT** fewer winning trades (incorrect vetoes = missed opportunity cost)
- **NOT** larger positions on bad trades (incorrect allows = direct loss)

The net value is the balance of avoided losses minus missed gains minus infrastructure cost.

## 3. Value Mechanisms

| # | Mechanism | How It Works | Measurable As |
|---|----------|-------------|---------------|
| 1 | **Avoided bad trades** | Critic vetoes trades that would have lost money | Sum of realized losses on vetoed trades (shadow) |
| 2 | **Reduced sizing on uncertain trades** | Critic downweights confidence → smaller positions | Reduced drawdown contribution from downweighted trades |
| 3 | **Regime-conditional selection** | Critic learns regime-specific risk patterns | Per-regime expectancy improvement |
| 4 | **Cost savings** | Fewer trades → fewer fees/slippage | Total cost reduction |
| 5 | **Risk-adjusted return improvement** | Lower drawdown → higher risk-adjusted return | Sharpe/DSR improvement |

## 4. Expected Value Model

### Gross Expected PnL (No Critic)
```
E[PnL_baseline] = N × C × (w × R_win + (1-w) × R_loss)
```
Where:
- N = number of trades per period
- C = capital per trade
- w = win rate
- R_win = average winning trade return (R-multiples, positive)
- R_loss = average losing trade return (R-multiples, negative)

### Net Expected PnL (No Critic)
```
E[PnL_net_baseline] = E[PnL_baseline] - N × C × (fee_r + slippage_r) - Fixed_Costs
```

### Critic Value Add
```
Critic_Value = Avoided_Losses - Missed_Gains - False_Allow_Losses + Sizing_Benefit + Cost_Savings - Critic_Costs
```

## 5. Avoided-Loss Model (VETO_TO_NO_TRADE)
```
Avoided_Losses = N_veto × C × TP_veto × |R_loss|
```
Where:
- N_veto = number of critic vetoes
- TP_veto = true positive rate of vetoes (vetoed trades that WOULD have lost)
- |R_loss| = average loss magnitude of correctly vetoed trades

### Missed-Gain Cost (False Vetoes)
```
Missed_Gains = N_veto × C × (1 - TP_veto) × R_win_correctly_vetoed
```
False vetoes are trades the critic blocked that would have been profitable — the opportunity cost.

## 6. Confidence-Downweight Model (DOWNWEIGHT_CONFIDENCE)
```
Sizing_Benefit = N_dw × C × (1 - adj) × ((1 - w_dw) × |R_loss_dw|)  [loss reduction benefit]
Missed_DW_Gain = N_dw × C × (1 - adj) × (w_dw × R_win_dw)            [gain reduction cost]
```
Where adj = confidence_adjustment_factor (e.g., 0.6 means 40% size reduction).

## 7. False Positive / False Negative Economics

| Event | Definition | Economic Impact | Measurement |
|-------|-----------|----------------|-------------|
| **True Positive Veto** | Critic vetoes → trade would have lost | +avoided loss | Shadow comparison |
| **False Positive Veto** | Critic vetoes → trade would have won | −missed profit | Shadow comparison |
| **True Positive Allow** | Critic allows → trade wins | +realized profit | Shadow comparison |
| **False Negative Allow** | Critic allows → trade loses | −realized loss | Shadow comparison |
| **True Positive Downweight** | Critic downweights → trade loses | +reduced loss | Shadow comparison |
| **False Positive Downweight** | Critic downweights → trade wins | −reduced gain | Shadow comparison |

### Net Critic Accuracy
```
Critic_Accuracy = (TP_veto + TP_allow + TP_dw) / Total_Decisions
Critic_Net_Value = Σ(Correct_Decision_Values) - Σ(Incorrect_Decision_Costs)
```

## 8. Core Profitability Formula (Consolidated)
```
Expected Net PnL (per period) =
    Number of trades
    × Capital per trade
    × (Expected return per winning trade × Win rate
       - Expected loss per losing trade × (1 - Win rate))
    + Avoided_Losses_from_Critic
    - Missed_Gains_from_Critic
    + Sizing_Benefit_from_Critic
    - Total fees
    - Total slippage
    - Total funding costs
    - Infrastructure costs
    - Critic_Engineering_Costs
```

## 9. Scenario Analysis

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

### Failure Scenario (Critic degrades performance)

| Metric | Baseline | With Critic (failing) | Delta |
|--------|---------|----------------------|-------|
| Trades/year | 1000 | 900 (100 vetoed) | -100 |
| True positive veto rate | N/A | 40% (60% false vetoes) | — |
| Win rate | 50% | 48% (vetoing winners) | -2% |
| Net expectancy | +0.25R | +0.15R | **-0.10R** |
| Net PnL | +$190,000 | +$140,000 | **-$50,000** |

Failure scenario: critic incorrectly vetoes winning trades while allowing losing trades. This is why shadow evidence is mandatory before any live influence.

## 10. Sensitivity Matrix

| Variable | Direction | Risk if Wrong | Measurement | Mitigation |
|----------|----------|--------------|-------------|-----------|
| Win rate | ↑ improves critic value | Overestimated → critic appears better than real | Shadow comparison | Conservative prior; shadow evidence |
| Average win (R_win) | ↑ increases missed-gain cost of false vetoes | Overestimated → false vetoes look more costly | Trade outcome data | Use conservative R_win estimates |
| Average loss (R_loss) | ↑ increases avoided-loss value | Underestimated → true vetoes look less valuable | Trade outcome data | Use conservative R_loss estimates |
| Trade count (N) | ↑ amplifies all effects | Both good and bad effects amplified | Scan frequency | Critic degrades gracefully at all volumes |
| Capital per trade (C) | ↑ amplifies all effects linearly | Capital scaling increases risk | Position sizing policy | Critic does not control C |
| Fee rate | ↑ reduces net expectancy | Critic may overtrade if fees underestimated | Simulation cost model | Use conservative fee estimates |
| Slippage rate | ↑ reduces net expectancy | Volatility-dependent; critic may miss this | Simulation cost model | Include vol-adjusted slippage |
| Funding rate | ↑ reduces net expectancy | DEFERRED — not in current model | Future implementation | Spot-only valid until funding implemented |
| Bad-trade avoid rate (TP_veto) | ↑ directly improves critic value | Overestimated → critic appears better than real | Shadow comparison | Requires ≥ 90 days shadow data |
| False veto rate (FP_veto) | ↑ directly reduces critic value | Underestimated → missed profit hidden | Shadow comparison | Bounded veto rate check |
| False allow rate (FN_allow) | ↑ directly reduces critic value | Underestimated → losses hidden | Shadow comparison | Per-trade outcome tracking |
| Regime shift | Changes all parameters simultaneously | Critic trained on regime A, deployed in regime B | Per-regime monitoring | Auto-degrade on regime mismatch |
| Model drift | Degrades critic accuracy over time | Slow degradation may go unnoticed | Staleness monitoring | Periodic retraining schedule |

## 11. Detailed Break-Even Analysis

### Engineering Cost Break-Even

```
Break-even avoid rate = (Annual_Eng_Cost + Annual_Infra_Cost) / (N × C × |R_loss|)
```

| Cost Scenario | Annual Cost | Trades/Year | Capital/Trade | Avg Loss | Breakeven Avoid Rate |
|--------------|------------|-------------|--------------|----------|----------------------|
| Minimal | $50,000 | 1000 | $1,000 | -1.0R | 5.0% (50 trades) |
| Moderate | $150,000 | 1000 | $1,000 | -1.0R | 15.0% (150 trades) |
| Full | $300,000 | 1000 | $1,000 | -1.0R | 30.0% (300 trades) |

### False Veto Tolerance

```
Max_Acceptable_FP_Rate = (Net_Benefit_per_True_Veto) / (Cost_per_False_Veto)
```

If a true veto saves |R_loss| = 1.0R and a false veto costs R_win = 1.5R:
- Each true veto must be accompanied by ≤ 0.67 false vetoes to break even
- Critic must have TP_veto rate ≥ 60% to be net positive

## 12. Drawdown-Adjusted Expected Value

```
Drawdown_Adjusted_EV = Net_Expected_PnL - λ × Expected_Max_Drawdown
```

Where λ is a risk-aversion parameter. A critic that reduces drawdown by 10% but reduces returns by 2% may still be valuable for risk-constrained traders.

## 13. What Invalidates the Business Case

The Policy Critic business case is **invalidated** if any of these occur:

1. **DSR p ≥ 0.05 after ≥ 90 days shadow**: Improvement not statistically significant → critic adds complexity without proven value
2. **PBO ≥ 0.20**: High probability the critic's apparent improvement is backtest overfitting
3. **Per-regime degradation**: Critic improves overall but worsens performance in any single regime → unacceptable risk concentration
4. **Drawdown worsening**: Any drawdown metric (max, duration, frequency) significantly worse than baseline
5. **False veto rate > 30%**: Critic blocks too many good trades → net negative value
6. **Infrastructure cost exceeds value**: Engineering + infra cost > measured improvement
7. **Live shadow OPE diverges from offline estimates**: OPE overestimated real-world performance → critic not trustworthy

## 14. Why This Is Not a Profit Guarantee

```
Policy Critic does not guarantee profit.
Current docs cannot prove actual profitability.
Actual profitability requires:
  - Shadow data (≥ 90 days)
  - Realized outcomes from simulation engine
  - Cost-adjusted simulation (fee + slippage + funding)
  - FQE/OPE validation
  - DSR/PBO statistical significance
  - Drawdown analysis
  - Paper/live evidence
  - Multi-regime validation
None of these exist today.
```

## 15. Recommended Next Measurements

| Measurement | Phase | Purpose |
|------------|-------|---------|
| Shadow veto rate baseline | 4 | Establish normal veto frequency |
| Per-veto outcome comparison | 4-5 | Measure TP/FP veto rates |
| Per-downweight drawdown impact | 5 | Measure sizing benefit |
| Monthly DSR trend | 5-6 | Track statistical significance over time |
| Regime-conditional breakdown | 5-6 | Detect per-regime degradation |
| Cost impact analysis | 6 | Verify fees/slippage not increased disproportionately |
| Live shadow vs offline OPE comparison | 6 | Validate OPE accuracy |
