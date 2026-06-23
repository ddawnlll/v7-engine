# V7 AlphaForge XGB — Combined Phase Plans

> **⚠️ SUPERSEDED — HISTORICAL REFERENCE ONLY**
> This combined document (578KB) was the pre-P0.8B combined phase plans reference. It has been superseded by `alphaforge/docs/phase_plan.md`. Do not use this document for current phase planning. See `alphaforge/docs/phase_plan.md` for the canonical phase plan.
>
> Superseded by: P0.8B Authority Lock (2026-06-18)
> Canonical entry: `alphaforge/docs/phase_plan.md`

Generated from individual v4.1.1 template-based phase plan files.

---

<!-- SOURCE: phase_plans/P0_5__shared_lib_foundation.md -->

# P0.5 — Shared Lib Foundation

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P0.5`  
**One-line goal:** Focused lib/ directory with shared Binance client, indicators, costs, and time utilities.  
**Why now:** Shared primitives with nearly identical usage between v7 and alphaforge must be extracted before phase work begins.  
**Blast radius:** src/v7/alpha/**, tests/v7/alpha/**, configs/v7/alpha/**, docs/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Execution class:** `implementation`  
**Execution automation:** `enabled`  
**Scale mode:** `stable_3`  
**Safe parallelism target:** `2`  
**Done when:** All workspaces pass acceptance criteria and phase JSON validates through Pi doctor.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P0.5` |
| Title | `Shared Lib Foundation` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Focused lib/ directory with shared Binance client, indicators, costs, and time utilities.` |
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

Shared primitives with nearly identical usage between v7 and alphaforge must be extracted before phase work begins.

Both v7 and alphaforge need market data, indicators, cost models, and time utilities. A focused lib/ prevents duplication without becoming a shared-everything dumping ground.

This phase uses `stable_3` scale-aware execution. The executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

---

## 3. What Carried Over — Must Stay Stable

* [ ] Runtime owns orchestration, execution, persistence, lifecycle, and hard safety.
* [ ] Model owns alpha evidence only.
* [ ] Simulation truth defines labels and evaluation.
* [ ] No hidden deterministic veto or hidden fallback.
* [ ] NO_TRADE remains first-class.
* [ ] Features are canonical-state only.
* [ ] Labels are mode-specific.
* [ ] Datasets are mode-specific and temporally split.
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

Both v7 and alphaforge need market data, indicators, cost models, and time utilities. A focused lib/ prevents duplication without becoming a shared-everything dumping ground.

---

## 5. Current Failure State / Known Blockers

* `lib/` = not implemented.
* `lib/market_data/` = not implemented.
* `lib/indicators/` = not implemented.
* `lib/costs/` = not implemented.
* `lib/time/` = not implemented.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Worktree isolation violation | low | critical | Path scope checks; stop execution on escape |
| Integration queue merges unvalidated diff | medium | high | Require workspace validation and integration validation |
| Merge conflict blocks plan | medium | medium | Generate conflict handoff artifact and stop queue safely |
| Safe parallelism is lower than requested | medium | medium | Doctor warning; show bottleneck; use safe batch preview |
| Validation lock limits throughput | medium | medium | Scheduler reduces concurrency while heavy validation runs |
| High-risk workspace failure | medium | high | Rollback path defined; manual review gating |

---

## 7. Workstreams

### P05.A — Market Data Service

**Goal:** Binance HTTP client, klines/funding service, standard schema exist.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** medium
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Binance HTTP client, klines/funding service, standard schema exist.
* Direct Binance API calls from v7/ or alphaforge/ are caught by hard stop.

**File Scope:**
```text
lib/market_data/**
tests/lib/market_data/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P05.B — Indicators & Costs

**Goal:** ATR, returns, volatility, rolling window indicators exist.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** medium
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* ATR, returns, volatility, rolling window indicators exist.
* Fee % and slippage estimation exist.
* No /simulation truth or regime logic in lib/. /simulation is a top-level authority.

**File Scope:**
```text
lib/indicators/**
lib/costs/**
tests/lib/indicators/**
tests/lib/costs/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P05.C — Time Utilities

**Goal:** Interval conversion and fold generation exist.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** low
**Queue Priority:** high
**Can run with:** None

**Requirements:
* Interval conversion and fold generation exist.

**File Scope:**
```text
lib/time/**
tests/lib/time/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P05.D — Lib Boundary Tests

**Goal:** Import boundary violations are caught.

**Dependencies:** P05.A, P05.B, P05.C
**Parallel Group:** batch_2
**Risk Level:** high
**Queue Priority:** high
**Can run with:** None

**Requirements:
* Import boundary violations are caught.
* lib/ must not import v7.* or alphaforge.*.
* No shared_everything_mistake (regime/risk/IO/adapters in lib/).

**File Scope:**
```text
tests/lib/**
```

**Isolation & Parallelism Notes:**
* Depends on P05.A, P05.B, P05.C for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.


---

## 8. Combined Implementation Order

```text
  Batch batch_1: P05.A + P05.B + P05.C
  Batch batch_2: P05.D
```

The dependency graph dictates that foundation workspaces run first, followed by parallel batches where dependencies permit. The DAG batch preview and safe batch preview may differ because of file overlap, validation lock pressure, or integration queue serialization.

---

## 9. Definition of Done

`P0.5` is complete when ALL are true:

* [ ] Binance HTTP client, klines/funding service, standard schema exist.
* [ ] ATR, returns, volatility, rolling window indicators exist.
* [ ] Interval conversion and fold generation exist.
* [ ] Import boundary violations are caught.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation is valid for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] No forbidden commands or files were used.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Validation planner misses a required failure.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Disable worktree mode only if safe fallback is required.
4. Pause or disable integration queue processing.
5. Preserve `.pi/worktrees/{planExecId}/` for debugging.
6. Fall back to shared-working-tree execution if explicitly allowed.
7. Keep dashboard telemetry read-only if safe.
8. Revert phase commits independently if needed.

---

## 11. What Next Phase Inherits

`P1` inherits:

* `P0.5` execution contract with worktree mode awareness.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Workspace-level parallelism/isolation/integration/validation metadata.
* Review hardening invariants: Shared lib authority, Import boundary enforcement

---

# Part 2 — Agent Brief

## Mission

Implement `P0.5` — Focused lib/ directory with shared Binance client, indicators, costs, and time utilities.

The agent must optimize for safe parallelism, not maximum concurrency. Higher worker counts are allowed only when scale-mode readiness passes and the executor can preserve correctness through worktree isolation, integration queue, validation locks, and completion gates.



---

## Hard Requirements

1. All P0.5 workstreams must pass acceptance criteria.
2. Worktree isolation must be enabled for parallel workspaces.
3. Integration queue must serialize merges.
4. Global validation lock must be active for heavy validation.
5. Watch-mode validation is forbidden.
6. `git push` is forbidden.
7. Raw destructive cleanup is forbidden.
8. Do not exceed selected scale-mode worker cap (3).
9. Do not merge workspace output without passed workspace validation.
10. Do not mark the plan complete if integration validation fails.
11. Do not treat merge conflict as ordinary worker failure.
12. Do not start the next plan while integration queue state is dirty.

---

## Execution Policies

```yaml
repair_modes:
  manual_0: autonomous_execution_allowed: false, agent_may_mutate_repo: false
  stable_3: autonomous_execution_allowed: true,  agent_may_mutate_repo: true

execution_automation:
  autonomous_execution_enabled: true
  agent_may_mutate_repo: true
  agent_may_run_commands: true
  manual_patch_application_required: false
  human_approval_required_for_every_patch: false

bounded_liveness:
  no_indefinite_waits: true
  llm_provider_timeout_required: true
  llm_stream_idle_watchdog_required: true
  validation_timeout_required: true
  process_tree_kill_required: true
  git_lock_bypass_forbidden: true
  state_write_serialization_required: true

scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
  worktree_required: true
  integration_queue_required: true

validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true

queue_optimization:
  enabled_by_default: true
  default_strategy: priority_then_fifo
  priority_levels: [critical, high, normal, low]
```

---

## Safety Stops

* Dependency cycles
* Invalid dependency patches
* Worktree path escaping `.pi/worktrees`
* Integration merge without passed workspace validation
* Validation failure
* Merge conflict without handoff artifact
* Unsafe scale mode
* Queue starting next plan while integration queue is dirty
* Forbidden file access
* Secrets access
* `git push`
* Watch-mode validation
* `autonomous_execution_requested_during_repair_mode`
* `agent_repo_mutation_requested_during_manual_repair`
* `scheduler_enabled_before_executor_isolation_gate`
* `llm_call_without_provider_timeout`
* `validation_command_without_timeout`
* `git_lock_bypass_detected`
* `state_store_write_without_serialization`
* `workspace_patch_without_human_approval`
* `promotion_gate_failed_or_missing`


# Part 2.5 — v4 ExecutionKernel Doctrine

## 2.5.1 Single Authority Model

v4 replaces the previous executor-owned or multi-component execution state model with an ExecutionKernel model.

```text
Before v4:
  Scheduler, executor, validation runner, retry router, cleanup, lease monitor,
  diagnostics, and brain workers could each influence or write partial execution truth.

After v4:
  All actors emit events.
  WorkspaceAttemptController mutates attempt state.
  PlanSupervisor mutates plan state.
  PostgreSQL stores authoritative runtime truth.
```

## 2.5.2 ExecutionKernel Components

| Component | Responsibility | May mutate execution state? |
|---|---|---:|
| `ExecutionAdmissionGate` | Authorize or reject execution requests before runtime starts | No |
| `ExecutionProfileDeriver` | Convert intent to required mechanisms | No |
| `PlanSupervisor` | Own plan FSM, slot tokens, completion predicate, final validation | Yes, plan state only |
| `WorkspaceAttemptController` | Own attempt FSM, retries, terminalization, handoff creation | Yes, attempt state only |
| `StateStoreWriter` | Commit transitions with authority token | Yes, through token only |
| `AttemptEventJournal` | Append versioned event records | No state mutation by itself |
| `DeadlineWatchdog` | Detect expired attempts and emit events | No |
| `ExecutorActor` | Run LLM/tools/bash for an attempt | No |
| `ValidationActor` | Run validation with deadlines and process containment | No |
| `GitRunner` | Serialize Git repo mutations | No attempt state mutation |

## 2.5.3 Attempt FSM Doctrine

A v4 attempt is a bounded state machine. It cannot remain in a non-terminal state forever.

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
Failure paths: RUNNING+timeout -> TIMED_OUT, critical violation -> FAILED_FINAL
Terminal states: SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, TIMED_OUT, HANDOFF_REQUIRED
Retry is legal only after terminal state.
```

## 2.5.4 PostgreSQL Truth Doctrine

Runtime truth is PostgreSQL. JSON fallback is forbidden in production.

Allowed filesystem data: stdout/stderr logs, raw tool output, patch artifacts, handoff Markdown.
Forbidden as authoritative runtime truth: JSON state fallback, NDJSON-only journal, filesystem-only state.

## 2.5.5 Intent-Driven Plan Doctrine

v4 authors express what they want, not the low-level mechanism matrix.

Human-authored: `parallelism`, `safetyLevel`, `conflictRisk`, `deadlines`, `executionEnvironment`.
System-derived: worktree requirement, integration queue, validation lanes, drift policy, watchdog policy.


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
    "name": "v7_alphaforge_xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p0_5"
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
    "writeSetDriftPolicy": "reject_or_handoff",
    "explain": [
      "stable_3 worktree mode: 3 workers, worktree isolation, integration queue",
      "Worktree isolation required for safe parallel execution",
      "All production execution requires PostgreSQL authoritative runtime state"
    ]
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
  "attemptLifecycle": {
    "modeSpecificLifecycles": {
      "worktree": {
        "initialState": "queued",
        "nonTerminalStates": [
          "queued",
          "leasing_worktree",
          "running",
          "validating",
          "waiting_for_validation_lane",
          "integration_queued",
          "integrating"
        ],
        "terminalStates": [
          "succeeded",
          "failed_retryable",
          "failed_final",
          "aborted",
          "timed_out",
          "quarantined",
          "handoff_required"
        ]
      }
    },
    "retryableTerminalStates": [
      "failed_retryable",
      "timed_out",
      "quarantined"
    ],
    "retryForbiddenFromNonTerminal": true,
    "deadlineRequiredForNonTerminalStates": true,
    "handoffRequiredCreatesQueueItem": true
  },
  "planLifecycle": {
    "completionPredicateRequired": true,
    "cannotCompleteWithRequiredNonTerminalWorkspaces": true,
    "cannotCompleteWithUnresolvedRequiredHandoff": true,
    "finalValidationRequiredBeforeCompleted": true,
    "states": [
      "created",
      "preflight",
      "running",
      "blocked_with_reason",
      "awaiting_handoff",
      "final_validation",
      "completed",
      "completed_with_warnings",
      "failed_final",
      "stopping",
      "stopped"
    ]
  },
  "actorPermissions": {
    "workspaceAttemptController": {
      "mayMutateAttemptState": true,
      "mayCreateRetryAttempt": true
    },
    "planSupervisor": {
      "mayMutatePlanState": true,
      "mayReserveSchedulerSlots": true
    },
    "executorActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayProducePatchArtifact": true,
      "mayEmitEvents": true
    },
    "validationActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayEmitEvents": true
    },
    "gitRunner": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true,
      "note": "May perform low-level git operations only when invoked by authorized repository mutation authority."
    },
    "leaseMonitor": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true
    },
    "retryPolicy": {
      "mayMutateAttemptState": false,
      "mayCreateRetryAttempt": false,
      "maySuggestRetry": true
    },
    "brainWorkers": {
      "mayMutateExecutionState": false,
      "mayEmitDiagnosis": true,
      "mayProposeAction": true
    },
    "diagnostics": {
      "mayMutateExecutionState": false,
      "mayEmitEvidence": true
    }
  },
  "admissionGate": {
    "required": true,
    "allEntrypointsMustUseGate": true,
    "coveredEntrypoints": [
      "cli_plan_run",
      "dashboard_run",
      "api_plan_run",
      "retry_endpoint",
      "cleanup_rerun_endpoint",
      "brain_worker_trigger",
      "overnight_runner",
      "proposal_executor"
    ],
    "rejectWhen": [
      "postgres_unavailable_for_authoritative_runtime",
      "json_runtime_fallback_detected",
      "repair_mode_autonomous_execution_disabled",
      "promotion_gates_missing",
      "unsafe_parallelism_requested",
      "execution_kernel_disabled",
      "state_authority_not_single"
    ]
  },
  "resourceCoordination": {
    "nestedLocksForbidden": true,
    "holdLockAcrossAwaitForbidden": true,
    "stateLocks": {
      "scope": "attempt",
      "maxHoldMs": 1000
    },
    "planLock": {
      "scope": "plan",
      "maxHoldMs": 1000,
      "purpose": "slot_reservation_only"
    },
    "gitRunner": {
      "mode": "queue",
      "repoMutationTimeoutMs": 60000,
      "lockBypassForbidden": true
    },
    "validationLanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    },
    "worktreeLeases": {
      "attemptScoped": true,
      "heartbeatRequired": true,
      "quarantineOnStale": true
    },
    "stateStore": {
      "writesThroughControllerOnly": true,
      "transactionOrWriteQueueRequired": true
    }
  },
  "deadlineWatchdog": {
    "required": true,
    "intervalSeconds": 15,
    "emitsEventsOnly": true,
    "eventType": "deadline_exceeded",
    "supervised": true,
    "onWatchdogUnavailable": "block_new_execution_or_downgrade"
  },
  "handoffQueue": {
    "required": true,
    "createdByStates": [
      "handoff_required"
    ],
    "allowedActions": [
      "retry_requested",
      "close_failed",
      "manual_resolution",
      "followup_plan_requested"
    ],
    "controllerMediatedRetryRequired": true
  },
  "boundedLiveness": {
    "required": true,
    "noIndefiniteWaits": true,
    "llm": {
      "providerRequestTimeoutMs": 120000,
      "streamIdleTimeoutMs": 300000,
      "workspaceOverallTimeoutMs": 1800000,
      "maxConsecutiveProviderTimeouts": 2,
      "onCircuitOpen": "fail_workspace_not_plan"
    },
    "validation": {
      "defaultTimeoutMs": 600000,
      "heavyTimeoutMs": 1200000,
      "killProcessTreeOnTimeout": true,
      "watchModeForbidden": true,
      "stdinClosed": true,
      "ciEnvRequired": true,
      "maxOutputBytes": 52428800
    },
    "git": {
      "repoMutationLockTimeoutMs": 60000,
      "lockBypassForbidden": true,
      "onLockTimeout": "fail_fast_and_retry_or_handoff"
    },
    "scheduler": {
      "stallDetectionEnabled": true,
      "noProgressTimeoutMs": 300000,
      "onNoProgress": "emit_blocked_reason"
    },
    "stateStore": {
      "transactionOrWriteQueueRequired": true,
      "atomicSnapshotRequired": true,
      "journalLineAtomicityRequired": true
    }
  },
  "llmRuntime": {
    "boundedProviderCallsRequired": true,
    "providerRequestTimeoutMs": 120000,
    "streamIdleTimeoutMs": 300000,
    "workspaceOverallTimeoutMs": 1800000,
    "circuitBreaker": {
      "enabled": true,
      "openAfterConsecutiveTimeouts": 2,
      "cooldownMs": 300000
    },
    "fallbackPolicy": {
      "enabled": false,
      "reason": "Patches must remain deterministic."
    }
  },
  "validationRuntime": {
    "managedRunnerRequired": true,
    "processGroupRequired": true,
    "killTreeOnTimeout": true,
    "maxOutputBytes": 52428800,
    "forbiddenInteractiveCommands": [
      "vitest --watch",
      "jest --watch",
      "npm run dev",
      "vite --host"
    ],
    "lanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    }
  },
  "validationPolicy": {
    "defaultMode": "deferred",
    "workspaceCompletionRequiresTargetCommand": false,
    "planCompletionRequiresFinalValidation": true,
    "heavyValidationDeferredByDefault": true,
    "allowWorkspaceImmediateValidation": true,
    "allowSmokeValidation": true,
    "watchModeForbidden": true,
    "finalValidationWorkspaceRequired": true,
    "finalRepairWorkspaceRecommended": true,
    "validationArtifactsRequired": true,
    "liveValidationVisibilityRequired": true
  },
  "planExecution": {
    "phase": "P0.5",
    "title": "Shared Lib Foundation",
    "mode": "implementation",
    "maxParallelWorkspaces": 3,
    "scheduling": {
      "continuous": true,
      "slotCount": 3,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": false,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "stable_3",
      "selectedMode": "stable_3",
      "modes": {
        "stable_3": {
          "executorType": "direct",
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false,
          "preserveExistingBehavior": true
        },
        "stable_6": {
          "executorType": "patch_transaction",
          "maxCodegenWorkers": 6,
          "patchIsolationRequired": true,
          "worktreeRequired": false,
          "patchCoordinatorRequired": true,
          "repositoryMutationAuthority": "patch_coordinator",
          "patchApplyLanes": 1,
          "singleRepositoryWriterRequired": true,
          "targetedValidationRequired": true,
          "finalIntegrationValidationRequired": true,
          "postgresRequired": true,
          "completionGateRequired": true
        },
        "experimental_worktree_6": {
          "executorType": "worktree",
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "explicitOptInRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true
    },
    "integrationQueue": {
      "enabled": true,
      "enabledForExecutorTypes": [
        "worktree"
      ],
      "processOneMergeAtATime": true,
      "stopOnMergeConflict": true,
      "requireWorkspaceValidationPass": true,
      "requireIntegrationValidationPass": true,
      "gitPushAllowed": false,
      "queuePriority": {
        "enabled": true,
        "defaultLevel": "normal",
        "levels": [
          "critical",
          "high",
          "normal",
          "low"
        ]
      },
      "queueOptimization": {
        "enabled": true,
        "strategy": "priority_then_fifo",
        "availableStrategies": [
          "priority_then_fifo",
          "critical_path_first",
          "weighted_shortest_job_first"
        ]
      }
    },
    "validation": {
      "globalValidationLockRequired": true,
      "targetedValidationEnabled": true,
      "finalIntegrationValidationRequired": true,
      "watchModeForbidden": true
    },
    "interactiveParallelismReview": {
      "enabled": true,
      "preflightRequired": true,
      "approvalRequiredBeforeRun": true,
      "allowDependencyEditing": true,
      "showEffectiveParallelism": true,
      "showSafeEffectiveParallelism": true,
      "showBatchPreview": true,
      "showSafeBatchPreview": true,
      "showCriticalPath": true,
      "showScaleModeReadiness": true,
      "warnWhenEffectiveParallelismBelowRequested": true,
      "warnWhenSafeParallelismBelowDagParallelism": true,
      "warnWhenScaleModePrerequisitesMissing": true,
      "persistApprovedGraph": true
    },
    "planIntake": {
      "enabled": true,
      "runOnUpload": true,
      "parserPriority": [
        "part3_json",
        "contractVersion_and_executionClass",
        "doctor",
        "execution_gate"
      ],
      "autoNormalize": true,
      "autoDoctor": true,
      "autoDagAnalysis": true,
      "autoOptimizationProposal": true,
      "autoQueuePriorityRecommendation": true,
      "autoWorkspaceSplitRecommendation": true,
      "autoDryRunForecast": true,
      "approvalRequiredBeforeApplyingOptimization": true,
      "approvalRequiredBeforeExecution": true
    },
    "optimizer": {
      "enabled": true,
      "mode": "advisory_until_approved",
      "objectives": [
        "maximize_safe_effective_parallelism",
        "minimize_critical_path",
        "minimize_same_file_conflicts",
        "minimize_validation_lock_contention",
        "prioritize_critical_path_queue_merges"
      ],
      "allowedPatches": [
        "dependencies",
        "parallelGroup",
        "queuePriority",
        "canRunWith",
        "cannotRunWith",
        "conflictScope",
        "workspaceSplitSuggestion",
        "workspaceMergeSuggestion"
      ],
      "forbiddenAutoPatches": [
        "allowedFiles",
        "forbiddenFiles",
        "capabilityManifest",
        "safety.hardStops",
        "forbiddenCommands"
      ]
    }
  },
  "controls": {
    "allowPause": true,
    "allowStop": true,
    "allowCancel": true,
    "resumePolicy": "paused_or_stopped_only"
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
      "git clean -fd",
      "vitest --watch",
      "jest --watch",
      "npm run dev"
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
  "parallelismReview": {
    "requestedMaxParallelWorkspaces": 3,
    "selectedScaleMode": "stable_3",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for parallel execution."
        },
        {
          "key": "integration_queue",
          "required": true,
          "met": true,
          "message": "Required for queued execution."
        },
        {
          "key": "validation_lock",
          "required": true,
          "met": true,
          "message": "Required for heavy validation."
        },
        {
          "key": "completion_gate",
          "required": true,
          "met": true,
          "message": "Required for completion hardening."
        }
      ]
    },
    "expectedDagEffectiveParallelismMin": 2,
    "expectedSafeEffectiveParallelismMin": 2,
    "dagEffectiveParallelism": null,
    "safeEffectiveParallelism": null,
    "preflightStatus": "required",
    "approvalState": "pending",
    "batchingStrategy": "dag_topological_batches_display_only",
    "safeBatchingStrategy": "dag_batches_with_p6_safety_constraints_display_only",
    "batchPreview": {
      "batches": [],
      "overallEffectiveParallelism": null,
      "criticalPath": [],
      "criticalPathLength": 0,
      "serializedTailLength": 0
    },
    "safeBatchPreview": {
      "batches": [],
      "overallSafeEffectiveParallelism": null,
      "bottlenecks": [],
      "blockedParallelismReasons": []
    },
    "optimizationReview": {
      "originalGraphHash": null,
      "proposedGraphHash": null,
      "approvedGraphHash": null,
      "originalDagEffectiveParallelism": null,
      "proposedDagEffectiveParallelism": null,
      "originalSafeEffectiveParallelism": null,
      "proposedSafeEffectiveParallelism": null,
      "criticalPathDelta": null,
      "serializedTailDelta": null,
      "suggestions": [],
      "approvalState": "pending"
    },
    "editableFields": [
      "workspaces[].dependencies",
      "workspaces[].parallelGroup",
      "workspaces[].dependencyReason",
      "workspaces[].parallelism.canRunWith",
      "workspaces[].parallelism.cannotRunWith",
      "workspaces[].parallelism.conflictScope",
      "workspaces[].integration.queuePriority",
      "workspaces[].integration.queueOptimizationNotes"
    ],
    "doctorWarnings": [
      "effective_parallelism_below_requested",
      "safe_parallelism_below_dag_parallelism",
      "fully_serialized_graph",
      "long_serialized_tail",
      "file_overlap_blocks_parallelism",
      "validation_lock_limits_parallelism",
      "integration_queue_serializes_merges",
      "scale_mode_prerequisites_missing",
      "worktree_isolation_required_for_scale",
      "queue_optimization_disabled_with_active_priority",
      "queue_priority_mismatch_with_configured_levels",
      "critical_path_workspace_has_low_priority",
      "optimizer_patch_without_approval"
    ],
    "persistedArtifacts": [
      "dependency_graph",
      "batch_preview",
      "safe_batch_preview",
      "critical_path",
      "scale_mode_readiness",
      "approved_dependency_patch",
      "approved_graph_hash",
      "queue_priority_snapshot",
      "queue_optimization_strategy",
      "queue_reorder_decision_log",
      "plan_intake_analysis",
      "optimizer_proposal",
      "graph_diff",
      "worktree_state",
      "lease_heartbeat_snapshots",
      "lease_reconciliation_log",
      "merge_priority_score_log",
      "empirical_write_set",
      "write_set_drift_report",
      "validation_lane_saturation_log"
    ]
  },
  "workspaces": [
    {
      "id": "P05.A",
      "title": "Market Data Service",
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
          "lib/market_data/**",
          "tests/lib/market_data/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "lib/market_data/**",
        "tests/lib/market_data/**"
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
        "Binance HTTP client, klines/funding service, standard schema exist.",
        "Direct Binance API calls from v7/ or alphaforge/ are caught by hard stop."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "lib/market_data/**",
          "tests/lib/market_data/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P05.B",
      "title": "Indicators & Costs",
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
          "lib/indicators/**",
          "lib/costs/**",
          "tests/lib/indicators/**",
          "tests/lib/costs/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "lib/indicators/**",
        "lib/costs/**",
        "tests/lib/indicators/**",
        "tests/lib/costs/**"
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
        "ATR, returns, volatility, rolling window indicators exist.",
        "Fee % and slippage estimation exist.",
        "No /simulation truth or regime logic in lib/. /simulation is a top-level authority."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "lib/indicators/**",
          "lib/costs/**",
          "tests/lib/indicators/**",
          "tests/lib/costs/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P05.C",
      "title": "Time Utilities",
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
          "lib/time/**",
          "tests/lib/time/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "lib/time/**",
        "tests/lib/time/**"
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
        "Interval conversion and fold generation exist."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "low",
      "capabilityManifest": {
        "canEdit": [
          "lib/time/**",
          "tests/lib/time/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P05.D",
      "title": "Lib Boundary Tests",
      "dependencies": [
        "P05.A",
        "P05.B",
        "P05.C"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P05.A, P05.B, P05.C for foundation.",
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
          "tests/lib/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "tests/lib/**"
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
        "Import boundary violations are caught.",
        "lib/ must not import v7.* or alphaforge.*.",
        "No shared_everything_mistake (regime/risk/IO/adapters in lib/)."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "tests/lib/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
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
  "phase": "P0.5",
  "title": "Shared Lib Foundation",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "selectedRepairMode": null,
  "targetPromotionMode": "stable_6",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "schedulerRuntimeUse": "enabled",
  "primaryGoal": "Focused lib/ directory with shared Binance client, indicators, costs, and time utilities.",
  "projectName": "v7_alphaforge_xgb",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresPatchIsolation": false,
  "requiresIntegrationQueue": true,
  "requiresPatchApplyQueue": false,
  "repositoryMutationAuthority": "worktree_integration",
  "queueOptimizationEnabled": true,
  "queueOptimizationStrategy": "priority_then_fifo",
  "continuousScheduling": true,
  "continuousSlotCount": 3,
  "safeEffectiveParallelismTarget": 2,
  "notInScope": [
    "External broker execution authority",
    "V7 runtime core modifications",
    "Non-XGBoost model families"
  ],
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
    "optimizer_patch_without_approval"
  ],
  "completionGate": "P0.5 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "P1"
}
```

---

## Review Hardening Requirements

* [ ] Shared lib authority
* [ ] Import boundary enforcement

---

<!-- SOURCE: phase_plans/P0__repo_alignment_and_alpha_foundations.md -->

# P0 — Repo Alignment & Alpha Foundations

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P0`  
**One-line goal:** Repository skeleton, central config, typed foundations, test scaffolding.  
**Why now:** The alpha system needs stable folders, configs, schemas, and safety scaffolding before implementation begins.  
**Blast radius:** src/v7/alpha/**, tests/v7/alpha/**, configs/v7/alpha/**, docs/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Execution class:** `repair`  
**Execution automation:** `disabled`  
**Scale mode:** `stable_3`  
**Safe parallelism target:** `2`  
**Done when:** All workspaces pass acceptance criteria and phase JSON validates through Pi doctor.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P0` |
| Title | `Repo Alignment & Alpha Foundations` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Repository skeleton, central config, typed foundations, test scaffolding.` |
| Product-code changes | `Allowed` |
| Execution class | `repair` |
| Execution automation | `disabled` |
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

The alpha system needs stable folders, configs, schemas, and safety scaffolding before implementation begins.

The existing V7 design defines mode-specific simulation semantics, hybrid model outputs, and runtime-owned execution boundaries. The new alpha generation system must align with those constraints.

This phase uses `stable_3` scale-aware execution. The executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

---

## 3. What Carried Over — Must Stay Stable

* [ ] Runtime owns orchestration, execution, persistence, lifecycle, and hard safety.
* [ ] Model owns alpha evidence only.
* [ ] Simulation truth defines labels and evaluation.
* [ ] No hidden deterministic veto or hidden fallback.
* [ ] NO_TRADE remains first-class.
* [ ] Features are canonical-state only.
* [ ] Labels are mode-specific.
* [ ] Datasets are mode-specific and temporally split.
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

The existing V7 design defines mode-specific simulation semantics, hybrid model outputs, and runtime-owned execution boundaries. The new alpha generation system must align with those constraints.

---

## 5. Current Failure State / Known Blockers

* `v7_alphaforge_xgb` = not implemented.
* `mode_specific_alpha_datasets` = not implemented.
* `xgboost_alpha_artifacts` = not implemented.
* `calibrated_alpha_score_builder` = not implemented.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Worktree isolation violation | low | critical | Path scope checks; stop execution on escape |
| Integration queue merges unvalidated diff | medium | high | Require workspace validation and integration validation |
| Merge conflict blocks plan | medium | medium | Generate conflict handoff artifact and stop queue safely |
| Safe parallelism is lower than requested | medium | medium | Doctor warning; show bottleneck; use safe batch preview |
| Validation lock limits throughput | medium | medium | Scheduler reduces concurrency while heavy validation runs |
| High-risk workspace failure | medium | high | Rollback path defined; manual review gating |

---

## 7. Workstreams

### P0.A — Repository Skeleton

**Goal:** Create src/v7/alpha package tree and tests tree.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** low
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Create src/v7/alpha package tree and tests tree.

**File Scope:**
```text
src/v7/alpha/**
tests/v7/alpha/**
configs/v7/alpha/**
docs/v7/alpha/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P0.B — Config Foundations

**Goal:** Add alpha defaults and mode-specific simulation config surfaces.

**Dependencies:** P0.A
**Parallel Group:** batch_2
**Risk Level:** low
**Queue Priority:** normal
**Can run with:** P0.C, P0.D

**Requirements:
* Add alpha defaults and mode-specific simulation config surfaces.

**File Scope:**
```text
src/v7/alpha/**
tests/v7/alpha/**
configs/v7/alpha/**
docs/v7/alpha/**
```

**Isolation & Parallelism Notes:**
* Depends on P0.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P0.C — Typed Foundations

**Goal:** Add domain errors, serialization helpers, and schema validation helpers.

**Dependencies:** P0.A
**Parallel Group:** batch_2
**Risk Level:** low
**Queue Priority:** normal
**Can run with:** None

**Requirements:
* Add domain errors, serialization helpers, and schema validation helpers.

**File Scope:**
```text
src/v7/alpha/**
tests/v7/alpha/**
configs/v7/alpha/**
docs/v7/alpha/**
```

**Isolation & Parallelism Notes:**
* Depends on P0.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P0.D — Smoke Tests

**Goal:** Add import, config-load, unknown-key, and JSON schema smoke tests.

**Dependencies:** P0.A
**Parallel Group:** batch_2
**Risk Level:** low
**Queue Priority:** normal
**Can run with:** None

**Requirements:
* Add import, config-load, unknown-key, and JSON schema smoke tests.

**File Scope:**
```text
src/v7/alpha/**
tests/v7/alpha/**
configs/v7/alpha/**
docs/v7/alpha/**
```

**Isolation & Parallelism Notes:**
* Depends on P0.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P0.E — Hardening Config Invariants

**Goal:** Central config defines anomaly fit scope, regime visibility, symbol encoding, and interval authority.

**Dependencies:** P0.B
**Parallel Group:** hardening
**Risk Level:** high
**Queue Priority:** high
**Can run with:** None

**Requirements:
* Central config defines anomaly fit scope, regime visibility, symbol encoding, and interval authority.
* SCALP primary=1h/context=4h/refinement=15m is enforced from config.

**File Scope:**
```text
configs/**
src/v7/alpha/config/**
tests/v7/alpha/unit/config/**
```

**Isolation & Parallelism Notes:**
* Depends on P0.B for foundation.
* Expected batch: hardening
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.


---

## 8. Combined Implementation Order

```text
  Batch batch_1: P0.A
  Batch batch_2: P0.B + P0.C + P0.D
  Batch hardening: P0.E
```

The dependency graph dictates that foundation workspaces run first, followed by parallel batches where dependencies permit. The DAG batch preview and safe batch preview may differ because of file overlap, validation lock pressure, or integration queue serialization.

---

## 9. Definition of Done

`P0` is complete when ALL are true:

* [ ] Create src/v7/alpha package tree and tests tree.
* [ ] Add alpha defaults and mode-specific simulation config surfaces.
* [ ] Add domain errors, serialization helpers, and schema validation helpers.
* [ ] Add import, config-load, unknown-key, and JSON schema smoke tests.
* [ ] Central config defines anomaly fit scope, regime visibility, symbol encoding, and interval authority.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation is valid for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] No forbidden commands or files were used.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Validation planner misses a required failure.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Disable worktree mode only if safe fallback is required.
4. Pause or disable integration queue processing.
5. Preserve `.pi/worktrees/{planExecId}/` for debugging.
6. Fall back to shared-working-tree execution if explicitly allowed.
7. Keep dashboard telemetry read-only if safe.
8. Revert phase commits independently if needed.

---

## 11. What Next Phase Inherits

`P0.5` inherits:

* `P0` execution contract with worktree mode awareness.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Workspace-level parallelism/isolation/integration/validation metadata.
* Review hardening invariants: SCALP interval authority, Symbol encoding future-proofing

---

# Part 2 — Agent Brief

## Mission

Implement `P0` — Repository skeleton, central config, typed foundations, test scaffolding.

The agent must optimize for safe parallelism, not maximum concurrency. Higher worker counts are allowed only when scale-mode readiness passes and the executor can preserve correctness through worktree isolation, integration queue, validation locks, and completion gates.


**For repair plans:** The agent is an advisor/reviewer/patch author, NOT an autonomous executor. The agent may propose patches but must NOT apply them. Human approval is required for every patch.


---

## Hard Requirements

1. All P0 workstreams must pass acceptance criteria.
2. Worktree isolation must be enabled for parallel workspaces.
3. Integration queue must serialize merges.
4. Global validation lock must be active for heavy validation.
5. Watch-mode validation is forbidden.
6. `git push` is forbidden.
7. Raw destructive cleanup is forbidden.
8. Do not exceed selected scale-mode worker cap (3).
9. Do not merge workspace output without passed workspace validation.
10. Do not mark the plan complete if integration validation fails.
11. Do not treat merge conflict as ordinary worker failure.
12. Do not start the next plan while integration queue state is dirty.

---

## Execution Policies

```yaml
repair_modes:
  manual_0: autonomous_execution_allowed: false, agent_may_mutate_repo: false
  stable_3: autonomous_execution_allowed: true,  agent_may_mutate_repo: true

execution_automation:
  autonomous_execution_enabled: false
  agent_may_mutate_repo: false
  agent_may_run_commands: false
  manual_patch_application_required: true
  human_approval_required_for_every_patch: true

bounded_liveness:
  no_indefinite_waits: true
  llm_provider_timeout_required: true
  llm_stream_idle_watchdog_required: true
  validation_timeout_required: true
  process_tree_kill_required: true
  git_lock_bypass_forbidden: true
  state_write_serialization_required: true

scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
  worktree_required: true
  integration_queue_required: true

validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true

queue_optimization:
  enabled_by_default: true
  default_strategy: priority_then_fifo
  priority_levels: [critical, high, normal, low]
```

---

## Safety Stops

* Dependency cycles
* Invalid dependency patches
* Worktree path escaping `.pi/worktrees`
* Integration merge without passed workspace validation
* Validation failure
* Merge conflict without handoff artifact
* Unsafe scale mode
* Queue starting next plan while integration queue is dirty
* Forbidden file access
* Secrets access
* `git push`
* Watch-mode validation
* `autonomous_execution_requested_during_repair_mode`
* `agent_repo_mutation_requested_during_manual_repair`
* `scheduler_enabled_before_executor_isolation_gate`
* `llm_call_without_provider_timeout`
* `validation_command_without_timeout`
* `git_lock_bypass_detected`
* `state_store_write_without_serialization`
* `workspace_patch_without_human_approval`
* `promotion_gate_failed_or_missing`


# Part 2.5 — v4 ExecutionKernel Doctrine

## 2.5.1 Single Authority Model

v4 replaces the previous executor-owned or multi-component execution state model with an ExecutionKernel model.

```text
Before v4:
  Scheduler, executor, validation runner, retry router, cleanup, lease monitor,
  diagnostics, and brain workers could each influence or write partial execution truth.

After v4:
  All actors emit events.
  WorkspaceAttemptController mutates attempt state.
  PlanSupervisor mutates plan state.
  PostgreSQL stores authoritative runtime truth.
```

## 2.5.2 ExecutionKernel Components

| Component | Responsibility | May mutate execution state? |
|---|---|---:|
| `ExecutionAdmissionGate` | Authorize or reject execution requests before runtime starts | No |
| `ExecutionProfileDeriver` | Convert intent to required mechanisms | No |
| `PlanSupervisor` | Own plan FSM, slot tokens, completion predicate, final validation | Yes, plan state only |
| `WorkspaceAttemptController` | Own attempt FSM, retries, terminalization, handoff creation | Yes, attempt state only |
| `StateStoreWriter` | Commit transitions with authority token | Yes, through token only |
| `AttemptEventJournal` | Append versioned event records | No state mutation by itself |
| `DeadlineWatchdog` | Detect expired attempts and emit events | No |
| `ExecutorActor` | Run LLM/tools/bash for an attempt | No |
| `ValidationActor` | Run validation with deadlines and process containment | No |
| `GitRunner` | Serialize Git repo mutations | No attempt state mutation |

## 2.5.3 Attempt FSM Doctrine

A v4 attempt is a bounded state machine. It cannot remain in a non-terminal state forever.

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
Failure paths: RUNNING+timeout -> TIMED_OUT, critical violation -> FAILED_FINAL
Terminal states: SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, TIMED_OUT, HANDOFF_REQUIRED
Retry is legal only after terminal state.
```

## 2.5.4 PostgreSQL Truth Doctrine

Runtime truth is PostgreSQL. JSON fallback is forbidden in production.

Allowed filesystem data: stdout/stderr logs, raw tool output, patch artifacts, handoff Markdown.
Forbidden as authoritative runtime truth: JSON state fallback, NDJSON-only journal, filesystem-only state.

## 2.5.5 Intent-Driven Plan Doctrine

v4 authors express what they want, not the low-level mechanism matrix.

Human-authored: `parallelism`, `safetyLevel`, `conflictRisk`, `deadlines`, `executionEnvironment`.
System-derived: worktree requirement, integration queue, validation lanes, drift policy, watchdog policy.


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
  "executionClass": "repair",
  "executionBackend": "postgres",
  "project": {
    "name": "v7_alphaforge_xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p0"
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
    "writeSetDriftPolicy": "reject_or_handoff",
    "explain": [
      "stable_3 worktree mode: 3 workers, worktree isolation, integration queue",
      "Worktree isolation required for safe parallel execution",
      "All production execution requires PostgreSQL authoritative runtime state"
    ]
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
    "autonomousExecutionEnabled": false,
    "agentMayMutateRepo": false,
    "agentMayRunCommands": false,
    "manualPatchApplicationRequired": true,
    "humanApprovalRequiredForEveryPatch": true
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
  "attemptLifecycle": {
    "modeSpecificLifecycles": {
      "worktree": {
        "initialState": "queued",
        "nonTerminalStates": [
          "queued",
          "leasing_worktree",
          "running",
          "validating",
          "waiting_for_validation_lane",
          "integration_queued",
          "integrating"
        ],
        "terminalStates": [
          "succeeded",
          "failed_retryable",
          "failed_final",
          "aborted",
          "timed_out",
          "quarantined",
          "handoff_required"
        ]
      }
    },
    "retryableTerminalStates": [
      "failed_retryable",
      "timed_out",
      "quarantined"
    ],
    "retryForbiddenFromNonTerminal": true,
    "deadlineRequiredForNonTerminalStates": true,
    "handoffRequiredCreatesQueueItem": true
  },
  "planLifecycle": {
    "completionPredicateRequired": true,
    "cannotCompleteWithRequiredNonTerminalWorkspaces": true,
    "cannotCompleteWithUnresolvedRequiredHandoff": true,
    "finalValidationRequiredBeforeCompleted": true,
    "states": [
      "created",
      "preflight",
      "running",
      "blocked_with_reason",
      "awaiting_handoff",
      "final_validation",
      "completed",
      "completed_with_warnings",
      "failed_final",
      "stopping",
      "stopped"
    ]
  },
  "actorPermissions": {
    "workspaceAttemptController": {
      "mayMutateAttemptState": true,
      "mayCreateRetryAttempt": true
    },
    "planSupervisor": {
      "mayMutatePlanState": true,
      "mayReserveSchedulerSlots": true
    },
    "executorActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayProducePatchArtifact": true,
      "mayEmitEvents": true
    },
    "validationActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayEmitEvents": true
    },
    "gitRunner": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true,
      "note": "May perform low-level git operations only when invoked by authorized repository mutation authority."
    },
    "leaseMonitor": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true
    },
    "retryPolicy": {
      "mayMutateAttemptState": false,
      "mayCreateRetryAttempt": false,
      "maySuggestRetry": true
    },
    "brainWorkers": {
      "mayMutateExecutionState": false,
      "mayEmitDiagnosis": true,
      "mayProposeAction": true
    },
    "diagnostics": {
      "mayMutateExecutionState": false,
      "mayEmitEvidence": true
    }
  },
  "admissionGate": {
    "required": true,
    "allEntrypointsMustUseGate": true,
    "coveredEntrypoints": [
      "cli_plan_run",
      "dashboard_run",
      "api_plan_run",
      "retry_endpoint",
      "cleanup_rerun_endpoint",
      "brain_worker_trigger",
      "overnight_runner",
      "proposal_executor"
    ],
    "rejectWhen": [
      "postgres_unavailable_for_authoritative_runtime",
      "json_runtime_fallback_detected",
      "repair_mode_autonomous_execution_disabled",
      "promotion_gates_missing",
      "unsafe_parallelism_requested",
      "execution_kernel_disabled",
      "state_authority_not_single"
    ]
  },
  "resourceCoordination": {
    "nestedLocksForbidden": true,
    "holdLockAcrossAwaitForbidden": true,
    "stateLocks": {
      "scope": "attempt",
      "maxHoldMs": 1000
    },
    "planLock": {
      "scope": "plan",
      "maxHoldMs": 1000,
      "purpose": "slot_reservation_only"
    },
    "gitRunner": {
      "mode": "queue",
      "repoMutationTimeoutMs": 60000,
      "lockBypassForbidden": true
    },
    "validationLanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    },
    "worktreeLeases": {
      "attemptScoped": true,
      "heartbeatRequired": true,
      "quarantineOnStale": true
    },
    "stateStore": {
      "writesThroughControllerOnly": true,
      "transactionOrWriteQueueRequired": true
    }
  },
  "deadlineWatchdog": {
    "required": true,
    "intervalSeconds": 15,
    "emitsEventsOnly": true,
    "eventType": "deadline_exceeded",
    "supervised": true,
    "onWatchdogUnavailable": "block_new_execution_or_downgrade"
  },
  "handoffQueue": {
    "required": true,
    "createdByStates": [
      "handoff_required"
    ],
    "allowedActions": [
      "retry_requested",
      "close_failed",
      "manual_resolution",
      "followup_plan_requested"
    ],
    "controllerMediatedRetryRequired": true
  },
  "boundedLiveness": {
    "required": true,
    "noIndefiniteWaits": true,
    "llm": {
      "providerRequestTimeoutMs": 120000,
      "streamIdleTimeoutMs": 300000,
      "workspaceOverallTimeoutMs": 1800000,
      "maxConsecutiveProviderTimeouts": 2,
      "onCircuitOpen": "fail_workspace_not_plan"
    },
    "validation": {
      "defaultTimeoutMs": 600000,
      "heavyTimeoutMs": 1200000,
      "killProcessTreeOnTimeout": true,
      "watchModeForbidden": true,
      "stdinClosed": true,
      "ciEnvRequired": true,
      "maxOutputBytes": 52428800
    },
    "git": {
      "repoMutationLockTimeoutMs": 60000,
      "lockBypassForbidden": true,
      "onLockTimeout": "fail_fast_and_retry_or_handoff"
    },
    "scheduler": {
      "stallDetectionEnabled": true,
      "noProgressTimeoutMs": 300000,
      "onNoProgress": "emit_blocked_reason"
    },
    "stateStore": {
      "transactionOrWriteQueueRequired": true,
      "atomicSnapshotRequired": true,
      "journalLineAtomicityRequired": true
    }
  },
  "llmRuntime": {
    "boundedProviderCallsRequired": true,
    "providerRequestTimeoutMs": 120000,
    "streamIdleTimeoutMs": 300000,
    "workspaceOverallTimeoutMs": 1800000,
    "circuitBreaker": {
      "enabled": true,
      "openAfterConsecutiveTimeouts": 2,
      "cooldownMs": 300000
    },
    "fallbackPolicy": {
      "enabled": false,
      "reason": "Patches must remain deterministic."
    }
  },
  "validationRuntime": {
    "managedRunnerRequired": true,
    "processGroupRequired": true,
    "killTreeOnTimeout": true,
    "maxOutputBytes": 52428800,
    "forbiddenInteractiveCommands": [
      "vitest --watch",
      "jest --watch",
      "npm run dev",
      "vite --host"
    ],
    "lanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    }
  },
  "validationPolicy": {
    "defaultMode": "deferred",
    "workspaceCompletionRequiresTargetCommand": false,
    "planCompletionRequiresFinalValidation": true,
    "heavyValidationDeferredByDefault": true,
    "allowWorkspaceImmediateValidation": true,
    "allowSmokeValidation": true,
    "watchModeForbidden": true,
    "finalValidationWorkspaceRequired": true,
    "finalRepairWorkspaceRecommended": true,
    "validationArtifactsRequired": true,
    "liveValidationVisibilityRequired": true
  },
  "planExecution": {
    "phase": "P0",
    "title": "Repo Alignment & Alpha Foundations",
    "mode": "manual_repair",
    "maxParallelWorkspaces": 3,
    "scheduling": {
      "continuous": true,
      "slotCount": 3,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": false,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "stable_3",
      "selectedMode": "stable_3",
      "modes": {
        "stable_3": {
          "executorType": "direct",
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false,
          "preserveExistingBehavior": true
        },
        "stable_6": {
          "executorType": "patch_transaction",
          "maxCodegenWorkers": 6,
          "patchIsolationRequired": true,
          "worktreeRequired": false,
          "patchCoordinatorRequired": true,
          "repositoryMutationAuthority": "patch_coordinator",
          "patchApplyLanes": 1,
          "singleRepositoryWriterRequired": true,
          "targetedValidationRequired": true,
          "finalIntegrationValidationRequired": true,
          "postgresRequired": true,
          "completionGateRequired": true
        },
        "experimental_worktree_6": {
          "executorType": "worktree",
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "explicitOptInRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true
    },
    "integrationQueue": {
      "enabled": true,
      "enabledForExecutorTypes": [
        "worktree"
      ],
      "processOneMergeAtATime": true,
      "stopOnMergeConflict": true,
      "requireWorkspaceValidationPass": true,
      "requireIntegrationValidationPass": true,
      "gitPushAllowed": false,
      "queuePriority": {
        "enabled": true,
        "defaultLevel": "normal",
        "levels": [
          "critical",
          "high",
          "normal",
          "low"
        ]
      },
      "queueOptimization": {
        "enabled": true,
        "strategy": "priority_then_fifo",
        "availableStrategies": [
          "priority_then_fifo",
          "critical_path_first",
          "weighted_shortest_job_first"
        ]
      }
    },
    "validation": {
      "globalValidationLockRequired": true,
      "targetedValidationEnabled": true,
      "finalIntegrationValidationRequired": true,
      "watchModeForbidden": true
    },
    "interactiveParallelismReview": {
      "enabled": true,
      "preflightRequired": true,
      "approvalRequiredBeforeRun": true,
      "allowDependencyEditing": true,
      "showEffectiveParallelism": true,
      "showSafeEffectiveParallelism": true,
      "showBatchPreview": true,
      "showSafeBatchPreview": true,
      "showCriticalPath": true,
      "showScaleModeReadiness": true,
      "warnWhenEffectiveParallelismBelowRequested": true,
      "warnWhenSafeParallelismBelowDagParallelism": true,
      "warnWhenScaleModePrerequisitesMissing": true,
      "persistApprovedGraph": true
    },
    "planIntake": {
      "enabled": true,
      "runOnUpload": true,
      "parserPriority": [
        "part3_json",
        "contractVersion_and_executionClass",
        "doctor",
        "execution_gate"
      ],
      "autoNormalize": true,
      "autoDoctor": true,
      "autoDagAnalysis": true,
      "autoOptimizationProposal": true,
      "autoQueuePriorityRecommendation": true,
      "autoWorkspaceSplitRecommendation": true,
      "autoDryRunForecast": true,
      "approvalRequiredBeforeApplyingOptimization": true,
      "approvalRequiredBeforeExecution": true
    },
    "optimizer": {
      "enabled": true,
      "mode": "advisory_until_approved",
      "objectives": [
        "maximize_safe_effective_parallelism",
        "minimize_critical_path",
        "minimize_same_file_conflicts",
        "minimize_validation_lock_contention",
        "prioritize_critical_path_queue_merges"
      ],
      "allowedPatches": [
        "dependencies",
        "parallelGroup",
        "queuePriority",
        "canRunWith",
        "cannotRunWith",
        "conflictScope",
        "workspaceSplitSuggestion",
        "workspaceMergeSuggestion"
      ],
      "forbiddenAutoPatches": [
        "allowedFiles",
        "forbiddenFiles",
        "capabilityManifest",
        "safety.hardStops",
        "forbiddenCommands"
      ]
    }
  },
  "controls": {
    "allowPause": true,
    "allowStop": true,
    "allowCancel": true,
    "resumePolicy": "paused_or_stopped_only"
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
      "git clean -fd",
      "vitest --watch",
      "jest --watch",
      "npm run dev"
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
  "parallelismReview": {
    "requestedMaxParallelWorkspaces": 3,
    "selectedScaleMode": "stable_3",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for parallel execution."
        },
        {
          "key": "integration_queue",
          "required": true,
          "met": true,
          "message": "Required for queued execution."
        },
        {
          "key": "validation_lock",
          "required": true,
          "met": true,
          "message": "Required for heavy validation."
        },
        {
          "key": "completion_gate",
          "required": true,
          "met": true,
          "message": "Required for completion hardening."
        }
      ]
    },
    "expectedDagEffectiveParallelismMin": 2,
    "expectedSafeEffectiveParallelismMin": 2,
    "dagEffectiveParallelism": null,
    "safeEffectiveParallelism": null,
    "preflightStatus": "required",
    "approvalState": "pending",
    "batchingStrategy": "dag_topological_batches_display_only",
    "safeBatchingStrategy": "dag_batches_with_p6_safety_constraints_display_only",
    "batchPreview": {
      "batches": [],
      "overallEffectiveParallelism": null,
      "criticalPath": [],
      "criticalPathLength": 0,
      "serializedTailLength": 0
    },
    "safeBatchPreview": {
      "batches": [],
      "overallSafeEffectiveParallelism": null,
      "bottlenecks": [],
      "blockedParallelismReasons": []
    },
    "optimizationReview": {
      "originalGraphHash": null,
      "proposedGraphHash": null,
      "approvedGraphHash": null,
      "originalDagEffectiveParallelism": null,
      "proposedDagEffectiveParallelism": null,
      "originalSafeEffectiveParallelism": null,
      "proposedSafeEffectiveParallelism": null,
      "criticalPathDelta": null,
      "serializedTailDelta": null,
      "suggestions": [],
      "approvalState": "pending"
    },
    "editableFields": [
      "workspaces[].dependencies",
      "workspaces[].parallelGroup",
      "workspaces[].dependencyReason",
      "workspaces[].parallelism.canRunWith",
      "workspaces[].parallelism.cannotRunWith",
      "workspaces[].parallelism.conflictScope",
      "workspaces[].integration.queuePriority",
      "workspaces[].integration.queueOptimizationNotes"
    ],
    "doctorWarnings": [
      "effective_parallelism_below_requested",
      "safe_parallelism_below_dag_parallelism",
      "fully_serialized_graph",
      "long_serialized_tail",
      "file_overlap_blocks_parallelism",
      "validation_lock_limits_parallelism",
      "integration_queue_serializes_merges",
      "scale_mode_prerequisites_missing",
      "worktree_isolation_required_for_scale",
      "queue_optimization_disabled_with_active_priority",
      "queue_priority_mismatch_with_configured_levels",
      "critical_path_workspace_has_low_priority",
      "optimizer_patch_without_approval"
    ],
    "persistedArtifacts": [
      "dependency_graph",
      "batch_preview",
      "safe_batch_preview",
      "critical_path",
      "scale_mode_readiness",
      "approved_dependency_patch",
      "approved_graph_hash",
      "queue_priority_snapshot",
      "queue_optimization_strategy",
      "queue_reorder_decision_log",
      "plan_intake_analysis",
      "optimizer_proposal",
      "graph_diff",
      "worktree_state",
      "lease_heartbeat_snapshots",
      "lease_reconciliation_log",
      "merge_priority_score_log",
      "empirical_write_set",
      "write_set_drift_report",
      "validation_lane_saturation_log"
    ]
  },
  "workspaces": [
    {
      "id": "P0.A",
      "title": "Repository Skeleton",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
      "manualApplicationRequired": true,
      "humanApprovalRequired": true,
      "autonomousExecutionAllowed": false,
      "rollbackRequired": true,
      "targetedValidationRequired": true,
      "parallelism": {
        "expectedBatch": "batch_1",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/**",
          "tests/v7/alpha/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/**",
        "tests/v7/alpha/**",
        "configs/v7/alpha/**",
        "docs/v7/alpha/**"
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
        "Create src/v7/alpha package tree and tests tree."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 0,
      "riskLevel": "low",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/**",
          "tests/v7/alpha/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P0.B",
      "title": "Config Foundations",
      "dependencies": [
        "P0.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P0.A for foundation.",
      "manualApplicationRequired": true,
      "humanApprovalRequired": true,
      "autonomousExecutionAllowed": false,
      "rollbackRequired": true,
      "targetedValidationRequired": true,
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [
          "P0.C",
          "P0.D"
        ],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/**",
          "tests/v7/alpha/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "normal",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/**",
        "tests/v7/alpha/**",
        "configs/v7/alpha/**",
        "docs/v7/alpha/**"
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
        "Add alpha defaults and mode-specific simulation config surfaces."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 0,
      "riskLevel": "low",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/**",
          "tests/v7/alpha/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P0.C",
      "title": "Typed Foundations",
      "dependencies": [
        "P0.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P0.A for foundation.",
      "manualApplicationRequired": true,
      "humanApprovalRequired": true,
      "autonomousExecutionAllowed": false,
      "rollbackRequired": true,
      "targetedValidationRequired": true,
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/**",
          "tests/v7/alpha/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "normal",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/**",
        "tests/v7/alpha/**",
        "configs/v7/alpha/**",
        "docs/v7/alpha/**"
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
        "Add domain errors, serialization helpers, and schema validation helpers."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 0,
      "riskLevel": "low",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/**",
          "tests/v7/alpha/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P0.D",
      "title": "Smoke Tests",
      "dependencies": [
        "P0.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P0.A for foundation.",
      "manualApplicationRequired": true,
      "humanApprovalRequired": true,
      "autonomousExecutionAllowed": false,
      "rollbackRequired": true,
      "targetedValidationRequired": true,
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/**",
          "tests/v7/alpha/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "normal",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/**",
        "tests/v7/alpha/**",
        "configs/v7/alpha/**",
        "docs/v7/alpha/**"
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
        "Add import, config-load, unknown-key, and JSON schema smoke tests."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 0,
      "riskLevel": "low",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/**",
          "tests/v7/alpha/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P0.E",
      "title": "Hardening Config Invariants",
      "dependencies": [
        "P0.B"
      ],
      "parallelGroup": "hardening",
      "dependencyReason": "Depends on P0.B for foundation.",
      "manualApplicationRequired": true,
      "humanApprovalRequired": true,
      "autonomousExecutionAllowed": false,
      "rollbackRequired": true,
      "targetedValidationRequired": true,
      "parallelism": {
        "expectedBatch": "hardening",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "configs/**",
          "src/v7/alpha/config/**",
          "tests/v7/alpha/unit/config/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "configs/**",
        "src/v7/alpha/config/**",
        "tests/v7/alpha/unit/config/**"
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
        "Central config defines anomaly fit scope, regime visibility, symbol encoding, and interval authority.",
        "SCALP primary=1h/context=4h/refinement=15m is enforced from config."
      ],
      "targetCommand": null,
      "roleBudget": "worker",
      "maxRetries": 0,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "configs/**",
          "src/v7/alpha/config/**",
          "tests/v7/alpha/unit/config/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
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
  "phase": "P0",
  "title": "Repo Alignment & Alpha Foundations",
  "executionClass": "repair",
  "executionAutomation": "disabled",
  "selectedRepairMode": "manual_1",
  "targetPromotionMode": "stable_6",
  "autonomousExecutionAllowed": false,
  "agentMayMutateRepo": false,
  "schedulerRuntimeUse": "disabled_until_promotion",
  "primaryGoal": "Repository skeleton, central config, typed foundations, test scaffolding.",
  "projectName": "v7_alphaforge_xgb",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresPatchIsolation": false,
  "requiresIntegrationQueue": true,
  "requiresPatchApplyQueue": false,
  "repositoryMutationAuthority": "worktree_integration",
  "queueOptimizationEnabled": true,
  "queueOptimizationStrategy": "priority_then_fifo",
  "continuousScheduling": true,
  "continuousSlotCount": 3,
  "safeEffectiveParallelismTarget": 2,
  "notInScope": [
    "External broker execution authority",
    "V7 runtime core modifications",
    "Non-XGBoost model families"
  ],
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
    "optimizer_patch_without_approval"
  ],
  "completionGate": "P0 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "P0.5"
}
```

---

## Review Hardening Requirements

* [ ] SCALP interval authority
* [ ] Symbol encoding future-proofing

---

<!-- SOURCE: phase_plans/P1__contracts_and_alpha_data_contract.md -->

# P1 — Contracts & Alpha Data Contract

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P1`  
**One-line goal:** Feature, label, prediction, artifact, and V7 bridge contracts.  
**Why now:** The runtime, training, and Pi agents need a stable typed boundary before feature, label, and model code can safely integrate.  
**Blast radius:** src/v7/alpha/**, tests/v7/alpha/**, configs/v7/alpha/**, docs/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Execution class:** `implementation`  
**Execution automation:** `enabled`  
**Scale mode:** `stable_3`  
**Safe parallelism target:** `2`  
**Done when:** All workspaces pass acceptance criteria and phase JSON validates through Pi doctor.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P1` |
| Title | `Contracts & Alpha Data Contract` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Feature, label, prediction, artifact, and V7 bridge contracts.` |
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

The runtime, training, and Pi agents need a stable typed boundary before feature, label, and model code can safely integrate.

Without typed contracts, feature schema changes silently break downstream consumers, label format drifts, and prediction surfaces become incompatible with V7 decision engine expectations.

This phase uses `stable_3` scale-aware execution. The executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

---

## 3. What Carried Over — Must Stay Stable

* [ ] Runtime owns orchestration, execution, persistence, lifecycle, and hard safety.
* [ ] Model owns alpha evidence only.
* [ ] Simulation truth defines labels and evaluation.
* [ ] No hidden deterministic veto or hidden fallback.
* [ ] NO_TRADE remains first-class.
* [ ] Features are canonical-state only.
* [ ] Labels are mode-specific.
* [ ] Datasets are mode-specific and temporally split.
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

Without typed contracts, feature schema changes silently break downstream consumers, label format drifts, and prediction surfaces become incompatible with V7 decision engine expectations.

---

## 5. Current Failure State / Known Blockers

* `alpha_feature_table` = not implemented.
* `alpha_label_table` = not implemented.
* `alpha_prediction_table` = not implemented.
* `alpha_artifact_bundle_schema` = not implemented.
* `V7AnalysisRequest / AnalysisResult bridge` = not implemented.

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

### P1.A — Feature Row Contract

**Goal:** alpha_feature_table contract with all required fields is typed.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** low
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* alpha_feature_table contract with all required fields is typed.
* feature_schema_version, symbol_encoding_family, symbol_universe_version are required fields.

**File Scope:**
```text
src/v7/alpha/contracts/**
tests/v7/alpha/unit/contracts/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P1.B — Label Row Contract

**Goal:** alpha_label_table contract with long_R_net, short_R_net, best_action_label, gap_R is typed.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** low
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* alpha_label_table contract with long_R_net, short_R_net, best_action_label, gap_R is typed.

**File Scope:**
```text
src/v7/alpha/contracts/**
tests/v7/alpha/unit/contracts/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P1.C — Prediction & Bridge Contracts

**Goal:** alpha_prediction_table contract typed.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** low
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* alpha_prediction_table contract typed.
* V7AnalysisRequest and AnalysisResult bridge contracts defined.
* ModelScope, Mode, and Action enums match V7 canonical values.

**File Scope:**
```text
src/v7/alpha/contracts/**
src/v7/alpha/runtime/**
tests/v7/alpha/unit/contracts/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P1.D — Contract Tests

**Goal:** All contracts have serialization round-trip tests.

**Dependencies:** P1.A, P1.B, P1.C
**Parallel Group:** batch_2
**Risk Level:** low
**Queue Priority:** normal
**Can run with:** None

**Requirements:
* All contracts have serialization round-trip tests.
* Schema version bumps are validated.

**File Scope:**
```text
tests/v7/alpha/unit/contracts/**
```

**Isolation & Parallelism Notes:**
* Depends on P1.A, P1.B, P1.C for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.


---

## 8. Combined Implementation Order

```text
  Batch batch_1: P1.A + P1.B + P1.C
  Batch batch_2: P1.D
```

The dependency graph dictates that foundation workspaces run first, followed by parallel batches where dependencies permit. The DAG batch preview and safe batch preview may differ because of file overlap, validation lock pressure, or integration queue serialization.

---

## 9. Definition of Done

`P1` is complete when ALL are true:

* [ ] alpha_feature_table contract with all required fields is typed.
* [ ] alpha_label_table contract with long_R_net, short_R_net, best_action_label, gap_R is typed.
* [ ] alpha_prediction_table contract typed.
* [ ] All contracts have serialization round-trip tests.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation is valid for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] No forbidden commands or files were used.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Validation planner misses a required failure.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Disable worktree mode only if safe fallback is required.
4. Pause or disable integration queue processing.
5. Preserve `.pi/worktrees/{planExecId}/` for debugging.
6. Fall back to shared-working-tree execution if explicitly allowed.
7. Keep dashboard telemetry read-only if safe.
8. Revert phase commits independently if needed.

---

## 11. What Next Phase Inherits

`P2` inherits:

* `P1` execution contract with worktree mode awareness.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Workspace-level parallelism/isolation/integration/validation metadata.
* Review hardening invariants: Data contract schema versioning

---

# Part 2 — Agent Brief

## Mission

Implement `P1` — Feature, label, prediction, artifact, and V7 bridge contracts.

The agent must optimize for safe parallelism, not maximum concurrency. Higher worker counts are allowed only when scale-mode readiness passes and the executor can preserve correctness through worktree isolation, integration queue, validation locks, and completion gates.



---

## Hard Requirements

1. All P1 workstreams must pass acceptance criteria.
2. Worktree isolation must be enabled for parallel workspaces.
3. Integration queue must serialize merges.
4. Global validation lock must be active for heavy validation.
5. Watch-mode validation is forbidden.
6. `git push` is forbidden.
7. Raw destructive cleanup is forbidden.
8. Do not exceed selected scale-mode worker cap (3).
9. Do not merge workspace output without passed workspace validation.
10. Do not mark the plan complete if integration validation fails.
11. Do not treat merge conflict as ordinary worker failure.
12. Do not start the next plan while integration queue state is dirty.

---

## Execution Policies

```yaml
repair_modes:
  manual_0: autonomous_execution_allowed: false, agent_may_mutate_repo: false
  stable_3: autonomous_execution_allowed: true,  agent_may_mutate_repo: true

execution_automation:
  autonomous_execution_enabled: true
  agent_may_mutate_repo: true
  agent_may_run_commands: true
  manual_patch_application_required: false
  human_approval_required_for_every_patch: false

bounded_liveness:
  no_indefinite_waits: true
  llm_provider_timeout_required: true
  llm_stream_idle_watchdog_required: true
  validation_timeout_required: true
  process_tree_kill_required: true
  git_lock_bypass_forbidden: true
  state_write_serialization_required: true

scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
  worktree_required: true
  integration_queue_required: true

validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true

queue_optimization:
  enabled_by_default: true
  default_strategy: priority_then_fifo
  priority_levels: [critical, high, normal, low]
```

---

## Safety Stops

* Dependency cycles
* Invalid dependency patches
* Worktree path escaping `.pi/worktrees`
* Integration merge without passed workspace validation
* Validation failure
* Merge conflict without handoff artifact
* Unsafe scale mode
* Queue starting next plan while integration queue is dirty
* Forbidden file access
* Secrets access
* `git push`
* Watch-mode validation
* `autonomous_execution_requested_during_repair_mode`
* `agent_repo_mutation_requested_during_manual_repair`
* `scheduler_enabled_before_executor_isolation_gate`
* `llm_call_without_provider_timeout`
* `validation_command_without_timeout`
* `git_lock_bypass_detected`
* `state_store_write_without_serialization`
* `workspace_patch_without_human_approval`
* `promotion_gate_failed_or_missing`


# Part 2.5 — v4 ExecutionKernel Doctrine

## 2.5.1 Single Authority Model

v4 replaces the previous executor-owned or multi-component execution state model with an ExecutionKernel model.

```text
Before v4:
  Scheduler, executor, validation runner, retry router, cleanup, lease monitor,
  diagnostics, and brain workers could each influence or write partial execution truth.

After v4:
  All actors emit events.
  WorkspaceAttemptController mutates attempt state.
  PlanSupervisor mutates plan state.
  PostgreSQL stores authoritative runtime truth.
```

## 2.5.2 ExecutionKernel Components

| Component | Responsibility | May mutate execution state? |
|---|---|---:|
| `ExecutionAdmissionGate` | Authorize or reject execution requests before runtime starts | No |
| `ExecutionProfileDeriver` | Convert intent to required mechanisms | No |
| `PlanSupervisor` | Own plan FSM, slot tokens, completion predicate, final validation | Yes, plan state only |
| `WorkspaceAttemptController` | Own attempt FSM, retries, terminalization, handoff creation | Yes, attempt state only |
| `StateStoreWriter` | Commit transitions with authority token | Yes, through token only |
| `AttemptEventJournal` | Append versioned event records | No state mutation by itself |
| `DeadlineWatchdog` | Detect expired attempts and emit events | No |
| `ExecutorActor` | Run LLM/tools/bash for an attempt | No |
| `ValidationActor` | Run validation with deadlines and process containment | No |
| `GitRunner` | Serialize Git repo mutations | No attempt state mutation |

## 2.5.3 Attempt FSM Doctrine

A v4 attempt is a bounded state machine. It cannot remain in a non-terminal state forever.

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
Failure paths: RUNNING+timeout -> TIMED_OUT, critical violation -> FAILED_FINAL
Terminal states: SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, TIMED_OUT, HANDOFF_REQUIRED
Retry is legal only after terminal state.
```

## 2.5.4 PostgreSQL Truth Doctrine

Runtime truth is PostgreSQL. JSON fallback is forbidden in production.

Allowed filesystem data: stdout/stderr logs, raw tool output, patch artifacts, handoff Markdown.
Forbidden as authoritative runtime truth: JSON state fallback, NDJSON-only journal, filesystem-only state.

## 2.5.5 Intent-Driven Plan Doctrine

v4 authors express what they want, not the low-level mechanism matrix.

Human-authored: `parallelism`, `safetyLevel`, `conflictRisk`, `deadlines`, `executionEnvironment`.
System-derived: worktree requirement, integration queue, validation lanes, drift policy, watchdog policy.


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
    "name": "v7_alphaforge_xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p1"
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
    "writeSetDriftPolicy": "reject_or_handoff",
    "explain": [
      "stable_3 worktree mode: 3 workers, worktree isolation, integration queue",
      "Worktree isolation required for safe parallel execution",
      "All production execution requires PostgreSQL authoritative runtime state"
    ]
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
  "attemptLifecycle": {
    "modeSpecificLifecycles": {
      "worktree": {
        "initialState": "queued",
        "nonTerminalStates": [
          "queued",
          "leasing_worktree",
          "running",
          "validating",
          "waiting_for_validation_lane",
          "integration_queued",
          "integrating"
        ],
        "terminalStates": [
          "succeeded",
          "failed_retryable",
          "failed_final",
          "aborted",
          "timed_out",
          "quarantined",
          "handoff_required"
        ]
      }
    },
    "retryableTerminalStates": [
      "failed_retryable",
      "timed_out",
      "quarantined"
    ],
    "retryForbiddenFromNonTerminal": true,
    "deadlineRequiredForNonTerminalStates": true,
    "handoffRequiredCreatesQueueItem": true
  },
  "planLifecycle": {
    "completionPredicateRequired": true,
    "cannotCompleteWithRequiredNonTerminalWorkspaces": true,
    "cannotCompleteWithUnresolvedRequiredHandoff": true,
    "finalValidationRequiredBeforeCompleted": true,
    "states": [
      "created",
      "preflight",
      "running",
      "blocked_with_reason",
      "awaiting_handoff",
      "final_validation",
      "completed",
      "completed_with_warnings",
      "failed_final",
      "stopping",
      "stopped"
    ]
  },
  "actorPermissions": {
    "workspaceAttemptController": {
      "mayMutateAttemptState": true,
      "mayCreateRetryAttempt": true
    },
    "planSupervisor": {
      "mayMutatePlanState": true,
      "mayReserveSchedulerSlots": true
    },
    "executorActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayProducePatchArtifact": true,
      "mayEmitEvents": true
    },
    "validationActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayEmitEvents": true
    },
    "gitRunner": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true,
      "note": "May perform low-level git operations only when invoked by authorized repository mutation authority."
    },
    "leaseMonitor": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true
    },
    "retryPolicy": {
      "mayMutateAttemptState": false,
      "mayCreateRetryAttempt": false,
      "maySuggestRetry": true
    },
    "brainWorkers": {
      "mayMutateExecutionState": false,
      "mayEmitDiagnosis": true,
      "mayProposeAction": true
    },
    "diagnostics": {
      "mayMutateExecutionState": false,
      "mayEmitEvidence": true
    }
  },
  "admissionGate": {
    "required": true,
    "allEntrypointsMustUseGate": true,
    "coveredEntrypoints": [
      "cli_plan_run",
      "dashboard_run",
      "api_plan_run",
      "retry_endpoint",
      "cleanup_rerun_endpoint",
      "brain_worker_trigger",
      "overnight_runner",
      "proposal_executor"
    ],
    "rejectWhen": [
      "postgres_unavailable_for_authoritative_runtime",
      "json_runtime_fallback_detected",
      "repair_mode_autonomous_execution_disabled",
      "promotion_gates_missing",
      "unsafe_parallelism_requested",
      "execution_kernel_disabled",
      "state_authority_not_single"
    ]
  },
  "resourceCoordination": {
    "nestedLocksForbidden": true,
    "holdLockAcrossAwaitForbidden": true,
    "stateLocks": {
      "scope": "attempt",
      "maxHoldMs": 1000
    },
    "planLock": {
      "scope": "plan",
      "maxHoldMs": 1000,
      "purpose": "slot_reservation_only"
    },
    "gitRunner": {
      "mode": "queue",
      "repoMutationTimeoutMs": 60000,
      "lockBypassForbidden": true
    },
    "validationLanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    },
    "worktreeLeases": {
      "attemptScoped": true,
      "heartbeatRequired": true,
      "quarantineOnStale": true
    },
    "stateStore": {
      "writesThroughControllerOnly": true,
      "transactionOrWriteQueueRequired": true
    }
  },
  "deadlineWatchdog": {
    "required": true,
    "intervalSeconds": 15,
    "emitsEventsOnly": true,
    "eventType": "deadline_exceeded",
    "supervised": true,
    "onWatchdogUnavailable": "block_new_execution_or_downgrade"
  },
  "handoffQueue": {
    "required": true,
    "createdByStates": [
      "handoff_required"
    ],
    "allowedActions": [
      "retry_requested",
      "close_failed",
      "manual_resolution",
      "followup_plan_requested"
    ],
    "controllerMediatedRetryRequired": true
  },
  "boundedLiveness": {
    "required": true,
    "noIndefiniteWaits": true,
    "llm": {
      "providerRequestTimeoutMs": 120000,
      "streamIdleTimeoutMs": 300000,
      "workspaceOverallTimeoutMs": 1800000,
      "maxConsecutiveProviderTimeouts": 2,
      "onCircuitOpen": "fail_workspace_not_plan"
    },
    "validation": {
      "defaultTimeoutMs": 600000,
      "heavyTimeoutMs": 1200000,
      "killProcessTreeOnTimeout": true,
      "watchModeForbidden": true,
      "stdinClosed": true,
      "ciEnvRequired": true,
      "maxOutputBytes": 52428800
    },
    "git": {
      "repoMutationLockTimeoutMs": 60000,
      "lockBypassForbidden": true,
      "onLockTimeout": "fail_fast_and_retry_or_handoff"
    },
    "scheduler": {
      "stallDetectionEnabled": true,
      "noProgressTimeoutMs": 300000,
      "onNoProgress": "emit_blocked_reason"
    },
    "stateStore": {
      "transactionOrWriteQueueRequired": true,
      "atomicSnapshotRequired": true,
      "journalLineAtomicityRequired": true
    }
  },
  "llmRuntime": {
    "boundedProviderCallsRequired": true,
    "providerRequestTimeoutMs": 120000,
    "streamIdleTimeoutMs": 300000,
    "workspaceOverallTimeoutMs": 1800000,
    "circuitBreaker": {
      "enabled": true,
      "openAfterConsecutiveTimeouts": 2,
      "cooldownMs": 300000
    },
    "fallbackPolicy": {
      "enabled": false,
      "reason": "Patches must remain deterministic."
    }
  },
  "validationRuntime": {
    "managedRunnerRequired": true,
    "processGroupRequired": true,
    "killTreeOnTimeout": true,
    "maxOutputBytes": 52428800,
    "forbiddenInteractiveCommands": [
      "vitest --watch",
      "jest --watch",
      "npm run dev",
      "vite --host"
    ],
    "lanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    }
  },
  "validationPolicy": {
    "defaultMode": "deferred",
    "workspaceCompletionRequiresTargetCommand": false,
    "planCompletionRequiresFinalValidation": true,
    "heavyValidationDeferredByDefault": true,
    "allowWorkspaceImmediateValidation": true,
    "allowSmokeValidation": true,
    "watchModeForbidden": true,
    "finalValidationWorkspaceRequired": true,
    "finalRepairWorkspaceRecommended": true,
    "validationArtifactsRequired": true,
    "liveValidationVisibilityRequired": true
  },
  "planExecution": {
    "phase": "P1",
    "title": "Contracts & Alpha Data Contract",
    "mode": "implementation",
    "maxParallelWorkspaces": 3,
    "scheduling": {
      "continuous": true,
      "slotCount": 3,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": false,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "stable_3",
      "selectedMode": "stable_3",
      "modes": {
        "stable_3": {
          "executorType": "direct",
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false,
          "preserveExistingBehavior": true
        },
        "stable_6": {
          "executorType": "patch_transaction",
          "maxCodegenWorkers": 6,
          "patchIsolationRequired": true,
          "worktreeRequired": false,
          "patchCoordinatorRequired": true,
          "repositoryMutationAuthority": "patch_coordinator",
          "patchApplyLanes": 1,
          "singleRepositoryWriterRequired": true,
          "targetedValidationRequired": true,
          "finalIntegrationValidationRequired": true,
          "postgresRequired": true,
          "completionGateRequired": true
        },
        "experimental_worktree_6": {
          "executorType": "worktree",
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "explicitOptInRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true
    },
    "integrationQueue": {
      "enabled": true,
      "enabledForExecutorTypes": [
        "worktree"
      ],
      "processOneMergeAtATime": true,
      "stopOnMergeConflict": true,
      "requireWorkspaceValidationPass": true,
      "requireIntegrationValidationPass": true,
      "gitPushAllowed": false,
      "queuePriority": {
        "enabled": true,
        "defaultLevel": "normal",
        "levels": [
          "critical",
          "high",
          "normal",
          "low"
        ]
      },
      "queueOptimization": {
        "enabled": true,
        "strategy": "priority_then_fifo",
        "availableStrategies": [
          "priority_then_fifo",
          "critical_path_first",
          "weighted_shortest_job_first"
        ]
      }
    },
    "validation": {
      "globalValidationLockRequired": true,
      "targetedValidationEnabled": true,
      "finalIntegrationValidationRequired": true,
      "watchModeForbidden": true
    },
    "interactiveParallelismReview": {
      "enabled": true,
      "preflightRequired": true,
      "approvalRequiredBeforeRun": true,
      "allowDependencyEditing": true,
      "showEffectiveParallelism": true,
      "showSafeEffectiveParallelism": true,
      "showBatchPreview": true,
      "showSafeBatchPreview": true,
      "showCriticalPath": true,
      "showScaleModeReadiness": true,
      "warnWhenEffectiveParallelismBelowRequested": true,
      "warnWhenSafeParallelismBelowDagParallelism": true,
      "warnWhenScaleModePrerequisitesMissing": true,
      "persistApprovedGraph": true
    },
    "planIntake": {
      "enabled": true,
      "runOnUpload": true,
      "parserPriority": [
        "part3_json",
        "contractVersion_and_executionClass",
        "doctor",
        "execution_gate"
      ],
      "autoNormalize": true,
      "autoDoctor": true,
      "autoDagAnalysis": true,
      "autoOptimizationProposal": true,
      "autoQueuePriorityRecommendation": true,
      "autoWorkspaceSplitRecommendation": true,
      "autoDryRunForecast": true,
      "approvalRequiredBeforeApplyingOptimization": true,
      "approvalRequiredBeforeExecution": true
    },
    "optimizer": {
      "enabled": true,
      "mode": "advisory_until_approved",
      "objectives": [
        "maximize_safe_effective_parallelism",
        "minimize_critical_path",
        "minimize_same_file_conflicts",
        "minimize_validation_lock_contention",
        "prioritize_critical_path_queue_merges"
      ],
      "allowedPatches": [
        "dependencies",
        "parallelGroup",
        "queuePriority",
        "canRunWith",
        "cannotRunWith",
        "conflictScope",
        "workspaceSplitSuggestion",
        "workspaceMergeSuggestion"
      ],
      "forbiddenAutoPatches": [
        "allowedFiles",
        "forbiddenFiles",
        "capabilityManifest",
        "safety.hardStops",
        "forbiddenCommands"
      ]
    }
  },
  "controls": {
    "allowPause": true,
    "allowStop": true,
    "allowCancel": true,
    "resumePolicy": "paused_or_stopped_only"
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
      "git clean -fd",
      "vitest --watch",
      "jest --watch",
      "npm run dev"
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
  "parallelismReview": {
    "requestedMaxParallelWorkspaces": 3,
    "selectedScaleMode": "stable_3",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for parallel execution."
        },
        {
          "key": "integration_queue",
          "required": true,
          "met": true,
          "message": "Required for queued execution."
        },
        {
          "key": "validation_lock",
          "required": true,
          "met": true,
          "message": "Required for heavy validation."
        },
        {
          "key": "completion_gate",
          "required": true,
          "met": true,
          "message": "Required for completion hardening."
        }
      ]
    },
    "expectedDagEffectiveParallelismMin": 2,
    "expectedSafeEffectiveParallelismMin": 2,
    "dagEffectiveParallelism": null,
    "safeEffectiveParallelism": null,
    "preflightStatus": "required",
    "approvalState": "pending",
    "batchingStrategy": "dag_topological_batches_display_only",
    "safeBatchingStrategy": "dag_batches_with_p6_safety_constraints_display_only",
    "batchPreview": {
      "batches": [],
      "overallEffectiveParallelism": null,
      "criticalPath": [],
      "criticalPathLength": 0,
      "serializedTailLength": 0
    },
    "safeBatchPreview": {
      "batches": [],
      "overallSafeEffectiveParallelism": null,
      "bottlenecks": [],
      "blockedParallelismReasons": []
    },
    "optimizationReview": {
      "originalGraphHash": null,
      "proposedGraphHash": null,
      "approvedGraphHash": null,
      "originalDagEffectiveParallelism": null,
      "proposedDagEffectiveParallelism": null,
      "originalSafeEffectiveParallelism": null,
      "proposedSafeEffectiveParallelism": null,
      "criticalPathDelta": null,
      "serializedTailDelta": null,
      "suggestions": [],
      "approvalState": "pending"
    },
    "editableFields": [
      "workspaces[].dependencies",
      "workspaces[].parallelGroup",
      "workspaces[].dependencyReason",
      "workspaces[].parallelism.canRunWith",
      "workspaces[].parallelism.cannotRunWith",
      "workspaces[].parallelism.conflictScope",
      "workspaces[].integration.queuePriority",
      "workspaces[].integration.queueOptimizationNotes"
    ],
    "doctorWarnings": [
      "effective_parallelism_below_requested",
      "safe_parallelism_below_dag_parallelism",
      "fully_serialized_graph",
      "long_serialized_tail",
      "file_overlap_blocks_parallelism",
      "validation_lock_limits_parallelism",
      "integration_queue_serializes_merges",
      "scale_mode_prerequisites_missing",
      "worktree_isolation_required_for_scale",
      "queue_optimization_disabled_with_active_priority",
      "queue_priority_mismatch_with_configured_levels",
      "critical_path_workspace_has_low_priority",
      "optimizer_patch_without_approval"
    ],
    "persistedArtifacts": [
      "dependency_graph",
      "batch_preview",
      "safe_batch_preview",
      "critical_path",
      "scale_mode_readiness",
      "approved_dependency_patch",
      "approved_graph_hash",
      "queue_priority_snapshot",
      "queue_optimization_strategy",
      "queue_reorder_decision_log",
      "plan_intake_analysis",
      "optimizer_proposal",
      "graph_diff",
      "worktree_state",
      "lease_heartbeat_snapshots",
      "lease_reconciliation_log",
      "merge_priority_score_log",
      "empirical_write_set",
      "write_set_drift_report",
      "validation_lane_saturation_log"
    ]
  },
  "workspaces": [
    {
      "id": "P1.A",
      "title": "Feature Row Contract",
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
          "src/v7/alpha/contracts/**",
          "tests/v7/alpha/unit/contracts/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/contracts/**",
        "tests/v7/alpha/unit/contracts/**"
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
        "alpha_feature_table contract with all required fields is typed.",
        "feature_schema_version, symbol_encoding_family, symbol_universe_version are required fields."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "low",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/contracts/**",
          "tests/v7/alpha/unit/contracts/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P1.B",
      "title": "Label Row Contract",
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
          "src/v7/alpha/contracts/**",
          "tests/v7/alpha/unit/contracts/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/contracts/**",
        "tests/v7/alpha/unit/contracts/**"
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
        "alpha_label_table contract with long_R_net, short_R_net, best_action_label, gap_R is typed."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "low",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/contracts/**",
          "tests/v7/alpha/unit/contracts/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P1.C",
      "title": "Prediction & Bridge Contracts",
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
          "src/v7/alpha/contracts/**",
          "src/v7/alpha/runtime/**",
          "tests/v7/alpha/unit/contracts/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/contracts/**",
        "src/v7/alpha/runtime/**",
        "tests/v7/alpha/unit/contracts/**"
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
        "alpha_prediction_table contract typed.",
        "V7AnalysisRequest and AnalysisResult bridge contracts defined.",
        "ModelScope, Mode, and Action enums match V7 canonical values."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "low",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/contracts/**",
          "src/v7/alpha/runtime/**",
          "tests/v7/alpha/unit/contracts/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P1.D",
      "title": "Contract Tests",
      "dependencies": [
        "P1.A",
        "P1.B",
        "P1.C"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P1.A, P1.B, P1.C for foundation.",
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
          "tests/v7/alpha/unit/contracts/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "normal",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "tests/v7/alpha/unit/contracts/**"
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
        "All contracts have serialization round-trip tests.",
        "Schema version bumps are validated."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "low",
      "capabilityManifest": {
        "canEdit": [
          "tests/v7/alpha/unit/contracts/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
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
  "phase": "P1",
  "title": "Contracts & Alpha Data Contract",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "selectedRepairMode": null,
  "targetPromotionMode": "stable_6",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "schedulerRuntimeUse": "enabled",
  "primaryGoal": "Feature, label, prediction, artifact, and V7 bridge contracts.",
  "projectName": "v7_alphaforge_xgb",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresPatchIsolation": false,
  "requiresIntegrationQueue": true,
  "requiresPatchApplyQueue": false,
  "repositoryMutationAuthority": "worktree_integration",
  "queueOptimizationEnabled": true,
  "queueOptimizationStrategy": "priority_then_fifo",
  "continuousScheduling": true,
  "continuousSlotCount": 3,
  "safeEffectiveParallelismTarget": 2,
  "notInScope": [
    "External broker execution authority",
    "V7 runtime core modifications",
    "Non-XGBoost model families"
  ],
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
    "optimizer_patch_without_approval"
  ],
  "completionGate": "P1 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "P2"
}
```

---

## Review Hardening Requirements

* [ ] Data contract schema versioning

---

<!-- SOURCE: phase_plans/P2__runtime_simulation_adapter_and_r-label_engine.md -->

# P2 — Runtime Simulation Adapter & R-Label Engine

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P2`  
**One-line goal:** Side-effect-free simulation adapter and mode-specific R-label generation.  
**Why now:** Alpha labels must come from the same V7 simulation truth layer that evaluates runtime outcomes.  
**Blast radius:** src/v7/alpha/**, tests/v7/alpha/**, configs/v7/alpha/**, docs/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Execution class:** `implementation`  
**Execution automation:** `enabled`  
**Scale mode:** `stable_3`  
**Safe parallelism target:** `2`  
**Done when:** All workspaces pass acceptance criteria and phase JSON validates through Pi doctor.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P2` |
| Title | `Runtime Simulation Adapter & R-Label Engine` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Side-effect-free simulation adapter and mode-specific R-label generation.` |
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

Alpha labels must come from the same V7 simulation truth layer that evaluates runtime outcomes.

The V7 runtime already owns simulation. AlphaForge must not create a second hidden simulator. Instead, it must adapt V7 simulation profiles into a label-generation pipeline that produces R-multiple targets per mode.

This phase uses `stable_3` scale-aware execution. The executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

---

## 3. What Carried Over — Must Stay Stable

* [ ] Runtime owns orchestration, execution, persistence, lifecycle, and hard safety.
* [ ] Model owns alpha evidence only.
* [ ] Simulation truth defines labels and evaluation.
* [ ] No hidden deterministic veto or hidden fallback.
* [ ] NO_TRADE remains first-class.
* [ ] Features are canonical-state only.
* [ ] Labels are mode-specific.
* [ ] Datasets are mode-specific and temporally split.
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

The V7 runtime already owns simulation. AlphaForge must not create a second hidden simulator. Instead, it must adapt V7 simulation profiles into a label-generation pipeline that produces R-multiple targets per mode.

---

## 5. Current Failure State / Known Blockers

* `simulation_adapter` = not implemented.
* `mode_config_resolver` = not implemented.
* `r_label_builder` = not implemented.
* `golden_label_tests` = not implemented.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Worktree isolation violation | low | critical | Path scope checks; stop execution on escape |
| Integration queue merges unvalidated diff | medium | high | Require workspace validation and integration validation |
| Merge conflict blocks plan | medium | medium | Generate conflict handoff artifact and stop queue safely |
| Safe parallelism is lower than requested | medium | medium | Doctor warning; show bottleneck; use safe batch preview |
| Validation lock limits throughput | medium | medium | Scheduler reduces concurrency while heavy validation runs |
| High-risk workspace failure | medium | high | Rollback path defined; manual review gating |

---

## 7. Workstreams

### P2.A — Simulation Adapter

**Goal:** Side-effect-free adapter consumes /simulation engine outputs.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** medium
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Side-effect-free adapter consumes /simulation engine outputs.
* No hidden simulator created.
* Symbol+timestamp+mode → simulation result mapping works.

**File Scope:**
```text
src/v7/alpha/simulation_adapter/**
tests/v7/alpha/unit/simulation_adapter/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P2.B — Mode Config Resolver

**Goal:** Resolves SWING/SCALP/AGGRESSIVE_SCALP intervals from central config.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** medium
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Resolves SWING/SCALP/AGGRESSIVE_SCALP intervals from central config.
* SCALP primary=1h, context=4h, refinement=15m enforced.

**File Scope:**
```text
src/v7/alpha/config/**
tests/v7/alpha/unit/config/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P2.C — R Label Builder

**Goal:** long_R_net, short_R_net, best_action_label, gap_R computed per mode.

**Dependencies:** P2.A, P2.B
**Parallel Group:** batch_2
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* long_R_net, short_R_net, best_action_label, gap_R computed per mode.
* NO_TRACE is first-class label.
* min_action_edge and ambiguity_gap applied from mode config.

**File Scope:**
```text
src/v7/alpha/labels/**
tests/v7/alpha/unit/labels/**
```

**Isolation & Parallelism Notes:**
* Depends on P2.A, P2.B for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P2.D — Golden Label Tests

**Goal:** Golden dataset with known expected R values passes.

**Dependencies:** P2.C
**Parallel Group:** batch_2
**Risk Level:** medium
**Queue Priority:** normal
**Can run with:** None

**Requirements:
* Golden dataset with known expected R values passes.
* Regression test catches label drift.

**File Scope:**
```text
tests/v7/alpha/golden/**
```

**Isolation & Parallelism Notes:**
* Depends on P2.C for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.


---

## 8. Combined Implementation Order

```text
  Batch batch_1: P2.A + P2.B
  Batch batch_2: P2.C + P2.D
```

The dependency graph dictates that foundation workspaces run first, followed by parallel batches where dependencies permit. The DAG batch preview and safe batch preview may differ because of file overlap, validation lock pressure, or integration queue serialization.

---

## 9. Definition of Done

`P2` is complete when ALL are true:

* [ ] Side-effect-free adapter consumes /simulation engine outputs.
* [ ] Resolves SWING/SCALP/AGGRESSIVE_SCALP intervals from central config.
* [ ] long_R_net, short_R_net, best_action_label, gap_R computed per mode.
* [ ] Golden dataset with known expected R values passes.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation is valid for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] No forbidden commands or files were used.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Validation planner misses a required failure.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Disable worktree mode only if safe fallback is required.
4. Pause or disable integration queue processing.
5. Preserve `.pi/worktrees/{planExecId}/` for debugging.
6. Fall back to shared-working-tree execution if explicitly allowed.
7. Keep dashboard telemetry read-only if safe.
8. Revert phase commits independently if needed.

---

## 11. What Next Phase Inherits

`P4` inherits:

* `P2` execution contract with worktree mode awareness.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Workspace-level parallelism/isolation/integration/validation metadata.
* Review hardening invariants: SCALP interval authority (mode config resolver)

---

# Part 2 — Agent Brief

## Mission

Implement `P2` — Side-effect-free simulation adapter and mode-specific R-label generation.

The agent must optimize for safe parallelism, not maximum concurrency. Higher worker counts are allowed only when scale-mode readiness passes and the executor can preserve correctness through worktree isolation, integration queue, validation locks, and completion gates.



---

## Hard Requirements

1. All P2 workstreams must pass acceptance criteria.
2. Worktree isolation must be enabled for parallel workspaces.
3. Integration queue must serialize merges.
4. Global validation lock must be active for heavy validation.
5. Watch-mode validation is forbidden.
6. `git push` is forbidden.
7. Raw destructive cleanup is forbidden.
8. Do not exceed selected scale-mode worker cap (3).
9. Do not merge workspace output without passed workspace validation.
10. Do not mark the plan complete if integration validation fails.
11. Do not treat merge conflict as ordinary worker failure.
12. Do not start the next plan while integration queue state is dirty.

---

## Execution Policies

```yaml
repair_modes:
  manual_0: autonomous_execution_allowed: false, agent_may_mutate_repo: false
  stable_3: autonomous_execution_allowed: true,  agent_may_mutate_repo: true

execution_automation:
  autonomous_execution_enabled: true
  agent_may_mutate_repo: true
  agent_may_run_commands: true
  manual_patch_application_required: false
  human_approval_required_for_every_patch: false

bounded_liveness:
  no_indefinite_waits: true
  llm_provider_timeout_required: true
  llm_stream_idle_watchdog_required: true
  validation_timeout_required: true
  process_tree_kill_required: true
  git_lock_bypass_forbidden: true
  state_write_serialization_required: true

scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
  worktree_required: true
  integration_queue_required: true

validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true

queue_optimization:
  enabled_by_default: true
  default_strategy: priority_then_fifo
  priority_levels: [critical, high, normal, low]
```

---

## Safety Stops

* Dependency cycles
* Invalid dependency patches
* Worktree path escaping `.pi/worktrees`
* Integration merge without passed workspace validation
* Validation failure
* Merge conflict without handoff artifact
* Unsafe scale mode
* Queue starting next plan while integration queue is dirty
* Forbidden file access
* Secrets access
* `git push`
* Watch-mode validation
* `autonomous_execution_requested_during_repair_mode`
* `agent_repo_mutation_requested_during_manual_repair`
* `scheduler_enabled_before_executor_isolation_gate`
* `llm_call_without_provider_timeout`
* `validation_command_without_timeout`
* `git_lock_bypass_detected`
* `state_store_write_without_serialization`
* `workspace_patch_without_human_approval`
* `promotion_gate_failed_or_missing`


# Part 2.5 — v4 ExecutionKernel Doctrine

## 2.5.1 Single Authority Model

v4 replaces the previous executor-owned or multi-component execution state model with an ExecutionKernel model.

```text
Before v4:
  Scheduler, executor, validation runner, retry router, cleanup, lease monitor,
  diagnostics, and brain workers could each influence or write partial execution truth.

After v4:
  All actors emit events.
  WorkspaceAttemptController mutates attempt state.
  PlanSupervisor mutates plan state.
  PostgreSQL stores authoritative runtime truth.
```

## 2.5.2 ExecutionKernel Components

| Component | Responsibility | May mutate execution state? |
|---|---|---:|
| `ExecutionAdmissionGate` | Authorize or reject execution requests before runtime starts | No |
| `ExecutionProfileDeriver` | Convert intent to required mechanisms | No |
| `PlanSupervisor` | Own plan FSM, slot tokens, completion predicate, final validation | Yes, plan state only |
| `WorkspaceAttemptController` | Own attempt FSM, retries, terminalization, handoff creation | Yes, attempt state only |
| `StateStoreWriter` | Commit transitions with authority token | Yes, through token only |
| `AttemptEventJournal` | Append versioned event records | No state mutation by itself |
| `DeadlineWatchdog` | Detect expired attempts and emit events | No |
| `ExecutorActor` | Run LLM/tools/bash for an attempt | No |
| `ValidationActor` | Run validation with deadlines and process containment | No |
| `GitRunner` | Serialize Git repo mutations | No attempt state mutation |

## 2.5.3 Attempt FSM Doctrine

A v4 attempt is a bounded state machine. It cannot remain in a non-terminal state forever.

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
Failure paths: RUNNING+timeout -> TIMED_OUT, critical violation -> FAILED_FINAL
Terminal states: SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, TIMED_OUT, HANDOFF_REQUIRED
Retry is legal only after terminal state.
```

## 2.5.4 PostgreSQL Truth Doctrine

Runtime truth is PostgreSQL. JSON fallback is forbidden in production.

Allowed filesystem data: stdout/stderr logs, raw tool output, patch artifacts, handoff Markdown.
Forbidden as authoritative runtime truth: JSON state fallback, NDJSON-only journal, filesystem-only state.

## 2.5.5 Intent-Driven Plan Doctrine

v4 authors express what they want, not the low-level mechanism matrix.

Human-authored: `parallelism`, `safetyLevel`, `conflictRisk`, `deadlines`, `executionEnvironment`.
System-derived: worktree requirement, integration queue, validation lanes, drift policy, watchdog policy.


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
    "name": "v7_alphaforge_xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p2"
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
    "writeSetDriftPolicy": "reject_or_handoff",
    "explain": [
      "stable_3 worktree mode: 3 workers, worktree isolation, integration queue",
      "Worktree isolation required for safe parallel execution",
      "All production execution requires PostgreSQL authoritative runtime state"
    ]
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
  "attemptLifecycle": {
    "modeSpecificLifecycles": {
      "worktree": {
        "initialState": "queued",
        "nonTerminalStates": [
          "queued",
          "leasing_worktree",
          "running",
          "validating",
          "waiting_for_validation_lane",
          "integration_queued",
          "integrating"
        ],
        "terminalStates": [
          "succeeded",
          "failed_retryable",
          "failed_final",
          "aborted",
          "timed_out",
          "quarantined",
          "handoff_required"
        ]
      }
    },
    "retryableTerminalStates": [
      "failed_retryable",
      "timed_out",
      "quarantined"
    ],
    "retryForbiddenFromNonTerminal": true,
    "deadlineRequiredForNonTerminalStates": true,
    "handoffRequiredCreatesQueueItem": true
  },
  "planLifecycle": {
    "completionPredicateRequired": true,
    "cannotCompleteWithRequiredNonTerminalWorkspaces": true,
    "cannotCompleteWithUnresolvedRequiredHandoff": true,
    "finalValidationRequiredBeforeCompleted": true,
    "states": [
      "created",
      "preflight",
      "running",
      "blocked_with_reason",
      "awaiting_handoff",
      "final_validation",
      "completed",
      "completed_with_warnings",
      "failed_final",
      "stopping",
      "stopped"
    ]
  },
  "actorPermissions": {
    "workspaceAttemptController": {
      "mayMutateAttemptState": true,
      "mayCreateRetryAttempt": true
    },
    "planSupervisor": {
      "mayMutatePlanState": true,
      "mayReserveSchedulerSlots": true
    },
    "executorActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayProducePatchArtifact": true,
      "mayEmitEvents": true
    },
    "validationActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayEmitEvents": true
    },
    "gitRunner": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true,
      "note": "May perform low-level git operations only when invoked by authorized repository mutation authority."
    },
    "leaseMonitor": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true
    },
    "retryPolicy": {
      "mayMutateAttemptState": false,
      "mayCreateRetryAttempt": false,
      "maySuggestRetry": true
    },
    "brainWorkers": {
      "mayMutateExecutionState": false,
      "mayEmitDiagnosis": true,
      "mayProposeAction": true
    },
    "diagnostics": {
      "mayMutateExecutionState": false,
      "mayEmitEvidence": true
    }
  },
  "admissionGate": {
    "required": true,
    "allEntrypointsMustUseGate": true,
    "coveredEntrypoints": [
      "cli_plan_run",
      "dashboard_run",
      "api_plan_run",
      "retry_endpoint",
      "cleanup_rerun_endpoint",
      "brain_worker_trigger",
      "overnight_runner",
      "proposal_executor"
    ],
    "rejectWhen": [
      "postgres_unavailable_for_authoritative_runtime",
      "json_runtime_fallback_detected",
      "repair_mode_autonomous_execution_disabled",
      "promotion_gates_missing",
      "unsafe_parallelism_requested",
      "execution_kernel_disabled",
      "state_authority_not_single"
    ]
  },
  "resourceCoordination": {
    "nestedLocksForbidden": true,
    "holdLockAcrossAwaitForbidden": true,
    "stateLocks": {
      "scope": "attempt",
      "maxHoldMs": 1000
    },
    "planLock": {
      "scope": "plan",
      "maxHoldMs": 1000,
      "purpose": "slot_reservation_only"
    },
    "gitRunner": {
      "mode": "queue",
      "repoMutationTimeoutMs": 60000,
      "lockBypassForbidden": true
    },
    "validationLanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    },
    "worktreeLeases": {
      "attemptScoped": true,
      "heartbeatRequired": true,
      "quarantineOnStale": true
    },
    "stateStore": {
      "writesThroughControllerOnly": true,
      "transactionOrWriteQueueRequired": true
    }
  },
  "deadlineWatchdog": {
    "required": true,
    "intervalSeconds": 15,
    "emitsEventsOnly": true,
    "eventType": "deadline_exceeded",
    "supervised": true,
    "onWatchdogUnavailable": "block_new_execution_or_downgrade"
  },
  "handoffQueue": {
    "required": true,
    "createdByStates": [
      "handoff_required"
    ],
    "allowedActions": [
      "retry_requested",
      "close_failed",
      "manual_resolution",
      "followup_plan_requested"
    ],
    "controllerMediatedRetryRequired": true
  },
  "boundedLiveness": {
    "required": true,
    "noIndefiniteWaits": true,
    "llm": {
      "providerRequestTimeoutMs": 120000,
      "streamIdleTimeoutMs": 300000,
      "workspaceOverallTimeoutMs": 1800000,
      "maxConsecutiveProviderTimeouts": 2,
      "onCircuitOpen": "fail_workspace_not_plan"
    },
    "validation": {
      "defaultTimeoutMs": 600000,
      "heavyTimeoutMs": 1200000,
      "killProcessTreeOnTimeout": true,
      "watchModeForbidden": true,
      "stdinClosed": true,
      "ciEnvRequired": true,
      "maxOutputBytes": 52428800
    },
    "git": {
      "repoMutationLockTimeoutMs": 60000,
      "lockBypassForbidden": true,
      "onLockTimeout": "fail_fast_and_retry_or_handoff"
    },
    "scheduler": {
      "stallDetectionEnabled": true,
      "noProgressTimeoutMs": 300000,
      "onNoProgress": "emit_blocked_reason"
    },
    "stateStore": {
      "transactionOrWriteQueueRequired": true,
      "atomicSnapshotRequired": true,
      "journalLineAtomicityRequired": true
    }
  },
  "llmRuntime": {
    "boundedProviderCallsRequired": true,
    "providerRequestTimeoutMs": 120000,
    "streamIdleTimeoutMs": 300000,
    "workspaceOverallTimeoutMs": 1800000,
    "circuitBreaker": {
      "enabled": true,
      "openAfterConsecutiveTimeouts": 2,
      "cooldownMs": 300000
    },
    "fallbackPolicy": {
      "enabled": false,
      "reason": "Patches must remain deterministic."
    }
  },
  "validationRuntime": {
    "managedRunnerRequired": true,
    "processGroupRequired": true,
    "killTreeOnTimeout": true,
    "maxOutputBytes": 52428800,
    "forbiddenInteractiveCommands": [
      "vitest --watch",
      "jest --watch",
      "npm run dev",
      "vite --host"
    ],
    "lanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    }
  },
  "validationPolicy": {
    "defaultMode": "deferred",
    "workspaceCompletionRequiresTargetCommand": false,
    "planCompletionRequiresFinalValidation": true,
    "heavyValidationDeferredByDefault": true,
    "allowWorkspaceImmediateValidation": true,
    "allowSmokeValidation": true,
    "watchModeForbidden": true,
    "finalValidationWorkspaceRequired": true,
    "finalRepairWorkspaceRecommended": true,
    "validationArtifactsRequired": true,
    "liveValidationVisibilityRequired": true
  },
  "planExecution": {
    "phase": "P2",
    "title": "Runtime Simulation Adapter & R-Label Engine",
    "mode": "implementation",
    "maxParallelWorkspaces": 3,
    "scheduling": {
      "continuous": true,
      "slotCount": 3,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": false,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "stable_3",
      "selectedMode": "stable_3",
      "modes": {
        "stable_3": {
          "executorType": "direct",
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false,
          "preserveExistingBehavior": true
        },
        "stable_6": {
          "executorType": "patch_transaction",
          "maxCodegenWorkers": 6,
          "patchIsolationRequired": true,
          "worktreeRequired": false,
          "patchCoordinatorRequired": true,
          "repositoryMutationAuthority": "patch_coordinator",
          "patchApplyLanes": 1,
          "singleRepositoryWriterRequired": true,
          "targetedValidationRequired": true,
          "finalIntegrationValidationRequired": true,
          "postgresRequired": true,
          "completionGateRequired": true
        },
        "experimental_worktree_6": {
          "executorType": "worktree",
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "explicitOptInRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true
    },
    "integrationQueue": {
      "enabled": true,
      "enabledForExecutorTypes": [
        "worktree"
      ],
      "processOneMergeAtATime": true,
      "stopOnMergeConflict": true,
      "requireWorkspaceValidationPass": true,
      "requireIntegrationValidationPass": true,
      "gitPushAllowed": false,
      "queuePriority": {
        "enabled": true,
        "defaultLevel": "normal",
        "levels": [
          "critical",
          "high",
          "normal",
          "low"
        ]
      },
      "queueOptimization": {
        "enabled": true,
        "strategy": "priority_then_fifo",
        "availableStrategies": [
          "priority_then_fifo",
          "critical_path_first",
          "weighted_shortest_job_first"
        ]
      }
    },
    "validation": {
      "globalValidationLockRequired": true,
      "targetedValidationEnabled": true,
      "finalIntegrationValidationRequired": true,
      "watchModeForbidden": true
    },
    "interactiveParallelismReview": {
      "enabled": true,
      "preflightRequired": true,
      "approvalRequiredBeforeRun": true,
      "allowDependencyEditing": true,
      "showEffectiveParallelism": true,
      "showSafeEffectiveParallelism": true,
      "showBatchPreview": true,
      "showSafeBatchPreview": true,
      "showCriticalPath": true,
      "showScaleModeReadiness": true,
      "warnWhenEffectiveParallelismBelowRequested": true,
      "warnWhenSafeParallelismBelowDagParallelism": true,
      "warnWhenScaleModePrerequisitesMissing": true,
      "persistApprovedGraph": true
    },
    "planIntake": {
      "enabled": true,
      "runOnUpload": true,
      "parserPriority": [
        "part3_json",
        "contractVersion_and_executionClass",
        "doctor",
        "execution_gate"
      ],
      "autoNormalize": true,
      "autoDoctor": true,
      "autoDagAnalysis": true,
      "autoOptimizationProposal": true,
      "autoQueuePriorityRecommendation": true,
      "autoWorkspaceSplitRecommendation": true,
      "autoDryRunForecast": true,
      "approvalRequiredBeforeApplyingOptimization": true,
      "approvalRequiredBeforeExecution": true
    },
    "optimizer": {
      "enabled": true,
      "mode": "advisory_until_approved",
      "objectives": [
        "maximize_safe_effective_parallelism",
        "minimize_critical_path",
        "minimize_same_file_conflicts",
        "minimize_validation_lock_contention",
        "prioritize_critical_path_queue_merges"
      ],
      "allowedPatches": [
        "dependencies",
        "parallelGroup",
        "queuePriority",
        "canRunWith",
        "cannotRunWith",
        "conflictScope",
        "workspaceSplitSuggestion",
        "workspaceMergeSuggestion"
      ],
      "forbiddenAutoPatches": [
        "allowedFiles",
        "forbiddenFiles",
        "capabilityManifest",
        "safety.hardStops",
        "forbiddenCommands"
      ]
    }
  },
  "controls": {
    "allowPause": true,
    "allowStop": true,
    "allowCancel": true,
    "resumePolicy": "paused_or_stopped_only"
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
      "git clean -fd",
      "vitest --watch",
      "jest --watch",
      "npm run dev"
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
  "parallelismReview": {
    "requestedMaxParallelWorkspaces": 3,
    "selectedScaleMode": "stable_3",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for parallel execution."
        },
        {
          "key": "integration_queue",
          "required": true,
          "met": true,
          "message": "Required for queued execution."
        },
        {
          "key": "validation_lock",
          "required": true,
          "met": true,
          "message": "Required for heavy validation."
        },
        {
          "key": "completion_gate",
          "required": true,
          "met": true,
          "message": "Required for completion hardening."
        }
      ]
    },
    "expectedDagEffectiveParallelismMin": 2,
    "expectedSafeEffectiveParallelismMin": 2,
    "dagEffectiveParallelism": null,
    "safeEffectiveParallelism": null,
    "preflightStatus": "required",
    "approvalState": "pending",
    "batchingStrategy": "dag_topological_batches_display_only",
    "safeBatchingStrategy": "dag_batches_with_p6_safety_constraints_display_only",
    "batchPreview": {
      "batches": [],
      "overallEffectiveParallelism": null,
      "criticalPath": [],
      "criticalPathLength": 0,
      "serializedTailLength": 0
    },
    "safeBatchPreview": {
      "batches": [],
      "overallSafeEffectiveParallelism": null,
      "bottlenecks": [],
      "blockedParallelismReasons": []
    },
    "optimizationReview": {
      "originalGraphHash": null,
      "proposedGraphHash": null,
      "approvedGraphHash": null,
      "originalDagEffectiveParallelism": null,
      "proposedDagEffectiveParallelism": null,
      "originalSafeEffectiveParallelism": null,
      "proposedSafeEffectiveParallelism": null,
      "criticalPathDelta": null,
      "serializedTailDelta": null,
      "suggestions": [],
      "approvalState": "pending"
    },
    "editableFields": [
      "workspaces[].dependencies",
      "workspaces[].parallelGroup",
      "workspaces[].dependencyReason",
      "workspaces[].parallelism.canRunWith",
      "workspaces[].parallelism.cannotRunWith",
      "workspaces[].parallelism.conflictScope",
      "workspaces[].integration.queuePriority",
      "workspaces[].integration.queueOptimizationNotes"
    ],
    "doctorWarnings": [
      "effective_parallelism_below_requested",
      "safe_parallelism_below_dag_parallelism",
      "fully_serialized_graph",
      "long_serialized_tail",
      "file_overlap_blocks_parallelism",
      "validation_lock_limits_parallelism",
      "integration_queue_serializes_merges",
      "scale_mode_prerequisites_missing",
      "worktree_isolation_required_for_scale",
      "queue_optimization_disabled_with_active_priority",
      "queue_priority_mismatch_with_configured_levels",
      "critical_path_workspace_has_low_priority",
      "optimizer_patch_without_approval"
    ],
    "persistedArtifacts": [
      "dependency_graph",
      "batch_preview",
      "safe_batch_preview",
      "critical_path",
      "scale_mode_readiness",
      "approved_dependency_patch",
      "approved_graph_hash",
      "queue_priority_snapshot",
      "queue_optimization_strategy",
      "queue_reorder_decision_log",
      "plan_intake_analysis",
      "optimizer_proposal",
      "graph_diff",
      "worktree_state",
      "lease_heartbeat_snapshots",
      "lease_reconciliation_log",
      "merge_priority_score_log",
      "empirical_write_set",
      "write_set_drift_report",
      "validation_lane_saturation_log"
    ]
  },
  "workspaces": [
    {
      "id": "P2.A",
      "title": "Simulation Adapter",
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
          "src/v7/alpha/simulation_adapter/**",
          "tests/v7/alpha/unit/simulation_adapter/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/simulation_adapter/**",
        "tests/v7/alpha/unit/simulation_adapter/**"
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
        "Side-effect-free adapter consumes /simulation engine outputs.",
        "No hidden simulator created.",
        "Symbol+timestamp+mode \u2192 simulation result mapping works."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/simulation_adapter/**",
          "tests/v7/alpha/unit/simulation_adapter/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P2.B",
      "title": "Mode Config Resolver",
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
          "src/v7/alpha/config/**",
          "tests/v7/alpha/unit/config/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/config/**",
        "tests/v7/alpha/unit/config/**"
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
        "Resolves SWING/SCALP/AGGRESSIVE_SCALP intervals from central config.",
        "SCALP primary=1h, context=4h, refinement=15m enforced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/config/**",
          "tests/v7/alpha/unit/config/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P2.C",
      "title": "R Label Builder",
      "dependencies": [
        "P2.A",
        "P2.B"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P2.A, P2.B for foundation.",
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
          "src/v7/alpha/labels/**",
          "tests/v7/alpha/unit/labels/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/labels/**",
        "tests/v7/alpha/unit/labels/**"
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
        "long_R_net, short_R_net, best_action_label, gap_R computed per mode.",
        "NO_TRACE is first-class label.",
        "min_action_edge and ambiguity_gap applied from mode config."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/labels/**",
          "tests/v7/alpha/unit/labels/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P2.D",
      "title": "Golden Label Tests",
      "dependencies": [
        "P2.C"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P2.C for foundation.",
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
          "tests/v7/alpha/golden/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "normal",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "tests/v7/alpha/golden/**"
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
        "Golden dataset with known expected R values passes.",
        "Regression test catches label drift."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "tests/v7/alpha/golden/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
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
  "phase": "P2",
  "title": "Runtime Simulation Adapter & R-Label Engine",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "selectedRepairMode": null,
  "targetPromotionMode": "stable_6",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "schedulerRuntimeUse": "enabled",
  "primaryGoal": "Side-effect-free simulation adapter and mode-specific R-label generation.",
  "projectName": "v7_alphaforge_xgb",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresPatchIsolation": false,
  "requiresIntegrationQueue": true,
  "requiresPatchApplyQueue": false,
  "repositoryMutationAuthority": "worktree_integration",
  "queueOptimizationEnabled": true,
  "queueOptimizationStrategy": "priority_then_fifo",
  "continuousScheduling": true,
  "continuousSlotCount": 3,
  "safeEffectiveParallelismTarget": 2,
  "notInScope": [
    "External broker execution authority",
    "V7 runtime core modifications",
    "Non-XGBoost model families"
  ],
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
    "optimizer_patch_without_approval"
  ],
  "completionGate": "P2 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "P4"
}
```

---

## Review Hardening Requirements

* [ ] SCALP interval authority (mode config resolver)

---

<!-- SOURCE: phase_plans/P3__multi-timeframe_feature_engine_and_unsupervised_context.md -->

# P3 — Multi-Timeframe Feature Engine & Unsupervised Context

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P3`  
**One-line goal:** Primary/context/refinement deterministic features and optional anomaly/regime features.  
**Why now:** Model quality depends on leakage-safe, mode-aware features computed from canonical state only.  
**Blast radius:** src/v7/alpha/**, tests/v7/alpha/**, configs/v7/alpha/**, docs/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Execution class:** `implementation`  
**Execution automation:** `enabled`  
**Scale mode:** `stable_3`  
**Safe parallelism target:** `2`  
**Done when:** All workspaces pass acceptance criteria and phase JSON validates through Pi doctor.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P3` |
| Title | `Multi-Timeframe Feature Engine & Unsupervised Context` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Primary/context/refinement deterministic features and optional anomaly/regime features.` |
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

Model quality depends on leakage-safe, mode-aware features computed from canonical state only.

Features must be computed from canonical state without future leakage. Unsupervised context layers (anomaly, regime) are allowed only as fold-scoped feature producers, never as hidden veto or execution authority.

This phase uses `stable_3` scale-aware execution. The executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

---

## 3. What Carried Over — Must Stay Stable

* [ ] Runtime owns orchestration, execution, persistence, lifecycle, and hard safety.
* [ ] Model owns alpha evidence only.
* [ ] Simulation truth defines labels and evaluation.
* [ ] No hidden deterministic veto or hidden fallback.
* [ ] NO_TRADE remains first-class.
* [ ] Features are canonical-state only.
* [ ] Labels are mode-specific.
* [ ] Datasets are mode-specific and temporally split.
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

Features must be computed from canonical state without future leakage. Unsupervised context layers (anomaly, regime) are allowed only as fold-scoped feature producers, never as hidden veto or execution authority.

---

## 5. Current Failure State / Known Blockers

* `feature_engine` = not implemented.
* `multi_timeframe_joiner` = not implemented.
* `unsupervised_context` = not implemented.
* `fold_scoped_anomaly_guard` = not implemented.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Worktree isolation violation | low | critical | Path scope checks; stop execution on escape |
| Integration queue merges unvalidated diff | medium | high | Require workspace validation and integration validation |
| Merge conflict blocks plan | medium | medium | Generate conflict handoff artifact and stop queue safely |
| Safe parallelism is lower than requested | medium | medium | Doctor warning; show bottleneck; use safe batch preview |
| Validation lock limits throughput | medium | medium | Scheduler reduces concurrency while heavy validation runs |
| High-risk workspace failure | medium | high | Rollback path defined; manual review gating |

---

## 7. Workstreams

### P3.A — Deterministic Features

**Goal:** Primary interval features (return, volatility, ATR, RSI, etc.) work.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** medium
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Primary interval features (return, volatility, ATR, RSI, etc.) work.
* Context interval trend/regime features work.
* Refinement entry-timing features work.

**File Scope:**
```text
src/v7/alpha/features/**
tests/v7/alpha/unit/features/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P3.B — Multi-Timeframe Join

**Goal:** Canonical state built from primary/context/refinement windows.

**Dependencies:** P3.A
**Parallel Group:** batch_2
**Risk Level:** medium
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Canonical state built from primary/context/refinement windows.
* Timestamps aligned correctly per mode config.

**File Scope:**
```text
src/v7/alpha/features/**
tests/v7/alpha/unit/features/**
```

**Isolation & Parallelism Notes:**
* Depends on P3.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P3.C — Unsupervised Context

**Goal:** Isolation Forest, anomaly_score, regime_id feature producers exist.

**Dependencies:** P3.A
**Parallel Group:** batch_2
**Risk Level:** high
**Queue Priority:** high
**Can run with:** None

**Requirements:
* Isolation Forest, anomaly_score, regime_id feature producers exist.
* Fold-scoped fitting enforced (H1).

**File Scope:**
```text
src/v7/alpha/anomaly/**
tests/v7/alpha/unit/anomaly/**
```

**Isolation & Parallelism Notes:**
* Depends on P3.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P3.D — Feature Tests

**Goal:** No future leakage in features.

**Dependencies:** P3.A, P3.B, P3.C
**Parallel Group:** batch_3
**Risk Level:** medium
**Queue Priority:** normal
**Can run with:** None

**Requirements:
* No future leakage in features.
* Feature schema versioning works.

**File Scope:**
```text
tests/v7/alpha/unit/features/**
```

**Isolation & Parallelism Notes:**
* Depends on P3.A, P3.B, P3.C for foundation.
* Expected batch: batch_3
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P3.E — Fold-Scoped Anomaly Fit Guard

**Goal:** Rejects rows where anomaly fit window crosses fold boundary.

**Dependencies:** P3.C
**Parallel Group:** batch_3
**Risk Level:** high
**Queue Priority:** high
**Can run with:** None

**Requirements:
* Rejects rows where anomaly fit window crosses fold boundary.
* Anomaly lineage fields stored per row.

**File Scope:**
```text
src/v7/alpha/anomaly/**
tests/v7/alpha/integration/**
```

**Isolation & Parallelism Notes:**
* Depends on P3.C for foundation.
* Expected batch: batch_3
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.


---

## 8. Combined Implementation Order

```text
  Batch batch_1: P3.A
  Batch batch_2: P3.B + P3.C
  Batch batch_3: P3.D + P3.E
```

The dependency graph dictates that foundation workspaces run first, followed by parallel batches where dependencies permit. The DAG batch preview and safe batch preview may differ because of file overlap, validation lock pressure, or integration queue serialization.

---

## 9. Definition of Done

`P3` is complete when ALL are true:

* [ ] Primary interval features (return, volatility, ATR, RSI, etc.) work.
* [ ] Canonical state built from primary/context/refinement windows.
* [ ] Isolation Forest, anomaly_score, regime_id feature producers exist.
* [ ] No future leakage in features.
* [ ] Rejects rows where anomaly fit window crosses fold boundary.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation is valid for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] No forbidden commands or files were used.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Validation planner misses a required failure.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Disable worktree mode only if safe fallback is required.
4. Pause or disable integration queue processing.
5. Preserve `.pi/worktrees/{planExecId}/` for debugging.
6. Fall back to shared-working-tree execution if explicitly allowed.
7. Keep dashboard telemetry read-only if safe.
8. Revert phase commits independently if needed.

---

## 11. What Next Phase Inherits

`P4` inherits:

* `P3` execution contract with worktree mode awareness.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Workspace-level parallelism/isolation/integration/validation metadata.
* Review hardening invariants: Fold-scoped anomaly fitting, Symbol encoding future-proofing

---

# Part 2 — Agent Brief

## Mission

Implement `P3` — Primary/context/refinement deterministic features and optional anomaly/regime features.

The agent must optimize for safe parallelism, not maximum concurrency. Higher worker counts are allowed only when scale-mode readiness passes and the executor can preserve correctness through worktree isolation, integration queue, validation locks, and completion gates.



---

## Hard Requirements

1. All P3 workstreams must pass acceptance criteria.
2. Worktree isolation must be enabled for parallel workspaces.
3. Integration queue must serialize merges.
4. Global validation lock must be active for heavy validation.
5. Watch-mode validation is forbidden.
6. `git push` is forbidden.
7. Raw destructive cleanup is forbidden.
8. Do not exceed selected scale-mode worker cap (3).
9. Do not merge workspace output without passed workspace validation.
10. Do not mark the plan complete if integration validation fails.
11. Do not treat merge conflict as ordinary worker failure.
12. Do not start the next plan while integration queue state is dirty.

---

## Execution Policies

```yaml
repair_modes:
  manual_0: autonomous_execution_allowed: false, agent_may_mutate_repo: false
  stable_3: autonomous_execution_allowed: true,  agent_may_mutate_repo: true

execution_automation:
  autonomous_execution_enabled: true
  agent_may_mutate_repo: true
  agent_may_run_commands: true
  manual_patch_application_required: false
  human_approval_required_for_every_patch: false

bounded_liveness:
  no_indefinite_waits: true
  llm_provider_timeout_required: true
  llm_stream_idle_watchdog_required: true
  validation_timeout_required: true
  process_tree_kill_required: true
  git_lock_bypass_forbidden: true
  state_write_serialization_required: true

scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
  worktree_required: true
  integration_queue_required: true

validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true

queue_optimization:
  enabled_by_default: true
  default_strategy: priority_then_fifo
  priority_levels: [critical, high, normal, low]
```

---

## Safety Stops

* Dependency cycles
* Invalid dependency patches
* Worktree path escaping `.pi/worktrees`
* Integration merge without passed workspace validation
* Validation failure
* Merge conflict without handoff artifact
* Unsafe scale mode
* Queue starting next plan while integration queue is dirty
* Forbidden file access
* Secrets access
* `git push`
* Watch-mode validation
* `autonomous_execution_requested_during_repair_mode`
* `agent_repo_mutation_requested_during_manual_repair`
* `scheduler_enabled_before_executor_isolation_gate`
* `llm_call_without_provider_timeout`
* `validation_command_without_timeout`
* `git_lock_bypass_detected`
* `state_store_write_without_serialization`
* `workspace_patch_without_human_approval`
* `promotion_gate_failed_or_missing`


# Part 2.5 — v4 ExecutionKernel Doctrine

## 2.5.1 Single Authority Model

v4 replaces the previous executor-owned or multi-component execution state model with an ExecutionKernel model.

```text
Before v4:
  Scheduler, executor, validation runner, retry router, cleanup, lease monitor,
  diagnostics, and brain workers could each influence or write partial execution truth.

After v4:
  All actors emit events.
  WorkspaceAttemptController mutates attempt state.
  PlanSupervisor mutates plan state.
  PostgreSQL stores authoritative runtime truth.
```

## 2.5.2 ExecutionKernel Components

| Component | Responsibility | May mutate execution state? |
|---|---|---:|
| `ExecutionAdmissionGate` | Authorize or reject execution requests before runtime starts | No |
| `ExecutionProfileDeriver` | Convert intent to required mechanisms | No |
| `PlanSupervisor` | Own plan FSM, slot tokens, completion predicate, final validation | Yes, plan state only |
| `WorkspaceAttemptController` | Own attempt FSM, retries, terminalization, handoff creation | Yes, attempt state only |
| `StateStoreWriter` | Commit transitions with authority token | Yes, through token only |
| `AttemptEventJournal` | Append versioned event records | No state mutation by itself |
| `DeadlineWatchdog` | Detect expired attempts and emit events | No |
| `ExecutorActor` | Run LLM/tools/bash for an attempt | No |
| `ValidationActor` | Run validation with deadlines and process containment | No |
| `GitRunner` | Serialize Git repo mutations | No attempt state mutation |

## 2.5.3 Attempt FSM Doctrine

A v4 attempt is a bounded state machine. It cannot remain in a non-terminal state forever.

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
Failure paths: RUNNING+timeout -> TIMED_OUT, critical violation -> FAILED_FINAL
Terminal states: SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, TIMED_OUT, HANDOFF_REQUIRED
Retry is legal only after terminal state.
```

## 2.5.4 PostgreSQL Truth Doctrine

Runtime truth is PostgreSQL. JSON fallback is forbidden in production.

Allowed filesystem data: stdout/stderr logs, raw tool output, patch artifacts, handoff Markdown.
Forbidden as authoritative runtime truth: JSON state fallback, NDJSON-only journal, filesystem-only state.

## 2.5.5 Intent-Driven Plan Doctrine

v4 authors express what they want, not the low-level mechanism matrix.

Human-authored: `parallelism`, `safetyLevel`, `conflictRisk`, `deadlines`, `executionEnvironment`.
System-derived: worktree requirement, integration queue, validation lanes, drift policy, watchdog policy.


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
    "name": "v7_alphaforge_xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p3"
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
    "writeSetDriftPolicy": "reject_or_handoff",
    "explain": [
      "stable_3 worktree mode: 3 workers, worktree isolation, integration queue",
      "Worktree isolation required for safe parallel execution",
      "All production execution requires PostgreSQL authoritative runtime state"
    ]
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
  "attemptLifecycle": {
    "modeSpecificLifecycles": {
      "worktree": {
        "initialState": "queued",
        "nonTerminalStates": [
          "queued",
          "leasing_worktree",
          "running",
          "validating",
          "waiting_for_validation_lane",
          "integration_queued",
          "integrating"
        ],
        "terminalStates": [
          "succeeded",
          "failed_retryable",
          "failed_final",
          "aborted",
          "timed_out",
          "quarantined",
          "handoff_required"
        ]
      }
    },
    "retryableTerminalStates": [
      "failed_retryable",
      "timed_out",
      "quarantined"
    ],
    "retryForbiddenFromNonTerminal": true,
    "deadlineRequiredForNonTerminalStates": true,
    "handoffRequiredCreatesQueueItem": true
  },
  "planLifecycle": {
    "completionPredicateRequired": true,
    "cannotCompleteWithRequiredNonTerminalWorkspaces": true,
    "cannotCompleteWithUnresolvedRequiredHandoff": true,
    "finalValidationRequiredBeforeCompleted": true,
    "states": [
      "created",
      "preflight",
      "running",
      "blocked_with_reason",
      "awaiting_handoff",
      "final_validation",
      "completed",
      "completed_with_warnings",
      "failed_final",
      "stopping",
      "stopped"
    ]
  },
  "actorPermissions": {
    "workspaceAttemptController": {
      "mayMutateAttemptState": true,
      "mayCreateRetryAttempt": true
    },
    "planSupervisor": {
      "mayMutatePlanState": true,
      "mayReserveSchedulerSlots": true
    },
    "executorActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayProducePatchArtifact": true,
      "mayEmitEvents": true
    },
    "validationActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayEmitEvents": true
    },
    "gitRunner": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true,
      "note": "May perform low-level git operations only when invoked by authorized repository mutation authority."
    },
    "leaseMonitor": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true
    },
    "retryPolicy": {
      "mayMutateAttemptState": false,
      "mayCreateRetryAttempt": false,
      "maySuggestRetry": true
    },
    "brainWorkers": {
      "mayMutateExecutionState": false,
      "mayEmitDiagnosis": true,
      "mayProposeAction": true
    },
    "diagnostics": {
      "mayMutateExecutionState": false,
      "mayEmitEvidence": true
    }
  },
  "admissionGate": {
    "required": true,
    "allEntrypointsMustUseGate": true,
    "coveredEntrypoints": [
      "cli_plan_run",
      "dashboard_run",
      "api_plan_run",
      "retry_endpoint",
      "cleanup_rerun_endpoint",
      "brain_worker_trigger",
      "overnight_runner",
      "proposal_executor"
    ],
    "rejectWhen": [
      "postgres_unavailable_for_authoritative_runtime",
      "json_runtime_fallback_detected",
      "repair_mode_autonomous_execution_disabled",
      "promotion_gates_missing",
      "unsafe_parallelism_requested",
      "execution_kernel_disabled",
      "state_authority_not_single"
    ]
  },
  "resourceCoordination": {
    "nestedLocksForbidden": true,
    "holdLockAcrossAwaitForbidden": true,
    "stateLocks": {
      "scope": "attempt",
      "maxHoldMs": 1000
    },
    "planLock": {
      "scope": "plan",
      "maxHoldMs": 1000,
      "purpose": "slot_reservation_only"
    },
    "gitRunner": {
      "mode": "queue",
      "repoMutationTimeoutMs": 60000,
      "lockBypassForbidden": true
    },
    "validationLanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    },
    "worktreeLeases": {
      "attemptScoped": true,
      "heartbeatRequired": true,
      "quarantineOnStale": true
    },
    "stateStore": {
      "writesThroughControllerOnly": true,
      "transactionOrWriteQueueRequired": true
    }
  },
  "deadlineWatchdog": {
    "required": true,
    "intervalSeconds": 15,
    "emitsEventsOnly": true,
    "eventType": "deadline_exceeded",
    "supervised": true,
    "onWatchdogUnavailable": "block_new_execution_or_downgrade"
  },
  "handoffQueue": {
    "required": true,
    "createdByStates": [
      "handoff_required"
    ],
    "allowedActions": [
      "retry_requested",
      "close_failed",
      "manual_resolution",
      "followup_plan_requested"
    ],
    "controllerMediatedRetryRequired": true
  },
  "boundedLiveness": {
    "required": true,
    "noIndefiniteWaits": true,
    "llm": {
      "providerRequestTimeoutMs": 120000,
      "streamIdleTimeoutMs": 300000,
      "workspaceOverallTimeoutMs": 1800000,
      "maxConsecutiveProviderTimeouts": 2,
      "onCircuitOpen": "fail_workspace_not_plan"
    },
    "validation": {
      "defaultTimeoutMs": 600000,
      "heavyTimeoutMs": 1200000,
      "killProcessTreeOnTimeout": true,
      "watchModeForbidden": true,
      "stdinClosed": true,
      "ciEnvRequired": true,
      "maxOutputBytes": 52428800
    },
    "git": {
      "repoMutationLockTimeoutMs": 60000,
      "lockBypassForbidden": true,
      "onLockTimeout": "fail_fast_and_retry_or_handoff"
    },
    "scheduler": {
      "stallDetectionEnabled": true,
      "noProgressTimeoutMs": 300000,
      "onNoProgress": "emit_blocked_reason"
    },
    "stateStore": {
      "transactionOrWriteQueueRequired": true,
      "atomicSnapshotRequired": true,
      "journalLineAtomicityRequired": true
    }
  },
  "llmRuntime": {
    "boundedProviderCallsRequired": true,
    "providerRequestTimeoutMs": 120000,
    "streamIdleTimeoutMs": 300000,
    "workspaceOverallTimeoutMs": 1800000,
    "circuitBreaker": {
      "enabled": true,
      "openAfterConsecutiveTimeouts": 2,
      "cooldownMs": 300000
    },
    "fallbackPolicy": {
      "enabled": false,
      "reason": "Patches must remain deterministic."
    }
  },
  "validationRuntime": {
    "managedRunnerRequired": true,
    "processGroupRequired": true,
    "killTreeOnTimeout": true,
    "maxOutputBytes": 52428800,
    "forbiddenInteractiveCommands": [
      "vitest --watch",
      "jest --watch",
      "npm run dev",
      "vite --host"
    ],
    "lanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    }
  },
  "validationPolicy": {
    "defaultMode": "deferred",
    "workspaceCompletionRequiresTargetCommand": false,
    "planCompletionRequiresFinalValidation": true,
    "heavyValidationDeferredByDefault": true,
    "allowWorkspaceImmediateValidation": true,
    "allowSmokeValidation": true,
    "watchModeForbidden": true,
    "finalValidationWorkspaceRequired": true,
    "finalRepairWorkspaceRecommended": true,
    "validationArtifactsRequired": true,
    "liveValidationVisibilityRequired": true
  },
  "planExecution": {
    "phase": "P3",
    "title": "Multi-Timeframe Feature Engine & Unsupervised Context",
    "mode": "implementation",
    "maxParallelWorkspaces": 3,
    "scheduling": {
      "continuous": true,
      "slotCount": 3,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": false,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "stable_3",
      "selectedMode": "stable_3",
      "modes": {
        "stable_3": {
          "executorType": "direct",
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false,
          "preserveExistingBehavior": true
        },
        "stable_6": {
          "executorType": "patch_transaction",
          "maxCodegenWorkers": 6,
          "patchIsolationRequired": true,
          "worktreeRequired": false,
          "patchCoordinatorRequired": true,
          "repositoryMutationAuthority": "patch_coordinator",
          "patchApplyLanes": 1,
          "singleRepositoryWriterRequired": true,
          "targetedValidationRequired": true,
          "finalIntegrationValidationRequired": true,
          "postgresRequired": true,
          "completionGateRequired": true
        },
        "experimental_worktree_6": {
          "executorType": "worktree",
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "explicitOptInRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true
    },
    "integrationQueue": {
      "enabled": true,
      "enabledForExecutorTypes": [
        "worktree"
      ],
      "processOneMergeAtATime": true,
      "stopOnMergeConflict": true,
      "requireWorkspaceValidationPass": true,
      "requireIntegrationValidationPass": true,
      "gitPushAllowed": false,
      "queuePriority": {
        "enabled": true,
        "defaultLevel": "normal",
        "levels": [
          "critical",
          "high",
          "normal",
          "low"
        ]
      },
      "queueOptimization": {
        "enabled": true,
        "strategy": "priority_then_fifo",
        "availableStrategies": [
          "priority_then_fifo",
          "critical_path_first",
          "weighted_shortest_job_first"
        ]
      }
    },
    "validation": {
      "globalValidationLockRequired": true,
      "targetedValidationEnabled": true,
      "finalIntegrationValidationRequired": true,
      "watchModeForbidden": true
    },
    "interactiveParallelismReview": {
      "enabled": true,
      "preflightRequired": true,
      "approvalRequiredBeforeRun": true,
      "allowDependencyEditing": true,
      "showEffectiveParallelism": true,
      "showSafeEffectiveParallelism": true,
      "showBatchPreview": true,
      "showSafeBatchPreview": true,
      "showCriticalPath": true,
      "showScaleModeReadiness": true,
      "warnWhenEffectiveParallelismBelowRequested": true,
      "warnWhenSafeParallelismBelowDagParallelism": true,
      "warnWhenScaleModePrerequisitesMissing": true,
      "persistApprovedGraph": true
    },
    "planIntake": {
      "enabled": true,
      "runOnUpload": true,
      "parserPriority": [
        "part3_json",
        "contractVersion_and_executionClass",
        "doctor",
        "execution_gate"
      ],
      "autoNormalize": true,
      "autoDoctor": true,
      "autoDagAnalysis": true,
      "autoOptimizationProposal": true,
      "autoQueuePriorityRecommendation": true,
      "autoWorkspaceSplitRecommendation": true,
      "autoDryRunForecast": true,
      "approvalRequiredBeforeApplyingOptimization": true,
      "approvalRequiredBeforeExecution": true
    },
    "optimizer": {
      "enabled": true,
      "mode": "advisory_until_approved",
      "objectives": [
        "maximize_safe_effective_parallelism",
        "minimize_critical_path",
        "minimize_same_file_conflicts",
        "minimize_validation_lock_contention",
        "prioritize_critical_path_queue_merges"
      ],
      "allowedPatches": [
        "dependencies",
        "parallelGroup",
        "queuePriority",
        "canRunWith",
        "cannotRunWith",
        "conflictScope",
        "workspaceSplitSuggestion",
        "workspaceMergeSuggestion"
      ],
      "forbiddenAutoPatches": [
        "allowedFiles",
        "forbiddenFiles",
        "capabilityManifest",
        "safety.hardStops",
        "forbiddenCommands"
      ]
    }
  },
  "controls": {
    "allowPause": true,
    "allowStop": true,
    "allowCancel": true,
    "resumePolicy": "paused_or_stopped_only"
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
      "git clean -fd",
      "vitest --watch",
      "jest --watch",
      "npm run dev"
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
  "parallelismReview": {
    "requestedMaxParallelWorkspaces": 3,
    "selectedScaleMode": "stable_3",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for parallel execution."
        },
        {
          "key": "integration_queue",
          "required": true,
          "met": true,
          "message": "Required for queued execution."
        },
        {
          "key": "validation_lock",
          "required": true,
          "met": true,
          "message": "Required for heavy validation."
        },
        {
          "key": "completion_gate",
          "required": true,
          "met": true,
          "message": "Required for completion hardening."
        }
      ]
    },
    "expectedDagEffectiveParallelismMin": 2,
    "expectedSafeEffectiveParallelismMin": 2,
    "dagEffectiveParallelism": null,
    "safeEffectiveParallelism": null,
    "preflightStatus": "required",
    "approvalState": "pending",
    "batchingStrategy": "dag_topological_batches_display_only",
    "safeBatchingStrategy": "dag_batches_with_p6_safety_constraints_display_only",
    "batchPreview": {
      "batches": [],
      "overallEffectiveParallelism": null,
      "criticalPath": [],
      "criticalPathLength": 0,
      "serializedTailLength": 0
    },
    "safeBatchPreview": {
      "batches": [],
      "overallSafeEffectiveParallelism": null,
      "bottlenecks": [],
      "blockedParallelismReasons": []
    },
    "optimizationReview": {
      "originalGraphHash": null,
      "proposedGraphHash": null,
      "approvedGraphHash": null,
      "originalDagEffectiveParallelism": null,
      "proposedDagEffectiveParallelism": null,
      "originalSafeEffectiveParallelism": null,
      "proposedSafeEffectiveParallelism": null,
      "criticalPathDelta": null,
      "serializedTailDelta": null,
      "suggestions": [],
      "approvalState": "pending"
    },
    "editableFields": [
      "workspaces[].dependencies",
      "workspaces[].parallelGroup",
      "workspaces[].dependencyReason",
      "workspaces[].parallelism.canRunWith",
      "workspaces[].parallelism.cannotRunWith",
      "workspaces[].parallelism.conflictScope",
      "workspaces[].integration.queuePriority",
      "workspaces[].integration.queueOptimizationNotes"
    ],
    "doctorWarnings": [
      "effective_parallelism_below_requested",
      "safe_parallelism_below_dag_parallelism",
      "fully_serialized_graph",
      "long_serialized_tail",
      "file_overlap_blocks_parallelism",
      "validation_lock_limits_parallelism",
      "integration_queue_serializes_merges",
      "scale_mode_prerequisites_missing",
      "worktree_isolation_required_for_scale",
      "queue_optimization_disabled_with_active_priority",
      "queue_priority_mismatch_with_configured_levels",
      "critical_path_workspace_has_low_priority",
      "optimizer_patch_without_approval"
    ],
    "persistedArtifacts": [
      "dependency_graph",
      "batch_preview",
      "safe_batch_preview",
      "critical_path",
      "scale_mode_readiness",
      "approved_dependency_patch",
      "approved_graph_hash",
      "queue_priority_snapshot",
      "queue_optimization_strategy",
      "queue_reorder_decision_log",
      "plan_intake_analysis",
      "optimizer_proposal",
      "graph_diff",
      "worktree_state",
      "lease_heartbeat_snapshots",
      "lease_reconciliation_log",
      "merge_priority_score_log",
      "empirical_write_set",
      "write_set_drift_report",
      "validation_lane_saturation_log"
    ]
  },
  "workspaces": [
    {
      "id": "P3.A",
      "title": "Deterministic Features",
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
          "src/v7/alpha/features/**",
          "tests/v7/alpha/unit/features/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/features/**",
        "tests/v7/alpha/unit/features/**"
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
        "Primary interval features (return, volatility, ATR, RSI, etc.) work.",
        "Context interval trend/regime features work.",
        "Refinement entry-timing features work."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/features/**",
          "tests/v7/alpha/unit/features/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P3.B",
      "title": "Multi-Timeframe Join",
      "dependencies": [
        "P3.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P3.A for foundation.",
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
          "src/v7/alpha/features/**",
          "tests/v7/alpha/unit/features/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/features/**",
        "tests/v7/alpha/unit/features/**"
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
        "Canonical state built from primary/context/refinement windows.",
        "Timestamps aligned correctly per mode config."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/features/**",
          "tests/v7/alpha/unit/features/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P3.C",
      "title": "Unsupervised Context",
      "dependencies": [
        "P3.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P3.A for foundation.",
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
          "src/v7/alpha/anomaly/**",
          "tests/v7/alpha/unit/anomaly/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/anomaly/**",
        "tests/v7/alpha/unit/anomaly/**"
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
        "Isolation Forest, anomaly_score, regime_id feature producers exist.",
        "Fold-scoped fitting enforced (H1)."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/anomaly/**",
          "tests/v7/alpha/unit/anomaly/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P3.D",
      "title": "Feature Tests",
      "dependencies": [
        "P3.A",
        "P3.B",
        "P3.C"
      ],
      "parallelGroup": "batch_3",
      "dependencyReason": "Depends on P3.A, P3.B, P3.C for foundation.",
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
          "tests/v7/alpha/unit/features/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "normal",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "tests/v7/alpha/unit/features/**"
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
        "No future leakage in features.",
        "Feature schema versioning works."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "tests/v7/alpha/unit/features/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P3.E",
      "title": "Fold-Scoped Anomaly Fit Guard",
      "dependencies": [
        "P3.C"
      ],
      "parallelGroup": "batch_3",
      "dependencyReason": "Depends on P3.C for foundation.",
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
          "src/v7/alpha/anomaly/**",
          "tests/v7/alpha/integration/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/anomaly/**",
        "tests/v7/alpha/integration/**"
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
        "Rejects rows where anomaly fit window crosses fold boundary.",
        "Anomaly lineage fields stored per row."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/anomaly/**",
          "tests/v7/alpha/integration/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
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
  "phase": "P3",
  "title": "Multi-Timeframe Feature Engine & Unsupervised Context",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "selectedRepairMode": null,
  "targetPromotionMode": "stable_6",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "schedulerRuntimeUse": "enabled",
  "primaryGoal": "Primary/context/refinement deterministic features and optional anomaly/regime features.",
  "projectName": "v7_alphaforge_xgb",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresPatchIsolation": false,
  "requiresIntegrationQueue": true,
  "requiresPatchApplyQueue": false,
  "repositoryMutationAuthority": "worktree_integration",
  "queueOptimizationEnabled": true,
  "queueOptimizationStrategy": "priority_then_fifo",
  "continuousScheduling": true,
  "continuousSlotCount": 3,
  "safeEffectiveParallelismTarget": 2,
  "notInScope": [
    "External broker execution authority",
    "V7 runtime core modifications",
    "Non-XGBoost model families"
  ],
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
    "optimizer_patch_without_approval"
  ],
  "completionGate": "P3 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "P4"
}
```

---

## Review Hardening Requirements

* [ ] Fold-scoped anomaly fitting
* [ ] Symbol encoding future-proofing

---

<!-- SOURCE: phase_plans/P4__dataset_assembly_walk-forward_splits_and_label_qa.md -->

# P4 — Dataset Assembly, Walk-Forward Splits & Label QA

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P4`  
**One-line goal:** Mode-specific datasets, temporal split family, row validity, symbol weights.  
**Why now:** The model cannot be trained until feature rows and simulation labels are joined safely and evaluated chronologically.  
**Blast radius:** src/v7/alpha/**, tests/v7/alpha/**, configs/v7/alpha/**, docs/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Execution class:** `implementation`  
**Execution automation:** `enabled`  
**Scale mode:** `stable_3`  
**Safe parallelism target:** `2`  
**Done when:** All workspaces pass acceptance criteria and phase JSON validates through Pi doctor.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P4` |
| Title | `Dataset Assembly, Walk-Forward Splits & Label QA` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Mode-specific datasets, temporal split family, row validity, symbol weights.` |
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

The model cannot be trained until feature rows and simulation labels are joined safely and evaluated chronologically.

Dataset assembly must enforce temporal ordering, reject invalid rows, and produce mode-specific datasets. Walk-forward splits are mandatory; IID random splits are forbidden for primary evaluation.

This phase uses `stable_3` scale-aware execution. The executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

---

## 3. What Carried Over — Must Stay Stable

* [ ] Runtime owns orchestration, execution, persistence, lifecycle, and hard safety.
* [ ] Model owns alpha evidence only.
* [ ] Simulation truth defines labels and evaluation.
* [ ] No hidden deterministic veto or hidden fallback.
* [ ] NO_TRADE remains first-class.
* [ ] Features are canonical-state only.
* [ ] Labels are mode-specific.
* [ ] Datasets are mode-specific and temporally split.
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

Dataset assembly must enforce temporal ordering, reject invalid rows, and produce mode-specific datasets. Walk-forward splits are mandatory; IID random splits are forbidden for primary evaluation.

---

## 5. Current Failure State / Known Blockers

* `dataset_joiner` = not implemented.
* `walk_forward_splitter` = not implemented.
* `row_validity_and_weights` = not implemented.
* `dataset_qa_reports` = not implemented.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Worktree isolation violation | low | critical | Path scope checks; stop execution on escape |
| Integration queue merges unvalidated diff | medium | high | Require workspace validation and integration validation |
| Merge conflict blocks plan | medium | medium | Generate conflict handoff artifact and stop queue safely |
| Safe parallelism is lower than requested | medium | medium | Doctor warning; show bottleneck; use safe batch preview |
| Validation lock limits throughput | medium | medium | Scheduler reduces concurrency while heavy validation runs |
| High-risk workspace failure | medium | high | Rollback path defined; manual review gating |

---

## 7. Workstreams

### P4.A — Dataset Joiner

**Goal:** Joins feature rows with label rows on symbol+timestamp+mode.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** medium
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Joins feature rows with label rows on symbol+timestamp+mode.
* Rejects rows with future data gaps or stale state.

**File Scope:**
```text
src/v7/alpha/dataset/**
tests/v7/alpha/unit/dataset/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P4.B — Walk-Forward Splitter

**Goal:** Walk-forward splits with 12mo train, 2mo validation.

**Dependencies:** P4.A
**Parallel Group:** batch_2
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Walk-forward splits with 12mo train, 2mo validation.
* IID random split detection and rejection.

**File Scope:**
```text
src/v7/alpha/dataset/**
tests/v7/alpha/unit/dataset/**
```

**Isolation & Parallelism Notes:**
* Depends on P4.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P4.C — Row Validity & Weights

**Goal:** Invalid/ambiguous/unresolved rows excluded from training.

**Dependencies:** P4.A
**Parallel Group:** batch_2
**Risk Level:** medium
**Queue Priority:** high
**Can run with:** None

**Requirements:
* Invalid/ambiguous/unresolved rows excluded from training.
* Symbol and class weighting applied.
* Excluded rows preserved with explicit reason.

**File Scope:**
```text
src/v7/alpha/dataset/**
tests/v7/alpha/unit/dataset/**
```

**Isolation & Parallelism Notes:**
* Depends on P4.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P4.D — Dataset QA Reports

**Goal:** Dataset statistics and QA report generated.

**Dependencies:** P4.A, P4.B, P4.C
**Parallel Group:** batch_3
**Risk Level:** low
**Queue Priority:** normal
**Can run with:** None

**Requirements:
* Dataset statistics and QA report generated.
* Label distribution, missingness, and anomaly lineage verified.

**File Scope:**
```text
tests/v7/alpha/unit/dataset/**
```

**Isolation & Parallelism Notes:**
* Depends on P4.A, P4.B, P4.C for foundation.
* Expected batch: batch_3
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.


---

## 8. Combined Implementation Order

```text
  Batch batch_1: P4.A
  Batch batch_2: P4.B + P4.C
  Batch batch_3: P4.D
```

The dependency graph dictates that foundation workspaces run first, followed by parallel batches where dependencies permit. The DAG batch preview and safe batch preview may differ because of file overlap, validation lock pressure, or integration queue serialization.

---

## 9. Definition of Done

`P4` is complete when ALL are true:

* [ ] Joins feature rows with label rows on symbol+timestamp+mode.
* [ ] Walk-forward splits with 12mo train, 2mo validation.
* [ ] Invalid/ambiguous/unresolved rows excluded from training.
* [ ] Dataset statistics and QA report generated.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation is valid for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] No forbidden commands or files were used.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Validation planner misses a required failure.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Disable worktree mode only if safe fallback is required.
4. Pause or disable integration queue processing.
5. Preserve `.pi/worktrees/{planExecId}/` for debugging.
6. Fall back to shared-working-tree execution if explicitly allowed.
7. Keep dashboard telemetry read-only if safe.
8. Revert phase commits independently if needed.

---

## 11. What Next Phase Inherits

`P5` inherits:

* `P4` execution contract with worktree mode awareness.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Workspace-level parallelism/isolation/integration/validation metadata.
* Review hardening invariants: Anomaly lineage compatibility checks, Walk-forward temporal split enforcement

---

# Part 2 — Agent Brief

## Mission

Implement `P4` — Mode-specific datasets, temporal split family, row validity, symbol weights.

The agent must optimize for safe parallelism, not maximum concurrency. Higher worker counts are allowed only when scale-mode readiness passes and the executor can preserve correctness through worktree isolation, integration queue, validation locks, and completion gates.



---

## Hard Requirements

1. All P4 workstreams must pass acceptance criteria.
2. Worktree isolation must be enabled for parallel workspaces.
3. Integration queue must serialize merges.
4. Global validation lock must be active for heavy validation.
5. Watch-mode validation is forbidden.
6. `git push` is forbidden.
7. Raw destructive cleanup is forbidden.
8. Do not exceed selected scale-mode worker cap (3).
9. Do not merge workspace output without passed workspace validation.
10. Do not mark the plan complete if integration validation fails.
11. Do not treat merge conflict as ordinary worker failure.
12. Do not start the next plan while integration queue state is dirty.

---

## Execution Policies

```yaml
repair_modes:
  manual_0: autonomous_execution_allowed: false, agent_may_mutate_repo: false
  stable_3: autonomous_execution_allowed: true,  agent_may_mutate_repo: true

execution_automation:
  autonomous_execution_enabled: true
  agent_may_mutate_repo: true
  agent_may_run_commands: true
  manual_patch_application_required: false
  human_approval_required_for_every_patch: false

bounded_liveness:
  no_indefinite_waits: true
  llm_provider_timeout_required: true
  llm_stream_idle_watchdog_required: true
  validation_timeout_required: true
  process_tree_kill_required: true
  git_lock_bypass_forbidden: true
  state_write_serialization_required: true

scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
  worktree_required: true
  integration_queue_required: true

validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true

queue_optimization:
  enabled_by_default: true
  default_strategy: priority_then_fifo
  priority_levels: [critical, high, normal, low]
```

---

## Safety Stops

* Dependency cycles
* Invalid dependency patches
* Worktree path escaping `.pi/worktrees`
* Integration merge without passed workspace validation
* Validation failure
* Merge conflict without handoff artifact
* Unsafe scale mode
* Queue starting next plan while integration queue is dirty
* Forbidden file access
* Secrets access
* `git push`
* Watch-mode validation
* `autonomous_execution_requested_during_repair_mode`
* `agent_repo_mutation_requested_during_manual_repair`
* `scheduler_enabled_before_executor_isolation_gate`
* `llm_call_without_provider_timeout`
* `validation_command_without_timeout`
* `git_lock_bypass_detected`
* `state_store_write_without_serialization`
* `workspace_patch_without_human_approval`
* `promotion_gate_failed_or_missing`


# Part 2.5 — v4 ExecutionKernel Doctrine

## 2.5.1 Single Authority Model

v4 replaces the previous executor-owned or multi-component execution state model with an ExecutionKernel model.

```text
Before v4:
  Scheduler, executor, validation runner, retry router, cleanup, lease monitor,
  diagnostics, and brain workers could each influence or write partial execution truth.

After v4:
  All actors emit events.
  WorkspaceAttemptController mutates attempt state.
  PlanSupervisor mutates plan state.
  PostgreSQL stores authoritative runtime truth.
```

## 2.5.2 ExecutionKernel Components

| Component | Responsibility | May mutate execution state? |
|---|---|---:|
| `ExecutionAdmissionGate` | Authorize or reject execution requests before runtime starts | No |
| `ExecutionProfileDeriver` | Convert intent to required mechanisms | No |
| `PlanSupervisor` | Own plan FSM, slot tokens, completion predicate, final validation | Yes, plan state only |
| `WorkspaceAttemptController` | Own attempt FSM, retries, terminalization, handoff creation | Yes, attempt state only |
| `StateStoreWriter` | Commit transitions with authority token | Yes, through token only |
| `AttemptEventJournal` | Append versioned event records | No state mutation by itself |
| `DeadlineWatchdog` | Detect expired attempts and emit events | No |
| `ExecutorActor` | Run LLM/tools/bash for an attempt | No |
| `ValidationActor` | Run validation with deadlines and process containment | No |
| `GitRunner` | Serialize Git repo mutations | No attempt state mutation |

## 2.5.3 Attempt FSM Doctrine

A v4 attempt is a bounded state machine. It cannot remain in a non-terminal state forever.

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
Failure paths: RUNNING+timeout -> TIMED_OUT, critical violation -> FAILED_FINAL
Terminal states: SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, TIMED_OUT, HANDOFF_REQUIRED
Retry is legal only after terminal state.
```

## 2.5.4 PostgreSQL Truth Doctrine

Runtime truth is PostgreSQL. JSON fallback is forbidden in production.

Allowed filesystem data: stdout/stderr logs, raw tool output, patch artifacts, handoff Markdown.
Forbidden as authoritative runtime truth: JSON state fallback, NDJSON-only journal, filesystem-only state.

## 2.5.5 Intent-Driven Plan Doctrine

v4 authors express what they want, not the low-level mechanism matrix.

Human-authored: `parallelism`, `safetyLevel`, `conflictRisk`, `deadlines`, `executionEnvironment`.
System-derived: worktree requirement, integration queue, validation lanes, drift policy, watchdog policy.


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
    "name": "v7_alphaforge_xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p4"
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
    "writeSetDriftPolicy": "reject_or_handoff",
    "explain": [
      "stable_3 worktree mode: 3 workers, worktree isolation, integration queue",
      "Worktree isolation required for safe parallel execution",
      "All production execution requires PostgreSQL authoritative runtime state"
    ]
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
  "attemptLifecycle": {
    "modeSpecificLifecycles": {
      "worktree": {
        "initialState": "queued",
        "nonTerminalStates": [
          "queued",
          "leasing_worktree",
          "running",
          "validating",
          "waiting_for_validation_lane",
          "integration_queued",
          "integrating"
        ],
        "terminalStates": [
          "succeeded",
          "failed_retryable",
          "failed_final",
          "aborted",
          "timed_out",
          "quarantined",
          "handoff_required"
        ]
      }
    },
    "retryableTerminalStates": [
      "failed_retryable",
      "timed_out",
      "quarantined"
    ],
    "retryForbiddenFromNonTerminal": true,
    "deadlineRequiredForNonTerminalStates": true,
    "handoffRequiredCreatesQueueItem": true
  },
  "planLifecycle": {
    "completionPredicateRequired": true,
    "cannotCompleteWithRequiredNonTerminalWorkspaces": true,
    "cannotCompleteWithUnresolvedRequiredHandoff": true,
    "finalValidationRequiredBeforeCompleted": true,
    "states": [
      "created",
      "preflight",
      "running",
      "blocked_with_reason",
      "awaiting_handoff",
      "final_validation",
      "completed",
      "completed_with_warnings",
      "failed_final",
      "stopping",
      "stopped"
    ]
  },
  "actorPermissions": {
    "workspaceAttemptController": {
      "mayMutateAttemptState": true,
      "mayCreateRetryAttempt": true
    },
    "planSupervisor": {
      "mayMutatePlanState": true,
      "mayReserveSchedulerSlots": true
    },
    "executorActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayProducePatchArtifact": true,
      "mayEmitEvents": true
    },
    "validationActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayEmitEvents": true
    },
    "gitRunner": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true,
      "note": "May perform low-level git operations only when invoked by authorized repository mutation authority."
    },
    "leaseMonitor": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true
    },
    "retryPolicy": {
      "mayMutateAttemptState": false,
      "mayCreateRetryAttempt": false,
      "maySuggestRetry": true
    },
    "brainWorkers": {
      "mayMutateExecutionState": false,
      "mayEmitDiagnosis": true,
      "mayProposeAction": true
    },
    "diagnostics": {
      "mayMutateExecutionState": false,
      "mayEmitEvidence": true
    }
  },
  "admissionGate": {
    "required": true,
    "allEntrypointsMustUseGate": true,
    "coveredEntrypoints": [
      "cli_plan_run",
      "dashboard_run",
      "api_plan_run",
      "retry_endpoint",
      "cleanup_rerun_endpoint",
      "brain_worker_trigger",
      "overnight_runner",
      "proposal_executor"
    ],
    "rejectWhen": [
      "postgres_unavailable_for_authoritative_runtime",
      "json_runtime_fallback_detected",
      "repair_mode_autonomous_execution_disabled",
      "promotion_gates_missing",
      "unsafe_parallelism_requested",
      "execution_kernel_disabled",
      "state_authority_not_single"
    ]
  },
  "resourceCoordination": {
    "nestedLocksForbidden": true,
    "holdLockAcrossAwaitForbidden": true,
    "stateLocks": {
      "scope": "attempt",
      "maxHoldMs": 1000
    },
    "planLock": {
      "scope": "plan",
      "maxHoldMs": 1000,
      "purpose": "slot_reservation_only"
    },
    "gitRunner": {
      "mode": "queue",
      "repoMutationTimeoutMs": 60000,
      "lockBypassForbidden": true
    },
    "validationLanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    },
    "worktreeLeases": {
      "attemptScoped": true,
      "heartbeatRequired": true,
      "quarantineOnStale": true
    },
    "stateStore": {
      "writesThroughControllerOnly": true,
      "transactionOrWriteQueueRequired": true
    }
  },
  "deadlineWatchdog": {
    "required": true,
    "intervalSeconds": 15,
    "emitsEventsOnly": true,
    "eventType": "deadline_exceeded",
    "supervised": true,
    "onWatchdogUnavailable": "block_new_execution_or_downgrade"
  },
  "handoffQueue": {
    "required": true,
    "createdByStates": [
      "handoff_required"
    ],
    "allowedActions": [
      "retry_requested",
      "close_failed",
      "manual_resolution",
      "followup_plan_requested"
    ],
    "controllerMediatedRetryRequired": true
  },
  "boundedLiveness": {
    "required": true,
    "noIndefiniteWaits": true,
    "llm": {
      "providerRequestTimeoutMs": 120000,
      "streamIdleTimeoutMs": 300000,
      "workspaceOverallTimeoutMs": 1800000,
      "maxConsecutiveProviderTimeouts": 2,
      "onCircuitOpen": "fail_workspace_not_plan"
    },
    "validation": {
      "defaultTimeoutMs": 600000,
      "heavyTimeoutMs": 1200000,
      "killProcessTreeOnTimeout": true,
      "watchModeForbidden": true,
      "stdinClosed": true,
      "ciEnvRequired": true,
      "maxOutputBytes": 52428800
    },
    "git": {
      "repoMutationLockTimeoutMs": 60000,
      "lockBypassForbidden": true,
      "onLockTimeout": "fail_fast_and_retry_or_handoff"
    },
    "scheduler": {
      "stallDetectionEnabled": true,
      "noProgressTimeoutMs": 300000,
      "onNoProgress": "emit_blocked_reason"
    },
    "stateStore": {
      "transactionOrWriteQueueRequired": true,
      "atomicSnapshotRequired": true,
      "journalLineAtomicityRequired": true
    }
  },
  "llmRuntime": {
    "boundedProviderCallsRequired": true,
    "providerRequestTimeoutMs": 120000,
    "streamIdleTimeoutMs": 300000,
    "workspaceOverallTimeoutMs": 1800000,
    "circuitBreaker": {
      "enabled": true,
      "openAfterConsecutiveTimeouts": 2,
      "cooldownMs": 300000
    },
    "fallbackPolicy": {
      "enabled": false,
      "reason": "Patches must remain deterministic."
    }
  },
  "validationRuntime": {
    "managedRunnerRequired": true,
    "processGroupRequired": true,
    "killTreeOnTimeout": true,
    "maxOutputBytes": 52428800,
    "forbiddenInteractiveCommands": [
      "vitest --watch",
      "jest --watch",
      "npm run dev",
      "vite --host"
    ],
    "lanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    }
  },
  "validationPolicy": {
    "defaultMode": "deferred",
    "workspaceCompletionRequiresTargetCommand": false,
    "planCompletionRequiresFinalValidation": true,
    "heavyValidationDeferredByDefault": true,
    "allowWorkspaceImmediateValidation": true,
    "allowSmokeValidation": true,
    "watchModeForbidden": true,
    "finalValidationWorkspaceRequired": true,
    "finalRepairWorkspaceRecommended": true,
    "validationArtifactsRequired": true,
    "liveValidationVisibilityRequired": true
  },
  "planExecution": {
    "phase": "P4",
    "title": "Dataset Assembly, Walk-Forward Splits & Label QA",
    "mode": "implementation",
    "maxParallelWorkspaces": 3,
    "scheduling": {
      "continuous": true,
      "slotCount": 3,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": false,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "stable_3",
      "selectedMode": "stable_3",
      "modes": {
        "stable_3": {
          "executorType": "direct",
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false,
          "preserveExistingBehavior": true
        },
        "stable_6": {
          "executorType": "patch_transaction",
          "maxCodegenWorkers": 6,
          "patchIsolationRequired": true,
          "worktreeRequired": false,
          "patchCoordinatorRequired": true,
          "repositoryMutationAuthority": "patch_coordinator",
          "patchApplyLanes": 1,
          "singleRepositoryWriterRequired": true,
          "targetedValidationRequired": true,
          "finalIntegrationValidationRequired": true,
          "postgresRequired": true,
          "completionGateRequired": true
        },
        "experimental_worktree_6": {
          "executorType": "worktree",
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "explicitOptInRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true
    },
    "integrationQueue": {
      "enabled": true,
      "enabledForExecutorTypes": [
        "worktree"
      ],
      "processOneMergeAtATime": true,
      "stopOnMergeConflict": true,
      "requireWorkspaceValidationPass": true,
      "requireIntegrationValidationPass": true,
      "gitPushAllowed": false,
      "queuePriority": {
        "enabled": true,
        "defaultLevel": "normal",
        "levels": [
          "critical",
          "high",
          "normal",
          "low"
        ]
      },
      "queueOptimization": {
        "enabled": true,
        "strategy": "priority_then_fifo",
        "availableStrategies": [
          "priority_then_fifo",
          "critical_path_first",
          "weighted_shortest_job_first"
        ]
      }
    },
    "validation": {
      "globalValidationLockRequired": true,
      "targetedValidationEnabled": true,
      "finalIntegrationValidationRequired": true,
      "watchModeForbidden": true
    },
    "interactiveParallelismReview": {
      "enabled": true,
      "preflightRequired": true,
      "approvalRequiredBeforeRun": true,
      "allowDependencyEditing": true,
      "showEffectiveParallelism": true,
      "showSafeEffectiveParallelism": true,
      "showBatchPreview": true,
      "showSafeBatchPreview": true,
      "showCriticalPath": true,
      "showScaleModeReadiness": true,
      "warnWhenEffectiveParallelismBelowRequested": true,
      "warnWhenSafeParallelismBelowDagParallelism": true,
      "warnWhenScaleModePrerequisitesMissing": true,
      "persistApprovedGraph": true
    },
    "planIntake": {
      "enabled": true,
      "runOnUpload": true,
      "parserPriority": [
        "part3_json",
        "contractVersion_and_executionClass",
        "doctor",
        "execution_gate"
      ],
      "autoNormalize": true,
      "autoDoctor": true,
      "autoDagAnalysis": true,
      "autoOptimizationProposal": true,
      "autoQueuePriorityRecommendation": true,
      "autoWorkspaceSplitRecommendation": true,
      "autoDryRunForecast": true,
      "approvalRequiredBeforeApplyingOptimization": true,
      "approvalRequiredBeforeExecution": true
    },
    "optimizer": {
      "enabled": true,
      "mode": "advisory_until_approved",
      "objectives": [
        "maximize_safe_effective_parallelism",
        "minimize_critical_path",
        "minimize_same_file_conflicts",
        "minimize_validation_lock_contention",
        "prioritize_critical_path_queue_merges"
      ],
      "allowedPatches": [
        "dependencies",
        "parallelGroup",
        "queuePriority",
        "canRunWith",
        "cannotRunWith",
        "conflictScope",
        "workspaceSplitSuggestion",
        "workspaceMergeSuggestion"
      ],
      "forbiddenAutoPatches": [
        "allowedFiles",
        "forbiddenFiles",
        "capabilityManifest",
        "safety.hardStops",
        "forbiddenCommands"
      ]
    }
  },
  "controls": {
    "allowPause": true,
    "allowStop": true,
    "allowCancel": true,
    "resumePolicy": "paused_or_stopped_only"
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
      "git clean -fd",
      "vitest --watch",
      "jest --watch",
      "npm run dev"
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
  "parallelismReview": {
    "requestedMaxParallelWorkspaces": 3,
    "selectedScaleMode": "stable_3",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for parallel execution."
        },
        {
          "key": "integration_queue",
          "required": true,
          "met": true,
          "message": "Required for queued execution."
        },
        {
          "key": "validation_lock",
          "required": true,
          "met": true,
          "message": "Required for heavy validation."
        },
        {
          "key": "completion_gate",
          "required": true,
          "met": true,
          "message": "Required for completion hardening."
        }
      ]
    },
    "expectedDagEffectiveParallelismMin": 2,
    "expectedSafeEffectiveParallelismMin": 2,
    "dagEffectiveParallelism": null,
    "safeEffectiveParallelism": null,
    "preflightStatus": "required",
    "approvalState": "pending",
    "batchingStrategy": "dag_topological_batches_display_only",
    "safeBatchingStrategy": "dag_batches_with_p6_safety_constraints_display_only",
    "batchPreview": {
      "batches": [],
      "overallEffectiveParallelism": null,
      "criticalPath": [],
      "criticalPathLength": 0,
      "serializedTailLength": 0
    },
    "safeBatchPreview": {
      "batches": [],
      "overallSafeEffectiveParallelism": null,
      "bottlenecks": [],
      "blockedParallelismReasons": []
    },
    "optimizationReview": {
      "originalGraphHash": null,
      "proposedGraphHash": null,
      "approvedGraphHash": null,
      "originalDagEffectiveParallelism": null,
      "proposedDagEffectiveParallelism": null,
      "originalSafeEffectiveParallelism": null,
      "proposedSafeEffectiveParallelism": null,
      "criticalPathDelta": null,
      "serializedTailDelta": null,
      "suggestions": [],
      "approvalState": "pending"
    },
    "editableFields": [
      "workspaces[].dependencies",
      "workspaces[].parallelGroup",
      "workspaces[].dependencyReason",
      "workspaces[].parallelism.canRunWith",
      "workspaces[].parallelism.cannotRunWith",
      "workspaces[].parallelism.conflictScope",
      "workspaces[].integration.queuePriority",
      "workspaces[].integration.queueOptimizationNotes"
    ],
    "doctorWarnings": [
      "effective_parallelism_below_requested",
      "safe_parallelism_below_dag_parallelism",
      "fully_serialized_graph",
      "long_serialized_tail",
      "file_overlap_blocks_parallelism",
      "validation_lock_limits_parallelism",
      "integration_queue_serializes_merges",
      "scale_mode_prerequisites_missing",
      "worktree_isolation_required_for_scale",
      "queue_optimization_disabled_with_active_priority",
      "queue_priority_mismatch_with_configured_levels",
      "critical_path_workspace_has_low_priority",
      "optimizer_patch_without_approval"
    ],
    "persistedArtifacts": [
      "dependency_graph",
      "batch_preview",
      "safe_batch_preview",
      "critical_path",
      "scale_mode_readiness",
      "approved_dependency_patch",
      "approved_graph_hash",
      "queue_priority_snapshot",
      "queue_optimization_strategy",
      "queue_reorder_decision_log",
      "plan_intake_analysis",
      "optimizer_proposal",
      "graph_diff",
      "worktree_state",
      "lease_heartbeat_snapshots",
      "lease_reconciliation_log",
      "merge_priority_score_log",
      "empirical_write_set",
      "write_set_drift_report",
      "validation_lane_saturation_log"
    ]
  },
  "workspaces": [
    {
      "id": "P4.A",
      "title": "Dataset Joiner",
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
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/dataset/**",
        "tests/v7/alpha/unit/dataset/**"
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
        "Joins feature rows with label rows on symbol+timestamp+mode.",
        "Rejects rows with future data gaps or stale state."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P4.B",
      "title": "Walk-Forward Splitter",
      "dependencies": [
        "P4.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P4.A for foundation.",
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
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/dataset/**",
        "tests/v7/alpha/unit/dataset/**"
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
        "Walk-forward splits with 12mo train, 2mo validation.",
        "IID random split detection and rejection."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P4.C",
      "title": "Row Validity & Weights",
      "dependencies": [
        "P4.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P4.A for foundation.",
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
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/dataset/**",
        "tests/v7/alpha/unit/dataset/**"
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
        "Invalid/ambiguous/unresolved rows excluded from training.",
        "Symbol and class weighting applied.",
        "Excluded rows preserved with explicit reason."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P4.D",
      "title": "Dataset QA Reports",
      "dependencies": [
        "P4.A",
        "P4.B",
        "P4.C"
      ],
      "parallelGroup": "batch_3",
      "dependencyReason": "Depends on P4.A, P4.B, P4.C for foundation.",
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
          "tests/v7/alpha/unit/dataset/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "normal",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "tests/v7/alpha/unit/dataset/**"
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
        "Dataset statistics and QA report generated.",
        "Label distribution, missingness, and anomaly lineage verified."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "low",
      "capabilityManifest": {
        "canEdit": [
          "tests/v7/alpha/unit/dataset/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
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
  "phase": "P4",
  "title": "Dataset Assembly, Walk-Forward Splits & Label QA",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "selectedRepairMode": null,
  "targetPromotionMode": "stable_6",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "schedulerRuntimeUse": "enabled",
  "primaryGoal": "Mode-specific datasets, temporal split family, row validity, symbol weights.",
  "projectName": "v7_alphaforge_xgb",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresPatchIsolation": false,
  "requiresIntegrationQueue": true,
  "requiresPatchApplyQueue": false,
  "repositoryMutationAuthority": "worktree_integration",
  "queueOptimizationEnabled": true,
  "queueOptimizationStrategy": "priority_then_fifo",
  "continuousScheduling": true,
  "continuousSlotCount": 3,
  "safeEffectiveParallelismTarget": 2,
  "notInScope": [
    "External broker execution authority",
    "V7 runtime core modifications",
    "Non-XGBoost model families"
  ],
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
    "optimizer_patch_without_approval"
  ],
  "completionGate": "P4 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "P5"
}
```

---

## Review Hardening Requirements

* [ ] Anomaly lineage compatibility checks
* [ ] Walk-forward temporal split enforcement

---

<!-- SOURCE: phase_plans/P5__xgboost_hybrid_model_training.md -->

# P5 — XGBoost Hybrid Model Training

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P5`  
**One-line goal:** Mode-specific classifier and expected-R regressors.  
**Why now:** The first candidate artifact family requires XGBoost training, artifact metadata, and reproducible model persistence.  
**Blast radius:** src/v7/alpha/**, tests/v7/alpha/**, configs/v7/alpha/**, docs/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Execution class:** `implementation`  
**Execution automation:** `enabled`  
**Scale mode:** `stable_3`  
**Safe parallelism target:** `2`  
**Done when:** All workspaces pass acceptance criteria and phase JSON validates through Pi doctor.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P5` |
| Title | `XGBoost Hybrid Model Training` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Mode-specific classifier and expected-R regressors.` |
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

The first candidate artifact family requires XGBoost training, artifact metadata, and reproducible model persistence.

XGBoost is the first-phase model family. Each mode gets its own classifier (LONG/SHORT/NO_TRADE) and separate long-R and short-R regressors. Artifacts must carry full lineage metadata.

This phase uses `stable_3` scale-aware execution. The executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

---

## 3. What Carried Over — Must Stay Stable

* [ ] Runtime owns orchestration, execution, persistence, lifecycle, and hard safety.
* [ ] Model owns alpha evidence only.
* [ ] Simulation truth defines labels and evaluation.
* [ ] No hidden deterministic veto or hidden fallback.
* [ ] NO_TRADE remains first-class.
* [ ] Features are canonical-state only.
* [ ] Labels are mode-specific.
* [ ] Datasets are mode-specific and temporally split.
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

XGBoost is the first-phase model family. Each mode gets its own classifier (LONG/SHORT/NO_TRADE) and separate long-R and short-R regressors. Artifacts must carry full lineage metadata.

---

## 5. Current Failure State / Known Blockers

* `classifier_training` = not implemented.
* `regressor_training` = not implemented.
* `artifact_bundles` = not implemented.
* `training_metrics` = not implemented.
* `symbol_encoding_metadata` = not implemented.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Worktree isolation violation | low | critical | Path scope checks; stop execution on escape |
| Integration queue merges unvalidated diff | medium | high | Require workspace validation and integration validation |
| Merge conflict blocks plan | medium | medium | Generate conflict handoff artifact and stop queue safely |
| Safe parallelism is lower than requested | medium | medium | Doctor warning; show bottleneck; use safe batch preview |
| Validation lock limits throughput | medium | medium | Scheduler reduces concurrency while heavy validation runs |
| High-risk workspace failure | medium | high | Rollback path defined; manual review gating |

---

## 7. Workstreams

### P5.A — Classifier Training

**Goal:** Mode-specific XGBoost classifier trains on SWING/SCALP/AGGRESSIVE datasets.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Mode-specific XGBoost classifier trains on SWING/SCALP/AGGRESSIVE datasets.
* NO_TRADE is first-class output class.

**File Scope:**
```text
src/v7/alpha/model/**
tests/v7/alpha/unit/model/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P5.B — Regressor Training

**Goal:** Separate long_R and short_R regressors train per mode.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Separate long_R and short_R regressors train per mode.
* Expected-R surfaces are reproducible.

**File Scope:**
```text
src/v7/alpha/model/**
tests/v7/alpha/unit/model/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P5.C — Artifact Bundles

**Goal:** Model + calibration + policy artifacts bundled per mode.

**Dependencies:** P5.A, P5.B
**Parallel Group:** batch_2
**Risk Level:** medium
**Queue Priority:** high
**Can run with:** None

**Requirements:
* Model + calibration + policy artifacts bundled per mode.
* Full lineage metadata stored in each bundle.

**File Scope:**
```text
src/v7/alpha/model/**
configs/v7/alpha/**
```

**Isolation & Parallelism Notes:**
* Depends on P5.A, P5.B for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P5.D — Training Metrics

**Goal:** Classification report, regression metrics, and feature importance logged.

**Dependencies:** P5.A, P5.B
**Parallel Group:** batch_2
**Risk Level:** medium
**Queue Priority:** normal
**Can run with:** None

**Requirements:
* Classification report, regression metrics, and feature importance logged.
* Metrics are temporally-aware, not IID.

**File Scope:**
```text
src/v7/alpha/evaluation/**
tests/v7/alpha/unit/evaluation/**
```

**Isolation & Parallelism Notes:**
* Depends on P5.A, P5.B for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P5.E — Symbol Encoding Metadata

**Goal:** symbol_encoding_family and symbol_universe_version stored.

**Dependencies:** P5.A
**Parallel Group:** batch_2
**Risk Level:** low
**Queue Priority:** normal
**Can run with:** None

**Requirements:
* symbol_encoding_family and symbol_universe_version stored.
* MVP uses symbol_one_hot_v1.

**File Scope:**
```text
src/v7/alpha/model/**
configs/v7/alpha/**
```

**Isolation & Parallelism Notes:**
* Depends on P5.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.


---

## 8. Combined Implementation Order

```text
  Batch batch_1: P5.A + P5.B
  Batch batch_2: P5.C + P5.D + P5.E
```

The dependency graph dictates that foundation workspaces run first, followed by parallel batches where dependencies permit. The DAG batch preview and safe batch preview may differ because of file overlap, validation lock pressure, or integration queue serialization.

---

## 9. Definition of Done

`P5` is complete when ALL are true:

* [ ] Mode-specific XGBoost classifier trains on SWING/SCALP/AGGRESSIVE datasets.
* [ ] Separate long_R and short_R regressors train per mode.
* [ ] Model + calibration + policy artifacts bundled per mode.
* [ ] Classification report, regression metrics, and feature importance logged.
* [ ] symbol_encoding_family and symbol_universe_version stored.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation is valid for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] No forbidden commands or files were used.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Validation planner misses a required failure.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Disable worktree mode only if safe fallback is required.
4. Pause or disable integration queue processing.
5. Preserve `.pi/worktrees/{planExecId}/` for debugging.
6. Fall back to shared-working-tree execution if explicitly allowed.
7. Keep dashboard telemetry read-only if safe.
8. Revert phase commits independently if needed.

---

## 11. What Next Phase Inherits

`P6` inherits:

* `P5` execution contract with worktree mode awareness.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Workspace-level parallelism/isolation/integration/validation metadata.
* Review hardening invariants: Symbol encoding metadata, Training reproducibility

---

# Part 2 — Agent Brief

## Mission

Implement `P5` — Mode-specific classifier and expected-R regressors.

The agent must optimize for safe parallelism, not maximum concurrency. Higher worker counts are allowed only when scale-mode readiness passes and the executor can preserve correctness through worktree isolation, integration queue, validation locks, and completion gates.



---

## Hard Requirements

1. All P5 workstreams must pass acceptance criteria.
2. Worktree isolation must be enabled for parallel workspaces.
3. Integration queue must serialize merges.
4. Global validation lock must be active for heavy validation.
5. Watch-mode validation is forbidden.
6. `git push` is forbidden.
7. Raw destructive cleanup is forbidden.
8. Do not exceed selected scale-mode worker cap (3).
9. Do not merge workspace output without passed workspace validation.
10. Do not mark the plan complete if integration validation fails.
11. Do not treat merge conflict as ordinary worker failure.
12. Do not start the next plan while integration queue state is dirty.

---

## Execution Policies

```yaml
repair_modes:
  manual_0: autonomous_execution_allowed: false, agent_may_mutate_repo: false
  stable_3: autonomous_execution_allowed: true,  agent_may_mutate_repo: true

execution_automation:
  autonomous_execution_enabled: true
  agent_may_mutate_repo: true
  agent_may_run_commands: true
  manual_patch_application_required: false
  human_approval_required_for_every_patch: false

bounded_liveness:
  no_indefinite_waits: true
  llm_provider_timeout_required: true
  llm_stream_idle_watchdog_required: true
  validation_timeout_required: true
  process_tree_kill_required: true
  git_lock_bypass_forbidden: true
  state_write_serialization_required: true

scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
  worktree_required: true
  integration_queue_required: true

validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true

queue_optimization:
  enabled_by_default: true
  default_strategy: priority_then_fifo
  priority_levels: [critical, high, normal, low]
```

---

## Safety Stops

* Dependency cycles
* Invalid dependency patches
* Worktree path escaping `.pi/worktrees`
* Integration merge without passed workspace validation
* Validation failure
* Merge conflict without handoff artifact
* Unsafe scale mode
* Queue starting next plan while integration queue is dirty
* Forbidden file access
* Secrets access
* `git push`
* Watch-mode validation
* `autonomous_execution_requested_during_repair_mode`
* `agent_repo_mutation_requested_during_manual_repair`
* `scheduler_enabled_before_executor_isolation_gate`
* `llm_call_without_provider_timeout`
* `validation_command_without_timeout`
* `git_lock_bypass_detected`
* `state_store_write_without_serialization`
* `workspace_patch_without_human_approval`
* `promotion_gate_failed_or_missing`


# Part 2.5 — v4 ExecutionKernel Doctrine

## 2.5.1 Single Authority Model

v4 replaces the previous executor-owned or multi-component execution state model with an ExecutionKernel model.

```text
Before v4:
  Scheduler, executor, validation runner, retry router, cleanup, lease monitor,
  diagnostics, and brain workers could each influence or write partial execution truth.

After v4:
  All actors emit events.
  WorkspaceAttemptController mutates attempt state.
  PlanSupervisor mutates plan state.
  PostgreSQL stores authoritative runtime truth.
```

## 2.5.2 ExecutionKernel Components

| Component | Responsibility | May mutate execution state? |
|---|---|---:|
| `ExecutionAdmissionGate` | Authorize or reject execution requests before runtime starts | No |
| `ExecutionProfileDeriver` | Convert intent to required mechanisms | No |
| `PlanSupervisor` | Own plan FSM, slot tokens, completion predicate, final validation | Yes, plan state only |
| `WorkspaceAttemptController` | Own attempt FSM, retries, terminalization, handoff creation | Yes, attempt state only |
| `StateStoreWriter` | Commit transitions with authority token | Yes, through token only |
| `AttemptEventJournal` | Append versioned event records | No state mutation by itself |
| `DeadlineWatchdog` | Detect expired attempts and emit events | No |
| `ExecutorActor` | Run LLM/tools/bash for an attempt | No |
| `ValidationActor` | Run validation with deadlines and process containment | No |
| `GitRunner` | Serialize Git repo mutations | No attempt state mutation |

## 2.5.3 Attempt FSM Doctrine

A v4 attempt is a bounded state machine. It cannot remain in a non-terminal state forever.

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
Failure paths: RUNNING+timeout -> TIMED_OUT, critical violation -> FAILED_FINAL
Terminal states: SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, TIMED_OUT, HANDOFF_REQUIRED
Retry is legal only after terminal state.
```

## 2.5.4 PostgreSQL Truth Doctrine

Runtime truth is PostgreSQL. JSON fallback is forbidden in production.

Allowed filesystem data: stdout/stderr logs, raw tool output, patch artifacts, handoff Markdown.
Forbidden as authoritative runtime truth: JSON state fallback, NDJSON-only journal, filesystem-only state.

## 2.5.5 Intent-Driven Plan Doctrine

v4 authors express what they want, not the low-level mechanism matrix.

Human-authored: `parallelism`, `safetyLevel`, `conflictRisk`, `deadlines`, `executionEnvironment`.
System-derived: worktree requirement, integration queue, validation lanes, drift policy, watchdog policy.


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
    "name": "v7_alphaforge_xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p5"
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
    "writeSetDriftPolicy": "reject_or_handoff",
    "explain": [
      "stable_3 worktree mode: 3 workers, worktree isolation, integration queue",
      "Worktree isolation required for safe parallel execution",
      "All production execution requires PostgreSQL authoritative runtime state"
    ]
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
  "attemptLifecycle": {
    "modeSpecificLifecycles": {
      "worktree": {
        "initialState": "queued",
        "nonTerminalStates": [
          "queued",
          "leasing_worktree",
          "running",
          "validating",
          "waiting_for_validation_lane",
          "integration_queued",
          "integrating"
        ],
        "terminalStates": [
          "succeeded",
          "failed_retryable",
          "failed_final",
          "aborted",
          "timed_out",
          "quarantined",
          "handoff_required"
        ]
      }
    },
    "retryableTerminalStates": [
      "failed_retryable",
      "timed_out",
      "quarantined"
    ],
    "retryForbiddenFromNonTerminal": true,
    "deadlineRequiredForNonTerminalStates": true,
    "handoffRequiredCreatesQueueItem": true
  },
  "planLifecycle": {
    "completionPredicateRequired": true,
    "cannotCompleteWithRequiredNonTerminalWorkspaces": true,
    "cannotCompleteWithUnresolvedRequiredHandoff": true,
    "finalValidationRequiredBeforeCompleted": true,
    "states": [
      "created",
      "preflight",
      "running",
      "blocked_with_reason",
      "awaiting_handoff",
      "final_validation",
      "completed",
      "completed_with_warnings",
      "failed_final",
      "stopping",
      "stopped"
    ]
  },
  "actorPermissions": {
    "workspaceAttemptController": {
      "mayMutateAttemptState": true,
      "mayCreateRetryAttempt": true
    },
    "planSupervisor": {
      "mayMutatePlanState": true,
      "mayReserveSchedulerSlots": true
    },
    "executorActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayProducePatchArtifact": true,
      "mayEmitEvents": true
    },
    "validationActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayEmitEvents": true
    },
    "gitRunner": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true,
      "note": "May perform low-level git operations only when invoked by authorized repository mutation authority."
    },
    "leaseMonitor": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true
    },
    "retryPolicy": {
      "mayMutateAttemptState": false,
      "mayCreateRetryAttempt": false,
      "maySuggestRetry": true
    },
    "brainWorkers": {
      "mayMutateExecutionState": false,
      "mayEmitDiagnosis": true,
      "mayProposeAction": true
    },
    "diagnostics": {
      "mayMutateExecutionState": false,
      "mayEmitEvidence": true
    }
  },
  "admissionGate": {
    "required": true,
    "allEntrypointsMustUseGate": true,
    "coveredEntrypoints": [
      "cli_plan_run",
      "dashboard_run",
      "api_plan_run",
      "retry_endpoint",
      "cleanup_rerun_endpoint",
      "brain_worker_trigger",
      "overnight_runner",
      "proposal_executor"
    ],
    "rejectWhen": [
      "postgres_unavailable_for_authoritative_runtime",
      "json_runtime_fallback_detected",
      "repair_mode_autonomous_execution_disabled",
      "promotion_gates_missing",
      "unsafe_parallelism_requested",
      "execution_kernel_disabled",
      "state_authority_not_single"
    ]
  },
  "resourceCoordination": {
    "nestedLocksForbidden": true,
    "holdLockAcrossAwaitForbidden": true,
    "stateLocks": {
      "scope": "attempt",
      "maxHoldMs": 1000
    },
    "planLock": {
      "scope": "plan",
      "maxHoldMs": 1000,
      "purpose": "slot_reservation_only"
    },
    "gitRunner": {
      "mode": "queue",
      "repoMutationTimeoutMs": 60000,
      "lockBypassForbidden": true
    },
    "validationLanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    },
    "worktreeLeases": {
      "attemptScoped": true,
      "heartbeatRequired": true,
      "quarantineOnStale": true
    },
    "stateStore": {
      "writesThroughControllerOnly": true,
      "transactionOrWriteQueueRequired": true
    }
  },
  "deadlineWatchdog": {
    "required": true,
    "intervalSeconds": 15,
    "emitsEventsOnly": true,
    "eventType": "deadline_exceeded",
    "supervised": true,
    "onWatchdogUnavailable": "block_new_execution_or_downgrade"
  },
  "handoffQueue": {
    "required": true,
    "createdByStates": [
      "handoff_required"
    ],
    "allowedActions": [
      "retry_requested",
      "close_failed",
      "manual_resolution",
      "followup_plan_requested"
    ],
    "controllerMediatedRetryRequired": true
  },
  "boundedLiveness": {
    "required": true,
    "noIndefiniteWaits": true,
    "llm": {
      "providerRequestTimeoutMs": 120000,
      "streamIdleTimeoutMs": 300000,
      "workspaceOverallTimeoutMs": 1800000,
      "maxConsecutiveProviderTimeouts": 2,
      "onCircuitOpen": "fail_workspace_not_plan"
    },
    "validation": {
      "defaultTimeoutMs": 600000,
      "heavyTimeoutMs": 1200000,
      "killProcessTreeOnTimeout": true,
      "watchModeForbidden": true,
      "stdinClosed": true,
      "ciEnvRequired": true,
      "maxOutputBytes": 52428800
    },
    "git": {
      "repoMutationLockTimeoutMs": 60000,
      "lockBypassForbidden": true,
      "onLockTimeout": "fail_fast_and_retry_or_handoff"
    },
    "scheduler": {
      "stallDetectionEnabled": true,
      "noProgressTimeoutMs": 300000,
      "onNoProgress": "emit_blocked_reason"
    },
    "stateStore": {
      "transactionOrWriteQueueRequired": true,
      "atomicSnapshotRequired": true,
      "journalLineAtomicityRequired": true
    }
  },
  "llmRuntime": {
    "boundedProviderCallsRequired": true,
    "providerRequestTimeoutMs": 120000,
    "streamIdleTimeoutMs": 300000,
    "workspaceOverallTimeoutMs": 1800000,
    "circuitBreaker": {
      "enabled": true,
      "openAfterConsecutiveTimeouts": 2,
      "cooldownMs": 300000
    },
    "fallbackPolicy": {
      "enabled": false,
      "reason": "Patches must remain deterministic."
    }
  },
  "validationRuntime": {
    "managedRunnerRequired": true,
    "processGroupRequired": true,
    "killTreeOnTimeout": true,
    "maxOutputBytes": 52428800,
    "forbiddenInteractiveCommands": [
      "vitest --watch",
      "jest --watch",
      "npm run dev",
      "vite --host"
    ],
    "lanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    }
  },
  "validationPolicy": {
    "defaultMode": "deferred",
    "workspaceCompletionRequiresTargetCommand": false,
    "planCompletionRequiresFinalValidation": true,
    "heavyValidationDeferredByDefault": true,
    "allowWorkspaceImmediateValidation": true,
    "allowSmokeValidation": true,
    "watchModeForbidden": true,
    "finalValidationWorkspaceRequired": true,
    "finalRepairWorkspaceRecommended": true,
    "validationArtifactsRequired": true,
    "liveValidationVisibilityRequired": true
  },
  "planExecution": {
    "phase": "P5",
    "title": "XGBoost Hybrid Model Training",
    "mode": "implementation",
    "maxParallelWorkspaces": 3,
    "scheduling": {
      "continuous": true,
      "slotCount": 3,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": false,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "stable_3",
      "selectedMode": "stable_3",
      "modes": {
        "stable_3": {
          "executorType": "direct",
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false,
          "preserveExistingBehavior": true
        },
        "stable_6": {
          "executorType": "patch_transaction",
          "maxCodegenWorkers": 6,
          "patchIsolationRequired": true,
          "worktreeRequired": false,
          "patchCoordinatorRequired": true,
          "repositoryMutationAuthority": "patch_coordinator",
          "patchApplyLanes": 1,
          "singleRepositoryWriterRequired": true,
          "targetedValidationRequired": true,
          "finalIntegrationValidationRequired": true,
          "postgresRequired": true,
          "completionGateRequired": true
        },
        "experimental_worktree_6": {
          "executorType": "worktree",
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "explicitOptInRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true
    },
    "integrationQueue": {
      "enabled": true,
      "enabledForExecutorTypes": [
        "worktree"
      ],
      "processOneMergeAtATime": true,
      "stopOnMergeConflict": true,
      "requireWorkspaceValidationPass": true,
      "requireIntegrationValidationPass": true,
      "gitPushAllowed": false,
      "queuePriority": {
        "enabled": true,
        "defaultLevel": "normal",
        "levels": [
          "critical",
          "high",
          "normal",
          "low"
        ]
      },
      "queueOptimization": {
        "enabled": true,
        "strategy": "priority_then_fifo",
        "availableStrategies": [
          "priority_then_fifo",
          "critical_path_first",
          "weighted_shortest_job_first"
        ]
      }
    },
    "validation": {
      "globalValidationLockRequired": true,
      "targetedValidationEnabled": true,
      "finalIntegrationValidationRequired": true,
      "watchModeForbidden": true
    },
    "interactiveParallelismReview": {
      "enabled": true,
      "preflightRequired": true,
      "approvalRequiredBeforeRun": true,
      "allowDependencyEditing": true,
      "showEffectiveParallelism": true,
      "showSafeEffectiveParallelism": true,
      "showBatchPreview": true,
      "showSafeBatchPreview": true,
      "showCriticalPath": true,
      "showScaleModeReadiness": true,
      "warnWhenEffectiveParallelismBelowRequested": true,
      "warnWhenSafeParallelismBelowDagParallelism": true,
      "warnWhenScaleModePrerequisitesMissing": true,
      "persistApprovedGraph": true
    },
    "planIntake": {
      "enabled": true,
      "runOnUpload": true,
      "parserPriority": [
        "part3_json",
        "contractVersion_and_executionClass",
        "doctor",
        "execution_gate"
      ],
      "autoNormalize": true,
      "autoDoctor": true,
      "autoDagAnalysis": true,
      "autoOptimizationProposal": true,
      "autoQueuePriorityRecommendation": true,
      "autoWorkspaceSplitRecommendation": true,
      "autoDryRunForecast": true,
      "approvalRequiredBeforeApplyingOptimization": true,
      "approvalRequiredBeforeExecution": true
    },
    "optimizer": {
      "enabled": true,
      "mode": "advisory_until_approved",
      "objectives": [
        "maximize_safe_effective_parallelism",
        "minimize_critical_path",
        "minimize_same_file_conflicts",
        "minimize_validation_lock_contention",
        "prioritize_critical_path_queue_merges"
      ],
      "allowedPatches": [
        "dependencies",
        "parallelGroup",
        "queuePriority",
        "canRunWith",
        "cannotRunWith",
        "conflictScope",
        "workspaceSplitSuggestion",
        "workspaceMergeSuggestion"
      ],
      "forbiddenAutoPatches": [
        "allowedFiles",
        "forbiddenFiles",
        "capabilityManifest",
        "safety.hardStops",
        "forbiddenCommands"
      ]
    }
  },
  "controls": {
    "allowPause": true,
    "allowStop": true,
    "allowCancel": true,
    "resumePolicy": "paused_or_stopped_only"
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
      "git clean -fd",
      "vitest --watch",
      "jest --watch",
      "npm run dev"
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
  "parallelismReview": {
    "requestedMaxParallelWorkspaces": 3,
    "selectedScaleMode": "stable_3",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for parallel execution."
        },
        {
          "key": "integration_queue",
          "required": true,
          "met": true,
          "message": "Required for queued execution."
        },
        {
          "key": "validation_lock",
          "required": true,
          "met": true,
          "message": "Required for heavy validation."
        },
        {
          "key": "completion_gate",
          "required": true,
          "met": true,
          "message": "Required for completion hardening."
        }
      ]
    },
    "expectedDagEffectiveParallelismMin": 2,
    "expectedSafeEffectiveParallelismMin": 2,
    "dagEffectiveParallelism": null,
    "safeEffectiveParallelism": null,
    "preflightStatus": "required",
    "approvalState": "pending",
    "batchingStrategy": "dag_topological_batches_display_only",
    "safeBatchingStrategy": "dag_batches_with_p6_safety_constraints_display_only",
    "batchPreview": {
      "batches": [],
      "overallEffectiveParallelism": null,
      "criticalPath": [],
      "criticalPathLength": 0,
      "serializedTailLength": 0
    },
    "safeBatchPreview": {
      "batches": [],
      "overallSafeEffectiveParallelism": null,
      "bottlenecks": [],
      "blockedParallelismReasons": []
    },
    "optimizationReview": {
      "originalGraphHash": null,
      "proposedGraphHash": null,
      "approvedGraphHash": null,
      "originalDagEffectiveParallelism": null,
      "proposedDagEffectiveParallelism": null,
      "originalSafeEffectiveParallelism": null,
      "proposedSafeEffectiveParallelism": null,
      "criticalPathDelta": null,
      "serializedTailDelta": null,
      "suggestions": [],
      "approvalState": "pending"
    },
    "editableFields": [
      "workspaces[].dependencies",
      "workspaces[].parallelGroup",
      "workspaces[].dependencyReason",
      "workspaces[].parallelism.canRunWith",
      "workspaces[].parallelism.cannotRunWith",
      "workspaces[].parallelism.conflictScope",
      "workspaces[].integration.queuePriority",
      "workspaces[].integration.queueOptimizationNotes"
    ],
    "doctorWarnings": [
      "effective_parallelism_below_requested",
      "safe_parallelism_below_dag_parallelism",
      "fully_serialized_graph",
      "long_serialized_tail",
      "file_overlap_blocks_parallelism",
      "validation_lock_limits_parallelism",
      "integration_queue_serializes_merges",
      "scale_mode_prerequisites_missing",
      "worktree_isolation_required_for_scale",
      "queue_optimization_disabled_with_active_priority",
      "queue_priority_mismatch_with_configured_levels",
      "critical_path_workspace_has_low_priority",
      "optimizer_patch_without_approval"
    ],
    "persistedArtifacts": [
      "dependency_graph",
      "batch_preview",
      "safe_batch_preview",
      "critical_path",
      "scale_mode_readiness",
      "approved_dependency_patch",
      "approved_graph_hash",
      "queue_priority_snapshot",
      "queue_optimization_strategy",
      "queue_reorder_decision_log",
      "plan_intake_analysis",
      "optimizer_proposal",
      "graph_diff",
      "worktree_state",
      "lease_heartbeat_snapshots",
      "lease_reconciliation_log",
      "merge_priority_score_log",
      "empirical_write_set",
      "write_set_drift_report",
      "validation_lane_saturation_log"
    ]
  },
  "workspaces": [
    {
      "id": "P5.A",
      "title": "Classifier Training",
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
          "src/v7/alpha/model/**",
          "tests/v7/alpha/unit/model/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/model/**",
        "tests/v7/alpha/unit/model/**"
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
        "Mode-specific XGBoost classifier trains on SWING/SCALP/AGGRESSIVE datasets.",
        "NO_TRADE is first-class output class."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/model/**",
          "tests/v7/alpha/unit/model/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P5.B",
      "title": "Regressor Training",
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
          "src/v7/alpha/model/**",
          "tests/v7/alpha/unit/model/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/model/**",
        "tests/v7/alpha/unit/model/**"
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
        "Separate long_R and short_R regressors train per mode.",
        "Expected-R surfaces are reproducible."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/model/**",
          "tests/v7/alpha/unit/model/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P5.C",
      "title": "Artifact Bundles",
      "dependencies": [
        "P5.A",
        "P5.B"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P5.A, P5.B for foundation.",
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
          "src/v7/alpha/model/**",
          "configs/v7/alpha/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/model/**",
        "configs/v7/alpha/**"
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
        "Model + calibration + policy artifacts bundled per mode.",
        "Full lineage metadata stored in each bundle."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/model/**",
          "configs/v7/alpha/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P5.D",
      "title": "Training Metrics",
      "dependencies": [
        "P5.A",
        "P5.B"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P5.A, P5.B for foundation.",
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
          "src/v7/alpha/evaluation/**",
          "tests/v7/alpha/unit/evaluation/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "normal",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/evaluation/**",
        "tests/v7/alpha/unit/evaluation/**"
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
        "Classification report, regression metrics, and feature importance logged.",
        "Metrics are temporally-aware, not IID."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/evaluation/**",
          "tests/v7/alpha/unit/evaluation/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P5.E",
      "title": "Symbol Encoding Metadata",
      "dependencies": [
        "P5.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P5.A for foundation.",
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
          "src/v7/alpha/model/**",
          "configs/v7/alpha/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "normal",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/model/**",
        "configs/v7/alpha/**"
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
        "symbol_encoding_family and symbol_universe_version stored.",
        "MVP uses symbol_one_hot_v1."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "low",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/model/**",
          "configs/v7/alpha/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
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
  "phase": "P5",
  "title": "XGBoost Hybrid Model Training",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "selectedRepairMode": null,
  "targetPromotionMode": "stable_6",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "schedulerRuntimeUse": "enabled",
  "primaryGoal": "Mode-specific classifier and expected-R regressors.",
  "projectName": "v7_alphaforge_xgb",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresPatchIsolation": false,
  "requiresIntegrationQueue": true,
  "requiresPatchApplyQueue": false,
  "repositoryMutationAuthority": "worktree_integration",
  "queueOptimizationEnabled": true,
  "queueOptimizationStrategy": "priority_then_fifo",
  "continuousScheduling": true,
  "continuousSlotCount": 3,
  "safeEffectiveParallelismTarget": 2,
  "notInScope": [
    "External broker execution authority",
    "V7 runtime core modifications",
    "Non-XGBoost model families"
  ],
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
    "optimizer_patch_without_approval"
  ],
  "completionGate": "P5 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "P6"
}
```

---

## Review Hardening Requirements

* [ ] Symbol encoding metadata
* [ ] Training reproducibility

---

<!-- SOURCE: phase_plans/P6__calibration_reliability_and_alpha_score_builder.md -->

# P6 — Calibration, Reliability & Alpha Score Builder

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P6`  
**One-line goal:** Per-mode calibration, expected-R reliability, and long/short alpha-R scores.  
**Why now:** V7 policy cannot safely use raw model scores; probabilities and expected-R must be reliability-reviewed and converted into R-native alpha evidence.  
**Blast radius:** src/v7/alpha/**, tests/v7/alpha/**, configs/v7/alpha/**, docs/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Execution class:** `implementation`  
**Execution automation:** `enabled`  
**Scale mode:** `stable_3`  
**Safe parallelism target:** `2`  
**Done when:** All workspaces pass acceptance criteria and phase JSON validates through Pi doctor.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P6` |
| Title | `Calibration, Reliability & Alpha Score Builder` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Per-mode calibration, expected-R reliability, and long/short alpha-R scores.` |
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

V7 policy cannot safely use raw model scores; probabilities and expected-R must be reliability-reviewed and converted into R-native alpha evidence.

Raw XGBoost scores are not confidence. Calibration maps scores to calibrated probabilities. Regression reliability checks ensure expected-R buckets match realized averages. The alpha score builder converts calibrated outputs to R-native alpha evidence.

This phase uses `stable_3` scale-aware execution. The executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

---

## 3. What Carried Over — Must Stay Stable

* [ ] Runtime owns orchestration, execution, persistence, lifecycle, and hard safety.
* [ ] Model owns alpha evidence only.
* [ ] Simulation truth defines labels and evaluation.
* [ ] No hidden deterministic veto or hidden fallback.
* [ ] NO_TRADE remains first-class.
* [ ] Features are canonical-state only.
* [ ] Labels are mode-specific.
* [ ] Datasets are mode-specific and temporally split.
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

Raw XGBoost scores are not confidence. Calibration maps scores to calibrated probabilities. Regression reliability checks ensure expected-R buckets match realized averages. The alpha score builder converts calibrated outputs to R-native alpha evidence.

---

## 5. Current Failure State / Known Blockers

* `probability_calibration` = not implemented.
* `regression_reliability` = not implemented.
* `alpha_score_builder` = not implemented.
* `calibration_tests` = not implemented.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Worktree isolation violation | low | critical | Path scope checks; stop execution on escape |
| Integration queue merges unvalidated diff | medium | high | Require workspace validation and integration validation |
| Merge conflict blocks plan | medium | medium | Generate conflict handoff artifact and stop queue safely |
| Safe parallelism is lower than requested | medium | medium | Doctor warning; show bottleneck; use safe batch preview |
| Validation lock limits throughput | medium | medium | Scheduler reduces concurrency while heavy validation runs |
| High-risk workspace failure | medium | high | Rollback path defined; manual review gating |

---

## 7. Workstreams

### P6.A — Probability Calibration

**Goal:** Calibrated p_long, p_short, p_no_trade produced per mode.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Calibrated p_long, p_short, p_no_trade produced per mode.
* Calibration artifact stored with model bundle.

**File Scope:**
```text
src/v7/alpha/calibration/**
tests/v7/alpha/unit/calibration/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P6.B — Regression Reliability

**Goal:** Expected-R bucket vs realized average R comparison works.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Expected-R bucket vs realized average R comparison works.
* Sign correctness and adverse pressure reliability computed.

**File Scope:**
```text
src/v7/alpha/calibration/**
tests/v7/alpha/unit/calibration/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P6.C — Alpha Score Builder

**Goal:** long_alpha_R and short_alpha_R computed from calibrated p * expected-R * confidence.

**Dependencies:** P6.A, P6.B
**Parallel Group:** batch_2
**Risk Level:** medium
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* long_alpha_R and short_alpha_R computed from calibrated p * expected-R * confidence.
* recommended_alpha_action emitted.

**File Scope:**
```text
src/v7/alpha/scoring/**
tests/v7/alpha/unit/scoring/**
```

**Isolation & Parallelism Notes:**
* Depends on P6.A, P6.B for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P6.D — Calibration Tests

**Goal:** Calibration quality measured via reliability error.

**Dependencies:** P6.A, P6.B, P6.C
**Parallel Group:** batch_2
**Risk Level:** medium
**Queue Priority:** normal
**Can run with:** None

**Requirements:
* Calibration quality measured via reliability error.
* Degradation is explicit.

**File Scope:**
```text
tests/v7/alpha/unit/calibration/**
```

**Isolation & Parallelism Notes:**
* Depends on P6.A, P6.B, P6.C for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.


---

## 8. Combined Implementation Order

```text
  Batch batch_1: P6.A + P6.B
  Batch batch_2: P6.C + P6.D
```

The dependency graph dictates that foundation workspaces run first, followed by parallel batches where dependencies permit. The DAG batch preview and safe batch preview may differ because of file overlap, validation lock pressure, or integration queue serialization.

---

## 9. Definition of Done

`P6` is complete when ALL are true:

* [ ] Calibrated p_long, p_short, p_no_trade produced per mode.
* [ ] Expected-R bucket vs realized average R comparison works.
* [ ] long_alpha_R and short_alpha_R computed from calibrated p * expected-R * confidence.
* [ ] Calibration quality measured via reliability error.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation is valid for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] No forbidden commands or files were used.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Validation planner misses a required failure.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Disable worktree mode only if safe fallback is required.
4. Pause or disable integration queue processing.
5. Preserve `.pi/worktrees/{planExecId}/` for debugging.
6. Fall back to shared-working-tree execution if explicitly allowed.
7. Keep dashboard telemetry read-only if safe.
8. Revert phase commits independently if needed.

---

## 11. What Next Phase Inherits

`P7` inherits:

* `P6` execution contract with worktree mode awareness.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Workspace-level parallelism/isolation/integration/validation metadata.
* Review hardening invariants: Calibration quality gates

---

# Part 2 — Agent Brief

## Mission

Implement `P6` — Per-mode calibration, expected-R reliability, and long/short alpha-R scores.

The agent must optimize for safe parallelism, not maximum concurrency. Higher worker counts are allowed only when scale-mode readiness passes and the executor can preserve correctness through worktree isolation, integration queue, validation locks, and completion gates.



---

## Hard Requirements

1. All P6 workstreams must pass acceptance criteria.
2. Worktree isolation must be enabled for parallel workspaces.
3. Integration queue must serialize merges.
4. Global validation lock must be active for heavy validation.
5. Watch-mode validation is forbidden.
6. `git push` is forbidden.
7. Raw destructive cleanup is forbidden.
8. Do not exceed selected scale-mode worker cap (3).
9. Do not merge workspace output without passed workspace validation.
10. Do not mark the plan complete if integration validation fails.
11. Do not treat merge conflict as ordinary worker failure.
12. Do not start the next plan while integration queue state is dirty.

---

## Execution Policies

```yaml
repair_modes:
  manual_0: autonomous_execution_allowed: false, agent_may_mutate_repo: false
  stable_3: autonomous_execution_allowed: true,  agent_may_mutate_repo: true

execution_automation:
  autonomous_execution_enabled: true
  agent_may_mutate_repo: true
  agent_may_run_commands: true
  manual_patch_application_required: false
  human_approval_required_for_every_patch: false

bounded_liveness:
  no_indefinite_waits: true
  llm_provider_timeout_required: true
  llm_stream_idle_watchdog_required: true
  validation_timeout_required: true
  process_tree_kill_required: true
  git_lock_bypass_forbidden: true
  state_write_serialization_required: true

scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
  worktree_required: true
  integration_queue_required: true

validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true

queue_optimization:
  enabled_by_default: true
  default_strategy: priority_then_fifo
  priority_levels: [critical, high, normal, low]
```

---

## Safety Stops

* Dependency cycles
* Invalid dependency patches
* Worktree path escaping `.pi/worktrees`
* Integration merge without passed workspace validation
* Validation failure
* Merge conflict without handoff artifact
* Unsafe scale mode
* Queue starting next plan while integration queue is dirty
* Forbidden file access
* Secrets access
* `git push`
* Watch-mode validation
* `autonomous_execution_requested_during_repair_mode`
* `agent_repo_mutation_requested_during_manual_repair`
* `scheduler_enabled_before_executor_isolation_gate`
* `llm_call_without_provider_timeout`
* `validation_command_without_timeout`
* `git_lock_bypass_detected`
* `state_store_write_without_serialization`
* `workspace_patch_without_human_approval`
* `promotion_gate_failed_or_missing`


# Part 2.5 — v4 ExecutionKernel Doctrine

## 2.5.1 Single Authority Model

v4 replaces the previous executor-owned or multi-component execution state model with an ExecutionKernel model.

```text
Before v4:
  Scheduler, executor, validation runner, retry router, cleanup, lease monitor,
  diagnostics, and brain workers could each influence or write partial execution truth.

After v4:
  All actors emit events.
  WorkspaceAttemptController mutates attempt state.
  PlanSupervisor mutates plan state.
  PostgreSQL stores authoritative runtime truth.
```

## 2.5.2 ExecutionKernel Components

| Component | Responsibility | May mutate execution state? |
|---|---|---:|
| `ExecutionAdmissionGate` | Authorize or reject execution requests before runtime starts | No |
| `ExecutionProfileDeriver` | Convert intent to required mechanisms | No |
| `PlanSupervisor` | Own plan FSM, slot tokens, completion predicate, final validation | Yes, plan state only |
| `WorkspaceAttemptController` | Own attempt FSM, retries, terminalization, handoff creation | Yes, attempt state only |
| `StateStoreWriter` | Commit transitions with authority token | Yes, through token only |
| `AttemptEventJournal` | Append versioned event records | No state mutation by itself |
| `DeadlineWatchdog` | Detect expired attempts and emit events | No |
| `ExecutorActor` | Run LLM/tools/bash for an attempt | No |
| `ValidationActor` | Run validation with deadlines and process containment | No |
| `GitRunner` | Serialize Git repo mutations | No attempt state mutation |

## 2.5.3 Attempt FSM Doctrine

A v4 attempt is a bounded state machine. It cannot remain in a non-terminal state forever.

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
Failure paths: RUNNING+timeout -> TIMED_OUT, critical violation -> FAILED_FINAL
Terminal states: SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, TIMED_OUT, HANDOFF_REQUIRED
Retry is legal only after terminal state.
```

## 2.5.4 PostgreSQL Truth Doctrine

Runtime truth is PostgreSQL. JSON fallback is forbidden in production.

Allowed filesystem data: stdout/stderr logs, raw tool output, patch artifacts, handoff Markdown.
Forbidden as authoritative runtime truth: JSON state fallback, NDJSON-only journal, filesystem-only state.

## 2.5.5 Intent-Driven Plan Doctrine

v4 authors express what they want, not the low-level mechanism matrix.

Human-authored: `parallelism`, `safetyLevel`, `conflictRisk`, `deadlines`, `executionEnvironment`.
System-derived: worktree requirement, integration queue, validation lanes, drift policy, watchdog policy.


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
    "name": "v7_alphaforge_xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p6"
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
    "writeSetDriftPolicy": "reject_or_handoff",
    "explain": [
      "stable_3 worktree mode: 3 workers, worktree isolation, integration queue",
      "Worktree isolation required for safe parallel execution",
      "All production execution requires PostgreSQL authoritative runtime state"
    ]
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
  "attemptLifecycle": {
    "modeSpecificLifecycles": {
      "worktree": {
        "initialState": "queued",
        "nonTerminalStates": [
          "queued",
          "leasing_worktree",
          "running",
          "validating",
          "waiting_for_validation_lane",
          "integration_queued",
          "integrating"
        ],
        "terminalStates": [
          "succeeded",
          "failed_retryable",
          "failed_final",
          "aborted",
          "timed_out",
          "quarantined",
          "handoff_required"
        ]
      }
    },
    "retryableTerminalStates": [
      "failed_retryable",
      "timed_out",
      "quarantined"
    ],
    "retryForbiddenFromNonTerminal": true,
    "deadlineRequiredForNonTerminalStates": true,
    "handoffRequiredCreatesQueueItem": true
  },
  "planLifecycle": {
    "completionPredicateRequired": true,
    "cannotCompleteWithRequiredNonTerminalWorkspaces": true,
    "cannotCompleteWithUnresolvedRequiredHandoff": true,
    "finalValidationRequiredBeforeCompleted": true,
    "states": [
      "created",
      "preflight",
      "running",
      "blocked_with_reason",
      "awaiting_handoff",
      "final_validation",
      "completed",
      "completed_with_warnings",
      "failed_final",
      "stopping",
      "stopped"
    ]
  },
  "actorPermissions": {
    "workspaceAttemptController": {
      "mayMutateAttemptState": true,
      "mayCreateRetryAttempt": true
    },
    "planSupervisor": {
      "mayMutatePlanState": true,
      "mayReserveSchedulerSlots": true
    },
    "executorActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayProducePatchArtifact": true,
      "mayEmitEvents": true
    },
    "validationActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayEmitEvents": true
    },
    "gitRunner": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true,
      "note": "May perform low-level git operations only when invoked by authorized repository mutation authority."
    },
    "leaseMonitor": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true
    },
    "retryPolicy": {
      "mayMutateAttemptState": false,
      "mayCreateRetryAttempt": false,
      "maySuggestRetry": true
    },
    "brainWorkers": {
      "mayMutateExecutionState": false,
      "mayEmitDiagnosis": true,
      "mayProposeAction": true
    },
    "diagnostics": {
      "mayMutateExecutionState": false,
      "mayEmitEvidence": true
    }
  },
  "admissionGate": {
    "required": true,
    "allEntrypointsMustUseGate": true,
    "coveredEntrypoints": [
      "cli_plan_run",
      "dashboard_run",
      "api_plan_run",
      "retry_endpoint",
      "cleanup_rerun_endpoint",
      "brain_worker_trigger",
      "overnight_runner",
      "proposal_executor"
    ],
    "rejectWhen": [
      "postgres_unavailable_for_authoritative_runtime",
      "json_runtime_fallback_detected",
      "repair_mode_autonomous_execution_disabled",
      "promotion_gates_missing",
      "unsafe_parallelism_requested",
      "execution_kernel_disabled",
      "state_authority_not_single"
    ]
  },
  "resourceCoordination": {
    "nestedLocksForbidden": true,
    "holdLockAcrossAwaitForbidden": true,
    "stateLocks": {
      "scope": "attempt",
      "maxHoldMs": 1000
    },
    "planLock": {
      "scope": "plan",
      "maxHoldMs": 1000,
      "purpose": "slot_reservation_only"
    },
    "gitRunner": {
      "mode": "queue",
      "repoMutationTimeoutMs": 60000,
      "lockBypassForbidden": true
    },
    "validationLanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    },
    "worktreeLeases": {
      "attemptScoped": true,
      "heartbeatRequired": true,
      "quarantineOnStale": true
    },
    "stateStore": {
      "writesThroughControllerOnly": true,
      "transactionOrWriteQueueRequired": true
    }
  },
  "deadlineWatchdog": {
    "required": true,
    "intervalSeconds": 15,
    "emitsEventsOnly": true,
    "eventType": "deadline_exceeded",
    "supervised": true,
    "onWatchdogUnavailable": "block_new_execution_or_downgrade"
  },
  "handoffQueue": {
    "required": true,
    "createdByStates": [
      "handoff_required"
    ],
    "allowedActions": [
      "retry_requested",
      "close_failed",
      "manual_resolution",
      "followup_plan_requested"
    ],
    "controllerMediatedRetryRequired": true
  },
  "boundedLiveness": {
    "required": true,
    "noIndefiniteWaits": true,
    "llm": {
      "providerRequestTimeoutMs": 120000,
      "streamIdleTimeoutMs": 300000,
      "workspaceOverallTimeoutMs": 1800000,
      "maxConsecutiveProviderTimeouts": 2,
      "onCircuitOpen": "fail_workspace_not_plan"
    },
    "validation": {
      "defaultTimeoutMs": 600000,
      "heavyTimeoutMs": 1200000,
      "killProcessTreeOnTimeout": true,
      "watchModeForbidden": true,
      "stdinClosed": true,
      "ciEnvRequired": true,
      "maxOutputBytes": 52428800
    },
    "git": {
      "repoMutationLockTimeoutMs": 60000,
      "lockBypassForbidden": true,
      "onLockTimeout": "fail_fast_and_retry_or_handoff"
    },
    "scheduler": {
      "stallDetectionEnabled": true,
      "noProgressTimeoutMs": 300000,
      "onNoProgress": "emit_blocked_reason"
    },
    "stateStore": {
      "transactionOrWriteQueueRequired": true,
      "atomicSnapshotRequired": true,
      "journalLineAtomicityRequired": true
    }
  },
  "llmRuntime": {
    "boundedProviderCallsRequired": true,
    "providerRequestTimeoutMs": 120000,
    "streamIdleTimeoutMs": 300000,
    "workspaceOverallTimeoutMs": 1800000,
    "circuitBreaker": {
      "enabled": true,
      "openAfterConsecutiveTimeouts": 2,
      "cooldownMs": 300000
    },
    "fallbackPolicy": {
      "enabled": false,
      "reason": "Patches must remain deterministic."
    }
  },
  "validationRuntime": {
    "managedRunnerRequired": true,
    "processGroupRequired": true,
    "killTreeOnTimeout": true,
    "maxOutputBytes": 52428800,
    "forbiddenInteractiveCommands": [
      "vitest --watch",
      "jest --watch",
      "npm run dev",
      "vite --host"
    ],
    "lanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    }
  },
  "validationPolicy": {
    "defaultMode": "deferred",
    "workspaceCompletionRequiresTargetCommand": false,
    "planCompletionRequiresFinalValidation": true,
    "heavyValidationDeferredByDefault": true,
    "allowWorkspaceImmediateValidation": true,
    "allowSmokeValidation": true,
    "watchModeForbidden": true,
    "finalValidationWorkspaceRequired": true,
    "finalRepairWorkspaceRecommended": true,
    "validationArtifactsRequired": true,
    "liveValidationVisibilityRequired": true
  },
  "planExecution": {
    "phase": "P6",
    "title": "Calibration, Reliability & Alpha Score Builder",
    "mode": "implementation",
    "maxParallelWorkspaces": 3,
    "scheduling": {
      "continuous": true,
      "slotCount": 3,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": false,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "stable_3",
      "selectedMode": "stable_3",
      "modes": {
        "stable_3": {
          "executorType": "direct",
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false,
          "preserveExistingBehavior": true
        },
        "stable_6": {
          "executorType": "patch_transaction",
          "maxCodegenWorkers": 6,
          "patchIsolationRequired": true,
          "worktreeRequired": false,
          "patchCoordinatorRequired": true,
          "repositoryMutationAuthority": "patch_coordinator",
          "patchApplyLanes": 1,
          "singleRepositoryWriterRequired": true,
          "targetedValidationRequired": true,
          "finalIntegrationValidationRequired": true,
          "postgresRequired": true,
          "completionGateRequired": true
        },
        "experimental_worktree_6": {
          "executorType": "worktree",
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "explicitOptInRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true
    },
    "integrationQueue": {
      "enabled": true,
      "enabledForExecutorTypes": [
        "worktree"
      ],
      "processOneMergeAtATime": true,
      "stopOnMergeConflict": true,
      "requireWorkspaceValidationPass": true,
      "requireIntegrationValidationPass": true,
      "gitPushAllowed": false,
      "queuePriority": {
        "enabled": true,
        "defaultLevel": "normal",
        "levels": [
          "critical",
          "high",
          "normal",
          "low"
        ]
      },
      "queueOptimization": {
        "enabled": true,
        "strategy": "priority_then_fifo",
        "availableStrategies": [
          "priority_then_fifo",
          "critical_path_first",
          "weighted_shortest_job_first"
        ]
      }
    },
    "validation": {
      "globalValidationLockRequired": true,
      "targetedValidationEnabled": true,
      "finalIntegrationValidationRequired": true,
      "watchModeForbidden": true
    },
    "interactiveParallelismReview": {
      "enabled": true,
      "preflightRequired": true,
      "approvalRequiredBeforeRun": true,
      "allowDependencyEditing": true,
      "showEffectiveParallelism": true,
      "showSafeEffectiveParallelism": true,
      "showBatchPreview": true,
      "showSafeBatchPreview": true,
      "showCriticalPath": true,
      "showScaleModeReadiness": true,
      "warnWhenEffectiveParallelismBelowRequested": true,
      "warnWhenSafeParallelismBelowDagParallelism": true,
      "warnWhenScaleModePrerequisitesMissing": true,
      "persistApprovedGraph": true
    },
    "planIntake": {
      "enabled": true,
      "runOnUpload": true,
      "parserPriority": [
        "part3_json",
        "contractVersion_and_executionClass",
        "doctor",
        "execution_gate"
      ],
      "autoNormalize": true,
      "autoDoctor": true,
      "autoDagAnalysis": true,
      "autoOptimizationProposal": true,
      "autoQueuePriorityRecommendation": true,
      "autoWorkspaceSplitRecommendation": true,
      "autoDryRunForecast": true,
      "approvalRequiredBeforeApplyingOptimization": true,
      "approvalRequiredBeforeExecution": true
    },
    "optimizer": {
      "enabled": true,
      "mode": "advisory_until_approved",
      "objectives": [
        "maximize_safe_effective_parallelism",
        "minimize_critical_path",
        "minimize_same_file_conflicts",
        "minimize_validation_lock_contention",
        "prioritize_critical_path_queue_merges"
      ],
      "allowedPatches": [
        "dependencies",
        "parallelGroup",
        "queuePriority",
        "canRunWith",
        "cannotRunWith",
        "conflictScope",
        "workspaceSplitSuggestion",
        "workspaceMergeSuggestion"
      ],
      "forbiddenAutoPatches": [
        "allowedFiles",
        "forbiddenFiles",
        "capabilityManifest",
        "safety.hardStops",
        "forbiddenCommands"
      ]
    }
  },
  "controls": {
    "allowPause": true,
    "allowStop": true,
    "allowCancel": true,
    "resumePolicy": "paused_or_stopped_only"
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
      "git clean -fd",
      "vitest --watch",
      "jest --watch",
      "npm run dev"
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
  "parallelismReview": {
    "requestedMaxParallelWorkspaces": 3,
    "selectedScaleMode": "stable_3",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for parallel execution."
        },
        {
          "key": "integration_queue",
          "required": true,
          "met": true,
          "message": "Required for queued execution."
        },
        {
          "key": "validation_lock",
          "required": true,
          "met": true,
          "message": "Required for heavy validation."
        },
        {
          "key": "completion_gate",
          "required": true,
          "met": true,
          "message": "Required for completion hardening."
        }
      ]
    },
    "expectedDagEffectiveParallelismMin": 2,
    "expectedSafeEffectiveParallelismMin": 2,
    "dagEffectiveParallelism": null,
    "safeEffectiveParallelism": null,
    "preflightStatus": "required",
    "approvalState": "pending",
    "batchingStrategy": "dag_topological_batches_display_only",
    "safeBatchingStrategy": "dag_batches_with_p6_safety_constraints_display_only",
    "batchPreview": {
      "batches": [],
      "overallEffectiveParallelism": null,
      "criticalPath": [],
      "criticalPathLength": 0,
      "serializedTailLength": 0
    },
    "safeBatchPreview": {
      "batches": [],
      "overallSafeEffectiveParallelism": null,
      "bottlenecks": [],
      "blockedParallelismReasons": []
    },
    "optimizationReview": {
      "originalGraphHash": null,
      "proposedGraphHash": null,
      "approvedGraphHash": null,
      "originalDagEffectiveParallelism": null,
      "proposedDagEffectiveParallelism": null,
      "originalSafeEffectiveParallelism": null,
      "proposedSafeEffectiveParallelism": null,
      "criticalPathDelta": null,
      "serializedTailDelta": null,
      "suggestions": [],
      "approvalState": "pending"
    },
    "editableFields": [
      "workspaces[].dependencies",
      "workspaces[].parallelGroup",
      "workspaces[].dependencyReason",
      "workspaces[].parallelism.canRunWith",
      "workspaces[].parallelism.cannotRunWith",
      "workspaces[].parallelism.conflictScope",
      "workspaces[].integration.queuePriority",
      "workspaces[].integration.queueOptimizationNotes"
    ],
    "doctorWarnings": [
      "effective_parallelism_below_requested",
      "safe_parallelism_below_dag_parallelism",
      "fully_serialized_graph",
      "long_serialized_tail",
      "file_overlap_blocks_parallelism",
      "validation_lock_limits_parallelism",
      "integration_queue_serializes_merges",
      "scale_mode_prerequisites_missing",
      "worktree_isolation_required_for_scale",
      "queue_optimization_disabled_with_active_priority",
      "queue_priority_mismatch_with_configured_levels",
      "critical_path_workspace_has_low_priority",
      "optimizer_patch_without_approval"
    ],
    "persistedArtifacts": [
      "dependency_graph",
      "batch_preview",
      "safe_batch_preview",
      "critical_path",
      "scale_mode_readiness",
      "approved_dependency_patch",
      "approved_graph_hash",
      "queue_priority_snapshot",
      "queue_optimization_strategy",
      "queue_reorder_decision_log",
      "plan_intake_analysis",
      "optimizer_proposal",
      "graph_diff",
      "worktree_state",
      "lease_heartbeat_snapshots",
      "lease_reconciliation_log",
      "merge_priority_score_log",
      "empirical_write_set",
      "write_set_drift_report",
      "validation_lane_saturation_log"
    ]
  },
  "workspaces": [
    {
      "id": "P6.A",
      "title": "Probability Calibration",
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
          "src/v7/alpha/calibration/**",
          "tests/v7/alpha/unit/calibration/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/calibration/**",
        "tests/v7/alpha/unit/calibration/**"
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
        "Calibrated p_long, p_short, p_no_trade produced per mode.",
        "Calibration artifact stored with model bundle."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/calibration/**",
          "tests/v7/alpha/unit/calibration/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P6.B",
      "title": "Regression Reliability",
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
          "src/v7/alpha/calibration/**",
          "tests/v7/alpha/unit/calibration/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/calibration/**",
        "tests/v7/alpha/unit/calibration/**"
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
        "Expected-R bucket vs realized average R comparison works.",
        "Sign correctness and adverse pressure reliability computed."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/calibration/**",
          "tests/v7/alpha/unit/calibration/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P6.C",
      "title": "Alpha Score Builder",
      "dependencies": [
        "P6.A",
        "P6.B"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P6.A, P6.B for foundation.",
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
          "src/v7/alpha/scoring/**",
          "tests/v7/alpha/unit/scoring/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/scoring/**",
        "tests/v7/alpha/unit/scoring/**"
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
        "long_alpha_R and short_alpha_R computed from calibrated p * expected-R * confidence.",
        "recommended_alpha_action emitted."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/scoring/**",
          "tests/v7/alpha/unit/scoring/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P6.D",
      "title": "Calibration Tests",
      "dependencies": [
        "P6.A",
        "P6.B",
        "P6.C"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P6.A, P6.B, P6.C for foundation.",
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
          "tests/v7/alpha/unit/calibration/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "normal",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "tests/v7/alpha/unit/calibration/**"
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
        "Calibration quality measured via reliability error.",
        "Degradation is explicit."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "tests/v7/alpha/unit/calibration/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
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
  "phase": "P6",
  "title": "Calibration, Reliability & Alpha Score Builder",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "selectedRepairMode": null,
  "targetPromotionMode": "stable_6",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "schedulerRuntimeUse": "enabled",
  "primaryGoal": "Per-mode calibration, expected-R reliability, and long/short alpha-R scores.",
  "projectName": "v7_alphaforge_xgb",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresPatchIsolation": false,
  "requiresIntegrationQueue": true,
  "requiresPatchApplyQueue": false,
  "repositoryMutationAuthority": "worktree_integration",
  "queueOptimizationEnabled": true,
  "queueOptimizationStrategy": "priority_then_fifo",
  "continuousScheduling": true,
  "continuousSlotCount": 3,
  "safeEffectiveParallelismTarget": 2,
  "notInScope": [
    "External broker execution authority",
    "V7 runtime core modifications",
    "Non-XGBoost model families"
  ],
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
    "optimizer_patch_without_approval"
  ],
  "completionGate": "P6 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "P7"
}
```

---

## Review Hardening Requirements

* [ ] Calibration quality gates

---

<!-- SOURCE: phase_plans/P7__v7_policy_portfolio_and_risk_integration.md -->

# P7 — V7 Policy, Portfolio & Risk Integration

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P7`  
**One-line goal:** Bridge alpha predictions into V7 policy/risk decision surfaces.  
**Why now:** Alpha predictions become useful only when consumed by V7's explicit policy, portfolio, and risk layers without hidden execution authority.  
**Blast radius:** src/v7/alpha/**, tests/v7/alpha/**, configs/v7/alpha/**, docs/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Execution class:** `implementation`  
**Execution automation:** `enabled`  
**Scale mode:** `stable_3`  
**Safe parallelism target:** `2`  
**Done when:** All workspaces pass acceptance criteria and phase JSON validates through Pi doctor.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P7` |
| Title | `V7 Policy, Portfolio & Risk Integration` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Bridge alpha predictions into V7 policy/risk decision surfaces.` |
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

Alpha predictions become useful only when consumed by V7's explicit policy, portfolio, and risk layers without hidden execution authority.

V7 owns policy, portfolio, and risk. The alpha bridge must expose calibrated alpha scores, regime visibility, and action recommendations without hiding execution authority or silently overriding V7 decisions.

This phase uses `stable_3` scale-aware execution. The executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

---

## 3. What Carried Over — Must Stay Stable

* [ ] Runtime owns orchestration, execution, persistence, lifecycle, and hard safety.
* [ ] Model owns alpha evidence only.
* [ ] Simulation truth defines labels and evaluation.
* [ ] No hidden deterministic veto or hidden fallback.
* [ ] NO_TRADE remains first-class.
* [ ] Features are canonical-state only.
* [ ] Labels are mode-specific.
* [ ] Datasets are mode-specific and temporally split.
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

V7 owns policy, portfolio, and risk. The alpha bridge must expose calibrated alpha scores, regime visibility, and action recommendations without hiding execution authority or silently overriding V7 decisions.

---

## 5. Current Failure State / Known Blockers

* `policy_bridge` = not implemented.
* `portfolio_context` = not implemented.
* `risk_visibility` = not implemented.
* `runtime_contract_tests` = not implemented.
* `regime_override_visibility` = not implemented.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Worktree isolation violation | low | critical | Path scope checks; stop execution on escape |
| Integration queue merges unvalidated diff | medium | high | Require workspace validation and integration validation |
| Merge conflict blocks plan | medium | medium | Generate conflict handoff artifact and stop queue safely |
| Safe parallelism is lower than requested | medium | medium | Doctor warning; show bottleneck; use safe batch preview |
| Validation lock limits throughput | medium | medium | Scheduler reduces concurrency while heavy validation runs |
| High-risk workspace failure | medium | high | Rollback path defined; manual review gating |

---

## 7. Workstreams

### P7.A — Policy Bridge

**Goal:** Alpha scores flow to V7 policy layer.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Alpha scores flow to V7 policy layer.
* No hidden execution authority in bridge.
* Mode-specific min_alpha_R and min_confidence thresholds configurable.

**File Scope:**
```text
src/v7/alpha/policy_bridge/**
tests/v7/alpha/unit/policy_bridge/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P7.B — Portfolio Context

**Goal:** Portfolio pressure considered in action ranking.

**Dependencies:** P7.A
**Parallel Group:** batch_2
**Risk Level:** medium
**Queue Priority:** high
**Can run with:** None

**Requirements:
* Portfolio pressure considered in action ranking.
* Multi-symbol candidate ranking works.

**File Scope:**
```text
src/v7/alpha/policy_bridge/**
tests/v7/alpha/unit/policy_bridge/**
```

**Isolation & Parallelism Notes:**
* Depends on P7.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P7.C — Risk Visibility

**Goal:** Risk hard gates visible in AnalysisResult.

**Dependencies:** P7.A
**Parallel Group:** batch_2
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Risk hard gates visible in AnalysisResult.
* Regime override reason codes exposed.
* regime_gate_forced_no_trade, regime_blocked_direction tracked.

**File Scope:**
```text
src/v7/alpha/policy_bridge/**
tests/v7/alpha/unit/policy_bridge/**
```

**Isolation & Parallelism Notes:**
* Depends on P7.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P7.D — Runtime Contract Tests

**Goal:** End-to-end inference → policy → decision flow passes.

**Dependencies:** P7.A, P7.B, P7.C
**Parallel Group:** batch_3
**Risk Level:** medium
**Queue Priority:** normal
**Can run with:** None

**Requirements:
* End-to-end inference → policy → decision flow passes.
* No hidden veto or fallback.

**File Scope:**
```text
tests/v7/alpha/integration/**
```

**Isolation & Parallelism Notes:**
* Depends on P7.A, P7.B, P7.C for foundation.
* Expected batch: batch_3
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P7.E — Regime Override Visibility

**Goal:** DecisionEvent snapshots regime gate reason codes.

**Dependencies:** P7.C
**Parallel Group:** batch_3
**Risk Level:** high
**Queue Priority:** high
**Can run with:** None

**Requirements:
* DecisionEvent snapshots regime gate reason codes.
* Monitoring slices no-trade by model vs regime vs risk source.

**File Scope:**
```text
src/v7/alpha/policy_bridge/**
tests/v7/alpha/integration/**
```

**Isolation & Parallelism Notes:**
* Depends on P7.C for foundation.
* Expected batch: batch_3
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.


---

## 8. Combined Implementation Order

```text
  Batch batch_1: P7.A
  Batch batch_2: P7.B + P7.C
  Batch batch_3: P7.D + P7.E
```

The dependency graph dictates that foundation workspaces run first, followed by parallel batches where dependencies permit. The DAG batch preview and safe batch preview may differ because of file overlap, validation lock pressure, or integration queue serialization.

---

## 9. Definition of Done

`P7` is complete when ALL are true:

* [ ] Alpha scores flow to V7 policy layer.
* [ ] Portfolio pressure considered in action ranking.
* [ ] Risk hard gates visible in AnalysisResult.
* [ ] End-to-end inference → policy → decision flow passes.
* [ ] DecisionEvent snapshots regime gate reason codes.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation is valid for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] No forbidden commands or files were used.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Validation planner misses a required failure.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Disable worktree mode only if safe fallback is required.
4. Pause or disable integration queue processing.
5. Preserve `.pi/worktrees/{planExecId}/` for debugging.
6. Fall back to shared-working-tree execution if explicitly allowed.
7. Keep dashboard telemetry read-only if safe.
8. Revert phase commits independently if needed.

---

## 11. What Next Phase Inherits

`P8` inherits:

* `P7` execution contract with worktree mode awareness.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Workspace-level parallelism/isolation/integration/validation metadata.
* Review hardening invariants: Regime/deterministic override visibility, Policy bridge safety

---

# Part 2 — Agent Brief

## Mission

Implement `P7` — Bridge alpha predictions into V7 policy/risk decision surfaces.

The agent must optimize for safe parallelism, not maximum concurrency. Higher worker counts are allowed only when scale-mode readiness passes and the executor can preserve correctness through worktree isolation, integration queue, validation locks, and completion gates.



---

## Hard Requirements

1. All P7 workstreams must pass acceptance criteria.
2. Worktree isolation must be enabled for parallel workspaces.
3. Integration queue must serialize merges.
4. Global validation lock must be active for heavy validation.
5. Watch-mode validation is forbidden.
6. `git push` is forbidden.
7. Raw destructive cleanup is forbidden.
8. Do not exceed selected scale-mode worker cap (3).
9. Do not merge workspace output without passed workspace validation.
10. Do not mark the plan complete if integration validation fails.
11. Do not treat merge conflict as ordinary worker failure.
12. Do not start the next plan while integration queue state is dirty.

---

## Execution Policies

```yaml
repair_modes:
  manual_0: autonomous_execution_allowed: false, agent_may_mutate_repo: false
  stable_3: autonomous_execution_allowed: true,  agent_may_mutate_repo: true

execution_automation:
  autonomous_execution_enabled: true
  agent_may_mutate_repo: true
  agent_may_run_commands: true
  manual_patch_application_required: false
  human_approval_required_for_every_patch: false

bounded_liveness:
  no_indefinite_waits: true
  llm_provider_timeout_required: true
  llm_stream_idle_watchdog_required: true
  validation_timeout_required: true
  process_tree_kill_required: true
  git_lock_bypass_forbidden: true
  state_write_serialization_required: true

scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
  worktree_required: true
  integration_queue_required: true

validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true

queue_optimization:
  enabled_by_default: true
  default_strategy: priority_then_fifo
  priority_levels: [critical, high, normal, low]
```

---

## Safety Stops

* Dependency cycles
* Invalid dependency patches
* Worktree path escaping `.pi/worktrees`
* Integration merge without passed workspace validation
* Validation failure
* Merge conflict without handoff artifact
* Unsafe scale mode
* Queue starting next plan while integration queue is dirty
* Forbidden file access
* Secrets access
* `git push`
* Watch-mode validation
* `autonomous_execution_requested_during_repair_mode`
* `agent_repo_mutation_requested_during_manual_repair`
* `scheduler_enabled_before_executor_isolation_gate`
* `llm_call_without_provider_timeout`
* `validation_command_without_timeout`
* `git_lock_bypass_detected`
* `state_store_write_without_serialization`
* `workspace_patch_without_human_approval`
* `promotion_gate_failed_or_missing`


# Part 2.5 — v4 ExecutionKernel Doctrine

## 2.5.1 Single Authority Model

v4 replaces the previous executor-owned or multi-component execution state model with an ExecutionKernel model.

```text
Before v4:
  Scheduler, executor, validation runner, retry router, cleanup, lease monitor,
  diagnostics, and brain workers could each influence or write partial execution truth.

After v4:
  All actors emit events.
  WorkspaceAttemptController mutates attempt state.
  PlanSupervisor mutates plan state.
  PostgreSQL stores authoritative runtime truth.
```

## 2.5.2 ExecutionKernel Components

| Component | Responsibility | May mutate execution state? |
|---|---|---:|
| `ExecutionAdmissionGate` | Authorize or reject execution requests before runtime starts | No |
| `ExecutionProfileDeriver` | Convert intent to required mechanisms | No |
| `PlanSupervisor` | Own plan FSM, slot tokens, completion predicate, final validation | Yes, plan state only |
| `WorkspaceAttemptController` | Own attempt FSM, retries, terminalization, handoff creation | Yes, attempt state only |
| `StateStoreWriter` | Commit transitions with authority token | Yes, through token only |
| `AttemptEventJournal` | Append versioned event records | No state mutation by itself |
| `DeadlineWatchdog` | Detect expired attempts and emit events | No |
| `ExecutorActor` | Run LLM/tools/bash for an attempt | No |
| `ValidationActor` | Run validation with deadlines and process containment | No |
| `GitRunner` | Serialize Git repo mutations | No attempt state mutation |

## 2.5.3 Attempt FSM Doctrine

A v4 attempt is a bounded state machine. It cannot remain in a non-terminal state forever.

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
Failure paths: RUNNING+timeout -> TIMED_OUT, critical violation -> FAILED_FINAL
Terminal states: SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, TIMED_OUT, HANDOFF_REQUIRED
Retry is legal only after terminal state.
```

## 2.5.4 PostgreSQL Truth Doctrine

Runtime truth is PostgreSQL. JSON fallback is forbidden in production.

Allowed filesystem data: stdout/stderr logs, raw tool output, patch artifacts, handoff Markdown.
Forbidden as authoritative runtime truth: JSON state fallback, NDJSON-only journal, filesystem-only state.

## 2.5.5 Intent-Driven Plan Doctrine

v4 authors express what they want, not the low-level mechanism matrix.

Human-authored: `parallelism`, `safetyLevel`, `conflictRisk`, `deadlines`, `executionEnvironment`.
System-derived: worktree requirement, integration queue, validation lanes, drift policy, watchdog policy.


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
    "name": "v7_alphaforge_xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p7"
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
    "writeSetDriftPolicy": "reject_or_handoff",
    "explain": [
      "stable_3 worktree mode: 3 workers, worktree isolation, integration queue",
      "Worktree isolation required for safe parallel execution",
      "All production execution requires PostgreSQL authoritative runtime state"
    ]
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
  "attemptLifecycle": {
    "modeSpecificLifecycles": {
      "worktree": {
        "initialState": "queued",
        "nonTerminalStates": [
          "queued",
          "leasing_worktree",
          "running",
          "validating",
          "waiting_for_validation_lane",
          "integration_queued",
          "integrating"
        ],
        "terminalStates": [
          "succeeded",
          "failed_retryable",
          "failed_final",
          "aborted",
          "timed_out",
          "quarantined",
          "handoff_required"
        ]
      }
    },
    "retryableTerminalStates": [
      "failed_retryable",
      "timed_out",
      "quarantined"
    ],
    "retryForbiddenFromNonTerminal": true,
    "deadlineRequiredForNonTerminalStates": true,
    "handoffRequiredCreatesQueueItem": true
  },
  "planLifecycle": {
    "completionPredicateRequired": true,
    "cannotCompleteWithRequiredNonTerminalWorkspaces": true,
    "cannotCompleteWithUnresolvedRequiredHandoff": true,
    "finalValidationRequiredBeforeCompleted": true,
    "states": [
      "created",
      "preflight",
      "running",
      "blocked_with_reason",
      "awaiting_handoff",
      "final_validation",
      "completed",
      "completed_with_warnings",
      "failed_final",
      "stopping",
      "stopped"
    ]
  },
  "actorPermissions": {
    "workspaceAttemptController": {
      "mayMutateAttemptState": true,
      "mayCreateRetryAttempt": true
    },
    "planSupervisor": {
      "mayMutatePlanState": true,
      "mayReserveSchedulerSlots": true
    },
    "executorActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayProducePatchArtifact": true,
      "mayEmitEvents": true
    },
    "validationActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayEmitEvents": true
    },
    "gitRunner": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true,
      "note": "May perform low-level git operations only when invoked by authorized repository mutation authority."
    },
    "leaseMonitor": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true
    },
    "retryPolicy": {
      "mayMutateAttemptState": false,
      "mayCreateRetryAttempt": false,
      "maySuggestRetry": true
    },
    "brainWorkers": {
      "mayMutateExecutionState": false,
      "mayEmitDiagnosis": true,
      "mayProposeAction": true
    },
    "diagnostics": {
      "mayMutateExecutionState": false,
      "mayEmitEvidence": true
    }
  },
  "admissionGate": {
    "required": true,
    "allEntrypointsMustUseGate": true,
    "coveredEntrypoints": [
      "cli_plan_run",
      "dashboard_run",
      "api_plan_run",
      "retry_endpoint",
      "cleanup_rerun_endpoint",
      "brain_worker_trigger",
      "overnight_runner",
      "proposal_executor"
    ],
    "rejectWhen": [
      "postgres_unavailable_for_authoritative_runtime",
      "json_runtime_fallback_detected",
      "repair_mode_autonomous_execution_disabled",
      "promotion_gates_missing",
      "unsafe_parallelism_requested",
      "execution_kernel_disabled",
      "state_authority_not_single"
    ]
  },
  "resourceCoordination": {
    "nestedLocksForbidden": true,
    "holdLockAcrossAwaitForbidden": true,
    "stateLocks": {
      "scope": "attempt",
      "maxHoldMs": 1000
    },
    "planLock": {
      "scope": "plan",
      "maxHoldMs": 1000,
      "purpose": "slot_reservation_only"
    },
    "gitRunner": {
      "mode": "queue",
      "repoMutationTimeoutMs": 60000,
      "lockBypassForbidden": true
    },
    "validationLanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    },
    "worktreeLeases": {
      "attemptScoped": true,
      "heartbeatRequired": true,
      "quarantineOnStale": true
    },
    "stateStore": {
      "writesThroughControllerOnly": true,
      "transactionOrWriteQueueRequired": true
    }
  },
  "deadlineWatchdog": {
    "required": true,
    "intervalSeconds": 15,
    "emitsEventsOnly": true,
    "eventType": "deadline_exceeded",
    "supervised": true,
    "onWatchdogUnavailable": "block_new_execution_or_downgrade"
  },
  "handoffQueue": {
    "required": true,
    "createdByStates": [
      "handoff_required"
    ],
    "allowedActions": [
      "retry_requested",
      "close_failed",
      "manual_resolution",
      "followup_plan_requested"
    ],
    "controllerMediatedRetryRequired": true
  },
  "boundedLiveness": {
    "required": true,
    "noIndefiniteWaits": true,
    "llm": {
      "providerRequestTimeoutMs": 120000,
      "streamIdleTimeoutMs": 300000,
      "workspaceOverallTimeoutMs": 1800000,
      "maxConsecutiveProviderTimeouts": 2,
      "onCircuitOpen": "fail_workspace_not_plan"
    },
    "validation": {
      "defaultTimeoutMs": 600000,
      "heavyTimeoutMs": 1200000,
      "killProcessTreeOnTimeout": true,
      "watchModeForbidden": true,
      "stdinClosed": true,
      "ciEnvRequired": true,
      "maxOutputBytes": 52428800
    },
    "git": {
      "repoMutationLockTimeoutMs": 60000,
      "lockBypassForbidden": true,
      "onLockTimeout": "fail_fast_and_retry_or_handoff"
    },
    "scheduler": {
      "stallDetectionEnabled": true,
      "noProgressTimeoutMs": 300000,
      "onNoProgress": "emit_blocked_reason"
    },
    "stateStore": {
      "transactionOrWriteQueueRequired": true,
      "atomicSnapshotRequired": true,
      "journalLineAtomicityRequired": true
    }
  },
  "llmRuntime": {
    "boundedProviderCallsRequired": true,
    "providerRequestTimeoutMs": 120000,
    "streamIdleTimeoutMs": 300000,
    "workspaceOverallTimeoutMs": 1800000,
    "circuitBreaker": {
      "enabled": true,
      "openAfterConsecutiveTimeouts": 2,
      "cooldownMs": 300000
    },
    "fallbackPolicy": {
      "enabled": false,
      "reason": "Patches must remain deterministic."
    }
  },
  "validationRuntime": {
    "managedRunnerRequired": true,
    "processGroupRequired": true,
    "killTreeOnTimeout": true,
    "maxOutputBytes": 52428800,
    "forbiddenInteractiveCommands": [
      "vitest --watch",
      "jest --watch",
      "npm run dev",
      "vite --host"
    ],
    "lanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    }
  },
  "validationPolicy": {
    "defaultMode": "deferred",
    "workspaceCompletionRequiresTargetCommand": false,
    "planCompletionRequiresFinalValidation": true,
    "heavyValidationDeferredByDefault": true,
    "allowWorkspaceImmediateValidation": true,
    "allowSmokeValidation": true,
    "watchModeForbidden": true,
    "finalValidationWorkspaceRequired": true,
    "finalRepairWorkspaceRecommended": true,
    "validationArtifactsRequired": true,
    "liveValidationVisibilityRequired": true
  },
  "planExecution": {
    "phase": "P7",
    "title": "V7 Policy, Portfolio & Risk Integration",
    "mode": "implementation",
    "maxParallelWorkspaces": 3,
    "scheduling": {
      "continuous": true,
      "slotCount": 3,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": false,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "stable_3",
      "selectedMode": "stable_3",
      "modes": {
        "stable_3": {
          "executorType": "direct",
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false,
          "preserveExistingBehavior": true
        },
        "stable_6": {
          "executorType": "patch_transaction",
          "maxCodegenWorkers": 6,
          "patchIsolationRequired": true,
          "worktreeRequired": false,
          "patchCoordinatorRequired": true,
          "repositoryMutationAuthority": "patch_coordinator",
          "patchApplyLanes": 1,
          "singleRepositoryWriterRequired": true,
          "targetedValidationRequired": true,
          "finalIntegrationValidationRequired": true,
          "postgresRequired": true,
          "completionGateRequired": true
        },
        "experimental_worktree_6": {
          "executorType": "worktree",
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "explicitOptInRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true
    },
    "integrationQueue": {
      "enabled": true,
      "enabledForExecutorTypes": [
        "worktree"
      ],
      "processOneMergeAtATime": true,
      "stopOnMergeConflict": true,
      "requireWorkspaceValidationPass": true,
      "requireIntegrationValidationPass": true,
      "gitPushAllowed": false,
      "queuePriority": {
        "enabled": true,
        "defaultLevel": "normal",
        "levels": [
          "critical",
          "high",
          "normal",
          "low"
        ]
      },
      "queueOptimization": {
        "enabled": true,
        "strategy": "priority_then_fifo",
        "availableStrategies": [
          "priority_then_fifo",
          "critical_path_first",
          "weighted_shortest_job_first"
        ]
      }
    },
    "validation": {
      "globalValidationLockRequired": true,
      "targetedValidationEnabled": true,
      "finalIntegrationValidationRequired": true,
      "watchModeForbidden": true
    },
    "interactiveParallelismReview": {
      "enabled": true,
      "preflightRequired": true,
      "approvalRequiredBeforeRun": true,
      "allowDependencyEditing": true,
      "showEffectiveParallelism": true,
      "showSafeEffectiveParallelism": true,
      "showBatchPreview": true,
      "showSafeBatchPreview": true,
      "showCriticalPath": true,
      "showScaleModeReadiness": true,
      "warnWhenEffectiveParallelismBelowRequested": true,
      "warnWhenSafeParallelismBelowDagParallelism": true,
      "warnWhenScaleModePrerequisitesMissing": true,
      "persistApprovedGraph": true
    },
    "planIntake": {
      "enabled": true,
      "runOnUpload": true,
      "parserPriority": [
        "part3_json",
        "contractVersion_and_executionClass",
        "doctor",
        "execution_gate"
      ],
      "autoNormalize": true,
      "autoDoctor": true,
      "autoDagAnalysis": true,
      "autoOptimizationProposal": true,
      "autoQueuePriorityRecommendation": true,
      "autoWorkspaceSplitRecommendation": true,
      "autoDryRunForecast": true,
      "approvalRequiredBeforeApplyingOptimization": true,
      "approvalRequiredBeforeExecution": true
    },
    "optimizer": {
      "enabled": true,
      "mode": "advisory_until_approved",
      "objectives": [
        "maximize_safe_effective_parallelism",
        "minimize_critical_path",
        "minimize_same_file_conflicts",
        "minimize_validation_lock_contention",
        "prioritize_critical_path_queue_merges"
      ],
      "allowedPatches": [
        "dependencies",
        "parallelGroup",
        "queuePriority",
        "canRunWith",
        "cannotRunWith",
        "conflictScope",
        "workspaceSplitSuggestion",
        "workspaceMergeSuggestion"
      ],
      "forbiddenAutoPatches": [
        "allowedFiles",
        "forbiddenFiles",
        "capabilityManifest",
        "safety.hardStops",
        "forbiddenCommands"
      ]
    }
  },
  "controls": {
    "allowPause": true,
    "allowStop": true,
    "allowCancel": true,
    "resumePolicy": "paused_or_stopped_only"
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
      "git clean -fd",
      "vitest --watch",
      "jest --watch",
      "npm run dev"
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
  "parallelismReview": {
    "requestedMaxParallelWorkspaces": 3,
    "selectedScaleMode": "stable_3",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for parallel execution."
        },
        {
          "key": "integration_queue",
          "required": true,
          "met": true,
          "message": "Required for queued execution."
        },
        {
          "key": "validation_lock",
          "required": true,
          "met": true,
          "message": "Required for heavy validation."
        },
        {
          "key": "completion_gate",
          "required": true,
          "met": true,
          "message": "Required for completion hardening."
        }
      ]
    },
    "expectedDagEffectiveParallelismMin": 2,
    "expectedSafeEffectiveParallelismMin": 2,
    "dagEffectiveParallelism": null,
    "safeEffectiveParallelism": null,
    "preflightStatus": "required",
    "approvalState": "pending",
    "batchingStrategy": "dag_topological_batches_display_only",
    "safeBatchingStrategy": "dag_batches_with_p6_safety_constraints_display_only",
    "batchPreview": {
      "batches": [],
      "overallEffectiveParallelism": null,
      "criticalPath": [],
      "criticalPathLength": 0,
      "serializedTailLength": 0
    },
    "safeBatchPreview": {
      "batches": [],
      "overallSafeEffectiveParallelism": null,
      "bottlenecks": [],
      "blockedParallelismReasons": []
    },
    "optimizationReview": {
      "originalGraphHash": null,
      "proposedGraphHash": null,
      "approvedGraphHash": null,
      "originalDagEffectiveParallelism": null,
      "proposedDagEffectiveParallelism": null,
      "originalSafeEffectiveParallelism": null,
      "proposedSafeEffectiveParallelism": null,
      "criticalPathDelta": null,
      "serializedTailDelta": null,
      "suggestions": [],
      "approvalState": "pending"
    },
    "editableFields": [
      "workspaces[].dependencies",
      "workspaces[].parallelGroup",
      "workspaces[].dependencyReason",
      "workspaces[].parallelism.canRunWith",
      "workspaces[].parallelism.cannotRunWith",
      "workspaces[].parallelism.conflictScope",
      "workspaces[].integration.queuePriority",
      "workspaces[].integration.queueOptimizationNotes"
    ],
    "doctorWarnings": [
      "effective_parallelism_below_requested",
      "safe_parallelism_below_dag_parallelism",
      "fully_serialized_graph",
      "long_serialized_tail",
      "file_overlap_blocks_parallelism",
      "validation_lock_limits_parallelism",
      "integration_queue_serializes_merges",
      "scale_mode_prerequisites_missing",
      "worktree_isolation_required_for_scale",
      "queue_optimization_disabled_with_active_priority",
      "queue_priority_mismatch_with_configured_levels",
      "critical_path_workspace_has_low_priority",
      "optimizer_patch_without_approval"
    ],
    "persistedArtifacts": [
      "dependency_graph",
      "batch_preview",
      "safe_batch_preview",
      "critical_path",
      "scale_mode_readiness",
      "approved_dependency_patch",
      "approved_graph_hash",
      "queue_priority_snapshot",
      "queue_optimization_strategy",
      "queue_reorder_decision_log",
      "plan_intake_analysis",
      "optimizer_proposal",
      "graph_diff",
      "worktree_state",
      "lease_heartbeat_snapshots",
      "lease_reconciliation_log",
      "merge_priority_score_log",
      "empirical_write_set",
      "write_set_drift_report",
      "validation_lane_saturation_log"
    ]
  },
  "workspaces": [
    {
      "id": "P7.A",
      "title": "Policy Bridge",
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
          "src/v7/alpha/policy_bridge/**",
          "tests/v7/alpha/unit/policy_bridge/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/policy_bridge/**",
        "tests/v7/alpha/unit/policy_bridge/**"
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
        "Alpha scores flow to V7 policy layer.",
        "No hidden execution authority in bridge.",
        "Mode-specific min_alpha_R and min_confidence thresholds configurable."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/policy_bridge/**",
          "tests/v7/alpha/unit/policy_bridge/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P7.B",
      "title": "Portfolio Context",
      "dependencies": [
        "P7.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P7.A for foundation.",
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
          "src/v7/alpha/policy_bridge/**",
          "tests/v7/alpha/unit/policy_bridge/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/policy_bridge/**",
        "tests/v7/alpha/unit/policy_bridge/**"
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
        "Portfolio pressure considered in action ranking.",
        "Multi-symbol candidate ranking works."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/policy_bridge/**",
          "tests/v7/alpha/unit/policy_bridge/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P7.C",
      "title": "Risk Visibility",
      "dependencies": [
        "P7.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P7.A for foundation.",
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
          "src/v7/alpha/policy_bridge/**",
          "tests/v7/alpha/unit/policy_bridge/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/policy_bridge/**",
        "tests/v7/alpha/unit/policy_bridge/**"
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
        "Risk hard gates visible in AnalysisResult.",
        "Regime override reason codes exposed.",
        "regime_gate_forced_no_trade, regime_blocked_direction tracked."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/policy_bridge/**",
          "tests/v7/alpha/unit/policy_bridge/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P7.D",
      "title": "Runtime Contract Tests",
      "dependencies": [
        "P7.A",
        "P7.B",
        "P7.C"
      ],
      "parallelGroup": "batch_3",
      "dependencyReason": "Depends on P7.A, P7.B, P7.C for foundation.",
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
          "tests/v7/alpha/integration/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "normal",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "tests/v7/alpha/integration/**"
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
        "End-to-end inference \u2192 policy \u2192 decision flow passes.",
        "No hidden veto or fallback."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "tests/v7/alpha/integration/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P7.E",
      "title": "Regime Override Visibility",
      "dependencies": [
        "P7.C"
      ],
      "parallelGroup": "batch_3",
      "dependencyReason": "Depends on P7.C for foundation.",
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
          "src/v7/alpha/policy_bridge/**",
          "tests/v7/alpha/integration/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/policy_bridge/**",
        "tests/v7/alpha/integration/**"
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
        "DecisionEvent snapshots regime gate reason codes.",
        "Monitoring slices no-trade by model vs regime vs risk source."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/policy_bridge/**",
          "tests/v7/alpha/integration/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
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
  "phase": "P7",
  "title": "V7 Policy, Portfolio & Risk Integration",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "selectedRepairMode": null,
  "targetPromotionMode": "stable_6",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "schedulerRuntimeUse": "enabled",
  "primaryGoal": "Bridge alpha predictions into V7 policy/risk decision surfaces.",
  "projectName": "v7_alphaforge_xgb",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresPatchIsolation": false,
  "requiresIntegrationQueue": true,
  "requiresPatchApplyQueue": false,
  "repositoryMutationAuthority": "worktree_integration",
  "queueOptimizationEnabled": true,
  "queueOptimizationStrategy": "priority_then_fifo",
  "continuousScheduling": true,
  "continuousSlotCount": 3,
  "safeEffectiveParallelismTarget": 2,
  "notInScope": [
    "External broker execution authority",
    "V7 runtime core modifications",
    "Non-XGBoost model families"
  ],
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
    "optimizer_patch_without_approval"
  ],
  "completionGate": "P7 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "P8"
}
```

---

## Review Hardening Requirements

* [ ] Regime/deterministic override visibility
* [ ] Policy bridge safety

---

<!-- SOURCE: phase_plans/P8__evaluation_backtest_paper_and_shadow_validation.md -->

# P8 — Evaluation, Backtest, Paper & Shadow Validation

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P8`  
**One-line goal:** Economic evaluation, no-trade quality, calibration quality, and shadow/paper readiness.  
**Why now:** Model promotion requires out-of-sample economic evidence, not raw accuracy or training metrics.  
**Blast radius:** src/v7/alpha/**, tests/v7/alpha/**, configs/v7/alpha/**, docs/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Execution class:** `implementation`  
**Execution automation:** `enabled`  
**Scale mode:** `stable_3`  
**Safe parallelism target:** `2`  
**Done when:** All workspaces pass acceptance criteria and phase JSON validates through Pi doctor.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P8` |
| Title | `Evaluation, Backtest, Paper & Shadow Validation` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Economic evaluation, no-trade quality, calibration quality, and shadow/paper readiness.` |
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

Model promotion requires out-of-sample economic evidence, not raw accuracy or training metrics.

Walk-forward evaluation must measure economic quality (R-multiple), no-trade quality, calibration reliability, and regime/symbol stability. Paper and shadow modes must exist before live eligibility.

This phase uses `stable_3` scale-aware execution. The executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

---

## 3. What Carried Over — Must Stay Stable

* [ ] Runtime owns orchestration, execution, persistence, lifecycle, and hard safety.
* [ ] Model owns alpha evidence only.
* [ ] Simulation truth defines labels and evaluation.
* [ ] No hidden deterministic veto or hidden fallback.
* [ ] NO_TRADE remains first-class.
* [ ] Features are canonical-state only.
* [ ] Labels are mode-specific.
* [ ] Datasets are mode-specific and temporally split.
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

Walk-forward evaluation must measure economic quality (R-multiple), no-trade quality, calibration reliability, and regime/symbol stability. Paper and shadow modes must exist before live eligibility.

---

## 5. Current Failure State / Known Blockers

* `walk_forward_evaluation` = not implemented.
* `ablations` = not implemented.
* `paper_shadow_harness` = not implemented.
* `promotion_report` = not implemented.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Worktree isolation violation | low | critical | Path scope checks; stop execution on escape |
| Integration queue merges unvalidated diff | medium | high | Require workspace validation and integration validation |
| Merge conflict blocks plan | medium | medium | Generate conflict handoff artifact and stop queue safely |
| Safe parallelism is lower than requested | medium | medium | Doctor warning; show bottleneck; use safe batch preview |
| Validation lock limits throughput | medium | medium | Scheduler reduces concurrency while heavy validation runs |
| High-risk workspace failure | medium | high | Rollback path defined; manual review gating |

---

## 7. Workstreams

### P8.A — Walk-Forward Evaluation

**Goal:** Economic quality metrics computed per fold.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Economic quality metrics computed per fold.
* No-trade quality, calibration, regression reliability evaluated.

**File Scope:**
```text
src/v7/alpha/evaluation/**
tests/v7/alpha/unit/evaluation/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P8.B — Ablations

**Goal:** Feature ablation, symbol stability, regime stability measured.

**Dependencies:** P8.A
**Parallel Group:** batch_2
**Risk Level:** medium
**Queue Priority:** high
**Can run with:** None

**Requirements:
* Feature ablation, symbol stability, regime stability measured.

**File Scope:**
```text
src/v7/alpha/evaluation/**
tests/v7/alpha/unit/evaluation/**
```

**Isolation & Parallelism Notes:**
* Depends on P8.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P8.C — Paper/Shadow Harness

**Goal:** Paper mode inference without execution exists.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Paper mode inference without execution exists.
* Shadow mode runs alongside live without affecting decisions.

**File Scope:**
```text
src/v7/alpha/runtime/**
tests/v7/alpha/integration/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P8.D — Promotion Report

**Goal:** Report summarizes all evaluation evidence for promotion review.

**Dependencies:** P8.A, P8.B, P8.C
**Parallel Group:** batch_3
**Risk Level:** low
**Queue Priority:** normal
**Can run with:** None

**Requirements:
* Report summarizes all evaluation evidence for promotion review.
* Rollback recommendation included.

**File Scope:**
```text
docs/v7/alpha/**
```

**Isolation & Parallelism Notes:**
* Depends on P8.A, P8.B, P8.C for foundation.
* Expected batch: batch_3
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.


---

## 8. Combined Implementation Order

```text
  Batch batch_1: P8.A + P8.C
  Batch batch_2: P8.B
  Batch batch_3: P8.D
```

The dependency graph dictates that foundation workspaces run first, followed by parallel batches where dependencies permit. The DAG batch preview and safe batch preview may differ because of file overlap, validation lock pressure, or integration queue serialization.

---

## 9. Definition of Done

`P8` is complete when ALL are true:

* [ ] Economic quality metrics computed per fold.
* [ ] Feature ablation, symbol stability, regime stability measured.
* [ ] Paper mode inference without execution exists.
* [ ] Report summarizes all evaluation evidence for promotion review.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation is valid for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] No forbidden commands or files were used.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Validation planner misses a required failure.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Disable worktree mode only if safe fallback is required.
4. Pause or disable integration queue processing.
5. Preserve `.pi/worktrees/{planExecId}/` for debugging.
6. Fall back to shared-working-tree execution if explicitly allowed.
7. Keep dashboard telemetry read-only if safe.
8. Revert phase commits independently if needed.

---

## 11. What Next Phase Inherits

`P9` inherits:

* `P8` execution contract with worktree mode awareness.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Workspace-level parallelism/isolation/integration/validation metadata.
* Review hardening invariants: Walk-forward economic evaluation, No-trade quality visibility

---

# Part 2 — Agent Brief

## Mission

Implement `P8` — Economic evaluation, no-trade quality, calibration quality, and shadow/paper readiness.

The agent must optimize for safe parallelism, not maximum concurrency. Higher worker counts are allowed only when scale-mode readiness passes and the executor can preserve correctness through worktree isolation, integration queue, validation locks, and completion gates.



---

## Hard Requirements

1. All P8 workstreams must pass acceptance criteria.
2. Worktree isolation must be enabled for parallel workspaces.
3. Integration queue must serialize merges.
4. Global validation lock must be active for heavy validation.
5. Watch-mode validation is forbidden.
6. `git push` is forbidden.
7. Raw destructive cleanup is forbidden.
8. Do not exceed selected scale-mode worker cap (3).
9. Do not merge workspace output without passed workspace validation.
10. Do not mark the plan complete if integration validation fails.
11. Do not treat merge conflict as ordinary worker failure.
12. Do not start the next plan while integration queue state is dirty.

---

## Execution Policies

```yaml
repair_modes:
  manual_0: autonomous_execution_allowed: false, agent_may_mutate_repo: false
  stable_3: autonomous_execution_allowed: true,  agent_may_mutate_repo: true

execution_automation:
  autonomous_execution_enabled: true
  agent_may_mutate_repo: true
  agent_may_run_commands: true
  manual_patch_application_required: false
  human_approval_required_for_every_patch: false

bounded_liveness:
  no_indefinite_waits: true
  llm_provider_timeout_required: true
  llm_stream_idle_watchdog_required: true
  validation_timeout_required: true
  process_tree_kill_required: true
  git_lock_bypass_forbidden: true
  state_write_serialization_required: true

scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
  worktree_required: true
  integration_queue_required: true

validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true

queue_optimization:
  enabled_by_default: true
  default_strategy: priority_then_fifo
  priority_levels: [critical, high, normal, low]
```

---

## Safety Stops

* Dependency cycles
* Invalid dependency patches
* Worktree path escaping `.pi/worktrees`
* Integration merge without passed workspace validation
* Validation failure
* Merge conflict without handoff artifact
* Unsafe scale mode
* Queue starting next plan while integration queue is dirty
* Forbidden file access
* Secrets access
* `git push`
* Watch-mode validation
* `autonomous_execution_requested_during_repair_mode`
* `agent_repo_mutation_requested_during_manual_repair`
* `scheduler_enabled_before_executor_isolation_gate`
* `llm_call_without_provider_timeout`
* `validation_command_without_timeout`
* `git_lock_bypass_detected`
* `state_store_write_without_serialization`
* `workspace_patch_without_human_approval`
* `promotion_gate_failed_or_missing`


# Part 2.5 — v4 ExecutionKernel Doctrine

## 2.5.1 Single Authority Model

v4 replaces the previous executor-owned or multi-component execution state model with an ExecutionKernel model.

```text
Before v4:
  Scheduler, executor, validation runner, retry router, cleanup, lease monitor,
  diagnostics, and brain workers could each influence or write partial execution truth.

After v4:
  All actors emit events.
  WorkspaceAttemptController mutates attempt state.
  PlanSupervisor mutates plan state.
  PostgreSQL stores authoritative runtime truth.
```

## 2.5.2 ExecutionKernel Components

| Component | Responsibility | May mutate execution state? |
|---|---|---:|
| `ExecutionAdmissionGate` | Authorize or reject execution requests before runtime starts | No |
| `ExecutionProfileDeriver` | Convert intent to required mechanisms | No |
| `PlanSupervisor` | Own plan FSM, slot tokens, completion predicate, final validation | Yes, plan state only |
| `WorkspaceAttemptController` | Own attempt FSM, retries, terminalization, handoff creation | Yes, attempt state only |
| `StateStoreWriter` | Commit transitions with authority token | Yes, through token only |
| `AttemptEventJournal` | Append versioned event records | No state mutation by itself |
| `DeadlineWatchdog` | Detect expired attempts and emit events | No |
| `ExecutorActor` | Run LLM/tools/bash for an attempt | No |
| `ValidationActor` | Run validation with deadlines and process containment | No |
| `GitRunner` | Serialize Git repo mutations | No attempt state mutation |

## 2.5.3 Attempt FSM Doctrine

A v4 attempt is a bounded state machine. It cannot remain in a non-terminal state forever.

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
Failure paths: RUNNING+timeout -> TIMED_OUT, critical violation -> FAILED_FINAL
Terminal states: SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, TIMED_OUT, HANDOFF_REQUIRED
Retry is legal only after terminal state.
```

## 2.5.4 PostgreSQL Truth Doctrine

Runtime truth is PostgreSQL. JSON fallback is forbidden in production.

Allowed filesystem data: stdout/stderr logs, raw tool output, patch artifacts, handoff Markdown.
Forbidden as authoritative runtime truth: JSON state fallback, NDJSON-only journal, filesystem-only state.

## 2.5.5 Intent-Driven Plan Doctrine

v4 authors express what they want, not the low-level mechanism matrix.

Human-authored: `parallelism`, `safetyLevel`, `conflictRisk`, `deadlines`, `executionEnvironment`.
System-derived: worktree requirement, integration queue, validation lanes, drift policy, watchdog policy.


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
    "name": "v7_alphaforge_xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p8"
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
    "writeSetDriftPolicy": "reject_or_handoff",
    "explain": [
      "stable_3 worktree mode: 3 workers, worktree isolation, integration queue",
      "Worktree isolation required for safe parallel execution",
      "All production execution requires PostgreSQL authoritative runtime state"
    ]
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
  "attemptLifecycle": {
    "modeSpecificLifecycles": {
      "worktree": {
        "initialState": "queued",
        "nonTerminalStates": [
          "queued",
          "leasing_worktree",
          "running",
          "validating",
          "waiting_for_validation_lane",
          "integration_queued",
          "integrating"
        ],
        "terminalStates": [
          "succeeded",
          "failed_retryable",
          "failed_final",
          "aborted",
          "timed_out",
          "quarantined",
          "handoff_required"
        ]
      }
    },
    "retryableTerminalStates": [
      "failed_retryable",
      "timed_out",
      "quarantined"
    ],
    "retryForbiddenFromNonTerminal": true,
    "deadlineRequiredForNonTerminalStates": true,
    "handoffRequiredCreatesQueueItem": true
  },
  "planLifecycle": {
    "completionPredicateRequired": true,
    "cannotCompleteWithRequiredNonTerminalWorkspaces": true,
    "cannotCompleteWithUnresolvedRequiredHandoff": true,
    "finalValidationRequiredBeforeCompleted": true,
    "states": [
      "created",
      "preflight",
      "running",
      "blocked_with_reason",
      "awaiting_handoff",
      "final_validation",
      "completed",
      "completed_with_warnings",
      "failed_final",
      "stopping",
      "stopped"
    ]
  },
  "actorPermissions": {
    "workspaceAttemptController": {
      "mayMutateAttemptState": true,
      "mayCreateRetryAttempt": true
    },
    "planSupervisor": {
      "mayMutatePlanState": true,
      "mayReserveSchedulerSlots": true
    },
    "executorActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayProducePatchArtifact": true,
      "mayEmitEvents": true
    },
    "validationActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayEmitEvents": true
    },
    "gitRunner": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true,
      "note": "May perform low-level git operations only when invoked by authorized repository mutation authority."
    },
    "leaseMonitor": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true
    },
    "retryPolicy": {
      "mayMutateAttemptState": false,
      "mayCreateRetryAttempt": false,
      "maySuggestRetry": true
    },
    "brainWorkers": {
      "mayMutateExecutionState": false,
      "mayEmitDiagnosis": true,
      "mayProposeAction": true
    },
    "diagnostics": {
      "mayMutateExecutionState": false,
      "mayEmitEvidence": true
    }
  },
  "admissionGate": {
    "required": true,
    "allEntrypointsMustUseGate": true,
    "coveredEntrypoints": [
      "cli_plan_run",
      "dashboard_run",
      "api_plan_run",
      "retry_endpoint",
      "cleanup_rerun_endpoint",
      "brain_worker_trigger",
      "overnight_runner",
      "proposal_executor"
    ],
    "rejectWhen": [
      "postgres_unavailable_for_authoritative_runtime",
      "json_runtime_fallback_detected",
      "repair_mode_autonomous_execution_disabled",
      "promotion_gates_missing",
      "unsafe_parallelism_requested",
      "execution_kernel_disabled",
      "state_authority_not_single"
    ]
  },
  "resourceCoordination": {
    "nestedLocksForbidden": true,
    "holdLockAcrossAwaitForbidden": true,
    "stateLocks": {
      "scope": "attempt",
      "maxHoldMs": 1000
    },
    "planLock": {
      "scope": "plan",
      "maxHoldMs": 1000,
      "purpose": "slot_reservation_only"
    },
    "gitRunner": {
      "mode": "queue",
      "repoMutationTimeoutMs": 60000,
      "lockBypassForbidden": true
    },
    "validationLanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    },
    "worktreeLeases": {
      "attemptScoped": true,
      "heartbeatRequired": true,
      "quarantineOnStale": true
    },
    "stateStore": {
      "writesThroughControllerOnly": true,
      "transactionOrWriteQueueRequired": true
    }
  },
  "deadlineWatchdog": {
    "required": true,
    "intervalSeconds": 15,
    "emitsEventsOnly": true,
    "eventType": "deadline_exceeded",
    "supervised": true,
    "onWatchdogUnavailable": "block_new_execution_or_downgrade"
  },
  "handoffQueue": {
    "required": true,
    "createdByStates": [
      "handoff_required"
    ],
    "allowedActions": [
      "retry_requested",
      "close_failed",
      "manual_resolution",
      "followup_plan_requested"
    ],
    "controllerMediatedRetryRequired": true
  },
  "boundedLiveness": {
    "required": true,
    "noIndefiniteWaits": true,
    "llm": {
      "providerRequestTimeoutMs": 120000,
      "streamIdleTimeoutMs": 300000,
      "workspaceOverallTimeoutMs": 1800000,
      "maxConsecutiveProviderTimeouts": 2,
      "onCircuitOpen": "fail_workspace_not_plan"
    },
    "validation": {
      "defaultTimeoutMs": 600000,
      "heavyTimeoutMs": 1200000,
      "killProcessTreeOnTimeout": true,
      "watchModeForbidden": true,
      "stdinClosed": true,
      "ciEnvRequired": true,
      "maxOutputBytes": 52428800
    },
    "git": {
      "repoMutationLockTimeoutMs": 60000,
      "lockBypassForbidden": true,
      "onLockTimeout": "fail_fast_and_retry_or_handoff"
    },
    "scheduler": {
      "stallDetectionEnabled": true,
      "noProgressTimeoutMs": 300000,
      "onNoProgress": "emit_blocked_reason"
    },
    "stateStore": {
      "transactionOrWriteQueueRequired": true,
      "atomicSnapshotRequired": true,
      "journalLineAtomicityRequired": true
    }
  },
  "llmRuntime": {
    "boundedProviderCallsRequired": true,
    "providerRequestTimeoutMs": 120000,
    "streamIdleTimeoutMs": 300000,
    "workspaceOverallTimeoutMs": 1800000,
    "circuitBreaker": {
      "enabled": true,
      "openAfterConsecutiveTimeouts": 2,
      "cooldownMs": 300000
    },
    "fallbackPolicy": {
      "enabled": false,
      "reason": "Patches must remain deterministic."
    }
  },
  "validationRuntime": {
    "managedRunnerRequired": true,
    "processGroupRequired": true,
    "killTreeOnTimeout": true,
    "maxOutputBytes": 52428800,
    "forbiddenInteractiveCommands": [
      "vitest --watch",
      "jest --watch",
      "npm run dev",
      "vite --host"
    ],
    "lanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    }
  },
  "validationPolicy": {
    "defaultMode": "deferred",
    "workspaceCompletionRequiresTargetCommand": false,
    "planCompletionRequiresFinalValidation": true,
    "heavyValidationDeferredByDefault": true,
    "allowWorkspaceImmediateValidation": true,
    "allowSmokeValidation": true,
    "watchModeForbidden": true,
    "finalValidationWorkspaceRequired": true,
    "finalRepairWorkspaceRecommended": true,
    "validationArtifactsRequired": true,
    "liveValidationVisibilityRequired": true
  },
  "planExecution": {
    "phase": "P8",
    "title": "Evaluation, Backtest, Paper & Shadow Validation",
    "mode": "implementation",
    "maxParallelWorkspaces": 3,
    "scheduling": {
      "continuous": true,
      "slotCount": 3,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": false,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "stable_3",
      "selectedMode": "stable_3",
      "modes": {
        "stable_3": {
          "executorType": "direct",
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false,
          "preserveExistingBehavior": true
        },
        "stable_6": {
          "executorType": "patch_transaction",
          "maxCodegenWorkers": 6,
          "patchIsolationRequired": true,
          "worktreeRequired": false,
          "patchCoordinatorRequired": true,
          "repositoryMutationAuthority": "patch_coordinator",
          "patchApplyLanes": 1,
          "singleRepositoryWriterRequired": true,
          "targetedValidationRequired": true,
          "finalIntegrationValidationRequired": true,
          "postgresRequired": true,
          "completionGateRequired": true
        },
        "experimental_worktree_6": {
          "executorType": "worktree",
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "explicitOptInRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true
    },
    "integrationQueue": {
      "enabled": true,
      "enabledForExecutorTypes": [
        "worktree"
      ],
      "processOneMergeAtATime": true,
      "stopOnMergeConflict": true,
      "requireWorkspaceValidationPass": true,
      "requireIntegrationValidationPass": true,
      "gitPushAllowed": false,
      "queuePriority": {
        "enabled": true,
        "defaultLevel": "normal",
        "levels": [
          "critical",
          "high",
          "normal",
          "low"
        ]
      },
      "queueOptimization": {
        "enabled": true,
        "strategy": "priority_then_fifo",
        "availableStrategies": [
          "priority_then_fifo",
          "critical_path_first",
          "weighted_shortest_job_first"
        ]
      }
    },
    "validation": {
      "globalValidationLockRequired": true,
      "targetedValidationEnabled": true,
      "finalIntegrationValidationRequired": true,
      "watchModeForbidden": true
    },
    "interactiveParallelismReview": {
      "enabled": true,
      "preflightRequired": true,
      "approvalRequiredBeforeRun": true,
      "allowDependencyEditing": true,
      "showEffectiveParallelism": true,
      "showSafeEffectiveParallelism": true,
      "showBatchPreview": true,
      "showSafeBatchPreview": true,
      "showCriticalPath": true,
      "showScaleModeReadiness": true,
      "warnWhenEffectiveParallelismBelowRequested": true,
      "warnWhenSafeParallelismBelowDagParallelism": true,
      "warnWhenScaleModePrerequisitesMissing": true,
      "persistApprovedGraph": true
    },
    "planIntake": {
      "enabled": true,
      "runOnUpload": true,
      "parserPriority": [
        "part3_json",
        "contractVersion_and_executionClass",
        "doctor",
        "execution_gate"
      ],
      "autoNormalize": true,
      "autoDoctor": true,
      "autoDagAnalysis": true,
      "autoOptimizationProposal": true,
      "autoQueuePriorityRecommendation": true,
      "autoWorkspaceSplitRecommendation": true,
      "autoDryRunForecast": true,
      "approvalRequiredBeforeApplyingOptimization": true,
      "approvalRequiredBeforeExecution": true
    },
    "optimizer": {
      "enabled": true,
      "mode": "advisory_until_approved",
      "objectives": [
        "maximize_safe_effective_parallelism",
        "minimize_critical_path",
        "minimize_same_file_conflicts",
        "minimize_validation_lock_contention",
        "prioritize_critical_path_queue_merges"
      ],
      "allowedPatches": [
        "dependencies",
        "parallelGroup",
        "queuePriority",
        "canRunWith",
        "cannotRunWith",
        "conflictScope",
        "workspaceSplitSuggestion",
        "workspaceMergeSuggestion"
      ],
      "forbiddenAutoPatches": [
        "allowedFiles",
        "forbiddenFiles",
        "capabilityManifest",
        "safety.hardStops",
        "forbiddenCommands"
      ]
    }
  },
  "controls": {
    "allowPause": true,
    "allowStop": true,
    "allowCancel": true,
    "resumePolicy": "paused_or_stopped_only"
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
      "git clean -fd",
      "vitest --watch",
      "jest --watch",
      "npm run dev"
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
  "parallelismReview": {
    "requestedMaxParallelWorkspaces": 3,
    "selectedScaleMode": "stable_3",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for parallel execution."
        },
        {
          "key": "integration_queue",
          "required": true,
          "met": true,
          "message": "Required for queued execution."
        },
        {
          "key": "validation_lock",
          "required": true,
          "met": true,
          "message": "Required for heavy validation."
        },
        {
          "key": "completion_gate",
          "required": true,
          "met": true,
          "message": "Required for completion hardening."
        }
      ]
    },
    "expectedDagEffectiveParallelismMin": 2,
    "expectedSafeEffectiveParallelismMin": 2,
    "dagEffectiveParallelism": null,
    "safeEffectiveParallelism": null,
    "preflightStatus": "required",
    "approvalState": "pending",
    "batchingStrategy": "dag_topological_batches_display_only",
    "safeBatchingStrategy": "dag_batches_with_p6_safety_constraints_display_only",
    "batchPreview": {
      "batches": [],
      "overallEffectiveParallelism": null,
      "criticalPath": [],
      "criticalPathLength": 0,
      "serializedTailLength": 0
    },
    "safeBatchPreview": {
      "batches": [],
      "overallSafeEffectiveParallelism": null,
      "bottlenecks": [],
      "blockedParallelismReasons": []
    },
    "optimizationReview": {
      "originalGraphHash": null,
      "proposedGraphHash": null,
      "approvedGraphHash": null,
      "originalDagEffectiveParallelism": null,
      "proposedDagEffectiveParallelism": null,
      "originalSafeEffectiveParallelism": null,
      "proposedSafeEffectiveParallelism": null,
      "criticalPathDelta": null,
      "serializedTailDelta": null,
      "suggestions": [],
      "approvalState": "pending"
    },
    "editableFields": [
      "workspaces[].dependencies",
      "workspaces[].parallelGroup",
      "workspaces[].dependencyReason",
      "workspaces[].parallelism.canRunWith",
      "workspaces[].parallelism.cannotRunWith",
      "workspaces[].parallelism.conflictScope",
      "workspaces[].integration.queuePriority",
      "workspaces[].integration.queueOptimizationNotes"
    ],
    "doctorWarnings": [
      "effective_parallelism_below_requested",
      "safe_parallelism_below_dag_parallelism",
      "fully_serialized_graph",
      "long_serialized_tail",
      "file_overlap_blocks_parallelism",
      "validation_lock_limits_parallelism",
      "integration_queue_serializes_merges",
      "scale_mode_prerequisites_missing",
      "worktree_isolation_required_for_scale",
      "queue_optimization_disabled_with_active_priority",
      "queue_priority_mismatch_with_configured_levels",
      "critical_path_workspace_has_low_priority",
      "optimizer_patch_without_approval"
    ],
    "persistedArtifacts": [
      "dependency_graph",
      "batch_preview",
      "safe_batch_preview",
      "critical_path",
      "scale_mode_readiness",
      "approved_dependency_patch",
      "approved_graph_hash",
      "queue_priority_snapshot",
      "queue_optimization_strategy",
      "queue_reorder_decision_log",
      "plan_intake_analysis",
      "optimizer_proposal",
      "graph_diff",
      "worktree_state",
      "lease_heartbeat_snapshots",
      "lease_reconciliation_log",
      "merge_priority_score_log",
      "empirical_write_set",
      "write_set_drift_report",
      "validation_lane_saturation_log"
    ]
  },
  "workspaces": [
    {
      "id": "P8.A",
      "title": "Walk-Forward Evaluation",
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
          "src/v7/alpha/evaluation/**",
          "tests/v7/alpha/unit/evaluation/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/evaluation/**",
        "tests/v7/alpha/unit/evaluation/**"
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
        "Economic quality metrics computed per fold.",
        "No-trade quality, calibration, regression reliability evaluated."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/evaluation/**",
          "tests/v7/alpha/unit/evaluation/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P8.B",
      "title": "Ablations",
      "dependencies": [
        "P8.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P8.A for foundation.",
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
          "src/v7/alpha/evaluation/**",
          "tests/v7/alpha/unit/evaluation/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/evaluation/**",
        "tests/v7/alpha/unit/evaluation/**"
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
        "Feature ablation, symbol stability, regime stability measured."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/evaluation/**",
          "tests/v7/alpha/unit/evaluation/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P8.C",
      "title": "Paper/Shadow Harness",
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
          "src/v7/alpha/runtime/**",
          "tests/v7/alpha/integration/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/runtime/**",
        "tests/v7/alpha/integration/**"
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
        "Paper mode inference without execution exists.",
        "Shadow mode runs alongside live without affecting decisions."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/runtime/**",
          "tests/v7/alpha/integration/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P8.D",
      "title": "Promotion Report",
      "dependencies": [
        "P8.A",
        "P8.B",
        "P8.C"
      ],
      "parallelGroup": "batch_3",
      "dependencyReason": "Depends on P8.A, P8.B, P8.C for foundation.",
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
          "docs/v7/alpha/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "normal",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "docs/v7/alpha/**"
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
        "Report summarizes all evaluation evidence for promotion review.",
        "Rollback recommendation included."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "low",
      "capabilityManifest": {
        "canEdit": [
          "docs/v7/alpha/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
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
  "phase": "P8",
  "title": "Evaluation, Backtest, Paper & Shadow Validation",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "selectedRepairMode": null,
  "targetPromotionMode": "stable_6",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "schedulerRuntimeUse": "enabled",
  "primaryGoal": "Economic evaluation, no-trade quality, calibration quality, and shadow/paper readiness.",
  "projectName": "v7_alphaforge_xgb",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresPatchIsolation": false,
  "requiresIntegrationQueue": true,
  "requiresPatchApplyQueue": false,
  "repositoryMutationAuthority": "worktree_integration",
  "queueOptimizationEnabled": true,
  "queueOptimizationStrategy": "priority_then_fifo",
  "continuousScheduling": true,
  "continuousSlotCount": 3,
  "safeEffectiveParallelismTarget": 2,
  "notInScope": [
    "External broker execution authority",
    "V7 runtime core modifications",
    "Non-XGBoost model families"
  ],
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
    "optimizer_patch_without_approval"
  ],
  "completionGate": "P8 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "P9"
}
```

---

## Review Hardening Requirements

* [ ] Walk-forward economic evaluation
* [ ] No-trade quality visibility

---

<!-- SOURCE: phase_plans/P9__deployment_monitoring_drift_promotion_and_rollback.md -->

# P9 — Deployment, Monitoring, Drift, Promotion & Rollback

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P9`  
**One-line goal:** Deployment safety, drift monitoring, kill switch, rollback bundles, and live eligibility gates.  
**Why now:** The alpha system must be operated safely with visible drift, explicit rollback, and per-mode promotion authority.  
**Blast radius:** src/v7/alpha/**, tests/v7/alpha/**, configs/v7/alpha/**, docs/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Execution class:** `implementation`  
**Execution automation:** `enabled`  
**Scale mode:** `stable_3`  
**Safe parallelism target:** `2`  
**Done when:** All workspaces pass acceptance criteria and phase JSON validates through Pi doctor.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P9` |
| Title | `Deployment, Monitoring, Drift, Promotion & Rollback` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Deployment safety, drift monitoring, kill switch, rollback bundles, and live eligibility gates.` |
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

The alpha system must be operated safely with visible drift, explicit rollback, and per-mode promotion authority.

Live deployment requires monitoring surfaces, drift detection, promotion registry with version bumps, and a rollback playbook that can revert model+calibration+policy bundles per mode.

This phase uses `stable_3` scale-aware execution. The executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

---

## 3. What Carried Over — Must Stay Stable

* [ ] Runtime owns orchestration, execution, persistence, lifecycle, and hard safety.
* [ ] Model owns alpha evidence only.
* [ ] Simulation truth defines labels and evaluation.
* [ ] No hidden deterministic veto or hidden fallback.
* [ ] NO_TRADE remains first-class.
* [ ] Features are canonical-state only.
* [ ] Labels are mode-specific.
* [ ] Datasets are mode-specific and temporally split.
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

Live deployment requires monitoring surfaces, drift detection, promotion registry with version bumps, and a rollback playbook that can revert model+calibration+policy bundles per mode.

---

## 5. Current Failure State / Known Blockers

* `monitoring_surfaces` = not implemented.
* `promotion_registry` = not implemented.
* `rollback_playbook` = not implemented.
* `live_eligibility_gate` = not implemented.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Worktree isolation violation | low | critical | Path scope checks; stop execution on escape |
| Integration queue merges unvalidated diff | medium | high | Require workspace validation and integration validation |
| Merge conflict blocks plan | medium | medium | Generate conflict handoff artifact and stop queue safely |
| Safe parallelism is lower than requested | medium | medium | Doctor warning; show bottleneck; use safe batch preview |
| Validation lock limits throughput | medium | medium | Scheduler reduces concurrency while heavy validation runs |
| High-risk workspace failure | medium | high | Rollback path defined; manual review gating |

---

## 7. Workstreams

### P9.A — Monitoring Surfaces

**Goal:** Prediction drift, feature drift, anomaly score drift monitored.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Prediction drift, feature drift, anomaly score drift monitored.
* Regime-forced vs model-preferred no-trade rate exposed.
* Dashboard visible.

**File Scope:**
```text
src/v7/alpha/monitoring/**
tests/v7/alpha/unit/monitoring/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P9.B — Promotion Registry

**Goal:** Per-mode versioned bundle promotion works.

**Dependencies:** P9.A
**Parallel Group:** batch_2
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Per-mode versioned bundle promotion works.
* Symbol universe changes require encoding-family version bump.

**File Scope:**
```text
src/v7/alpha/deployment/**
configs/v7/alpha/**
```

**Isolation & Parallelism Notes:**
* Depends on P9.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P9.C — Rollback Playbook

**Goal:** Rollback can revert model+calibration+policy per mode.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Rollback can revert model+calibration+policy per mode.
* Kill switch stops new alpha inference.

**File Scope:**
```text
docs/v7/alpha/**
src/v7/alpha/deployment/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.

### P9.D — Live Eligibility Gate

**Goal:** Paper/shadow evidence required before live.

**Dependencies:** P9.A
**Parallel Group:** batch_2
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:
* Paper/shadow evidence required before live.
* Interval mismatch and anomaly leakage checks pass.

**File Scope:**
```text
src/v7/alpha/deployment/**
tests/v7/alpha/regression/**
```

**Isolation & Parallelism Notes:**
* Depends on P9.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
* Same-file parallel edits should not run concurrently unless Pi optimizer explicitly approves a split.


---

## 8. Combined Implementation Order

```text
  Batch batch_1: P9.A + P9.C
  Batch batch_2: P9.B + P9.D
```

The dependency graph dictates that foundation workspaces run first, followed by parallel batches where dependencies permit. The DAG batch preview and safe batch preview may differ because of file overlap, validation lock pressure, or integration queue serialization.

---

## 9. Definition of Done

`P9` is complete when ALL are true:

* [ ] Prediction drift, feature drift, anomaly score drift monitored.
* [ ] Per-mode versioned bundle promotion works.
* [ ] Rollback can revert model+calibration+policy per mode.
* [ ] Paper/shadow evidence required before live.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation is valid for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] No forbidden commands or files were used.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Validation planner misses a required failure.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Disable worktree mode only if safe fallback is required.
4. Pause or disable integration queue processing.
5. Preserve `.pi/worktrees/{planExecId}/` for debugging.
6. Fall back to shared-working-tree execution if explicitly allowed.
7. Keep dashboard telemetry read-only if safe.
8. Revert phase commits independently if needed.

---

## 11. What Next Phase Inherits

`NONE` inherits:

* `P9` execution contract with worktree mode awareness.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Workspace-level parallelism/isolation/integration/validation metadata.
* Review hardening invariants: Drift monitoring, Promotion registry versioning, Rollback safety

---

# Part 2 — Agent Brief

## Mission

Implement `P9` — Deployment safety, drift monitoring, kill switch, rollback bundles, and live eligibility gates.

The agent must optimize for safe parallelism, not maximum concurrency. Higher worker counts are allowed only when scale-mode readiness passes and the executor can preserve correctness through worktree isolation, integration queue, validation locks, and completion gates.



---

## Hard Requirements

1. All P9 workstreams must pass acceptance criteria.
2. Worktree isolation must be enabled for parallel workspaces.
3. Integration queue must serialize merges.
4. Global validation lock must be active for heavy validation.
5. Watch-mode validation is forbidden.
6. `git push` is forbidden.
7. Raw destructive cleanup is forbidden.
8. Do not exceed selected scale-mode worker cap (3).
9. Do not merge workspace output without passed workspace validation.
10. Do not mark the plan complete if integration validation fails.
11. Do not treat merge conflict as ordinary worker failure.
12. Do not start the next plan while integration queue state is dirty.

---

## Execution Policies

```yaml
repair_modes:
  manual_0: autonomous_execution_allowed: false, agent_may_mutate_repo: false
  stable_3: autonomous_execution_allowed: true,  agent_may_mutate_repo: true

execution_automation:
  autonomous_execution_enabled: true
  agent_may_mutate_repo: true
  agent_may_run_commands: true
  manual_patch_application_required: false
  human_approval_required_for_every_patch: false

bounded_liveness:
  no_indefinite_waits: true
  llm_provider_timeout_required: true
  llm_stream_idle_watchdog_required: true
  validation_timeout_required: true
  process_tree_kill_required: true
  git_lock_bypass_forbidden: true
  state_write_serialization_required: true

scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
  worktree_required: true
  integration_queue_required: true

validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true

queue_optimization:
  enabled_by_default: true
  default_strategy: priority_then_fifo
  priority_levels: [critical, high, normal, low]
```

---

## Safety Stops

* Dependency cycles
* Invalid dependency patches
* Worktree path escaping `.pi/worktrees`
* Integration merge without passed workspace validation
* Validation failure
* Merge conflict without handoff artifact
* Unsafe scale mode
* Queue starting next plan while integration queue is dirty
* Forbidden file access
* Secrets access
* `git push`
* Watch-mode validation
* `autonomous_execution_requested_during_repair_mode`
* `agent_repo_mutation_requested_during_manual_repair`
* `scheduler_enabled_before_executor_isolation_gate`
* `llm_call_without_provider_timeout`
* `validation_command_without_timeout`
* `git_lock_bypass_detected`
* `state_store_write_without_serialization`
* `workspace_patch_without_human_approval`
* `promotion_gate_failed_or_missing`


# Part 2.5 — v4 ExecutionKernel Doctrine

## 2.5.1 Single Authority Model

v4 replaces the previous executor-owned or multi-component execution state model with an ExecutionKernel model.

```text
Before v4:
  Scheduler, executor, validation runner, retry router, cleanup, lease monitor,
  diagnostics, and brain workers could each influence or write partial execution truth.

After v4:
  All actors emit events.
  WorkspaceAttemptController mutates attempt state.
  PlanSupervisor mutates plan state.
  PostgreSQL stores authoritative runtime truth.
```

## 2.5.2 ExecutionKernel Components

| Component | Responsibility | May mutate execution state? |
|---|---|---:|
| `ExecutionAdmissionGate` | Authorize or reject execution requests before runtime starts | No |
| `ExecutionProfileDeriver` | Convert intent to required mechanisms | No |
| `PlanSupervisor` | Own plan FSM, slot tokens, completion predicate, final validation | Yes, plan state only |
| `WorkspaceAttemptController` | Own attempt FSM, retries, terminalization, handoff creation | Yes, attempt state only |
| `StateStoreWriter` | Commit transitions with authority token | Yes, through token only |
| `AttemptEventJournal` | Append versioned event records | No state mutation by itself |
| `DeadlineWatchdog` | Detect expired attempts and emit events | No |
| `ExecutorActor` | Run LLM/tools/bash for an attempt | No |
| `ValidationActor` | Run validation with deadlines and process containment | No |
| `GitRunner` | Serialize Git repo mutations | No attempt state mutation |

## 2.5.3 Attempt FSM Doctrine

A v4 attempt is a bounded state machine. It cannot remain in a non-terminal state forever.

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
Failure paths: RUNNING+timeout -> TIMED_OUT, critical violation -> FAILED_FINAL
Terminal states: SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, TIMED_OUT, HANDOFF_REQUIRED
Retry is legal only after terminal state.
```

## 2.5.4 PostgreSQL Truth Doctrine

Runtime truth is PostgreSQL. JSON fallback is forbidden in production.

Allowed filesystem data: stdout/stderr logs, raw tool output, patch artifacts, handoff Markdown.
Forbidden as authoritative runtime truth: JSON state fallback, NDJSON-only journal, filesystem-only state.

## 2.5.5 Intent-Driven Plan Doctrine

v4 authors express what they want, not the low-level mechanism matrix.

Human-authored: `parallelism`, `safetyLevel`, `conflictRisk`, `deadlines`, `executionEnvironment`.
System-derived: worktree requirement, integration queue, validation lanes, drift policy, watchdog policy.


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
    "name": "v7_alphaforge_xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p9"
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
    "writeSetDriftPolicy": "reject_or_handoff",
    "explain": [
      "stable_3 worktree mode: 3 workers, worktree isolation, integration queue",
      "Worktree isolation required for safe parallel execution",
      "All production execution requires PostgreSQL authoritative runtime state"
    ]
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
  "attemptLifecycle": {
    "modeSpecificLifecycles": {
      "worktree": {
        "initialState": "queued",
        "nonTerminalStates": [
          "queued",
          "leasing_worktree",
          "running",
          "validating",
          "waiting_for_validation_lane",
          "integration_queued",
          "integrating"
        ],
        "terminalStates": [
          "succeeded",
          "failed_retryable",
          "failed_final",
          "aborted",
          "timed_out",
          "quarantined",
          "handoff_required"
        ]
      }
    },
    "retryableTerminalStates": [
      "failed_retryable",
      "timed_out",
      "quarantined"
    ],
    "retryForbiddenFromNonTerminal": true,
    "deadlineRequiredForNonTerminalStates": true,
    "handoffRequiredCreatesQueueItem": true
  },
  "planLifecycle": {
    "completionPredicateRequired": true,
    "cannotCompleteWithRequiredNonTerminalWorkspaces": true,
    "cannotCompleteWithUnresolvedRequiredHandoff": true,
    "finalValidationRequiredBeforeCompleted": true,
    "states": [
      "created",
      "preflight",
      "running",
      "blocked_with_reason",
      "awaiting_handoff",
      "final_validation",
      "completed",
      "completed_with_warnings",
      "failed_final",
      "stopping",
      "stopped"
    ]
  },
  "actorPermissions": {
    "workspaceAttemptController": {
      "mayMutateAttemptState": true,
      "mayCreateRetryAttempt": true
    },
    "planSupervisor": {
      "mayMutatePlanState": true,
      "mayReserveSchedulerSlots": true
    },
    "executorActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayProducePatchArtifact": true,
      "mayEmitEvents": true
    },
    "validationActor": {
      "mayMutateAttemptState": false,
      "mayMutateRepository": false,
      "mayEmitEvents": true
    },
    "gitRunner": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true,
      "note": "May perform low-level git operations only when invoked by authorized repository mutation authority."
    },
    "leaseMonitor": {
      "mayMutateAttemptState": false,
      "mayEmitEvents": true
    },
    "retryPolicy": {
      "mayMutateAttemptState": false,
      "mayCreateRetryAttempt": false,
      "maySuggestRetry": true
    },
    "brainWorkers": {
      "mayMutateExecutionState": false,
      "mayEmitDiagnosis": true,
      "mayProposeAction": true
    },
    "diagnostics": {
      "mayMutateExecutionState": false,
      "mayEmitEvidence": true
    }
  },
  "admissionGate": {
    "required": true,
    "allEntrypointsMustUseGate": true,
    "coveredEntrypoints": [
      "cli_plan_run",
      "dashboard_run",
      "api_plan_run",
      "retry_endpoint",
      "cleanup_rerun_endpoint",
      "brain_worker_trigger",
      "overnight_runner",
      "proposal_executor"
    ],
    "rejectWhen": [
      "postgres_unavailable_for_authoritative_runtime",
      "json_runtime_fallback_detected",
      "repair_mode_autonomous_execution_disabled",
      "promotion_gates_missing",
      "unsafe_parallelism_requested",
      "execution_kernel_disabled",
      "state_authority_not_single"
    ]
  },
  "resourceCoordination": {
    "nestedLocksForbidden": true,
    "holdLockAcrossAwaitForbidden": true,
    "stateLocks": {
      "scope": "attempt",
      "maxHoldMs": 1000
    },
    "planLock": {
      "scope": "plan",
      "maxHoldMs": 1000,
      "purpose": "slot_reservation_only"
    },
    "gitRunner": {
      "mode": "queue",
      "repoMutationTimeoutMs": 60000,
      "lockBypassForbidden": true
    },
    "validationLanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    },
    "worktreeLeases": {
      "attemptScoped": true,
      "heartbeatRequired": true,
      "quarantineOnStale": true
    },
    "stateStore": {
      "writesThroughControllerOnly": true,
      "transactionOrWriteQueueRequired": true
    }
  },
  "deadlineWatchdog": {
    "required": true,
    "intervalSeconds": 15,
    "emitsEventsOnly": true,
    "eventType": "deadline_exceeded",
    "supervised": true,
    "onWatchdogUnavailable": "block_new_execution_or_downgrade"
  },
  "handoffQueue": {
    "required": true,
    "createdByStates": [
      "handoff_required"
    ],
    "allowedActions": [
      "retry_requested",
      "close_failed",
      "manual_resolution",
      "followup_plan_requested"
    ],
    "controllerMediatedRetryRequired": true
  },
  "boundedLiveness": {
    "required": true,
    "noIndefiniteWaits": true,
    "llm": {
      "providerRequestTimeoutMs": 120000,
      "streamIdleTimeoutMs": 300000,
      "workspaceOverallTimeoutMs": 1800000,
      "maxConsecutiveProviderTimeouts": 2,
      "onCircuitOpen": "fail_workspace_not_plan"
    },
    "validation": {
      "defaultTimeoutMs": 600000,
      "heavyTimeoutMs": 1200000,
      "killProcessTreeOnTimeout": true,
      "watchModeForbidden": true,
      "stdinClosed": true,
      "ciEnvRequired": true,
      "maxOutputBytes": 52428800
    },
    "git": {
      "repoMutationLockTimeoutMs": 60000,
      "lockBypassForbidden": true,
      "onLockTimeout": "fail_fast_and_retry_or_handoff"
    },
    "scheduler": {
      "stallDetectionEnabled": true,
      "noProgressTimeoutMs": 300000,
      "onNoProgress": "emit_blocked_reason"
    },
    "stateStore": {
      "transactionOrWriteQueueRequired": true,
      "atomicSnapshotRequired": true,
      "journalLineAtomicityRequired": true
    }
  },
  "llmRuntime": {
    "boundedProviderCallsRequired": true,
    "providerRequestTimeoutMs": 120000,
    "streamIdleTimeoutMs": 300000,
    "workspaceOverallTimeoutMs": 1800000,
    "circuitBreaker": {
      "enabled": true,
      "openAfterConsecutiveTimeouts": 2,
      "cooldownMs": 300000
    },
    "fallbackPolicy": {
      "enabled": false,
      "reason": "Patches must remain deterministic."
    }
  },
  "validationRuntime": {
    "managedRunnerRequired": true,
    "processGroupRequired": true,
    "killTreeOnTimeout": true,
    "maxOutputBytes": 52428800,
    "forbiddenInteractiveCommands": [
      "vitest --watch",
      "jest --watch",
      "npm run dev",
      "vite --host"
    ],
    "lanes": {
      "heavy": {
        "maxConcurrent": 1
      },
      "targeted": {
        "maxConcurrent": 3
      }
    }
  },
  "validationPolicy": {
    "defaultMode": "deferred",
    "workspaceCompletionRequiresTargetCommand": false,
    "planCompletionRequiresFinalValidation": true,
    "heavyValidationDeferredByDefault": true,
    "allowWorkspaceImmediateValidation": true,
    "allowSmokeValidation": true,
    "watchModeForbidden": true,
    "finalValidationWorkspaceRequired": true,
    "finalRepairWorkspaceRecommended": true,
    "validationArtifactsRequired": true,
    "liveValidationVisibilityRequired": true
  },
  "planExecution": {
    "phase": "P9",
    "title": "Deployment, Monitoring, Drift, Promotion & Rollback",
    "mode": "implementation",
    "maxParallelWorkspaces": 3,
    "scheduling": {
      "continuous": true,
      "slotCount": 3,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": false,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "stable_3",
      "selectedMode": "stable_3",
      "modes": {
        "stable_3": {
          "executorType": "direct",
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false,
          "preserveExistingBehavior": true
        },
        "stable_6": {
          "executorType": "patch_transaction",
          "maxCodegenWorkers": 6,
          "patchIsolationRequired": true,
          "worktreeRequired": false,
          "patchCoordinatorRequired": true,
          "repositoryMutationAuthority": "patch_coordinator",
          "patchApplyLanes": 1,
          "singleRepositoryWriterRequired": true,
          "targetedValidationRequired": true,
          "finalIntegrationValidationRequired": true,
          "postgresRequired": true,
          "completionGateRequired": true
        },
        "experimental_worktree_6": {
          "executorType": "worktree",
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "explicitOptInRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true
    },
    "integrationQueue": {
      "enabled": true,
      "enabledForExecutorTypes": [
        "worktree"
      ],
      "processOneMergeAtATime": true,
      "stopOnMergeConflict": true,
      "requireWorkspaceValidationPass": true,
      "requireIntegrationValidationPass": true,
      "gitPushAllowed": false,
      "queuePriority": {
        "enabled": true,
        "defaultLevel": "normal",
        "levels": [
          "critical",
          "high",
          "normal",
          "low"
        ]
      },
      "queueOptimization": {
        "enabled": true,
        "strategy": "priority_then_fifo",
        "availableStrategies": [
          "priority_then_fifo",
          "critical_path_first",
          "weighted_shortest_job_first"
        ]
      }
    },
    "validation": {
      "globalValidationLockRequired": true,
      "targetedValidationEnabled": true,
      "finalIntegrationValidationRequired": true,
      "watchModeForbidden": true
    },
    "interactiveParallelismReview": {
      "enabled": true,
      "preflightRequired": true,
      "approvalRequiredBeforeRun": true,
      "allowDependencyEditing": true,
      "showEffectiveParallelism": true,
      "showSafeEffectiveParallelism": true,
      "showBatchPreview": true,
      "showSafeBatchPreview": true,
      "showCriticalPath": true,
      "showScaleModeReadiness": true,
      "warnWhenEffectiveParallelismBelowRequested": true,
      "warnWhenSafeParallelismBelowDagParallelism": true,
      "warnWhenScaleModePrerequisitesMissing": true,
      "persistApprovedGraph": true
    },
    "planIntake": {
      "enabled": true,
      "runOnUpload": true,
      "parserPriority": [
        "part3_json",
        "contractVersion_and_executionClass",
        "doctor",
        "execution_gate"
      ],
      "autoNormalize": true,
      "autoDoctor": true,
      "autoDagAnalysis": true,
      "autoOptimizationProposal": true,
      "autoQueuePriorityRecommendation": true,
      "autoWorkspaceSplitRecommendation": true,
      "autoDryRunForecast": true,
      "approvalRequiredBeforeApplyingOptimization": true,
      "approvalRequiredBeforeExecution": true
    },
    "optimizer": {
      "enabled": true,
      "mode": "advisory_until_approved",
      "objectives": [
        "maximize_safe_effective_parallelism",
        "minimize_critical_path",
        "minimize_same_file_conflicts",
        "minimize_validation_lock_contention",
        "prioritize_critical_path_queue_merges"
      ],
      "allowedPatches": [
        "dependencies",
        "parallelGroup",
        "queuePriority",
        "canRunWith",
        "cannotRunWith",
        "conflictScope",
        "workspaceSplitSuggestion",
        "workspaceMergeSuggestion"
      ],
      "forbiddenAutoPatches": [
        "allowedFiles",
        "forbiddenFiles",
        "capabilityManifest",
        "safety.hardStops",
        "forbiddenCommands"
      ]
    }
  },
  "controls": {
    "allowPause": true,
    "allowStop": true,
    "allowCancel": true,
    "resumePolicy": "paused_or_stopped_only"
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
      "git clean -fd",
      "vitest --watch",
      "jest --watch",
      "npm run dev"
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
  "parallelismReview": {
    "requestedMaxParallelWorkspaces": 3,
    "selectedScaleMode": "stable_3",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for parallel execution."
        },
        {
          "key": "integration_queue",
          "required": true,
          "met": true,
          "message": "Required for queued execution."
        },
        {
          "key": "validation_lock",
          "required": true,
          "met": true,
          "message": "Required for heavy validation."
        },
        {
          "key": "completion_gate",
          "required": true,
          "met": true,
          "message": "Required for completion hardening."
        }
      ]
    },
    "expectedDagEffectiveParallelismMin": 2,
    "expectedSafeEffectiveParallelismMin": 2,
    "dagEffectiveParallelism": null,
    "safeEffectiveParallelism": null,
    "preflightStatus": "required",
    "approvalState": "pending",
    "batchingStrategy": "dag_topological_batches_display_only",
    "safeBatchingStrategy": "dag_batches_with_p6_safety_constraints_display_only",
    "batchPreview": {
      "batches": [],
      "overallEffectiveParallelism": null,
      "criticalPath": [],
      "criticalPathLength": 0,
      "serializedTailLength": 0
    },
    "safeBatchPreview": {
      "batches": [],
      "overallSafeEffectiveParallelism": null,
      "bottlenecks": [],
      "blockedParallelismReasons": []
    },
    "optimizationReview": {
      "originalGraphHash": null,
      "proposedGraphHash": null,
      "approvedGraphHash": null,
      "originalDagEffectiveParallelism": null,
      "proposedDagEffectiveParallelism": null,
      "originalSafeEffectiveParallelism": null,
      "proposedSafeEffectiveParallelism": null,
      "criticalPathDelta": null,
      "serializedTailDelta": null,
      "suggestions": [],
      "approvalState": "pending"
    },
    "editableFields": [
      "workspaces[].dependencies",
      "workspaces[].parallelGroup",
      "workspaces[].dependencyReason",
      "workspaces[].parallelism.canRunWith",
      "workspaces[].parallelism.cannotRunWith",
      "workspaces[].parallelism.conflictScope",
      "workspaces[].integration.queuePriority",
      "workspaces[].integration.queueOptimizationNotes"
    ],
    "doctorWarnings": [
      "effective_parallelism_below_requested",
      "safe_parallelism_below_dag_parallelism",
      "fully_serialized_graph",
      "long_serialized_tail",
      "file_overlap_blocks_parallelism",
      "validation_lock_limits_parallelism",
      "integration_queue_serializes_merges",
      "scale_mode_prerequisites_missing",
      "worktree_isolation_required_for_scale",
      "queue_optimization_disabled_with_active_priority",
      "queue_priority_mismatch_with_configured_levels",
      "critical_path_workspace_has_low_priority",
      "optimizer_patch_without_approval"
    ],
    "persistedArtifacts": [
      "dependency_graph",
      "batch_preview",
      "safe_batch_preview",
      "critical_path",
      "scale_mode_readiness",
      "approved_dependency_patch",
      "approved_graph_hash",
      "queue_priority_snapshot",
      "queue_optimization_strategy",
      "queue_reorder_decision_log",
      "plan_intake_analysis",
      "optimizer_proposal",
      "graph_diff",
      "worktree_state",
      "lease_heartbeat_snapshots",
      "lease_reconciliation_log",
      "merge_priority_score_log",
      "empirical_write_set",
      "write_set_drift_report",
      "validation_lane_saturation_log"
    ]
  },
  "workspaces": [
    {
      "id": "P9.A",
      "title": "Monitoring Surfaces",
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
          "src/v7/alpha/monitoring/**",
          "tests/v7/alpha/unit/monitoring/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/monitoring/**",
        "tests/v7/alpha/unit/monitoring/**"
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
        "Prediction drift, feature drift, anomaly score drift monitored.",
        "Regime-forced vs model-preferred no-trade rate exposed.",
        "Dashboard visible."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/monitoring/**",
          "tests/v7/alpha/unit/monitoring/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P9.B",
      "title": "Promotion Registry",
      "dependencies": [
        "P9.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P9.A for foundation.",
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
          "src/v7/alpha/deployment/**",
          "configs/v7/alpha/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/deployment/**",
        "configs/v7/alpha/**"
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
        "Per-mode versioned bundle promotion works.",
        "Symbol universe changes require encoding-family version bump."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/deployment/**",
          "configs/v7/alpha/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P9.C",
      "title": "Rollback Playbook",
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
          "docs/v7/alpha/**",
          "src/v7/alpha/deployment/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "docs/v7/alpha/**",
        "src/v7/alpha/deployment/**"
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
        "Rollback can revert model+calibration+policy per mode.",
        "Kill switch stops new alpha inference."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "docs/v7/alpha/**",
          "src/v7/alpha/deployment/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
      }
    },
    {
      "id": "P9.D",
      "title": "Live Eligibility Gate",
      "dependencies": [
        "P9.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on P9.A for foundation.",
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
          "src/v7/alpha/deployment/**",
          "tests/v7/alpha/regression/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
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
        "src/v7/alpha/deployment/**",
        "tests/v7/alpha/regression/**"
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
        "Paper/shadow evidence required before live.",
        "Interval mismatch and anomaly leakage checks pass."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/deployment/**",
          "tests/v7/alpha/regression/**"
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
          "git clean -fd",
          "vitest --watch",
          "jest --watch",
          "npm run dev"
        ]
      },
      "telemetry": {
        "expectedEvents": [
          "workspace_started",
          "workspace_completed",
          "workspace_validated"
        ],
        "logLevel": "info"
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
  "phase": "P9",
  "title": "Deployment, Monitoring, Drift, Promotion & Rollback",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "selectedRepairMode": null,
  "targetPromotionMode": "stable_6",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "schedulerRuntimeUse": "enabled",
  "primaryGoal": "Deployment safety, drift monitoring, kill switch, rollback bundles, and live eligibility gates.",
  "projectName": "v7_alphaforge_xgb",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresPatchIsolation": false,
  "requiresIntegrationQueue": true,
  "requiresPatchApplyQueue": false,
  "repositoryMutationAuthority": "worktree_integration",
  "queueOptimizationEnabled": true,
  "queueOptimizationStrategy": "priority_then_fifo",
  "continuousScheduling": true,
  "continuousSlotCount": 3,
  "safeEffectiveParallelismTarget": 2,
  "notInScope": [
    "External broker execution authority",
    "V7 runtime core modifications",
    "Non-XGBoost model families"
  ],
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
    "optimizer_patch_without_approval"
  ],
  "completionGate": "P9 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "NONE"
}
```

---

## Review Hardening Requirements

* [ ] Drift monitoring
* [ ] Promotion registry versioning
* [ ] Rollback safety

---

