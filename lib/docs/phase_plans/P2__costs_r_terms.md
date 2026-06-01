# P2 — Costs: R-Normalized Cost Functions

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P2`
**One-line goal:** Add R-normalized cost functions (`fee_cost_r`, `slippage_cost_r`, `total_cost_r`) to `lib/costs/`.
**Why now:** Both simulation's ActionOutcome (S1.B/S2.B) and alphaforge's R-label builder (P2.C) need costs expressed in R-terms. The formula is pure arithmetic over existing lib/ primitives — put it in lib/ to prevent both systems from reimplementing the same division.
**Blast radius:** `lib/costs/r_costs.py`, `lib/costs/__init__.py`, `lib/tests/test_costs_r.py`
**Rollback path:** Revert added file, remove new exports from `__init__.py`. Downstream consumers not yet implemented — zero impact.
**Execution class:** `implementation`
**Execution automation:** `enabled`
**Scale mode:** `stable_3`
**Safe parallelism target:** `1`
**Done when:** `r_costs.py` exists, all test gates pass, import boundary holds, existing cost tests unaffected.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P2` |
| Title | `Costs: R-Normalized Cost Functions` |
| Status | `Planned` |
| Last updated | `2026-06-01` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `R-normalized fee and slippage cost computation shared by simulation and alphaforge` |
| Product-code changes | `Allowed` |
| Execution class | `implementation` |
| Execution automation | `enabled` |
| Selected scale mode | `stable_3` |
| Requested max workers | `3` |
| Expected DAG effective parallelism | `1` |
| Expected safe effective parallelism | `1` |
| Worktree isolation | `Required` |
| Integration queue | `Required` |
| Isolation mode | `worktree` |

### 1.1 RACI

| Workstream | R | A | C | I |
|---|---|---|---|---|
| All phase workstreams | Implementation Agent | Plan Owner | V7 Runtime/ML Reviewer | Maintainers |

---

## 2. Purpose

`lib/costs/` currently has `estimate_fee`, `estimate_maker_fee`, `estimate_taker_fee` (absolute quote currency) and `get_slippage` (absolute quote currency). Both simulation's `ActionOutcome` contract and alphaforge's P2.C R-label builder need costs in R-terms — i.e., normalized by `atr * stop_multiplier`.

The formula is pure arithmetic: `existing_lib_function(notional, ...) / (atr * stop_multiplier)`. It depends only on existing lib/costs primitives and the ATR/stop_multiplier values passed as parameters. No mode config, no profile versioning, no simulation state.

Adding these to `lib/costs/` prevents both simulation and alphaforge from independently implementing the same division — which would violate the architecture rule that "simulation wraps and versions cost formulas, lib/ provides the primitives."

---

## 3. What Carried Over — Must Stay Stable

* [ ] lib/ stays primitive; no imports from v7, alphaforge, or simulation.
* [ ] Must call existing `estimate_fee` and `get_slippage` — no reimplementation.
* [ ] Existing cost functions (`estimate_fee`, `estimate_maker_fee`, `estimate_taker_fee`, `get_slippage`) remain unchanged.
* [ ] Import boundary test must continue to pass.
* [ ] `1R = atr * stop_multiplier` (the simulation convention — not `atr * entry_price`).
* [ ] Worktree isolation remains available.
* [ ] Integration queue remains enabled.
* [ ] `git push` remains forbidden.

---

## 4. Background / What Was Wrong

The `ActionOutcome` contract in `simulation/docs/contracts.md` explicitly includes `fee_cost_r: number` and `slippage_cost_r: number` as first-class fields. AlphaForge P2.C's R-label builder computes `long_R_net = gross_R - fee_cost_r - slippage_cost_r`.

The conversion from absolute cost to R-terms is always the same formula:
```
cost_r = cost_quote / (atr * stop_multiplier)
```

This formula has no business logic — it's division. Putting it in lib/ eliminates a predictable code duplication between simulation/resolvers/cost_resolver.py and alphaforge's labels.

---

## 5. Current Failure State / Known Blockers

* `lib/costs/r_costs.py` = not implemented
* `fee_cost_r`, `slippage_cost_r`, `total_cost_r` = not implemented
* No R-term cost availability for either simulation or alphaforge

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Division by zero (atr=0 or stop_multiplier=0) | medium | medium | Explicit guard: return 0.0 if atr <= 0 or stop_multiplier <= 0; test covers this |
| Reimplements fee/slippage logic instead of calling existing functions | low | high | Acceptance criteria explicitly require calling existing `estimate_fee` and `get_slippage`; test verifies |
| Import boundary violation | low | critical | Existing test gate catches this; no new external imports |
| Existing cost tests break | low | medium | No existing files modified — only new file + __init__.py additions |

---

## 7. Workstreams

### P2.A — R-Normalized Cost Functions

**Goal:** Add `fee_cost_r`, `slippage_cost_r`, and `total_cost_r` to `lib/costs/r_costs.py`.

**Dependencies:** None (foundation — depends only on existing `lib/costs/fees.py` and `lib/costs/slippage.py` which are already built)
**Parallel Group:** batch_1
**Risk Level:** low
**Queue Priority:** critical
**Can run with:** None (single workspace — linear dependency)

**Requirements:**
* `fee_cost_r(notional: float, entry_price: float, atr: float, stop_multiplier: float, tier: str = "taker") -> float`
  * Formula: `estimate_fee(notional, tier) / (atr * stop_multiplier)`
  * Returns 0.0 if `atr <= 0` or `stop_multiplier <= 0`
* `slippage_cost_r(notional: float, entry_price: float, atr: float, stop_multiplier: float, avg_liquidity: float = 0.0) -> float`
  * Formula: `get_slippage(notional, avg_liquidity) / (atr * stop_multiplier)`
  * Returns 0.0 if `atr <= 0` or `stop_multiplier <= 0`
* `total_cost_r(notional: float, entry_price: float, atr: float, stop_multiplier: float, tier: str = "taker", avg_liquidity: float = 0.0) -> float`
  * Formula: `fee_cost_r(...) + slippage_cost_r(...)`

**File Scope:**
```text
lib/costs/r_costs.py
lib/costs/__init__.py
lib/tests/test_costs_r.py
```

**Acceptance Criteria:**
* `fee_cost_r` returns `estimate_fee(notional, tier) / (atr * stop_multiplier)`
* `slippage_cost_r` returns `get_slippage(notional, avg_liquidity) / (atr * stop_multiplier)`
* `total_cost_r` returns `fee_cost_r + slippage_cost_r` (within float epsilon)
* `atr=0` → returns 0.0 (no division by zero)
* `stop_multiplier=0` → returns 0.0
* `atr < 0` → returns 0.0
* Known numeric example verified by hand: e.g., notional=10000, atr=100, stop_multiplier=2.0, taker fee → fee=4.0, cost_r=4.0/200=0.02
* Does NOT reimplement fee or slippage logic — calls existing functions

### P2.B — Test Gates & Integration

**Goal:** All tests pass, import boundary holds, existing cost tests unaffected.

**Dependencies:** P2.A
**Parallel Group:** batch_2
**Risk Level:** low
**Queue Priority:** high
**Can run with:** None

**Requirements:**
* `lib/tests/test_costs_r.py` covers all acceptance criteria from P2.A
* Import boundary test (`test_import_boundary.py`) still passes
* All existing cost tests (`test_costs.py`) still pass

**File Scope:**
```text
lib/tests/test_costs_r.py
```

**Acceptance Criteria:**
* `pytest lib/tests/test_costs_r.py -q` passes with zero failures
* `pytest lib/tests/ -q` passes with zero failures
* Import boundary test passes
* `test_costs.py` passes (no regressions)

---

## 8. Combined Implementation Order

```text
  Batch batch_1: P2.A  (sole foundation workspace)
  Batch batch_2: P2.B  (test gate — depends on P2.A)
```

Single linear chain. Only one implementation workspace. P2.B runs after P2.A validation passes. No file overlap conflicts.

---

## 9. Definition of Done

`P2` is complete when ALL are true:

* [ ] `lib/costs/r_costs.py` exists with `fee_cost_r`, `slippage_cost_r`, `total_cost_r`
* [ ] `lib/costs/__init__.py` exports all three new functions
* [ ] All three functions call existing `estimate_fee` / `get_slippage` — no reimplementation
* [ ] Zero/negative ATR guard returns 0.0 (no division by zero)
* [ ] Zero/negative stop_multiplier guard returns 0.0
* [ ] `lib/tests/test_costs_r.py` exists and passes
* [ ] `test_import_boundary.py` passes
* [ ] `test_costs.py` passes (no regressions)
* [ ] `1R = atr * stop_multiplier` convention correctly used
* [ ] No imports from v7, alphaforge, or simulation
* [ ] Integration queue status clean
* [ ] No forbidden commands or files used

---

## 10. Rollback Playbook

**Trigger conditions:**
* Any new test fails
* Import boundary test fails after additions
* Existing cost tests break
* Division by zero not handled

**Rollback procedure:**
1. Remove `lib/costs/r_costs.py`
2. Revert `lib/costs/__init__.py` (remove new exports)
3. Remove `lib/tests/test_costs_r.py`
4. Run `pytest lib/tests/ -q` to confirm baseline passes
5. If integration queue blocked, create handoff artifact and stop

---

## 11. What Next Phase Inherits

`P3` inherits:

* `fee_cost_r`, `slippage_cost_r`, `total_cost_r` available in `lib.costs`
* No regressions in existing cost estimation
* Clean import boundary

---

# Part 2 — Agent Brief

## Mission

Add R-normalized cost functions to `lib/costs/r_costs.py`. These functions take absolute cost estimates from existing `lib/costs/fees.py` and `lib/costs/slippage.py` and normalize them by `atr * stop_multiplier` to produce R-term costs. Must not reimplement any fee or slippage logic.

---

## Hard Requirements

1. Must call existing `estimate_fee` from `lib.costs.fees` — no reimplementation.
2. Must call existing `get_slippage` from `lib.costs.slippage` — no reimplementation.
3. No imports from v7, alphaforge, or simulation.
4. Division by zero guarded: return 0.0 when atr <= 0 or stop_multiplier <= 0.
5. `1R = atr * stop_multiplier` (not `atr * entry_price`).
6. Existing tests must not break.
7. Import boundary test must pass.
8. Worktree isolation must be enabled for parallel workspaces.
9. Integration queue must serialize merges.
10. `git push` is forbidden.

---

## Execution Policies

```yaml
execution_automation:
  autonomous_execution_enabled: true
  agent_may_mutate_repo: true
  agent_may_run_commands: true

scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
  worktree_required: true
  integration_queue_required: true

validation:
  global_validation_lock_required: true
  watch_mode_forbidden: true
```

---

## Safety Stops

* Import boundary violation (lib/ imports v7, alphaforge, or simulation)
* Fee/slippage reimplementation (not calling existing functions)
* Division by zero not handled
* Existing test regression
* `git push`

---

# Part 2.5 — v4 ExecutionKernel Doctrine

v4 replaces executor-owned execution state with an ExecutionKernel model. All actors emit events. WorkspaceAttemptController mutates attempt state. PlanSupervisor mutates plan state. PostgreSQL stores authoritative runtime truth.

---

# Part 3 — Machine-Readable Execution Contract

```json
{
  "contractVersion": "4.1.1",
  "templateVersion": "4.1.1",
  "executionClass": "implementation",
  "executionBackend": "postgres",
  "project": {
    "name": "v7_engine_lib",
    "rootPath": ".",
    "type": "repo",
    "tags": ["v7", "lib", "costs", "p2"]
  },
  "intent": {
    "parallelism": 3,
    "safetyLevel": "strict",
    "conflictRisk": "low",
    "executionEnvironment": {
      "mode": "local_sandbox",
      "untrustedCodeAllowed": false,
      "networkPolicy": "host_default",
      "secretsPolicy": "forbidden_files_and_env_allowlist"
    },
    "deadlines": {
      "llmRequestMs": 120000,
      "llmStreamIdleMs": 300000,
      "workspaceOverallMs": 1800000,
      "validationDefaultMs": 600000,
      "validationHeavyMs": 1200000,
      "schedulerNoProgressMs": 300000
    }
  },
  "derivedExecutionProfile": {
    "isolationMode": "worktree",
    "worktreeRequired": true,
    "maxCodegenWorkers": 3,
    "integrationQueueRequired": true,
    "gitRunnerQueueRequired": true,
    "admissionGateMode": "strict",
    "writeSetDriftPolicy": "reject_or_handoff"
  },
  "executionAutomation": {
    "autonomousExecutionEnabled": true,
    "agentMayMutateRepo": true,
    "agentMayRunCommands": true
  },
  "safety": {
    "hardStops": [
      "import_boundary_violation",
      "fee_slippage_reimplementation",
      "division_by_zero_unhandled",
      "existing_test_regression",
      "worktree_path_escape",
      "integration_merge_without_validation",
      "watch_mode_validation",
      "git_push"
    ],
    "forbiddenCommands": [
      "git push", "git push --force", "rm -rf"
    ]
  },
  "workspaces": [
    {
      "id": "P2.A",
      "title": "R-Normalized Cost Functions",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "conflictScope": ["lib/costs/r_costs.py", "lib/costs/__init__.py", "lib/tests/test_costs_r.py"],
      "worktree": { "required": true },
      "integration": { "queueRequired": true, "queuePriority": "critical" },
      "acceptanceCriteria": [
        "fee_cost_r(notional, entry_price, atr, stop_multiplier, tier='taker') -> float",
        "slippage_cost_r(notional, entry_price, atr, stop_multiplier, avg_liquidity=0.0) -> float",
        "total_cost_r(notional, entry_price, atr, stop_multiplier, tier='taker', avg_liquidity=0.0) -> float",
        "fee_cost_r calls estimate_fee from lib.costs.fees — no reimplementation",
        "slippage_cost_r calls get_slippage from lib.costs.slippage — no reimplementation",
        "total_cost_r = fee_cost_r + slippage_cost_r (within float epsilon)",
        "atr=0 returns 0.0 (no division by zero)",
        "stop_multiplier=0 returns 0.0",
        "atr < 0 returns 0.0",
        "Known numeric example: notional=10000, atr=100, stop_multiplier=2.0, taker -> fee=4.0, cost_r=0.02",
        "1R = atr * stop_multiplier convention used"
      ],
      "riskLevel": "low"
    },
    {
      "id": "P2.B",
      "title": "Test Gates & Integration",
      "dependencies": ["P2.A"],
      "parallelGroup": "batch_2",
      "conflictScope": ["lib/tests/test_costs_r.py"],
      "worktree": { "required": true },
      "integration": { "queueRequired": true, "queuePriority": "high" },
      "acceptanceCriteria": [
        "pytest lib/tests/test_costs_r.py -q passes with zero failures",
        "pytest lib/tests/ -q passes with zero failures",
        "test_import_boundary.py passes",
        "test_costs.py passes (no regressions)",
        "Covers: fee_cost_r, slippage_cost_r, total_cost_r, zero atr, zero multiplier, negative atr, known example"
      ],
      "riskLevel": "low"
    }
  ]
}
```

---

# Part 4 — Machine-Readable Summary

```json
{
  "contractVersion": "4.1.1",
  "phase": "P2",
  "title": "Costs: R-Normalized Cost Functions",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "primaryGoal": "Add fee_cost_r, slippage_cost_r, total_cost_r to lib/costs/ — R-normalized cost functions calling existing lib primitives",
  "projectName": "v7_engine_lib",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresIntegrationQueue": true,
  "safeEffectiveParallelismTarget": 1,
  "completionGate": "P2 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "TBD"
}
```
