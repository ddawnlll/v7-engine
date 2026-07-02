# Simulation Profiles — Mode-Specific Configuration

## Purpose

This document defines the mode-specific simulation profiles for `SWING`, `SCALP`, and `AGGRESSIVE_SCALP`. Each profile parameterizes the same simulation engine with different holding horizons, stop/target multipliers, ambiguity margins, and penalty weights.

Profile changes bump `simulation_profile_version`. No silent profile drift.

## Configuration Architecture

```
simulation_configs:
  swing:            ← SimulationProfile for SWING mode
  scalp:            ← SimulationProfile for SCALP mode
  aggressive_scalp: ← SimulationProfile for AGGRESSIVE_SCALP mode
```

All profiles share the same structure. Mode-specific differences are explicit.

---

## SWING Profile

| Parameter | Value | Notes |
|---|---|---|
| Primary interval | `4h` | Four-hour candles |
| Context intervals | `["1d", "1h"]` | Daily and hourly context |
| Refinement interval | `1h` | Hourly refinement |
| Max holding bars | `30` | Up to 5 days (30 × 4h) |
| Stop method | `atr_wide` | Wide ATR-based stop |
| Stop multiplier (ATR) | `2.0` | Conservative stop placement |
| Target method | `atr_wide` | Wide ATR-based target |
| Target multiplier (ATR) | `2.0` | Ambitious R:R targets |
| Ambiguity margin (R) | `0.20` | Actions within 0.20R utility are ambiguous |
| Min action edge (R) | `0.35` | Directional must beat NO_TRADE by 0.35R |
| MAE penalty weight | `1.0` | Moderate MAE penalization |
| Cost penalty weight | `1.0` | Moderate cost penalization |
| Time penalty weight | `0.3` | Lower time sensitivity |
| Funding rate | `0.0` | Perpetual funding cost per bar (bps) |
| NO_TRADE tendency | `LOW` | Default is directional when clear |

```yaml
simulation_configs:
  swing:
    profile_version: "1.0.0"
    mode: "SWING"
    primary_interval: "4h"
    context_intervals: ["1d", "1h"]
    refinement_intervals: ["1h"]
    max_holding_bars: 30
    stop_method: "atr_wide"
    stop_multiplier: 2.0
    target_method: "atr_wide"
    target_multiplier: 2.0
    ambiguity_margin_r: 0.20
    min_action_edge_r: 0.35
    mae_penalty_weight: 1.0
    cost_penalty_weight: 1.0
    time_penalty_weight: 0.3
    funding_rate: 0.0
    no_trade_default: false
```

---

## SCALP Profile

| Parameter | Value | Notes |
|---|---|---|
| Primary interval | `1h` | Hourly candles (config may also support 30m per repo convention) |
| Context intervals | `["4h", "15m"]` | 4h trend context, 15m refinement |
| Refinement interval | `15m` | 15-minute refinement |
| Max holding bars | `12` | Up to 12 hours |
| Stop method | `atr_medium` | Medium ATR-based stop |
| Stop multiplier (ATR) | `1.5` | Tighter than SWING |
| Target method | `atr_medium` | Medium ATR-based target |
| Target multiplier (ATR) | `1.5` | Proportional to stop |
| Ambiguity margin (R) | `0.10` | Actions within 0.10R utility are ambiguous |
| Min action edge (R) | `0.15` | Directional must beat NO_TRADE by 0.15R |
| MAE penalty weight | `2.0` | Higher MAE sensitivity |
| Cost penalty weight | `2.0` | Higher cost sensitivity |
| Time penalty weight | `1.5` | Moderate time sensitivity |
| Funding rate | `0.0` | Perpetual funding cost per bar (bps) |
| NO_TRADE tendency | `MEDIUM` | Directional when clear, NO_TRADE when ambiguous |

```yaml
simulation_configs:
  scalp:
    profile_version: "1.0.0"
    mode: "SCALP"
    primary_interval: "1h"
    context_intervals: ["4h", "15m"]
    refinement_intervals: ["15m"]
    max_holding_bars: 12
    stop_method: "atr_medium"
    stop_multiplier: 1.5
    target_method: "atr_medium"
    target_multiplier: 1.5
    ambiguity_margin_r: 0.10
    min_action_edge_r: 0.15
    mae_penalty_weight: 2.0
    cost_penalty_weight: 2.0
    time_penalty_weight: 1.5
    funding_rate: 0.0
    no_trade_default: true
```

**Note on SCALP primary interval:** Existing V7 docs reference both `30m` and `1h` as SCALP primary. The profile supports `1h` as the canonical default. If a deployment configures `30m`, it is a config/profile choice, not an architecture contradiction. The `primary_interval` field is config-driven.

---

## AGGRESSIVE_SCALP Profile

| Parameter | Value | Notes |
|---|---|---|
| Primary interval | `15m` | Fifteen-minute candles |
| Context intervals | `["1h", "5m"]` | Hourly context, 5m refinement |
| Refinement interval | `5m` | Five-minute refinement |
| Max holding bars | `5` | Up to 75 minutes |
| Stop method | `atr_tight` | Tight ATR-based stop |
| Stop multiplier (ATR) | `1.0` | Very tight stop |
| Target method | `atr_tight` | Tight ATR-based target |
| Target multiplier (ATR) | `1.0` | Quick targets |
| Ambiguity margin (R) | `0.05` | Very small ambiguity window |
| Min action edge (R) | `0.08` | Small edge needed |
| MAE penalty weight | `3.0` | Very high MAE sensitivity |
| Cost penalty weight | `3.0` | Very high cost sensitivity |
| Time penalty weight | `2.5` | High time sensitivity |
| Funding rate | `0.0` | Perpetual funding cost per bar (bps) |
| NO_TRADE tendency | `HIGH` | Default NO_TRADE, trade only with strong signals |

```yaml
simulation_configs:
  aggressive_scalp:
    profile_version: "1.0.0"
    mode: "AGGRESSIVE_SCALP"
    primary_interval: "15m"
    context_intervals: ["1h", "5m"]
    refinement_intervals: ["5m"]
    max_holding_bars: 5
    stop_method: "atr_tight"
    stop_multiplier: 1.0
    target_method: "atr_tight"
    target_multiplier: 1.0
    ambiguity_margin_r: 0.05
    min_action_edge_r: 0.08
    mae_penalty_weight: 3.0
    cost_penalty_weight: 3.0
    time_penalty_weight: 2.5
    funding_rate: 0.0
    no_trade_default: true
```

---

## Action Utility Function

Each mode uses its profile weights to compute per-action utility. Utility determines `best_action` selection:

```python
def compute_action_utility(action_outcome, profile):
    """
    Returns a single utility score for an action.
    Higher = better.
    """
    return (
        action_outcome.realized_r_net
        - profile.mae_penalty_weight * abs(action_outcome.path_metrics.mae_r)
        - profile.cost_penalty_weight * action_outcome.total_cost_r
        - profile.time_penalty_weight * (action_outcome.path_metrics.time_to_mfe or 0) * 0.1
    )

def compute_no_trade_utility(no_trade_outcome):
    """
    No-trade utility is its saved_loss_score.
    No-trade avoids adverse movement. Its value is in loss avoidance.
    """
    return no_trade_outcome.saved_loss_score
```

## Profile Selection

Profiles are selected based on the `mode` field in `SimulationInput`. The mode router in v7 selects the profile before calling the simulation engine:

```
SimulationInput.mode == "SWING"             → swing profile
SimulationInput.mode == "SCALP"             → scalp profile
SimulationInput.mode == "AGGRESSIVE_SCALP"  → aggressive_scalp profile
```

Invalid or unknown modes must produce an explicit error. No silent default fallback.

## Profile Versioning

Any change to any profile parameter bumps `simulation_profile_version` for that profile. Version bumps must be:

- Recorded in lineage
- Propagated to dataset metadata
- Visible in evaluation and monitoring

Profiles are versioned independently. A change to SWING parameters does not bump SCALP or AGGRESSIVE_SCALP versions (unless the profile structure itself changes).

## Regime Interaction (Explicit, Not Hidden)

Regime detection produces constraints at the policy layer, not inside simulation:

```text
Regime constraints may produce:
  constraint_level = ADVISORY | SOFT_BLOCK | HARD_BLOCK
  reason_code = regime_gate_forced_no_trade
  reason_code = regime_blocked_direction
  reason_code = regime_threshold_multiplier_applied

But the simulation engine must still preserve comparative output visibility:
  long simulated outcome
  short simulated outcome
  no-trade outcome
  best_action before policy constraints
  final_policy_action after policy constraints, if applicable
```

The `TRANSITION` regime stop multiplier of 99.0 (referenced in existing docs) is a **policy-layer override**, not a simulation semantic. Simulation must still compute the raw economic outcomes so that monitoring, evaluation, and promotion evidence are not hidden behind regime gates.

## Success Thresholds (for Downstream Labels)

These are alphaforge's label interpretation thresholds, not simulation config. Included here for cross-reference:

| Parameter | SWING | SCALP | AGGRESSIVE_SCALP |
|---|---|---|---|
| `min_net_r_for_success` | 0.75 | 0.20 | 0.10 |
| `max_mae_r_for_success` | -0.60 | -0.25 | -0.10 |
| `min_mfe_r_for_good_exit` | 1.0 | — | — |
| `allow_no_trade_on_ambiguity` | false | true | true |
| `no_trade_default` | false | true | true |

---

## Document Authority

**Canonical hub:** [ai_summary.md](ai_summary.md) — read this first for the full system synthesis and table of contents.

**Related docs for this topic:**

| [architecture.md](architecture.md) | How profiles are resolved at runtime |
| [cost_model.md](cost_model.md) | Cost model paired with each profile |
| [exits_and_horizons.md](exits_and_horizons.md) | Stop/target multipliers from profiles |
| [lineage_and_versioning.md](lineage_and_versioning.md) | Profile version bump rules |
    
**Parent:** [../README.md](../README.md) — authority overview and ownership diagram.

**For implementation:** See [phases/](phases/) for v4.1.1 phase plans S0–S6.

**For validation:** See [validation.md](validation.md) for required test gates.

