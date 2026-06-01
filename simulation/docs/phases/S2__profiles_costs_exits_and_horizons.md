# S2 — Profiles, Costs, Exits & Horizons

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `S2`
**One-line goal:** Define and implement versioned mode profiles, cost models, stop/target/horizon/time-exit semantics.
**Why now:** The core engine needs mode-specific parameters, cost-aware R computation, and deterministic exit logic before it can produce economically honest outputs.
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
| Phase | `S2` |
| Title | `Profiles, Costs, Exits & Horizons` |
| Status | `Planned` |
| Last updated | `2026-06-01` |
| Delivery status | `Not started` |
| Target environment | `Local / Staging` |
| Primary focus | `Define and implement versioned mode profiles, cost models, stop/target/horizon/time-exit semantics.` |
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

The core engine needs mode-specific parameters, cost-aware R computation, and deterministic exit logic before it can produce economically honest outputs.

Mode profiles (SWING/SCALP/AGGRESSIVE_SCALP) parameterize the engine. Cost model applies fees and slippage. Exit logic determines stop/target/time-exit. Unresolved/invalidated semantics handle incomplete data.

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

Mode profiles (SWING/SCALP/AGGRESSIVE_SCALP) parameterize the engine. Cost model applies fees and slippage. Exit logic determines stop/target/time-exit. Unresolved/invalidated semantics handle incomplete data.

---

## 5. Current Failure State / Known Blockers

* Mode profile resolver = not implemented.
* Cost/fee/slippage model = not versioned.
* Stop/target/time-exit resolver = not deterministic.
* Unresolved/invalidated behavior = not distinct.
* Version bump rules = not enforced.

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

### S2.A — Mode Profile Resolver

**Goal:** SWING profile resolves with: 4h primary, 30 max bars, 2.0-2.5 stop, 2.0-3.0 target.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** medium
**Queue Priority:** critical
**Can run with:** None

**Requirements:**
* SWING profile resolves with: 4h primary, 30 max bars, 2.0-2.5 stop, 2.0-3.0 target.
* SCALP profile resolves with: 1h primary, 12 max bars, 1.5-2.0 stop/target.
* AGGRESSIVE_SCALP profile resolves with: 15m primary, 5 max bars, 1.0-1.5 stop/target.
* Invalid mode produces explicit error.

**File Scope:**
```text
simulation/profiles/**.py
simulation/resolvers/profile_resolver.py
simulation/tests/unit/profiles/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
### S2.B — Cost/Fee/Slippage Model

**Goal:** Fee model: maker_fee_bps=2.0, taker_fee_bps=4.0.

**Dependencies:** None (foundation)
**Parallel Group:** batch_1
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:**
* Fee model: maker_fee_bps=2.0, taker_fee_bps=4.0.
* Slippage model: slippage_bps=1.0, volatility_adjust=true.
* fee_cost_r and slippage_cost_r computed correctly.
* cost_model_version included in output lineage.

**File Scope:**
```text
simulation/resolvers/cost_resolver.py
simulation/tests/unit/costs/**
```

**Isolation & Parallelism Notes:**
* Foundation workspace for this phase.
* Expected batch: batch_1
* Worktree isolation required.
### S2.C — Stop/Target/Time-Exit Resolver

**Goal:** Stop level = entry_price +/- (atr * stop_multiplier).

**Dependencies:** S2.A
**Parallel Group:** batch_2
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:**
* Stop level = entry_price +/- (atr * stop_multiplier).
* Target level = entry_price +/- (atr * target_multiplier).
* Stop checked before target (conservative precedence).
* Same-candle ambiguity: stop-first, ambiguity recorded.
* Time exit after max_holding_bars.
* Horizon end when path exhausted.

**File Scope:**
```text
simulation/exits/exits.py
simulation/resolvers/stop_resolver.py
simulation/resolvers/time_exit_resolver.py
simulation/tests/unit/exits/**
```

**Isolation & Parallelism Notes:**
* Depends on S2.A for foundation.
* Expected batch: batch_2
* Worktree isolation required.
### S2.D — Unresolved/Invalidated Behavior

**Goal:** UNRESOLVED when future window incomplete and may complete.

**Dependencies:** S2.C
**Parallel Group:** batch_2
**Risk Level:** high
**Queue Priority:** critical
**Can run with:** None

**Requirements:**
* UNRESOLVED when future window incomplete and may complete.
* INVALIDATED after 2x horizon length without data.
* Immediate INVALIDATED for corrupted future data.
* Invalidity reasons: DATA_CORRUPTED, DATA_GAP, DATA_STALE, etc.
* Neither UNRESOLVED nor INVALIDATED used as training labels.

**File Scope:**
```text
simulation/engine/resolution.py
simulation/tests/unit/engine/**
```

**Isolation & Parallelism Notes:**
* Depends on S2.C for foundation.
* Expected batch: batch_2
* Worktree isolation required.
### S2.E — Version Bump Rules

**Goal:** simulation_family_version bumped on engine semantic changes.

**Dependencies:** S2.A, S2.B, S2.C
**Parallel Group:** batch_3
**Risk Level:** medium
**Queue Priority:** high
**Can run with:** None

**Requirements:**
* simulation_family_version bumped on engine semantic changes.
* simulation_profile_version bumped per-mode on parameter changes.
* cost_model_version bumped on fee/slippage logic changes.
* Old labels traceable to producing simulation family.

**File Scope:**
```text
simulation/lineage/lineage.py
simulation/tests/unit/lineage/**
```

**Isolation & Parallelism Notes:**
* Depends on S2.A, S2.B, S2.C for foundation.
* Expected batch: batch_3
* Worktree isolation required.

---

## 8. Combined Implementation Order

```text
  Batch batch_1: S2.A + S2.B
  Batch batch_2: S2.C + S2.D
  Batch batch_3: S2.E
```

---

## 9. Definition of Done

`S2` is complete when ALL are true:

* [ ] SWING profile resolves with: 4h primary, 30 max bars, 2.0-2.5 stop, 2.0-3.0 target.
* [ ] Fee model: maker_fee_bps=2.0, taker_fee_bps=4.0.
* [ ] Stop level = entry_price +/- (atr * stop_multiplier).
* [ ] UNRESOLVED when future window incomplete and may complete.
* [ ] simulation_family_version bumped on engine semantic changes.
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

`S3` inherits: Execution contract with worktree mode, scale-mode validation rules, integration queue requirements, workspace metadata, and review hardening invariants.

---

# Part 2 — Agent Brief

## Mission

Implement `S2` — Define and implement versioned mode profiles, cost models, stop/target/horizon/time-exit semantics.

The agent must optimize for safe parallelism, not maximum concurrency.


**Authority context:** See [`/simulation/docs/ai_summary.md`](../ai_summary.md) for the complete system synthesis before implementing this phase.
## Hard Requirements

1. All S2 workstreams must pass acceptance criteria.
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
      "s2"
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
      "id": "S2.A",
      "title": "Mode Profile Resolver",
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
          "simulation/profiles/**.py",
          "simulation/resolvers/profile_resolver.py",
          "simulation/tests/unit/profiles/**"
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
        "simulation/profiles/**.py",
        "simulation/resolvers/profile_resolver.py",
        "simulation/tests/unit/profiles/**"
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
        "SWING profile resolves with: 4h primary, 30 max bars, 2.0-2.5 stop, 2.0-3.0 target.",
        "SCALP profile resolves with: 1h primary, 12 max bars, 1.5-2.0 stop/target.",
        "AGGRESSIVE_SCALP profile resolves with: 15m primary, 5 max bars, 1.0-1.5 stop/target.",
        "Invalid mode produces explicit error."
      ],
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "simulation/profiles/**.py",
          "simulation/resolvers/profile_resolver.py",
          "simulation/tests/unit/profiles/**"
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
      "id": "S2.B",
      "title": "Cost/Fee/Slippage Model",
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
          "simulation/resolvers/cost_resolver.py",
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
        "simulation/resolvers/cost_resolver.py",
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
        "Fee model: maker_fee_bps=2.0, taker_fee_bps=4.0.",
        "Slippage model: slippage_bps=1.0, volatility_adjust=true.",
        "fee_cost_r and slippage_cost_r computed correctly.",
        "cost_model_version included in output lineage."
      ],
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "simulation/resolvers/cost_resolver.py",
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
      "id": "S2.C",
      "title": "Stop/Target/Time-Exit Resolver",
      "dependencies": [
        "S2.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on S2.A for foundation.",
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
          "simulation/exits/exits.py",
          "simulation/resolvers/stop_resolver.py",
          "simulation/resolvers/time_exit_resolver.py",
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
        "simulation/exits/exits.py",
        "simulation/resolvers/stop_resolver.py",
        "simulation/resolvers/time_exit_resolver.py",
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
        "Stop level = entry_price +/- (atr * stop_multiplier).",
        "Target level = entry_price +/- (atr * target_multiplier).",
        "Stop checked before target (conservative precedence).",
        "Same-candle ambiguity: stop-first, ambiguity recorded.",
        "Time exit after max_holding_bars.",
        "Horizon end when path exhausted."
      ],
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "simulation/exits/exits.py",
          "simulation/resolvers/stop_resolver.py",
          "simulation/resolvers/time_exit_resolver.py",
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
      "id": "S2.D",
      "title": "Unresolved/Invalidated Behavior",
      "dependencies": [
        "S2.C"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on S2.C for foundation.",
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
          "simulation/engine/resolution.py",
          "simulation/tests/unit/engine/**"
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
        "simulation/engine/resolution.py",
        "simulation/tests/unit/engine/**"
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
        "UNRESOLVED when future window incomplete and may complete.",
        "INVALIDATED after 2x horizon length without data.",
        "Immediate INVALIDATED for corrupted future data.",
        "Invalidity reasons: DATA_CORRUPTED, DATA_GAP, DATA_STALE, etc.",
        "Neither UNRESOLVED nor INVALIDATED used as training labels."
      ],
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "simulation/engine/resolution.py",
          "simulation/tests/unit/engine/**"
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
      "id": "S2.E",
      "title": "Version Bump Rules",
      "dependencies": [
        "S2.A",
        "S2.B",
        "S2.C"
      ],
      "parallelGroup": "batch_3",
      "dependencyReason": "Depends on S2.A, S2.B, S2.C for foundation.",
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
          "simulation/lineage/lineage.py",
          "simulation/tests/unit/lineage/**"
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
        "queuePriority": "high"
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
        "simulation/lineage/lineage.py",
        "simulation/tests/unit/lineage/**"
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
        "simulation_family_version bumped on engine semantic changes.",
        "simulation_profile_version bumped per-mode on parameter changes.",
        "cost_model_version bumped on fee/slippage logic changes.",
        "Old labels traceable to producing simulation family."
      ],
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "simulation/lineage/lineage.py",
          "simulation/tests/unit/lineage/**"
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
  "phase": "S2",
  "title": "Profiles, Costs, Exits & Horizons",
  "executionClass": "implementation",
  "executionAutomation": "enabled",
  "autonomousExecutionAllowed": true,
  "agentMayMutateRepo": true,
  "schedulerRuntimeUse": "enabled",
  "primaryGoal": "Define and implement versioned mode profiles, cost models, stop/target/horizon/time-exit semantics.",
  "projectName": "v7_engine_simulation",
  "stateBackend": "postgres",
  "selectedScaleMode": "stable_3",
  "maxParallelWorkspaces": 3,
  "requiresWorktreeIsolation": true,
  "requiresIntegrationQueue": true,
  "safeEffectiveParallelismTarget": 2,
  "completionGate": "S2 complete only when all workspaces pass acceptance criteria and final validation passes.",
  "nextPhase": "S3"
}
```
