# AlphaForge Label Contract

**Purpose:** Define how SimulationOutput is transformed into AlphaForge training labels. This is the bridge between simulation economic truth and alpha discovery.

**Authority:** Simulation owns economic truth. AlphaForge consumes it and produces labels. This document is LOCKED.

---

## Core Principle

SimulationOutput is the **authoritative economic truth** for AlphaForge labels. AlphaForge does NOT invent labels from price data directly — it consumes simulation outcomes and transforms them into structured label datasets suitable for supervised learning.

---

## Label Source: SimulationOutput

AlphaForge consumes `SimulationOutput` (schema: [simulation_output.schema.json](../../contracts/schemas/simulation_output.schema.json)) and produces `AlphaForgeLabel` rows (schema: [alphaforge_label.schema.json](../../contracts/schemas/alphaforge_label.schema.json)).

The field-level mapping is documented in: [../../contracts/mappings/simulation_to_alphaforge.md](../../contracts/mappings/simulation_to_alphaforge.md)

---

## Label Fields

### Derived from ActionOutcome (LONG / SHORT)

| Label Field | Source Field | Description |
|-------------|-------------|-------------|
| long_R_net | long_outcome.realized_r_net | Net R for LONG_NOW |
| short_R_net | short_outcome.realized_r_net | Net R for SHORT_NOW |
| long_mfe_R | long_outcome.path_metrics.mfe_r | MFE in R for LONG |
| short_mfe_R | short_outcome.path_metrics.mfe_r | MFE in R for SHORT |
| long_mae_R | long_outcome.path_metrics.mae_r | MAE in R for LONG |
| short_mae_R | short_outcome.path_metrics.mae_r | MAE in R for SHORT |

### Derived from NoTradeOutcome

| Label Field | Source Field | Description |
|-------------|-------------|-------------|
| saved_loss_score | no_trade_outcome.saved_loss_score | Normalized saved loss score |
| missed_opportunity_score | no_trade_outcome.missed_opportunity_score | Normalized missed opportunity score |
| no_trade_quality | no_trade_outcome.no_trade_quality | CORRECT_NO_TRADE, SAVED_LOSS, MISSED_OPPORTUNITY, AMBIGUOUS_NO_TRADE |

### Classification Labels

| Label Field | Source Field | Description |
|-------------|-------------|-------------|
| best_action_label | best_action | LONG_NOW, SHORT_NOW, NO_TRADE, AMBIGUOUS_STATE |
| label_validity | Derived from resolution_status + is_ambiguous | Controls whether row is used for training |

### Cost-Aware Labels

Costs are embedded in the label values (realized_r_net already includes fees and slippage):

| Label Field | Source Field | Description |
|-------------|-------------|-------------|
| long_R_gross | long_outcome.realized_r_gross | Gross R before costs |
| short_R_gross | short_outcome.realized_r_gross | Gross R before costs |
| cost_impact_long | long_outcome.total_cost_r | Total cost impact on LONG |
| cost_impact_short | short_outcome.total_cost_r | Total cost impact on SHORT |

---

## Label Dataset Specification

The LabelDatasetSpec (schema: [label_dataset_spec.schema.json](../../contracts/schemas/alphaforge/label_dataset_spec.schema.json)) documents:

| Field | Description |
|-------|-------------|
| label_dataset_id | Unique identifier |
| mode | SCALP, AGGRESSIVE_SCALP, SWING |
| simulation_profile_id | Which simulation profile was used |
| label_source | Always "simulation_output" |
| label_fields | Which label fields are included |
| cost_model_ref | Cost model version |
| funding_status | Current: "DEFERRED" |
| no_trade_comparison | Summary of NO_TRADE label distribution |
| lineage | Full provenance chain |

---

## NO_TRADE Comparison Requirement

Every label dataset must include NO_TRADE as a first-class label, not as a fallback:

- **CORRECT_NO_TRADE:** The best action was to do nothing; directional actions would have lost.
- **SAVED_LOSS:** NO_TRADE avoided a loss.
- **MISSED_OPPORTUNITY:** NO_TRADE missed a gain.
- **AMBIGUOUS_NO_TRADE:** Unclear whether trading or not trading was better.

The label distribution must be reported. If NO_TRADE dominates directional labels, the mode may not be tradeable.

---

## Label Leakage Rules

1. Labels are derived from **future** price action (post-decision). They MUST NOT be used for feature computation at the same decision point.
2. Purge windows between training and test splits must account for label overlap.
3. Labels derived from invalidated or unresolved simulation runs must be excluded from training.
4. `label_validity` must be checked before any row enters training.

---

## Cost-Aware Labels

Labels are net of costs (fees + slippage). A positive long_R_net means LONG was profitable AFTER costs.
- If long_R_gross > 0 but long_R_net < 0, costs consumed the edge.
- This case MUST be flagged in the label dataset.
- Alpha theses that only work gross (not net) are automatically rejected.

---

## Funding Deferred Limitation

**Current status: DEFERRED.** The funding cost model is not yet implemented.

Impact on labels:
- Labels currently reflect fee + slippage costs only.
- Funding costs (for perpetual futures) are NOT included.
- Labels are valid for SPOT-equivalent analysis only.
- Any alpha thesis requiring perpetual/live trading must flag this limitation.
- Labels MUST carry `funding_status: "DEFERRED"` until the funding model is implemented.

---

## Mode-Specific Label Readiness

| Mode | Label Status | Notes |
|------|-------------|-------|
| SCALP | Requires labels from simulation | High sensitivity to cost assumptions |
| AGGRESSIVE_SCALP | Requires labels from simulation | Extreme cost sensitivity, liquidity caveats |
| SWING | Requires labels from simulation | Lower cost sensitivity, baseline validation |

---

## Related Docs

- [ai_summary.md](ai_summary.md)
- [data_contract.md](data_contract.md)
- [feature_contract.md](feature_contract.md)
- [report_contracts.md](report_contracts.md)
- [validation_contract.md](validation_contract.md)

## Related Contracts

- [../../contracts/schemas/alphaforge/label_dataset_spec.schema.json](../../contracts/schemas/alphaforge/label_dataset_spec.schema.json)
- [../../contracts/schemas/simulation_output.schema.json](../../contracts/schemas/simulation_output.schema.json)
- [../../contracts/schemas/alphaforge_label.schema.json](../../contracts/schemas/alphaforge_label.schema.json)
- [../../contracts/mappings/simulation_to_alphaforge.md](../../contracts/mappings/simulation_to_alphaforge.md)

## Forbidden Assumptions

- Labels do NOT represent trade signals. They are training targets.
- Positive long_R_net does NOT mean "always go long." It is one label among many.
- AlphaForge does NOT modify labels to make an alpha look better.

## Open Holds

- Funding DEFERRED blocks funding-aware labels.
- Label quality depends on simulation profile accuracy.
