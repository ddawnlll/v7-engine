# AlphaForge — AI Summary

**Thin hub.** Read this first (1–2 minutes) to understand AlphaForge.

**P0.8E complete.** Gate mapping corrected to V7 canonical IDs. Timeframe stacks aligned to locked simulation profiles. Label schema completed (gross/net cost, NO_TRADE quality). Validation contract aligned to V7 gates (6-fold, canonical regimes). MHT/data-snooping controls added. Nested schema requirements strengthened. Fixture validation and schema strictness tests pass. P0.9A gated on P0.8E PASS.

**v0.25 Diagnostics Repair (2026-06-27):** Active trade metric system added — `compute_oos_metrics()` tracks LONG_NOW/SHORT_NOW/NO_TRADE counts, cost decomposition, net-R, exposure pct with NaN guards. `mode_research_report.schema.json` updated with 8 new active metric fields (3 required). MHT correction module (`mht.py`) provides Bonferroni step-down, Benjamini-Hochberg FDR, deflated Sharpe ratio, and data-snooping risk assessment. 6-fold walk-forward validation with anchored expanding windows in `cli/real_training.py`. SOLUSDT stop/target optimized. 1578 tests pass.

**Issue #143 — Multi-Timeframe Alpha Tuning (2026-07-01):** SCALP and AGGRESSIVE_SCALP walk-forward pipelines operational with mode-specific hyperparameters, annualization factors (SCALP=8760, AGGRESSIVE_SCALP=35040), and purge/embargo defaults. Cross-timeframe edge comparison module (`cross_timeframe.py`) compares edges across all three canonical timeframes — detects dominant timeframe, multi-TF confirmation, timeframe specialization, direction conflicts. `train_multi_timeframe.py` script runs all three modes. 1129 alphaforge tests pass (+46 new).

---

## Mission

AlphaForge is the **anomaly discovery and alpha research authority** within V7 Engine. It discovers alpha candidates, tests them against simulation-derived economic truth, validates them through walk-forward analysis, and packages evidence for V7 acceptance gates. AlphaForge does NOT make trade decisions — V7 retains final policy authority.

---

## Authority Boundaries

| Owns | Does NOT Own |
|------|-------------|
| Anomaly discovery | Final trade decision |
| Alpha thesis lifecycle | Live execution |
| Feature research | Portfolio/risk policy |
| Dataset/research manifest definition | Runtime lifecycle |
| Simulation label consumption | Exchange connectivity |
| Model training experiment definition | Simulation economic truth |
| Walk-forward validation reporting | V7 promotion gate authority |
| Mode-level research reports | — |
| V7 handoff packages | — |

**Upstream:** [lib](../../lib/) (primitives), [simulation](../../simulation/docs/) (economic truth)
**Downstream:** [V7](../../v7/docs/) (policy acceptance)

---

## Mode Priority Summary

| Mode | Business Priority | Research Priority | Threshold Status | Locked Primary Timeframe |
|------|------------------|-------------------|-----------------|-------------------------|
| SCALP | PRIMARY | PRIMARY | HOLD (empirical evidence required) | **1h** (context 4h, refine 15m) |
| AGGRESSIVE_SCALP | PRIMARY | PRIMARY | HOLD (empirical evidence required) | **15m** (context 1h, refine 5m) |
| SWING | SECONDARY_BASELINE | SECONDARY_BASELINE | LOCKED_INITIAL_BASELINE | **4h** (context 1d, refine 1h) |

Timeframes are LOCKED from `simulation/docs/profiles.md`. P0.8E corrected previous incorrect assumptions.

---

## Doc Map

| Doc | Purpose |
|-----|---------|
| [discovery_authority.md](discovery_authority.md) | What AlphaForge owns, consumes, produces, and is forbidden from doing |
| [alpha_thesis_lifecycle.md](alpha_thesis_lifecycle.md) | Alpha thesis states from PROPOSED to V7_CANDIDATE |
| [data_contract.md](data_contract.md) | Data layers: raw → normalized → feature → label → manifest. P0.8E: timeframes corrected |
| [feature_contract.md](feature_contract.md) | FeatureSetSpec, feature groups, leakage rules. P0.8E: timeframes corrected |
| [label_contract.md](label_contract.md) | SimulationOutput → AlphaForge label transformation |
| [report_contracts.md](report_contracts.md) | ModeResearchReport, AlphaForgeResearchReport format and verdicts |
| [validation_contract.md](validation_contract.md) | Walk-forward, OOS, cost stress, overfit detection, MHT control |
| [model_artifact_contract.md](model_artifact_contract.md) | ModelArtifact and CalibrationCandidate formats |
| [handoff_to_v7.md](handoff_to_v7.md) | V7HandoffPackage: what AlphaForge delivers to V7. P0.8E: gate mapping corrected |
| [storage_policy.md](storage_policy.md) | What stays in repo vs. external storage |
| [phase_plan.md](phase_plan.md) | Implementation phases P0.8B through P1.0 |
| [decision_log.md](decision_log.md) | Locked AlphaForge decisions |

**Legacy docs (historical reference only):**
- `ai_summary__v7_alphaforge_xgb.md` (625KB) — pre-authority-lock combined doc. SUPERSEDED by the 12 canonical docs above.
- `phase_plans_combined.md` (578KB) — pre-P0.8B combined plans. SUPERSEDED by `phase_plan.md`.

---

## V7 Gate Mapping (P0.8E Corrected)

AlphaForge evidence maps to V7 canonical gates as defined in `v7/docs/pipeline/evaluation.md`:

| V7 Gate | Name | AlphaForge Evidence Source |
|---------|------|---------------------------|
| G0 | DOC_READY | Data scope, flags, lineage, all authority docs |
| G1 | RESEARCH_BACKTEST | Initial backtest metrics with cost-honest labels |
| G2 | WALK_FORWARD_OOS | ValidationReport OOS summary, 6-fold walk-forward |
| G3 | COST_STRESS | ValidationReport cost stress: fee × multiplier, slippage |
| G4 | REGIME_BREAKDOWN | ValidationReport regime breakdown: TREND_UP/DOWN/RANGE/TRANSITION |
| G5 | SYMBOL_STABILITY | ValidationReport symbol stability: per-symbol contribution |
| G6 | CALIBRATION_RELIABILITY | CalibrationCandidate metrics: ECE, confidence bins |
| G7 | SHADOW | Not yet built (P0.9A+ dependency) |
| G8 | PAPER | Not yet built (P0.9A+ dependency) |
| G9 | TINY_LIVE | Not yet built (far future) |
| G10 | LIVE | Not yet built (far future) |

**⚠️ Previous incorrect gate names (G0: Data Quality, G1: Feature Validity, etc.) were NOT the V7 canonical gate IDs. Corrected in P0.8E.**

---

## Contract Map

### Schemas (`../../contracts/schemas/alphaforge/`)
- [alpha_thesis.schema.json](../../contracts/schemas/alphaforge/alpha_thesis.schema.json)
- [alpha_candidate.schema.json](../../contracts/schemas/alphaforge/alpha_candidate.schema.json)
- [feature_set_spec.schema.json](../../contracts/schemas/alphaforge/feature_set_spec.schema.json)
- [label_dataset_spec.schema.json](../../contracts/schemas/alphaforge/label_dataset_spec.schema.json)
- [mode_research_report.schema.json](../../contracts/schemas/alphaforge/mode_research_report.schema.json)
- [alphaforge_research_report.schema.json](../../contracts/schemas/alphaforge/alphaforge_research_report.schema.json)
- [validation_report.schema.json](../../contracts/schemas/alphaforge/validation_report.schema.json)
- [model_artifact.schema.json](../../contracts/schemas/alphaforge/model_artifact.schema.json)
- [calibration_candidate.schema.json](../../contracts/schemas/alphaforge/calibration_candidate.schema.json)
- [v7_handoff_package.schema.json](../../contracts/schemas/alphaforge/v7_handoff_package.schema.json) — P0.8E: gate mapping corrected

### Fixtures (`../../contracts/fixtures/alphaforge/`)
- All 5 fixtures updated P0.8E: timeframes corrected, nested fields strengthened, MHT control added
- [Fixture validation tests](../../integration/tests/test_alphaforge_fixture_validation.py)
- [Contract semantics tests](../../integration/tests/test_alphaforge_contract_semantics.py)

### Mappings (`../../contracts/mappings/`)
- [simulation_to_alphaforge.md](../../contracts/mappings/simulation_to_alphaforge.md)
- [alphaforge_to_v7.md](../../contracts/mappings/alphaforge_to_v7.md) — P0.8E: gate mapping corrected

---

## Data Flow (Text)

```
Raw Market Data (external)
    │
    ▼
Normalized Market Data (OHLCV, events)
    │
    ├──► FeatureDataset (mode/timeframe-aware feature matrix)
    │
    ▼
Simulation Engine (economic truth) — locked profiles: SCALP 1h, AGGRESSIVE 15m, SWING 4h
    │
    ▼
SimulationOutput ──► LabelDataset (cost-aware, NO_TRADE-aware labels)
    │
    ▼
AlphaForge Training Run (feature + label → model)
    │
    ▼
Validation (walk-forward 6-fold, OOS, cost stress, no-trade, MHT control)
    │
    ▼
ModeResearchReport (per-mode verdict)
    │
    ▼
AlphaForgeResearchReport (aggregate: all 3 modes required)
    │
    ▼
V7HandoffPackage (canonical G0-G10 gate mapping) ──► V7 Acceptance Gates
```

---

## Safe Next Implementation Order

1. **P0.8B:** Authority lock, docs, contracts — DONE
2. **P0.8C:** Re-audit after authority lock — DONE
3. **P0.8D:** Profitability/efficiency squeeze audit — DONE
4. **P0.8E:** Contract/docs patch (this task) — fix gate mapping, timeframes, strengthen schemas, add fixture tests — IN PROGRESS (BLOCKS P0.9A)
5. **P0.9A:** AlphaForge implementation scaffold — BLOCKED (requires P0.8E PASS)
6. **P0.9B:** Data/label/feature pipeline
7. **P0.9C:** All-mode research reports
8. **P1.0:** V7 handoff candidate

---

## Do Not Do (For Agents)

- Do NOT implement AlphaForge source code until P0.9A
- Do NOT add training scripts, dataset builders, or model code
- Do NOT modify lib/, simulation/, v7/, runtime/, or interface/ source files
- Do NOT change SimulationOutput semantics
- Do NOT use wrong V7 gate names — canonical names are in `v7/docs/pipeline/evaluation.md`
- Do NOT use wrong timeframes — locked profiles: SCALP 1h, AGGRESSIVE_SCALP 15m, SWING 4h
- Do NOT lock SCALP or AGGRESSIVE_SCALP thresholds without empirical evidence
- Do NOT mark SCALP/AGGRESSIVE_SCALP as promotion-ready
- Do NOT remove funding DEFERRED hold
- Do NOT store large datasets or model binaries in repo
- Do NOT create fake empirical results
- Do NOT claim an alpha works without data
- Do NOT issue trade commands from AlphaForge

---

## Linked Domains

- [lib/](../../lib/) — shared primitives
- [simulation/](../../simulation/docs/) — economic truth authority
- [v7/](../../v7/docs/) — policy acceptance authority (G0-G10 canonical gates)
- [contracts/](../../contracts/) — cross-domain schemas
- [runtime/](../../runtime/docs/) — execution lifecycle
