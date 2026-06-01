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
