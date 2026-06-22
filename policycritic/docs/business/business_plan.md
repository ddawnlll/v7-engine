# Business Plan — V7 Policy Critic

## 1. Business Objective

Build an advisory Policy Critic that improves V7's net trade expectancy by 0.05R-0.15R per trade (base scenario) through context-aware risk assessment, without replacing deterministic safety gates, without holding final trade authority, and without requiring online RL exploration in live markets.

## 2. Strategic Thesis

**Why build this now**: V7's deterministic gates are necessary but insufficient. They apply fixed thresholds regardless of context. A regime-transition trade with 0.55 confidence has fundamentally different risk from a calm-trend trade with 0.55 confidence — but gates treat them identically. The critic fills this gap with learned, context-aware risk assessment.

**Why advisory, not autonomous**: Safe RL literature (Alshiekh et al. 2018) proves learned components must sit under deterministic shields. V7's architecture follows this exactly. The critic advises; gates decide.

**Why not give RL final authority**: RL agents overfit backtests (DSR/PBO), exploit reward misspecification (reward hacking), and fail silently under regime shift. Deterministic gates are verifiable; RL policies are not. The critic adds value without replacing verifiable safety.

## 3. Strategic Rationale

### The Problem We're Solving

V7's deterministic policy gates apply fixed thresholds (min confidence = 0.55, min expected-R = 0.5) to every trade decision regardless of context. A 0.55-confidence trade in a calm trending regime has a fundamentally different risk profile from a 0.55-confidence trade in a high-volatility transition regime — but the gates treat them identically.

The Policy Critic adds **context-aware risk assessment** without replacing the gates. It can recommend NO_TRADE when deterministic thresholds pass but the combined risk factors suggest negative expected value.

### Why This Matters Financially

In a system doing N trades per period, even a small improvement in trade selection quality compounds significantly:

- **Avoiding negative-expectancy trades**: If the critic correctly prevents 5% of trades that would have lost 0.5R each, on 1000 trades/year with $1000/trade, that's $25,000/year in avoided losses.
- **Confidence-adjusted sizing**: If the critic correctly downweights overconfident trades, position sizing is more accurately calibrated to true edge — reducing drawdowns without proportionally reducing returns.
- **Regime-conditional edge**: The critic can learn that certain patterns work in trending regimes but not in ranging — information the gates cannot express.

## 2. Staged Investment

| Phase | Investment | Expected Output | Risk Level |
|-------|-----------|----------------|------------|
| 0: Research & Design | 2-3 weeks (docs only) | Design package, business case | Zero (no code) |
| 1: Observability & Schema | 2-3 days | Contract registered | Minimal |
| 2: Replay Buffer | 3-4 weeks | Training data infrastructure | Low |
| 3: Offline Training | 12-18 weeks | V2 + V3 critic models | Medium |
| 4: Shadow Runtime | 2-3 weeks | Shadow-only critic in scan loop | Low |
| 5: Guarded Influence | 8-12 weeks | Advisory influence in SWING | Medium-High |
| 6: Business Validation | 12+ weeks | Evidence package for live consideration | Medium |

**Total estimated investment**: 40-55 weeks of engineering time across all phases. Phases 0-4 are relatively low-risk (shadow-only, no live influence). Phases 5-6 carry real financial risk and require human approval at each sub-stage.

## 3. ROI Logic (Scenario-Based)

### Conservative Scenario

- Critic identifies and avoids 2% of losing trades
- No improvement in sizing accuracy
- Infrastructure cost: $X (engineering time)
- Running cost: minimal (inference on existing hardware)
- Breakeven: depends on trade volume and size

### Base Scenario

- Critic avoids 5% of losing trades (DSR significant)
- Confidence downweight improves sizing calibration
- Net expectancy improvement: +0.05R per trade
- On 1000 trades/year at $1000/trade: +$50,000/year expected
- Breakeven within 12 months of Phase 5 deployment

### Aggressive Scenario (NOT COMMITTED)

- Critic avoids 10% of losing trades + improves sizing
- Net expectancy improvement: +0.10R per trade
- Requires: excellent replay buffer coverage, well-calibrated IQL, favorable regime conditions
- Probability: low — do not budget against this scenario

## 4. What Data Is Needed Before Real Profitability Claims

1. **Shadow comparison**: ≥ 90 days of critic verdicts vs actual outcomes
2. **DSR significance**: p < 0.05 on improvement over baseline
3. **PBO**: < 0.10
4. **Per-regime breakdown**: No single-regime degradation
5. **Drawdown profile**: No worsening vs baseline
6. **Transaction cost impact**: Critic's influence on trade frequency must not increase total costs disproportionately

## 5. Go/No-Go Decision Points

| Gate | Decision | Criteria |
|------|---------|----------|
| Phase 0→1 | Proceed to contract | Docs approved by partner |
| Phase 2→3 | Proceed to training | ≥ 1000 tuples, data quality validated |
| Phase 3→4 | Deploy shadow critic | V2 DSR/PBO passed |
| Phase 4→5 | Enable guarded influence | ≥ 30 days stable shadow, human approval |
| Phase 5→6 | Business validation | ≥ 60 days guarded influence, no safety degradation |
| Phase 6→live | Live consideration | All metrics maintained ≥ 90 days, human approval |

## 6. Team Requirements

| Role | Phase Involvement |
|------|------------------|
| ML/RL Engineer | Phases 2-6 (replay buffer, training, evaluation) |
| Backend Engineer | Phases 2, 4-6 (infrastructure, runtime integration) |
| Quant/Trader | Phases 0-6 (reward design, evaluation, business validation) |
| DevOps | Phases 4-6 (deployment, monitoring, kill-switch) |
| Risk Manager | Phases 5-6 (live influence approval, ongoing monitoring) |

## 7. Key Assumptions (To Be Validated)

- Historical trading data contains enough signal for IQL to learn useful Q-functions
- Simulation engine's `realized_r_net` is an accurate proxy for live trading costs
- Replay buffer can be populated without disrupting existing scan loop
- XGBoost expectile/quantile regression converges on financial data
- Conformal calibration provides approximately valid coverage despite exchangeability violation
- Market regime classification is stable enough for per-regime critic training

## 8. Milestone-Based Investment Plan

| Milestone | Phase | Cost Type | Expected Evidence | Decision | Funding Level | Kill Condition |
|----------|-------|-----------|-------------------|----------|--------------|----------------|
| Design lock | 0 | Time only (2-3 weeks) | Docs package approved | Proceed to contract | Zero (no code) | Partner rejection |
| Contract registered | 1 | Time only (2-3 days) | Schema validated | Proceed to buffer | Minimal | Schema rejection |
| Buffer populated | 2 | Eng (3-4 weeks) | ≥ 1000 tuples, no leakage | Proceed to training | 1 FTE | Data quality failure |
| V2 trained | 3A | Eng + Compute (4-6 weeks) | DSR p<0.05, PBO<0.10 | Proceed to OPE | 1-2 FTE | DSR/PBO failure |
| OPE validated | 3B | Eng (3-4 weeks) | FQE CI overlaps realized | Proceed to IQL | 1-2 FTE | FQE divergence |
| V3 trained | 3C | Eng + Compute (8-12 weeks) | IQL FQE pass, CQL bounded | Deploy shadow | 2 FTE | Bellman divergence |
| Shadow running | 4 | Eng (2-3 weeks) | 30 days stable, zero influence | Consider influence | 2 FTE | Stability failure |
| Guarded influence | 5 | Eng + Risk (8-12 weeks) | 60 days, DSR maintained | Consider validation | 2-3 FTE | Safety degradation |
| Business validated | 6 | Eng + Risk (12+ weeks) | ≥ 90 days, all metrics held | Live consideration | 3 FTE | Any metric failure |

## 9. What to Build Now, What to Postpone

### Build Now (Phase 0 — current)
- Complete docs/design package
- Problem statement, research, business case, quality scoring
- Independent AI review packet

### Build Soon (Phases 1-2)
- PolicyCriticReview contract
- Replay buffer infrastructure

### Build Later (Phases 3-4)
- V2 supervised critic training
- OPE/FQE evaluation infrastructure
- V3 IQL critic training
- Shadow runtime integration

### Postpone (Phases 5-6, conditional)
- Guarded influence (requires shadow evidence + human approval)
- V4 constrained optimizer (requires V3 stable ≥ 60 days)
- SCALP/AGGRESSIVE influence (permanently HOLD without independent evidence)
- Live promotion (requires all gates + human approval)

## 10. What Would Kill the Project

The Policy Critic project should be **killed or indefinitely suspended** if:

1. **Replay buffer cannot be populated**: Without (s,a,r,s',terminal) tuples, no learning is possible
2. **DSR never reaches p < 0.05**: After ≥ 90 days shadow, improvement not statistically significant → critic adds complexity without proven value
3. **PBO exceeds 0.20**: Critic selection is likely overfit → redeploying would be irresponsible
4. **Any safety metric degrades and cannot be fixed**: Drawdown, max loss, or circuit breaker frequency worsens
5. **Business case invalidated**: Infrastructure + engineering cost exceeds measured value for ≥ 2 consecutive quarters
6. **Regime shift makes critic permanently stale**: Market structure changes fundamentally → retraining doesn't recover performance
7. **Human approval denied for Phase 5+**: Without approval, critic remains shadow-only → no live value

## 11. Stakeholder Map

| Stakeholder | Role | Decision Authority | Information Needs |
|------------|------|-------------------|------------------|
| Partner/PM | Resource allocation, phase approval | Phase transitions, budget | ROI estimates, milestone progress |
| Quant/Trader | Reward design, evaluation | Reward function, evaluation criteria | Critic performance metrics |
| ML Engineer | Training, calibration | Model architecture, training config | Data quality, training metrics |
| Backend Engineer | Infrastructure, runtime | Integration design | Latency, reliability metrics |
| Risk Manager | Safety, drawdown limits | Live influence approval | Risk metrics, violation reports |
| Operator | Dashboard, monitoring | Operational decisions | Critic verdicts, divergence alerts |
