# AlphaForge → V7 Handoff Contract

**Purpose:** Define what AlphaForge delivers to V7 acceptance gates — the V7HandoffPackage format, gate mapping, and handoff rejection rules.

**Authority:** AlphaForge assembles handoff packages. V7 is the final acceptance authority. This document is LOCKED.

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
| v7_gate_mapping | object | Mapping of AlphaForge evidence to V7 gates |
| recommended_status | enum | REVIEW_REQUIRED, SHADOW_READY, PROMOTION_CANDIDATE |
| blocked_scopes | array | Scopes explicitly blocked |
| limitations | array | Known limitations |
| lineage | object | Full provenance chain |

---

## V7 Gate Mapping

AlphaForge evidence maps to V7 promotion gates (G0–G10). The handoff package must specify which gates each piece of evidence addresses.

| V7 Gate | AlphaForge Evidence | Purpose |
|---------|-------------------|---------|
| G0: Data Quality | Data quality flags, checksums, lineage | Confirm data integrity |
| G1: Feature Validity | FeatureSetSpec, leakage audit | Confirm features are valid |
| G2: Label Validity | LabelDatasetSpec, simulation lineage | Confirm labels derived from authoritative simulation |
| G3: Model Sanity | ModelArtifact, training metrics | Confirm model trains without obvious issues |
| G4: OOS Performance | ValidationReport OOS summary | Confirm edge exists out-of-sample |
| G5: Cost Resilience | ValidationReport cost stress | Confirm edge survives realistic costs |
| G6: Regime Robustness | ValidationReport regime breakdown | Confirm edge works across regimes |
| G7: Stability | ValidationReport symbol stability, fold stability | Confirm edge is stable |
| G8: Calibration | CalibrationCandidate, calibration metrics | Confirm model outputs are usable |
| G9: No-Trade Baseline | ValidationReport no_trade_comparison | Confirm alpha beats doing nothing |
| G10: Paper/Shadow | Combined evidence package | Final promotion decision |

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
- [../../v7/docs/pipeline/evaluation.md](../../v7/docs/pipeline/evaluation.md) — V7 G0-G10 gates

## Forbidden Assumptions

- AlphaForge does NOT tell V7 what to do.
- PROMOTION_CANDIDATE recommendation is a suggestion, not a command.
- V7 rejection is not a failure — it is the system working as designed.

## Open Holds

- V7 gate mapping is defined contractually; actual gate execution waits for P0.9A+.
- Funding DEFERRED blocks perpetual/live handoff packages.
