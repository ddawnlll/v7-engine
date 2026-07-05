# AlphaForge Discovery Authority

**Purpose:** Define what AlphaForge owns, consumes, produces, and is forbidden from doing.

**Authority:** This document is the canonical authority boundary reference for AlphaForge. It is LOCKED.

---

## Mission

AlphaForge is the **anomaly discovery and alpha research authority** within V7 Engine. It discovers, tests, validates, and reports alpha candidates. It produces evidence packages (reports, model metadata, calibration data) that V7 accepts or rejects through its promotion gates. AlphaForge does NOT issue trade decisions.

---

## Authority Table

### Owns

| Domain | Description |
|--------|-------------|
| Anomaly discovery | Identifying patterns in market data that may have predictive value |
| Alpha thesis lifecycle | Full lifecycle from PROPOSED through V7_CANDIDATE or REJECTED |
| Feature research | Designing, testing, and specifying feature sets per mode |
| Dataset/research manifest definition | Defining what data was used, how it was processed, and its provenance |
| Simulation label consumption | Transforming SimulationOutput into training labels |
| Model training experiment definition | Specifying training runs, hyperparameters, and configurations |
| Walk-forward validation reporting | Validating models through walk-forward analysis and producing validation reports |
| Mode-level research reports | Per-mode reports (ModeResearchReport) with verdicts |
| Aggregate research reports | Cross-mode synthesis (AlphaForgeResearchReport) |
| V7 handoff packages | Assembling V7HandoffPackage for V7 acceptance gates |

### Consumes

| From | What | Purpose |
|------|------|---------|
| lib | Shared primitives (data structures, utilities) | Foundation for feature/label/model code |
| simulation | SimulationOutput | Economic truth for label generation |
| simulation | SimulationProfile | Mode-specific configuration |
| contracts | Schema definitions | Contract compliance |

### Produces

| Output | Consumer | Format |
|--------|----------|--------|
| AlphaThesis | AlphaForge (internal) | [alpha_thesis.schema.json](../../contracts/schemas/alphaforge/alpha_thesis.schema.json) |
| FeatureSetSpec | AlphaForge (internal) | [feature_set_spec.schema.json](../../contracts/schemas/alphaforge/feature_set_spec.schema.json) |
| LabelDatasetSpec | AlphaForge (internal) | [label_dataset_spec.schema.json](../../contracts/schemas/alphaforge/label_dataset_spec.schema.json) |
| AlphaCandidate | AlphaForge (internal) | [alpha_candidate.schema.json](../../contracts/schemas/alphaforge/alpha_candidate.schema.json) |
| ModeResearchReport | AlphaForge, V7 | [mode_research_report.schema.json](../../contracts/schemas/alphaforge/mode_research_report.schema.json) |
| AlphaForgeResearchReport | V7 | [alphaforge_research_report.schema.json](../../contracts/schemas/alphaforge/alphaforge_research_report.schema.json) |
| ValidationReport | AlphaForge, V7 | [validation_report.schema.json](../../contracts/schemas/alphaforge/validation_report.schema.json) |
| ModelArtifact | AlphaForge, V7 | [model_artifact.schema.json](../../contracts/schemas/alphaforge/model_artifact.schema.json) |
| CalibrationCandidate | AlphaForge, V7 | [calibration_candidate.schema.json](../../contracts/schemas/alphaforge/calibration_candidate.schema.json) |
| V7HandoffPackage | V7 | [v7_handoff_package.schema.json](../../contracts/schemas/alphaforge/v7_handoff_package.schema.json) |
| ResearchRunManifest | AlphaForge (internal) | Defined in [data_contract.md](data_contract.md) |

### Forbidden

| Action | Reason |
|--------|--------|
| Issue trade commands | V7 owns final trade decisions |
| Execute live orders | Runtime owns execution lifecycle |
| Set portfolio risk limits | V7 owns policy/risk authority |
| Modify SimulationOutput | Simulation owns economic truth |
| Bypass cost models | Simulation costs are authoritative |
| Store large datasets in repo | Storage policy: manifests only in repo |
| Store model binaries in repo | Storage policy: URIs only in repo |
| Claim profitability without evidence | All claims require validation |
| Lock SCALP/AGGRESSIVE_SCALP thresholds | Requires empirical evidence |
| Remove funding DEFERRED hold | Blocks perpetual/live scope |

---

## Integration Boundaries

### With lib
- AlphaForge uses lib primitives for data structures and utilities.
- AlphaForge does NOT add domain-specific logic to lib/.
- If AlphaForge needs a new primitive, it requests it via lib's contract process.

### With simulation
- AlphaForge consumes SimulationOutput as authoritative economic truth.
- AlphaForge does NOT modify SimulationOutput semantics.
- AlphaForge maps SimulationOutput fields to labels via [label_contract.md](label_contract.md).
- The mapping is documented in [../../contracts/mappings/simulation_to_alphaforge.md](../../contracts/mappings/simulation_to_alphaforge.md).

### With V7
- AlphaForge delivers V7HandoffPackage to V7 acceptance gates.
- V7 retains final authority over acceptance/rejection.
- The handoff contract is documented in [handoff_to_v7.md](handoff_to_v7.md).
- The mapping is documented in [../../contracts/mappings/alphaforge_to_v7.md](../../contracts/mappings/alphaforge_to_v7.md).

### With runtime
- AlphaForge has NO direct integration with runtime.
- Runtime operates on V7 decisions, not AlphaForge research outputs.

### With interface
- AlphaForge has NO direct integration with interface.
- Interface observes runtime API, not AlphaForge state.

---

## Mode Authority

### SCALP (PRIMARY)
- Primary business and research mode.
- Thresholds are HOLD — require empirical research.
- Report type: `primary_research_report`.
- Must demonstrate edge over NO_TRADE after costs.

### AGGRESSIVE_SCALP (PRIMARY)
- Primary business and research mode.
- Thresholds are HOLD — require empirical research.
- Report type: `primary_research_report`.
- Higher fee/slippage sensitivity. Must include liquidity/spread caveats.

### SWING (SECONDARY_BASELINE)
- Secondary baseline/control mode.
- Thresholds are LOCKED_INITIAL_BASELINE.
- Report type: `secondary_baseline_report`.
- Does NOT override primary SCALP/AGGRESSIVE_SCALP research priority.
- Threshold recalibration required after first walk-forward.

---

## Key Principles

1. **AlphaForge discovers alpha; V7 decides; Simulation measures truth.** (PRINCIPLE-001)
2. **Report before implementation.** Contracts lock before code. (PRINCIPLE-002)
3. **Every alpha must be rejectable.** Explicit rejection criteria required. (PRINCIPLE-008)
4. **NO_TRADE is a first-class comparator.** (PRINCIPLE-009)
5. **Cost-aware research.** No candidate without cost/slippage/funding analysis. (PRINCIPLE-010)
6. **Repo stores schemas/manifests/fixtures, not big datasets.** (PRINCIPLE-007)

---

## Metric Philosophy

Metrics live at the layer closest to their source data. No downstream layer recomputes what an upstream layer already computed.

### Layer Metric Ownership

| Layer | Owns | Key Metrics | Passes To |
|-------|------|-------------|-----------|
| Simulation | Economic truth | gross_return_r, total_cost_r, funding_cost_r, slippage_cost_r | AlphaForge label layer |
| AlphaForge (Label) | Label-time economics | gross_return_r, net_return_r, funding_cost_r, total_cost_r, no_trade_quality | Training pipeline |
| AlphaForge (Validation) | Walk-forward statistics | OOS expectancy_r, OOS Sharpe, fold stability, cost stress survival, regime breakdown | Research reports |
| AlphaForge (Report) | Report-level aggregates | active_trade_count, total_gross_R, total_net_R, exposure_pct, avg_net_R_per_active_trade | V7HandoffPackage |
| V7 | Policy metrics | Promotion readiness, confidence calibration, risk-adjusted thresholds | Runtime |

---

## Related Docs

- [ai_summary.md](ai_summary.md) — thin hub
- [alpha_thesis_lifecycle.md](alpha_thesis_lifecycle.md) — thesis states
- [data_contract.md](data_contract.md) — data layers
- [handoff_to_v7.md](handoff_to_v7.md) — V7 delivery
- [decision_log.md](decision_log.md) — locked decisions

## Related Contracts

- [../../contracts/schemas/alphaforge/](../../contracts/schemas/alphaforge/) — all schemas
- [../../contracts/mappings/simulation_to_alphaforge.md](../../contracts/mappings/simulation_to_alphaforge.md)
- [../../contracts/mappings/alphaforge_to_v7.md](../../contracts/mappings/alphaforge_to_v7.md)

## Forbidden Assumptions

- AlphaForge output is NOT a trade command.
- Model confidence does NOT override risk gates.
- SCALP/AGGRESSIVE_SCALP are NOT promotion-ready.
- Funding is DEFERRED — blocks perpetual/live claims.

## Open Holds

| Hold | Reason | Release Condition |
|------|--------|-------------------|
| SCALP thresholds | No empirical evidence | Primary research report |
| AGGRESSIVE_SCALP thresholds | No empirical evidence | Primary research report |
| Funding model | DEFERRED | Implementation of funding cost model |
| SWING recalibration | Initial baseline only | First walk-forward validation |
