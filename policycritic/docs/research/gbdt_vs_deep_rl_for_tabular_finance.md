# GBDT vs Deep RL for Tabular Finance

## Abstract

Grinsztajn et al. (2022, NeurIPS) empirically demonstrated that gradient-boosted decision trees (GBDT: XGBoost, LightGBM, CatBoost) consistently outperform deep neural networks on tabular data with up to ~50K samples. Trees are more robust to uninformative features, have inductive bias better suited to non-smooth decision boundaries typical in tabular data, and require far less hyperparameter tuning. Deep learning advantages emerge only on: high-cardinality categorical features, image/text modalities, and very large datasets (>100K samples with specialized architectures).

## Why It Matters for V7

The AlphaForge design commits to XGBoost as the primary model class. The Policy Critic V2 (supervised) will use XGBoost. The V3 IQL critic will use XGBoost expectile/quantile regression, not neural networks. This aligns with the evidence: at V7's expected data scale (10^4-10^6 transitions), trees beat neural networks.

## What the Literature Says

### Key Findings (Grinsztajn et al. 2022)

1. **GBDT outperforms NNs on 85% of medium-scale tabular benchmarks** (N < 50K)
2. **NNs are biased toward smooth functions** — tabular data often has sharp discontinuities (e.g., threshold effects in finance)
3. **NNs are more affected by uninformative features** — GBDT naturally performs feature selection via split importance
4. **GBDT requires less tuning** — default hyperparameters often work well; NNs require extensive architecture search
5. **At very large scale (N > 100K)**, specialized architectures (FT-Transformer, NODE) can match or exceed GBDT

### XGBoost Advantages for V7

- **Quantile regression**: `objective='reg:quantileerror'` — directly supports distributional Q-function (V3)
- **Expectile regression**: Implementable as custom objective for IQL value function
- **Monotonicity constraints**: Can enforce that higher confidence → higher expected return
- **Feature importance**: Built-in — interpretable critic decisions
- **Training speed**: Orders of magnitude faster than neural network RL

## How It Applies to V7

1. **V2 critic**: XGBoost regressor predicting realized_r_net from state features
2. **V3 critic**: XGBoost expectile regression for IQL V(s); XGBoost quantile regression for distributional Q(s,a)
3. **Ensemble**: IQL + CQL as separate XGBoost models, not separate neural network architectures

## Decision: USE NOW (model class confirmed)

XGBoost is the confirmed model class for all Policy Critic versions (V1-V3). Neural network RL (DQN, SAC, PPO) is rejected for V7 due to sample inefficiency on tabular data at this scale.
