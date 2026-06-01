# P1 — Indicators: RSI, Candle Geometry, Momentum, Rolling Extensions

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P1`
**One-line goal:** Add RSI, candle geometry, momentum/ROC, and rolling min/max/mean to `lib/indicators/`.
**Why now:** P3.A (Deterministic Features) and v7 features.md both require these indicators. They're pure math — no state, no adapters, no mode config. Adding them to lib/ now prevents both systems from implementing the same formulas independently.
**Blast radius:** `lib/indicators/`, `lib/tests/`, `lib/indicators/__init__.py`
**Rollback path:** Revert added files. Remove new exports from `__init__.py`. No downstream consumers yet — zero impact.
**Execution class:** `implementation`
**Execution automation:** `enabled`
**Scale mode:** `stable_3`
**Safe parallelism target:** `2`
**Done when:** All 4 modules + 4 test files exist, all tests pass, import boundary test passes, all existing tests still pass.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P1` |
| Title | `Indicators: RSI, Candle Geometry, Momentum, Rolling Extensions` |
| Status | `Planned` |
| Last updated | `2026-06-01` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Pure math indicator functions shared by v7 and alphaforge` |
| Product-code changes | `Allowed` |
| Execution class | `implementation` |
| Execution automation | `enabled` |
| Selected scale mode | `stable_3` |
| Requested max workers | `3` |
| Expected DAG effective parallelism | `2` |
| Expected safe effective parallelism | `2` |
| Worktree isolation | `Required` |
| Integration queue | `Required` |
| Isolation mode | `worktree` |

### 1.1 RACI

| Workstream | R | A | C | I |
|---|---|---|---|---|
| All phase workstreams | Implementation Agent | Plan Owner | V7 Runtime/ML Reviewer | Maintainers |

---

## 2. Purpose

`lib/indicators/` currently has ATR, returns (log/simple), volatility (rolling std, Parkinson), and a generic `rolling_apply`. Both alphaforge P3.A and v7 features.md require RSI, candle geometry (body ratio, wick ratios), momentum/rate-of-change, and rolling min/max/mean.

These are pure math transforms over price sequences. They have zero business logic, zero config dependencies, zero state. Implementing them in lib/ prevents code duplication between v7 and alphaforge.

---

## 3. What Carried Over — Must Stay Stable

* [ ] lib/ stays primitive; no imports from v7, alphaforge, or simulation.
* [ ] No external dependencies (no pandas, no numpy, no ta-lib).
* [ ] Existing indicator functions (ATR, returns, volatility, rolling_apply) remain unchanged.
* [ ] Import boundary test must continue to pass.
* [ ] RSI must use Wilder's smoothed EMA (same method as existing ATR).
* [ ] Worktree isolation remains available.
* [ ] Integration queue remains enabled.
* [ ] `git push` remains forbidden.

---

## 4. Background / What Was Wrong

`lib/indicators/` is missing four categories of indicators that both alphaforge P3.A and v7 features.md explicitly list as required:

- **RSI**: Listed as a primary interval feature in P3.A acceptance criteria ("return, volatility, ATR, RSI, etc.")
- **Candle geometry**: Listed as a primary decision feature group in both P3.A and v7 features.md ("candle geometry")
- **Momentum/ROC**: Listed in primary, context, and refinement feature groups across both systems
- **Rolling min/max/mean**: Implicitly needed by "range structure", "support/resistance distance", "range compression/expansion" — all referenced in feature specs

Without these in lib/, alphaforge and v7 would each implement their own versions of the same math.

---

## 5. Current Failure State / Known Blockers

* `lib/indicators/rsi.py` = not implemented
* `lib/indicators/candle.py` = not implemented
* `lib/indicators/momentum.py` = not implemented
* `lib/indicators/rolling.py` — `rolling_max`, `rolling_min`, `rolling_mean` = not implemented

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| RSI uses simple average instead of Wilder's EMA | low | high | Acceptance criteria explicitly require Wilder's method; test verifies against known values |
| Candle ratios divide by zero (high==low) | medium | medium | Explicit NaN return when high==low; test coverage for this edge case |
| Momentum/ROC NaN for zero/negative prices | low | low | Explicit NaN return; test coverage |
| Rolling functions inconsistent with existing rolling_std | low | medium | Same NaN prefix convention (period-1); same signature style |
| Import boundary violation | low | critical | Existing test gate catches this; no new imports by design |

---

## 7. Workstreams

### P1.A — RSI Indicator

**Goal:** Add `rsi()` to `lib/indicators/rsi.py` using Wilder's smoothed EMA.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** low
**Queue Priority:** critical
**Can run with:** P1.B, P1.C, P1.D

**Requirements:**
* `rsi(prices: Sequence[float], period: int = 14) -> list[float]`
* Uses Wilder's smoothed EMA for average gain / average loss (same smoothing as existing `compute_atr`)
* First `period` values are NaN
* Handles edge cases: empty input → empty list, period > len(prices) → all NaN, zero/negative prices → NaN

**File Scope:**
```text
lib/indicators/rsi.py
lib/indicators/__init__.py
lib/tests/test_indicators_rsi.py
```

**Acceptance Criteria:**
* RSI values for a known price sequence match manually verified output
* First `period` values are all NaN
* period=1 returns all NaN (not enough bars for average gain/loss)
* Empty input returns empty list
* RSI values are in [0, 100] for valid inputs

### P1.B — Candle Geometry

**Goal:** Add `body_ratio`, `upper_wick_ratio`, `lower_wick_ratio` to `lib/indicators/candle.py`.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** low
**Queue Priority:** critical
**Can run with:** P1.A, P1.C, P1.D

**Requirements:**
* `body_ratio(opens, highs, lows, closes: Sequence[float]) -> list[float]` — `abs(close-open) / (high-low)`, NaN when high==low
* `upper_wick_ratio(opens, highs, lows, closes: Sequence[float]) -> list[float]` — `(high - max(open,close)) / (high-low)`, NaN when high==low
* `lower_wick_ratio(opens, highs, lows, closes: Sequence[float]) -> list[float]` — `(min(open,close) - low) / (high-low)`, NaN when high==low
* All outputs in [0, 1] when valid
* All four input sequences must have equal length (raise ValueError on mismatch)

**File Scope:**
```text
lib/indicators/candle.py
lib/indicators/__init__.py
lib/tests/test_indicators_candle.py
```

**Acceptance Criteria:**
* `body_ratio` returns correct values for known OHLC data
* Doji candle (open==close) returns body_ratio=0.0 (not NaN)
* Flat candle (high==low) returns NaN for all three ratios
* All ratios in [0, 1] for any valid non-flat candles
* Input length mismatch raises ValueError

### P1.C — Momentum / Rate of Change

**Goal:** Add `momentum` and `rate_of_change` to `lib/indicators/momentum.py`.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** low
**Queue Priority:** critical
**Can run with:** P1.A, P1.B, P1.D

**Requirements:**
* `momentum(prices: Sequence[float], period: int = 10) -> list[float]` — `(P_t - P_{t-period}) / P_{t-period}`
* `rate_of_change(prices: Sequence[float], period: int = 10) -> list[float]` — same formula × 100
* First `period` values are NaN
* Zero or negative `P_{t-period}` → NaN for that index
* Empty input → empty list, period > len(prices) → all NaN

**File Scope:**
```text
lib/indicators/momentum.py
lib/indicators/__init__.py
lib/tests/test_indicators_momentum.py
```

**Acceptance Criteria:**
* `momentum` returns `(P_t - P_{t-period}) / P_{t-period}` for known sequence
* `rate_of_change` returns `momentum * 100` for same input (within float epsilon)
* First `period` values are NaN
* Zero base price → NaN (no division by zero)
* Negative base price → NaN

### P1.D — Rolling Extensions

**Goal:** Add `rolling_max`, `rolling_min`, `rolling_mean` to existing `lib/indicators/rolling.py`.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** low
**Queue Priority:** critical
**Can run with:** P1.A, P1.B, P1.C

**Requirements:**
* `rolling_max(values: Sequence[float], period: int) -> list[float]`
* `rolling_min(values: Sequence[float], period: int) -> list[float]`
* `rolling_mean(values: Sequence[float], period: int) -> list[float]`
* First `period-1` values are NaN (consistent with existing `rolling_std`)
* period=1 returns values unchanged
* Constant series returns constant values after NaN prefix
* Empty input → empty list

**File Scope:**
```text
lib/indicators/rolling.py
lib/indicators/__init__.py
lib/tests/test_indicators_rolling_extensions.py
```

**Acceptance Criteria:**
* `rolling_max([1,3,2,5,4], period=3)` returns `[NaN, NaN, 3, 5, 5]`
* `rolling_min([5,3,4,1,2], period=3)` returns `[NaN, NaN, 3, 1, 1]`
* `rolling_mean([1,2,3], period=3)` returns `[NaN, NaN, 2.0]`
* period=1 returns identical values
* Constant series `[5,5,5,5]` period=2 returns `[NaN, 5, 5, 5]`
* Empty input returns empty list
* Existing `rolling_std` and `rolling_apply` still work and pass their tests

### P1.E — Test Gates & Integration

**Goal:** All tests pass, import boundary holds, existing tests unaffected.

**Dependencies:** P1.A, P1.B, P1.C, P1.D
**Parallel Group:** batch_2
**Risk Level:** low
**Queue Priority:** high
**Can run with:** None

**Requirements:**
* All new test files pass
* Import boundary test (`test_import_boundary.py`) still passes
* All existing indicator tests (`test_indicators.py`) still pass
* RSI test covers: known values, NaN prefix, period=1 edge, empty input, zero/negative prices
* Candle test covers: body_ratio, wick ratios, high==low → NaN, flat candles, all outputs in [0,1], length mismatch
* Momentum test covers: momentum, ROC, NaN prefix, zero price → NaN, negative price → NaN
* Rolling extensions test covers: rolling_max, rolling_min, rolling_mean, period=1, constant series, period > data length

**File Scope:**
```text
lib/tests/test_indicators_rsi.py
lib/tests/test_indicators_candle.py
lib/tests/test_indicators_momentum.py
lib/tests/test_indicators_rolling_extensions.py
```

**Acceptance Criteria:**
* `pytest lib/tests/ -q` passes with zero failures
* Import boundary test passes
* All pre-existing tests still pass

---

## 8. Combined Implementation Order

```text
  Batch batch_1: P1.A + P1.B + P1.C + P1.D  (all foundation, no cross-dependencies)
  Batch batch_2: P1.E                        (test gate — depends on all four)
```

All four indicator workspaces are independent foundations. They touch separate files with no overlap:
- P1.A: `lib/indicators/rsi.py`
- P1.B: `lib/indicators/candle.py`
- P1.C: `lib/indicators/momentum.py`
- P1.D: `lib/indicators/rolling.py` (existing file, appends new functions)

P1.A, P1.B, P1.C, and P1.D all touch `lib/indicators/__init__.py` (adding exports). This is the lone shared-file conflict. Use worktree isolation + integration queue serialization to resolve safely.

---

## 9. Definition of Done

`P1` is complete when ALL are true:

* [ ] `lib/indicators/rsi.py` exists with `rsi()` using Wilder's smoothed EMA
* [ ] `lib/indicators/candle.py` exists with `body_ratio`, `upper_wick_ratio`, `lower_wick_ratio`
* [ ] `lib/indicators/momentum.py` exists with `momentum` and `rate_of_change`
* [ ] `lib/indicators/rolling.py` has `rolling_max`, `rolling_min`, `rolling_mean`
* [ ] `lib/indicators/__init__.py` exports all new functions
* [ ] `lib/tests/test_indicators_rsi.py` exists and passes
* [ ] `lib/tests/test_indicators_candle.py` exists and passes
* [ ] `lib/tests/test_indicators_momentum.py` exists and passes
* [ ] `lib/tests/test_indicators_rolling_extensions.py` exists and passes
* [ ] `test_import_boundary.py` passes
* [ ] `test_indicators.py` passes (no regressions)
* [ ] All hard stops observed (no external deps, no v7/alphaforge/simulation imports, Wilder's EMA for RSI)
* [ ] DAG batch preview reviewed
* [ ] Integration queue status clean
* [ ] No forbidden commands or files used

---

## 10. Rollback Playbook

**Trigger conditions:**
* Any new test fails
* Import boundary test fails after additions
* Existing tests break
* __init__.py merge conflict during integration

**Rollback procedure:**
1. Remove `lib/indicators/rsi.py`, `lib/indicators/candle.py`, `lib/indicators/momentum.py`
2. Revert `lib/indicators/rolling.py` to pre-P1 state
3. Revert `lib/indicators/__init__.py` (remove new exports)
4. Remove four new test files
5. Run `pytest lib/tests/ -q` to confirm baseline passes
6. If integration queue blocked, create handoff artifact and stop

---

## 11. What Next Phase Inherits

`P2` inherits:

* All new indicator functions available in `lib.indicators`
* No regressions in existing indicator behavior
* Clean import boundary

---

# Part 2 — Agent Brief

## Mission

Add four pure-math indicator modules to `lib/indicators/`: RSI, candle geometry, momentum/ROC, and rolling min/max/mean. All functions must be pure transforms over price sequences with no external dependencies, no state, and no imports from v7, alphaforge, or simulation.

---

## Hard Requirements

1. RSI must use Wilder's smoothed EMA (same method as existing `lib/indicators/atr.py`).
2. No external dependencies (no pandas, no numpy, no ta-lib).
3. No imports from v7, alphaforge, or simulation.
4. All NaN/edge case behavior matches the spec in each workstream.
5. Existing tests must not break.
6. Import boundary test must pass.
7. Worktree isolation must be enabled for parallel workspaces.
8. Integration queue must serialize merges.
9. `git push` is forbidden.
10. Do not exceed worker cap (3).

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
* External dependency (pandas, numpy, ta-lib)
* Existing test regression
* RSI not using Wilder's EMA
* Division by zero not handled (high==low in candle, zero price in momentum)
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
    "tags": ["v7", "lib", "indicators", "p1"]
  },
  "intent": {
    "parallelism": 3,
    "safetyLevel": "strict",
    "conflictRisk": "medium",
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
      "external_dependency_detected",
      "rsi_not_wilder_ema",
      "division_by_zero_unhandled",
      "existing_test_regression",
      "worktree_path_escape",
      "integration_merge_without_validation",
      "watch_mode_validation",
      "git_push"
    ],
    "forbiddenCommands": [
      "git push", "git push --force", "rm -rf",
      "pip install pandas", "pip install numpy", "pip install ta-lib"
    ]
  },
  "workspaces": [
    {
      "id": "P1.A",
      "title": "RSI Indicator",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "conflictScope": ["lib/indicators/rsi.py", "lib/indicators/__init__.py", "lib/tests/test_indicators_rsi.py"],
      "worktree": { "required": true },
      "integration": { "queueRequired": true, "queuePriority": "critical" },
      "acceptanceCriteria": [
        "rsi(prices: Sequence[float], period: int = 14) -> list[float]",
        "Uses Wilder's smoothed EMA for average gain/loss",
        "First `period` values are NaN",
        "Empty input returns empty list",
        "period=1 returns all NaN",
        "RSI values in [0, 100] for valid inputs"
      ],
      "riskLevel": "low"
    },
    {
      "id": "P1.B",
      "title": "Candle Geometry",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "conflictScope": ["lib/indicators/candle.py", "lib/indicators/__init__.py", "lib/tests/test_indicators_candle.py"],
      "worktree": { "required": true },
      "integration": { "queueRequired": true, "queuePriority": "critical" },
      "acceptanceCriteria": [
        "body_ratio(opens, highs, lows, closes) -> list[float] with abs(close-open)/(high-low)",
        "upper_wick_ratio, lower_wick_ratio with correct formulas",
        "All ratios NaN when high==low",
        "All outputs in [0, 1] for valid non-flat candles",
        "Doji (open==close) returns body_ratio=0.0 not NaN",
        "Length mismatch raises ValueError"
      ],
      "riskLevel": "low"
    },
    {
      "id": "P1.C",
      "title": "Momentum / Rate of Change",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "conflictScope": ["lib/indicators/momentum.py", "lib/indicators/__init__.py", "lib/tests/test_indicators_momentum.py"],
      "worktree": { "required": true },
      "integration": { "queueRequired": true, "queuePriority": "critical" },
      "acceptanceCriteria": [
        "momentum(prices, period=10) returns (P_t - P_{t-period}) / P_{t-period}",
        "rate_of_change(prices, period=10) returns momentum * 100",
        "First `period` values are NaN",
        "Zero base price returns NaN",
        "Negative base price returns NaN",
        "Empty input returns empty list"
      ],
      "riskLevel": "low"
    },
    {
      "id": "P1.D",
      "title": "Rolling Extensions",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "conflictScope": ["lib/indicators/rolling.py", "lib/indicators/__init__.py", "lib/tests/test_indicators_rolling_extensions.py"],
      "worktree": { "required": true },
      "integration": { "queueRequired": true, "queuePriority": "critical" },
      "acceptanceCriteria": [
        "rolling_max([1,3,2,5,4], 3) returns [NaN, NaN, 3, 5, 5]",
        "rolling_min([5,3,4,1,2], 3) returns [NaN, NaN, 3, 1, 1]",
        "rolling_mean([1,2,3], 3) returns [NaN, NaN, 2.0]",
        "period=1 returns identical values",
        "Constant series returns constant values after NaN prefix",
        "Empty input returns empty list",
        "Existing rolling_std and rolling_apply unchanged"
      ],
      "riskLevel": "low"
    },
    {
      "id": "P1.E",
      "title": "Test Gates & Integration",
      "dependencies": ["P1.A", "P1.B", "P1.C", "P1.D"],
      "parallelGroup": "batch_2",
      "conflictScope": [
        "lib/tests/test_indicators_rsi.py",
        "lib/tests/test_indicators_candle.py",
        "lib/tests/test_indicators_momentum.py",
        "lib/tests/test_indicators_rolling_extensions.py"
      ],
      "worktree": { "required": true },
      "integration": { "queueRequired": true, "queuePriority": "high" },
      "acceptanceCriteria": [
        "pytest lib/tests/ -q passes with zero failures",
        "test_import_boundary.py passes",
        "test_indicators.py passes (no regressions)",
        "RSI test: known values, NaN prefix, period=1, empty, zero/negative prices",
        "Candle test: body_ratio, wick ratios, flat candle, all in [0,1], length mismatch",
        "Momentum test: momentum, ROC, NaN prefix, zero price, negative price",
        "Rolling test: max/min/mean, period=1, constant series, period > len"
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
  "phase": "P1",
  "title": "Indicators: RSI, Candle Geometry, Momentum, Rolling Extensions",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "primaryGoal": "Add RSI, candle geometry, momentum/ROC, and rolling min/max/mean to lib/indicators/",
  "projectName": "v7_engine_lib",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresIntegrationQueue": true,
  "safeEffectiveParallelismTarget": 2,
  "completionGate": "P1 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "P2"
}
```
