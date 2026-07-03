# V7 Roadmap

## Purpose

Defines the recommended implementation and rollout order for V7.

It answers:

> Now that the documentation set exists, what should be implemented first, what can wait, and what should not be mixed into the early phases?

This is a sequencing document, not a second architecture document.

---

## Core Position

V7 should be built in layers:

1. contract correctness
2. truth-layer correctness
3. dataset/model correctness
4. calibration/policy correctness
5. runtime integration correctness
6. safety and rollout hardening

Do not start with the hardest runtime or infra problems.

---

## Current State

Documentation authority is largely complete for:

- core direction
- **mode-centric architecture** (see `v7_mode_centric_architecture.md`)
- **regime-aware extensions** (see `v7_regime_aware_extensions.md`)
- **profitability thesis** (see `profitability_thesis.md` — P0.6A design lock)
- contract family
- runtime integration
- runtime fallback/deployment policy
- full pipeline authority set

**P0.7A-C Lock Status (2026-06-18):**
- **P0.7A — Simulation MVP:** ✅ PASS. Simulation truth authority has minimal viable implementation (contracts, engine, exits, costs, golden tests, import boundary). 222 tests pass. `SimulationProfile` fixture exists.
- **P0.7B — CI Enforcement:** ✅ PASS (CI_FIRST_GREEN_RUN_HOLD). `.github/workflows/ci.yml` enforces contract checks, boundary checks, and full test suite on push/PR. First GitHub green run pending verification.
- **P0.7C — SWING Thresholds:** ✅ PASS. SWING promotion thresholds are **LOCKED_INITIAL_BASELINE** — owner-reviewed conservative baselines ready for implementation. SCALP thresholds remain **HOLD** pending empirical evidence. AGGRESSIVE_SCALP thresholds are **LOCKED_INITIAL_BASELINE** (Issue #36).
- **P0.x — Policy Critic RL Research:** ✅ PASS. Full research + codebase mapping (V7 pipeline, AlphaForge, Simulation, Contracts/Runtime) + literature review (offline RL methods, critic/calibration, reward design, finance RL failure modes) + grounded RL architecture recommendation completed. **LOCK_CANDIDATE** — design documented in `v7/docs/policy_critic/`. Open HOLDs (replay buffer, regret_r, funding, per-direction expected_R, synthesized features, conformal exchangeability) must be resolved before lock.

**Design Lock Status:** The V7 pre-implementation design is now **LOCKABLE_WITH_HOLDS**. Implementation can proceed with SWING as secondary baseline/control mode (LOCKED_INITIAL_BASELINE thresholds). Remaining holds are explicitly scoped (funding LOCKED_INITIAL_BASELINE, SCALP HOLD, AGGRESSIVE_SCALP LOCKED_INITIAL_BASELINE, CI first green run hold).

That means the next work should be implementation-led, not more concept invention. **Implementation starts with SWING as the secondary baseline/control mode — the safest, most lockable starting point. Primary business/research priority is SCALP and AGGRESSIVE_SCALP (see Mode Priority Alignment below).**

---

## Make/Menu Test Harness Repair (2026-07-03)

**What changed:**
- `make test` / menu test choice now use a configurable `PYTHON` defaulting to `.venv/bin/python3` when present, otherwise `python3`; this fixes environments where `python` is not installed.
- `make install` bootstraps pip with `ensurepip` when needed.
- Duplicate `candidate` target and malformed `.PHONY` continuation were removed, eliminating Makefile override warnings during `make menu`.
- `make test-all` now runs the documented local suite: `lib/tests/`, `integration/tests/`, and `simulation/tests/` while ignoring the CI-only Binance market-data test.
- Menu Python module execution now uses the active interpreter (`sys.executable`) and passes it into sub-`make` through `PYTHON`.
- Follow-on test blockers fixed: DataGateway no longer resolves symlinked temp paths, ModeResearchReport scaffolds include required `oos_ic`/`oos_rank_ic`, and CandidateOutcomeBuilder no longer imports `simulation` directly.

**Lock status:** LOCKED for local test harness usability; no trading-mode threshold changes.

**Remaining holds:** Pytest config still emits warnings for unknown `timeout` option and unknown `integration` marker; non-blocking cleanup hold, release condition is registering/adding the matching pytest plugin or removing those config assumptions.

**Design lock score:** N/A — harness repair, no architecture threshold lock.

**Evidence:** `make test`, `make test-all`, `make check-boundaries`, `make check-contracts`, and non-interactive `make menu` test selections pass on macOS with Python 3.14 venv.

---

## Pipeline Backfill/Report CLI Repair (2026-07-03)

**What changed:**
- `python -m cli backfill` no longer imports removed `AlphaForgeBackfillPipeline`; it delegates to the maintained Binance Vision downloader using the active interpreter.
- `make backfill MODE=...` now passes mode, symbols, and data directory into the CLI and writes to the canonical `data_lake/raw/binance/um/klines` layout.
- Pipeline Makefile targets now use `$(PYTHON)` instead of hardcoded `python3`, so menu and Make targets share the same venv.
- `make install` now installs the practical CLI/test dependency set needed by downloader/report paths (`numpy`, `pandas`, `pyarrow`, `aiohttp`, `tqdm`, `jsonschema`, `jinja2`, `optuna`).
- Binance Vision downloader now writes `timestamp` instead of `open_time` and accepts legacy `open_time` during 1h→4h resampling.
- Empirical ModeResearchReport builder now emits required `oos_ic` and `oos_rank_ic`, fixing `make report MODE=...` schema validation.

**Lock status:** LOCKED for Makefile/CLI harness repair. No promotion thresholds or trading decisions changed.

**Remaining holds:** `simulate`, `build-dataset`, `train`, and `wfv` legacy CLI commands remain conservative stubs/gated outside the v0.2 pipeline path; release condition is explicit wiring to production implementations or documented deprecation in favor of `make pipeline-v0.2`.

**Design lock score:** N/A — operational harness repair only.

**Evidence:** Backfill dry-run resolves to downloader command, a one-file real Binance Vision smoke backfill succeeded to `/tmp`, `make report MODE=SCALP` generated a schema-valid report, boundaries/contracts pass, and local suite remains `792 passed, 2 skipped`.

---

## Menu/Data Health Rework + Command Audit (2026-07-03)

**What changed:**
- `make menu` was rewritten from a 32-option flat list into 6 workflow-first choices: Quick Start, Data, Pipeline, Tests, Reports, and Maintenance/Advanced.
- Data workflows now ask for mode, symbol universe (BTC-only, core 4, full 20, custom), date range (smoke, half-year, year, production, custom), intervals, data directory, and execute confirmation.
- Data health now respects the selected `DATA_DIR` during interval discovery and disk coverage scanning instead of using the global `data_lake` path; stale file-count catalog entries are overridden by healthy disk coverage.
- `make data-health` accepts `ARGS` for `--intervals`, `--start`, `--end`, and `--no-auto-repair`; smoke health checks can be scoped to exactly the downloaded data range.
- Legacy `make train` and `make wfv` no longer exit with errors when gates are not satisfied; they report gated no-op status and point to `pipeline-v0.2` for executable training/WFV.
- `make pipeline` now defaults to the safe v0.2 synthetic pipeline path instead of the stale legacy chain.
- `make diagnostic` was repaired for the current `generate_labels()` return signature.

**Lock status:** LOCKED for CLI/menu usability and command health. No trading thresholds, mode authority, or live promotion semantics changed.

**Remaining holds:** Full production download remains intentionally confirmation-gated because it can be large/slow. Legacy `simulate` and `build-dataset` still report no-op/not-implemented status rather than pretending to execute production simulation/dataset construction; release condition is explicit implementation wiring or formal deprecation.

**Design lock score:** N/A — operational UX/harness repair only.

**Evidence:** Menu workflows exercised non-interactively (quick synthetic pipeline, guided download preview, guided health check, tests, reports, advanced candidate preview). Make command audit covered install, help, checks, validate, smoke backfill, scoped data-health, pipeline synthetic, pipeline-v0.2 dry-run, download dry-run, diagnostic, train/WFV gates, report, lint, and typecheck. Focused tests: 87 passed. Local suite: 792 passed, 2 skipped. System/contracts/boundaries pass.

---

## Mode Priority Alignment

### Primary vs Secondary Mode Classification

The mode implementation order (SWING first) must not be confused with business/research priority.

| Mode | Business Priority | Research Priority | Threshold Status | AlphaForge Report Type | Promotion Readiness |
|------|------------------|-------------------|-----------------|----------------------|---------------------|
| SCALP | **PRIMARY** | **PRIMARY** | HOLD (empirical evidence required) | Primary research report | Not ready until evidence |
| AGGRESSIVE_SCALP | **PRIMARY** | **PRIMARY** | LOCKED_INITIAL_BASELINE (Issue #36) | Primary research report | Baseline ready; recalibrate after first evidence |
| SWING | SECONDARY_BASELINE | SECONDARY_BASELINE | LOCKED_INITIAL_BASELINE | Secondary baseline report | Baseline ready; recalibration required after first evidence |

### Key Principles

1. **SCALP and AGGRESSIVE_SCALP are the PRIMARY business/research modes.** V7's main edge search targets shorter-term opportunities, anomaly capture, cost-aware fast reaction, and high-frequency signal validation. These modes carry the highest commercial upside.

2. **SWING is the SECONDARY_BASELINE / CONTROL mode.** SWING was locked first because it is safer, lower-noise, and easier to baseline — not because it is the primary product. It serves as a control anchor: if SWING fails, something is fundamentally wrong. If SWING works, it validates the architecture but does not validate SCALP or AGGRESSIVE_SCALP.

3. **AGGRESSIVE_SCALP is now LOCKED_INITIAL_BASELINE (Issue #36). SCALP remains HOLD.** AGGRESSIVE_SCALP threshold baselines (min_expected_r=0.10, max_drawdown_r=-3.0, cost_stress_multiplier=3.0, funding_sensitivity=CRITICAL, min_volume_ratio=1.5) are conservative starting points. SCALP HOLD reflects research difficulty and empirical evidence requirement.

4. **Promotion-readiness and research-priority are independent dimensions.** SWING and AGGRESSIVE_SCALP are LOCKED_INITIAL_BASELINE. SCALP requires empirical evidence before threshold lock.

5. **AlphaForge must support all three modes.** AlphaForge produces primary research reports for SCALP and AGGRESSIVE_SCALP, and a secondary baseline/control report for SWING. No mode is optional.

### AlphaForge Authority Lock (P0.8B+C)

**P0.8B — AlphaForge Discovery Authority Lock:** AlphaForge authority boundaries, docs, contracts, and report-level schemas are now LOCKED. See [../../alphaforge/docs/ai_summary.md](../../alphaforge/docs/ai_summary.md) for the thin hub.

**Key outcomes:**
- AlphaForge authority boundary is explicit: discovers alpha, does NOT decide trades
- 10 contract schemas, 5 minimal fixtures, 2 mapping docs created
- `contracts/registry.json` updated with AlphaForge contract entries
- `contracts/compatibility.json` updated with AlphaForge compatibility rules
- All three modes have ModeResearchReport contracts (SCALP/AGGRESSIVE_SCALP: primary_research_report, SWING: secondary_baseline_report)

**Verdict:** LOCKABLE_WITH_HOLDS. Ready for P0.9A implementation scaffold.

**P0.8C — AlphaForge Re-Audit:** ✅ PASS. Post-authority-lock re-audit confirmed AlphaForge docs, contracts, fixtures, and tests are self-consistent. `reports/p0_8c_alphaforge_reaudit.accp.yaml`.

**P0.8D — AlphaForge Profitability/Efficiency Squeeze Audit:** ✅ PASS. Identified critical contract/doc drift (gate mapping, timeframe alignment, label schema gaps, validation contract misalignment, MHT absence, schema strictness). Recommended P0.8E targeted patch. `reports/p0_8d_alphaforge_profitability_efficiency_squeeze_audit.accp.yaml`.

**P0.8E — AlphaForge Contract/Docs Profitability Patch:** ✅ PASS (2026-06-23). All 8 objectives complete:
- Gate mapping corrected to V7 canonical G0-G10
- Timeframe stacks reconciled to locked simulation profiles
- AlphaForgeLabel schema completed (gross/net cost, NO_TRADE quality, lineage)
- Validation contract aligned to V7 gates (6-fold, canonical regimes)
- MHT/data-snooping controls added
- Schema strictness tightened (nested required, empty payload rejection)
- Legacy combined docs marked SUPERSEDED
- P0.9A gated on P0.8E PASS
295 tests pass, 0 failures. `reports/p0_8e_alphaforge_profitability_contract_patch.accp.yaml`.

**Status:** P0.9A (AlphaForge implementation scaffold) is now unblocked. P0.8E prerequisites satisfied.

---

## P0.9C — AlphaForge Research Reports Finalization (2026-06-26)

**Issue:** #98 — Empirical report builder, tests, CLI report command.

**What changed:**
- `alphaforge/src/alphaforge/reports/empirical.py` — Empirical report builder that consumes WFV results (per-fold metrics, OOS summary, cost stress, regime breakdown) and produces full ModeResearchReport with REAL metrics (not placeholder zeros)
- Evidence-gated verdict system: INCONCLUSIVE → CONTINUE_RESEARCH → BASELINE_VALID → PROMOTION_CANDIDATE, mapped to schema-allowed verdicts (REJECT, CONTINUE_RESEARCH, BASELINE_VALID, CANDIDATE_FOR_V7_GATES)
- Verdict computation considers: OOS trade count, fold count, fold stability, OOS expectancy_r, OOS Sharpe, cost stress survival, regime stability
- Cost stress builder, regime breakdown builder, no-trade comparison builder all produce empirical values from WFV results
- V7 gate readiness mapping based on actual evidence quality
- `cli/v7_engine.py` — `make report` now generates empirical reports to `data/reports/{mode}/`
- `alphaforge/tests/test_empirical_report.py` — 37 tests covering verdict computation, fold stability, full report building, schema validation, JSON serialization, all three modes, cost/regime blocking

**Verdict thresholds (evidence-gated, NOT profitability claims):**
- INCONCLUSIVE: < 100 OOS trades, < 6 folds, or OOS expectancy_r <= 0
- CONTINUE_RESEARCH: OOS expectancy_r >= 0.05, OOS Sharpe >= 0.3
- BASELINE_VALID (secondary modes): OOS expectancy_r >= 0.10, OOS Sharpe >= 0.5
- PROMOTION_CANDIDATE (primary): OOS expectancy_r >= 0.15, OOS Sharpe >= 0.8
- PROMOTION_CANDIDATE (baseline exceeding): OOS expectancy_r >= 0.15, OOS Sharpe >= 0.8
- All promotions blocked by cost stress failure or regime instability

**Lock status:**
- Empirical report builder: LOCKED_INITIAL_BASELINE
- Verdict thresholds: LOCKED_INITIAL_BASELINE — recalibrate after first real data
- CLI report command: LOCKED_INITIAL_BASELINE

**Remaining holds:**
- No real profitability evidence (HOLD — requires real training + WFV)
- Verdict thresholds may need recalibration with real data (HOLD)
- Multiple symbol support not yet tested (HOLD)

**Evidence:** 37/37 tests pass (empirical reports), 589/589 alphaforge tests pass, boundaries clean. ACCP report at `reports/accp/issue-98.yaml`.

---

## #128 — Feature/Label Leakage + Causality Audit (2026-07-01)

**Issue:** #128 — Comprehensive causality audit of all alphaforge/src/ source files (read-only).

**What changed:**
- Created `alphaforge/tests/test_causality_audit.py` with 76 programmatic audit tests covering all 10 audit dimensions
- No core source files were modified — read-only audit of alphaforge/src/ per issue requirements

**Audit findings:**
1. **All active features are causally correct** (PASS): All 7 feature groups use only data up to current bar t. No-revision property verified for every function.
2. **Label/feature timestamp separation** (PASS_WITH_WARNINGS): Enforced when `label_timestamp` column present; silently skipped when absent (documented test-scenario gap).
3. **WFV purge/embargo correctness** (PASS): Purge gaps correctly computed, mode-specific constants verified.
4. **Cross-symbol lead-lag DEFERRED** (PASS): No active leakage. Note: `compute_lead_lag_score()` accesses future context data for negative lags — must be fixed before enablement.
5. **Pipeline stateless/deterministic** (PASS): Pure functional, no mutable global state.
6. **Roll/EWM no lookahead** (PASS): All EMA/MACD/RSI computations are causal.
7. **Label adapter per-record** (PASS): No cross-record state or lookahead.
8. **Domain boundary integrity** (PASS): No forbidden imports.

**Remaining holds:**
- Label timestamp separation without explicit `label_timestamp` column (MEDIUM)
- Lead-lag future data in `compute_lead_lag_score()` (INFORMATIONAL — DEFERRED)
- Embargo not actively enforced during WFV `split()` (LOW)

**Evidence:** 76/76 causality audit tests pass. All existing tests continue to pass (1687 total, 3 skipped). ACCP report at `reports/accp/issue-128.yaml`.

---

## TR-08 — Final Training Readiness Audit — v0.1 Milestone COMPLETE (2026-06-26)

**Issue:** #12 — Final audit gate. Verify all TR-01 through TR-07 gates have evidence, run full test suite, update roadmap.

**v0.1 MILESTONE: COMPLETE.** All 8 Training-Ready gates (TR-00 through TR-07) are verified with git commits, ACCP reports, and passing tests.

### TR Gate Evidence Summary

| Gate | Description | Commit | ACCP Report | Tests |
|------|------------|--------|-------------|-------|
| TR-00 | Reality Gap Baseline | `8e1d1f9` | `tr00_reality_gap_baseline_verification.accp.yaml` | PASS |
| TR-01 | Market Data Backfill | `9142f19`, `8f12939` | `issue-5.yaml` | 26/26 PASS |
| TR-02 | Simulation Adapter | P1 bundle | `training_ready_p1_execution.accp.yaml` | PASS |
| TR-03 | Pipeline CLI/Makefile/Runbook | P1 bundle | `training_ready_p1_execution.accp.yaml` | PASS |
| TR-04 | Funding/Rate Limit | P1 bundle | `training_ready_p1_execution.accp.yaml` | PASS |
| TR-05 | XGBoost Training | `f646e51` | `issue-9.yaml` | PASS |
| TR-06 | Walk-Forward Validation | `ae15e10` | `issue-10.yaml` | PASS |
| TR-07 | V7 Policy Acceptance | `0b30ac5` | `issue-11.yaml` | 93/93 PASS |

### Final Audit Results (2026-06-26)

- `make check-contracts`: 20/20 PASS (contract registry 11 + schema parity 9)
- `make check-boundaries`: 6/6 PASS (lib boundary 1 + cross-domain 5, 1 skipped)
- Full test suite: **1136 passed, 1 skipped, 0 failures** (lib/ + integration/ + simulation/ + alphaforge/ + v7/ + runtime/)
- v7 package: `v7/tests/` **93/93 PASS** (builder, validator, router, policy, gates, e2e_swing)
- EXPLICIT_GBM_BLOCK: operating as designed (post-TR-05, xgboost installed blocks ml_pilot gate import)

### v0.1 Architecture Delivered

- **lib/**: market data backfill, storage, catalog, quality, indicators, costs, funding pagination, rate limiter (244 tests)
- **simulation/**: truth authority with cost model, batch runner, market data adapter, OHLCV bridge
- **alphaforge/**: 9-module scaffold, label adapter, feature pipeline, dataset assembler, training runner, walk-forward validation
- **v7/**: Python package (6 modules) with builder, validator, router, policy, G0-G10 gates, SWING mode end-to-end
- **runtime/**: scan control, safety gates, conftest fixtures
- **contracts/**: registry.json with cross-domain schemas, compatibility.json
- **cli/**: pipeline CLI, Makefile targets, runbook

### Lock Status at v0.1

- SWING mode thresholds: **LOCKED_INITIAL_BASELINE**
- AGGRESSIVE_SCALP mode thresholds: **LOCKED_INITIAL_BASELINE** (Issue #36)
- AlphaForge contracts: **LOCKED** (canonical G0-G10, label schema, MHT, timeframes)
- Funding cost model: **LOCKED_INITIAL_BASELINE**
- Design lock: **LOCKABLE_WITH_HOLDS**

### Remaining HOLDS (post-v0.1)

| Hold | Domain | Release Condition |
|------|--------|-------------------|
| SCALP thresholds | v7 | Empirical walk-forward OOS evidence, fee/slippage stress, funding validation |
| Regime gate (G4) | v7/gates | Real regime detector implementation (current: placeholder) |
| G1-G5, G7-G8 gates | v7/gates | Real evidence data (current: placeholder implementations) |
| Real profitability evidence | All | Requires simulation labels, features, training, WF, OOS on real data |
| EXPLICIT_GBM_BLOCK | alphaforge/gates | Post-training xgboost presence is expected; gate works as designed |

**Evidence:** ACCP report at `reports/accp/issue-12.yaml`. Full test output archived in commit.

---

### Implementation Sequence

SWING is implemented first as the **control baseline** — it validates the entire architecture (contracts, simulation truth, labels, features, model training, calibration, policy, portfolio, risk, runtime integration) with the lowest risk. Once the architecture is proven via SWING, SCALP and AGGRESSIVE_SCALP research accelerates on a validated foundation.

---

## Recommended Delivery Order

### Phase 0 — Repo alignment
Goal:
- create module skeletons
- create config skeleton
- create contract types
- create test scaffolding

Exit condition:
- repository shape matches docs enough to begin implementation safely
- contract and config module skeleton tests pass

---

### Phase 1 — Contract surfaces
Goal:
- implement `AnalysisRequest`
- implement `AnalysisResult`
- implement `DecisionEvent`
- implement `TradeOutcome`
- contract validation tests

Exit condition:
- atomic lifecycle objects exist
- serialization / validation / round-trip tests pass

---

### Phase 2 — Runtime simulation, replay, and Monte Carlo layer
Goal:
- standardize the existing runtime-hosted simulation engine interface
- separate pure simulation paths from live execution side effects
- add/confirm `V6 simulation profile` and `V7 simulation profile` adapters
- add deterministic training/replay and evaluation adapters
- standardize paper forward simulation and historical replay driver behavior
- add or plan Monte Carlo robustness mode on top of the runtime simulation engine

Exit condition:
- runtime simulation scenario tests pass
- training/evaluation adapters are side-effect-free
- labels, evaluation, paper forward simulation, historical replay, outcomes, and Monte Carlo robustness mode consume the same runtime simulation engine semantics

---

### Phase 3 — Labels and features
Goal:
- implement label generation by `model_scope`
- implement canonical-state feature generation for scope defaults (`SWING` 4h/1d/1h, `SCALP` 1h/4h/15m, `AGGRESSIVE_SCALP` 15m/1h/5m)
- implement schema/version tests

Exit condition:
- deterministic feature/label rows can be produced from canonical state and runtime simulation adapter outputs
- leakage and ambiguity tests pass

---

### Phase 4 — Dataset assembly
Goal:
- implement walk-forward dataset construction with separate dataset families by `model_scope` and no mixing of primary clocks or label horizons
- symbol weighting / balancing
- lineage-preserving row export

Exit condition:
- training-ready datasets exist without temporal leakage
- walk-forward dataset tests pass

---

### Phase 5 — Model and calibration
Goal:
- train first XGBoost model-suite baseline or staged scope baseline under one shared training framework without model-side simulation
- `SWING` is the secondary baseline/control mode — implemented first to validate the architecture with lowest risk. `SCALP` and `AGGRESSIVE_SCALP` are PRIMARY business/research modes added as separate artifacts under the same framework after SWING validates the architecture.
- produce calibration artifacts per scope
- validate confidence surface per scope
- validate no-trade behavior per scope

Exit condition:
- each activated `model_scope` candidate produces stable calibrated outputs
- model + calibration smoke/evaluation tests pass per activated scope

Note:
This phase produces **candidate** artifacts, not automatically promoted artifacts.

---

### Phase 6 — Policy / portfolio / risk
Goal:
- implement policy surface per `model_scope`
- implement portfolio suppression
- implement risk hard guards
- keep timing extension advisory-first

Exit condition:
- normalized result surface matches documented semantics
- policy / portfolio / risk integration tests pass

---

### Phase 7 — Runtime integration
Goal:
- request builder
- result validator
- event creation
- outcome lifecycle
- actionability vs execution-eligibility split

Primary authority:
- `runtime/runtime_integration.md`

Exit condition:
- runtime can consume V7 contracts safely in replay/paper contexts
- lifecycle integration tests pass

---

### Phase 8 — Evaluation and monitoring
Goal:
- candidate vs baseline comparison per `model_scope`
- walk-forward review per `model_scope`
- calibration review per `model_scope`
- no-trade review per `model_scope`
- monitoring by `model_scope`, including fallback/degraded rate, calibration drift, and harmful symbol-side cohorts
- promotion gate per `model_scope`

Exit condition:
- promotion is evidence-based rather than subjective
- baseline update rules are implemented per scope
- evaluation/monitoring distinguishes activated scopes and does not infer one scope's safety from another

---

### Phase 9 — Deployment safety
Goal:
- paper mode per `model_scope`
- shadow mode where required per `model_scope`
- deployment safety gates per `model_scope`
- rollback and kill switch hardening with compatible scope artifact bundles

Exit condition:
- rollout gates from `runtime/deployment_safety.md` are testable
- rollback and kill switch tests pass
- release gate distinguishes:
  - candidate
  - paper-eligible
  - live-eligible

### Shadow-mode rule
Shadow mode is optional for general experimentation.
For the **first live-eligible V7 release**, shadow should be treated as required unless release authority explicitly waives it.

---

## Iteration Rule

The roadmap is logically phased, but implementation is not perfectly linear.

Expected loop:
- train
- calibrate
- evaluate
- adjust
- re-train
- re-evaluate

Do not treat Phase 5 and Phase 9 as a contradiction.
Phase 5 creates candidates.
Phase 9 decides promotion discipline.

---

## Things That Should Wait

These are explicitly not first implementation priorities.

### Full runtime rewrite
Wait because V7 first needs:
- stable contracts
- stable simulation truth
- stable runtime integration boundaries

### Large deep-learning stack
Wait because first phase is about:
- shared baseline quality
- explainable economic surfaces
- calibration discipline

### Per-symbol model or calibration families
Wait until shared-family evidence clearly fails and a new family is justified.

### Heavy timing planner
Wait until advisory timing evidence proves operational value.

### Advanced portfolio optimizer
Wait until lightweight portfolio rules are proven insufficient.

---

## First Real Release Shape

The first credible V7 release should be able to do all of these:

- consume valid atomic request
- produce valid atomic result
- create decision event
- create/update trade outcome
- run the runtime-hosted simulation engine through paper/replay adapters
- generate labels/features/datasets
- train a scope-compatible baseline model suite or staged activated scope artifact
- calibrate each activated scope artifact
- apply compact policy
- paper or replay evaluate it safely through the runtime simulation engine
- monitor degradation and coverage

If it cannot do these, it is not yet a complete V7 slice.

---

## Success Criteria

The first implementation milestone should demonstrate:

- contract-family correctness
- no hidden degraded paths
- runtime-hosted simulation engine shared by labels, evaluation, replay, paper, outcomes, and Monte Carlo robustness mode through side-effect-free adapters
- no-trade quality is measurable
- confidence is calibrated or visibly uncalibrated
- event/outcome lifecycle is traceable
- runtime can distinguish actionability from execution eligibility

---

## Artifact Lifecycle Note

Artifact publishing, promotion, rollback, and retirement are separate concerns.

Minimal rule set:
- training creates candidate artifacts
- evaluation determines promotability
- deployment safety governs live eligibility
- rollback changes forward active authority, not historical records

Do not collapse these into one vague “publish” step.

---

## P0.8E + P0.9A — AlphaForge Authority Lock and Implementation Scaffold (2026-06-23)

**What changed:**
- P0.8E verification found 5 blocker categories that were repaired
- Gate mapping aligned to canonical V7 G0-G10 (no old names)
- AlphaForgeLabel schema completed (24 required fields: gross/net R, cost decomposition, NO_TRADE quality, funding)
- MHT/data-snooping block added to all 3 AlphaForge report schemas with blocking semantics
- Timeframe drift fixed: SCALP primary=1h, AGGRESSIVE_SCALP primary=15m
- Schema strictness: 6-fold minimum, cost_stress/no_trade_comparison required fields, empty payloads fail
- P0.9A scaffold: 9 modules + 6 test files (48 tests, all passing)
- Implementation readiness: ~5.5 → ~7.0

**Lock status:**
- AlphaForge contracts: LOCKED (canonical G0-G10, label schema, MHT, timeframes)
- Implementation scaffold: LOCKED_INITIAL_BASELINE
- NO_TRADE as metric/comparator (not promotion gate): LOCKED
- Funding: LOCKED_INITIAL_BASELINE (funding_cost_r wired into total_cost_r and simulation engine; integration test passing)

**Remaining holds:**
- No real profitability evidence (HOLD — requires simulation labels, features, training, WF, OOS)
- SCALP/AGGRESSIVE_SCALP thresholds (HOLD — empirical backtest evidence required)
- XGBoost training (DEFERRED to P0.9B/P0.9C)
- Real data ingestion (DEFERRED to P0.9B)

**Safe next step:** V7-P0.9B AlphaForge deterministic data-label-feature pipeline

---

---

## v0.25 — Diagnostics Repair & Metric System — LOCKED (2026-07-01)

**What changed:**
- Active trade metric system implemented (`compute_oos_metrics`) — tracks LONG_NOW/SHORT_NOW/NO_TRADE counts, cost decomposition (fee + slippage), net-R arithmetic, exposure percentage, NaN guards for zero-active edge cases. 17 tests pass.
- `mode_research_report.schema.json` updated with 8 new active trade metric fields (`active_trade_count`, `long_trade_count`, `short_trade_count`, `no_trade_count`, `total_gross_R`, `total_net_R`, `exposure_pct`, `avg_net_R_per_active_trade`). Schema strictness increased: 3 new required fields in metrics object.
- All 3 mode fixtures (SWING/SCALP/AGGRESSIVE_SCALP) updated with active trade metric fields.
- `contracts/tests/test_schema_active_metrics.py` — 232-line schema validation test file for active metrics.
- `alphaforge/tests/test_active_trade_metrics.py` — 17 tests covering count correctness, cost arithmetic, edge cases, NaN guards, empty input.
- `empirical.py` report builder wired to consume `active_trade_metrics` from WFV results — wires active trade counts, net-R, exposure pct into report output.
- MHT correction module (`alphaforge/src/alphaforge/reports/mht.py`) created with Bonferroni step-down correction, Benjamini-Hochberg FDR control, deflated Sharpe ratio, trial count computation, and data-snooping risk assessment. `test_mht.py` with unit tests.
- 6-fold walk-forward validation in `cli/real_training.py` — `walk_forward_validate()` with anchored expanding windows, purge/embargo periods, 125 measures per fold (124 MHT hypotheses per fold), per-fold accuracy/stability metrics, OOS summary.
- SOLUSDT stop/target optimization (`optimize_sol_stop_target_results.json`) — best params found: stop_mult=1.0, target_mult=5.0, expectancy_r=0.10, win_rate=0.996.
- Issues #115 Cost Stress Matrix, #116 Regime Stability, #117 NO_TRADE Collapse, #118 Autotune Engine, #119 Alpha Surface Expansion — all implemented and closed.

**Lock status:**
- Active trade metric system: LOCKED
- Schema active metrics contract: LOCKED
- MHT correction module: LOCKED
- 6-fold walk-forward validation: LOCKED
- SOLUSDT optimized params: LOCKED_INITIAL_BASELINE
- Cost Stress Matrix: LOCKED
- Symbol + Regime Stability: LOCKED_INITIAL_BASELINE
- NO_TRADE Collapse Detector: LOCKED_INITIAL_BASELINE
- Autotune Engine with Nested WFV: LOCKED_INITIAL_BASELINE
- Alpha Surface Expansion: LOCKED_INITIAL_BASELINE

**Remaining holds:**
- Real profitability evidence (HOLD — requires real training + WFV)
- Walk-forward OOS expectancy_r/Sharpe still placeholder 0.0 (HOLD — needs per-fold PnL)

**Evidence:** 2048 passed, 2 skipped, 0 failures in alphaforge. All 8 issues closed with commit references. ACCP report at `reports/accp/v0.25-completion.accp.yaml`.

---

## v0.26 — MHT Pipeline/Builder Contradiction Fix + Alpha Profitability Engine — LOCKED (2026-07-01)

**What changed (MHT Pipeline/Builder Contradiction — Issue #138):**
- `_build_empirical_mht_control()` now respects pipeline's explicit `correction_method` — no longer overrides to "Bonferroni" just because `trial_count > 1`. Defaults to "NONE_APPLIED" when pipeline does not specify.
- Deflated Sharpe ratio computed from actual OOS data (`oos_sharpe` and `oos_trade_count`) when MHT is applied, via `deflated_sharpe_or_equivalent` field.
- PBO/overfit risk assessment (`pbo_or_backtest_overfit_risk`) added: CRITICAL/HIGH/MEDIUM/LOW/NOT_RUN based on deflated Sharpe and trial count.
- Blocking hold note added when `correction_method == "NONE_APPLIED"` with `trial_count > 1`.
- `rejected_candidate_count` tracks actual Benjamini-Hochberg rejections when pipeline provides `p_values`.
- 17 new tests for pipeline/builder agreement, deflated Sharpe, PBO, blocking hold, BH rejection tracking.

**What changed (Alpha Profitability Engine — Issues #145-#153):**
- Optuna core integration with TPE sampler and ASHA pruning — study management, parallel trial execution
- XGBoost search space with financial time-series optimized ranges per mode
- Nested walk-forward validation — inner fold tune + outer fold validate
- Multi-objective optimization — Sharpe + Profit Factor Pareto frontier
- Mode-specific parameter sets for SWING, SCALP, AGGRESSIVE_SCALP
- ASHA pruning to kill bad trials early
- Feature ablation with tuned model — minimum viable feature set identification
- Real data pipeline for Binance live market data tuning (BONUS gate)
- Profitability gate report with G1-G6 gate verification

**Lock status:**
- MHT pipeline/builder agreement: LOCKED
- Deflated Sharpe from actual data: LOCKED
- PBO assessment: LOCKED
- Optuna TPE sampler + ASHA pruning: LOCKED
- Nested walk-forward validation: LOCKED
- Multi-objective Sharpe + Profit Factor: LOCKED
- Mode-specific parameter profiles: LOCKED

**Remaining holds:**
- Real data pipeline: requires Binance API keys for full test (HOLD)
- MHT correction real thresholds (HOLD — requires empirical baseline)
- Cost Stress Matrix (HOLD — requires regime-aware cost multipliers)
- Real profitability evidence (HOLD — requires real training + WFV)

**Evidence:** 2048 passed, 2 skipped, 0 failures in alphaforge. All 9 issues closed with commit references. ACCP report at `reports/accp/v0.26-profitability-gate.accp.yaml`.

---

## #151 — Feature Ablation with Tuned Model (2026-07-01)

**Issue:** #151 (P2) — Identify minimum viable feature set using tuned model ablation.

**What changed:**
- Created `alphaforge/src/alphaforge/tuning/` package with `ablation.py` providing feature-level ablation using tuned XGBoost hyperparameters
- `compute_tuned_importance()` — trains tuned model, computes normalized gain importance (SHAP proxy)
- `run_feature_ablation()` — iteratively removes lowest-ranked features, retrains, monitors accuracy drop
- `recommend_minimum_feature_set()` — analyzes ablation steps for optimal trade-off recommendation
- `FeatureAblationResult` — frozen dataclass recording full ablation history
- `alphaforge/tests/test_ablation_tuned.py` — 36 tests covering importance, ablation, recommendation, validation, edge cases

**Lock status:**
- TUNED_HYPERPARAMS: LOCKED_INITIAL_BASELINE — recalibrate after Optuna study
- DEFAULT_MAX_PERFORMANCE_DROP_REL (10%): LOCKED_INITIAL_BASELINE
- TARGET_FEATURE_MIN/MAX (12-18): LOCKED_INITIAL_BASELINE

**Remaining holds:**
- SHAP package not installed — gain-based importance is a proxy (HOLD)
- Sharpe-based evaluation requires simulation integration (HOLD — classification accuracy used as proxy)
- Optuna hyperparameter tuning not yet run (HOLD — defaults used)

**Evidence:** 36/36 tests pass. ACCP report at `reports/accp-issue-151.yaml`.

---

## #158 — Feature Caching with Parquet+Zstd for Pipeline Speedup (2026-07-01)

**Issue:** #158 — Add Parquet+Zstd disk caching to the feature pipeline to eliminate redundant 5-15 minute recomputations.

**What changed:**
- Created `FeatureCache` class in `alphaforge/src/alphaforge/features/pipeline.py`:
  - Cache key = SHA-256 hash of `(symbol, interval, mode, PIPELINE_VERSION)` — version change automatically invalidates
  - Stores feature matrices as PyArrow Parquet files with Zstd compression
  - Loads with `memory_map=True` for zero-copy read access
  - Thread-safe write via `threading.Lock`
  - Methods: `get()`, `put()`, `invalidate()`, `clear_all()`
- Added `cached_compute_features()` — thin wrapper around `compute_features()` that checks cache before computing
- Added `CACHE_DIR_DEFAULT: str = ".cache/features/"` for default cache location
- Bumped `PIPELINE_VERSION` to `"0.2.0"` to reflect new caching capability
- Updated `alphaforge/src/alphaforge/features/__init__.py` to export new symbols
- Created `alphaforge/tests/test_feature_cache.py` — 31 tests covering cache key determinism, put/get roundtrip, NaN preservation, metadata preservation, invalidate/clear_all lifecycle, thread safety, cached_compute_features wrapper integration, error resilience, and edge cases (empty matrix, corrupt files, missing symbol)

**Lock status:**
- FeatureCache: LOCKED_INITIAL_BASELINE
- cached_compute_features wrapper: LOCKED_INITIAL_BASELINE
- CACHE_DIR_DEFAULT: LOCKED_INITIAL_BASELINE
- PIPELINE_VERSION 0.2.0: LOCKED

**Remaining holds:**
- Cache directory not yet configurable via environment variable or config file (LOW — can be added when CLI config lands)
- No cache size limit or LRU eviction (LOW — storage is cheap; can add later)
- No cross-process file locking (LOW — single-process pipeline is the expected use case)

**Evidence:** 31/31 new cache tests pass. 76/76 causality audit tests pass (version check updated to 0.2.0). ACCP report at `reports/accp/issue-158.yaml`.

---

## v0.30 — Real Data Lake + Evidence-Gated Workflow Research (2026-07-02)

**Scope:** RESEARCH_ONLY — No code, no config, no backfill.

### What was researched
- **14 external data sources** evaluated: Binance public archive (P0 ✅), Binance REST API (P0-P2 ✅), Glassnode (P3 conditional ✅), Coinalyze (P3 conditional), Tardis.dev (P4), Crypto Lake (P4), CryptoQuant (P4 deferred ❌), Santiment (P4 blocked ❌)
- **Data Lake architecture** designed: `lib/data_lake/` with DatasetSpec, DataCatalog, DataPassport, BackfillPlanner, ParallelDownloader, CoverageReport, ChecksumReport, DataGateway
- **DataPassport standard** designed: provenance schema for every claim
- **RealDataRequired gate** designed: hard block on synthetic data for serious claims
- **Metric plumbing gap** identified and rooted: consolidated `active_trade_count=0` vs WFV detail `1344`
- **On-chain vendor workflow** designed with PIT test protocol

### Key decisions locked
- Centralized Data Lake required — LOCKED
- Synthetic fallback blocked for ALPHA_HAS_EDGE etc. — LOCKED
- Binance public data sufficient for P0 — LOCKED
- Metric plumbing fix before data backfill — LOCKED
- On-chain data cannot generate labels — LOCKED (immutable rule)
- `lib/data_lake/` is correct module location — LOCKED_INITIAL_BASELINE
- No vendor purchases before v0.30E — LOCKED

### Reports produced (6 files)
- `reports/research/v030_real_data_lake_research.md` (794 lines)
- `reports/research/v030_data_source_matrix.yaml` (367 lines, 14 sources)
- `reports/research/v030_data_workflow_plan.md` (473 lines, 7 phases)
- `reports/research/v030_onchain_vendor_workflow.md` (270 lines)
- `reports/research/v030_repo_impact_map.md` (172 lines, 17 new + 6 modified files)
- `reports/accp/v030_real_data_lake_acccp.yaml` (146 lines)

### Implementation Status (2026-07-02)

**v0.30A + v0.30D — DatasetSpec, DataCatalog, Metric Plumbing Fix**
- ✅ `lib/data_lake/spec.py` — DatasetSpec frozen dataclass (LOCKED)
- ✅ `lib/data_lake/catalog.py` — DataCatalog with gap analysis (LOCKED)
- ✅ `target_validator.py` — `active_trade_count` fallback to `total_oos_trades` (LOCKED)
- ✅ `walk_forward_runner.py` — forward-compat `active_trade_count` key (LOCKED)
- ✅ 17 + 11 + 6 tests pass

**v0.30B + v0.30C — Data Lake Bootstrap, DataPassport, RealDataGate**
- ✅ `lib/data_lake/storage.py` — DataLakePaths medallion path resolution (LOCKED)
- ✅ `lib/data_lake/coverage.py` — CoverageReport + builders (LOCKED)
- ✅ `lib/data_lake/checksum.py` — ChecksumReport + SHA-256 batch verify (LOCKED)
- ✅ `lib/data_lake/backfill_planner.py` — BackfillPlanner + DownloadManifest (LOCKED)
- ✅ `lib/data_lake/downloader.py` — BinanceUmDownloader multi-worker (LOCKED)
- ✅ `lib/data_lake/gateway.py` — DataGateway unified read (LOCKED)
- ✅ `lib/data_lake/passport.py` — DataPassport + trustworthiness (LOCKED)
- ✅ `lib/evidence_engine/hard_caps.py` — V11 RealDataRequired gate (LOCKED)
- ✅ `alphaforge/evidence_adapter.py` — `attach_data_passport()`, `has_real_data()` (LOCKED)
- ✅ 158 data lake tests + 39 passport+gate tests pass
- Commit: `2bc74a0`

**v0.30E Config — Test-Training Profile + Data Health Checker**
- ✅ `lib/data_lake/health.py` — DataHealthChecker with auto-repair (LOCKED_INITIAL_BASELINE)
- ✅ `configs/profiles/test-training.yaml` — 4 sym × 4y, SCALP primary (LOCKED_INITIAL_BASELINE)
- ✅ `scripts/health_check.py`, `verify_training.py`, `check_passport.py` — CLI helpers (LOCKED)
- ✅ `Makefile` — `data-health`, `test-training`, `test-training-full` targets (LOCKED)
- ✅ 14 health checker tests pass
- Commit: `4809b99`

### Remaining holds
- Real data not yet downloaded (HOLD — Binance Vision backfill not executed)
- Metric plumbing fix not yet committed to training output (HOLD — pending real data run)
- v0.30E real-data baseline not yet produced (HOLD — requires backfill + training run)
- Glassnode PIT test not executed (HOLD — P3 scope, deferred)
- 20-symbol expansion (HOLD — after P0 baseline stable)

### Recommended implementation order
```
Phase 0 — v0.30D: Metric Plumbing Integrity Fix          (1 day, PARALEL)
Phase 0 — v0.30A: DatasetSpec + DataCatalog              (3-5 days, PARALEL)
Phase 1 — v0.30B: Binance UM Data Lake Bootstrap         (5-7 days)
  → 5 symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT
  → Intervals: 1h, 15m, 4h, 1d
  → Data: klines + funding_rate + mark/index/premium price
  → Range: 2022-present
Phase 2 — v0.30C: DataPassport + RealDataRequired Gate   (2-3 days)
Phase 3 — v0.30E: Real Data Baseline Evidence Control    (2-3 days)
  → CONTROL_REALDATA_SCALP_1H_BASELINE_V030
  → NO Optuna, NO threshold change, NO feature-set change
  → Measure: NO_TRADE defeat, random defeat, ALWAYS_LONG defeat, net_R, fold_pass_ratio, exposure
Phase 4 — v0.30F: On-Chain Vendor Evidence Gate          (future — after E stable)
Phase 5 — v0.30G: 20-Symbol Expansion                    (future — after E stable)
```

**20-symbol expansion gate:** Before expanding beyond 5 symbols, these conditions must ALL be met:
- 5-symbol P0 coverage > 90%, checksum pass, DataPassport present
- Metric plumbing fixed (consolidated report matches WFV detail)
- First real-data baseline evidence snapshot produced
- Evidence Engine deciding on real data, not synthetic

**On-chain / L2 gate:** Not before v0.30E complete. On-chain hard rules are immutable:
- On-chain data CANNOT generate labels
- On-chain data CANNOT be ground truth
- If NOT PIT safe: backtest feature usage FORBIDDEN

### Design Lock Status
- Data Lake architecture: LOCKED_INITIAL_BASELINE
- DataPassport standard: LOCKED_INITIAL_BASELINE
- RealDataRequired Gate: LOCKED_INITIAL_BASELINE
- Metric plumbing root cause: LOCKED
- On-chain vendor protocol: LOCKED_INITIAL_BASELINE
- Binance P0 sources: LOCKED

### Remaining holds
- Metric plumbing fix not yet applied (HOLD — pending implementation)
- Data Lake not yet implemented (HOLD — pending implementation)
- Real data backfill not yet started (HOLD — pending implementation)
- Glassnode PIT test not yet executed (HOLD — P3 scope)
- OI/Taker volume 30-day limitation (DEFERRED — P1 scope)
- 20-symbol expansion (DEFERRED — after P0 baseline)


---

## v0.30B+v0.30C — Binance UM Data Lake Bootstrap + DataPassport/RealDataRequired Gate — LOCKED (2026-07-02)

**What was implemented:**
- **v0.30A foundation:** `DatasetSpec` (immutable dataset requirement descriptor) and `DataCatalog` (extended gap-analysis catalog with spec-vs-ingested comparison, completeness scoring, and timeline gap detection) — 2 source files, 2 test files
- **v0.30B — Binance UM Data Lake Bootstrap:** Centralized medallion-architecture storage path resolution (`DataLakePaths`), backfill planner (`BackfillPlanner` with `DownloadManifest`), multi-worker parallel Binance downloader (`BinanceUmDownloader` with rate limiting, retry/backoff, atomic writes), SHA-256 batch checksum verification (`ChecksumReport`), coverage reporting (`CoverageReport`), and unified data gateway (`DataGateway` with parquet read-only access) — 6 source files, 6 test files
- **v0.30C — DataPassport:** `DataPassport` (immutable provenance/coverage/trustworthiness artifact with blocking semantics), designed for integration with `RealDataRequiredGate` — 1 source file, 1 test file
- **Total:** 10 source modules, 9 test files, **158 tests all passing**

**Lock status (all implemented modules):**
- Data Lake architecture (v0.30A): LOCKED
- Data lake storage paths: LOCKED
- Backfill planner: LOCKED
- Parallel downloader: LOCKED
- Checksum verification: LOCKED
- Coverage report: LOCKED
- Data gateway: LOCKED
- DataPassport standard: LOCKED

**Remaining holds:**
- Metric plumbing fix not yet committed (HOLD)
- v0.30E — Real Data Baseline Evidence Control not started (HOLD)
- Real data backfill not yet started (HOLD — pending v0.30E)
- Binance API key availability (NEEDS_VERIFICATION)

**Evidence:** 158/158 data lake tests pass, 469/469 lib tests pass. ACCP report at `reports/accp/v030_data_lake_implementation.accp.yaml`.

---

## FREEZE_AND_REDESIGN — P0.9A Freeze + Metric Ownership Redesign (2026-07-02)

**What:** Freeze the original P0.9A implementation scaffold for redesign. The scaffold was built before the Metric Philosophy (layer metric ownership) was fully understood. v0.25 diagnostics repair and v0.30 metric plumbing audit revealed that metric computation and ownership were inconsistently distributed across layers.

**Layer Metric Ownership:** LOCKED. See [discovery_authority.md](../alphaforge/docs/discovery_authority.md) for the full layer ownership table.

| Layer | Owns | Key Principle |
|-------|------|--------------|
| Simulation | Raw P&L, costs, economic truth | No downstream recomputes simulation metrics |
| AlphaForge (Label) | Label-time returns, costs, NO_TRADE quality | Label is the last per-trade boundary |
| AlphaForge (Validation) | Walk-forward statistics, OOS summary | Validation aggregates, does not recompute per-trade |
| AlphaForge (Report) | Report-level aggregates, verdicts | Reports summarize, do not recompute |
| V7 | Policy metrics, confidence calibration | Policy consumes reports, does not recompute alpha metrics |

**Milestone issues:**
- P0.9A metric ownership refactor — redesign scaffold to respect layer boundaries
- Metric Philosophy documentation — added to discovery_authority.md
- Layer boundary tests for metric computation — verify no cross-layer recomputation

**Lock status:**
- P0.9A-FREEZE phase: IN_PROGRESS
- Layer Metric Ownership: LOCKED
- Metric Philosophy section in discovery_authority.md: LOCKED

---

## Final Position

The roadmap for V7 is not:
- write everything
- rewrite runtime
- hope it works

It is:
- lock semantics
- implement the smallest coherent slice
- prove the truth layer
- prove the contract layer
- prove the learning layer
- only then broaden runtime and deployment sophistication

## AlphaForge Profitability v0.1 — Complete (2026-07-01)

### Implemented (14 issues)
- OrderBook features: OBI, OBI_N, OFI, VAMP, spread/VWAP-to-mid, volume HHI, micro-price (#154, #162-#166, #170)
- Triple-barrier labeling + Meta-labeling (#156, #160)
- Funding rate features (#157)
- Online regime classifier (#161)
- Combinatorial CV + Purged CV for Optuna (#159, #169)
- Symbol diversity scoring (#168)

### Not Implemented (5 issues)
- #155 (data download), #158 (caching), #167 (SHAP), #171 (docs), #172 (epic)
- Status: DEFERRED — will be revisited in v0.2

### Design Lock Status
- SWING mode feature set: LOCKED_INITIAL_BASELINE (expanded)
- OrderBook feature group: LOCKED_INITIAL_BASELINE (14 functions)
- CPCV validation: LOCKABLE_WITH_HOLDS (needs empirical calibration)
- Meta-labeling: LOCKABLE_WITH_HOLDS (threshold tuning needed)
