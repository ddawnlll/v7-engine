# AlphaForge Research Plan — 2026-07-06

> **Planner:** AlphaForge Research Factory v1.0
> **Period:** 2026-07-06 to 2026-07-13 (sprint window)
> **State:** Baseline establishment — `data/runs/` is empty

---

## Executive Summary

`data/runs/` has zero experiment outputs. The pipeline infrastructure exists (feature engine, label builder, simulation authority, XGBoost trainer) but has never produced a tracked experiment artifact. The professional quant dossier (`reports/research/alphaforge_professional_quant_dossier.md`) catalogues 11+ authoritative sources with concrete P0/P1 action items, **none of which are yet implemented in the pipeline**.

This plan proposes **3 concrete research directions**, ordered by impact-per-effort, each implementable in one night.

---

## Situational Assessment

### What Exists
| Component | Status | Path |
|-----------|--------|------|
| Feature engine | Mature | `alphaforge/src/alphaforge/features/` — 10 feature modules |
| Regime detection | Implemented | HMM, CUSUM, vol regimes, multi-symbol (`regime.py`) |
| Label generation | Built | `labels/builder.py`, `labels/adapter.py` |
| Simulation authority | Active | `simulation/authority.py` (SCALP profile only) |
| Training scripts | Written | `alphaforge/runs/phase3_feature_set_final.py` etc. |
| Experiment outputs | **EMPTY** | `data/runs/` — no tracked artifacts |
| Feature ablation | Script exists | `alphaforge/runs/feature_ablation.py` |
| Validator hardening | **NOT IMPLEMENTED** | V1-V10 rules from dossier |
| Cost-aware filtering | **NOT IMPLEMENTED** | V1/P0 |

### What is Missing (Gaps Identified)
- **Experiment tracking**: No canonical first experiment producing `data/runs/<ts>/` artifacts
- **Cost-aware execution**: No `expected_net_R > cost_per_trade_R` filter in the pipeline
- **Regime-conditional calibration**: Per-regime confidence bucket analysis not wired
- **Feature family correlation**: No cross-family IC/ICIR correlation matrix
- **Baseline library**: NO_TRADE, RANDOM, ALWAYS_LONG/SHORT baselines not computed
- **PBO/DSR**: Not integrated into validation pipeline

### Recent arxiv Signal (last 30 days — June/July 2026)

| Paper | ID | Relevance | Why It Matters |
|-------|----|-----------|----------------|
| **AlphaCrafter** — Multi-agent factor ensemble | 2605.05580 | High | Continuously adaptive factor ensemble; similar to AlphaForge's vision |
| **QuantaAlpha** — Evolutionary LLM alpha mining | 2602.07085 | High | Mutation/crossover for alpha factor discovery |
| **Hubble** — LLM alpha discovery with AST sandbox | 2604.09601 | High | 181 factors; 100% safety rate; evolutionary feedback |
| **Heads, Not Backbones** — Output head importance | 2606.30037 | Medium-High | For fat-tailed returns, the prediction head matters more than backbone |
| **BAVAR-BLED** — Bayesian VAR portfolio optimization | 2606.09104 | Medium | Sharpe 1.72 on DJIA; fat-tail aware allocation |
| **Regime-Conditional Dist. Comparison** | 2606.31251 | High | Framework for regime-conditional strategy comparison |
| **E2E Parametric Portfolio Policies** | 2607.00475 | Medium | Cross-asset futures timing with AI |
| **SBBTS** — Synthetic TS generation | 2604.07159 | Medium | Data augmentation for small-sample finance |
| **SOCK** — Differentiable conv features for TS generation | 2606.05138 | Low-Medium | Generative feature matching for small samples |
| **CryptoGAT** — Crypto TS forecasting | 2606.27670 | Medium | Time series models for crypto prediction bench |

---

## Direction 1: Cost-Aware Execution Threshold Optimization
**Priority:** HIGH | **Effort:** ~4 hours | **Corresponds to:** V1/P0

### Hypothesis
The primary performance bottleneck in the SCALP pipeline is not model accuracy but the **forecast→trade conversion layer**. Naive sign-based trading (buy if confidence > 0.55, sell if < 0.45) fails under realistic transaction costs (10 bps round-trip). Adding a cost-aware magnitude threshold that requires `expected_net_R > cost_per_trade_R` will improve net Sharpe more than any model architecture change.

### Source Evidence
- arXiv:2606.00060 (Bitcoin Trading Under Transaction Costs): "Naive sign-based strategies fail once transaction costs of ten basis points are imposed"
- AlphaCrafter (2605.05580): Trader agent performs dynamic position sizing with explicit cost constraints
- Dossier V1: Cost-aware filter not implemented → economic_score hard cap = 20

### Experiment Design

**Step 1: Baseline measurement**
```yaml
model: XGBoost (existing SCALP pipeline)
label: simulation-authority R-multiple
threshold: confidence > 0.55
cost: 10 bps round-trip (authority default)
metrics: net_sharpe, win_rate, avg_net_R, turnover, max_drawdown
```

**Step 2: Cost-aware filter sweep**
```yaml
parameters:
  confidence_threshold: [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
  cost_multiple_threshold: [1.0x, 1.5x, 2.0x, 2.5x, 3.0x]  # expected_net_R > N * cost_per_trade_R
cells: 7 × 5 = 35 combinations
protocol: walk-forward (same folds as baseline)
```

**Step 3: Analysis**
- Contour plot of net Sharpe over (confidence, cost_multiple) space
- Pareto frontier identifying optimal operating point
- Turnover reduction vs net Sharpe improvement trade-off
- Compare against dossier's recommended `min_action_edge_r = 0.15 R` from authority profile

### Expected Outcome
- ~30-50% reduction in turnover
- ~0.2-0.4 improvement in net Sharpe vs naive threshold
- Optimal operating point expected around (confidence=0.60, cost_multiple=1.5x)
- Result directly unlocks V1 validator gate

### Files to Create/Modify
```
alphaforge/runs/cost_aware_sweep.py  — sweep script (new)
alphaforge/src/alphaforge/evaluation/cost_filter.py  — cost filter module (new)
data/runs/<ts>/cost_aware_sweep/  — experiment output (first tracked artifacts)
```

---

## Direction 2: Regime-Conditional Confidence Calibration
**Priority:** HIGH | **Effort:** ~5 hours | **Corresponds to:** V9/P1

### Hypothesis
Model confidence calibration is regime-dependent. A model that appears well-calibrated overall (Brier score 0.22) may be overconfident in low-volatility regimes and underconfident in high-volatility regimes. Regime-conditional calibration can identify regimes where the model's confidence is unreliable, enabling regime-gated trade filtering.

### Source Evidence
- Regime-Conditional Distributional Comparison (2606.31251): GAMLSS/ZAGA framework compares strategy performance conditional on market regime
- Heads, Not Backbones (2606.30037): Output head design matters critically for fat-tailed returns
- Dossier V9: Confidence bucket calibration not implemented → behavior score cap 30
- Existing `regime.py` already implements HMM states, CUSUM change detection, and volatility regimes

### Experiment Design

**Step 1: Regime label extraction**
```yaml
regime_types:
  - volatility_regime: [low_vol, normal_vol, high_vol]  # from compute_volatility_regime()
  - trend_regime: [uptrend, downtrend, sideways]  # from classify_regime()
  - hmm_state: [0, 1, 2]  # from compute_hmm_vol_state()
attach_to: training frame (augment with regime column at prediction time)
```

**Step 2: Per-regime calibration measurement**
```yaml
metrics:
  - ECE (Expected Calibration Error) per regime
  - Reliability diagrams per regime
  - Confidence bucket realized_net_R (0.50-0.55, 0.55-0.60, 0.60-0.65, 0.65+)
  - AUROC per regime
```

**Step 3: Regime-gated threshold optimization**
```yaml
action: For regimes with ECE > 0.10, apply a penalty to the confidence score
         (e.g., confidence_effective = confidence - k * ECE_regime)
sweep: penalty coefficient k ∈ [0.0, 0.1, 0.2, 0.5, 1.0]
evaluate: net Sharpe improvement vs static threshold
```

### Expected Outcome
- At least one regime will show significantly worse calibration (ECE > 0.10)
- Regime-gated confidence will improve net Sharpe by 0.1-0.3
- Report identifies which regimes the model trusts but shouldn't
- Unlocks V9 validator gate

### Files to Create/Modify
```
alphaforge/runs/regime_calibration.py  — calibration experiment script (new)
alphaforge/src/alphaforge/reports/calibration.py  — calibration report module (extends existing)
data/runs/<ts>/regime_calibration/  — experiment output
```

---

## Direction 3: Feature Family Ablation & Cross-Factor Analysis
**Priority:** MEDIUM | **Effort:** ~3 hours | **Corresponds to:** V10/P1

### Hypothesis
Some feature families contribute noise rather than signal. The existing feature set can be grouped into families, and removing the lowest-IC families while retaining uncorrelated high-IC families will improve portfolio-level metrics more than adding more features.

### Source Evidence
- WorldQuant 101 Formulaic Alphas: Average pairwise correlation is only 15.9% — diversification across uncorrelated signals is the source of alpha
- AutoAlpha: Hierarchical evolutionary search discovers low-correlation factor sets
- Dossier V10: Feature family ablation not implemented → proximity max 40
- `feature_ablation.py` already exists in `alphaforge/runs/`

### Experiment Design

**Step 1: Feature family classification**
```yaml
families:
  momentum: [ROC_5, ROC_10, ROC_20, ROC_60, MA_cross, MACD]
  volatility: [ATR, STDDEV_5, STDDEV_10, BB_width, Parkinson_vol]
  volume: [volume_MA_ratio, OBV, VPT, dollar_volume]
  price_pattern: [KMID, KLEN, KUP, KLOW, KSFT, candle_body_ratio]
  microstructure: [funding_rate, open_interest, spread]
  cross_sectional: [cross_sectional_rank, relative_strength]
  regime: [hmm_state, vol_regime, trend_regime, cusum_signal]
```

**Step 2: Leave-one-family-out ablation**
```yaml
protocol: train 7 models (each missing one family) + 1 full model
# CRITICAL: Alpha-invariant — same hyperparameters, same random_state
metrics_per_model:
  - RankIC (mean, std)
  - RankICIR
  - net_Sharpe
  - feature_importance within each retained family
```

**Step 3: Cross-family correlation matrix**
```yaml
method: compute pairwise Spearman rank correlation between each family's
        top-prediction signal (not the features themselves — the resulting trade signal)
output: 7×7 correlation heatmap
target: identify families with avg cross-correlation < 0.20 (diversifiers)
        vs > 0.60 (redundant)
```

### Expected Outcome
- 1-2 families will show negative or near-zero marginal contribution
- Cross-family correlation will reveal which signals are truly diversifying
- Report identifies which families deserve more feature engineering investment
- Unlocks V10 validator gate

### Files to Create/Modify
```
alphaforge/runs/family_ablation.py  — family ablation experiment (extends feature_ablation.py)
alphaforge/src/alphaforge/features/ablation.py  — ablation module (new)
data/runs/<ts>/family_ablation/  — experiment output
```

---

## Implementation Order

| Order | Direction | Est. Time | Depends On | Unlocks |
|-------|-----------|-----------|------------|---------|
| 1 | Cost-Aware Threshold Sweep | 4h | Existing pipeline + authority config | V1 gate, baseline establishment |
| 2 | Regime-Conditional Calibration | 5h | Direction 1 outputs (baseline) | V9 gate, regime-aware gating |
| 3 | Feature Family Ablation | 3h | Direction 1-2 feature infrastructure | V10 gate, alpha diversification |

### Rationale for Order
1. **Cost-aware first**: Highest impact (directly addresses the #1 failure mode per literature). Produces the first tracked experiment in `data/runs/`.
2. **Regime calibration second**: Builds on baseline from Direction 1. The cost-aware threshold from Direction 1 can be analyzed per regime.
3. **Feature ablation third**: Informational — identifies which feature R&D to prioritize next. Lower urgency since no feature changes are pending.

---

## Success Criteria

| Criterion | Threshold | Measurement |
|-----------|-----------|-------------|
| Baseline established | `data/runs/<ts>/` exists with artifacts | File exists, git HEAD logged |
| Cost-aware filter OK | net_Sharpe improvement > 0.15 | Sweep report comparison |
| Regime calibration OK | At least 1 regime flagged as high-ECE | Calibration report |
| Family ablation OK | Correlation matrix produced | Ablation report with 7+ families |
| Validator gates unlocked | V1, V9, V10 green | Validator pass on next run |
| All experiments reproducible | `data/runs/<ts>/config.yaml` logged | Config matches command-line intent |

---

## References

1. arXiv:2606.00060 — "Machine Learning-Based Bitcoin Trading Under Transaction Costs"
2. arXiv:2605.05580 — "AlphaCrafter: A Full-Stack Multi-Agent Framework for Cross-Sectional Quantitative Trading"
3. arXiv:2606.31251 — "Regime-Conditional Distributional Comparison of Trading Strategies"
4. arXiv:2606.30037 — "Heads, Not Backbones: Output Heads Dominate Architectures on Fat-Tailed Returns"
5. arXiv:2604.09601 — "Hubble: LLM-Driven Alpha Factor Discovery"
6. arXiv:2602.07085 — "QuantaAlpha: Evolutionary LLM-Driven Alpha Mining"
7. arXiv:2606.09104 — "BAVAR-BLED: Bayesian VAR for Portfolio Optimization"
8. SSRN 2326253 — Bailey & López de Prado: Probability of Backtest Overfitting
9. SSRN 2460551 — López de Prado: Deflated Sharpe Ratio
10. arXiv:1601.00991 — Kakushadze: 101 Formulaic Alphas

---

> **Top Recommendation: Direction 1 — Cost-Aware Execution Threshold Optimization.**
> Implement tonight. It's P0 per the dossier, requires no model architecture changes, directly addresses the #1 failure mode (cost blindness), and produces the first tracked experiment artifacts to establish the `data/runs/` baseline. Expected payoff: 0.2-0.4 net Sharpe improvement from a single afternoon of threshold sweeping.
