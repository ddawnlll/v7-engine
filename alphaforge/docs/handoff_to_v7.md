# AlphaForge → V7 Handoff Contract

**Purpose:** Define what AlphaForge delivers to V7 acceptance gates — the V7HandoffPackage format, gate mapping, and handoff rejection rules.

**Authority:** AlphaForge assembles handoff packages. V7 is the final acceptance authority. This document is LOCKED.

**P0.8E note:** Gate references corrected to match V7 canonical gate IDs from `v7/docs/pipeline/evaluation.md`. Previous AlphaForge-invented gate names replaced.

---

## V7HandoffPackage

**Schema:** [v7_handoff_package.schema.json](../../contracts/schemas/alphaforge/v7_handoff_package.schema.json)

The V7HandoffPackage is the single delivery artifact from AlphaForge to V7. It bundles all evidence V7 needs to evaluate an alpha candidate through its promotion gates.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| schema_version | string | Schema version |
| handoff_package_id | string | Unique package identifier |
| mode | enum | SCALP, AGGRESSIVE_SCALP, SWING |
| alpha_candidate_id | string | AlphaCandidate reference |
| mode_research_report_id | string | ModeResearchReport reference |
| validation_report_id | string | ValidationReport reference |
| model_artifact_id | string | ModelArtifact reference |
| calibration_candidate_id | string | CalibrationCandidate reference |
| v7_gate_mapping | object | Mapping of AlphaForge evidence to V7 canonical gates (G0_doc_ready…G10_live) |
| recommended_status | enum | REVIEW_REQUIRED, SHADOW_READY, PROMOTION_CANDIDATE |
| blocked_scopes | array | Scopes explicitly blocked |
| limitations | array | Known limitations |
| lineage | object | Full provenance chain |

---

## V7 Gate Mapping

AlphaForge evidence maps to V7 promotion gates. The handoff package must specify which gates each piece of evidence addresses. Gate IDs match `v7/docs/pipeline/evaluation.md` exactly:

| V7 Gate | AlphaForge Evidence | Purpose |
|---------|-------------------|---------|
| G0: DOC_READY | Authority docs, data quality flags, checksums, lineage | Confirm complete documentation and data integrity |
| G1: RESEARCH_BACKTEST | Initial research backtest metrics with cost-honest labels | Confirm positive expectancy R; no-trade quality meets threshold |
| G2: WALK_FORWARD_OOS | ValidationReport OOS summary, 6-fold walk-forward | Confirm median fold expectancy meets mode threshold |
| G3: COST_STRESS | ValidationReport cost stress (fee×multiplier, slippage, funding) | Confirm edge survives cost stress; SCALP ≥0.10R cost-adjusted |
| G4: REGIME_BREAKDOWN | ValidationReport regime breakdown (TREND_UP/DOWN/RANGE/TRANSITION) | Confirm no single regime hides catastrophic loss |
| G5: SYMBOL_STABILITY | ValidationReport symbol stability (per-symbol contribution) | Confirm no single symbol >40% of total edge |
| G6: CALIBRATION_RELIABILITY | CalibrationCandidate metrics, reliability error per bucket | Confirm probability/expected-R surfaces are trustworthy |
| G7: SHADOW | Shadow trading evidence (infrastructure: P0.9A+) | Live-market observation without order placement |
| G8: PAPER | Paper trading evidence (infrastructure: P0.9A+) | Paper forward simulation with full trade lifecycle |
| G9: TINY_LIVE | Tiny-live validation evidence (infrastructure: far future) | Small real-capital validation with strict kill switches |
| G10: LIVE | Combined evidence package, all prior gates passed | Production-eligible mode after independent promotion |

**Replaces incorrect previous mapping:** Old AlphaForge gate names (G0: Data Quality, G1: Feature Validity, G2: Label Validity, G3: Model Sanity, G4: OOS Performance, G5: Cost Resilience, G6: Regime Robustness, G7: Stability, G8: Calibration, G9: No-Trade Baseline, G10: Paper/Shadow) were NOT the correct V7 canonical gate names. Corrected in P0.8E.

---

## Recommended Status

AlphaForge may recommend a status, but V7 is the final authority:

| Status | Meaning | V7 Action |
|--------|---------|-----------|
| REVIEW_REQUIRED | Package needs V7 review before any action | V7 evaluates, decides |
| SHADOW_READY | Candidate may be eligible for shadow trading | V7 decides shadow parameters |
| PROMOTION_CANDIDATE | Candidate may be eligible for live promotion | V7 decides promotion |

---

## Handoff Rejection Rules

V7 may reject a handoff package for ANY of these reasons:

1. **Missing evidence:** Required reports or artifacts not included in package.
2. **Incomplete gate mapping:** V7 gate mapping insufficient for evaluation.
3. **Lineage break:** Provenance chain cannot be verified.
4. **Checksum mismatch:** Model artifact checksum doesn't match binary.
5. **Validation failure:** Validation report shows FAIL or INCONCLUSIVE.
6. **Cost vulnerability:** Edge destroyed under realistic cost assumptions.
7. **Overfit detected:** Multiple overfit risk flags fired.
8. **Single-symbol overfitting:** Edge only on one symbol without rationale.
9. **Calibration unusable:** Calibration status is UNRELIABLE.
10. **Funding unknown:** Alpha requires perpetual/live but funding is DEFERRED.
11. **Blocked scope violation:** Package claims scope AlphaForge flagged as blocked.
12. **Policy conflict:** Alpha conflicts with existing V7 policy/risk constraints.

---

## V7 Remains Final Authority

**Critical rule:** V7 is ALWAYS the final decision authority.

- AlphaForge RECOMMENDS. V7 DECIDES.
- A handoff package with recommended_status: PROMOTION_CANDIDATE may be REJECTED by V7.
- V7 may request additional evidence from AlphaForge.
- V7 may impose additional evaluation gates beyond what AlphaForge mapped.
- V7 may shadow-trade without promoting to live.
- V7 may accept for shadow but reject for live.

Under NO circumstances does AlphaForge override V7's acceptance decision.

---

## Handoff Package Lineage

Every handoff package must trace its full provenance:

```
Raw Market Data → Normalized Market Data → FeatureDataset → SimulationProfile
    → SimulationOutput → LabelDataset → Model Training → Validation
    → Calibration → ModeResearchReport → AlphaForgeResearchReport
    → V7HandoffPackage
```

Each link in the chain must be referenced by ID and checksum.

---

## Blocked Scopes

The handoff package must explicitly list scopes that are NOT covered:

- "This package does NOT cover symbols outside BTCUSDT and ETHUSDT."
- "This package does NOT cover funding costs (funding model DEFERRED)."
- "This package does NOT cover live execution latency."
- "This package does NOT cover exchange-specific fee structures."
- "This package does NOT cover cross-sectional multi-symbol data (P0.9B dependency)."

Blocked scopes protect V7 from over-extrapolation.

---

## Related Docs

- [ai_summary.md](ai_summary.md)
- [report_contracts.md](report_contracts.md)
- [validation_contract.md](validation_contract.md)
- [model_artifact_contract.md](model_artifact_contract.md)
- [decision_log.md](decision_log.md)

## Related Contracts

- [../../contracts/schemas/alphaforge/v7_handoff_package.schema.json](../../contracts/schemas/alphaforge/v7_handoff_package.schema.json)
- [../../contracts/mappings/alphaforge_to_v7.md](../../contracts/mappings/alphaforge_to_v7.md)
- [../../v7/docs/pipeline/evaluation.md](../../v7/docs/pipeline/evaluation.md) — V7 canonical G0-G10 gates (source of truth)

## Forbidden Assumptions

- AlphaForge does NOT tell V7 what to do.
- PROMOTION_CANDIDATE recommendation is a suggestion, not a command.
- V7 rejection is not a failure — it is the system working as designed.

## Open Holds

- V7 gate mapping is defined contractually; actual gate execution waits for P0.9A+.
- G7 (SHADOW), G8 (PAPER), G9 (TINY_LIVE), G10 (LIVE) require infrastructure not yet built.
- Funding DEFERRED blocks perpetual/live handoff packages.
- P0.8E corrected gate mapping to canonical V7 IDs.
