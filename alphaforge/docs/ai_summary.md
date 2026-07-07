# AlphaForge â€” AI Summary

**Thin hub.** Read this first (1â€“2 minutes) to understand AlphaForge.

**P0.8E complete.** Gate mapping corrected to V7 canonical IDs. Timeframe stacks aligned to locked simulation profiles. Label schema completed (gross/net cost, NO_TRADE quality). Validation contract aligned to V7 gates (6-fold, canonical regimes). MHT/data-snooping controls added. Nested schema requirements strengthened. Fixture validation and schema strictness tests pass. P0.9A gated on P0.8E PASS.

**v0.25 Diagnostics Repair (2026-06-27):** Active trade metric system added â€” `compute_oos_metrics()` tracks LONG_NOW/SHORT_NOW/NO_TRADE counts, cost decomposition, net-R, exposure pct with NaN guards. `mode_research_report.schema.json` updated with 8 new active metric fields (3 required). MHT correction module (`mht.py`) provides Bonferroni step-down, Benjamini-Hochberg FDR, deflated Sharpe ratio, and data-snooping risk assessment. 6-fold walk-forward validation with anchored expanding windows in `cli/real_training.py`. SOLUSDT stop/target optimized. 1578 tests pass.

- **P0.x â€” Research Artifact Registry (2026-07-01):** `ResearchRunIndex` class creates/maintains `alphaforge_report/research_run_index.json` â€” a single index tracking every research run with canonical/superseded distinction, duplicate detection, and artifact paths. Integrated into CLI report generation. 29 tests, 1640 total pass.
- **Issue #146 â€” XGBoost Search Space Design (2026-07-01):** New `alphaforge/src/alphaforge/tuning/` package with mode-specific XGBoost hyperparameter search spaces (SWING, SCALP, AGGRESSIVE_SCALP). Log-uniform regularization sampling. Optuna integration via `suggest_params()` and `build_objective()`. 78 tests.
- **Make/Menu + Pipeline CLI Repair (2026-07-03):** Scaffold and empirical ModeResearchReport builders now include required primary AlphaForge metrics `oos_ic` and `oos_rank_ic`; CandidateOutcomeBuilder consumes simulation-output-shaped objects without importing `simulation`, restoring AlphaForge boundary compliance. `make backfill` delegates to the maintained Binance Vision downloader and `make report MODE=...` validates. Relevant AlphaForge/integration boundary tests pass.
- **SCALP Training Harness Repair (2026-07-05):** `alphaforge.train` now builds timestamp-aligned per-symbol training frames instead of truncating concatenated symbol blocks, computes active-trade economics from predicted decisions, and exposes a deterministic positive-control path that passes when the harness is healthy. Profitability evidence remains HOLD until real alpha clears the new harness.
- **SCALP Alpha Discovery — BB Position Mean-Reversion v1 (2026-07-05):** First validated alpha candidate. 6-fold walk-forward validation on synthetic 5-symbol data (BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, ADAUSDT). Confidence threshold optimized from 0.55 → **0.715** via composite metric (`total_net_R / max_drawdown`). Feature set pruned 54 → **32** via DoubleEnsemble shuffle ablation. **bb_position** identified as dominant feature (99.49% shuffle impact). **⚠️ 2026-07-06: Future leakage discovered.** `_rolling_mean` in `pipeline.py` used `np.convolve(mode='same')` (centered window), leaking up to 10h of future close into bb_position. The "no look-ahead" claim was invalid — the causality audit only caught this after _rolling_mean was fixed to use `mode='full'[:n]`. This alpha must be re-validated on corrected features. Alpha thesis: "BB Position Dominated Mean-Reversion/Location Edge." Test/OOS (held-out fold 6): total_net_R=10.96 > 0, block-bootstrap 95% CI=[0.0225, 0.0256] fully positive, max_DD=0.049, composite=223.0. Handoff package saved: `discovered_alphas/SCALP_bb_position_mean_reversion_v1.json`. See [discovered_alphas/SCALP_bb_position_mean_reversion_v1.json](discovered_alphas/SCALP_bb_position_mean_reversion_v1.json) for full feature formulas, ablation ranking, and model comparison data. Position sizing as standalone lever confirmed FAIL (all 10 schemes reduced total net R). SCALP threshold status remains HOLD — synthetic data only.
 
---

## Mission

AlphaForge is the **anomaly discovery and alpha research authority** within V7 Engine. It discovers alpha candidates, tests them against simulation-derived economic truth, validates them through walk-forward analysis, and packages evidence for V7 acceptance gates. AlphaForge does NOT make trade decisions â€” V7 retains final policy authority.

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
| Mode-level research reports | â€” |
| V7 handoff packages | â€” |

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
| [data_contract.md](data_contract.md) | Data layers: raw â†’ normalized â†’ feature â†’ label â†’ manifest. P0.8E: timeframes corrected |
| [feature_contract.md](feature_contract.md) | FeatureSetSpec, feature groups, leakage rules. P0.8E: timeframes corrected |
| [label_contract.md](label_contract.md) | SimulationOutput â†’ AlphaForge label transformation |
| [report_contracts.md](report_contracts.md) | ModeResearchReport, AlphaForgeResearchReport format and verdicts |
| [validation_contract.md](validation_contract.md) | Walk-forward, OOS, cost stress, overfit detection, MHT control |
| [model_artifact_contract.md](model_artifact_contract.md) | ModelArtifact and CalibrationCandidate formats |
| [handoff_to_v7.md](handoff_to_v7.md) | V7HandoffPackage: what AlphaForge delivers to V7. P0.8E: gate mapping corrected |
| [storage_policy.md](storage_policy.md) | What stays in repo vs. external storage |
| [phase_plan.md](phase_plan.md) | Implementation phases P0.8B through P1.0 |
| [decision_log.md](decision_log.md) | Locked AlphaForge decisions |
| [discovered_alphas/](discovered_alphas/) | Validated alpha candidates with full feature definitions, formulas, ablation metrics, and V7 handoff packages |
| `alphaforge/src/alphaforge/tuning/search_space.py` | XGBoost search space definitions per mode + Optuna integration (Issue #146) |

**Legacy docs (historical reference only):**
- `ai_summary__v7_alphaforge_xgb.md` (625KB) â€” pre-authority-lock combined doc. SUPERSEDED by the 12 canonical docs above.
- `phase_plans_combined.md` (578KB) â€” pre-P0.8B combined plans. SUPERSEDED by `phase_plan.md`.

---

## V7 Gate Mapping (P0.8E Corrected)

AlphaForge evidence maps to V7 canonical gates as defined in `v7/docs/pipeline/evaluation.md`:

| V7 Gate | Name | AlphaForge Evidence Source | Current Status |
|---------|------|---------------------------|----------------|
| G0 | DOC_READY | Data scope, flags, lineage, all authority docs | PASS |
| G1 | RESEARCH_BACKTEST | Initial backtest metrics with cost-honest labels | PASS (SCALP v1) |
| G2 | WALK_FORWARD_OOS | ValidationReport OOS summary, 6-fold walk-forward | PASS (SCALP v1) |
| G3 | COST_STRESS | ValidationReport cost stress: fee × multiplier, slippage | PASS — cost deducted in labels |
| G4 | REGIME_BREAKDOWN | ValidationReport regime breakdown: TREND_UP/DOWN/RANGE/TRANSITION | NOT_EVALUATED (synthetic data) |
| G5 | SYMBOL_STABILITY | ValidationReport symbol stability: per-symbol contribution | NOT_EVALUATED (synthetic data) |
| G6 | CALIBRATION_RELIABILITY | CalibrationCandidate metrics: ECE, confidence bins | PENDING (threshold selected, calibration artifact not yet produced) |
| G7 | SHADOW | Not yet built (P0.9A+ dependency) | NOT_EVALUATED |
| G8 | PAPER | Not yet built (P0.9A+ dependency) | NOT_EVALUATED |
| G9 | TINY_LIVE | Not yet built (far future) | NOT_EVALUATED |
| G10 | LIVE | Not yet built (far future) | NOT_EVALUATED |

**âš ï¸ Previous incorrect gate names (G0: Data Quality, G1: Feature Validity, etc.) were NOT the V7 canonical gate IDs. Corrected in P0.8E.**

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
- [v7_handoff_package.schema.json](../../contracts/schemas/alphaforge/v7_handoff_package.schema.json) â€” P0.8E: gate mapping corrected

### Fixtures (`../../contracts/fixtures/alphaforge/`)
- All 5 fixtures updated P0.8E: timeframes corrected, nested fields strengthened, MHT control added
- [Fixture validation tests](../../integration/tests/test_alphaforge_fixture_validation.py)
- [Contract semantics tests](../../integration/tests/test_alphaforge_contract_semantics.py)

### Mappings (`../../contracts/mappings/`)
- [simulation_to_alphaforge.md](../../contracts/mappings/simulation_to_alphaforge.md)
- [alphaforge_to_v7.md](../../contracts/mappings/alphaforge_to_v7.md) â€” P0.8E: gate mapping corrected

---

## Data Flow (Text)

```
Raw Market Data (external)
    â”‚
    â–¼
Normalized Market Data (OHLCV, events)
    â”‚
    â”œâ”€â”€â–º FeatureDataset (mode/timeframe-aware feature matrix)
    â”‚
    â–¼
Simulation Engine (economic truth) â€” locked profiles: SCALP 1h, AGGRESSIVE 15m, SWING 4h
    â”‚
    â–¼
SimulationOutput â”€â”€â–º LabelDataset (cost-aware, NO_TRADE-aware labels)
    â”‚
    â–¼
AlphaForge Training Run (feature + label â†’ model)
    â”‚
    â–¼
Validation (walk-forward 6-fold, OOS, cost stress, no-trade, MHT control)
    â”‚
    â–¼
ModeResearchReport (per-mode verdict)
    â”‚
    â–¼
AlphaForgeResearchReport (aggregate: all 3 modes required)
    â”‚
    â–¼
V7HandoffPackage (canonical G0-G10 gate mapping) â”€â”€â–º V7 Acceptance Gates
```

---

## Safe Next Implementation Order

1. **P0.8B:** Authority lock, docs, contracts â€” DONE
2. **P0.8C:** Re-audit after authority lock â€” DONE
3. **P0.8D:** Profitability/efficiency squeeze audit â€” DONE
4. **P0.8E:** Contract/docs patch â€” fix gate mapping, timeframes, strengthen schemas, add fixture tests â€” DONE
5. **P0.9A-FREEZE:** Freeze + Metric Ownership Redesign â€” IN PROGRESS
6. **P0.9A:** AlphaForge implementation scaffold â€” REDESIGN_IN_PROGRESS (blocked by P0.9A-FREEZE)
7. **XSMOM:** Cross-Sectional Momentum Baseline â€” DONE
8. **P0.9B:** Data/label/feature pipeline
9. **P0.9C:** All-mode research reports
10. **P1.0:** V7 handoff candidate

---

## Do First (For Agents)

- **SCALP bb_position alpha:** First validated alpha candidate at `discovered_alphas/SCALP_bb_position_mean_reversion_v1.json`. Real market data validation is next priority — regime/symbol stability cannot be evaluated on synthetic data.
- **XSMOM baseline:** Cross-sectional momentum ranking and scoring for all 16 symbols. See [phase_plan.md](phase_plan.md).
- **Metric Philosophy compliance:** When implementing metric computation, verify the owning layer from discovery_authority.md. Do not recompute upstream-layer metrics downstream.
- **P0.9A metric ownership refactor:** Redesign scaffold to respect layer metric boundaries.

---

## Do Not Do (For Agents)

- Do NOT implement AlphaForge source code until P0.9A (exceptions: tuning/search_space.py â€” Issue #146)
- Do NOT add training scripts, dataset builders, or model code (exceptions: training/xgb_trainer.py, tuning/search_space.py)
- Do NOT modify lib/, simulation/, v7/, runtime/, or interface/ source files
- Do NOT change SimulationOutput semantics
- Do NOT use wrong V7 gate names â€” canonical names are in `v7/docs/pipeline/evaluation.md`
- Do NOT use wrong timeframes â€” locked profiles: SCALP 1h, AGGRESSIVE_SCALP 15m, SWING 4h
- Do NOT lock SCALP or AGGRESSIVE_SCALP thresholds without empirical evidence
- Do NOT mark SCALP/AGGRESSIVE_SCALP as promotion-ready
- Do NOT remove funding DEFERRED hold
- Do NOT store large datasets or model binaries in repo
- Do NOT create fake empirical results
- Do NOT claim an alpha works without data
- Do NOT issue trade commands from AlphaForge

---

## Version History

- **2026-07-07 — Alpha Truth Upgrade V1-V6:** Per-symbol panel loader (B4), mode-aware labels (B1), residual momentum (B3), unified eval representation (V4), debias quarantine (V5), simulation scoreboard (V6). REJECT on 4-sym panel (E[R]=0.0515R, PF=1.11). See `reports/accp/alpha_truth_upgrade.yaml`.
- **2026-07-07:** W1-W6 pipeline optimization (2000× rank stage speedup). See `reports/accp/training_pipeline_optimization_impl.yaml`.

## Linked Domains

- [lib/](../../lib/) â€” shared primitives
- [simulation/](../../simulation/docs/) â€” economic truth authority
- [v7/](../../v7/docs/) â€” policy acceptance authority (G0-G10 canonical gates)
- [contracts/](../../contracts/) â€” cross-domain schemas
- [runtime/](../../runtime/docs/) â€” execution lifecycle



