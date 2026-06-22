# Unit Economics — V7 Policy Critic

## 1. Per-Trade Economics

### Baseline (No Critic)

| Component | Formula | Typical Value |
|-----------|---------|---------------|
| Gross expected return | E[realized_r_gross] | +0.25R |
| Fee cost | fee_cost_r (taker 4bps both sides) | -0.05R |
| Slippage cost | slippage_cost_r (1bps vol-adjusted) | -0.02R |
| Net expected return | realized_r_net = gross - fee - slippage | +0.18R |
| Funding cost | DEFERRED (spot-only) | 0 (for now) |
| **Net per trade** | | **+0.18R** |

### With Critic (Base Scenario)

| Component | Impact |
|-----------|--------|
| Gross expected return | +0.05R improvement (better trade selection) |
| Sizing adjustment | -0.01R (smaller positions on uncertain trades reduces variance) |
| Cost savings | +0.003R (fewer trades → fewer fees) |
| **Net improvement per trade** | **+0.043R** |

## 2. Cost Structure

### Fixed Costs (per year)

| Item | Cost | Notes |
|------|------|-------|
| Engineering (1-2 FTE) | $100K-$200K | Phases 2-6 |
| Training compute | $5K-$20K | XGBoost on CPU, not GPU-hungry |
| Shadow storage (PostgreSQL) | $1K-$5K | Additional replay buffer rows |
| Monitoring/Observability | $2K-$5K | Dashboards, alerts |
| **Total fixed** | **$108K-$230K** | |

### Variable Costs (per trade)

| Item | Cost | Notes |
|------|------|-------|
| Critic inference latency | <10ms | Negligible on CPU |
| Additional DB writes | ~1KB per decision | Negligible |
| **Total variable** | **Negligible** | |

### Cost per Vetoed Trade

When the critic recommends VETO_TO_NO_TRADE:
- The trade is not executed → fees and slippage are saved
- But: potential profit is also foregone
- Net: depends on whether the vetoed trade would have been profitable

## 3. Margin Analysis

### Profit Margin per Trade (Base Scenario)

```
Revenue per trade = Capital × Net expected return
                 = $1,000 × 0.223R = $223

Cost per trade (fees + slippage) = $1,000 × 0.07R = $70

Gross margin per trade = $223 - $70 = $153

Critic contribution per trade = $1,000 × 0.043R = $43
Critic margin = $43 / $223 = 19% of gross margin
```

## 4. Scalability

| Dimension | Current Assumption | Scaling Note |
|-----------|-------------------|-------------|
| Symbols | ~20 (universe) | Critic trains per-mode, not per-symbol; scales well |
| Modes | 3 (SWING, SCALP, AGGRESSIVE) | SCALP/AGGRESSIVE on HOLD; SWING first |
| Trade frequency | ~3/day (SWING 4h) | Higher frequency = more data = better training |
| Capital per trade | $1,000 (paper baseline) | Scales linearly; critic does not constrain capital |
| Total AUM | Variable | Critic does not manage portfolio allocation |

## 5. Unit Economics Caveats

- **All per-trade values are expected values** — realized values have high variance
- **Win rate and avg return are regime-dependent** — unit economics vary by market condition
- **Funding costs (DEFERRED) will reduce margins** — perp trading will have lower net expectancy
- **Scaling capital per trade increases risk linearly** — critic does not replace risk management
- **Infrastructure costs are estimates** — actual costs depend on engineering team composition and cloud pricing
