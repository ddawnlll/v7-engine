# S5 — Golden Tests, Replay Parity & Drift Guards

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `S5`
**One-line goal:** Create the validation gates that prevent simulation drift.
**Why now:** Without golden tests and parity checks, simulation semantics can drift silently. Import boundary enforcement prevents hidden simulators.
**Blast radius:** simulation/**, v7/docs/**, alphaforge/docs/**
**Rollback path:** Revert this phase's workspaces, restore previous compatible state, and rerun targeted + final validation.
**Execution class:** `implementation`
**Execution automation:** `enabled`
**Scale mode:** `stable_3`
**Safe parallelism target:** `2`
**Done when:** All workspaces pass acceptance criteria and phase JSON validates through Pi doctor.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `S5` |
| Title | `Golden Tests, Replay Parity & Drift Guards` |
| Status | `Planned` |
| Last updated | `2026-06-01` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Create the validation gates that prevent simulation drift.` |
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

---

## 2. Purpose

Without golden tests and parity checks, simulation semantics can drift silently. Import boundary enforcement prevents hidden simulators.

Golden fixtures pin known input/output pairs. Replay/paper/training parity tests verify cross-adapter consistency. Import boundary tests enforce dependency rules. Hidden simulator audit searches for forbidden patterns.

This phase uses `stable_3` scale-aware execution. The executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

---

## 3. What Carried Over — Must Stay Stable

* [ ] Runtime owns orchestration, execution, persistence, lifecycle, and hard safety.
* [ ] /simulation owns economic truth semantics and contracts.
* [ ] V7 runtime hosts/executes simulation operationally through stable contracts.
* [ ] AlphaForge consumes /simulation outputs through deterministic side-effect-free adapters.
* [ ] lib/ stays primitive; simulation is NOT in lib/.
* [ ] No hidden label-only or backtest-only simulator.
* [ ] No hidden deterministic veto; regime constraints are policy-layer only.
* [ ] NO_TRADE remains first-class action.
* [ ] Version bumps are explicit; no silent semantic drift.
* [ ] Monte Carlo is diagnostic; does not replace realized truth.
* [ ] Worktree isolation remains available when requested.
* [ ] Integration queue remains enabled when required.
* [ ] Global validation lock remains active for heavy validation.
* [ ] Completion gate hardening remains active.
* [ ] Merge conflicts produce handoff artifacts and do not mark the plan complete.
* [ ] The next plan does not start while the integration queue is dirty.
* [ ] `git push` remains forbidden.
* [ ] Raw destructive cleanup remains forbidden.
* [ ] Watch-mode validation remains forbidden.
* [ ] The ExecutionKernel remains the source of truth for state transitions; executors and actors emit events only.

---

## 4. Background / What Was Wrong

Golden fixtures pin known input/output pairs. Replay/paper/training parity tests verify cross-adapter consistency. Import boundary tests enforce dependency rules. Hidden simulator audit searches for forbidden patterns.

---

## 5. Current Failure State / Known Blockers

* Golden fixtures = not created.
* Stop/target precedence tests = not comprehensive.
* Cost correctness tests = not covering edge cases.
* Adapter side-effect isolation tests = not implemented.
* V7/AlphaForge parity tests = not implemented.
* Hidden simulator audit = not performed.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Worktree isolation violation | low | critical | Path scope checks; stop execution on escape |
| Integration queue merges unvalidated diff | medium | high | Require workspace validation and integration validation |
| Merge conflict blocks plan | medium | medium | Generate conflict handoff artifact and stop queue safely |
| Safe parallelism is lower than requested | medium | medium | Doctor warning; show bottleneck; use safe batch preview |
| Validation lock limits throughput | medium | medium | Scheduler reduces concurrency while heavy validation runs |

---

## 7. Workstreams

### S5.A — Golden Fixtures

**Goal:** 12+ golden fixtures: swing/short stop, scalp/time exit, aggressive/target, same-candle ambiguity, no-trade saved loss/missed opp, unresolved, invalidated, costs.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:**
* 12+ golden fixtures: swing/short stop, scalp/time exit, aggressive/target, same-candle ambiguity, no-trade saved loss/missed opp, unresolved, invalidated, costs.
* Golden tests produce exact match.
* Fixtures versioned with simulation_family_version.

**File Scope:**
```text
simulation/tests/golden/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
### S5.B — Stop/Target Precedence Tests

**Goal:** Stop before target verified across all modes.

**Dependencies:** S5.A
**Parallel Group:** batch_2
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:**
* Stop before target verified across all modes.
* Target before stop verified.
* Same-candle ambiguity stop-first verified.
* Time exit and horizon end verified.
* Exit prices match conservative values.

**File Scope:**
```text
simulation/tests/unit/exits/**
```

**Isolation & Parallelism Notes:**
* Depends on S5.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
### S5.C — Cost Correctness Tests

**Goal:** Fee reduces net R correctly.

**Dependencies:** S5.A
**Parallel Group:** batch_2
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:**
* Fee reduces net R correctly.
* Slippage reduces net R correctly.
* Gross R + costs = net R.
* Volatility-adjusted slippage verified.
* Zero-cost edge case handled.

**File Scope:**
```text
simulation/tests/unit/costs/**
```

**Isolation & Parallelism Notes:**
* Depends on S5.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
### S5.D — Adapter Side-Effect Isolation Tests

**Goal:** Training adapter no live side effects.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:**
* Training adapter no live side effects.
* Evaluation adapter no live side effects.
* Training output == Evaluation output for identical input.
* All adapters deterministic.

**File Scope:**
```text
simulation/tests/integration/**
simulation/tests/unit/adapters/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
### S5.E — V7/AlphaForge Parity Tests

**Goal:** Paper == replay == training == evaluation for identical input.

**Dependencies:** S5.D
**Parallel Group:** batch_3
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:**
* Paper == replay == training == evaluation for identical input.
* V7-hosted simulation produces same outputs as direct engine calls.

**File Scope:**
```text
simulation/tests/integration/**
```

**Isolation & Parallelism Notes:**
* Depends on S5.D for foundation.
* Expected batch: batch_3
* Worktree isolation required.
### S5.F — Hidden Simulator Audit

**Goal:** No 'label-only simulator' in alphaforge or v7.

**Dependencies:** S5.D, S5.E
**Parallel Group:** batch_3
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:**
* No 'label-only simulator' in alphaforge or v7.
* No 'backtest-only simulator'.
* No simulation truth in lib.
* No TradeOutcome with alternative sim logic.
* Audit passable as CI gate.

**File Scope:**
```text
simulation/tests/audit/**
```

**Isolation & Parallelism Notes:**
* Depends on S5.D, S5.E for foundation.
* Expected batch: batch_3
* Worktree isolation required.
### S5.G — Import Boundary Enforcement

**Goal:** simulation/ does not import v7/** (HARD STOP).

**Dependencies:** S5.F
**Parallel Group:** batch_3
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:**
* simulation/ does not import v7/** (HARD STOP).
* simulation/ does not import alphaforge/** (HARD STOP).
* lib/ does not import simulation/** (HARD STOP).
* alphaforge/ does not contain hidden simulation truth.

**File Scope:**
```text
simulation/tests/import_boundary/**
lib/tests/test_import_boundary.py
```

**Isolation & Parallelism Notes:**
* Depends on S5.F for foundation.
* Expected batch: batch_3
* Worktree isolation required.

---

## 8. Combined Implementation Order

```text
  Batch batch_1: S5.A + S5.D
  Batch batch_2: S5.B + S5.C
  Batch batch_3: S5.E + S5.F + S5.G
```

---

## 9. Definition of Done

`S5` is complete when ALL are true:

* [ ] 12+ golden fixtures: swing/short stop, scalp/time exit, aggressive/target, same-candle ambiguity, no-trade saved loss/missed opp, unresolved, invalidated, costs.
* [ ] Stop before target verified across all modes.
* [ ] Fee reduces net R correctly.
* [ ] Training adapter no live side effects.
* [ ] Paper == replay == training == evaluation for identical input.
* [ ] No 'label-only simulator' in alphaforge or v7.
* [ ] simulation/ does not import v7/** (HARD STOP).
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation is valid for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] No forbidden commands or files were used.
* [ ] Validation gates passed.

---

## 10. Rollback Playbook

**Trigger conditions:** Worktree isolation violation, integration queue corruption, merge conflicts not detected.
**Procedure:** 1. Set scale to stable_3. 2. Reduce workers to 3. 3. Pause integration queue. 4. Preserve .pi/worktrees for debugging. 5. Revert phase commits independently.

---

## 11. What Next Phase Inherits

`S6` inherits: Execution contract with worktree mode, scale-mode validation rules, integration queue requirements, workspace metadata, and review hardening invariants.

---

# Part 2 — Agent Brief

## Mission

Implement `S5` — Create the validation gates that prevent simulation drift.

The agent must optimize for safe parallelism, not maximum concurrency.


**Authority context:** See [`/simulation/docs/ai_summary.md`](../ai_summary.md) for the complete system synthesis before implementing this phase.
## Hard Requirements

1. All S5 workstreams must pass acceptance criteria.
2. Worktree isolation must be enabled for parallel workspaces.
3. Integration queue must serialize merges.
4. Global validation lock active for heavy validation.
5. Watch-mode validation forbidden.
6. `git push` forbidden.
7. Raw destructive cleanup forbidden.
8. Do not exceed worker cap (3).
9. Do not merge unvalidated workspace output.
10. Do not mark plan complete if integration validation fails.

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


# Part 2.5 — v4 ExecutionKernel Doctrine

## 2.5.1 Single Authority Model

v4 replaces executor-owned execution state with an ExecutionKernel model. All actors emit events.
WorkspaceAttemptController mutates attempt state. PlanSupervisor mutates plan state.
PostgreSQL stores authoritative runtime truth.

## 2.5.2 ExecutionKernel Components

| Component | Responsibility | May mutate execution state? |
|---|---|---:|
| ExecutionAdmissionGate | Authorize or reject execution requests before runtime starts | No |
| ExecutionProfileDeriver | Convert intent to required mechanisms | No |
| PlanSupervisor | Own plan FSM, slot tokens, completion predicate, final validation | Yes, plan state only |
| WorkspaceAttemptController | Own attempt FSM, retries, terminalization, handoff creation | Yes, attempt state only |
| StateStoreWriter | Commit transitions with authority token | Yes, through token only |
| AttemptEventJournal | Append versioned event records | No state mutation by itself |
| DeadlineWatchdog | Detect expired attempts and emit events | No |
| ExecutorActor | Run LLM/tools/bash for an attempt | No |
| ValidationActor | Run validation with deadlines and process containment | No |
| GitRunner | Serialize Git repo mutations | No attempt state mutation |

## 2.5.3 Attempt FSM Doctrine

QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
Failure: RUNNING+timeout -> TIMED_OUT, critical -> FAILED_FINAL
Terminal: SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, TIMED_OUT, HANDOFF_REQUIRED

## 2.5.4 PostgreSQL Truth Doctrine

Runtime truth is PostgreSQL. JSON fallback is forbidden in production.

## 2.5.5 Intent-Driven Plan Doctrine

v4 authors express what they want, not the low-level mechanism matrix.


---

# Part 3 — Machine-Readable Execution Contract

```json
{
  "contractVersion": "4.1.1",
  "templateVersion": "4.1.1",
  "legacyCompatibility": {
    "v3EnvelopePreserved": true,
    "legacyValidatorMode": "v3_compatible_extensions",
    "fallbackContractVersionForLegacyParser": "3.0.0",
    "legacyMechanismFieldsAreHints": true,
    "unknownV4FieldsPolicy": "ignore_for_read_only_legacy_consumers_reject_for_execution_without_v4_validator"
  },
  "executionClass": "implementation",
  "executionBackend": "postgres",
  "project": {
    "name": "v7_engine_simulation",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "simulation",
      "s5"
    ]
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
    "generatedBy": "ExecutionProfileDeriver",
    "deriverVersion": "4.1.1",
    "readOnly": true,
    "isolationMode": "worktree",
    "worktreeRequired": true,
    "patchIsolationRequired": false,
    "patchCoordinatorRequired": false,
    "repositoryMutationAuthority": "worktree_integration",
    "patchApplyLanes": 0,
    "maxCodegenWorkers": 3,
    "integrationQueueRequired": true,
    "gitRunnerQueueRequired": true,
    "validationLanesRequired": true,
    "attemptScopedArtifactsRequired": true,
    "deadlineWatchdogRequired": true,
    "admissionGateMode": "strict",
    "writeSetDriftPolicy": "reject_or_handoff"
  },
  "persistence": {
    "authoritativeBackend": "postgres",
    "jsonRuntimeFallbackAllowed": false,
    "eventJournalBackend": "postgres",
    "transitionBackend": "postgres",
    "controllerInboxBackend": "postgres",
    "handoffQueueBackend": "postgres",
    "rawLogsBackend": "filesystem",
    "artifactIndexBackend": "postgres",
    "debugExportAllowed": true
  },
  "executionAutomation": {
    "autonomousExecutionEnabled": true,
    "agentMayMutateRepo": true,
    "agentMayRunCommands": true,
    "manualPatchApplicationRequired": false,
    "humanApprovalRequiredForEveryPatch": false
  },
  "executionKernel": {
    "enabled": true,
    "stateAuthority": "workspace_attempt_controller",
    "planAuthority": "plan_supervisor",
    "stateAuthorityTokenRequired": true,
    "admissionGateRequired": true,
    "eventSourcedAttempts": true,
    "attemptEventJournalRequired": true,
    "directStateMutationForbidden": true,
    "actorsEmitEventsOnly": true,
    "policiesSuggestOnly": true,
    "brainWorkersReadOnly": true,
    "retryRequiresTerminalAttempt": true,
    "everyNonTerminalStateHasDeadline": true,
    "controllerSerializesDecisionsNotWork": true,
    "controllerLeadership": {
      "required": true,
      "mode": "postgres_advisory_lock_plus_expected_version",
      "transitionRequiresExpectedVersion": true,
      "onVersionConflict": "reject_and_emit_controller_conflict"
    }
  },
  "safety": {
    "hardStops": [
      "secrets",
      "destructive_ops",
      "forbidden_files",
      "budget_violations",
      "dependency_cycles",
      "unapproved_parallelism_review",
      "invalid_dependency_patch",
      "worktree_path_escape",
      "raw_destructive_cleanup",
      "integration_merge_without_validation",
      "integration_validation_failure",
      "merge_conflict_without_handoff",
      "unsafe_scale_mode",
      "queue_next_plan_while_integration_dirty",
      "scale_mode_approval_stale",
      "worktree_required_for_requested_parallelism",
      "watch_mode_validation",
      "execution_without_dry_run",
      "execution_without_approval",
      "optimizer_patch_without_approval",
      "autonomous_execution_requested_during_repair_mode",
      "agent_repo_mutation_requested_during_manual_repair",
      "agent_command_execution_requested_during_manual_repair",
      "scheduler_enabled_before_executor_isolation_gate",
      "stable_6_requested_before_promotion_gates",
      "llm_call_without_provider_timeout",
      "llm_stream_without_idle_watchdog",
      "validation_command_without_timeout",
      "validation_process_without_process_group",
      "validation_watch_or_dev_server_command",
      "git_lock_bypass_detected",
      "state_store_write_without_serialization",
      "workspace_patch_without_human_approval",
      "repair_workspace_missing_rollback",
      "repair_workspace_missing_targeted_validation",
      "dogfood_required_but_missing",
      "promotion_gate_failed_or_missing",
      "direct_attempt_state_mutation_detected",
      "executor_mutates_attempt_state",
      "state_transition_outside_controller",
      "non_terminal_state_without_deadline",
      "deadline_watchdog_unavailable",
      "lock_held_across_external_await",
      "nested_resource_lock_detected",
      "execution_entrypoint_bypasses_admission_gate",
      "attempt_without_event_journal",
      "postgres_unavailable_for_authoritative_runtime",
      "json_runtime_fallback_detected",
      "dual_authoritative_state_detected",
      "transition_without_expected_version",
      "handoff_required_without_queue_item"
    ],
    "forbiddenCommands": [
      "git push",
      "git push --force",
      "rm -rf",
      "npm publish",
      "terraform destroy",
      "kubectl delete",
      "git reset --hard",
      "git clean -fd"
    ],
    "forbiddenFiles": [
      ".env*",
      "**/*.pem",
      "**/*.key",
      "**/*.p12",
      "**/*.pfx",
      "**/id_rsa",
      "**/credentials/**",
      "**/secrets/**"
    ]
  },
  "workspaces": [
    {
      "id": "S5.A",
      "title": "Golden Fixtures",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
      "manualApplicationRequired": false,
      "humanApprovalRequired": false,
      "autonomousExecutionAllowed": true,
      "rollbackRequired": true,
      "targetedValidationRequired": true,
      "parallelism": {
        "expectedBatch": "batch_1",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "simulation/tests/golden/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation."
      },
      "worktree": {
        "required": true,
        "isolationMode": "worktree",
        "cleanupPolicy": "quarantine_on_failure"
      },
      "integration": {
        "queueRequired": true,
        "requiresWorkspaceValidation": true,
        "requiresIntegrationValidation": true,
        "conflictHandoffRequired": true,
        "queuePriority": "critical"
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true,
        "timeoutMs": 600000,
        "managedRunnerRequired": true,
        "processGroupRequired": true,
        "killTreeOnTimeout": true,
        "maxOutputBytes": 52428800
      },
      "allowedFiles": [
        "simulation/tests/golden/**"
      ],
      "forbiddenFiles": [
        ".env*",
        "**/*.pem",
        "**/*.key",
        "**/*.p12",
        "**/*.pfx",
        "**/id_rsa",
        "**/credentials/**",
        "**/secrets/**"
      ],
      "acceptanceCriteria": [
        "12+ golden fixtures: swing/short stop, scalp/time exit, aggressive/target, same-candle ambiguity, no-trade saved loss/missed opp, unresolved, invalidated, costs.",
        "Golden tests produce exact match.",
        "Fixtures versioned with simulation_family_version."
      ],
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "simulation/tests/golden/**"
        ],
        "cannotEdit": [
          ".env*",
          "**/*.pem",
          "**/*.key",
          "**/*.p12",
          "**/*.pfx",
          "**/id_rsa",
          "**/credentials/**",
          "**/secrets/**"
        ],
        "canRun": [
          "pytest",
          "python",
          "ruff",
          "mypy"
        ],
        "cannotRun": [
          "git push",
          "git push --force",
          "rm -rf",
          "npm publish",
          "terraform destroy",
          "kubectl delete",
          "git reset --hard",
          "git clean -fd"
        ]
      }
    },
    {
      "id": "S5.B",
      "title": "Stop/Target Precedence Tests",
      "dependencies": [
        "S5.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on S5.A for foundation.",
      "manualApplicationRequired": false,
      "humanApprovalRequired": false,
      "autonomousExecutionAllowed": true,
      "rollbackRequired": true,
      "targetedValidationRequired": true,
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "simulation/tests/unit/exits/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation."
      },
      "worktree": {
        "required": true,
        "isolationMode": "worktree",
        "cleanupPolicy": "quarantine_on_failure"
      },
      "integration": {
        "queueRequired": true,
        "requiresWorkspaceValidation": true,
        "requiresIntegrationValidation": true,
        "conflictHandoffRequired": true,
        "queuePriority": "critical"
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true,
        "timeoutMs": 600000,
        "managedRunnerRequired": true,
        "processGroupRequired": true,
        "killTreeOnTimeout": true,
        "maxOutputBytes": 52428800
      },
      "allowedFiles": [
        "simulation/tests/unit/exits/**"
      ],
      "forbiddenFiles": [
        ".env*",
        "**/*.pem",
        "**/*.key",
        "**/*.p12",
        "**/*.pfx",
        "**/id_rsa",
        "**/credentials/**",
        "**/secrets/**"
      ],
      "acceptanceCriteria": [
        "Stop before target verified across all modes.",
        "Target before stop verified.",
        "Same-candle ambiguity stop-first verified.",
        "Time exit and horizon end verified.",
        "Exit prices match conservative values."
      ],
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "simulation/tests/unit/exits/**"
        ],
        "cannotEdit": [
          ".env*",
          "**/*.pem",
          "**/*.key",
          "**/*.p12",
          "**/*.pfx",
          "**/id_rsa",
          "**/credentials/**",
          "**/secrets/**"
        ],
        "canRun": [
          "pytest",
          "python",
          "ruff",
          "mypy"
        ],
        "cannotRun": [
          "git push",
          "git push --force",
          "rm -rf",
          "npm publish",
          "terraform destroy",
          "kubectl delete",
          "git reset --hard",
          "git clean -fd"
        ]
      }
    },
    {
      "id": "S5.C",
      "title": "Cost Correctness Tests",
      "dependencies": [
        "S5.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on S5.A for foundation.",
      "manualApplicationRequired": false,
      "humanApprovalRequired": false,
      "autonomousExecutionAllowed": true,
      "rollbackRequired": true,
      "targetedValidationRequired": true,
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "simulation/tests/unit/costs/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation."
      },
      "worktree": {
        "required": true,
        "isolationMode": "worktree",
        "cleanupPolicy": "quarantine_on_failure"
      },
      "integration": {
        "queueRequired": true,
        "requiresWorkspaceValidation": true,
        "requiresIntegrationValidation": true,
        "conflictHandoffRequired": true,
        "queuePriority": "critical"
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true,
        "timeoutMs": 600000,
        "managedRunnerRequired": true,
        "processGroupRequired": true,
        "killTreeOnTimeout": true,
        "maxOutputBytes": 52428800
      },
      "allowedFiles": [
        "simulation/tests/unit/costs/**"
      ],
      "forbiddenFiles": [
        ".env*",
        "**/*.pem",
        "**/*.key",
        "**/*.p12",
        "**/*.pfx",
        "**/id_rsa",
        "**/credentials/**",
        "**/secrets/**"
      ],
      "acceptanceCriteria": [
        "Fee reduces net R correctly.",
        "Slippage reduces net R correctly.",
        "Gross R + costs = net R.",
        "Volatility-adjusted slippage verified.",
        "Zero-cost edge case handled."
      ],
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "simulation/tests/unit/costs/**"
        ],
        "cannotEdit": [
          ".env*",
          "**/*.pem",
          "**/*.key",
          "**/*.p12",
          "**/*.pfx",
          "**/id_rsa",
          "**/credentials/**",
          "**/secrets/**"
        ],
        "canRun": [
          "pytest",
          "python",
          "ruff",
          "mypy"
        ],
        "cannotRun": [
          "git push",
          "git push --force",
          "rm -rf",
          "npm publish",
          "terraform destroy",
          "kubectl delete",
          "git reset --hard",
          "git clean -fd"
        ]
      }
    },
    {
      "id": "S5.D",
      "title": "Adapter Side-Effect Isolation Tests",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
      "manualApplicationRequired": false,
      "humanApprovalRequired": false,
      "autonomousExecutionAllowed": true,
      "rollbackRequired": true,
      "targetedValidationRequired": true,
      "parallelism": {
        "expectedBatch": "batch_1",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "simulation/tests/integration/**",
          "simulation/tests/unit/adapters/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation."
      },
      "worktree": {
        "required": true,
        "isolationMode": "worktree",
        "cleanupPolicy": "quarantine_on_failure"
      },
      "integration": {
        "queueRequired": true,
        "requiresWorkspaceValidation": true,
        "requiresIntegrationValidation": true,
        "conflictHandoffRequired": true,
        "queuePriority": "critical"
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true,
        "timeoutMs": 600000,
        "managedRunnerRequired": true,
        "processGroupRequired": true,
        "killTreeOnTimeout": true,
        "maxOutputBytes": 52428800
      },
      "allowedFiles": [
        "simulation/tests/integration/**",
        "simulation/tests/unit/adapters/**"
      ],
      "forbiddenFiles": [
        ".env*",
        "**/*.pem",
        "**/*.key",
        "**/*.p12",
        "**/*.pfx",
        "**/id_rsa",
        "**/credentials/**",
        "**/secrets/**"
      ],
      "acceptanceCriteria": [
        "Training adapter no live side effects.",
        "Evaluation adapter no live side effects.",
        "Training output == Evaluation output for identical input.",
        "All adapters deterministic."
      ],
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "simulation/tests/integration/**",
          "simulation/tests/unit/adapters/**"
        ],
        "cannotEdit": [
          ".env*",
          "**/*.pem",
          "**/*.key",
          "**/*.p12",
          "**/*.pfx",
          "**/id_rsa",
          "**/credentials/**",
          "**/secrets/**"
        ],
        "canRun": [
          "pytest",
          "python",
          "ruff",
          "mypy"
        ],
        "cannotRun": [
          "git push",
          "git push --force",
          "rm -rf",
          "npm publish",
          "terraform destroy",
          "kubectl delete",
          "git reset --hard",
          "git clean -fd"
        ]
      }
    },
    {
      "id": "S5.E",
      "title": "V7/AlphaForge Parity Tests",
      "dependencies": [
        "S5.D"
      ],
      "parallelGroup": "batch_3",
      "dependencyReason": "Depends on S5.D for foundation.",
      "manualApplicationRequired": false,
      "humanApprovalRequired": false,
      "autonomousExecutionAllowed": true,
      "rollbackRequired": true,
      "targetedValidationRequired": true,
      "parallelism": {
        "expectedBatch": "batch_3",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "simulation/tests/integration/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation."
      },
      "worktree": {
        "required": true,
        "isolationMode": "worktree",
        "cleanupPolicy": "quarantine_on_failure"
      },
      "integration": {
        "queueRequired": true,
        "requiresWorkspaceValidation": true,
        "requiresIntegrationValidation": true,
        "conflictHandoffRequired": true,
        "queuePriority": "critical"
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true,
        "timeoutMs": 600000,
        "managedRunnerRequired": true,
        "processGroupRequired": true,
        "killTreeOnTimeout": true,
        "maxOutputBytes": 52428800
      },
      "allowedFiles": [
        "simulation/tests/integration/**"
      ],
      "forbiddenFiles": [
        ".env*",
        "**/*.pem",
        "**/*.key",
        "**/*.p12",
        "**/*.pfx",
        "**/id_rsa",
        "**/credentials/**",
        "**/secrets/**"
      ],
      "acceptanceCriteria": [
        "Paper == replay == training == evaluation for identical input.",
        "V7-hosted simulation produces same outputs as direct engine calls."
      ],
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "simulation/tests/integration/**"
        ],
        "cannotEdit": [
          ".env*",
          "**/*.pem",
          "**/*.key",
          "**/*.p12",
          "**/*.pfx",
          "**/id_rsa",
          "**/credentials/**",
          "**/secrets/**"
        ],
        "canRun": [
          "pytest",
          "python",
          "ruff",
          "mypy"
        ],
        "cannotRun": [
          "git push",
          "git push --force",
          "rm -rf",
          "npm publish",
          "terraform destroy",
          "kubectl delete",
          "git reset --hard",
          "git clean -fd"
        ]
      }
    },
    {
      "id": "S5.F",
      "title": "Hidden Simulator Audit",
      "dependencies": [
        "S5.D",
        "S5.E"
      ],
      "parallelGroup": "batch_3",
      "dependencyReason": "Depends on S5.D, S5.E for foundation.",
      "manualApplicationRequired": false,
      "humanApprovalRequired": false,
      "autonomousExecutionAllowed": true,
      "rollbackRequired": true,
      "targetedValidationRequired": true,
      "parallelism": {
        "expectedBatch": "batch_3",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "simulation/tests/audit/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation."
      },
      "worktree": {
        "required": true,
        "isolationMode": "worktree",
        "cleanupPolicy": "quarantine_on_failure"
      },
      "integration": {
        "queueRequired": true,
        "requiresWorkspaceValidation": true,
        "requiresIntegrationValidation": true,
        "conflictHandoffRequired": true,
        "queuePriority": "critical"
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true,
        "timeoutMs": 600000,
        "managedRunnerRequired": true,
        "processGroupRequired": true,
        "killTreeOnTimeout": true,
        "maxOutputBytes": 52428800
      },
      "allowedFiles": [
        "simulation/tests/audit/**"
      ],
      "forbiddenFiles": [
        ".env*",
        "**/*.pem",
        "**/*.key",
        "**/*.p12",
        "**/*.pfx",
        "**/id_rsa",
        "**/credentials/**",
        "**/secrets/**"
      ],
      "acceptanceCriteria": [
        "No 'label-only simulator' in alphaforge or v7.",
        "No 'backtest-only simulator'.",
        "No simulation truth in lib.",
        "No TradeOutcome with alternative sim logic.",
        "Audit passable as CI gate."
      ],
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "simulation/tests/audit/**"
        ],
        "cannotEdit": [
          ".env*",
          "**/*.pem",
          "**/*.key",
          "**/*.p12",
          "**/*.pfx",
          "**/id_rsa",
          "**/credentials/**",
          "**/secrets/**"
        ],
        "canRun": [
          "pytest",
          "python",
          "ruff",
          "mypy"
        ],
        "cannotRun": [
          "git push",
          "git push --force",
          "rm -rf",
          "npm publish",
          "terraform destroy",
          "kubectl delete",
          "git reset --hard",
          "git clean -fd"
        ]
      }
    },
    {
      "id": "S5.G",
      "title": "Import Boundary Enforcement",
      "dependencies": [
        "S5.F"
      ],
      "parallelGroup": "batch_3",
      "dependencyReason": "Depends on S5.F for foundation.",
      "manualApplicationRequired": false,
      "humanApprovalRequired": false,
      "autonomousExecutionAllowed": true,
      "rollbackRequired": true,
      "targetedValidationRequired": true,
      "parallelism": {
        "expectedBatch": "batch_3",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "simulation/tests/import_boundary/**",
          "lib/tests/test_import_boundary.py"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation."
      },
      "worktree": {
        "required": true,
        "isolationMode": "worktree",
        "cleanupPolicy": "quarantine_on_failure"
      },
      "integration": {
        "queueRequired": true,
        "requiresWorkspaceValidation": true,
        "requiresIntegrationValidation": true,
        "conflictHandoffRequired": true,
        "queuePriority": "critical"
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true,
        "timeoutMs": 600000,
        "managedRunnerRequired": true,
        "processGroupRequired": true,
        "killTreeOnTimeout": true,
        "maxOutputBytes": 52428800
      },
      "allowedFiles": [
        "simulation/tests/import_boundary/**",
        "lib/tests/test_import_boundary.py"
      ],
      "forbiddenFiles": [
        ".env*",
        "**/*.pem",
        "**/*.key",
        "**/*.p12",
        "**/*.pfx",
        "**/id_rsa",
        "**/credentials/**",
        "**/secrets/**"
      ],
      "acceptanceCriteria": [
        "simulation/ does not import v7/** (HARD STOP).",
        "simulation/ does not import alphaforge/** (HARD STOP).",
        "lib/ does not import simulation/** (HARD STOP).",
        "alphaforge/ does not contain hidden simulation truth."
      ],
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "simulation/tests/import_boundary/**",
          "lib/tests/test_import_boundary.py"
        ],
        "cannotEdit": [
          ".env*",
          "**/*.pem",
          "**/*.key",
          "**/*.p12",
          "**/*.pfx",
          "**/id_rsa",
          "**/credentials/**",
          "**/secrets/**"
        ],
        "canRun": [
          "pytest",
          "python",
          "ruff",
          "mypy"
        ],
        "cannotRun": [
          "git push",
          "git push --force",
          "rm -rf",
          "npm publish",
          "terraform destroy",
          "kubectl delete",
          "git reset --hard",
          "git clean -fd"
        ]
      }
    }
  ]
}
```

---

# Part 4 — Machine-Readable Summary

```json
{
  "contractVersion": "4.1.1",
  "phase": "S5",
  "title": "Golden Tests, Replay Parity & Drift Guards",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "schedulerRuntimeUse": "enabled",
  "primaryGoal": "Create the validation gates that prevent simulation drift.",
  "projectName": "v7_engine_simulation",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresIntegrationQueue": true,
  "safeEffectiveParallelismTarget": 2,
  "completionGate": "S5 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "S6"
}
```
