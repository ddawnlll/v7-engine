# AlphaForge → V7 Mapping

**Purpose:** Document how AlphaForge research outputs map to V7 evaluation and promotion gates. This is the authoritative handoff bridge between alpha discovery and policy acceptance.

**Authority:** AlphaForge produces evidence. V7 is the final acceptance authority. This mapping is LOCKED.

---

## AlphaForge Output → V7 Gates

### ModeResearchReport → V7 Evaluation Gates

| AlphaForge Evidence | V7 Gate | Purpose |
|--------------------|---------|---------|
| `data_scope` (symbols, date range, data quality) | G0: Data Quality | Confirm data integrity and scope |
| `feature_set_refs` + leakage audit | G1: Feature Validity | Confirm features are valid and leak-free |
| `label_dataset_refs` + simulation lineage | G2: Label Validity | Confirm labels from authoritative simulation |
| `metrics.oos_*` (sharpe, expectancy, win rate) | G4: OOS Performance | Confirm edge exists out-of-sample |
| `cost_stress` (fee, slippage, combined) | G5: Cost Resilience | Confirm edge survives realistic costs |
| `regime_breakdown` (per-regime metrics) | G6: Regime Robustness | Confirm edge across market regimes |
| `no_trade_comparison` (active vs no-trade) | G9: No-Trade Baseline | Confirm alpha beats doing nothing |
| Overall `verdict` | V7 Decision Input | Synthesis for V7 evaluation |

### ValidationReport → V7 Promotion Gates

| AlphaForge Evidence | V7 Gate | Purpose |
|--------------------|---------|---------|
| `split_policy` (train/val/OOS config) | G0-G4 methodology audit | Confirm valid split design |
| `walk_forward_folds` (per-fold metrics) | G4: OOS Performance | Detailed fold-level evidence |
| `oos_summary` (aggregate OOS metrics) | G4: OOS Performance | Aggregate OOS assessment |
| `symbol_stability` (cross-symbol variance) | G7: Stability | Confirm edge across symbols |
| `regime_breakdown` (detailed by regime) | G6: Regime Robustness | Detailed regime analysis |
| `cost_stress` (sensitivity levels) | G5: Cost Resilience | Detailed cost sensitivity |
| `no_trade_comparison` | G9: No-Trade Baseline | Detailed no-trade analysis |
| `overfit_risk_flags` | V7 Risk Assessment | Overfit risk for V7 to evaluate |
| `verdict` (PASS/FAIL/INCONCLUSIVE) | V7 Decision Input | Validation conclusion |

### ModelArtifact → V7 Model Loading

| AlphaForge Evidence | V7 Use | Purpose |
|--------------------|--------|---------|
| `model_artifact_id` | Model identity | Which model to load |
| `artifact_uri` | Model location | Where to load from |
| `checksum` | Integrity verification | Confirm model hasn't changed |
| `model_family` | Compatibility check | Can V7 load this model type? |
| `feature_set_id` | Feature compatibility | Can V7 compute the required features? |
| `training_metrics` | Quality baseline | Expected model behavior |
| `hyperparameters` | Reproducibility | Configuration for shadow evaluation |
| `limitations` | Risk awareness | Known issues V7 must consider |

**Key rule:** V7 does NOT execute the model without explicit acceptance. ModelArtifact metadata enables V7 to evaluate whether loading the model is appropriate.

### CalibrationCandidate → V7 Calibration Gate

| AlphaForge Evidence | V7 Gate | Purpose |
|--------------------|---------|---------|
| `calibration_method` | G8: Calibration | How was calibration done? |
| `calibration_metrics.ece` | G8: Calibration | Is calibration acceptable? |
| `confidence_bins` | G8: Calibration | Bin-level reliability assessment |
| `status` (CALIBRATED/UNCALIBRATED/UNRELIABLE) | G8: Calibration | Go/no-go for probability use |

### V7HandoffPackage → V7 Review Queue

| Handoff Field | V7 Action |
|--------------|-----------|
| `handoff_package_id` | Identity for V7 tracking |
| `v7_gate_mapping` (G0-G10 evidence references) | Structured gate evaluation |
| `recommended_status` | Suggestion (not binding) |
| `blocked_scopes` | Scopes V7 should NOT extrapolate to |
| `limitations` | Known issues for V7 awareness |
| `lineage` | Full provenance for V7 audit |
| `rejection_rules_applied` | Which rules were checked before handoff |

---

## V7 Final Authority

**Critical rules:**

1. **V7 is ALWAYS the final decision authority.** AlphaForge recommends; V7 decides.
2. **V7 can REJECT any handoff package regardless of AlphaForge's recommendation.**
3. **V7 can request additional evidence from AlphaForge.** The handoff is a submission, not a conclusion.
4. **V7 can impose additional evaluation gates.** G0-G10 are the baseline; V7 may add more.
5. **V7 can promote to shadow without promoting to live.** Shadow trading is a V7 decision.
6. **V7 can accept for evaluation without accepting for live.** Each gate is independently evaluated.
7. **V7 owns the final policy decision.** AlphaForge evidence informs policy; it does not set it.

---

## What V7 Does NOT Accept From AlphaForge

- Trade commands (AlphaForge never issues these)
- Direct model execution (V7 loads models only after acceptance)
- Risk limit overrides (V7 owns risk policy)
- Funding assumptions without funding model (flag if DEFERRED)
- Claims of live readiness without empirical evidence

---

## Rejection Flow

If V7 rejects a handoff package:
1. V7 documents rejection reason referencing specific gate failures.
2. AlphaForge may address the issues and re-submit.
3. Rejection is a normal outcome, not a system failure.
4. The alpha may return to CONTINUE_RESEARCH for further work.

---

## Related Docs

- [../alphaforge/docs/handoff_to_v7.md](../alphaforge/docs/handoff_to_v7.md)
- [../alphaforge/docs/report_contracts.md](../alphaforge/docs/report_contracts.md)
- [../v7/docs/pipeline/evaluation.md](../v7/docs/pipeline/evaluation.md) — V7 G0-G10 gates

## Related Contracts

- [../schemas/alphaforge/v7_handoff_package.schema.json](../schemas/alphaforge/v7_handoff_package.schema.json)
- [../schemas/alphaforge/mode_research_report.schema.json](../schemas/alphaforge/mode_research_report.schema.json)
- [../schemas/alphaforge/validation_report.schema.json](../schemas/alphaforge/validation_report.schema.json)

## Forbidden Assumptions

- AlphaForge evidence is NOT a V7 decision.
- V7 gate mapping is a structure, not a pass guarantee.
- PROMOTION_CANDIDATE is a recommendation, not an authorization.

## Open Holds

- Actual V7 gate evaluation logic is defined in V7 pipeline docs, not here.
- Gate G10 (Paper/Shadow) requires paper trading infrastructure not yet built.
- Funding DEFERRED blocks perpetual/live gate evaluation.
