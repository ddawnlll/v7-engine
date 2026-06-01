# No-Trade Quality — First-Class Action Evaluation

## Purpose

This document defines how `NO_TRADE` is evaluated as a first-class action in the `/simulation` engine. No-trade is not the absence of simulation; it has real economic outcomes that must be computed, classified, and fed to downstream pipelines.

## Core Principle

```
NO_TRADE is a real learned action that competes directly with LONG_NOW and SHORT_NOW.

A correct skip is economically valuable.
A missed opportunity is economically costly.
```

## No-Trade Quality Classifications

| Classification | Meaning | When |
|---|---|---|
| `CORRECT_NO_TRADE` | Skipping was the right choice | Both directional actions lose money, or best directional action < min_action_edge |
| `SAVED_LOSS` | Skipping avoided a loss | At least one directional action lost money, and the net loss avoided exceeds threshold |
| `MISSED_OPPORTUNITY` | Skipping missed a profitable trade | Best directional action produced net positive R above min_action_edge |
| `AMBIGUOUS_NO_TRADE` | The no-trade decision is borderline | Action gap is within ambiguity margin, or outcomes are contradictory |

## Saved Loss Computation

Saved loss measures how much adverse movement was avoided by not trading:

```python
def compute_saved_loss(long_outcome, short_outcome):
    """
    Returns the maximum adverse R avoided by skipping.
    If both directional actions are profitable, saved_loss is 0.
    """
    worst_directional_r = min(long_outcome.realized_r_net, short_outcome.realized_r_net)
    return max(0.0, -worst_directional_r)

# Normalized score (0–1):
# saved_loss_score = saved_loss_r / max_saved_loss_r_expected
# where max_saved_loss_r_expected is typically 1.0 (1R stop)
```

### Saved Loss Score Examples

| long_R_net | short_R_net | saved_loss_r | Interpretation |
|---|---|---|---|
| -0.8 | +0.3 | 0.8 | Short would have earned 0.3R, but long would have lost 0.8R. Skipping avoided 0.8R loss. |
| -0.2 | -0.5 | 0.5 | Both lose. Skipping avoided the worse 0.5R loss. |
| +0.5 | +0.3 | 0.0 | Both win. No loss avoided. (Focus shifts to missed_opportunity.) |
| +0.1 | -0.1 | 0.1 | Marginal. Close to ambiguous. |

## Missed Opportunity Computation

Missed opportunity measures how much potential gain was missed by skipping:

```python
def compute_missed_opportunity(long_outcome, short_outcome, profile):
    """
    Returns the maximum positive R missed by skipping.
    Only counts if the best action exceeds min_action_edge_r.
    """
    best_directional_r = max(long_outcome.realized_r_net, short_outcome.realized_r_net)
    if best_directional_r > profile.min_action_edge_r:
        return best_directional_r
    return 0.0

# Normalized score (0–1):
# missed_opportunity_score = missed_opportunity_r / max_opportunity_r_expected
# where max_opportunity_r_expected is typically target_multiplier
```

### Missed Opportunity Score Examples

| long_R_net | short_R_net | missed_opp_r | min_edge (SWING=0.35) | Counted? |
|---|---|---|---|---|
| +1.5 | +0.8 | 1.5 | yes | Missed 1.5R opportunity |
| +0.3 | +0.1 | 0.0 | no (0.3 < 0.35) | Below edge, not counted |
| -0.5 | +0.9 | 0.9 | yes | Missed 0.9R opportunity |
| -0.2 | -0.8 | 0.0 | no (loss) | Both lose, no opportunity |

## No-Trade Quality Assignment

```python
def classify_no_trade(saved_loss_r, missed_opportunity_r, profile):
    if saved_loss_r == 0 and missed_opportunity_r == 0:
        return "CORRECT_NO_TRADE"  # Neither lost nor missed (both directional near-zero)
    if saved_loss_r > 0 and missed_opportunity_r == 0:
        return "SAVED_LOSS"
    if missed_opportunity_r > 0:
        return "MISSED_OPPORTUNITY"
    if saved_loss_r > 0 and missed_opportunity_r > 0:
        # Contradictory: one direction lost, the other won
        # Classify as AMBIGUOUS if the gap is small
        if abs(saved_loss_r - missed_opportunity_r) < profile.ambiguity_margin_r:
            return "AMBIGUOUS_NO_TRADE"
        # Otherwise, the larger effect dominates
        elif saved_loss_r >= missed_opportunity_r:
            return "SAVED_LOSS"
        else:
            return "MISSED_OPPORTUNITY"
    return "CORRECT_NO_TRADE"
```

## How No-Trade Quality Is Used Downstream

### AlphaForge Labels

| Simulation Output | AlphaForge Label Field |
|---|---|
| `no_trade_outcome.saved_loss_score` | `saved_loss_score` |
| `no_trade_outcome.missed_opportunity_score` | `missed_opportunity_score` |
| `no_trade_outcome.no_trade_quality` | `no_trade_quality_label` |
| `no_trade_outcome.was_correct_skip` | `skip_was_correct` |

### AlphaForge Evaluation

- **No-trade quality distribution**: What fraction of NO_TRADE decisions were correct, saved loss, or missed opportunity?
- **Regret analysis**: When the system chose NO_TRADE, what was the counterfactual best action?
- **Calibration**: Is the model's confidence aligned with actual no-trade quality?

### AlphaForge Calibration

- Probability of `CORRECT_NO_TRADE` conditional on predicted `P(NO_TRADE)`
- Reliability of no-trade confidence scores

### AlphaForge Monitoring

- **Saved-loss rate**: % of no-trades that avoided losses
- **Missed-opportunity rate**: % of no-trades that missed profitable trades
- **Regime-forced vs model-preferred no-trade rate**: How often does regime force no-trade when the model preferred a directional action?

## Relationship to Regret and Action Gap

| Metric | Meaning | Computed From |
|---|---|---|
| `action_gap_r` | Utility gap between best and second-best action | `abs(best_action_utility - second_best_action_utility)` |
| `regret_r` | Difference between actual action and best action | `best_action_utility - actual_action_utility` (0 if actual is best) |
| `saved_loss_r` | Loss avoided by not taking the worst action | `max(0, -min(long_R_net, short_R_net))` |
| `missed_opportunity_r` | Gain missed by not taking the best action | `max(0, max(long_R_net, short_R_net))` |

These are all available in `SimulationOutput` and flow into labels, evaluation, and monitoring.

## No-Trade Is Not a Fallback

In V7 + `/simulation`, `NO_TRADE` must never be:

- The default when the model is uncertain (that's `AMBIGUOUS_STATE`, which is explicit)
- A silent suppressor of directional signals
- A cosmetic fallback after all other systems fail
- Invisible in evaluation metrics

`NO_TRADE` is a first-class action that competes with `LONG_NOW` and `SHORT_NOW` under the same cost, exit, and path-metric semantics.

## Configurable Thresholds (AlphaForge)

These are alphaforge label interpretation thresholds, not simulation engine internals:

| Threshold | SWING | SCALP | AGGRESSIVE_SCALP |
|---|---|---|---|
| Saved-loss threshold | 0.20R | 0.10R | 0.05R |
| Missed-opportunity threshold | 0.35R | 0.15R | 0.08R |
| No-trade correctness threshold | 0.20R | 0.10R | 0.05R |

---

## Document Authority

**Canonical hub:** [ai_summary.md](ai_summary.md) — read this first for the full system synthesis and table of contents.

**Related docs for this topic:**

| [contracts.md](contracts.md) | NoTradeOutcome schema |
| [exits_and_horizons.md](exits_and_horizons.md) | How no-trade interacts with exit semantics |
| [profiles.md](profiles.md) | Mode-specific no-trade tendency and thresholds |
| [validation.md](validation.md) | No-trade quality test requirements |
    
**Parent:** [../README.md](../README.md) — authority overview and ownership diagram.

**For implementation:** See [phases/](phases/) for v4.1.1 phase plans S0–S6.

**For validation:** See [validation.md](validation.md) for required test gates.

