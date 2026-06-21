# AlphaForge → V7 Mapping

**Purpose:** Document how AlphaForge research outputs map to V7 evaluation and promotion gates. This is the authoritative handoff bridge between alpha discovery and policy acceptance.

**Authority:** AlphaForge produces evidence. V7 is the final acceptance authority. This mapping is LOCKED.

**P0.8E note:** Gate mapping corrected to match V7 canonical gate IDs from `v7/docs/pipeline/evaluation.md`. Previous AlphaForge-invented gate names (G0: Data Quality, G1: Feature Validity, etc.) have been replaced with the authoritative V7 gate sequence: G0_DOC_READY through G10_LIVE.

---

## V7 Canonical Gate Reference

Source of truth: `v7/docs/pipeline/evaluation.md`. V7 defines the following promotion gates:

| Gate | V7 Name | Meaning |
|------|---------|---------|
| G0 | DOC_READY | Mode has complete docs, contracts, labels, model outputs, and risk rules |
| G1 | RESEARCH_BACKTEST | Initial research backtest with cost-honest labels and no-trade quality |
| G2 | WALK_FORWARD_OOS | Walk-forward out-of-sample evidence across multiple folds |
| G3 | COST_STRESS | Fee, slippage, spread, and funding stress where applicable |
| G4 | REGIME_BREAKDOWN | Performance evaluated per TREND_UP, TREND_DOWN, RANGE, TRANSITION |
| G5 | SYMBOL_STABILITY | No single symbol or cluster explains majority of edge |
| G6 | CALIBRATION_RELIABILITY | Probability and expected-R surfaces calibrated enough for policy gates |
| G7 | SHADOW | Live-market observation without order placement |
| G8 | PAPER | Paper trading with runtime lifecycle and outcome reconciliation |
| G9 | TINY_LIVE | Small real-capital live validation with strict kill switches |
| G10 | LIVE | Production-eligible mode after independent promotion |

---

## AlphaForge Output → V7 Gates

### ModeResearchReport → V7 Evaluation Gates

| AlphaForge Evidence | V7 Gate | Purpose |
|--------------------|---------|---------|
| `data_scope` (symbols, date range, data quality, timeframe stack) | G0: DOC_READY | Confirm data integrity, complete docs, and scope |
| `metrics` (oos_sharpe, oos_expectancy_r, oos_win_rate) | G1: RESEARCH_BACKTEST | Initial research backtest evidence |
| `validation_summary` (fold_count, verdict, overfit_risk) | G2: WALK_FORWARD_OOS | Walk-forward OOS evidence reference |
| `cost_stress` (fee, slippage, combined stress levels) | G3: COST_STRESS | Confirm edge survives realistic costs |
| `regime_breakdown` (per-regime metrics across TREND_UP/DOWN/RANGE/TRANSITION) | G4: REGIME_BREAKDOWN | Confirm edge across market regimes |
| `metrics` symbol/regime slicing consistency | G5: SYMBOL_STABILITY | Confirm no single symbol/cluster dominates |
| Overall `verdict` | V7 Decision Input | Synthesis for V7 evaluation |
| `no_trade_comparison` (active vs no-trade) | All gates (cross-cutting quality) | Confirm alpha beats doing nothing |

### ValidationReport → V7 Promotion Gates

| AlphaForge Evidence | V7 Gate | Purpose |
|--------------------|---------|---------|
| `split_policy` (train/val/OOS config, purge, embargo) | G0-G2 methodology audit | Confirm valid split design |
| `walk_forward_folds` (per-fold metrics, 6 folds min) | G2: WALK_FORWARD_OOS | Detailed fold-level evidence |
| `oos_summary` (aggregate OOS metrics) | G2: WALK_FORWARD_OOS | Aggregate OOS assessment |
| `cost_stress` (fee, slippage, funding sensitivity levels) | G3: COST_STRESS | Detailed cost sensitivity |
| `regime_breakdown` (TREND_UP/DOWN/RANGE/TRANSITION) | G4: REGIME_BREAKDOWN | Detailed regime analysis |
| `symbol_stability` (per-symbol contribution, 40%/60% limits) | G5: SYMBOL_STABILITY | Confirm edge across symbols |
| `no_trade_comparison` | All gates (cross-cutting) | Detailed no-trade analysis |
| `overfit_risk_flags` | V7 Risk Assessment | Overfit risk for V7 to evaluate |
| `multiple_hypothesis_control` | V7 Risk Assessment | Data-snooping / MHT control evidence |
| `verdict` (PASS/PASS_WITH_LIMITATIONS/FAIL_*/INCONCLUSIVE) | V7 Decision Input | Validation conclusion |

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
| `calibration_method` | G6: CALIBRATION_RELIABILITY | How was calibration done? |
| `calibration_metrics.ece` | G6: CALIBRATION_RELIABILITY | Is calibration acceptable? |
| `confidence_bins` | G6: CALIBRATION_RELIABILITY | Bin-level reliability assessment |
| `status` (CALIBRATED/UNCALIBRATED/UNRELIABLE) | G6: CALIBRATION_RELIABILITY | Go/no-go for probability use |

### V7HandoffPackage → V7 Review Queue

| Handoff Field | V7 Action |
|--------------|-----------|
| `handoff_package_id` | Identity for V7 tracking |
| `v7_gate_mapping` (G0_doc_ready through G10_live with evidence_ref and status per gate) | Structured gate evaluation |
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
- [../v7/docs/pipeline/evaluation.md](../v7/docs/pipeline/evaluation.md) — V7 canonical G0-G10 gates (source of truth)

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
- Gates G7 (SHADOW), G8 (PAPER), G9 (TINY_LIVE), G10 (LIVE) require infrastructure not yet built.
- Funding DEFERRED blocks perpetual/live gate evaluation.
- P0.8E: gate IDs now match V7 evaluation.md canonical names; mapping verified.
