# Unit Economics — V7 Policy Critic

## 1. Per-Signal Economics

Every scan decision produces a signal. The critic reviews each signal. Unit economics start here.

| Metric | Definition | Typical Value | Source |
|--------|-----------|---------------|--------|
| Signals/day (SWING 4h, 20 symbols) | Scan decisions per day | ~60 (3/mode/symbol) | Scan runtime |
| Signals reviewed by critic | 100% of non-hard-blocked signals | ~60/day | Critic adapter |
| Critic inference cost per signal | CPU inference time × cost | <$0.0001 | Negligible |
| Shadow storage per signal | PolicyCriticReview row size | ~2KB | PostgreSQL |
| **Cost per signal** | | **<$0.001** | |

## 2. Per-Trade Economics

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

## 3. Per-Verdict Economics

### VETO_TO_NO_TRADE
| Outcome | Economic Impact | Measurement |
|---------|----------------|-------------|
| True positive veto (trade would have lost) | +|R_loss| avoided per veto | Shadow: compare vetoed vs would-have-been outcome |
| False positive veto (trade would have won) | -R_win missed per veto | Shadow: compare vetoed vs would-have-been outcome |
| **Net veto value** | TP_veto × |R_loss| - FP_veto × R_win | Requires ≥ 90 days shadow data |

### DOWNWEIGHT_CONFIDENCE
| Outcome | Economic Impact | Measurement |
|---------|----------------|-------------|
| Downweighted losing trade | +(1-adj) × |R_loss| saved | Position size comparison |
| Downweighted winning trade | -(1-adj) × R_win missed | Position size comparison |
| **Net downweight value** | Benefit on losers - Cost on winners | Requires per-trade sizing comparison |

### ALLOW (Critic Agrees)
| Outcome | Economic Impact |
|---------|----------------|
| Trade wins | Baseline profit (critic correctly did not interfere) |
| Trade loses | Baseline loss (critic failed to detect — false negative allow) |

## 4. False Veto / False Allow Cost Analysis

### False Veto Cost (per occurrence)
```
Cost_FP_veto = C × R_win_foregone
```
A $1,000 trade that would have won +1.5R costs $1,500 in missed profit when falsely vetoed.

### False Allow Cost (per occurrence)
```
Cost_FN_allow = C × |R_loss_incurred|
```
A $1,000 trade that loses -1.0R costs $1,000 when falsely allowed.

### Required Accuracy for Net Positive Value
```
TP_veto × |R_loss| > FP_veto × R_win + FN_allow × |R_loss|
```
With R_win=1.5R, R_loss=-1.0R: critic needs TP_veto / FP_veto > 1.5 to be net positive on vetoes alone.

## 5. Cost Structure

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

### Per-Model-Run Cost

| Item | Cost | Frequency |
|------|------|-----------|
| Full retraining (IQL + CQL) | ~$50-$200 compute | Quarterly |
| Conformal recalibration | ~$10-$50 compute | Monthly |
| OPE/FQE evaluation | ~$20-$100 compute | Per retraining |
| **Annual training cost** | **$500-$2,000** | |

## 6. Cost Hierarchy

```
Level 1: Per-signal (critic review) → negligible
Level 2: Per-trade (executed with critic influence) → measured in R-multiples
Level 3: Per-model-run (training) → $50-$200 per run
Level 4: Per-phase (engineering) → $50K-$300K per phase
Level 5: Per-year (total) → $100K-$300K
```

## 7. Scalability

| Dimension | Current Assumption | Scaling Note |
|-----------|-------------------|-------------|
| Symbols | ~20 (universe) | Critic trains per-mode, not per-symbol; scales well |
| Modes | 3 (SWING, SCALP, AGGRESSIVE) | SCALP/AGGRESSIVE on HOLD; SWING first |
| Trade frequency | ~3/day (SWING 4h) | Higher frequency = more data = better training |
| Capital per trade | $1,000 (paper baseline) | Scales linearly; critic does not constrain capital |
| Total AUM | Variable | Critic does not manage portfolio allocation |

## 8. Minimum Telemetry Fields for Unit Economics

| Field | Source | Required Before Phase |
|-------|--------|----------------------|
| signal_id | Scan runtime | 4 (shadow) |
| proposed_action | AlphaForge/V6 | 4 |
| proposed_confidence | AlphaForge/V6 | 4 |
| critic_verdict | PolicyCriticReview | 4 |
| confidence_adjustment_factor | PolicyCriticReview | 5 |
| realized_r_net | SimulationOutput | 4 |
| mae_r | SimulationOutput | 4 |
| exit_reason | TradeOutcome | 4 |
| regime_label | Deterministic context | 4 |
| fee_cost_r | SimulationOutput | 4 |
| slippage_cost_r | SimulationOutput | 4 |

## 9. Unit Economics Caveats

- **All per-trade values are expected values** — realized values have high variance
- **Win rate and avg return are regime-dependent** — unit economics vary by market condition
- **Funding costs (DEFERRED) will reduce margins** — perp trading will have lower net expectancy
- **Scaling capital per trade increases risk linearly** — critic does not replace risk management
- **Infrastructure costs are estimates** — actual costs depend on engineering team composition and cloud pricing
- **False veto/allow costs can only be measured in shadow** — no live measurement until Phase 5+
- **Critic value is bounded by baseline edge** — if the baseline system has zero edge, no critic can create edge from nothing
