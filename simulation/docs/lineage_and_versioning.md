# Lineage & Versioning — Semantic Change Tracking

## Purpose

This document defines every versioned surface in `/simulation`. Any semantic change to simulation logic bumps a version. Versions are stored in `SimulationOutput.lineage` and flow through the entire downstream pipeline: labels, datasets, models, evaluation, and monitoring.

## Core Rule

```
Any semantic change to stop/target/cost/horizon/time-exit/no-trade quality bumps a version.
No silent version change.
Old labels must remain traceable to the simulation family that produced them.
```

## Version Surfaces

| Surface | Field in Lineage | What It Covers | Bumped When |
|---|---|---|---|
| `simulation_family_version` | `lineage.simulation_family_version` | Engine-level semantics | Engine logic changes (precedence rules, path metrics, action selection) |
| `simulation_profile_version` | `lineage.simulation_profile_version` | Mode-specific parameters | Stop multiplier, target multiplier, ambiguity margin, penalty weights change |
| `cost_model_version` | `lineage.cost_model_version` | Composite cost model | Fee logic, slippage logic, total cost formula changes |
| `fee_model_version` | `lineage.fee_model_version` | Fee computation | Fee rate changes (maker/taker bps), fee formula changes |
| `slippage_model_version` | `lineage.slippage_model_version` | Slippage computation | Slippage bps, volatility adjustment logic changes |
| `horizon_family` | `lineage.horizon_family` | Holding horizon | Max holding bars, horizon end logic changes |
| `stop_family` | `lineage.stop_family` | Stop logic | Stop computation method, stop-first precedence changes |
| `target_family` | `lineage.target_family` | Target logic | Target computation method, target behavior changes |
| `time_exit_family` | `lineage.time_exit_family` | Time exit logic | Max holding bars, time exit precedence changes |
| `runtime_simulation_adapter_version` | (in adapter metadata) | Adapter layer | Adapter input construction, output normalization changes |
| `monte_carlo_family_version` | `monte_carlo_output.monte_carlo_family_version` | Monte Carlo logic | Path perturbation algorithm, distribution computation changes |
| `label_interpretation_version` | (in alphaforge labels) | Label derivation | How simulation outputs map to classification/regression labels |

## Version Bump Rules

### simulation_family_version

Bump when:

- Engine-level stop/target precedence changes (e.g., stop-first → target-first)
- Action utility function changes
- Path metric computation changes
- No-trade quality classification logic changes
- Comparative action selection algorithm changes
- Unresolved/invalidated semantics change
- New required input fields added

Do NOT bump for:

- Profile parameter changes (those bump `simulation_profile_version`)
- Cost model changes (those bump `cost_model_version`)
- Bug fixes that restore intended behavior (unless the behavior was relied upon)

Version format: `simfam-X.Y` (major.minor)

### simulation_profile_version

Bump when:

- Stop multiplier range changes
- Target multiplier range changes
- Ambiguity margin changes
- Min action edge changes
- Penalty weights (MAE, cost, time) change
- NO_TRADE tendency changes
- Max holding bars changes

Version format: `swing-profile-X.Y`, `scalp-profile-X.Y`, `aggressive_profile-X.Y`
Each mode profile is versioned independently.

### cost_model_version

Bump when:

- Fee rate changed (even external change like Binance fee update)
- Slippage formula changed
- New cost component added
- Net R formula changed

Version format: `cost-X.Y`

### horizon_family

Bump when:

- Max holding bars changed for a mode
- Horizon end semantics changed
- Invalidation multiplier changed

Family identifiers: `swing_horizon`, `scalp_horizon`, `aggressive_scalp_horizon`
Each horizon family carries its own version.

### stop_family and target_family

Bump when:

- Stop/target computation method changes (e.g., ATR → volatility bands)
- Stop/target multiplier calculation changes
- Stop-first → target-first (this bumps simulation_family_version too)

Family identifiers: `atr_wide`, `atr_medium`, `atr_tight`

## Lineage Flow Through the Pipeline

```
SimulationOutput.lineage
        │
        ▼
AlphaForge labels
  ├── simulation_family_version
  ├── simulation_profile_version
  ├── cost_model_version
  ├── horizon_family
  └── label_interpretation_version
        │
        ▼
AlphaForge datasets
  ├── All label lineage fields
  └── feature_schema_version
        │
        ▼
AlphaForge model artifacts
  ├── training_dataset_lineage (snapshot of all versions used)
  └── model_artifact_version
        │
        ▼
AlphaForge evaluation
  ├── All dataset lineage fields
  └── walk_forward_run_id
        │
        ▼
AlphaForge monitoring
  ├── Artifact lineage
  └── Drift detection on version boundaries
```

## Tracing Old Labels

Every label row in AlphaForge datasets carries:

```yaml
label_lineage:
  simulation_family_version: "simfam-1.0"
  simulation_profile_version: "swing-profile-1.0"
  cost_model_version: "cost-1.0"
  horizon_family: "swing_horizon"
  stop_family: "atr_wide"
  target_family: "atr_wide"
  label_interpretation_version: "labelinterp-1.0"
```

When a version bump occurs, old labels are NOT retroactively changed. New labels use the new versions. Evaluation can compare model performance across version boundaries.

## Compatibility Rules

1. **Backward-compatible**: Adding optional fields to a contract does not bump the major version.
2. **Breaking change**: Renaming/removing fields, changing field semantics, changing default behavior bumps the major version.
3. **Profile-only change**: Changing a mode profile parameter only bumps that profile's version, not `simulation_family_version`.
4. **Cost-only change**: Changing fee/slippage only bumps `cost_model_version` (and sub-versions), not `simulation_family_version`.
5. **Cross-bump**: A change may bump multiple versions. Example: changing stop-first to target-first bumps `simulation_family_version` AND `stop_family` AND possibly `target_family`.

## Version Registry

A version registry (config or database table) must track:

```yaml
simulation_versions:
  simfam-1.0:
    released: "2026-06-01"
    description: "Initial simulation family with conservative stop-first precedence"
    profiles: ["swing-profile-1.0", "scalp-profile-1.0", "aggressive_profile-1.0"]
    cost_model: "cost-1.0"
    
  simfam-1.1:
    released: "2026-07-15"
    description: "Added path_quality_score v2 with drawdown depth weighting"
    changes: ["path_metrics.path_quality_score"]
    profiles: ["swing-profile-1.0", "scalp-profile-1.0", "aggressive_profile-1.0"]  # unchanged
```

## Migration Policy

When a version bump occurs:

1. Old version continues to be supported for reading existing labels/datasets.
2. New labels are generated with the new version.
3. Evaluation reports must show the version boundary clearly.
4. Models trained on old labels may need re-training if the version bump is significant.
5. Monitoring dashboards should annotate the version boundary.

---

## Document Authority

**Canonical hub:** [ai_summary.md](ai_summary.md) — read this first for the full system synthesis and table of contents.

**Related docs for this topic:**

| [contracts.md](contracts.md) | Where version fields appear in contracts |
| [profiles.md](profiles.md) | Profile versioning per mode |
| [cost_model.md](cost_model.md) | Cost model versioning |
| [exits_and_horizons.md](exits_and_horizons.md) | Exit family versioning |
| [monte_carlo.md](monte_carlo.md) | Monte Carlo family versioning |
    
**Parent:** [../README.md](../README.md) — authority overview and ownership diagram.

**For implementation:** See [phases/](phases/) for v4.1.1 phase plans S0–S6.

**For validation:** See [validation.md](validation.md) for required test gates.

