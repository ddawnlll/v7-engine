# AlphaForge — AI Summary

**Thin hub.** Read this first (1–2 minutes) to understand AlphaForge.

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

| Mode | Business Priority | Research Priority | Threshold Status |
|------|------------------|-------------------|-----------------|
| SCALP | PRIMARY | PRIMARY | HOLD (empirical evidence required) |
| AGGRESSIVE_SCALP | PRIMARY | PRIMARY | HOLD (empirical evidence required) |
| SWING | SECONDARY_BASELINE | SECONDARY_BASELINE | LOCKED_INITIAL_BASELINE |

SCALP and AGGRESSIVE_SCALP are the primary research targets. SWING is implemented as a safer baseline/control mode.

---

## Doc Map

| Doc | Purpose |
|-----|---------|
| [discovery_authority.md](discovery_authority.md) | What AlphaForge owns, consumes, produces, and is forbidden from doing |
| [alpha_thesis_lifecycle.md](alpha_thesis_lifecycle.md) | Alpha thesis states from PROPOSED to V7_CANDIDATE |
| [data_contract.md](data_contract.md) | Data layers: raw → normalized → feature → label → manifest |
| [feature_contract.md](feature_contract.md) | FeatureSetSpec, feature groups, leakage rules |
| [label_contract.md](label_contract.md) | SimulationOutput → AlphaForge label transformation |
| [report_contracts.md](report_contracts.md) | ModeResearchReport, AlphaForgeResearchReport format and verdicts |
| [validation_contract.md](validation_contract.md) | Walk-forward, OOS, cost stress, overfit detection |
| [model_artifact_contract.md](model_artifact_contract.md) | ModelArtifact and CalibrationCandidate formats |
| [handoff_to_v7.md](handoff_to_v7.md) | V7HandoffPackage: what AlphaForge delivers to V7 |
| [storage_policy.md](storage_policy.md) | What stays in repo vs. external storage |
| [phase_plan.md](phase_plan.md) | Implementation phases P0.8B through P1.0 |
| [decision_log.md](decision_log.md) | Locked AlphaForge decisions |

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
- [v7_handoff_package.schema.json](../../contracts/schemas/alphaforge/v7_handoff_package.schema.json)

### Fixtures (`../../contracts/fixtures/alphaforge/`)
- [scalp_mode_research_report_minimal.json](../../contracts/fixtures/alphaforge/scalp_mode_research_report_minimal.json)
- [aggressive_scalp_mode_research_report_minimal.json](../../contracts/fixtures/alphaforge/aggressive_scalp_mode_research_report_minimal.json)
- [swing_mode_research_report_minimal.json](../../contracts/fixtures/alphaforge/swing_mode_research_report_minimal.json)
- [alphaforge_research_report_minimal.json](../../contracts/fixtures/alphaforge/alphaforge_research_report_minimal.json)
- [v7_handoff_package_minimal.json](../../contracts/fixtures/alphaforge/v7_handoff_package_minimal.json)

### Mappings (`../../contracts/mappings/`)
- [simulation_to_alphaforge.md](../../contracts/mappings/simulation_to_alphaforge.md)
- [alphaforge_to_v7.md](../../contracts/mappings/alphaforge_to_v7.md)

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
Simulation Engine (economic truth)
    │
    ▼
SimulationOutput ──► LabelDataset (LONG/SHORT/NO_TRADE labels)
    │
    ▼
AlphaForge Training Run (feature + label → model)
    │
    ▼
Validation (walk-forward, OOS, cost stress, no-trade comparison)
    │
    ▼
ModeResearchReport (per-mode verdict)
    │
    ▼
AlphaForgeResearchReport (aggregate)
    │
    ▼
V7HandoffPackage ──► V7 Acceptance Gates
```

---

## Safe Next Implementation Order

1. **P0.8B** (this task): Authority lock, docs, contracts — DONE
2. **P0.8C**: Re-audit after authority lock — DONE
3. **P0.9A**: AlphaForge implementation scaffold (package structure, contract readers, report writer interfaces)
4. **P0.9B**: Data/label/feature pipeline
5. **P0.9C**: All-mode research reports
6. **P1.0**: V7 handoff candidate

---

## Do Not Do (For Agents)

- Do NOT implement AlphaForge source code until P0.9A
- Do NOT add training scripts, dataset builders, or model code
- Do NOT modify lib/, simulation/, v7/, runtime/, or interface/ source files
- Do NOT change SimulationOutput semantics
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
- [v7/](../../v7/docs/) — policy acceptance authority
- [contracts/](../../contracts/) — cross-domain schemas
- [runtime/](../../runtime/docs/) — execution lifecycle
