# Simulation → AlphaForge Mapping

**Purpose:** Document how SimulationOutput fields map to AlphaForge label and report concepts. This is the authoritative bridge between simulation economic truth and alpha discovery.

**Authority:** Simulation owns economic truth. AlphaForge consumes it. This mapping is LOCKED.

---

## SimulationOutput → LabelDatasetSpec

### ActionOutcome → Label Fields

| SimulationOutput Field | AlphaForge Label Concept | Description |
|------------------------|--------------------------|-------------|
| `long_outcome.realized_r_net` | `long_R_net` | Net R for LONG action (after fees + slippage) |
| `short_outcome.realized_r_net` | `short_R_net` | Net R for SHORT action (after fees + slippage) |
| `long_outcome.realized_r_gross` | `long_R_gross` | Gross R for LONG (before costs) |
| `short_outcome.realized_r_gross` | `short_R_gross` | Gross R for SHORT (before costs) |
| `long_outcome.fee_cost_r` | `fee_cost_long` | Fee impact on LONG in R terms |
| `long_outcome.slippage_cost_r` | `slippage_cost_long` | Slippage impact on LONG in R terms |
| `long_outcome.total_cost_r` | `total_cost_long` | Total cost impact on LONG |
| `short_outcome.fee_cost_r` | `fee_cost_short` | Fee impact on SHORT in R terms |
| `short_outcome.slippage_cost_r` | `slippage_cost_short` | Slippage impact on SHORT in R terms |
| `short_outcome.total_cost_r` | `total_cost_short` | Total cost impact on SHORT |

### ActionOutcome → Path Metrics

| SimulationOutput Field | AlphaForge Label Concept | Description |
|------------------------|--------------------------|-------------|
| `long_outcome.path_metrics.mfe_r` | `long_mfe_R` | Maximum favourable excursion for LONG |
| `short_outcome.path_metrics.mfe_r` | `short_mfe_R` | Maximum favourable excursion for SHORT |
| `long_outcome.path_metrics.mae_r` | `long_mae_R` | Maximum adverse excursion for LONG |
| `short_outcome.path_metrics.mae_r` | `short_mae_R` | Maximum adverse excursion for SHORT |
| `long_outcome.path_metrics.path_quality_score` | `long_path_quality` | Path quality for LONG (0-1) |
| `short_outcome.path_metrics.path_quality_score` | `short_path_quality` | Path quality for SHORT (0-1) |
| `long_outcome.path_metrics.path_quality_bucket` | `long_path_quality_bucket` | HIGH/MEDIUM/LOW |
| `short_outcome.exit_reason` | `exit_reason` | STOP_HIT / TARGET_HIT / TIME_EXIT / HORIZON_END |

### Best Action → Classification Labels

| SimulationOutput Field | AlphaForge Label Concept | Description |
|------------------------|--------------------------|-------------|
| `best_action` | `best_action_label` | LONG_NOW / SHORT_NOW / NO_TRADE / AMBIGUOUS_STATE |
| `action_gap_r` | `action_gap_R` | Utility gap between best and second-best |
| `regret_r` | `regret_R` | Regret relative to best action |
| `is_ambiguous` | `is_ambiguous` | Whether action gap is below ambiguity margin |
| `resolution_status` | `label_validity` | COMPLETE → valid; UNRESOLVED/INVALIDATED → invalid |

### NoTradeOutcome → NO_TRADE Quality

| SimulationOutput Field | AlphaForge Label Concept | Description |
|------------------------|--------------------------|-------------|
| `no_trade_outcome.saved_loss_r` | `saved_loss_R` | Loss avoided by not trading |
| `no_trade_outcome.saved_loss_score` | `saved_loss_score` | Normalized saved loss (0-1) |
| `no_trade_outcome.missed_opportunity_r` | `missed_opportunity_R` | Gain missed by not trading |
| `no_trade_outcome.missed_opportunity_score` | `missed_opportunity_score` | Normalized missed opportunity (0-1) |
| `no_trade_outcome.no_trade_quality` | `no_trade_quality` | CORRECT_NO_TRADE / SAVED_LOSS / MISSED_OPPORTUNITY / AMBIGUOUS_NO_TRADE |
| `no_trade_outcome.was_correct_skip` | `was_correct_skip` | True if NO_TRADE was the correct decision |

---

## SimulationOutput → ValidationReport Metrics

### PathMetrics → Report Metrics

| SimulationOutput Field | ValidationReport Use | Description |
|------------------------|---------------------|-------------|
| `long_outcome.path_metrics` | Per-decision path quality | Used to assess decision quality distribution |
| `no_trade_outcome.*` | NO_TRADE comparison | Foundation for "does alpha beat doing nothing?" |
| `action_gap_r` | Ambiguity analysis | How often is the decision clear vs. ambiguous? |
| `regret_r` | Regret analysis | What is the cost of wrong decisions? |

---

## Cost Fields → Net R

### Cost Impact on Labels

| SimulationOutput Field | Impact | Description |
|------------------------|--------|-------------|
| `long_outcome.total_cost_r` | Reduces `long_R_net` vs `long_R_gross` | Cost-aware labels |
| `short_outcome.total_cost_r` | Reduces `short_R_net` vs `short_R_gross` | Cost-aware labels |
| All cost fields | Must be > 0 for alpha to survive | Cost stress validation |

**Key rule:** If `realized_r_gross > 0` but `realized_r_net < 0`, the alpha's edge is consumed by costs. This must be flagged in the label dataset.

---

## Funding DEFERRED Limitation

**Current status:** The funding cost model is NOT implemented in simulation.

**Impact on mapping:**
- `cost_model_ref` in LabelDatasetSpec points to a cost model that excludes funding.
- Labels are valid for SPOT-equivalent analysis only.
- Perpetual/live trading labels would require funding costs, which are not available.
- This limitation is propagated to all downstream artifacts: labels, reports, validation, and handoff packages.

---

## Related Docs

- [../alphaforge/docs/label_contract.md](../alphaforge/docs/label_contract.md)
- [../alphaforge/docs/data_contract.md](../alphaforge/docs/data_contract.md)
- [../simulation/docs/cost_model.md](../simulation/docs/cost_model.md)
- [../simulation/docs/contracts.md](../simulation/docs/contracts.md)

## Related Contracts

- [../schemas/simulation_output.schema.json](../schemas/simulation_output.schema.json)
- [../schemas/alphaforge_label.schema.json](../schemas/alphaforge_label.schema.json)
- [../schemas/alphaforge/label_dataset_spec.schema.json](../schemas/alphaforge/label_dataset_spec.schema.json)
- [simulation_to_alphaforge.json](simulation_to_alphaforge.json) — field-level JSON mapping

## Forbidden Assumptions

- SimulationOutput is NOT modified by AlphaForge — it is consumed as-is.
- Labels do NOT represent trade signals — they represent economic outcomes.
- Cost fields are NOT optional — cost-aware labels are mandatory.

## Open Holds

- Funding DEFERRED — mapping excludes funding cost fields.
- Exact field mapping for per-mode specifics may be refined during implementation.
