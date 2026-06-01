# Monte Carlo Robustness — Diagnostic & Distributional Evidence

## Purpose

This document defines Monte Carlo robustness simulation within the `/simulation` engine. Monte Carlo produces distributional evidence about expected outcomes. It is diagnostic only — it does not replace realized simulation truth.

## Core Principle

```
Monte Carlo is diagnostic/distributional evidence.
Monte Carlo does not replace realized simulation truth.
Monte Carlo outputs must carry separate lineage (monte_carlo_run_id).
```

## What Monte Carlo Provides

Monte Carlo answers distributional questions that a single future path cannot:

| Question | Monte Carlo Metric |
|---|---|
| How wide is the expected R distribution? | Standard deviation, percentile ranges |
| What's the downside risk? | CVaR / expected shortfall, p5 |
| What's the probability of hitting target before stop? | target_before_stop_probability |
| What's the probability of hitting stop before target? | stop_before_target_probability |
| How stable is the confidence in expected R? | confidence_stability |
| What's the tail risk? | tail_risk (beyond p5) |

## How Monte Carlo Works

```
1. Take the baseline SimulationInput with its realized future_path
2. Generate N perturbed future paths (perturbation method is versioned)
3. Run the same simulation engine on each perturbed path
4. Collect SimulationOutput for each path
5. Aggregate into MonteCarloOutput
```

### Perturbation Methods (First Version)

**Method 1 — Price Noise Perturbation:**
Add small Gaussian noise to each candle in the future path:
```
perturbed_bar[i].close = bar[i].close * (1 + noise), noise ~ N(0, sigma)
perturbed_bar[i].high  = max(bar[i].high, perturbed_bar[i].close)
perturbed_bar[i].low   = min(bar[i].low, perturbed_bar[i].close)
sigma = configurable (default: 0.002, i.e., 0.2% std dev)
```

**Method 2 — Path Resampling with Bootstrap:**
Resample bar-level returns with replacement from recent history:
```
For each future bar i:
  sample a return r_i from an empirical distribution of k-bar returns
  bar[i].close = bar[i-1].close * (1 + r_i)
```

The perturbation method is configurable and versioned. First version uses Method 1 with `sigma = 0.002`.

### Number of Paths

Default: `N = 100` paths
Configurable range: `50–1000`

More paths = better distributional accuracy, but higher computational cost. For production monitoring, 100 paths is adequate. For deep backtesting, 500–1000 may be warranted.

## Monte Carlo Output

```yaml
MonteCarloOutput:
  monte_carlo_run_id: "mc_20260601_001"
  monte_carlo_family_version: "mcfam-1.0"
  base_simulation_run_id: "sim_20260601_001"    # links to the realized simulation
  
  # Perturbation metadata
  perturbation_method: "price_noise"
  perturbation_sigma: 0.002
  num_paths: 100
  
  # Distribution of expected R (across all N paths)
  expected_r_distribution:
    mean: 0.45
    std: 0.32
    p5: -0.15      # 5th percentile
    p25: 0.22
    p50: 0.44      # median
    p75: 0.68
    p95: 1.05      # 95th percentile
  
  # Downside risk
  downside_risk: 0.18    # CVaR / expected shortfall (average of worst 5%)
  
  # Path-level probabilities
  target_before_stop_probability: 0.62
  stop_before_target_probability: 0.28
  
  # Tail risk
  tail_risk: 0.35         # worst-case beyond p5 (max drawdown)
  
  # Confidence stability
  confidence_stability: 0.78  # 0–1: how stable the expected R is across paths
                               # (1 = perfectly stable, 0 = highly variable)
  
  # Per-path detail (optional, for deep analysis)
  path_details: optional array of per-path SimulationOutput references
```

## Interpreting Monte Carlo Evidence

| Monte Carlo Pattern | Interpretation | Action |
|---|---|---|
| High mean R, tight distribution | Strong, reliable signal | High conviction |
| High mean R, wide distribution | Potential return, high risk | Size down, tight stops |
| Low mean R, tight distribution | Weak signal, consistent | Skip or minimal size |
| Low mean R, wide distribution | Weak, unreliable | Skip |
| Negative mean R | Adverse expectation | Hard skip |
| HIGH target_before_stop prob, LOW stop_before_target prob | Favorable R:R | Normal size |
| LOW target_before_stop prob, HIGH stop_before_target prob | Unfavorable R:R | Skip or micro-size |
| LOW confidence_stability (< 0.5) | Path-sensitive, fragile | Skip or deeply discounted |

## Monte Carlo vs Realized Simulation

| Aspect | Realized Simulation | Monte Carlo |
|---|---|---|
| Input | Actual future path | Perturbed/synthetic paths |
| Purpose | Economic truth for labels, evaluation, outcomes | Distributional evidence for sizing, risk assessment |
| Authority | Definitive for realized R | Diagnostic only |
| Lineage | simulation_run_id | monte_carlo_run_id |
| Used for labels? | Yes | No |
| Used for promotion? | Yes (as primary evidence) | Yes (as supplementary evidence) |
| Replaces realized truth? | — | Never |

## First-Phase Scope

First-phase Monte Carlo is conservative:

- Perturbation: price noise only (Method 1)
- N = 100 paths
- Computed on demand (not every simulation)
- Used for:
  - Pre-trade risk assessment (diagnostic)
  - Promotion evidence (supplementary)
  - Downside risk evaluation
  - Confidence stability measurement

Not included in first phase:
- Full path resampling with regime-aware perturbation
- Real-time Monte Carlo for every decision (too expensive)
- Multi-path horizon optimization
- Correlation-aware multi-symbol Monte Carlo

## Config Surface

```yaml
monte_carlo_config:
  enabled: true
  family_version: "mcfam-1.0"
  default_num_paths: 100
  min_paths: 50
  max_paths: 1000
  perturbation_method: "price_noise"
  perturbation_sigma: 0.002
  perturbation_seed: optional  # for reproducibility
```

## Testing

- Monte Carlo output carries `monte_carlo_run_id` and distinguishable lineage
- Monte Carlo `SimulationOutput` per-path matches engine output format
- `target_before_stop_probability + stop_before_target_probability <= 1.0` (because some paths are time-exit/horizon-end/unresolved)
- Perturbation sigma = 0 produces identical output to base simulation (deterministic test)
- Monte Carlo output NEVER replaces base simulation output in labels or datasets

---

## Document Authority

**Canonical hub:** [ai_summary.md](ai_summary.md) — read this first for the full system synthesis and table of contents.

**Related docs for this topic:**

| [contracts.md](contracts.md) | MonteCarloOutput schema |
| [lineage_and_versioning.md](lineage_and_versioning.md) | monte_carlo_family_version |
| [validation.md](validation.md) | Monte Carlo test requirements |
| [replay_paper_and_runtime_hosting.md](replay_paper_and_runtime_hosting.md) | Monte Carlo driver in adapter model |
    
**Parent:** [../README.md](../README.md) — authority overview and ownership diagram.

**For implementation:** See [phases/](phases/) for v4.1.1 phase plans S0–S6.

**For validation:** See [validation.md](validation.md) for required test gates.

