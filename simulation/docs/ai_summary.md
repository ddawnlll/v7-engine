# Simulation AI Summary — Machine-Readable Authority Reference

## META

This document is the **root hub** of `/simulation` documentation. It is:

1. A dense synthesis of every `/simulation` markdown file — designed for LLM code agents and AI-assisted engineering workflows.
2. The **canonical entry point** for any human or agent needing to understand the simulation authority.
3. A **table of contents** linking to every authority doc with a one-line summary.

**If you read only one doc, read this one.** If this doc conflicts with lower-level authority docs, the lower-level authority docs win.

### Cross-Domain Authority Notice

The root cross-domain contract authority now lives in **`contracts/`** at the repo root.
The root cross-domain governance lives in **`docs/architecture/governance.md`**.

This document is the **simulation-local** authority summary — it describes simulation-internal semantics,
contracts, and implementation plans. For cross-domain contract definitions (SimulationOutput schema,
SimulationProfile schema, field mappings to alphaforge/v7), consult:

- `contracts/registry.json` — master contract list
- `contracts/schemas/simulation_output.schema.json` — canonical SimulationOutput schema
- `contracts/schemas/simulation_profile.schema.json` — canonical SimulationProfile schema
- `contracts/mappings/simulation_to_alphaforge.json` — field-level mapping to AlphaForgeLabel
- `contracts/mappings/simulation_to_v7.json` — field-level mapping to TradeOutcome
- `contracts/compatibility.json` — version compatibility rules
- `docs/architecture/governance.md` — conflict resolution and domain ownership

**Sibling subsystem summaries (for complete context):**
- `ai_summary.md` at repo root — meta-hub linking all subsystem summaries
- `v7/docs/ai_summary.md` — V7 pipeline: contracts, labels, features, model, calibration, policy, portfolio, risk, evaluation, monitoring, implementation phases
- `runtime/docs/ai_summary.md` — operational Python backend: scan loop, analyzer, learning, schema, API routes
- `interface/docs/ai_summary.md` — React operator UI: workspace structure, page ownership, component architecture, migration plan

Simulation-local docs remain authoritative for simulation-internal details.
For cross-domain conflicts, `docs/architecture/governance.md` wins.

**Source tree:** `simulation/docs/`
**Files synthesized (14 docs):**

| Doc | One-Line Purpose |
|---|---|
| [vision.md](vision.md) | What simulation is, why it exists, success definition, what it is NOT |
| [architecture.md](architecture.md) | Component design, data flow, module structure, dependency rules |
| [contracts.md](contracts.md) | SimulationInput, SimulationOutput, ActionOutcome, NoTradeOutcome, PathMetrics, SimulationProfile — all typed schemas |
| [profiles.md](profiles.md) | Mode-specific config: SWING (4h), SCALP (1h), AGGRESSIVE_SCALP (15m) — all parameters |
| [cost_model.md](cost_model.md) | Fee (maker/taker bps), slippage (volatility-adjusted), net R formula |
| [exits_and_horizons.md](exits_and_horizons.md) | Stop, target, time-exit, horizon-end, unresolved, invalidated — precedence rules |
| [no_trade_quality.md](no_trade_quality.md) | NO_TRADE as first-class: saved-loss, missed-opportunity, quality classification |
| [lineage_and_versioning.md](lineage_and_versioning.md) | All 12 version surfaces, bump rules, old-label traceability, version registry |
| [replay_paper_and_runtime_hosting.md](replay_paper_and_runtime_hosting.md) | V7 hosting contract, 5 adapters, side-effect-free guarantees, paper/replay parity |
| [monte_carlo.md](monte_carlo.md) | Diagnostic/distributional simulation, N=100 paths, perturbation, MC lineage |
| [validation.md](validation.md) | Test gates: unit, golden, integration, import-boundary, parity, hidden-simulator audit |
| [migration_from_v7.md](migration_from_v7.md) | Old→new location map, wording changes, migration checklist, rollback plan |
| [../README.md](../README.md) | Authority overview, ownership diagram, key design rules, current status |
| [phases/](phases/) | S0–S6 implementation phase plans (v4.1.1 template) |

## Reading Order

**For AI agents (recommended):**
1. This file (complete)
2. [vision.md](vision.md) — understand the "why"
3. [architecture.md](architecture.md) — understand the "how"
4. [contracts.md](contracts.md) — understand the I/O shapes
5. Drill into specific docs as needed (profiles, costs, exits, etc.)

**For implementation agents executing phase S1–S6:**
1. This file (complete)
2. The specific phase plan in [phases/](phases/)
3. All docs referenced by that phase's workstreams
4. [validation.md](validation.md) — know what tests you must pass

**For architecture review:**
1. [vision.md](vision.md) → [architecture.md](architecture.md) → [contracts.md](contracts.md)
2. [profiles.md](profiles.md) → [cost_model.md](cost_model.md) → [exits_and_horizons.md](exits_and_horizons.md)
3. [replay_paper_and_runtime_hosting.md](replay_paper_and_runtime_hosting.md) → [validation.md](validation.md)

---

## 1. SYSTEM IDENTITY

> **Source:** [vision.md](vision.md), [../README.md](../README.md)

### 1.1 One-Sentence Definition
`/simulation` is the single economic truth authority that evaluates LONG_NOW, SHORT_NOW, and NO_TRADE outcomes under one configurable, versioned, mode-specific simulation engine — producing cost-aware realized R, path metrics, and comparative action evidence consumed by V7 runtime and AlphaForge pipelines.

### 1.2 Authority Boundaries
- **simulation/ owns:** economic truth semantics, contracts, engine logic, profiles, costs, exits, path metrics, no-trade quality, Monte Carlo, lineage, golden tests
- **v7/ runtime owns:** operational hosting, execution, paper/replay/live control, TradeOutcome normalization, policy/risk interpretation
- **alphaforge/ owns:** labels, datasets, training, calibration, evaluation (consumes simulation outputs via adapters)
- **lib/ owns:** primitive helpers only (market data client, indicators, basic cost formulas, time utilities)

### 1.3 Dependency Rules
```
simulation may import lib/ primitives
simulation MUST NOT import v7/** or alphaforge/**
v7 may import/host simulation through stable contracts
alphaforge may consume simulation through side-effect-free adapters
lib MUST NOT import simulation/, v7/, or alphaforge/
```

### 1.4 Key Design Rules
1. One engine, mode-configured (SWING/SCALP/AGGRESSIVE_SCALP)
2. No label-only simulator (alphaforge must not contain hidden simulation truth)
3. No backtest-only simulator (replay is the same engine in replay mode)
4. No hidden deterministic veto (regime constraints are policy-layer, not simulation)
5. Side-effect-free adapters for training/evaluation
6. Paper/replay parity (identical outputs for identical inputs)
7. Versioned everything (any semantic change bumps a version)
8. Unresolved ≠ Invalidated (distinct states with clear semantics)
9. Monte Carlo is diagnostic only (does NOT replace realized truth)
10. Timing annotations are metadata-only in first version

---

## 2. CONTRACT SURFACES

> **Source:** [contracts.md](contracts.md)

### 2.1 SimulationInput
| Field Group | Key Fields |
|---|---|
| Identity | symbol, decision_timestamp, mode, primary_interval |
| Market State | canonical_state_lineage (state_version, feature_schema_version, source_data_version) |
| Future Path | candles[], completeness_status (COMPLETE/PARTIAL/CORRUPTED), expected_bars |
| Profile Refs | simulation_profile_version, simulation_family_version, cost_model_version, fee_model_version, slippage_model_version, horizon_family, stop_family, target_family, time_exit_family, invalidation_multiplier |
| Entry Context | entry_price, atr |
| Metadata | adapter_kind (TRAINING/EVALUATION/REPLAY/PAPER/LIVE_OUTCOME), entry_timing_annotation (metadata-only) |

### 2.2 SimulationOutput
| Field Group | Key Fields |
|---|---|
| Identity | simulation_run_id, symbol, decision_timestamp, mode, primary_interval |
| Resolution | resolution_status (COMPLETE/UNRESOLVED/INVALIDATED), invalidity_reason |
| Comparative | long_outcome (ActionOutcome), short_outcome (ActionOutcome), no_trade_outcome (NoTradeOutcome) |
| Selection | best_action, second_best_action, action_gap_r, regret_r, is_ambiguous |
| Lineage | All version fields from input + adapter_kind |
| Monte Carlo | monte_carlo_run_id (optional, only for MC) |

### 2.3 ActionOutcome
realized_r_gross, realized_r_net, fee_cost_r, slippage_cost_r, total_cost_r, exit_resolution (ExitResolution), path_metrics (PathMetrics), action_utility

### 2.4 NoTradeOutcome
saved_loss_r, saved_loss_score, missed_opportunity_r, missed_opportunity_score, no_trade_quality (CORRECT_NO_TRADE/SAVED_LOSS/MISSED_OPPORTUNITY/AMBIGUOUS_NO_TRADE), was_correct_skip

### 2.5 ExitResolution
exit_reason (STOP_HIT/TARGET_HIT/TIME_EXIT/HORIZON_END/UNRESOLVED/INVALIDATED), stop_hit, target_hit, time_exit, horizon_end, stop_before_target, target_before_stop, same_candle_ambiguity, ambiguous_resolution

### 2.6 PathMetrics
mfe, mae, mfe_r, mae_r, time_to_mfe, time_to_mae, path_quality_score (0–1), path_quality_bucket (HIGH/MEDIUM/LOW)

### 2.7 SimulationProfile (per mode)
primary_interval, context_intervals, refinement_intervals, max_holding_bars, stop_method, stop_multiplier, target_method, target_multiplier, ambiguity_margin_r, min_action_edge_r, mae_penalty_weight, cost_penalty_weight, time_penalty_weight, no_trade_default

---

## 3. MODE PROFILES

> **Source:** [profiles.md](profiles.md)

| Parameter | SWING | SCALP | AGGRESSIVE_SCALP |
|---|---|---|---|
| Primary interval | 4h | 1h | 15m |
| Context intervals | [1d, 1h] | [4h, 15m] | [1h, 5m] |
| Refinement intervals | [1h] | [15m] | [5m] |
| Max holding bars | 30 | 12 | 5 |
| Stop multiplier | 2.0–2.5 | 1.5–2.0 | 1.0–1.5 |
| Target multiplier | 2.0–3.0 | 1.5–2.0 | 1.0–1.5 |
| Ambiguity margin (R) | 0.20 | 0.10 | 0.05 |
| Min action edge (R) | 0.35 | 0.15 | 0.08 |
| MAE penalty weight | 1.0 | 2.0 | 3.0 |
| Cost penalty weight | 1.0 | 2.0 | 3.0 |
| Time penalty weight | 0.3 | 1.5 | 2.5 |
| NO_TRADE tendency | LOW | MEDIUM | HIGH (default) |

---

## 4. COST MODEL

> **Source:** [cost_model.md](cost_model.md)

### 4.1 Core Formula
realized_r_net = realized_r_gross - fee_cost_r - slippage_cost_r
1R = atr * stop_multiplier

### 4.2 Fee Model
- maker_fee_bps: 2.0 (0.02%)
- taker_fee_bps: 4.0 (0.04%)
- Conservative default: use taker fees for both entry and exit
- fee_cost_r = (entry_fee + exit_fee) / 1R

### 4.3 Slippage Model
- slippage_bps: 1.0 (0.01%)
- volatility_adjust: true
- slippage_cost_r = (entry_slippage + exit_slippage) / 1R

---

## 5. EXIT FAMILIES

> **Source:** [exits_and_horizons.md](exits_and_horizons.md)

### 5.1 Stop/Target/Time Exit
- Stop/target levels: entry_price ± (atr * multiplier)
- Precedence: stop checked before target (conservative, versioned)
- Same-candle ambiguity: stop takes precedence, ambiguity recorded
- Time exit: exit at close after max_holding_bars
- Horizon end: path exhausted without exit

### 5.2 Unresolved vs Invalidated
- UNRESOLVED: future window incomplete, may still complete
- INVALIDATED: data corrupted, missing > 2× horizon, irrecoverable
- Neither used as training labels
- INVALIDATED carries explicit invalidity_reason

---

## 6. NO-TRADE QUALITY

> **Source:** [no_trade_quality.md](no_trade_quality.md)

| Classification | Condition |
|---|---|
| CORRECT_NO_TRADE | Both directions near-zero or below edge |
| SAVED_LOSS | At least one direction lost money |
| MISSED_OPPORTUNITY | Best direction beat min_action_edge |
| AMBIGUOUS_NO_TRADE | Contradictory outcomes within ambiguity margin |

saved_loss_r = max(0, -min(long_r_net, short_r_net))
missed_opportunity_r = max(0, best_directional_r) if best > min_edge else 0

---

## 7. LINEAGE AND VERSIONING

> **Source:** [lineage_and_versioning.md](lineage_and_versioning.md)

Any semantic change to stop/target/cost/horizon/time-exit/no-trade quality bumps the corresponding version.

| Surface | Version Field |
|---|---|
| Engine semantics | simulation_family_version |
| Profile parameters | simulation_profile_version (per mode) |
| Cost model | cost_model_version |
| Fee computation | fee_model_version |
| Slippage computation | slippage_model_version |
| Horizon | horizon_family |
| Stop logic | stop_family |
| Target logic | target_family |
| Time exit | time_exit_family |
| Monte Carlo | monte_carlo_family_version |
| Label interpretation | label_interpretation_version (alphaforge) |

Old labels remain traceable to the simulation family that produced them.

---

## 8. ADAPTER RULES

> **Source:** [replay_paper_and_runtime_hosting.md](replay_paper_and_runtime_hosting.md)

### 8.1 Adapter Types
- Training adapter (alphaforge): side-effect-free, deterministic, no live execution
- Evaluation adapter (alphaforge): side-effect-free, deterministic, no live execution
- Replay driver (v7): historical replay, no live exchange/broker
- Paper driver (v7): paper forward simulation, no order submission
- Monte Carlo driver: N perturbed paths, diagnostic output

### 8.2 Parity
Training output == Evaluation output == Replay output == Paper output (identical input → identical output)

### 8.3 Regime Visibility
Regime constraints (ADVISORY/SOFT_BLOCK/HARD_BLOCK) are policy-layer, not simulation. Simulation always exposes raw comparative outcomes. Policy override is recorded separately.

---

## 9. MONTE CARLO

> **Source:** [monte_carlo.md](monte_carlo.md)

- Diagnostic/distributional only
- N paths (default 100)
- Perturbation: price noise (Method 1, sigma=0.002)
- Output: expected-R distribution, downside risk, target/stop probabilities, confidence stability
- Carries separate lineage (monte_carlo_run_id)
- Never replaces realized truth

---

## 10. VALIDATION GATES

> **Source:** [validation.md](validation.md)

| Gate | Type |
|---|---|
| Stop/target/time-exit correctness | Unit tests |
| Fee/slippage correctness | Unit tests |
| Path metrics correctness | Unit tests |
| No-trade quality classification | Unit tests |
| Comparative action selection | Unit tests |
| Resolution status correctness | Unit tests |
| Golden tests (12+ fixtures) | Golden tests |
| Full input→output flow | Integration tests |
| Import boundaries (simulation not import v7/alphaforge) | Hard-stop tests |
| Adapter parity | Parity tests |
| Monte Carlo distinguishable from realized | MC tests |
| Hidden simulator audit | Search-based audit |
| Timing annotation metadata-only | Annotation tests |
| Regime visibility preservation | Visibility tests |
| Profile resolution and validation | Config tests |

---

## 11. PHASE SUMMARY

> **Source:** [phases/](phases/)

| Phase | Goal |
|---|---|
| S0 | Create /simulation authority, docs, contracts, migration pointers |
| S1 | Standardize comparative LONG_NOW/SHORT_NOW/NO_TRADE engine |
| S2 | Profiles, costs, exits, horizons, versioning |
| S3 | Side-effect-free adapters, runtime hosting integration |
| S4 | Path metrics, no-trade quality, Monte Carlo |
| S5 | Golden tests, replay parity, drift guards, hidden simulator audit |
| S6 | V7/AlphaForge integration and rollout |

---

## 12. FORBIDDEN PATTERNS

> **Source:** [validation.md](validation.md), [replay_paper_and_runtime_hosting.md](replay_paper_and_runtime_hosting.md), [architecture.md](architecture.md) (import rules)

| Pattern | Detection |
|---|---|
| Hidden label-only simulator in alphaforge | Import boundary + search audit |
| Hidden backtest-only simulator in alphaforge | Import boundary + search audit |
| Simulation truth implemented in lib/ | Import boundary |
| V7 policy/risk silently overriding simulation outputs | Code review + regime visibility tests |
| Regime forcing no-trade via 99.0 stop multiplier inside simulation | Architecture rule: regime is policy-layer |
| Simulator that ignores costs | Test: fee/slippage always included |
| Timing annotation silently shifting entry price | Test: annotation preserved as metadata only |
| INVALIDATED outcomes used as training labels | Test: invalid outcomes excluded from dataset |
| Simulation importing v7/ or alphaforge/ | Hard-stop import boundary test |
| Monte Carlo outputs used as realized truth | Test: MC lineage always distinct |

---

## 13. SEARCH TERMS

> **Use these terms for audits across the entire v7-engine monorepo.**
> See also: [migration_from_v7.md](migration_from_v7.md) for stale-wording audit checklist.

simulation, simulation truth, truth layer, runtime-hosted simulation, label-only simulator, backtest-only simulator, side-effect-free adapter, TradeOutcome, R-label, R multiple, realized R, NO_TRADE, LONG_NOW, SHORT_NOW, cost model, fee model, slippage model, horizon family, stop family, target family, time-exit family, unresolved, invalidated, Monte Carlo, paper forward, historical replay, runtime simulation, AlphaForge simulation adapter, import boundary, hidden simulator, regime gate forced no trade

---

## 14. GPU/CUDA BACKTEST MIGRATION (LOCKABLE_WITH_HOLDS)

CPU-parallel numba batch path is **LOCKED** and wired into production via `backtest_signals()` → `BatchSimulator(use_batch=True)`. Two real bugs found and fixed (MFE clamp, time_to_mae). Parity: 500 cases × 10 fields = all 0.00e+00 max diff.

**GPU (cuda.jit):** Retained behind `force_gpu=True` opt-in. Proven 2-3x slower than CPU-parallel at ALL scales (100–2M paths on Tesla T4). GPU utilization 0–62% but never wins. Not recommended for short-path workloads (5–30 bars).

**Production wiring:** `pipeline.py` → `backtest_signals()` → `BatchSimulator(run_batch_cpu())`. CPU-parallel is the default and only active path.

**Key numbers:** 10K signals: original 5.0s → new 3.2s (1.58x). 69K signals measured: ~6.6s.

See: [gpu_cuda_migration_plan.md](gpu_cuda_migration_plan.md) — full benchmark data, bug fix details, GPU crossover analysis.
