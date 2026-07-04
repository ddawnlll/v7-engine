# MLOps & AI Factory Maturity for Quantitative Trading Systems
## Comprehensive Research Report

**Date:** 2026-07-04
**Scope:** Industry best practices for MLOps maturity, AI Factory architecture, and implementation patterns for alpha research / quantitative trading systems
**Sources:** Google MLOps documentation, Microsoft MLOps maturity model, NVIDIA AI Factory framework, MLflow/DVC/W&B documentation, de Prado's Advances in Financial Machine Learning, TFX/TFMA patterns, QuantInsti research, production ML failure analyses

---

## Table of Contents

1. [MLOps Maturity Models](#1-mlops-maturity-models)
2. [Industry Maturity Distribution](#2-industry-maturity-distribution)
3. [Dataset Manifest & Data Lineage](#3-dataset-manifest--data-lineage)
4. [Experiment Tracking](#4-experiment-tracking)
5. [Run Registry & Artifact Registry](#5-run-registry--artifact-registry)
6. [Config-driven Experiments](#6-config-driven-experiments)
7. [Reproducibility](#7-reproducibility)
8. [Walk-forward Validation & Leakage Detection](#8-walk-forward-validation--leakage-detection)
9. [Eval Gates (Automated Promotion Gates)](#9-eval-gates-automated-promotion-gates)
10. [Promotion Gates (Shadow, Canary, A/B)](#10-promotion-gates-shadow-canary-ab)
11. [Baseline Management](#11-baseline-management)
12. [Leaderboard Systems](#12-leaderboard-systems)
13. [Failure Taxonomy](#13-failure-taxonomy)
14. [Cost Sensitivity Analysis](#14-cost-sensitivity-analysis)
15. [Shadow Mode (Shadow Trading)](#15-shadow-mode-shadow-trading)
16. [Source of Truth Architecture](#16-source-of-truth-architecture)
17. [Open Source Tools Comparison](#17-open-source-tools-comparison)
18. [Recommended Stack by Team Size](#18-recommended-stack-by-team-size)

---

## 1. MLOps Maturity Models

### 1.1 Google's Three-Level Model

| Level | Name | Description | Quant Trading Translation |
|-------|------|-------------|---------------------------|
| **0** | Manual Process | All steps manual. Code in notebooks. Models deployed few times/year. No CI/CD. | Researcher runs backtest in Jupyter, exports pickle, hands to quant dev. No monitoring. |
| **1** | ML Pipeline Automation | Entire ML workflow automated as orchestrated pipeline. Continuous training via triggers. Feature store introduced. | Feature engineering pipeline automated. Model training triggered by new data. Feature store ensures same features in research and production. |
| **2** | CI/CD Pipeline Automation | Automated CI/CD layered on Level 1. Six-stage flow: dev, pipeline CI, pipeline CD, auto-triggering, model CD, monitoring. | CI tests run on every PR: feature transform correctness, model convergence, numerical stability. Pipeline changes auto-tested and deployed. |

### 1.2 Microsoft's Five-Level Model

| Level | Name | Description | Quant Trading Translation |
|-------|------|-------------|---------------------------|
| **0** | No MLOps | Fully manual builds, deployments, training. No tracking. | Ad-hoc backtests, manual signal research |
| **1** | DevOps but No MLOps | Application CI/CD exists, but ML-specific processes still manual | Shared pipelines, basic experiment tracking |
| **2** | Automated Training | Experiment tracking centralized. Feature store adopted. Model registry introduced. | Automated alpha discovery pipeline, model registry, CI/CD |
| **3** | Automated Model Deployment | CI/CD manages releases end-to-end. A/B testing. Full lineage from deployed model to training data. | Automated promotion through gates, shadow trading, auto-deployment |
| **4** | Full MLOps Automated Operations | Production metrics trigger retraining. Feature health monitored. Policy-based auto-promotion. Zero downtime. | Self-serve alpha research platform with auto-promotion and auto-retirement |

### 1.3 Concrete Tools by Maturity Level

| Level | Data Versioning | Experiment Tracking | Pipeline | Feature Store | Model Registry | CI/CD | Monitoring |
|-------|----------------|---------------------|----------|---------------|---------------|-------|-----------|
| 0 | Git (manual) | None or spreadsheets | None | None | None | None | None |
| 1 | DVC or Git LFS | MLflow or W&B basic | Kubeflow or Airflow | None or basic | None | Application CI only | None |
| 2 | DVC + cloud storage | MLflow or W&B full | Kubeflow or Airflow | Feast | MLflow Registry | GitHub Actions | Basic dashboards |
| 3 | Delta Lake or LakeFS | Full lineage tracking | Orchestrated with triggers | Managed feature store | Registry with lifecycle stages | Full CI/CD with A/B | Performance dashboards |
| 4 | Automated data validation | End-to-end lineage | Self-triggering pipelines | Feature health monitoring | Policy-based auto-promotion | Automated rollback/retrain | Drift detection with auto-retrain |

---

## 2. Industry Maturity Distribution

### 2.1 Overall Industry

| Level | Approximate % of All Firms | Finance/Trading Firms | Top Quant Funds |
|-------|---------------------------|----------------------|-----------------|
| Level 0 (Manual) | 30-35% | 15-20% | Near 0% |
| Level 1 (Basic CI) | 30-35% | 25-30% | 5-10% |
| Level 2 (Automated Training) | 15-20% | 25-30% | 30-40% |
| Level 3 (Automated Deployment) | 10-15% | 15-20% | 35-45% |
| Level 4 (Full Automation) | 5-10% | 5-10% | 15-25% |

**Key observations:**
- Only 20-30% of firms overall consider themselves at advanced MLOps levels
- Quantitative hedge funds (Renaissance, Two Sigma, DE Shaw, Citadel) cluster at Level 3-4
- Traditional asset managers lag significantly; many still at Level 0-1
- Regulatory pressure (SR 11-7, EU AI Act) is accelerating adoption in financial services
- Level 0 teams ship 1-2 models per year; Level 3+ teams ship dozens reliably

### 2.2 V7 Engine Current Positioning

| Subsystem | Approximate Level | Path to Next Level |
|-----------|-------------------|-------------------|
| AlphaForge alpha discovery | Level 2 | Automated promotion decisions, drift-triggered retraining |
| V7 policy acceptance | Level 2-3 | Policy-based auto-promotion through gates |
| Simulation and cost modeling | Level 3 | Integration with live monitoring feedback loop |
| Runtime execution | Level 2 | Automated deployment, monitoring |

---

## 3. Dataset Manifest & Data Lineage

### 3.1 Core Concepts

**Dataset Manifest:** A machine-readable file (YAML/JSON) capturing dataset identity -- name, version (digest/hash), schema, source location, number of records, time range, and provenance metadata.

**Data Lineage:** The DAG connecting raw data sources through transformation stages to features, training sets, trained models, and evaluations. In quant trading: market data feed -> raw bars -> cleaned bars -> engineered features -> labeled training set -> model -> backtest -> signal.

### 3.2 DVC Dataset Manifest

**`.dvc` file schema (created by `dvc add`):**

```yaml
# data/ohlcv_btcusdt_2024.dvc
outs:
  - md5: a304afb96060aad90176268345e10355
    path: ohlcv_btcusdt_2024.parquet
    desc: "BTC/USDT 1h OHLCV bars, 2024-01 to 2024-12, from Binance API"
    size: 524288000
    nfiles: null
```

### 3.3 Custom Dataset Manifest Schema (Composite Pattern)

```yaml
# manifests/dataset_manifest_v1.yaml
manifest_version: "2.0.0"
dataset:
  name: "btcusdt_1h_features_v1"
  version: "2024.12.15-abc1234"
  created_at: "2024-12-15T14:30:00Z"
  author: "alphaforge-pipeline"

provenance:
  source_system: "binance"
  source_type: "exchange_api"
  fetch_timestamp: "2024-12-15T00:00:00Z"
  raw_data_hash: "sha256:def5678..."
  dvc_commit: "abc1234"
  git_commit: "7f3a2b1"
  pipeline_version: "v7.2.1"

schema:
  format: "parquet"
  row_count: 8200
  column_count: 47
  columns:
    - name: "rsi_14"
      type: "float64"
      derived_from: ["close"]
      transform: "rsi(close, 14)"
    - name: "volatility_24"
      type: "float64"
      derived_from: ["close"]
      transform: "rolling_std(returns, 24)"

time_range:
  start: "2024-01-01T00:00:00Z"
  end: "2024-12-14T23:00:00Z"
  bar_interval: "1h"
  timezone: "UTC"
  total_bars: 8200

quality_checks:
  null_ratio_max: 0.01
  actual_null_ratio: 0.002
  price_continuity_check: "PASS"
  volume_anomaly_check: "PASS"

lineage:
  parent_datasets:
    - name: "ohlcv_btcusdt_1h_raw"
      version: "2024.12.15-abc1234"
      relationship: "raw_source"
  dependent_artifacts:
    - name: "xgb_btcusdt_v1_model"
      type: "model"
      relationship: "trained_on"
```

### 3.4 Trading-Specific Data Lineage DAG

```
Exchange API (Binance)
       |
       v
  raw/ohlcv_btcusdt_1h.parquet  [.dvc tracked, S3 remote]
       |
       v
  clean/ohlcv_btcusdt_1h.parquet  [outlier removal, gap filling]
       |
       +---> features/btcusdt_features.parquet  [47 columns]
       |           |
       +---> labels/btcusdt_labels.parquet  [triple-barrier labels]
       |           |
       |           v
       |    models/xgb_btcusdt_v1.pkl  [MLflow registered model]
       |           |
       |           v
       |    reports/backtest_results.json  [Sharpe, drawdown, win rate]
       |
       +---> dvc.yaml pipeline (stages 1-6)
       +-- MLflow run (experiment tracking)
       +-- custom manifests (domain metadata)
```

### 3.5 Tool Comparison for Data Lineage

| Capability | DVC | MLflow | W&B |
|---|---|---|---|
| **Data versioning** | Primary purpose. Git-coupled, content-addressed. Best for large datasets. | Secondary. `log_input` records references (name + hash + source). | Artifacts store data with deduplication. Good for medium datasets. |
| **Lineage tracking** | Implicit via `dvc.yaml` pipeline DAG. | `log_input` + `log_model` creates run-level input/output graph. | Automatic lineage graph via `use_artifact()` vs `log_artifact()`. |
| **Git coupling** | Deep. Every `.dvc` file is a Git-tracked pointer. | Loose. Params/metrics in runs. Dataset references are metadata only. | Loose. Artifacts are server-side, not Git-tracked. |

**Recommended composite architecture:** DVC (data versioning) + MLflow (experiments + model registry) + custom manifests (domain metadata).

---

## 4. Experiment Tracking

### 4.1 MLflow Configuration Pattern

```yaml
# docker-compose.yml (production)
services:
  postgres:
    image: postgres:13
    environment:
      POSTGRES_DB: mlflow
      POSTGRES_USER: mlflow
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"

  mlflow:
    build: .
    ports:
      - "5000:5000"
    environment:
      MLFLOW_TRACKING_URI: postgresql://mlflow:${POSTGRES_PASSWORD}@postgres:5432/mlflow
      MLFLOW_S3_ENDPOINT_URL: http://minio:9000
    command: >
      mlflow server
      --backend-store-uri postgresql://mlflow:${POSTGRES_PASSWORD}@postgres:5432/mlflow
      --default-artifact-root s3://mlflow-artifacts/
      --host 0.0.0.0 --port 5000
```

### 4.2 Quantitative Trading Integration Pattern

```python
import mlflow
from xgboost import XGBClassifier

mlflow.set_tracking_uri("postgresql://mlflow:password@localhost:5432/mlflow")
mlflow.set_experiment("alpha-factor-v1")

with mlflow.start_run(run_name="xgboost_volatility_factor"):
    # Log hyperparameters
    mlflow.log_params({
        "model_type": "xgboost",
        "lookback_days": 60,
        "universe": "sp500",
        "factor_name": "realized_vol_60d",
        "rebalance_freq": "weekly",
    })

    # Train model
    model = XGBClassifier(n_estimators=100, max_depth=6)
    model.fit(X_train, y_train)

    # Log quantitative metrics
    mlflow.log_metrics({
        "sharpe_ratio": 1.82,
        "max_drawdown": -0.12,
        "win_rate": 0.58,
        "profit_factor": 1.65,
        "ic": 0.045,
        "rank_ic": 0.062,
        "turnover": 0.23,
    })

    # Log model artifact
    mlflow.sklearn.log_model(model, "model")
```

### 4.3 W&B Artifact Lineage Pattern

```python
import wandb

run = wandb.init(project="alpha-discovery", config={
    "mode": "SCALP", "universe": "crypto_perp",
    "model": "xgboost", "features": ["rv_60d", "ofi", "funding_rate"],
})

# Log raw data artifact (input)
raw_artifact = wandb.Artifact(name="ohlcv-btcusdt-1h", type="dataset",
    metadata={"symbol": "BTCUSDT", "interval": "1h", "source": "binance"})
raw_artifact.add_dir("data/raw")
run.log_artifact(raw_artifact)

# Log features artifact (derived)
features_artifact = wandb.Artifact(name="features-btcusdt", type="dataset",
    metadata={"feature_count": 47, "parent_dataset": "ohlcv-btcusdt-1h:v3"})
features_artifact.add_file("data/features/btcusdt_features.parquet")
run.log_artifact(features_artifact)

# Declare inputs (builds lineage edges)
run.use_artifact(raw_artifact)
run.use_artifact(features_artifact)

# Log model artifact (output)
model_artifact = wandb.Artifact(name="xgb-btcusdt-model", type="model")
model_artifact.add_file("models/xgb_btcusdt_v1.pkl")
run.log_artifact(model_artifact)
```

---

## 5. Run Registry & Artifact Registry

### 5.1 MLflow Run Registry Query Patterns

```python
from mlflow.tracking import MlflowClient

client = MlflowClient()

# Query runs by metric threshold
runs = client.search_runs(
    experiment_ids=["1"],
    filter_string="metrics.sharpe_ratio > 1.5",
    order_by=["metrics.sharpe_ratio DESC"],
    max_results=10
)

for run in runs:
    print(f"Run: {run.info.run_id}, Sharpe: {run.data.metrics['sharpe_ratio']}")
```

### 5.2 DVC Run Registry

```bash
# List all experiments
dvc exp list --all

# Compare experiments
dvc exp show

# Diff metrics between experiments
dvc exp diff --metrics

# Export to CSV for analysis
dvc exp show --csv > experiments.csv

# Run experiment with param changes
dvc exp run -S model.n_estimators=200 -S training.cv_folds=10
```

### 5.3 LakeFS Data Versioning

```python
import lakefs

client = lakefs.Client(endpoint="http://localhost:8000")

# Create repository for alpha factors
repo = client.repositories.create(
    name="alpha-factors",
    storage_namespace="s3://quant-data/alpha-factors"
)

# Create branch for experiment
branch = repo.branch("experiment-vol-factor-v2")

# Commit with metadata
commit = branch.commit(
    message="Add realized volatility features for 2024",
    metadata={"data_period": "2024-01 to 2024-12", "universe": "sp500"}
)
```

### 5.4 Comparative Matrix

| Feature | MLflow | W&B | DVC | LakeFS |
|---------|--------|-----|-----|--------|
| **Run Registry** | SQL query | API query | Git-based | Git-based |
| **Artifact Storage** | S3/MinIO/GCS | W&B cloud | S3/GCS/SSH | S3/GCS/Azure |
| **Model Registry** | Yes (full lifecycle) | Yes | No (use MLflow) | No (use MLflow) |
| **Self-Hostable** | Yes | No (cloud only) | Yes | Yes |
| **Quant Trading Fit** | High | High | High | Medium |

---

## 6. Config-driven Experiments

### 6.1 Hydra + OmegaConf Configuration Structure

```
conf/
  config.yaml          # Main config with defaults
  model/
    xgboost.yaml
    lightgbm.yaml
  features/
    technical.yaml
    alternative.yaml
  training/
    default.yaml
    aggressive.yaml
```

**Main config.yaml:**
```yaml
defaults:
  - model: xgboost
  - features: technical
  - training: default
  - _self_

experiment:
  name: "baseline_run"
  seed: 42
  output_dir: "outputs/${experiment.name}"
```

**Model config (model/xgboost.yaml):**
```yaml
_target_: xgboost.XGBClassifier
n_estimators: 500
max_depth: 6
learning_rate: 0.05
subsample: 0.8
colsample_bytree: 0.8
```

### 6.2 Hydra Training Script Pattern

```python
import hydra
from omegaconf import DictConfig, OmegaConf

@hydra.main(version_base=None, config_path="conf", config_name="config")
def train(cfg: DictConfig) -> None:
    print(OmegaConf.to_yaml(cfg))
    
    model = hydra.utils.instantiate(cfg.model)
    optimizer = hydra.utils.instantiate(cfg.training.optimizer, params=model.parameters())
    
    # Log config to experiment tracker
    wandb.config.update(OmegaConf.to_container(cfg, resolve=True))

if __name__ == "__main__":
    train()
```

### 6.3 Multi-run Sweeps

```bash
# Grid search over models and learning rates
python train.py --multirun model=xgboost,lightgbm training.optimizer.lr=0.001,0.01,0.1

# Optuna integration for Bayesian optimization
python train.py --multirun --config-name=config_hpo
```

**Optuna sweeper config:**
```yaml
defaults:
  - override hydra/sweeper: optuna

hydra:
  sweeper:
    _target_: hydra_plugins.optuna_sweeper.OptunaSweeper
    direction: minimize
    study_name: alpha_optimization
    n_trials: 50
    n_jobs: 4
    sampler:
      _target_: optuna.samplers.TPESampler
    search_space:
      training.optimizer.lr:
        type: loguniform
        bounds: [0.0001, 0.1]
```

---

## 7. Reproducibility

### 7.1 DVC Pipeline Pattern

```yaml
# dvc.yaml
stages:
  prepare_data:
    cmd: python src/data/prepare.py
    deps:
      - src/data/prepare.py
      - data/raw/market_data.parquet
    outs:
      - data/processed/features.parquet
    params:
      - data.prepare.seed
      - data.prepare.train_split

  train_model:
    cmd: python src/models/train.py
    deps:
      - src/models/train.py
      - data/processed/features.parquet
    params:
      - model
      - training
    outs:
      - models/model.pkl
    metrics:
      - metrics/train_metrics.json:
          cache: false

  evaluate:
    cmd: python src/models/evaluate.py
    deps:
      - src/models/evaluate.py
      - models/model.pkl
    metrics:
      - metrics/eval_results.json:
          cache: false
```

### 7.2 Seed Management for Determinism

```python
import random, numpy as np, torch, os

def set_global_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    torch.use_deterministic_algorithms(True)
    os.environ["PYTHONHASHSEED"] = str(seed)
```

### 7.3 Environment Capturing

```python
import subprocess, json
from datetime import datetime

def capture_environment():
    return {
        "timestamp": datetime.now().isoformat(),
        "python_version": subprocess.check_output(["python", "--version"]).decode().strip(),
        "pip_packages": subprocess.check_output(["pip", "freeze"]).decode().strip(),
        "git_hash": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
        "cuda_version": torch.version.cuda if torch.cuda.is_available() else None,
    }
```

### 7.4 Git LFS vs DVC

| Feature | Git LFS | DVC |
|---------|---------|-----|
| **Purpose** | Large file storage | ML pipeline management |
| **Pipeline support** | None | Built-in DAG execution |
| **Experiment tracking** | Basic | Full metrics/params tracking |
| **Best for** | Simple binary versioning | Multi-stage ML workflows |

**Hybrid approach:** Git LFS for small binary assets (models, configs) + DVC for datasets and pipeline outputs.

### 7.5 Dockerized Reproduction

```dockerfile
FROM python:3.10-slim as base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install -r requirements.txt
WORKDIR /app
COPY . .
ENV PYTHONHASHSEED=42
ENTRYPOINT ["python", "train.py"]
```

**Full reproduction command:**
```bash
docker run --rm --gpus all \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/outputs:/app/outputs \
  ml-experiment:v1.0.0 \
  python train.py --config-name=experiment_123 seed=42
```

---

## 8. Walk-forward Validation & Leakage Detection

### 8.1 Walk-Forward Validation Variants

**Expanding Window:**
```
Fold 1: train [0..19], test [20..24]
Fold 2: train [0..24], test [25..29]
Fold 3: train [0..29], test [30..34]
```

**Rolling (Sliding) Window:**
```
Fold 1: train [0..19], test [20..24]
Fold 2: train [5..24], test [25..29]
Fold 3: train [10..29], test [30..34]
```

**WFO Efficiency Ratio:** `efficiency = oos_sharpe / is_sharpe`. A strategy keeping 50-70% of in-sample performance OOS is realistic. Below 30% indicates overfitting.

### 8.2 Purged K-Fold Cross Validation (de Prado)

Standard k-fold CV is catastrophic for financial time series because it shuffles data randomly, breaking temporal ordering.

**Purging condition:** A training observation at time i is purged if its label interval overlaps the test interval:
```
purge when: (t_{i,0} <= T_{j,1}) AND (t_{i,1} >= T_{j,0})
```

**Embargo:** Removes training samples that start shortly after the test period ends (prevents information leakage through feature autocorrelation).

**Embargo sizing formulas:**

| Method | Formula | When to Use |
|--------|---------|-------------|
| Percentage-based | `embargo = pct * len(data)` | General default (1-5%) |
| Feature-lookback | `embargo = max(lookback_window)` | When feature lookback is known |
| Label-horizon | `embargo = label_horizon / 2` | When labels are path-dependent |
| Half-ACF-decay | `embargo = lag where ACF < 0.05` | Data-driven, most rigorous |

### 8.3 Library Implementations

```python
# purgedcv library
from purgedcv import PurgedKFold, WalkForwardSplit, CombinatorialPurgedCV

splitter = PurgedKFold(
    n_splits=5,
    prediction_times=pred_series,
    evaluation_times=eval_series,
    purge_horizon="2D",
    embargo="3D"
)

# WalkForwardSplit
splitter = WalkForwardSplit(
    n_splits=10,
    test_size=63,            # 3 months
    window="sliding",        # or "expanding"
    train_size=252,          # 1 year
    purge_horizon="5D"
)
```

### 8.4 Combinatorial Purged CV (CPCV)

Generates multiple train/test combinations, producing a distribution of Sharpe ratios rather than a single point estimate.

**Probability of Backtest Overfitting (PBO):** PBO > 0.5 means the strategy selection process is overfitting.

### 8.5 Automated Leakage Detection

**Bar-Shift Test (definitive look-ahead bias detector):**
```python
def bar_shift_test(strategy, data):
    original_sharpe = backtest(strategy, data, signal_lag=0)
    shifted_sharpe = backtest(strategy, data, signal_lag=1)
    performance_drop = (original_sharpe - shifted_sharpe) / original_sharpe
    if performance_drop > 0.50:
        print("WARNING: Likely look-ahead bias detected")
    return performance_drop
```

**Too-Good-to-Be-True Heuristics:**
```python
def automated_bias_screen(backtest_results):
    warnings = []
    if backtest_results['sharpe'] > 3.5:
        warnings.append("Sharpe > 3.5 -- nearly impossible without future knowledge")
    if backtest_results['max_drawdown_pct'] < 3:
        warnings.append("Max drawdown < 3% -- unrealistically smooth")
    if backtest_results['is_sharpe'] / max(backtest_results['oos_sharpe'], 0.01) > 3:
        warnings.append("IS/OOS ratio > 3x -- severe overfitting or leakage")
    return warnings
```

### 8.6 Recommended Validation Pipeline

```
1. Point-in-time data verification
2. Feature timing audit (automated)
3. Purged K-Fold CV with embargo (model selection/tuning)
4. Walk-Forward Validation (final performance estimation)
5. Bar-Shift Test (binary leak detector)
6. CPCV for PBO estimation (PBO < 0.5 required)
7. Deflated Sharpe Ratio (DSR > 2.0 for live deployment)
```

---

## 9. Eval Gates (Automated Promotion Gates)

### 9.1 Gate Architecture

```
Gate 0: Data Quality     -> schema validation, null rates, distribution checks
Gate 1: Training Health   -> convergence, loss curves, gradient norms
Gate 2: Offline Metrics   -> AUC, F1, RMSE against absolute thresholds
Gate 3: Baseline Compare  -> candidate vs. baseline with statistical significance
Gate 4: Robustness        -> adversarial, edge cases, subgroup performance
Gate 5: Serving Feasibility -> latency, memory, throughput benchmarks
Gate 6: Shadow/Canary     -> live-data validation before full promotion
```

### 9.2 Trading-Specific Metrics and Thresholds

| Metric | Absolute Threshold | Relative Threshold (vs. Baseline) | Statistical Test |
|--------|-------------------|-----------------------------------|-----------------|
| Sharpe Ratio (OOS) | >= 1.0 | Improvement >= 0.2 | Bootstrap CI |
| Max Drawdown | < 20% | Not worse | One-sided test |
| Information Coefficient (IC) | >= 0.05 | Stable | Permutation test |
| IC IR | >= 0.5 | Stable | Bootstrap CI |
| Profit Factor | >= 1.5 | Improvement >= 10% | Paired bootstrap |
| Turnover | Within target band | No excessive increase | Direct comparison |

### 9.3 TFMA Implementation Pattern

```python
metrics {
  class_name: "AUC"
  threshold {
    value_threshold {
      lower_bound { value: 0.9 }
    }
    change_threshold {
      direction: HIGHER_IS_BETTER
      absolute { value: -1e-10 }
    }
  }
}
```

---

## 10. Promotion Gates (Shadow, Canary, A/B)

### 10.1 Shadow Mode

New model runs in parallel with production, receiving live traffic, but predictions are logged, not served.

**Key Comparison Metrics:**

| Metric | What to Compare | Threshold for Concern |
|--------|-----------------|----------------------|
| Prediction agreement rate | How often models agree on direction | < 70% warrants investigation |
| Prediction magnitude divergence | Difference in predicted returns | > 2 standard deviations |
| Simulated PnL difference | New model's simulated returns vs. production | Negative alpha after 20+ days |

**Minimum Shadow Duration:** 20-60 trading days depending on strategy holding period.

### 10.2 Canary Deployment

Gradually increasing live traffic (capital allocation) to the new model.

| Stage | Capital Allocation | Duration | Promotion Gate |
|-------|-------------------|----------|----------------|
| 1 - Smoke Test | 1% of max position | 1-3 days | No errors, latency within bounds |
| 2 - Small Live | 5% of max position | 5-10 days | Sharpe > 0, drawdown < threshold |
| 3 - Medium Live | 25% of max position | 10-20 days | All metrics stable, no drift |
| 4 - Full Deployment | 100% | Ongoing | Continuous monitoring |

**Automated Rollback Triggers:**

| Metric | Threshold | Duration | Action |
|--------|-----------|----------|--------|
| Error rate | > 5% | 5 minutes | Auto-rollback |
| Prediction drift (PSI) | > 0.2 | 1 hour | Alert + review |
| Sharpe degradation | < 50% of baseline | 5 trading days | Auto-rollback |
| Max drawdown | Exceeds limit | Any time | Immediate halt |

### 10.3 A/B Testing (Champion-Challenger)

```python
from scipy import stats

# Collect paired daily returns
champion_returns = [...]
challenger_returns = [...]

# Paired t-test
t_stat, p_value = stats.ttest_rel(challenger_returns, champion_returns)

# Non-parametric alternative (Wilcoxon signed-rank)
w_stat, w_pvalue = stats.wilcoxon(challenger_returns, champion_returns)

# Bootstrap confidence interval
diffs = np.array(challenger_returns) - np.array(champion_returns)
boot_means = [np.mean(np.random.choice(diffs, size=len(diffs), replace=True))
              for _ in range(10000)]
ci_lower, ci_upper = np.percentile(boot_means, [2.5, 97.5])
```

**Decision Rules:**

| Condition | Action |
|-----------|--------|
| p < 0.05 AND challenger Sharpe > champion Sharpe | Promote challenger |
| p < 0.05 AND challenger Sharpe < champion Sharpe | Keep champion |
| p >= 0.05 AND challenger Sharpe > champion Sharpe | Extend test |
| p >= 0.05 AND challenger Sharpe < champion Sharpe | Reject challenger |

**Minimum Sample Sizes:**

| Expected Sharpe Difference | Required Trading Days (power=0.8, alpha=0.05) |
|---------------------------|-----------------------------------------------|
| 0.1 | ~1600 |
| 0.2 | ~400 |
| 0.5 | ~65 |
| 1.0 | ~18 |

### 10.4 Complete Promotion Pipeline

```
TRAINING COMPLETE
      |
      v
Gate 0: Data Quality    -> PSI < 0.1 for all features
Gate 1: Train Health    -> Loss convergence, no NaN gradients
Gate 2: Offline Eval    -> AUC >= 0.70, F1 >= 0.60
Gate 3: Baseline Cmp    -> McNemar / Bootstrap CI, p < 0.05
Gate 4: Robustness      -> Subgroup performance, stress scenarios
Gate 5: Serving OK      -> Latency P99 < 200ms, Memory < 512MB
Gate 6: Shadow Mode     -> 20-60 days parallel, agreement >= 70%
Gate 7: Canary          -> 1% -> 5% -> 25% -> 100% with auto-rollback
      |
      v
  PRODUCTION
      |
      v
Continuous Monitoring   -> PSI, KS test, performance metrics
```

### 10.5 Statistical Test Selection Guide

| Data Type | Sample Size | Recommended Test |
|-----------|------------|-----------------|
| Binary outcomes, large N | > 1000 | McNemar's chi-squared |
| Binary outcomes, small N | < 1000 | Mid-P McNemar's |
| Continuous returns, non-normal | Any | Wilcoxon signed-rank or Bootstrap |
| Distribution comparison | > 100 | KS test |
| Any metric, any distribution | > 100 | BCa Bootstrap CI |
| Minimal assumptions | > 50 | Permutation test |

---

## 11. Baseline Management

### 11.1 What Baselines to Track

| Baseline | Purpose | When to Update |
|----------|---------|----------------|
| **Random Baseline** | Proves model has signal at all | Never (always keep) |
| **Naive Baseline** | Last prediction, simple heuristic | Never (always keep) |
| **Previous Champion** | Current production model | On each promotion |
| **Statistical Baseline** | Equal-weight or mean prediction | Never |
| **Champion of Record** | Best model ever deployed | On each new record |
| **Walk-Forward Baseline** | OOS performance from development | On each new development cycle |

### 11.2 Baseline Snapshot Schema

```yaml
baseline:
  model_id: "v2.3.1"
  registered_at: "2026-07-01T00:00:00Z"
  metrics:
    auc: 0.924
    f1: 0.713
    sharpe_oos: 1.34
    max_drawdown: -0.142
    profit_factor: 1.87
    information_coefficient: 0.068
    ic_ir: 0.72
    turnover_daily: 0.23
  training_data:
    date_range: ["2024-01-01", "2026-03-31"]
    n_samples: 125000
    data_hash: "sha256:abc123..."
  evaluation_data:
    date_range: ["2026-04-01", "2026-06-30"]
    n_samples: 8500
    data_hash: "sha256:def456..."
  promotion_history:
    - stage: "staging"
      at: "2026-06-15T10:00:00Z"
    - stage: "shadow"
      at: "2026-06-15T10:00:00Z"
      duration_days: 25
    - stage: "production"
      at: "2026-07-01T00:00:00Z"
```

### 11.3 Multi-Baseline Comparison Matrix

| Candidate vs. | Metric | Winner Threshold | Statistical Test |
|---------------|--------|------------------|-----------------|
| Random Baseline | AUC | > 0.50 | Binomial test |
| Naive Baseline | Sharpe | > 0 | Paired t-test |
| Previous Champion | AUC | > +0.005 (0.5%) | McNemar's test |
| Previous Champion | Sharpe | > +0.2 | Bootstrap CI |
| Previous Champion | Max Drawdown | Not worse | One-sided test |

### 11.4 MLflow Model Registry Lifecycle

```
None -> Staging -> Production -> Archived
```

| Stage | Purpose | Gate Required |
|-------|---------|---------------|
| None | Initial registration | Model artifact logged |
| Staging | Testing and validation | Eval gates 0-4 pass |
| Production | Deployed and serving | Shadow/canary pass + human approval |
| Archived | Inactive / superseded | Automatic on new production promotion |

---

## 12. Leaderboard Systems

### 12.1 Architecture Patterns

| Pattern | Description | Use Case |
|---------|-------------|----------|
| **Event-Driven** | Submissions trigger validation -> evaluation -> ranking pipeline | Real-time leaderboards |
| **CQRS** | Separate write paths (submissions) from read paths (queries) | High-read workloads |
| **Fan-out/Fan-in** | Parallel evaluation across datasets, then aggregate | Multi-metric ranking |

### 12.2 Ranking Patterns

| Pattern | Implementation | Trade-offs |
|---------|----------------|------------|
| **Multi-Metric** | Pareto-based or weighted scoring | Requires metric weights |
| **Elo Rating** | Head-to-head comparison style | Computationally expensive |
| **Tiered/Bracket** | Group models by capability tiers | Simple, interpretable |
| **Rolling Window** | Time-decayed scores favoring recent submissions | Penalizes stable models |

### 12.3 Best Practices

- Idempotent submissions via unique submission IDs
- Deterministic seeds and fixed test sets for reproducibility
- Holdout sets and statistical significance tests for anti-gaming
- Immutable audit trail of all submissions and ranking changes
- Pre-computed leaderboard rankings cached in Redis

---

## 13. Failure Taxonomy

### 13.1 Primary Failure Categories

| Category | Subcategories | Detection Signals |
|----------|---------------|-------------------|
| **Data Failures** | Schema drift, distribution shift, missing values, label errors, feature leakage | Schema validation, statistical distribution checks, freshness monitoring |
| **Model Failures** | Overfitting, underfitting, shortcut learning, calibration drift, concept drift | Accuracy metrics by slice, PSI > 0.25 threshold, confidence calibration |
| **Infrastructure Failures** | GPU OOM, dependency conflicts, orchestration timeouts | Resource monitoring, pinned dependencies, idempotent pipeline steps |
| **Monitoring Failures** | Broken instrumentation, alert fatigue, silent degradation | Audit trail validation, alert response time tracking |
| **Human/Process Failures** | Ownership ambiguity, governance gaps | Clear incident classification, ownership maps |

### 13.2 Key Findings

- ~80% of failures trace to data or pipeline issues, not model weights
- Training-serving skew creates day-one mismatch
- Aggregate accuracy metrics hide segment failures (model can hold 88% overall while failing at 51% on high-value cohorts)
- Ownership ambiguity turns 2-hour incidents into 3-day incidents

### 13.3 Incident Classification System

```
Alert Trigger -> What kind of failure?
                |
   +------------+------------+
   |            |            |
Serving/     Data/       Quality/
Latency      Features    Behavior
   |            |            |
Check        Check       Check
infra,       freshness,  recent model,
pods,        schema,     traffic slices,
timeouts     joins       labels
```

---

## 14. Cost Sensitivity Analysis

### 14.1 Transaction Cost Components

| Cost Type | Components | Typical Range | Measurement |
|-----------|------------|---------------|-------------|
| **Commission** | Brokerage fees, exchange fees | 0.01%-0.10% | Per trade |
| **Slippage** | Market impact, spread costs, latency | 0.05%-0.50% | Expected vs actual fill |
| **Funding** | Margin borrowing, short sell fees | 3%-10% annualized | Daily accrual |
| **Opportunity** | Capital locked in positions | Risk-free rate | Daily |

### 14.2 Cost-Aware ML Optimization Patterns

1. **Cost-Adjusted Return Optimization:**
   - `net_return = gross_return - (commission + slippage + funding)`

2. **Turnover Penalties:**
   - `objective = alpha - lambda * turnover`

3. **Realistic Backtesting:**
   - Model market impact as `impact = k * sqrt(volume / ADV)`

4. **Sensitivity Analysis Framework:**
   - Test strategy performance across cost assumption ranges
   - Run Monte Carlo simulations with cost distributions
   - Track Sharpe ratio decay as costs increase

### 14.3 Specific Metrics Tracked

- Net Sharpe Ratio (after all costs)
- Turnover Ratio (trades / capital)
- Cost Drag (% return lost to costs)
- Break-even Cost Threshold (max tolerable cost)
- Slippage Realization (actual vs estimated)

---

## 15. Shadow Mode (Shadow Trading)

### 15.1 Architecture

```
Live Market Data
       |
       v
Feature Engine  (identical for both paths)
       |
   +---+---+
   |       |
Prod     Shadow
Model    Model
   |       |
   v       v
Order    Order
Mgmt     Logger  <- NO exchange submission
   |       |
   v       v
Exchange   PnL Tracker (simulated fill at market price)
```

### 15.2 Shadow Trading Metrics

| Metric | Production | Shadow | Comparison |
|--------|-----------|--------|------------|
| Signal generation rate | signals/day | signals/day | Within 20% |
| Direction agreement | - | % agreement | >= 70% |
| Simulated Sharpe | - | rolling 20-day | > 0 |
| Simulated max DD | - | from peak | < threshold |
| Fill simulation | actual fills | estimated fills | Slippage delta |

### 15.3 Minimum Duration Rules

| Strategy Type | Minimum Shadow Days | Rationale |
|---------------|--------------------:|-----------|
| Intraday scalping | 15-20 | High frequency, quick statistical convergence |
| Daily rebalancing | 20-40 | Need multiple market regimes |
| Swing trading (3-10 day) | 40-80 | Must span multiple complete trades |
| Monthly rebalancing | 60-120 | Very slow signal, need patience |

---

## 16. Source of Truth Architecture

### 16.1 Single Source of Truth by Data Type

| Data Type | Source of Truth | Implementation |
|-----------|-----------------|----------------|
| **Raw Market Data** | Data Lake (S3/GCS) | Immutable, append-only storage |
| **Cleaned Features** | Feature Store (Feast, Tecton) | Versioned feature definitions |
| **Model Artifacts** | Model Registry (MLflow) | Versioned model storage with metadata |
| **Experiment Results** | Experiment Tracking (W&B, MLflow) | Immutable experiment logs |
| **Production Metrics** | Monitoring Store (Prometheus, InfluxDB) | Time-series metrics |
| **Business KPIs** | Data Warehouse (Snowflake, Databricks) | Aggregated analytics |

### 16.2 Architectural Patterns

| Pattern | Description | When to Use |
|---------|-------------|-------------|
| **Feature Store** | Centralized layer serving as SoT for ML features | Real-time feature serving |
| **Data Warehouse/Lakehouse** | SoT for structured/semi-structured data | Batch analytics, training data |
| **Metadata Store** | Tracks lineage, versions, experiments | Governance, reproducibility |
| **Event Sourcing** | Immutable event log as alternative to SoT | Streaming ML systems |
| **CDC (Change Data Capture)** | Real-time data synchronization | Near-real-time ML pipelines |

### 16.3 Truth Hierarchy (V7 Engine Specific)

```
simulation > realized > contract > runtime > model
```

---

## 17. Open Source Tools Comparison

### 17.1 Tool Matrix

| Tool | Latest Version | Primary Focus | GitHub Stars | Quant Trading Fit |
|------|---------------|---------------|--------------|-------------------|
| **MLflow** | v3.14.0 | Experiment tracking, model registry | 19k+ | High |
| **Weights & Biases** | SaaS | Experiment tracking, visualization | 8k+ | High |
| **Metaflow** | 2.19.35 | Pipeline orchestration | 10.2k | High |
| **ZenML** | 0.96.1 | Pipeline orchestration, composable MLOps | 6.2k | High |
| **Pachyderm** | v2.12.2 | Data versioning, data-centric pipelines | 6.3k | High |
| **DVC** | 3.x | Data versioning, pipeline management | 14k+ | High |
| **LakeFS** | Latest | Git-like versioning for data lakes | 5k+ | Medium |

### 17.2 Capability Comparison

| Capability | MLflow | W&B | Metaflow | ZenML | Pachyderm | DVC |
|------------|--------|-----|----------|-------|-----------|-----|
| **Experiment Tracking** | Strong | Strongest | Basic | Strong | Weak | Basic |
| **Data Versioning** | Limited | Artifacts | Checkpoints | Integration | Best | Strong |
| **Pipeline Orchestration** | Projects | Integrations | Native | Native | Native | Native |
| **Model Registry** | Best | Good | None | Good | None | None |
| **Self-Hostable** | Yes | No | Yes | Yes | Yes | Yes |
| **Lineage Tracking** | Limited | Automatic | Limited | Full | Full | DAG-based |

### 17.3 Recommendation by Team Size

| Team Size | Recommended Stack | Rationale |
|-----------|-------------------|-----------|
| **Small (1-5)** | W&B (free tier) + Metaflow | Low barrier, excellent visualization, simple orchestration |
| **Medium (5-20)** | MLflow (self-hosted) + ZenML | Balance of control and flexibility |
| **Enterprise (20+)** | W&B Enterprise + Pachyderm + ZenML | Enterprise governance, advanced data versioning |

### 17.4 Recommended Stack for Quantitative Trading (V7 Engine)

**Primary:** MLflow + DVC
- MLflow for experiment tracking, metrics, and model registry
- DVC for data versioning and pipeline orchestration
- Both are self-hostable, Git-native, and production-ready

**Alternative:** W&B (if cloud-hosted is acceptable)
- Superior visualization and collaboration
- Strong artifact management

**Avoid:** Neptune.ai (acquired by OpenAI, discontinued March 2026)

**Hybrid Pattern:**
- lakeFS for large-scale data lake versioning if already on S3/GCS
- MLflow for experiment tracking UI and model registry
- DVC for pipeline orchestration and parameter tracking

---

## 18. Recommended Stack by Team Size

### For V7 Engine Context

Given the V7 Engine's existing architecture with AlphaForge, V7 Policy, Simulation, and Runtime subsystems:

| Component | Tool | Purpose |
|-----------|------|---------|
| Data Versioning | DVC + S3 remote | Market data snapshots, feature matrices |
| Experiment Tracking | MLflow (self-hosted) | Backtest results, model parameters |
| Pipeline Orchestration | DVC + Prefect/Airflow | Feature engineering, training, evaluation |
| Model Registry | MLflow Model Registry | Lifecycle: research -> validated -> paper -> live |
| Config Management | Hydra + OmegaConf | Experiment configs, mode-specific parameters |
| Feature Store | Feast (or custom) | Consistent features across research and production |
| Monitoring | Evidently AI + Prometheus | Data drift, model performance, latency |
| Statistical Testing | scipy + custom | Purged K-Fold, Bootstrap CI, KS test |

### Implementation Roadmap

**Phase 1 (Level 0 to 1): Foundation**
- Implement DVC for data versioning
- Set up MLflow for experiment tracking
- Containerize training environments (Docker)
- Create basic data pipeline
- Tools: DVC, MLflow, Docker, Git

**Phase 2 (Level 1 to 2): Automation**
- Build feature store (Feast)
- Implement CI pipeline: test feature transforms, model convergence
- Set up model registry with lifecycle stages
- Automate backtest validation gates
- Tools: Feast, GitHub Actions, MLflow Model Registry

**Phase 3 (Level 2 to 3): Deployment Automation**
- Implement A/B testing infrastructure
- Build automated promotion pipeline (backtest gate, paper trading gate, live gate)
- Full lineage tracking from data to trade decision
- Tools: Custom promotion framework, feature store monitoring

**Phase 4 (Level 3 to 4): Autonomous Operations**
- Implement drift detection (data drift, concept drift, signal decay)
- Automated retraining triggers based on performance degradation
- Policy-based model promotion and retirement
- Self-healing: auto-rollback when live performance drops below threshold
- Tools: Evidently AI, Event Grid, automated rollback logic

---

## 19. V7 Engine-Specific Integration Points

### 19.1 IC Threshold Framework (Production-Grade)

Standard IC health classification for alpha viability:

```python
IC_THRESHOLDS = {
    "alive": 0.03,      # IC > 0.03 -> alpha is viable
    "weak": 0.01,       # 0.01 < IC < 0.03 -> alpha is weakening
    "dead": 0.01,       # IC < 0.01 -> alpha is dead
}
```

**Action:** `alphaforge/features/evaluation.py` already computes per-timestamp Rank IC as a time-indexed Series. Add a decay monitor that tracks when IC crosses these thresholds.

### 19.2 CUSUM Parameters Matching V7 Constants

The existing `alphaforge/features/regime.py` implements CUSUM and HMM on price data. The research confirms these threshold conventions per mode:

| Mode | CUSUM Threshold | Rationale |
|------|----------------|-----------|
| SWING | 5.0 | Slower regime detection, wider bands |
| SCALP | 3.0 | Faster detection, tighter noise tolerance |
| AGGRESSIVE_SCALP | 2.0 | Most sensitive, earliest regime signal |

### 19.3 EWMA RiskMetrics Standard

```python
# Industry standard: lambda=0.94 daily -> half-life ~11 trading days
EWMA_LAMBDA = 0.94
HALF_LIFE_DAYS = -np.log(2) / np.log(0.94)  # approximately 11.2 days
```

### 19.4 Key Architectural Gap Identified

The existing `evaluation.py` already computes **per-timestamp Rank IC as a time-indexed Series**, but only aggregates it to mean/median/ICIR. The raw IC series is the natural substrate for adding decay monitoring **without any architectural changes** to the factor evaluation pipeline.

### 19.5 Recommended Module: Alpha Decay Monitor

A new `reports/alpha_decay_monitor.py` module would:

1. Ingest the per-timestamp IC series from `evaluation.py`
2. Apply rolling window analysis (60-day default)
3. Compute half-life estimates via OLS on log-autocorrelation
4. Trigger CUSUM alerts when IC crosses thresholds
5. Feed regime state from `regime.py` into factor weighting decisions

This follows the existing `reports/collapse_detector.py` pattern (sliding-window trend + severity escalation).

### 19.6 Concrete Integration Path

```
evaluation.py (Rank IC series)
    -> alpha_decay_monitor.py (rolling IC, half-life, CUSUM alerts)
    -> regime.py (existing CUSUM/HMM on price data)
    -> adaptive_position_sizing.py (regime-conditioned Kelly)
```

### 19.7 Critical Production Warning: Meta-Labeling

Meta-labeling (primary model for direction, meta model for trade filtering) showed $8.61/trade edge in backtest but **collapsed 86x in paper trading** due to alpha decay. Meta-labeling is a filter, not an alpha source. This confirms that decay monitoring must be a first-class concern, not an afterthought.

---

## Sources

- Google Cloud MLOps Documentation: https://cloud.google.com/architecture/ml-lifecycle-cloud
- Microsoft MLOps Maturity Model: https://learn.microsoft.com/en-us/azure/architecture/example-scenario/mlops/mlops-maturity-model
- NVIDIA AI Factory Framework: https://www.nvidia.com/en-us/data-center/ai-factory/
- MLflow Documentation: https://mlflow.org/docs/latest/
- Weights & Biases Documentation: https://docs.wandb.ai/
- DVC Documentation: https://doc.dvc.org/
- LakeFS Documentation: https://docs.lakefs.io/
- Metaflow Documentation: https://metaflow.org/
- ZenML Documentation: https://docs.zenml.io/
- Pachyderm Documentation: https://docs.pachyderm.com/
- de Prado, M.L. Advances in Financial Machine Learning (2018)
- QuantInsti Paper Trading Research: https://www.quantinsti.com/
- Meta: Reliability analysis and failure taxonomy for large-scale ML clusters
- TFX/TFMA Model Analysis: https://www.tensorflow.org/tfx/model_analysis/get_started
