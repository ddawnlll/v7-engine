# V7 AlphaForge XGB — Combined Phase Plans

Generated from individual phase plan files.

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
**Scale mode:** `experimental_6`  
**Safe parallelism target:** `4`  
**Done when:** All workstreams pass acceptance criteria and phase JSON validates through Pi doctor.

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
| Primary focus | `Repository skeleton, central config, typed foundations, test scaffolding` |
| Product-code changes | `Allowed` |
| Selected scale mode | `experimental_6` |
| Requested max workers | `6` |
| Expected DAG effective parallelism | `4` |
| Expected safe effective parallelism | `4` |
| Worktree isolation | `Required` |
| Integration queue | `Required` |

### 1.1 RACI

| Workstream | R | A | C | I |
|---|---|---|---|---|
| All phase workstreams | Implementation Agent | Plan Owner | V7 Runtime/ML Reviewer | Maintainers |

---

## 2. Purpose

The alpha system needs stable folders, configs, schemas, and safety scaffolding before implementation begins.

This phase is part of the `V7 AlphaForge XGB` implementation. It must preserve V7's market-first, simulation-native, mode-scoped architecture. The phase must not introduce execution authority into the model layer, must not create a second hidden simulator, and must not use raw future returns as the production alpha truth when V7 simulation-derived R labels are required.

When scale mode is `experimental_6`, the executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

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
* [ ] Worktree isolation remains available when requested by scale mode.
* [ ] Integration queue remains enabled when required by scale mode.
* [ ] Global validation lock remains active for heavy validation.
* [ ] Completion gate hardening remains active.
* [ ] Merge conflicts produce handoff artifacts and do not mark the plan complete.
* [ ] The next plan does not start while the integration queue is dirty.
* [ ] `git push` remains forbidden.
* [ ] Raw destructive cleanup remains forbidden.
* [ ] Watch-mode validation remains forbidden.
* [ ] The executor remains the source of truth for state transitions.

---

## 4. Background / What Was Wrong

The existing V7 design defines mode-specific simulation semantics, hybrid model outputs, and runtime-owned execution boundaries. The new alpha generation system must align with those constraints instead of acting as an independent trading model.

The main missing capability is a V7-native alpha evidence layer that can train on 20 symbols, respect SWING / SCALP / AGGRESSIVE_SCALP semantics, emit calibrated XGBoost classification and regression surfaces, and expose R-native alpha scores to the V7 decision engine.

---

## 5. Current Failure State / Known Blockers

* `v7_alphaforge_xgb` = not implemented.
* `mode_specific_alpha_datasets` = not implemented until P4.
* `xgboost_alpha_artifacts` = not implemented until P5.
* `calibrated_alpha_score_builder` = not implemented until P6.
* `v7_policy_bridge` = not implemented until P7.
* `worktree_isolation` = enabled when selected scale mode requires it.
* `integration_queue` = enabled.
* `scale_mode_readiness` = pending Pi doctor review.
* `safe_effective_parallelism` = expected, not yet computed.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Future leakage enters feature rows | med | critical | Contract forbidden fields, leakage tests, timestamp checks |
| Alpha labels diverge from V7 simulation truth | med | critical | Use runtime simulation adapter only; golden tests |
| Raw XGBoost scores used as calibrated confidence | med | high | confidence_kind required; calibration tests |
| Mode datasets accidentally mixed | med | high | mode field and dataset-family validation |
| Safe parallelism lower than requested | med | med | Doctor warning; use safe batch preview |
| Merge conflict blocks plan | med | med | Handoff artifact and stop queue safely |
| Worktree path escapes `.pi/worktrees` | low | critical | Path scope checks; stop execution on escape |
| Cleanup deletes wrong files | low | critical | Raw destructive cleanup forbidden |

---

## 7. Workstreams

### 7.A — Repository Skeleton

**Goal:** Create src/v7/alpha package tree and tests tree.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Create src/v7/alpha package tree and tests tree.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream A may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.B — Config Foundations

**Goal:** Add alpha defaults and mode-specific simulation config surfaces.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Add alpha defaults and mode-specific simulation config surfaces.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream B may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.C — Typed Foundations

**Goal:** Add domain errors, serialization helpers, and schema validation helpers.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Add domain errors, serialization helpers, and schema validation helpers.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream C may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.D — Smoke Tests

**Goal:** Add import, config-load, unknown-key, and JSON schema smoke tests.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Add import, config-load, unknown-key, and JSON schema smoke tests.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream D may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.

---

## 8. Combined Implementation Order

```text
Dependencies: None
Batch 1: P0.A
Batch 2: P0.B + P0.C + P0.D, subject to same-file conflict review
Next phase: P1
```

Pi's computed approved graph is authoritative. Authored batches are only advisory. Continuous scheduling may run ready workspaces without waiting for batch barriers when safety constraints pass.

---

## 9. Definition of Done

`P0` is complete when ALL are true:

* [ ] All phase workstreams satisfy acceptance criteria.
* [ ] Relevant tests pass.
* [ ] No forbidden commands or files were used.
* [ ] No hidden fallback, hidden simulator, or future leakage was introduced.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation status is correct for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Future leakage detected.
* Simulation truth mismatch detected.
* Contract or schema validation fails.
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Dashboard or doctor reports misleading scale readiness.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Pause integration queue processing.
4. Preserve `.pi/worktrees/{planExecId}/` for debugging.
5. Revert phase workspaces independently.
6. Restore previous compatible config/schema/artifact bundle.
7. Rerun targeted validation and final integration validation.

---

## 11. What Next Phase Inherits

`P1` inherits:

* Completed outputs from `P0`.
* Worktree-aware execution contract.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Safe effective parallelism review.
* Workspace-level parallelism/isolation/integration/validation metadata.

---

# Part 2 — Agent Brief

## Mission

Implement `P0 — Repo Alignment & Alpha Foundations` for `V7 AlphaForge XGB` while preserving V7 runtime ownership, simulation-native labels, mode-specific datasets, explicit contracts, and safe Pi autonomous execution behavior.

## Hard Requirements

1. Do not create a second simulator.
2. Do not allow future data in features.
3. Do not use raw model scores as calibrated confidence.
4. Do not mix SWING, SCALP, and AGGRESSIVE_SCALP datasets unless explicitly building a report, not a model dataset.
5. Do not exceed selected scale-mode worker cap.
6. Do not run more than 3 workers unless worktree isolation and integration queue readiness pass.
7. Do not merge workspace output without passed workspace validation.
8. Do not mark a plan complete if integration validation fails.
9. Do not treat merge conflict as ordinary worker failure.
10. Do not start the next plan while integration queue state is dirty.
11. Do not run watch-mode validation.
12. Do not run `git push`.
13. Do not run raw destructive cleanup commands.
14. Do not access secrets or forbidden files.
15. The executor remains the only component that mutates execution state.

## Execution Policies

```yaml
scale:
  selected_mode: experimental_6
  max_parallel_workspaces: 6
worktree:
  enabled: true
  root: .pi/worktrees
  state_persistence_path: .pi/worktree-state.json
  crash_recovery_enabled: true
integration_queue:
  enabled: true
  process_one_merge_at_a_time: true
  stop_on_merge_conflict: true
  git_push_allowed: false
queue_optimization:
  enabled: true
  strategy: critical_path_first
validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true
```

## Safety Stops

Hard stop for dependency cycles, unapproved parallelism review, worktree path escape, raw destructive cleanup, integration validation failure, merge conflict without handoff, unsafe scale mode, forbidden file access, secrets access, `git push`, watch-mode validation, optimizer patch without approval, scope mismatch, and future leakage detection.

---

# Part 3 — Machine-Readable Execution Contract

```json
{
  "contractVersion": "2.5.1",
  "executionBackend": "postgres",
  "project": {
    "name": "v7-alphaforge-xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p0"
    ]
  },
  "planExecution": {
    "phase": "P0",
    "title": "Repo Alignment & Alpha Foundations",
    "mode": "autonomous",
    "maxParallelWorkspaces": 6,
    "scheduling": {
      "continuous": true,
      "slotCount": 6,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": true,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "experimental_6",
      "selectedMode": "experimental_6",
      "modes": {
        "stable_3": {
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false
        },
        "experimental_6": {
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true
        },
        "scale_8": {
          "maxParallelWorkspaces": 8,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "dogfoodPassRequired": true,
          "explicitApprovalRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "prewarmCount": 6,
      "statePersistencePath": ".pi/worktree-state.json",
      "crashRecoveryEnabled": true,
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true,
      "diffPreservationPath": ".pi/executions/{planExecId}/worktrees/{wsId}.patch"
    },
    "integrationQueue": {
      "enabled": true,
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
        "strategy": "critical_path_first",
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
        "markdown_fallback"
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
      "scope_mismatch",
      "future_leakage_detected"
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
    "requestedMaxParallelWorkspaces": 6,
    "selectedScaleMode": "experimental_6",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for experimental_6 and scale_8."
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
    "expectedDagEffectiveParallelismMin": 4,
    "expectedSafeEffectiveParallelismMin": 4,
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
      "worktree_state"
    ]
  },
  "workspaces": [
    {
      "id": "P0.A",
      "title": "Repository Skeleton",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
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
        "watchModeForbidden": true
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
        "Create src/v7/alpha package tree and tests tree.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
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
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
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
        "watchModeForbidden": true
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
        "Add alpha defaults and mode-specific simulation config surfaces.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
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
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
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
        "watchModeForbidden": true
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
        "Add domain errors, serialization helpers, and schema validation helpers.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
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
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
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
        "watchModeForbidden": true
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
        "Add import, config-load, unknown-key, and JSON schema smoke tests.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
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
    }
  ]
}
```

---

# Part 4 — Machine-Readable Summary

```json
{
  "phase": "P0",
  "title": "Repo Alignment & Alpha Foundations",
  "model_name": "V7 AlphaForge XGB",
  "model_slug": "v7_alphaforge_xgb",
  "depends_on": [],
  "next_phase": "P1",
  "scale_mode": "experimental_6",
  "requested_max_workers": 6,
  "expected_safe_parallelism": 4,
  "primary_focus": "Repository skeleton, central config, typed foundations, test scaffolding",
  "done_when": "Phase acceptance criteria pass and Part 3 JSON validates."
}
```


## 12. Review Hardening Requirements

* [ ] Central config defines interval authority for SWING, SCALP, and AGGRESSIVE_SCALP.
* [ ] SCALP primary interval is `1h`; `15m` is SCALP refinement and AGGRESSIVE_SCALP primary only.
* [ ] Config includes anomaly fit scope, symbol encoding family, and regime visibility settings.

---


<!-- SOURCE: phase_plans/P0_5__shared_lib_foundation.md -->

# P0.5 — Shared Lib Foundation (Focused)

# Part 1 — Phase Plan

## 0. TL;DR

**Phase:** `P0.5`
**One-line goal:** Create a minimal `lib/` with only the primitives that are **nearly identical usage** between v7 and alphaforge: Binance data fetching, pure math indicators, basic cost formulas, and time utilities.
**Scope rule:** If a primitive is used differently by v7 vs alphaforge, it stays in its owning package. `lib/` is curated, not comprehensive.
**Blast radius:** `lib/`, `lib/docs/`, existing data utilities that should be migrated.
**Done when:** All acceptance criteria pass.

---

## 1. Header

| Field | Value |
|---|---|
| Phase | `P0.5` |
| Title | `Shared Lib Foundation (Focused)` |
| Status | `Planned` |
| Last updated | `2026-05-23` |
| Primary focus | `Minimal lib/ for truly shared primitives only` |
| Product-code changes | `Allowed` |

---

## 2. What Goes in lib/

| Module | Contents | Why Shared |
|---|---|---|
| `market_data/binance/` | Binance HTTP client, klines service, funding service, market data service | Raw data fetching is identical |
| `market_data/contracts.py` | KlineRecord, MarketDataResult, DataQualityReport | Standard schema shared by both systems |
| `market_data/quality.py` | Gap/duplicate detection | Same quality rules |
| `indicators/atr.py` | `compute_atr()` | Pure math, identical |
| `indicators/returns.py` | Log/simple returns | Pure math, identical |
| `indicators/volatility.py` | Rolling std, range-based vol | Pure math, identical |
| `indicators/rolling.py` | Generic rolling window | Utility, identical |
| `costs/fees.py` | Maker/taker fee estimation | Basic formulas, identical |
| `costs/slippage.py` | `get_slippage()` | Basic estimation, identical |
| `time/intervals.py` | Interval string ↔ minutes | Utility, identical |
| `time/folds.py` | `generate_folds()` | Temporal walk-forward, identical |

## 3. What Does NOT Go in lib/

| Thing | Reason |
|---|---|
| Regime enums/detectors | V7 uses for policy; alphaforge uses for features. Different semantics. |
| R-multiple | V7 = ATR+mode truth; research = fixed%. Not the same thing. |
| IO utilities | Each system writes output differently. |
| Generic serialization | Premature. Add when needed. |
| Cache abstractions | Each system caches differently. |
| Adapters | Owned by v7 and alphaforge respectively. |

## 4. Dependency

| Phase | Depends On |
|---|---|
| P0.5 | P0 |

Downstream phases that use lib primitives (P1's data contracts, P2's simulation, P3's features, P4's dataset) now depend on P0.5.

## 5. Acceptance Criteria

- `lib/` skeleton exists with only the modules listed above
- Binance client does NOT live in v7 or alphaforge — it's in `lib/market_data/binance/`
- Pure math functions (ATR, returns, vol) live in `lib/indicators/` not in any system package
- Fee/slippage estimation lives in `lib/costs/` not in simulation or labels
- Fold generation lives in `lib/time/` not in dataset assembly
- No regime, risk, IO, or adapter logic lives in lib/
- Import-boundary test passes: `lib/` must NOT import v7 or alphaforge
- Docs clearly state what's shared and what's not (this file + lib/README.md)

## 6. Hard Stops

- `direct_binance_call_outside_lib` — Binance API call from v7/ or alphaforge/
- `lib_import_boundary_violation` — lib/ imports v7 or alphaforge
- `shared_everything_mistake` — putting regime, risk, IO, or adapters in lib/

---


<!-- SOURCE: phase_plans/P1__contracts_and_alpha_data_contract.md -->

# P1 — Contracts & Alpha Data Contract

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P1`  
**One-line goal:** Feature, label, prediction, artifact, and V7 bridge contracts.  
**Why now:** The runtime, training, and Pi agents need a stable typed boundary before feature, label, and model code can safely integrate.  
**Blast radius:** src/v7/alpha/contracts/**, tests/v7/alpha/unit/contracts/**, schemas/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Scale mode:** `experimental_6`  
**Safe parallelism target:** `3`  
**Done when:** All workstreams pass acceptance criteria and phase JSON validates through Pi doctor.

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
| Primary focus | `Feature, label, prediction, artifact, and V7 bridge contracts` |
| Product-code changes | `Allowed` |
| Selected scale mode | `experimental_6` |
| Requested max workers | `6` |
| Expected DAG effective parallelism | `4` |
| Expected safe effective parallelism | `3` |
| Worktree isolation | `Required` |
| Integration queue | `Required` |

### 1.1 RACI

| Workstream | R | A | C | I |
|---|---|---|---|---|
| All phase workstreams | Implementation Agent | Plan Owner | V7 Runtime/ML Reviewer | Maintainers |

---

## 2. Purpose

The runtime, training, and Pi agents need a stable typed boundary before feature, label, and model code can safely integrate.

This phase is part of the `V7 AlphaForge XGB` implementation. It must preserve V7's market-first, simulation-native, mode-scoped architecture. The phase must not introduce execution authority into the model layer, must not create a second hidden simulator, and must not use raw future returns as the production alpha truth when V7 simulation-derived R labels are required.

When scale mode is `experimental_6`, the executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

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
* [ ] Worktree isolation remains available when requested by scale mode.
* [ ] Integration queue remains enabled when required by scale mode.
* [ ] Global validation lock remains active for heavy validation.
* [ ] Completion gate hardening remains active.
* [ ] Merge conflicts produce handoff artifacts and do not mark the plan complete.
* [ ] The next plan does not start while the integration queue is dirty.
* [ ] `git push` remains forbidden.
* [ ] Raw destructive cleanup remains forbidden.
* [ ] Watch-mode validation remains forbidden.
* [ ] The executor remains the source of truth for state transitions.

---

## 4. Background / What Was Wrong

The existing V7 design defines mode-specific simulation semantics, hybrid model outputs, and runtime-owned execution boundaries. The new alpha generation system must align with those constraints instead of acting as an independent trading model.

The main missing capability is a V7-native alpha evidence layer that can train on 20 symbols, respect SWING / SCALP / AGGRESSIVE_SCALP semantics, emit calibrated XGBoost classification and regression surfaces, and expose R-native alpha scores to the V7 decision engine.

---

## 5. Current Failure State / Known Blockers

* `v7_alphaforge_xgb` = not implemented.
* `mode_specific_alpha_datasets` = not implemented until P4.
* `xgboost_alpha_artifacts` = not implemented until P5.
* `calibrated_alpha_score_builder` = not implemented until P6.
* `v7_policy_bridge` = not implemented until P7.
* `worktree_isolation` = enabled when selected scale mode requires it.
* `integration_queue` = enabled.
* `scale_mode_readiness` = pending Pi doctor review.
* `safe_effective_parallelism` = expected, not yet computed.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Future leakage enters feature rows | med | critical | Contract forbidden fields, leakage tests, timestamp checks |
| Alpha labels diverge from V7 simulation truth | med | critical | Use runtime simulation adapter only; golden tests |
| Raw XGBoost scores used as calibrated confidence | med | high | confidence_kind required; calibration tests |
| Mode datasets accidentally mixed | med | high | mode field and dataset-family validation |
| Safe parallelism lower than requested | med | med | Doctor warning; use safe batch preview |
| Merge conflict blocks plan | med | med | Handoff artifact and stop queue safely |
| Worktree path escapes `.pi/worktrees` | low | critical | Path scope checks; stop execution on escape |
| Cleanup deletes wrong files | low | critical | Raw destructive cleanup forbidden |

---

## 7. Workstreams

### 7.A — Feature Row Contract

**Goal:** Define alpha feature row schema and forbidden leakage fields.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Define alpha feature row schema and forbidden leakage fields.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream A may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.B — Label Row Contract

**Goal:** Define long_R/short_R and classification label schema.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Define long_R/short_R and classification label schema.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream B may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.C — Prediction Contract

**Goal:** Define calibrated probability, expected-R, and alpha score output.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Define calibrated probability, expected-R, and alpha score output.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream C may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.D — Contract Tests

**Goal:** Round-trip, enum, numeric-bound, and scope compatibility tests.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Round-trip, enum, numeric-bound, and scope compatibility tests.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream D may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.

---

## 8. Combined Implementation Order

```text
Dependencies: P0
Batch 1: P1.A
Batch 2: P1.B + P1.C + P1.D, subject to same-file conflict review
Next phase: P2
```

Pi's computed approved graph is authoritative. Authored batches are only advisory. Continuous scheduling may run ready workspaces without waiting for batch barriers when safety constraints pass.

---

## 9. Definition of Done

`P1` is complete when ALL are true:

* [ ] All phase workstreams satisfy acceptance criteria.
* [ ] Relevant tests pass.
* [ ] No forbidden commands or files were used.
* [ ] No hidden fallback, hidden simulator, or future leakage was introduced.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation status is correct for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Future leakage detected.
* Simulation truth mismatch detected.
* Contract or schema validation fails.
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Dashboard or doctor reports misleading scale readiness.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Pause integration queue processing.
4. Preserve `.pi/worktrees/{planExecId}/` for debugging.
5. Revert phase workspaces independently.
6. Restore previous compatible config/schema/artifact bundle.
7. Rerun targeted validation and final integration validation.

---

## 11. What Next Phase Inherits

`P2` inherits:

* Completed outputs from `P1`.
* Worktree-aware execution contract.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Safe effective parallelism review.
* Workspace-level parallelism/isolation/integration/validation metadata.

---

# Part 2 — Agent Brief

## Mission

Implement `P1 — Contracts & Alpha Data Contract` for `V7 AlphaForge XGB` while preserving V7 runtime ownership, simulation-native labels, mode-specific datasets, explicit contracts, and safe Pi autonomous execution behavior.

## Hard Requirements

1. Do not create a second simulator.
2. Do not allow future data in features.
3. Do not use raw model scores as calibrated confidence.
4. Do not mix SWING, SCALP, and AGGRESSIVE_SCALP datasets unless explicitly building a report, not a model dataset.
5. Do not exceed selected scale-mode worker cap.
6. Do not run more than 3 workers unless worktree isolation and integration queue readiness pass.
7. Do not merge workspace output without passed workspace validation.
8. Do not mark a plan complete if integration validation fails.
9. Do not treat merge conflict as ordinary worker failure.
10. Do not start the next plan while integration queue state is dirty.
11. Do not run watch-mode validation.
12. Do not run `git push`.
13. Do not run raw destructive cleanup commands.
14. Do not access secrets or forbidden files.
15. The executor remains the only component that mutates execution state.

## Execution Policies

```yaml
scale:
  selected_mode: experimental_6
  max_parallel_workspaces: 6
worktree:
  enabled: true
  root: .pi/worktrees
  state_persistence_path: .pi/worktree-state.json
  crash_recovery_enabled: true
integration_queue:
  enabled: true
  process_one_merge_at_a_time: true
  stop_on_merge_conflict: true
  git_push_allowed: false
queue_optimization:
  enabled: true
  strategy: critical_path_first
validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true
```

## Safety Stops

Hard stop for dependency cycles, unapproved parallelism review, worktree path escape, raw destructive cleanup, integration validation failure, merge conflict without handoff, unsafe scale mode, forbidden file access, secrets access, `git push`, watch-mode validation, optimizer patch without approval, scope mismatch, and future leakage detection.

---

# Part 3 — Machine-Readable Execution Contract

```json
{
  "contractVersion": "2.5.1",
  "executionBackend": "postgres",
  "project": {
    "name": "v7-alphaforge-xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p1"
    ]
  },
  "planExecution": {
    "phase": "P1",
    "title": "Contracts & Alpha Data Contract",
    "mode": "autonomous",
    "maxParallelWorkspaces": 6,
    "scheduling": {
      "continuous": true,
      "slotCount": 6,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": true,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "experimental_6",
      "selectedMode": "experimental_6",
      "modes": {
        "stable_3": {
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false
        },
        "experimental_6": {
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true
        },
        "scale_8": {
          "maxParallelWorkspaces": 8,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "dogfoodPassRequired": true,
          "explicitApprovalRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "prewarmCount": 6,
      "statePersistencePath": ".pi/worktree-state.json",
      "crashRecoveryEnabled": true,
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true,
      "diffPreservationPath": ".pi/executions/{planExecId}/worktrees/{wsId}.patch"
    },
    "integrationQueue": {
      "enabled": true,
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
        "strategy": "critical_path_first",
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
        "markdown_fallback"
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
      "scope_mismatch",
      "future_leakage_detected"
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
    "requestedMaxParallelWorkspaces": 6,
    "selectedScaleMode": "experimental_6",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for experimental_6 and scale_8."
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
    "expectedDagEffectiveParallelismMin": 4,
    "expectedSafeEffectiveParallelismMin": 3,
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
      "worktree_state"
    ]
  },
  "workspaces": [
    {
      "id": "P1.A",
      "title": "Feature Row Contract",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
      "parallelism": {
        "expectedBatch": "batch_1",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/contracts/**",
          "tests/v7/alpha/unit/contracts/**",
          "schemas/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/contracts/**",
        "tests/v7/alpha/unit/contracts/**",
        "schemas/**"
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
        "Define alpha feature row schema and forbidden leakage fields.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/contracts/**",
          "tests/v7/alpha/unit/contracts/**",
          "schemas/**"
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
      "dependencies": [
        "P1.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [
          "P1.C",
          "P1.D"
        ],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/contracts/**",
          "tests/v7/alpha/unit/contracts/**",
          "schemas/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/contracts/**",
        "tests/v7/alpha/unit/contracts/**",
        "schemas/**"
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
        "Define long_R/short_R and classification label schema.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/contracts/**",
          "tests/v7/alpha/unit/contracts/**",
          "schemas/**"
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
      "title": "Prediction Contract",
      "dependencies": [
        "P1.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/contracts/**",
          "tests/v7/alpha/unit/contracts/**",
          "schemas/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/contracts/**",
        "tests/v7/alpha/unit/contracts/**",
        "schemas/**"
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
        "Define calibrated probability, expected-R, and alpha score output.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/contracts/**",
          "tests/v7/alpha/unit/contracts/**",
          "schemas/**"
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
        "P1.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/contracts/**",
          "tests/v7/alpha/unit/contracts/**",
          "schemas/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/contracts/**",
        "tests/v7/alpha/unit/contracts/**",
        "schemas/**"
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
        "Round-trip, enum, numeric-bound, and scope compatibility tests.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/contracts/**",
          "tests/v7/alpha/unit/contracts/**",
          "schemas/**"
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
  "phase": "P1",
  "title": "Contracts & Alpha Data Contract",
  "model_name": "V7 AlphaForge XGB",
  "model_slug": "v7_alphaforge_xgb",
  "depends_on": [
    "P0"
  ],
  "next_phase": "P2",
  "scale_mode": "experimental_6",
  "requested_max_workers": 6,
  "expected_safe_parallelism": 3,
  "primary_focus": "Feature, label, prediction, artifact, and V7 bridge contracts",
  "done_when": "Phase acceptance criteria pass and Part 3 JSON validates."
}
```


## 12. Review Hardening Requirements

* [ ] Feature row contract includes anomaly artifact lineage and fit-window metadata.
* [ ] Prediction contract includes deterministic/regime interaction fields.
* [ ] Decision lifecycle contract supports regime reason codes and constraint levels.
* [ ] Symbol encoding family and symbol universe version are explicit schema fields.

---


<!-- SOURCE: phase_plans/P2__runtime_simulation_adapter_and_r-label_engine.md -->

# P2 — Runtime Simulation Adapter & R-Label Engine

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P2`  
**One-line goal:** Side-effect-free simulation adapter and mode-specific R-label generation.  
**Why now:** Alpha labels must come from the same V7 simulation truth layer that evaluates runtime outcomes.  
**Blast radius:** src/v7/alpha/simulation_adapter/**, src/v7/alpha/labels/**, tests/v7/alpha/golden/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Scale mode:** `experimental_6`  
**Safe parallelism target:** `3`  
**Done when:** All workstreams pass acceptance criteria and phase JSON validates through Pi doctor.

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
| Primary focus | `Side-effect-free simulation adapter and mode-specific R-label generation` |
| Product-code changes | `Allowed` |
| Selected scale mode | `experimental_6` |
| Requested max workers | `6` |
| Expected DAG effective parallelism | `4` |
| Expected safe effective parallelism | `3` |
| Worktree isolation | `Required` |
| Integration queue | `Required` |

### 1.1 RACI

| Workstream | R | A | C | I |
|---|---|---|---|---|
| All phase workstreams | Implementation Agent | Plan Owner | V7 Runtime/ML Reviewer | Maintainers |

---

## 2. Purpose

Alpha labels must come from the same V7 simulation truth layer that evaluates runtime outcomes.

This phase is part of the `V7 AlphaForge XGB` implementation. It must preserve V7's market-first, simulation-native, mode-scoped architecture. The phase must not introduce execution authority into the model layer, must not create a second hidden simulator, and must not use raw future returns as the production alpha truth when V7 simulation-derived R labels are required.

When scale mode is `experimental_6`, the executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

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
* [ ] Worktree isolation remains available when requested by scale mode.
* [ ] Integration queue remains enabled when required by scale mode.
* [ ] Global validation lock remains active for heavy validation.
* [ ] Completion gate hardening remains active.
* [ ] Merge conflicts produce handoff artifacts and do not mark the plan complete.
* [ ] The next plan does not start while the integration queue is dirty.
* [ ] `git push` remains forbidden.
* [ ] Raw destructive cleanup remains forbidden.
* [ ] Watch-mode validation remains forbidden.
* [ ] The executor remains the source of truth for state transitions.

---

## 4. Background / What Was Wrong

The existing V7 design defines mode-specific simulation semantics, hybrid model outputs, and runtime-owned execution boundaries. The new alpha generation system must align with those constraints instead of acting as an independent trading model.

The main missing capability is a V7-native alpha evidence layer that can train on 20 symbols, respect SWING / SCALP / AGGRESSIVE_SCALP semantics, emit calibrated XGBoost classification and regression surfaces, and expose R-native alpha scores to the V7 decision engine.

---

## 5. Current Failure State / Known Blockers

* `v7_alphaforge_xgb` = not implemented.
* `mode_specific_alpha_datasets` = not implemented until P4.
* `xgboost_alpha_artifacts` = not implemented until P5.
* `calibrated_alpha_score_builder` = not implemented until P6.
* `v7_policy_bridge` = not implemented until P7.
* `worktree_isolation` = enabled when selected scale mode requires it.
* `integration_queue` = enabled.
* `scale_mode_readiness` = pending Pi doctor review.
* `safe_effective_parallelism` = expected, not yet computed.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Future leakage enters feature rows | med | critical | Contract forbidden fields, leakage tests, timestamp checks |
| Alpha labels diverge from V7 simulation truth | med | critical | Use runtime simulation adapter only; golden tests |
| Raw XGBoost scores used as calibrated confidence | med | high | confidence_kind required; calibration tests |
| Mode datasets accidentally mixed | med | high | mode field and dataset-family validation |
| Safe parallelism lower than requested | med | med | Doctor warning; use safe batch preview |
| Merge conflict blocks plan | med | med | Handoff artifact and stop queue safely |
| Worktree path escapes `.pi/worktrees` | low | critical | Path scope checks; stop execution on escape |
| Cleanup deletes wrong files | low | critical | Raw destructive cleanup forbidden |

---

## 7. Workstreams

### 7.A — Simulation Adapter

**Goal:** Create side-effect-free wrapper around runtime simulation semantics.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Create side-effect-free wrapper around runtime simulation semantics.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream A may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.B — Mode Config Resolver

**Goal:** Resolve SWING/SCALP/AGGRESSIVE config and lineage.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Resolve SWING/SCALP/AGGRESSIVE config and lineage.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream B may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.C — R Label Builder

**Goal:** Emit long_R, short_R, NO_TRADE quality, ambiguity, and validity fields.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Emit long_R, short_R, NO_TRADE quality, ambiguity, and validity fields.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream C may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.D — Golden Tests

**Goal:** Stop-first, target-first, time-exit, fees/slippage, ambiguity cases.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Stop-first, target-first, time-exit, fees/slippage, ambiguity cases.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream D may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.

---

## 8. Combined Implementation Order

```text
Dependencies: P1
Batch 1: P2.A
Batch 2: P2.B + P2.C + P2.D, subject to same-file conflict review
Next phase: P3
```

Pi's computed approved graph is authoritative. Authored batches are only advisory. Continuous scheduling may run ready workspaces without waiting for batch barriers when safety constraints pass.

---

## 9. Definition of Done

`P2` is complete when ALL are true:

* [ ] All phase workstreams satisfy acceptance criteria.
* [ ] Relevant tests pass.
* [ ] No forbidden commands or files were used.
* [ ] No hidden fallback, hidden simulator, or future leakage was introduced.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation status is correct for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Future leakage detected.
* Simulation truth mismatch detected.
* Contract or schema validation fails.
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Dashboard or doctor reports misleading scale readiness.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Pause integration queue processing.
4. Preserve `.pi/worktrees/{planExecId}/` for debugging.
5. Revert phase workspaces independently.
6. Restore previous compatible config/schema/artifact bundle.
7. Rerun targeted validation and final integration validation.

---

## 11. What Next Phase Inherits

`P3` inherits:

* Completed outputs from `P2`.
* Worktree-aware execution contract.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Safe effective parallelism review.
* Workspace-level parallelism/isolation/integration/validation metadata.

---

# Part 2 — Agent Brief

## Mission

Implement `P2 — Runtime Simulation Adapter & R-Label Engine` for `V7 AlphaForge XGB` while preserving V7 runtime ownership, simulation-native labels, mode-specific datasets, explicit contracts, and safe Pi autonomous execution behavior.

## Hard Requirements

1. Do not create a second simulator.
2. Do not allow future data in features.
3. Do not use raw model scores as calibrated confidence.
4. Do not mix SWING, SCALP, and AGGRESSIVE_SCALP datasets unless explicitly building a report, not a model dataset.
5. Do not exceed selected scale-mode worker cap.
6. Do not run more than 3 workers unless worktree isolation and integration queue readiness pass.
7. Do not merge workspace output without passed workspace validation.
8. Do not mark a plan complete if integration validation fails.
9. Do not treat merge conflict as ordinary worker failure.
10. Do not start the next plan while integration queue state is dirty.
11. Do not run watch-mode validation.
12. Do not run `git push`.
13. Do not run raw destructive cleanup commands.
14. Do not access secrets or forbidden files.
15. The executor remains the only component that mutates execution state.

## Execution Policies

```yaml
scale:
  selected_mode: experimental_6
  max_parallel_workspaces: 6
worktree:
  enabled: true
  root: .pi/worktrees
  state_persistence_path: .pi/worktree-state.json
  crash_recovery_enabled: true
integration_queue:
  enabled: true
  process_one_merge_at_a_time: true
  stop_on_merge_conflict: true
  git_push_allowed: false
queue_optimization:
  enabled: true
  strategy: critical_path_first
validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true
```

## Safety Stops

Hard stop for dependency cycles, unapproved parallelism review, worktree path escape, raw destructive cleanup, integration validation failure, merge conflict without handoff, unsafe scale mode, forbidden file access, secrets access, `git push`, watch-mode validation, optimizer patch without approval, scope mismatch, and future leakage detection.

---

# Part 3 — Machine-Readable Execution Contract

```json
{
  "contractVersion": "2.5.1",
  "executionBackend": "postgres",
  "project": {
    "name": "v7-alphaforge-xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p2"
    ]
  },
  "planExecution": {
    "phase": "P2",
    "title": "Runtime Simulation Adapter & R-Label Engine",
    "mode": "autonomous",
    "maxParallelWorkspaces": 6,
    "scheduling": {
      "continuous": true,
      "slotCount": 6,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": true,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "experimental_6",
      "selectedMode": "experimental_6",
      "modes": {
        "stable_3": {
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false
        },
        "experimental_6": {
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true
        },
        "scale_8": {
          "maxParallelWorkspaces": 8,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "dogfoodPassRequired": true,
          "explicitApprovalRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "prewarmCount": 6,
      "statePersistencePath": ".pi/worktree-state.json",
      "crashRecoveryEnabled": true,
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true,
      "diffPreservationPath": ".pi/executions/{planExecId}/worktrees/{wsId}.patch"
    },
    "integrationQueue": {
      "enabled": true,
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
        "strategy": "critical_path_first",
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
        "markdown_fallback"
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
      "scope_mismatch",
      "future_leakage_detected"
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
    "requestedMaxParallelWorkspaces": 6,
    "selectedScaleMode": "experimental_6",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for experimental_6 and scale_8."
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
    "expectedDagEffectiveParallelismMin": 4,
    "expectedSafeEffectiveParallelismMin": 3,
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
      "worktree_state"
    ]
  },
  "workspaces": [
    {
      "id": "P2.A",
      "title": "Simulation Adapter",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
      "parallelism": {
        "expectedBatch": "batch_1",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/simulation_adapter/**",
          "src/v7/alpha/labels/**",
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
        "queuePriority": "critical",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/simulation_adapter/**",
        "src/v7/alpha/labels/**",
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
        "Create side-effect-free wrapper around runtime simulation semantics.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/simulation_adapter/**",
          "src/v7/alpha/labels/**",
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
    },
    {
      "id": "P2.B",
      "title": "Mode Config Resolver",
      "dependencies": [
        "P2.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [
          "P2.C",
          "P2.D"
        ],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/simulation_adapter/**",
          "src/v7/alpha/labels/**",
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/simulation_adapter/**",
        "src/v7/alpha/labels/**",
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
        "Resolve SWING/SCALP/AGGRESSIVE config and lineage.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/simulation_adapter/**",
          "src/v7/alpha/labels/**",
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
    },
    {
      "id": "P2.C",
      "title": "R Label Builder",
      "dependencies": [
        "P2.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/simulation_adapter/**",
          "src/v7/alpha/labels/**",
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/simulation_adapter/**",
        "src/v7/alpha/labels/**",
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
        "Emit long_R, short_R, NO_TRADE quality, ambiguity, and validity fields.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/simulation_adapter/**",
          "src/v7/alpha/labels/**",
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
    },
    {
      "id": "P2.D",
      "title": "Golden Tests",
      "dependencies": [
        "P2.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/simulation_adapter/**",
          "src/v7/alpha/labels/**",
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/simulation_adapter/**",
        "src/v7/alpha/labels/**",
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
        "Stop-first, target-first, time-exit, fees/slippage, ambiguity cases.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/simulation_adapter/**",
          "src/v7/alpha/labels/**",
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
  "phase": "P2",
  "title": "Runtime Simulation Adapter & R-Label Engine",
  "model_name": "V7 AlphaForge XGB",
  "model_slug": "v7_alphaforge_xgb",
  "depends_on": [
    "P1"
  ],
  "next_phase": "P3",
  "scale_mode": "experimental_6",
  "requested_max_workers": 6,
  "expected_safe_parallelism": 3,
  "primary_focus": "Side-effect-free simulation adapter and mode-specific R-label generation",
  "done_when": "Phase acceptance criteria pass and Part 3 JSON validates."
}
```


## 12. Review Hardening Requirements

* [ ] Simulation profile selection resolves all intervals from central config.
* [ ] Label horizon family uses mode config rather than hardcoded interval literals.
* [ ] SCALP simulation profile asserts primary=1h/context=4h/refinement=15m.

---


<!-- SOURCE: phase_plans/P3__multi-timeframe_feature_engine_and_unsupervised_context.md -->

# P3 — Multi-Timeframe Feature Engine & Unsupervised Context

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P3`  
**One-line goal:** Primary/context/refinement deterministic features and optional anomaly/regime features.  
**Why now:** Model quality depends on leakage-safe, mode-aware features computed from canonical state only.  
**Blast radius:** src/v7/alpha/features/**, src/v7/alpha/anomaly/**, tests/v7/alpha/unit/features/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Scale mode:** `experimental_6`  
**Safe parallelism target:** `4`  
**Done when:** All workstreams pass acceptance criteria and phase JSON validates through Pi doctor.

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
| Primary focus | `Primary/context/refinement deterministic features and optional anomaly/regime features` |
| Product-code changes | `Allowed` |
| Selected scale mode | `experimental_6` |
| Requested max workers | `6` |
| Expected DAG effective parallelism | `4` |
| Expected safe effective parallelism | `4` |
| Worktree isolation | `Required` |
| Integration queue | `Required` |

### 1.1 RACI

| Workstream | R | A | C | I |
|---|---|---|---|---|
| All phase workstreams | Implementation Agent | Plan Owner | V7 Runtime/ML Reviewer | Maintainers |

---

## 2. Purpose

Model quality depends on leakage-safe, mode-aware features computed from canonical state only.

This phase is part of the `V7 AlphaForge XGB` implementation. It must preserve V7's market-first, simulation-native, mode-scoped architecture. The phase must not introduce execution authority into the model layer, must not create a second hidden simulator, and must not use raw future returns as the production alpha truth when V7 simulation-derived R labels are required.

When scale mode is `experimental_6`, the executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

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
* [ ] Worktree isolation remains available when requested by scale mode.
* [ ] Integration queue remains enabled when required by scale mode.
* [ ] Global validation lock remains active for heavy validation.
* [ ] Completion gate hardening remains active.
* [ ] Merge conflicts produce handoff artifacts and do not mark the plan complete.
* [ ] The next plan does not start while the integration queue is dirty.
* [ ] `git push` remains forbidden.
* [ ] Raw destructive cleanup remains forbidden.
* [ ] Watch-mode validation remains forbidden.
* [ ] The executor remains the source of truth for state transitions.

---

## 4. Background / What Was Wrong

The existing V7 design defines mode-specific simulation semantics, hybrid model outputs, and runtime-owned execution boundaries. The new alpha generation system must align with those constraints instead of acting as an independent trading model.

The main missing capability is a V7-native alpha evidence layer that can train on 20 symbols, respect SWING / SCALP / AGGRESSIVE_SCALP semantics, emit calibrated XGBoost classification and regression surfaces, and expose R-native alpha scores to the V7 decision engine.

---

## 5. Current Failure State / Known Blockers

* `v7_alphaforge_xgb` = not implemented.
* `mode_specific_alpha_datasets` = not implemented until P4.
* `xgboost_alpha_artifacts` = not implemented until P5.
* `calibrated_alpha_score_builder` = not implemented until P6.
* `v7_policy_bridge` = not implemented until P7.
* `worktree_isolation` = enabled when selected scale mode requires it.
* `integration_queue` = enabled.
* `scale_mode_readiness` = pending Pi doctor review.
* `safe_effective_parallelism` = expected, not yet computed.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Future leakage enters feature rows | med | critical | Contract forbidden fields, leakage tests, timestamp checks |
| Alpha labels diverge from V7 simulation truth | med | critical | Use runtime simulation adapter only; golden tests |
| Raw XGBoost scores used as calibrated confidence | med | high | confidence_kind required; calibration tests |
| Mode datasets accidentally mixed | med | high | mode field and dataset-family validation |
| Safe parallelism lower than requested | med | med | Doctor warning; use safe batch preview |
| Merge conflict blocks plan | med | med | Handoff artifact and stop queue safely |
| Worktree path escapes `.pi/worktrees` | low | critical | Path scope checks; stop execution on escape |
| Cleanup deletes wrong files | low | critical | Raw destructive cleanup forbidden |

---

## 7. Workstreams

### 7.A — Deterministic Features

**Goal:** Build return, volatility, volume, candle, trend, and technical features.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Build return, volatility, volume, candle, trend, and technical features.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream A may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.B — Multi-Timeframe Join

**Goal:** Attach primary/context/refinement views without future leakage.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Attach primary/context/refinement views without future leakage.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream B may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.C — Unsupervised Context

**Goal:** Add anomaly_score and regime_id as auxiliary features only.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Add anomaly_score and regime_id as auxiliary features only.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream C may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.D — Feature Tests

**Goal:** Leakage, missingness, schema stability, and train-only fit tests.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Leakage, missingness, schema stability, and train-only fit tests.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream D may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.


### 7.E — Fold-Scoped Anomaly Fit Guard

**Goal:** Ensure every unsupervised anomaly/regime artifact is fit only on the active walk-forward fold's training window.

**Requirements:**
* Fit anomaly/regime/clustering artifacts per fold, never on full history.
* Persist anomaly artifact lineage with fit-window metadata.
* Provide transform-only behavior for validation, holdout, replay, paper, and live rows.

**Acceptance Criteria:**
* Tests fail if an anomaly artifact fit window crosses the fold train boundary.
* Feature rows include `fold_id`, `anomaly_artifact_id`, `anomaly_fit_window_start_utc`, and `anomaly_fit_window_end_utc`.
* Global full-history anomaly fitting is blocked by config validation.

**Isolation & Parallelism Notes:**
* This workstream depends on deterministic feature schemas and can run after 7.A.
* It may overlap with feature tests only if Pi assigns separate files/worktrees.
* Workspace validation must include leakage tests.

---

## 8. Combined Implementation Order

```text
Dependencies: P1
Batch 1: P3.A
Batch 2: P3.B + P3.C + P3.D, subject to same-file conflict review
Next phase: P4
```

Pi's computed approved graph is authoritative. Authored batches are only advisory. Continuous scheduling may run ready workspaces without waiting for batch barriers when safety constraints pass.

---

## 9. Definition of Done

`P3` is complete when ALL are true:

* [ ] All phase workstreams satisfy acceptance criteria.
* [ ] Relevant tests pass.
* [ ] No forbidden commands or files were used.
* [ ] No hidden fallback, hidden simulator, or future leakage was introduced.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation status is correct for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Future leakage detected.
* Simulation truth mismatch detected.
* Contract or schema validation fails.
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Dashboard or doctor reports misleading scale readiness.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Pause integration queue processing.
4. Preserve `.pi/worktrees/{planExecId}/` for debugging.
5. Revert phase workspaces independently.
6. Restore previous compatible config/schema/artifact bundle.
7. Rerun targeted validation and final integration validation.

---

## 11. What Next Phase Inherits

`P4` inherits:

* Completed outputs from `P3`.
* Worktree-aware execution contract.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Safe effective parallelism review.
* Workspace-level parallelism/isolation/integration/validation metadata.

---

# Part 2 — Agent Brief

## Mission

Implement `P3 — Multi-Timeframe Feature Engine & Unsupervised Context` for `V7 AlphaForge XGB` while preserving V7 runtime ownership, simulation-native labels, mode-specific datasets, explicit contracts, and safe Pi autonomous execution behavior.

## Hard Requirements

1. Do not create a second simulator.
2. Do not allow future data in features.
3. Do not use raw model scores as calibrated confidence.
4. Do not mix SWING, SCALP, and AGGRESSIVE_SCALP datasets unless explicitly building a report, not a model dataset.
5. Do not exceed selected scale-mode worker cap.
6. Do not run more than 3 workers unless worktree isolation and integration queue readiness pass.
7. Do not merge workspace output without passed workspace validation.
8. Do not mark a plan complete if integration validation fails.
9. Do not treat merge conflict as ordinary worker failure.
10. Do not start the next plan while integration queue state is dirty.
11. Do not run watch-mode validation.
12. Do not run `git push`.
13. Do not run raw destructive cleanup commands.
14. Do not access secrets or forbidden files.
15. The executor remains the only component that mutates execution state.

## Execution Policies

```yaml
scale:
  selected_mode: experimental_6
  max_parallel_workspaces: 6
worktree:
  enabled: true
  root: .pi/worktrees
  state_persistence_path: .pi/worktree-state.json
  crash_recovery_enabled: true
integration_queue:
  enabled: true
  process_one_merge_at_a_time: true
  stop_on_merge_conflict: true
  git_push_allowed: false
queue_optimization:
  enabled: true
  strategy: critical_path_first
validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true
```

## Safety Stops

Hard stop for dependency cycles, unapproved parallelism review, worktree path escape, raw destructive cleanup, integration validation failure, merge conflict without handoff, unsafe scale mode, forbidden file access, secrets access, `git push`, watch-mode validation, optimizer patch without approval, scope mismatch, and future leakage detection.

---

# Part 3 — Machine-Readable Execution Contract

```json
{
  "contractVersion": "2.5.1",
  "executionBackend": "postgres",
  "project": {
    "name": "v7-alphaforge-xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p3"
    ]
  },
  "planExecution": {
    "phase": "P3",
    "title": "Multi-Timeframe Feature Engine & Unsupervised Context",
    "mode": "autonomous",
    "maxParallelWorkspaces": 6,
    "scheduling": {
      "continuous": true,
      "slotCount": 6,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": true,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "experimental_6",
      "selectedMode": "experimental_6",
      "modes": {
        "stable_3": {
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false
        },
        "experimental_6": {
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true
        },
        "scale_8": {
          "maxParallelWorkspaces": 8,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "dogfoodPassRequired": true,
          "explicitApprovalRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "prewarmCount": 6,
      "statePersistencePath": ".pi/worktree-state.json",
      "crashRecoveryEnabled": true,
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true,
      "diffPreservationPath": ".pi/executions/{planExecId}/worktrees/{wsId}.patch"
    },
    "integrationQueue": {
      "enabled": true,
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
        "strategy": "critical_path_first",
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
        "markdown_fallback"
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
      "scope_mismatch",
      "future_leakage_detected"
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
    "requestedMaxParallelWorkspaces": 6,
    "selectedScaleMode": "experimental_6",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for experimental_6 and scale_8."
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
    "expectedDagEffectiveParallelismMin": 4,
    "expectedSafeEffectiveParallelismMin": 4,
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
      "worktree_state"
    ]
  },
  "workspaces": [
    {
      "id": "P3.A",
      "title": "Deterministic Features",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
      "parallelism": {
        "expectedBatch": "batch_1",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/features/**",
          "src/v7/alpha/anomaly/**",
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/features/**",
        "src/v7/alpha/anomaly/**",
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
        "Build return, volatility, volume, candle, trend, and technical features.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/features/**",
          "src/v7/alpha/anomaly/**",
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
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [
          "P3.C",
          "P3.D"
        ],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/features/**",
          "src/v7/alpha/anomaly/**",
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/features/**",
        "src/v7/alpha/anomaly/**",
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
        "Attach primary/context/refinement views without future leakage.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/features/**",
          "src/v7/alpha/anomaly/**",
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
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/features/**",
          "src/v7/alpha/anomaly/**",
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/features/**",
        "src/v7/alpha/anomaly/**",
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
        "Add anomaly_score and regime_id as auxiliary features only.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/features/**",
          "src/v7/alpha/anomaly/**",
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
      "id": "P3.D",
      "title": "Feature Tests",
      "dependencies": [
        "P3.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/features/**",
          "src/v7/alpha/anomaly/**",
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
        "queuePriority": "high",
        "queueOptimizationNotes": "Critical-path or phase-unblocking work should merge first; leaf QA/report work can merge later."
      },
      "validation": {
        "profile": "targeted_then_final",
        "heavyCommandUsesGlobalLock": true,
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/features/**",
        "src/v7/alpha/anomaly/**",
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
        "Leakage, missingness, schema stability, and train-only fit tests.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/features/**",
          "src/v7/alpha/anomaly/**",
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
    }
  ]
}
```

---

# Part 4 — Machine-Readable Summary

```json
{
  "phase": "P3",
  "title": "Multi-Timeframe Feature Engine & Unsupervised Context",
  "model_name": "V7 AlphaForge XGB",
  "model_slug": "v7_alphaforge_xgb",
  "depends_on": [
    "P1"
  ],
  "next_phase": "P4",
  "scale_mode": "experimental_6",
  "requested_max_workers": 6,
  "expected_safe_parallelism": 4,
  "primary_focus": "Primary/context/refinement deterministic features and optional anomaly/regime features",
  "done_when": "Phase acceptance criteria pass and Part 3 JSON validates."
}
```


## 12. Review Hardening Requirements

* [ ] Unsupervised anomaly/regime artifacts are fit only on each fold's training window.
* [ ] Full-history anomaly fitting is forbidden for training/evaluation.
* [ ] Anomaly feature rows include artifact ID, fit-window start/end, transform timestamp, and fold ID.
* [ ] Symbol one-hot encoding is implemented as `symbol_one_hot_v1`, explicitly marked as an MVP encoding family.
* [ ] SCALP feature builder reads primary=1h/context=4h/refinement=15m from config.

---


<!-- SOURCE: phase_plans/P4__dataset_assembly,_walk-forward_splits_and_label_qa.md -->

# P4 — Dataset Assembly, Walk-Forward Splits & Label QA

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P4`  
**One-line goal:** Mode-specific datasets, temporal split family, row validity, symbol weights.  
**Why now:** The model cannot be trained until feature rows and simulation labels are joined safely and evaluated chronologically.  
**Blast radius:** src/v7/alpha/dataset/**, tests/v7/alpha/unit/dataset/**, reports/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Scale mode:** `experimental_6`  
**Safe parallelism target:** `3`  
**Done when:** All workstreams pass acceptance criteria and phase JSON validates through Pi doctor.

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
| Primary focus | `Mode-specific datasets, temporal split family, row validity, symbol weights` |
| Product-code changes | `Allowed` |
| Selected scale mode | `experimental_6` |
| Requested max workers | `6` |
| Expected DAG effective parallelism | `4` |
| Expected safe effective parallelism | `3` |
| Worktree isolation | `Required` |
| Integration queue | `Required` |

### 1.1 RACI

| Workstream | R | A | C | I |
|---|---|---|---|---|
| All phase workstreams | Implementation Agent | Plan Owner | V7 Runtime/ML Reviewer | Maintainers |

---

## 2. Purpose

The model cannot be trained until feature rows and simulation labels are joined safely and evaluated chronologically.

This phase is part of the `V7 AlphaForge XGB` implementation. It must preserve V7's market-first, simulation-native, mode-scoped architecture. The phase must not introduce execution authority into the model layer, must not create a second hidden simulator, and must not use raw future returns as the production alpha truth when V7 simulation-derived R labels are required.

When scale mode is `experimental_6`, the executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

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
* [ ] Worktree isolation remains available when requested by scale mode.
* [ ] Integration queue remains enabled when required by scale mode.
* [ ] Global validation lock remains active for heavy validation.
* [ ] Completion gate hardening remains active.
* [ ] Merge conflicts produce handoff artifacts and do not mark the plan complete.
* [ ] The next plan does not start while the integration queue is dirty.
* [ ] `git push` remains forbidden.
* [ ] Raw destructive cleanup remains forbidden.
* [ ] Watch-mode validation remains forbidden.
* [ ] The executor remains the source of truth for state transitions.

---

## 4. Background / What Was Wrong

The existing V7 design defines mode-specific simulation semantics, hybrid model outputs, and runtime-owned execution boundaries. The new alpha generation system must align with those constraints instead of acting as an independent trading model.

The main missing capability is a V7-native alpha evidence layer that can train on 20 symbols, respect SWING / SCALP / AGGRESSIVE_SCALP semantics, emit calibrated XGBoost classification and regression surfaces, and expose R-native alpha scores to the V7 decision engine.

---

## 5. Current Failure State / Known Blockers

* `v7_alphaforge_xgb` = not implemented.
* `mode_specific_alpha_datasets` = not implemented until P4.
* `xgboost_alpha_artifacts` = not implemented until P5.
* `calibrated_alpha_score_builder` = not implemented until P6.
* `v7_policy_bridge` = not implemented until P7.
* `worktree_isolation` = enabled when selected scale mode requires it.
* `integration_queue` = enabled.
* `scale_mode_readiness` = pending Pi doctor review.
* `safe_effective_parallelism` = expected, not yet computed.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Future leakage enters feature rows | med | critical | Contract forbidden fields, leakage tests, timestamp checks |
| Alpha labels diverge from V7 simulation truth | med | critical | Use runtime simulation adapter only; golden tests |
| Raw XGBoost scores used as calibrated confidence | med | high | confidence_kind required; calibration tests |
| Mode datasets accidentally mixed | med | high | mode field and dataset-family validation |
| Safe parallelism lower than requested | med | med | Doctor warning; use safe batch preview |
| Merge conflict blocks plan | med | med | Handoff artifact and stop queue safely |
| Worktree path escapes `.pi/worktrees` | low | critical | Path scope checks; stop execution on escape |
| Cleanup deletes wrong files | low | critical | Raw destructive cleanup forbidden |

---

## 7. Workstreams

### 7.A — Dataset Joiner

**Goal:** Join feature rows and label rows by symbol/timestamp/mode.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Join feature rows and label rows by symbol/timestamp/mode.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream A may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.B — Walk-Forward Splitter

**Goal:** Implement 6-fold chronological split with metadata.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Implement 6-fold chronological split with metadata.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream B may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.C — Row Validity & Weights

**Goal:** Exclude invalid/unresolved; assign symbol/class weights.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Exclude invalid/unresolved; assign symbol/class weights.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream C may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.D — Dataset QA Reports

**Goal:** Label distributions, missingness, leakage checks, symbol coverage.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Label distributions, missingness, leakage checks, symbol coverage.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream D may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.

---

## 8. Combined Implementation Order

```text
Dependencies: P2, P3
Batch 1: P4.A
Batch 2: P4.B + P4.C + P4.D, subject to same-file conflict review
Next phase: P5
```

Pi's computed approved graph is authoritative. Authored batches are only advisory. Continuous scheduling may run ready workspaces without waiting for batch barriers when safety constraints pass.

---

## 9. Definition of Done

`P4` is complete when ALL are true:

* [ ] All phase workstreams satisfy acceptance criteria.
* [ ] Relevant tests pass.
* [ ] No forbidden commands or files were used.
* [ ] No hidden fallback, hidden simulator, or future leakage was introduced.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation status is correct for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Future leakage detected.
* Simulation truth mismatch detected.
* Contract or schema validation fails.
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Dashboard or doctor reports misleading scale readiness.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Pause integration queue processing.
4. Preserve `.pi/worktrees/{planExecId}/` for debugging.
5. Revert phase workspaces independently.
6. Restore previous compatible config/schema/artifact bundle.
7. Rerun targeted validation and final integration validation.

---

## 11. What Next Phase Inherits

`P5` inherits:

* Completed outputs from `P4`.
* Worktree-aware execution contract.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Safe effective parallelism review.
* Workspace-level parallelism/isolation/integration/validation metadata.

---

# Part 2 — Agent Brief

## Mission

Implement `P4 — Dataset Assembly, Walk-Forward Splits & Label QA` for `V7 AlphaForge XGB` while preserving V7 runtime ownership, simulation-native labels, mode-specific datasets, explicit contracts, and safe Pi autonomous execution behavior.

## Hard Requirements

1. Do not create a second simulator.
2. Do not allow future data in features.
3. Do not use raw model scores as calibrated confidence.
4. Do not mix SWING, SCALP, and AGGRESSIVE_SCALP datasets unless explicitly building a report, not a model dataset.
5. Do not exceed selected scale-mode worker cap.
6. Do not run more than 3 workers unless worktree isolation and integration queue readiness pass.
7. Do not merge workspace output without passed workspace validation.
8. Do not mark a plan complete if integration validation fails.
9. Do not treat merge conflict as ordinary worker failure.
10. Do not start the next plan while integration queue state is dirty.
11. Do not run watch-mode validation.
12. Do not run `git push`.
13. Do not run raw destructive cleanup commands.
14. Do not access secrets or forbidden files.
15. The executor remains the only component that mutates execution state.

## Execution Policies

```yaml
scale:
  selected_mode: experimental_6
  max_parallel_workspaces: 6
worktree:
  enabled: true
  root: .pi/worktrees
  state_persistence_path: .pi/worktree-state.json
  crash_recovery_enabled: true
integration_queue:
  enabled: true
  process_one_merge_at_a_time: true
  stop_on_merge_conflict: true
  git_push_allowed: false
queue_optimization:
  enabled: true
  strategy: critical_path_first
validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true
```

## Safety Stops

Hard stop for dependency cycles, unapproved parallelism review, worktree path escape, raw destructive cleanup, integration validation failure, merge conflict without handoff, unsafe scale mode, forbidden file access, secrets access, `git push`, watch-mode validation, optimizer patch without approval, scope mismatch, and future leakage detection.

---

# Part 3 — Machine-Readable Execution Contract

```json
{
  "contractVersion": "2.5.1",
  "executionBackend": "postgres",
  "project": {
    "name": "v7-alphaforge-xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p4"
    ]
  },
  "planExecution": {
    "phase": "P4",
    "title": "Dataset Assembly, Walk-Forward Splits & Label QA",
    "mode": "autonomous",
    "maxParallelWorkspaces": 6,
    "scheduling": {
      "continuous": true,
      "slotCount": 6,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": true,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "experimental_6",
      "selectedMode": "experimental_6",
      "modes": {
        "stable_3": {
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false
        },
        "experimental_6": {
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true
        },
        "scale_8": {
          "maxParallelWorkspaces": 8,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "dogfoodPassRequired": true,
          "explicitApprovalRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "prewarmCount": 6,
      "statePersistencePath": ".pi/worktree-state.json",
      "crashRecoveryEnabled": true,
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true,
      "diffPreservationPath": ".pi/executions/{planExecId}/worktrees/{wsId}.patch"
    },
    "integrationQueue": {
      "enabled": true,
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
        "strategy": "critical_path_first",
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
        "markdown_fallback"
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
      "scope_mismatch",
      "future_leakage_detected"
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
    "requestedMaxParallelWorkspaces": 6,
    "selectedScaleMode": "experimental_6",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for experimental_6 and scale_8."
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
    "expectedDagEffectiveParallelismMin": 4,
    "expectedSafeEffectiveParallelismMin": 3,
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
      "worktree_state"
    ]
  },
  "workspaces": [
    {
      "id": "P4.A",
      "title": "Dataset Joiner",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
      "parallelism": {
        "expectedBatch": "batch_1",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**",
          "reports/v7/alpha/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/dataset/**",
        "tests/v7/alpha/unit/dataset/**",
        "reports/v7/alpha/**"
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
        "Join feature rows and label rows by symbol/timestamp/mode.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**",
          "reports/v7/alpha/**"
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
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [
          "P4.C",
          "P4.D"
        ],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**",
          "reports/v7/alpha/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/dataset/**",
        "tests/v7/alpha/unit/dataset/**",
        "reports/v7/alpha/**"
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
        "Implement 6-fold chronological split with metadata.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**",
          "reports/v7/alpha/**"
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
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**",
          "reports/v7/alpha/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/dataset/**",
        "tests/v7/alpha/unit/dataset/**",
        "reports/v7/alpha/**"
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
        "Exclude invalid/unresolved; assign symbol/class weights.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**",
          "reports/v7/alpha/**"
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
        "P4.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**",
          "reports/v7/alpha/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/dataset/**",
        "tests/v7/alpha/unit/dataset/**",
        "reports/v7/alpha/**"
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
        "Label distributions, missingness, leakage checks, symbol coverage.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/dataset/**",
          "tests/v7/alpha/unit/dataset/**",
          "reports/v7/alpha/**"
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
  "phase": "P4",
  "title": "Dataset Assembly, Walk-Forward Splits & Label QA",
  "model_name": "V7 AlphaForge XGB",
  "model_slug": "v7_alphaforge_xgb",
  "depends_on": [
    "P2",
    "P3"
  ],
  "next_phase": "P5",
  "scale_mode": "experimental_6",
  "requested_max_workers": 6,
  "expected_safe_parallelism": 3,
  "primary_focus": "Mode-specific datasets, temporal split family, row validity, symbol weights",
  "done_when": "Phase acceptance criteria pass and Part 3 JSON validates."
}
```


## 12. Review Hardening Requirements

* [ ] Dataset assembly rejects rows where anomaly artifact fit-window crosses the fold train boundary.
* [ ] Walk-forward fold metadata is persisted with every row.
* [ ] Dataset QA reports anomaly lineage coverage and leakage-check failures.
* [ ] Mode datasets remain separate; SCALP dataset uses config-resolved primary=1h.

---


<!-- SOURCE: phase_plans/P5__xgboost_hybrid_model_training.md -->

# P5 — XGBoost Hybrid Model Training

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P5`  
**One-line goal:** Mode-specific classifier and expected-R regressors.  
**Why now:** The first candidate artifact family requires XGBoost training, artifact metadata, and reproducible model persistence.  
**Blast radius:** src/v7/alpha/model/**, tests/v7/alpha/integration/model/**, artifacts/v7/alpha/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Scale mode:** `experimental_6`  
**Safe parallelism target:** `3`  
**Done when:** All workstreams pass acceptance criteria and phase JSON validates through Pi doctor.

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
| Primary focus | `Mode-specific classifier and expected-R regressors` |
| Product-code changes | `Allowed` |
| Selected scale mode | `experimental_6` |
| Requested max workers | `6` |
| Expected DAG effective parallelism | `4` |
| Expected safe effective parallelism | `3` |
| Worktree isolation | `Required` |
| Integration queue | `Required` |

### 1.1 RACI

| Workstream | R | A | C | I |
|---|---|---|---|---|
| All phase workstreams | Implementation Agent | Plan Owner | V7 Runtime/ML Reviewer | Maintainers |

---

## 2. Purpose

The first candidate artifact family requires XGBoost training, artifact metadata, and reproducible model persistence.

This phase is part of the `V7 AlphaForge XGB` implementation. It must preserve V7's market-first, simulation-native, mode-scoped architecture. The phase must not introduce execution authority into the model layer, must not create a second hidden simulator, and must not use raw future returns as the production alpha truth when V7 simulation-derived R labels are required.

When scale mode is `experimental_6`, the executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

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
* [ ] Worktree isolation remains available when requested by scale mode.
* [ ] Integration queue remains enabled when required by scale mode.
* [ ] Global validation lock remains active for heavy validation.
* [ ] Completion gate hardening remains active.
* [ ] Merge conflicts produce handoff artifacts and do not mark the plan complete.
* [ ] The next plan does not start while the integration queue is dirty.
* [ ] `git push` remains forbidden.
* [ ] Raw destructive cleanup remains forbidden.
* [ ] Watch-mode validation remains forbidden.
* [ ] The executor remains the source of truth for state transitions.

---

## 4. Background / What Was Wrong

The existing V7 design defines mode-specific simulation semantics, hybrid model outputs, and runtime-owned execution boundaries. The new alpha generation system must align with those constraints instead of acting as an independent trading model.

The main missing capability is a V7-native alpha evidence layer that can train on 20 symbols, respect SWING / SCALP / AGGRESSIVE_SCALP semantics, emit calibrated XGBoost classification and regression surfaces, and expose R-native alpha scores to the V7 decision engine.

---

## 5. Current Failure State / Known Blockers

* `v7_alphaforge_xgb` = not implemented.
* `mode_specific_alpha_datasets` = not implemented until P4.
* `xgboost_alpha_artifacts` = not implemented until P5.
* `calibrated_alpha_score_builder` = not implemented until P6.
* `v7_policy_bridge` = not implemented until P7.
* `worktree_isolation` = enabled when selected scale mode requires it.
* `integration_queue` = enabled.
* `scale_mode_readiness` = pending Pi doctor review.
* `safe_effective_parallelism` = expected, not yet computed.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Future leakage enters feature rows | med | critical | Contract forbidden fields, leakage tests, timestamp checks |
| Alpha labels diverge from V7 simulation truth | med | critical | Use runtime simulation adapter only; golden tests |
| Raw XGBoost scores used as calibrated confidence | med | high | confidence_kind required; calibration tests |
| Mode datasets accidentally mixed | med | high | mode field and dataset-family validation |
| Safe parallelism lower than requested | med | med | Doctor warning; use safe batch preview |
| Merge conflict blocks plan | med | med | Handoff artifact and stop queue safely |
| Worktree path escapes `.pi/worktrees` | low | critical | Path scope checks; stop execution on escape |
| Cleanup deletes wrong files | low | critical | Raw destructive cleanup forbidden |

---

## 7. Workstreams

### 7.A — Classifier Training

**Goal:** Train P(LONG_NOW), P(SHORT_NOW), P(NO_TRADE) per mode.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Train P(LONG_NOW), P(SHORT_NOW), P(NO_TRADE) per mode.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream A may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.B — Regressor Training

**Goal:** Train expected_R_long and expected_R_short per mode.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Train expected_R_long and expected_R_short per mode.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream B may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.C — Artifact Bundles

**Goal:** Persist model bundle metadata and compatibility checks.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Persist model bundle metadata and compatibility checks.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream C may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.D — Training Metrics

**Goal:** Produce classification and regression validation summaries.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Produce classification and regression validation summaries.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream D may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.


### 7.E — Symbol Encoding Metadata

**Goal:** Make symbol encoding an explicit artifact and feature-schema family rather than a hidden modeling assumption.

**Requirements:**
* MVP uses `symbol_one_hot_v1` over the approved 20-symbol universe.
* Artifact metadata records `symbol_encoding_family` and `symbol_universe_version`.
* Universe expansion requires schema or encoding-family version bump.

**Acceptance Criteria:**
* Training fails if symbol encoding metadata is missing.
* Training fails if the dataset contains symbols outside the approved universe version.
* Tests document the future swap path for target encoding or embedding-derived features.

**Isolation & Parallelism Notes:**
* This workstream depends on artifact bundle metadata.
* It can run alongside metrics work if file overlap is low.

---

## 8. Combined Implementation Order

```text
Dependencies: P4
Batch 1: P5.A
Batch 2: P5.B + P5.C + P5.D, subject to same-file conflict review
Next phase: P6
```

Pi's computed approved graph is authoritative. Authored batches are only advisory. Continuous scheduling may run ready workspaces without waiting for batch barriers when safety constraints pass.

---

## 9. Definition of Done

`P5` is complete when ALL are true:

* [ ] All phase workstreams satisfy acceptance criteria.
* [ ] Relevant tests pass.
* [ ] No forbidden commands or files were used.
* [ ] No hidden fallback, hidden simulator, or future leakage was introduced.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation status is correct for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Future leakage detected.
* Simulation truth mismatch detected.
* Contract or schema validation fails.
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Dashboard or doctor reports misleading scale readiness.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Pause integration queue processing.
4. Preserve `.pi/worktrees/{planExecId}/` for debugging.
5. Revert phase workspaces independently.
6. Restore previous compatible config/schema/artifact bundle.
7. Rerun targeted validation and final integration validation.

---

## 11. What Next Phase Inherits

`P6` inherits:

* Completed outputs from `P5`.
* Worktree-aware execution contract.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Safe effective parallelism review.
* Workspace-level parallelism/isolation/integration/validation metadata.

---

# Part 2 — Agent Brief

## Mission

Implement `P5 — XGBoost Hybrid Model Training` for `V7 AlphaForge XGB` while preserving V7 runtime ownership, simulation-native labels, mode-specific datasets, explicit contracts, and safe Pi autonomous execution behavior.

## Hard Requirements

1. Do not create a second simulator.
2. Do not allow future data in features.
3. Do not use raw model scores as calibrated confidence.
4. Do not mix SWING, SCALP, and AGGRESSIVE_SCALP datasets unless explicitly building a report, not a model dataset.
5. Do not exceed selected scale-mode worker cap.
6. Do not run more than 3 workers unless worktree isolation and integration queue readiness pass.
7. Do not merge workspace output without passed workspace validation.
8. Do not mark a plan complete if integration validation fails.
9. Do not treat merge conflict as ordinary worker failure.
10. Do not start the next plan while integration queue state is dirty.
11. Do not run watch-mode validation.
12. Do not run `git push`.
13. Do not run raw destructive cleanup commands.
14. Do not access secrets or forbidden files.
15. The executor remains the only component that mutates execution state.

## Execution Policies

```yaml
scale:
  selected_mode: experimental_6
  max_parallel_workspaces: 6
worktree:
  enabled: true
  root: .pi/worktrees
  state_persistence_path: .pi/worktree-state.json
  crash_recovery_enabled: true
integration_queue:
  enabled: true
  process_one_merge_at_a_time: true
  stop_on_merge_conflict: true
  git_push_allowed: false
queue_optimization:
  enabled: true
  strategy: critical_path_first
validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true
```

## Safety Stops

Hard stop for dependency cycles, unapproved parallelism review, worktree path escape, raw destructive cleanup, integration validation failure, merge conflict without handoff, unsafe scale mode, forbidden file access, secrets access, `git push`, watch-mode validation, optimizer patch without approval, scope mismatch, and future leakage detection.

---

# Part 3 — Machine-Readable Execution Contract

```json
{
  "contractVersion": "2.5.1",
  "executionBackend": "postgres",
  "project": {
    "name": "v7-alphaforge-xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p5"
    ]
  },
  "planExecution": {
    "phase": "P5",
    "title": "XGBoost Hybrid Model Training",
    "mode": "autonomous",
    "maxParallelWorkspaces": 6,
    "scheduling": {
      "continuous": true,
      "slotCount": 6,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": true,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "experimental_6",
      "selectedMode": "experimental_6",
      "modes": {
        "stable_3": {
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false
        },
        "experimental_6": {
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true
        },
        "scale_8": {
          "maxParallelWorkspaces": 8,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "dogfoodPassRequired": true,
          "explicitApprovalRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "prewarmCount": 6,
      "statePersistencePath": ".pi/worktree-state.json",
      "crashRecoveryEnabled": true,
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true,
      "diffPreservationPath": ".pi/executions/{planExecId}/worktrees/{wsId}.patch"
    },
    "integrationQueue": {
      "enabled": true,
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
        "strategy": "critical_path_first",
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
        "markdown_fallback"
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
      "scope_mismatch",
      "future_leakage_detected"
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
    "requestedMaxParallelWorkspaces": 6,
    "selectedScaleMode": "experimental_6",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for experimental_6 and scale_8."
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
    "expectedDagEffectiveParallelismMin": 4,
    "expectedSafeEffectiveParallelismMin": 3,
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
      "worktree_state"
    ]
  },
  "workspaces": [
    {
      "id": "P5.A",
      "title": "Classifier Training",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
      "parallelism": {
        "expectedBatch": "batch_1",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/model/**",
          "tests/v7/alpha/integration/model/**",
          "artifacts/v7/alpha/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/model/**",
        "tests/v7/alpha/integration/model/**",
        "artifacts/v7/alpha/**"
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
        "Train P(LONG_NOW), P(SHORT_NOW), P(NO_TRADE) per mode.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/model/**",
          "tests/v7/alpha/integration/model/**",
          "artifacts/v7/alpha/**"
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
      "dependencies": [
        "P5.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [
          "P5.C",
          "P5.D"
        ],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/model/**",
          "tests/v7/alpha/integration/model/**",
          "artifacts/v7/alpha/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/model/**",
        "tests/v7/alpha/integration/model/**",
        "artifacts/v7/alpha/**"
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
        "Train expected_R_long and expected_R_short per mode.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/model/**",
          "tests/v7/alpha/integration/model/**",
          "artifacts/v7/alpha/**"
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
        "P5.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/model/**",
          "tests/v7/alpha/integration/model/**",
          "artifacts/v7/alpha/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/model/**",
        "tests/v7/alpha/integration/model/**",
        "artifacts/v7/alpha/**"
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
        "Persist model bundle metadata and compatibility checks.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/model/**",
          "tests/v7/alpha/integration/model/**",
          "artifacts/v7/alpha/**"
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
        "P5.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/model/**",
          "tests/v7/alpha/integration/model/**",
          "artifacts/v7/alpha/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/model/**",
        "tests/v7/alpha/integration/model/**",
        "artifacts/v7/alpha/**"
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
        "Produce classification and regression validation summaries.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/model/**",
          "tests/v7/alpha/integration/model/**",
          "artifacts/v7/alpha/**"
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
  "phase": "P5",
  "title": "XGBoost Hybrid Model Training",
  "model_name": "V7 AlphaForge XGB",
  "model_slug": "v7_alphaforge_xgb",
  "depends_on": [
    "P4"
  ],
  "next_phase": "P6",
  "scale_mode": "experimental_6",
  "requested_max_workers": 6,
  "expected_safe_parallelism": 3,
  "primary_focus": "Mode-specific classifier and expected-R regressors",
  "done_when": "Phase acceptance criteria pass and Part 3 JSON validates."
}
```


## 12. Review Hardening Requirements

* [ ] Model training consumes fold-compatible anomaly features only.
* [ ] Training artifact bundle records anomaly artifact lineage per fold.
* [ ] Symbol encoding family is recorded in artifact metadata.
* [ ] Expanding beyond the approved 20-symbol universe requires schema or encoding-family version bump and retraining.

---


<!-- SOURCE: phase_plans/P6__calibration,_reliability_and_alpha_score_builder.md -->

# P6 — Calibration, Reliability & Alpha Score Builder

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P6`  
**One-line goal:** Per-mode calibration, expected-R reliability, and long/short alpha-R scores.  
**Why now:** V7 policy cannot safely use raw model scores; probabilities and expected-R must be reliability-reviewed and converted into R-native alpha evidence.  
**Blast radius:** src/v7/alpha/calibration/**, src/v7/alpha/scoring/**, tests/v7/alpha/unit/calibration/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Scale mode:** `experimental_6`  
**Safe parallelism target:** `3`  
**Done when:** All workstreams pass acceptance criteria and phase JSON validates through Pi doctor.

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
| Primary focus | `Per-mode calibration, expected-R reliability, and long/short alpha-R scores` |
| Product-code changes | `Allowed` |
| Selected scale mode | `experimental_6` |
| Requested max workers | `6` |
| Expected DAG effective parallelism | `4` |
| Expected safe effective parallelism | `3` |
| Worktree isolation | `Required` |
| Integration queue | `Required` |

### 1.1 RACI

| Workstream | R | A | C | I |
|---|---|---|---|---|
| All phase workstreams | Implementation Agent | Plan Owner | V7 Runtime/ML Reviewer | Maintainers |

---

## 2. Purpose

V7 policy cannot safely use raw model scores; probabilities and expected-R must be reliability-reviewed and converted into R-native alpha evidence.

This phase is part of the `V7 AlphaForge XGB` implementation. It must preserve V7's market-first, simulation-native, mode-scoped architecture. The phase must not introduce execution authority into the model layer, must not create a second hidden simulator, and must not use raw future returns as the production alpha truth when V7 simulation-derived R labels are required.

When scale mode is `experimental_6`, the executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

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
* [ ] Worktree isolation remains available when requested by scale mode.
* [ ] Integration queue remains enabled when required by scale mode.
* [ ] Global validation lock remains active for heavy validation.
* [ ] Completion gate hardening remains active.
* [ ] Merge conflicts produce handoff artifacts and do not mark the plan complete.
* [ ] The next plan does not start while the integration queue is dirty.
* [ ] `git push` remains forbidden.
* [ ] Raw destructive cleanup remains forbidden.
* [ ] Watch-mode validation remains forbidden.
* [ ] The executor remains the source of truth for state transitions.

---

## 4. Background / What Was Wrong

The existing V7 design defines mode-specific simulation semantics, hybrid model outputs, and runtime-owned execution boundaries. The new alpha generation system must align with those constraints instead of acting as an independent trading model.

The main missing capability is a V7-native alpha evidence layer that can train on 20 symbols, respect SWING / SCALP / AGGRESSIVE_SCALP semantics, emit calibrated XGBoost classification and regression surfaces, and expose R-native alpha scores to the V7 decision engine.

---

## 5. Current Failure State / Known Blockers

* `v7_alphaforge_xgb` = not implemented.
* `mode_specific_alpha_datasets` = not implemented until P4.
* `xgboost_alpha_artifacts` = not implemented until P5.
* `calibrated_alpha_score_builder` = not implemented until P6.
* `v7_policy_bridge` = not implemented until P7.
* `worktree_isolation` = enabled when selected scale mode requires it.
* `integration_queue` = enabled.
* `scale_mode_readiness` = pending Pi doctor review.
* `safe_effective_parallelism` = expected, not yet computed.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Future leakage enters feature rows | med | critical | Contract forbidden fields, leakage tests, timestamp checks |
| Alpha labels diverge from V7 simulation truth | med | critical | Use runtime simulation adapter only; golden tests |
| Raw XGBoost scores used as calibrated confidence | med | high | confidence_kind required; calibration tests |
| Mode datasets accidentally mixed | med | high | mode field and dataset-family validation |
| Safe parallelism lower than requested | med | med | Doctor warning; use safe batch preview |
| Merge conflict blocks plan | med | med | Handoff artifact and stop queue safely |
| Worktree path escapes `.pi/worktrees` | low | critical | Path scope checks; stop execution on escape |
| Cleanup deletes wrong files | low | critical | Raw destructive cleanup forbidden |

---

## 7. Workstreams

### 7.A — Probability Calibration

**Goal:** Fit per-mode calibrated action probability surfaces.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Fit per-mode calibrated action probability surfaces.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream A may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.B — Regression Reliability

**Goal:** Bucket predicted R vs realized R and mark unreliable heads.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Bucket predicted R vs realized R and mark unreliable heads.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream B may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.C — Alpha Score Builder

**Goal:** Compute long_alpha_R and short_alpha_R with confidence.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Compute long_alpha_R and short_alpha_R with confidence.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream C may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.D — Calibration Tests

**Goal:** Verify raw confidence is never mislabeled as calibrated.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Verify raw confidence is never mislabeled as calibrated.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream D may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.

---

## 8. Combined Implementation Order

```text
Dependencies: P5
Batch 1: P6.A
Batch 2: P6.B + P6.C + P6.D, subject to same-file conflict review
Next phase: P7
```

Pi's computed approved graph is authoritative. Authored batches are only advisory. Continuous scheduling may run ready workspaces without waiting for batch barriers when safety constraints pass.

---

## 9. Definition of Done

`P6` is complete when ALL are true:

* [ ] All phase workstreams satisfy acceptance criteria.
* [ ] Relevant tests pass.
* [ ] No forbidden commands or files were used.
* [ ] No hidden fallback, hidden simulator, or future leakage was introduced.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation status is correct for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Future leakage detected.
* Simulation truth mismatch detected.
* Contract or schema validation fails.
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Dashboard or doctor reports misleading scale readiness.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Pause integration queue processing.
4. Preserve `.pi/worktrees/{planExecId}/` for debugging.
5. Revert phase workspaces independently.
6. Restore previous compatible config/schema/artifact bundle.
7. Rerun targeted validation and final integration validation.

---

## 11. What Next Phase Inherits

`P7` inherits:

* Completed outputs from `P6`.
* Worktree-aware execution contract.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Safe effective parallelism review.
* Workspace-level parallelism/isolation/integration/validation metadata.

---

# Part 2 — Agent Brief

## Mission

Implement `P6 — Calibration, Reliability & Alpha Score Builder` for `V7 AlphaForge XGB` while preserving V7 runtime ownership, simulation-native labels, mode-specific datasets, explicit contracts, and safe Pi autonomous execution behavior.

## Hard Requirements

1. Do not create a second simulator.
2. Do not allow future data in features.
3. Do not use raw model scores as calibrated confidence.
4. Do not mix SWING, SCALP, and AGGRESSIVE_SCALP datasets unless explicitly building a report, not a model dataset.
5. Do not exceed selected scale-mode worker cap.
6. Do not run more than 3 workers unless worktree isolation and integration queue readiness pass.
7. Do not merge workspace output without passed workspace validation.
8. Do not mark a plan complete if integration validation fails.
9. Do not treat merge conflict as ordinary worker failure.
10. Do not start the next plan while integration queue state is dirty.
11. Do not run watch-mode validation.
12. Do not run `git push`.
13. Do not run raw destructive cleanup commands.
14. Do not access secrets or forbidden files.
15. The executor remains the only component that mutates execution state.

## Execution Policies

```yaml
scale:
  selected_mode: experimental_6
  max_parallel_workspaces: 6
worktree:
  enabled: true
  root: .pi/worktrees
  state_persistence_path: .pi/worktree-state.json
  crash_recovery_enabled: true
integration_queue:
  enabled: true
  process_one_merge_at_a_time: true
  stop_on_merge_conflict: true
  git_push_allowed: false
queue_optimization:
  enabled: true
  strategy: critical_path_first
validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true
```

## Safety Stops

Hard stop for dependency cycles, unapproved parallelism review, worktree path escape, raw destructive cleanup, integration validation failure, merge conflict without handoff, unsafe scale mode, forbidden file access, secrets access, `git push`, watch-mode validation, optimizer patch without approval, scope mismatch, and future leakage detection.

---

# Part 3 — Machine-Readable Execution Contract

```json
{
  "contractVersion": "2.5.1",
  "executionBackend": "postgres",
  "project": {
    "name": "v7-alphaforge-xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p6"
    ]
  },
  "planExecution": {
    "phase": "P6",
    "title": "Calibration, Reliability & Alpha Score Builder",
    "mode": "autonomous",
    "maxParallelWorkspaces": 6,
    "scheduling": {
      "continuous": true,
      "slotCount": 6,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": true,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "experimental_6",
      "selectedMode": "experimental_6",
      "modes": {
        "stable_3": {
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false
        },
        "experimental_6": {
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true
        },
        "scale_8": {
          "maxParallelWorkspaces": 8,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "dogfoodPassRequired": true,
          "explicitApprovalRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "prewarmCount": 6,
      "statePersistencePath": ".pi/worktree-state.json",
      "crashRecoveryEnabled": true,
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true,
      "diffPreservationPath": ".pi/executions/{planExecId}/worktrees/{wsId}.patch"
    },
    "integrationQueue": {
      "enabled": true,
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
        "strategy": "critical_path_first",
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
        "markdown_fallback"
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
      "scope_mismatch",
      "future_leakage_detected"
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
    "requestedMaxParallelWorkspaces": 6,
    "selectedScaleMode": "experimental_6",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for experimental_6 and scale_8."
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
    "expectedDagEffectiveParallelismMin": 4,
    "expectedSafeEffectiveParallelismMin": 3,
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
      "worktree_state"
    ]
  },
  "workspaces": [
    {
      "id": "P6.A",
      "title": "Probability Calibration",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
      "parallelism": {
        "expectedBatch": "batch_1",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/calibration/**",
          "src/v7/alpha/scoring/**",
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/calibration/**",
        "src/v7/alpha/scoring/**",
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
        "Fit per-mode calibrated action probability surfaces.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/calibration/**",
          "src/v7/alpha/scoring/**",
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
      "dependencies": [
        "P6.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [
          "P6.C",
          "P6.D"
        ],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/calibration/**",
          "src/v7/alpha/scoring/**",
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/calibration/**",
        "src/v7/alpha/scoring/**",
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
        "Bucket predicted R vs realized R and mark unreliable heads.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/calibration/**",
          "src/v7/alpha/scoring/**",
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
        "P6.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/calibration/**",
          "src/v7/alpha/scoring/**",
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/calibration/**",
        "src/v7/alpha/scoring/**",
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
        "Compute long_alpha_R and short_alpha_R with confidence.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/calibration/**",
          "src/v7/alpha/scoring/**",
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
      "id": "P6.D",
      "title": "Calibration Tests",
      "dependencies": [
        "P6.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/calibration/**",
          "src/v7/alpha/scoring/**",
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/calibration/**",
        "src/v7/alpha/scoring/**",
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
        "Verify raw confidence is never mislabeled as calibrated.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "medium",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/calibration/**",
          "src/v7/alpha/scoring/**",
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
  "phase": "P6",
  "title": "Calibration, Reliability & Alpha Score Builder",
  "model_name": "V7 AlphaForge XGB",
  "model_slug": "v7_alphaforge_xgb",
  "depends_on": [
    "P5"
  ],
  "next_phase": "P7",
  "scale_mode": "experimental_6",
  "requested_max_workers": 6,
  "expected_safe_parallelism": 3,
  "primary_focus": "Per-mode calibration, expected-R reliability, and long/short alpha-R scores",
  "done_when": "Phase acceptance criteria pass and Part 3 JSON validates."
}
```


## 12. Review Hardening Requirements

* [ ] Reliability reports separate deterministic/regime policy influence from model confidence.
* [ ] Alpha score builder does not hide regime threshold multipliers.
* [ ] Calibration artifacts remain per mode and compatible with the feature/anomaly lineage used during training.

---


<!-- SOURCE: phase_plans/P7__v7_policy,_portfolio_and_risk_integration.md -->

# P7 — V7 Policy, Portfolio & Risk Integration

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P7`  
**One-line goal:** Bridge alpha predictions into V7 policy/risk decision surfaces.  
**Why now:** Alpha predictions become useful only when consumed by V7's explicit policy, portfolio, and risk layers without hidden execution authority.  
**Blast radius:** src/v7/alpha/policy_bridge/**, src/v7/alpha/runtime/**, tests/v7/alpha/integration/runtime/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Scale mode:** `experimental_6`  
**Safe parallelism target:** `3`  
**Done when:** All workstreams pass acceptance criteria and phase JSON validates through Pi doctor.

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
| Primary focus | `Bridge alpha predictions into V7 policy/risk decision surfaces` |
| Product-code changes | `Allowed` |
| Selected scale mode | `experimental_6` |
| Requested max workers | `6` |
| Expected DAG effective parallelism | `4` |
| Expected safe effective parallelism | `3` |
| Worktree isolation | `Required` |
| Integration queue | `Required` |

### 1.1 RACI

| Workstream | R | A | C | I |
|---|---|---|---|---|
| All phase workstreams | Implementation Agent | Plan Owner | V7 Runtime/ML Reviewer | Maintainers |

---

## 2. Purpose

Alpha predictions become useful only when consumed by V7's explicit policy, portfolio, and risk layers without hidden execution authority.

This phase is part of the `V7 AlphaForge XGB` implementation. It must preserve V7's market-first, simulation-native, mode-scoped architecture. The phase must not introduce execution authority into the model layer, must not create a second hidden simulator, and must not use raw future returns as the production alpha truth when V7 simulation-derived R labels are required.

When scale mode is `experimental_6`, the executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

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
* [ ] Worktree isolation remains available when requested by scale mode.
* [ ] Integration queue remains enabled when required by scale mode.
* [ ] Global validation lock remains active for heavy validation.
* [ ] Completion gate hardening remains active.
* [ ] Merge conflicts produce handoff artifacts and do not mark the plan complete.
* [ ] The next plan does not start while the integration queue is dirty.
* [ ] `git push` remains forbidden.
* [ ] Raw destructive cleanup remains forbidden.
* [ ] Watch-mode validation remains forbidden.
* [ ] The executor remains the source of truth for state transitions.

---

## 4. Background / What Was Wrong

The existing V7 design defines mode-specific simulation semantics, hybrid model outputs, and runtime-owned execution boundaries. The new alpha generation system must align with those constraints instead of acting as an independent trading model.

The main missing capability is a V7-native alpha evidence layer that can train on 20 symbols, respect SWING / SCALP / AGGRESSIVE_SCALP semantics, emit calibrated XGBoost classification and regression surfaces, and expose R-native alpha scores to the V7 decision engine.

---

## 5. Current Failure State / Known Blockers

* `v7_alphaforge_xgb` = not implemented.
* `mode_specific_alpha_datasets` = not implemented until P4.
* `xgboost_alpha_artifacts` = not implemented until P5.
* `calibrated_alpha_score_builder` = not implemented until P6.
* `v7_policy_bridge` = not implemented until P7.
* `worktree_isolation` = enabled when selected scale mode requires it.
* `integration_queue` = enabled.
* `scale_mode_readiness` = pending Pi doctor review.
* `safe_effective_parallelism` = expected, not yet computed.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Future leakage enters feature rows | med | critical | Contract forbidden fields, leakage tests, timestamp checks |
| Alpha labels diverge from V7 simulation truth | med | critical | Use runtime simulation adapter only; golden tests |
| Raw XGBoost scores used as calibrated confidence | med | high | confidence_kind required; calibration tests |
| Mode datasets accidentally mixed | med | high | mode field and dataset-family validation |
| Safe parallelism lower than requested | med | med | Doctor warning; use safe batch preview |
| Merge conflict blocks plan | med | med | Handoff artifact and stop queue safely |
| Worktree path escapes `.pi/worktrees` | low | critical | Path scope checks; stop execution on escape |
| Cleanup deletes wrong files | low | critical | Raw destructive cleanup forbidden |

---

## 7. Workstreams

### 7.A — Policy Bridge

**Goal:** Expose alpha scores to V7 actionability gates.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Expose alpha scores to V7 actionability gates.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream A may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.B — Portfolio Context

**Goal:** Feed expected-R and confidence to ranking/suppression surfaces.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Feed expected-R and confidence to ranking/suppression surfaces.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream B may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.C — Risk Visibility

**Goal:** Ensure risk blocks remain explicit and alpha cannot override hard gates.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Ensure risk blocks remain explicit and alpha cannot override hard gates.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream C may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.D — Runtime Contract Tests

**Goal:** End-to-end AnalysisRequest -> alpha output -> DecisionEvent tests.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* End-to-end AnalysisRequest -> alpha output -> DecisionEvent tests.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream D may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.


### 7.E — Regime Override Visibility

**Goal:** Make every deterministic/regime policy influence visible, reviewable, and monitorable.

**Requirements:**
* AnalysisResult exposes regime state, constraint level, policy action, and reason codes.
* DecisionEvent records regime gate reason codes and whether regime changed the model-preferred action.
* Silent deterministic vetoes are forbidden.

**Acceptance Criteria:**
* TRANSITION-forced no-trade emits `regime_gate_forced_no_trade`.
* Direction blocks emit `regime_blocked_direction`.
* Tests prove model-preferred action and final policy action are both persisted.

**Isolation & Parallelism Notes:**
* This workstream depends on policy bridge work and contract surfaces.
* It should not run concurrently with same-file policy edits unless Pi optimizer approves.

---

## 8. Combined Implementation Order

```text
Dependencies: P6
Batch 1: P7.A
Batch 2: P7.B + P7.C + P7.D, subject to same-file conflict review
Next phase: P8
```

Pi's computed approved graph is authoritative. Authored batches are only advisory. Continuous scheduling may run ready workspaces without waiting for batch barriers when safety constraints pass.

---

## 9. Definition of Done

`P7` is complete when ALL are true:

* [ ] All phase workstreams satisfy acceptance criteria.
* [ ] Relevant tests pass.
* [ ] No forbidden commands or files were used.
* [ ] No hidden fallback, hidden simulator, or future leakage was introduced.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation status is correct for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Future leakage detected.
* Simulation truth mismatch detected.
* Contract or schema validation fails.
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Dashboard or doctor reports misleading scale readiness.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Pause integration queue processing.
4. Preserve `.pi/worktrees/{planExecId}/` for debugging.
5. Revert phase workspaces independently.
6. Restore previous compatible config/schema/artifact bundle.
7. Rerun targeted validation and final integration validation.

---

## 11. What Next Phase Inherits

`P8` inherits:

* Completed outputs from `P7`.
* Worktree-aware execution contract.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Safe effective parallelism review.
* Workspace-level parallelism/isolation/integration/validation metadata.

---

# Part 2 — Agent Brief

## Mission

Implement `P7 — V7 Policy, Portfolio & Risk Integration` for `V7 AlphaForge XGB` while preserving V7 runtime ownership, simulation-native labels, mode-specific datasets, explicit contracts, and safe Pi autonomous execution behavior.

## Hard Requirements

1. Do not create a second simulator.
2. Do not allow future data in features.
3. Do not use raw model scores as calibrated confidence.
4. Do not mix SWING, SCALP, and AGGRESSIVE_SCALP datasets unless explicitly building a report, not a model dataset.
5. Do not exceed selected scale-mode worker cap.
6. Do not run more than 3 workers unless worktree isolation and integration queue readiness pass.
7. Do not merge workspace output without passed workspace validation.
8. Do not mark a plan complete if integration validation fails.
9. Do not treat merge conflict as ordinary worker failure.
10. Do not start the next plan while integration queue state is dirty.
11. Do not run watch-mode validation.
12. Do not run `git push`.
13. Do not run raw destructive cleanup commands.
14. Do not access secrets or forbidden files.
15. The executor remains the only component that mutates execution state.

## Execution Policies

```yaml
scale:
  selected_mode: experimental_6
  max_parallel_workspaces: 6
worktree:
  enabled: true
  root: .pi/worktrees
  state_persistence_path: .pi/worktree-state.json
  crash_recovery_enabled: true
integration_queue:
  enabled: true
  process_one_merge_at_a_time: true
  stop_on_merge_conflict: true
  git_push_allowed: false
queue_optimization:
  enabled: true
  strategy: critical_path_first
validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true
```

## Safety Stops

Hard stop for dependency cycles, unapproved parallelism review, worktree path escape, raw destructive cleanup, integration validation failure, merge conflict without handoff, unsafe scale mode, forbidden file access, secrets access, `git push`, watch-mode validation, optimizer patch without approval, scope mismatch, and future leakage detection.

---

# Part 3 — Machine-Readable Execution Contract

```json
{
  "contractVersion": "2.5.1",
  "executionBackend": "postgres",
  "project": {
    "name": "v7-alphaforge-xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p7"
    ]
  },
  "planExecution": {
    "phase": "P7",
    "title": "V7 Policy, Portfolio & Risk Integration",
    "mode": "autonomous",
    "maxParallelWorkspaces": 6,
    "scheduling": {
      "continuous": true,
      "slotCount": 6,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": true,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "experimental_6",
      "selectedMode": "experimental_6",
      "modes": {
        "stable_3": {
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false
        },
        "experimental_6": {
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true
        },
        "scale_8": {
          "maxParallelWorkspaces": 8,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "dogfoodPassRequired": true,
          "explicitApprovalRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "prewarmCount": 6,
      "statePersistencePath": ".pi/worktree-state.json",
      "crashRecoveryEnabled": true,
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true,
      "diffPreservationPath": ".pi/executions/{planExecId}/worktrees/{wsId}.patch"
    },
    "integrationQueue": {
      "enabled": true,
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
        "strategy": "critical_path_first",
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
        "markdown_fallback"
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
      "scope_mismatch",
      "future_leakage_detected"
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
    "requestedMaxParallelWorkspaces": 6,
    "selectedScaleMode": "experimental_6",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for experimental_6 and scale_8."
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
    "expectedDagEffectiveParallelismMin": 4,
    "expectedSafeEffectiveParallelismMin": 3,
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
      "worktree_state"
    ]
  },
  "workspaces": [
    {
      "id": "P7.A",
      "title": "Policy Bridge",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
      "parallelism": {
        "expectedBatch": "batch_1",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/policy_bridge/**",
          "src/v7/alpha/runtime/**",
          "tests/v7/alpha/integration/runtime/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/policy_bridge/**",
        "src/v7/alpha/runtime/**",
        "tests/v7/alpha/integration/runtime/**"
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
        "Expose alpha scores to V7 actionability gates.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/policy_bridge/**",
          "src/v7/alpha/runtime/**",
          "tests/v7/alpha/integration/runtime/**"
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
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [
          "P7.C",
          "P7.D"
        ],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/policy_bridge/**",
          "src/v7/alpha/runtime/**",
          "tests/v7/alpha/integration/runtime/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/policy_bridge/**",
        "src/v7/alpha/runtime/**",
        "tests/v7/alpha/integration/runtime/**"
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
        "Feed expected-R and confidence to ranking/suppression surfaces.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/policy_bridge/**",
          "src/v7/alpha/runtime/**",
          "tests/v7/alpha/integration/runtime/**"
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
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/policy_bridge/**",
          "src/v7/alpha/runtime/**",
          "tests/v7/alpha/integration/runtime/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/policy_bridge/**",
        "src/v7/alpha/runtime/**",
        "tests/v7/alpha/integration/runtime/**"
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
        "Ensure risk blocks remain explicit and alpha cannot override hard gates.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/policy_bridge/**",
          "src/v7/alpha/runtime/**",
          "tests/v7/alpha/integration/runtime/**"
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
        "P7.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/policy_bridge/**",
          "src/v7/alpha/runtime/**",
          "tests/v7/alpha/integration/runtime/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/policy_bridge/**",
        "src/v7/alpha/runtime/**",
        "tests/v7/alpha/integration/runtime/**"
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
        "End-to-end AnalysisRequest -> alpha output -> DecisionEvent tests.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/policy_bridge/**",
          "src/v7/alpha/runtime/**",
          "tests/v7/alpha/integration/runtime/**"
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
  "phase": "P7",
  "title": "V7 Policy, Portfolio & Risk Integration",
  "model_name": "V7 AlphaForge XGB",
  "model_slug": "v7_alphaforge_xgb",
  "depends_on": [
    "P6"
  ],
  "next_phase": "P8",
  "scale_mode": "experimental_6",
  "requested_max_workers": 6,
  "expected_safe_parallelism": 3,
  "primary_focus": "Bridge alpha predictions into V7 policy/risk decision surfaces",
  "done_when": "Phase acceptance criteria pass and Part 3 JSON validates."
}
```


## 12. Review Hardening Requirements

* [ ] Every regime modifier writes explicit reason codes into AnalysisResult and DecisionEvent.
* [ ] Regime constraint level is one of ADVISORY, SOFT_BLOCK, HARD_BLOCK.
* [ ] Any TRANSITION-forced no-trade is visible as `regime_gate_forced_no_trade`.
* [ ] Any direction block is visible as `regime_blocked_direction`.
* [ ] Silent deterministic vetoes are forbidden.

---


<!-- SOURCE: phase_plans/P8__evaluation,_backtest,_paper_and_shadow_validation.md -->

# P8 — Evaluation, Backtest, Paper & Shadow Validation

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P8`  
**One-line goal:** Economic evaluation, no-trade quality, calibration quality, and shadow/paper readiness.  
**Why now:** Model promotion requires out-of-sample economic evidence, not raw accuracy or training metrics.  
**Blast radius:** src/v7/alpha/evaluation/**, src/v7/alpha/monitoring/**, reports/v7/alpha/**, tests/v7/alpha/integration/evaluation/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Scale mode:** `experimental_6`  
**Safe parallelism target:** `4`  
**Done when:** All workstreams pass acceptance criteria and phase JSON validates through Pi doctor.

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
| Primary focus | `Economic evaluation, no-trade quality, calibration quality, and shadow/paper readiness` |
| Product-code changes | `Allowed` |
| Selected scale mode | `experimental_6` |
| Requested max workers | `6` |
| Expected DAG effective parallelism | `4` |
| Expected safe effective parallelism | `4` |
| Worktree isolation | `Required` |
| Integration queue | `Required` |

### 1.1 RACI

| Workstream | R | A | C | I |
|---|---|---|---|---|
| All phase workstreams | Implementation Agent | Plan Owner | V7 Runtime/ML Reviewer | Maintainers |

---

## 2. Purpose

Model promotion requires out-of-sample economic evidence, not raw accuracy or training metrics.

This phase is part of the `V7 AlphaForge XGB` implementation. It must preserve V7's market-first, simulation-native, mode-scoped architecture. The phase must not introduce execution authority into the model layer, must not create a second hidden simulator, and must not use raw future returns as the production alpha truth when V7 simulation-derived R labels are required.

When scale mode is `experimental_6`, the executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

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
* [ ] Worktree isolation remains available when requested by scale mode.
* [ ] Integration queue remains enabled when required by scale mode.
* [ ] Global validation lock remains active for heavy validation.
* [ ] Completion gate hardening remains active.
* [ ] Merge conflicts produce handoff artifacts and do not mark the plan complete.
* [ ] The next plan does not start while the integration queue is dirty.
* [ ] `git push` remains forbidden.
* [ ] Raw destructive cleanup remains forbidden.
* [ ] Watch-mode validation remains forbidden.
* [ ] The executor remains the source of truth for state transitions.

---

## 4. Background / What Was Wrong

The existing V7 design defines mode-specific simulation semantics, hybrid model outputs, and runtime-owned execution boundaries. The new alpha generation system must align with those constraints instead of acting as an independent trading model.

The main missing capability is a V7-native alpha evidence layer that can train on 20 symbols, respect SWING / SCALP / AGGRESSIVE_SCALP semantics, emit calibrated XGBoost classification and regression surfaces, and expose R-native alpha scores to the V7 decision engine.

---

## 5. Current Failure State / Known Blockers

* `v7_alphaforge_xgb` = not implemented.
* `mode_specific_alpha_datasets` = not implemented until P4.
* `xgboost_alpha_artifacts` = not implemented until P5.
* `calibrated_alpha_score_builder` = not implemented until P6.
* `v7_policy_bridge` = not implemented until P7.
* `worktree_isolation` = enabled when selected scale mode requires it.
* `integration_queue` = enabled.
* `scale_mode_readiness` = pending Pi doctor review.
* `safe_effective_parallelism` = expected, not yet computed.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Future leakage enters feature rows | med | critical | Contract forbidden fields, leakage tests, timestamp checks |
| Alpha labels diverge from V7 simulation truth | med | critical | Use runtime simulation adapter only; golden tests |
| Raw XGBoost scores used as calibrated confidence | med | high | confidence_kind required; calibration tests |
| Mode datasets accidentally mixed | med | high | mode field and dataset-family validation |
| Safe parallelism lower than requested | med | med | Doctor warning; use safe batch preview |
| Merge conflict blocks plan | med | med | Handoff artifact and stop queue safely |
| Worktree path escapes `.pi/worktrees` | low | critical | Path scope checks; stop execution on escape |
| Cleanup deletes wrong files | low | critical | Raw destructive cleanup forbidden |

---

## 7. Workstreams

### 7.A — Walk-Forward Evaluation

**Goal:** Compute per-mode OOS R, drawdown, no-trade, and regret metrics.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Compute per-mode OOS R, drawdown, no-trade, and regret metrics.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream A may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.B — Ablations

**Goal:** Run primary-only, +context, +refinement, no-anomaly, classifier-only comparisons.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Run primary-only, +context, +refinement, no-anomaly, classifier-only comparisons.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream B may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.C — Paper/Shadow Harness

**Goal:** Record alpha decisions without live execution authority.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Record alpha decisions without live execution authority.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream C may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.D — Promotion Report

**Goal:** Compare candidate vs baseline and mark eligibility level.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Compare candidate vs baseline and mark eligibility level.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream D may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.

---

## 8. Combined Implementation Order

```text
Dependencies: P5, P6, P7
Batch 1: P8.A
Batch 2: P8.B + P8.C + P8.D, subject to same-file conflict review
Next phase: P9
```

Pi's computed approved graph is authoritative. Authored batches are only advisory. Continuous scheduling may run ready workspaces without waiting for batch barriers when safety constraints pass.

---

## 9. Definition of Done

`P8` is complete when ALL are true:

* [ ] All phase workstreams satisfy acceptance criteria.
* [ ] Relevant tests pass.
* [ ] No forbidden commands or files were used.
* [ ] No hidden fallback, hidden simulator, or future leakage was introduced.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation status is correct for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Future leakage detected.
* Simulation truth mismatch detected.
* Contract or schema validation fails.
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Dashboard or doctor reports misleading scale readiness.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Pause integration queue processing.
4. Preserve `.pi/worktrees/{planExecId}/` for debugging.
5. Revert phase workspaces independently.
6. Restore previous compatible config/schema/artifact bundle.
7. Rerun targeted validation and final integration validation.

---

## 11. What Next Phase Inherits

`P9` inherits:

* Completed outputs from `P8`.
* Worktree-aware execution contract.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Safe effective parallelism review.
* Workspace-level parallelism/isolation/integration/validation metadata.

---

# Part 2 — Agent Brief

## Mission

Implement `P8 — Evaluation, Backtest, Paper & Shadow Validation` for `V7 AlphaForge XGB` while preserving V7 runtime ownership, simulation-native labels, mode-specific datasets, explicit contracts, and safe Pi autonomous execution behavior.

## Hard Requirements

1. Do not create a second simulator.
2. Do not allow future data in features.
3. Do not use raw model scores as calibrated confidence.
4. Do not mix SWING, SCALP, and AGGRESSIVE_SCALP datasets unless explicitly building a report, not a model dataset.
5. Do not exceed selected scale-mode worker cap.
6. Do not run more than 3 workers unless worktree isolation and integration queue readiness pass.
7. Do not merge workspace output without passed workspace validation.
8. Do not mark a plan complete if integration validation fails.
9. Do not treat merge conflict as ordinary worker failure.
10. Do not start the next plan while integration queue state is dirty.
11. Do not run watch-mode validation.
12. Do not run `git push`.
13. Do not run raw destructive cleanup commands.
14. Do not access secrets or forbidden files.
15. The executor remains the only component that mutates execution state.

## Execution Policies

```yaml
scale:
  selected_mode: experimental_6
  max_parallel_workspaces: 6
worktree:
  enabled: true
  root: .pi/worktrees
  state_persistence_path: .pi/worktree-state.json
  crash_recovery_enabled: true
integration_queue:
  enabled: true
  process_one_merge_at_a_time: true
  stop_on_merge_conflict: true
  git_push_allowed: false
queue_optimization:
  enabled: true
  strategy: critical_path_first
validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true
```

## Safety Stops

Hard stop for dependency cycles, unapproved parallelism review, worktree path escape, raw destructive cleanup, integration validation failure, merge conflict without handoff, unsafe scale mode, forbidden file access, secrets access, `git push`, watch-mode validation, optimizer patch without approval, scope mismatch, and future leakage detection.

---

# Part 3 — Machine-Readable Execution Contract

```json
{
  "contractVersion": "2.5.1",
  "executionBackend": "postgres",
  "project": {
    "name": "v7-alphaforge-xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p8"
    ]
  },
  "planExecution": {
    "phase": "P8",
    "title": "Evaluation, Backtest, Paper & Shadow Validation",
    "mode": "autonomous",
    "maxParallelWorkspaces": 6,
    "scheduling": {
      "continuous": true,
      "slotCount": 6,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": true,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "experimental_6",
      "selectedMode": "experimental_6",
      "modes": {
        "stable_3": {
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false
        },
        "experimental_6": {
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true
        },
        "scale_8": {
          "maxParallelWorkspaces": 8,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "dogfoodPassRequired": true,
          "explicitApprovalRequired": true
        }
      }
    },
    "worktree": {
      "enabled": true,
      "enabledByDefault": true,
      "root": ".pi/worktrees",
      "prewarmCount": 6,
      "statePersistencePath": ".pi/worktree-state.json",
      "crashRecoveryEnabled": true,
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true,
      "diffPreservationPath": ".pi/executions/{planExecId}/worktrees/{wsId}.patch"
    },
    "integrationQueue": {
      "enabled": true,
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
        "strategy": "critical_path_first",
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
        "markdown_fallback"
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
      "scope_mismatch",
      "future_leakage_detected"
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
    "requestedMaxParallelWorkspaces": 6,
    "selectedScaleMode": "experimental_6",
    "scaleModeReadiness": {
      "ready": true,
      "blockedReasons": [],
      "warnings": [],
      "prerequisites": [
        {
          "key": "worktree_isolation",
          "required": true,
          "met": true,
          "message": "Required for experimental_6 and scale_8."
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
    "expectedDagEffectiveParallelismMin": 4,
    "expectedSafeEffectiveParallelismMin": 4,
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
      "worktree_state"
    ]
  },
  "workspaces": [
    {
      "id": "P8.A",
      "title": "Walk-Forward Evaluation",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
      "parallelism": {
        "expectedBatch": "batch_1",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/evaluation/**",
          "src/v7/alpha/monitoring/**",
          "reports/v7/alpha/**",
          "tests/v7/alpha/integration/evaluation/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/evaluation/**",
        "src/v7/alpha/monitoring/**",
        "reports/v7/alpha/**",
        "tests/v7/alpha/integration/evaluation/**"
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
        "Compute per-mode OOS R, drawdown, no-trade, and regret metrics.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/evaluation/**",
          "src/v7/alpha/monitoring/**",
          "reports/v7/alpha/**",
          "tests/v7/alpha/integration/evaluation/**"
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
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [
          "P8.C",
          "P8.D"
        ],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/evaluation/**",
          "src/v7/alpha/monitoring/**",
          "reports/v7/alpha/**",
          "tests/v7/alpha/integration/evaluation/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/evaluation/**",
        "src/v7/alpha/monitoring/**",
        "reports/v7/alpha/**",
        "tests/v7/alpha/integration/evaluation/**"
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
        "Run primary-only, +context, +refinement, no-anomaly, classifier-only comparisons.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/evaluation/**",
          "src/v7/alpha/monitoring/**",
          "reports/v7/alpha/**",
          "tests/v7/alpha/integration/evaluation/**"
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
      "dependencies": [
        "P8.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/evaluation/**",
          "src/v7/alpha/monitoring/**",
          "reports/v7/alpha/**",
          "tests/v7/alpha/integration/evaluation/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/evaluation/**",
        "src/v7/alpha/monitoring/**",
        "reports/v7/alpha/**",
        "tests/v7/alpha/integration/evaluation/**"
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
        "Record alpha decisions without live execution authority.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/evaluation/**",
          "src/v7/alpha/monitoring/**",
          "reports/v7/alpha/**",
          "tests/v7/alpha/integration/evaluation/**"
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
        "P8.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/evaluation/**",
          "src/v7/alpha/monitoring/**",
          "reports/v7/alpha/**",
          "tests/v7/alpha/integration/evaluation/**"
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/evaluation/**",
        "src/v7/alpha/monitoring/**",
        "reports/v7/alpha/**",
        "tests/v7/alpha/integration/evaluation/**"
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
        "Compare candidate vs baseline and mark eligibility level.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/evaluation/**",
          "src/v7/alpha/monitoring/**",
          "reports/v7/alpha/**",
          "tests/v7/alpha/integration/evaluation/**"
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
  "phase": "P8",
  "title": "Evaluation, Backtest, Paper & Shadow Validation",
  "model_name": "V7 AlphaForge XGB",
  "model_slug": "v7_alphaforge_xgb",
  "depends_on": [
    "P5",
    "P6",
    "P7"
  ],
  "next_phase": "P9",
  "scale_mode": "experimental_6",
  "requested_max_workers": 6,
  "expected_safe_parallelism": 4,
  "primary_focus": "Economic evaluation, no-trade quality, calibration quality, and shadow/paper readiness",
  "done_when": "Phase acceptance criteria pass and Part 3 JSON validates."
}
```


## 12. Review Hardening Requirements

* [ ] Evaluation proves anomaly features were generated by fold-scoped artifacts.
* [ ] Ablation includes model with and without anomaly/regime features.
* [ ] Evaluation reports regime-forced no-trade share vs model-preferred no-trade share.
* [ ] Interval consistency test verifies SCALP primary=1h throughout simulation, labels, datasets, and inference.

---


<!-- SOURCE: phase_plans/P9__deployment,_monitoring,_drift,_promotion_and_rollback.md -->

# P9 — Deployment, Monitoring, Drift, Promotion & Rollback

# Part 1 — Phase Plan

## 0. TL;DR / Compact Mental Model

**Phase:** `P9`  
**One-line goal:** Deployment safety, drift monitoring, kill switch, rollback bundles, and live eligibility gates.  
**Why now:** The alpha system must be operated safely with visible drift, explicit rollback, and per-mode promotion authority.  
**Blast radius:** src/v7/alpha/monitoring/**, src/v7/alpha/deployment/**, configs/v7/alpha/**, docs/v7/alpha/**, tests/v7/alpha/regression/**  
**Rollback path:** Revert this phase's workspaces, restore previous compatible alpha config/schema/artifact bundle, and rerun targeted + final validation.  
**Scale mode:** `stable_3`  
**Safe parallelism target:** `2`  
**Done when:** All workstreams pass acceptance criteria and phase JSON validates through Pi doctor.

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
| Primary focus | `Deployment safety, drift monitoring, kill switch, rollback bundles, and live eligibility gates` |
| Product-code changes | `Allowed` |
| Selected scale mode | `stable_3` |
| Requested max workers | `3` |
| Expected DAG effective parallelism | `3` |
| Expected safe effective parallelism | `2` |
| Worktree isolation | `Optional` |
| Integration queue | `Required` |

### 1.1 RACI

| Workstream | R | A | C | I |
|---|---|---|---|---|
| All phase workstreams | Implementation Agent | Plan Owner | V7 Runtime/ML Reviewer | Maintainers |

---

## 2. Purpose

The alpha system must be operated safely with visible drift, explicit rollback, and per-mode promotion authority.

This phase is part of the `V7 AlphaForge XGB` implementation. It must preserve V7's market-first, simulation-native, mode-scoped architecture. The phase must not introduce execution authority into the model layer, must not create a second hidden simulator, and must not use raw future returns as the production alpha truth when V7 simulation-derived R labels are required.

When scale mode is `stable_3`, the executor should optimize for safe effective parallelism, not maximum concurrency. Worktree isolation, integration queue, validation locks, and completion gates remain mandatory whenever more than three workers are requested.

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
* [ ] Worktree isolation remains available when requested by scale mode.
* [ ] Integration queue remains enabled when required by scale mode.
* [ ] Global validation lock remains active for heavy validation.
* [ ] Completion gate hardening remains active.
* [ ] Merge conflicts produce handoff artifacts and do not mark the plan complete.
* [ ] The next plan does not start while the integration queue is dirty.
* [ ] `git push` remains forbidden.
* [ ] Raw destructive cleanup remains forbidden.
* [ ] Watch-mode validation remains forbidden.
* [ ] The executor remains the source of truth for state transitions.

---

## 4. Background / What Was Wrong

The existing V7 design defines mode-specific simulation semantics, hybrid model outputs, and runtime-owned execution boundaries. The new alpha generation system must align with those constraints instead of acting as an independent trading model.

The main missing capability is a V7-native alpha evidence layer that can train on 20 symbols, respect SWING / SCALP / AGGRESSIVE_SCALP semantics, emit calibrated XGBoost classification and regression surfaces, and expose R-native alpha scores to the V7 decision engine.

---

## 5. Current Failure State / Known Blockers

* `v7_alphaforge_xgb` = not implemented.
* `mode_specific_alpha_datasets` = not implemented until P4.
* `xgboost_alpha_artifacts` = not implemented until P5.
* `calibrated_alpha_score_builder` = not implemented until P6.
* `v7_policy_bridge` = not implemented until P7.
* `worktree_isolation` = enabled when selected scale mode requires it.
* `integration_queue` = enabled.
* `scale_mode_readiness` = pending Pi doctor review.
* `safe_effective_parallelism` = expected, not yet computed.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Future leakage enters feature rows | med | critical | Contract forbidden fields, leakage tests, timestamp checks |
| Alpha labels diverge from V7 simulation truth | med | critical | Use runtime simulation adapter only; golden tests |
| Raw XGBoost scores used as calibrated confidence | med | high | confidence_kind required; calibration tests |
| Mode datasets accidentally mixed | med | high | mode field and dataset-family validation |
| Safe parallelism lower than requested | med | med | Doctor warning; use safe batch preview |
| Merge conflict blocks plan | med | med | Handoff artifact and stop queue safely |
| Worktree path escapes `.pi/worktrees` | low | critical | Path scope checks; stop execution on escape |
| Cleanup deletes wrong files | low | critical | Raw destructive cleanup forbidden |

---

## 7. Workstreams

### 7.A — Monitoring Surfaces

**Goal:** Track confidence, expected-R, action mix, no-trade rate, drift, finality lag.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Track confidence, expected-R, action mix, no-trade rate, drift, finality lag.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream A may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.B — Promotion Registry

**Goal:** Store per-mode model/calibration/policy bundle eligibility.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Store per-mode model/calibration/policy bundle eligibility.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream B may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.C — Rollback Playbook

**Goal:** Revert compatible artifact bundles per mode.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Revert compatible artifact bundles per mode.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream C may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.
### 7.D — Live Eligibility Gate

**Goal:** Require paper/shadow evidence, kill switch, and baseline comparison.

**Requirements:**
* Must preserve V7 contract boundaries.
* Must avoid hidden fallbacks and future leakage.
* Must keep all thresholds and behavior config-driven.

**Acceptance Criteria:**
* Require paper/shadow evidence, kill switch, and baseline comparison.
* Tests are added or updated.
* The phase contract remains valid JSON.

**Isolation & Parallelism Notes:**
* Workstream D may run in an isolated worktree.
* Same-file edits must not run concurrently unless Pi optimizer approves a split.
* Workspace validation is required before integration queue entry.

---

## 8. Combined Implementation Order

```text
Dependencies: P8
Batch 1: P9.A
Batch 2: P9.B + P9.C + P9.D, subject to same-file conflict review
Next phase: NONE
```

Pi's computed approved graph is authoritative. Authored batches are only advisory. Continuous scheduling may run ready workspaces without waiting for batch barriers when safety constraints pass.

---

## 9. Definition of Done

`P9` is complete when ALL are true:

* [ ] All phase workstreams satisfy acceptance criteria.
* [ ] Relevant tests pass.
* [ ] No forbidden commands or files were used.
* [ ] No hidden fallback, hidden simulator, or future leakage was introduced.
* [ ] DAG batch preview has been reviewed if required.
* [ ] Safe batch preview has been reviewed if required.
* [ ] Selected scale mode readiness passes.
* [ ] Worktree isolation status is correct for selected scale mode.
* [ ] Integration queue status is clean or intentionally blocked with handoff.
* [ ] Validation gates passed.
* [ ] Typecheck/build/test requirements passed where applicable.

---

## 10. Rollback Playbook

**Trigger conditions:**
* Future leakage detected.
* Simulation truth mismatch detected.
* Contract or schema validation fails.
* Worktree creation or cleanup behaves unsafely.
* Integration queue merges incorrect or unvalidated diffs.
* Merge conflicts are not detected or no handoff artifact is produced.
* Safe scale mode causes resource exhaustion or state corruption.
* Dashboard or doctor reports misleading scale readiness.

**Rollback procedure:**
1. Set scale mode to `stable_3`.
2. Set `maxParallelWorkspaces` to `3` or lower.
3. Pause integration queue processing.
4. Preserve `.pi/worktrees/{planExecId}/` for debugging.
5. Revert phase workspaces independently.
6. Restore previous compatible config/schema/artifact bundle.
7. Rerun targeted validation and final integration validation.

---

## 11. What Next Phase Inherits

`NONE` inherits:

* Completed outputs from `P9`.
* Worktree-aware execution contract.
* Scale-mode-aware validation rules.
* Integration queue requirements.
* Safe effective parallelism review.
* Workspace-level parallelism/isolation/integration/validation metadata.

---

# Part 2 — Agent Brief

## Mission

Implement `P9 — Deployment, Monitoring, Drift, Promotion & Rollback` for `V7 AlphaForge XGB` while preserving V7 runtime ownership, simulation-native labels, mode-specific datasets, explicit contracts, and safe Pi autonomous execution behavior.

## Hard Requirements

1. Do not create a second simulator.
2. Do not allow future data in features.
3. Do not use raw model scores as calibrated confidence.
4. Do not mix SWING, SCALP, and AGGRESSIVE_SCALP datasets unless explicitly building a report, not a model dataset.
5. Do not exceed selected scale-mode worker cap.
6. Do not run more than 3 workers unless worktree isolation and integration queue readiness pass.
7. Do not merge workspace output without passed workspace validation.
8. Do not mark a plan complete if integration validation fails.
9. Do not treat merge conflict as ordinary worker failure.
10. Do not start the next plan while integration queue state is dirty.
11. Do not run watch-mode validation.
12. Do not run `git push`.
13. Do not run raw destructive cleanup commands.
14. Do not access secrets or forbidden files.
15. The executor remains the only component that mutates execution state.

## Execution Policies

```yaml
scale:
  selected_mode: stable_3
  max_parallel_workspaces: 3
worktree:
  enabled: false
  root: .pi/worktrees
  state_persistence_path: .pi/worktree-state.json
  crash_recovery_enabled: true
integration_queue:
  enabled: true
  process_one_merge_at_a_time: true
  stop_on_merge_conflict: true
  git_push_allowed: false
queue_optimization:
  enabled: true
  strategy: critical_path_first
validation:
  global_validation_lock_required: true
  targeted_validation_enabled: true
  final_integration_validation_required: true
  watch_mode_forbidden: true
```

## Safety Stops

Hard stop for dependency cycles, unapproved parallelism review, worktree path escape, raw destructive cleanup, integration validation failure, merge conflict without handoff, unsafe scale mode, forbidden file access, secrets access, `git push`, watch-mode validation, optimizer patch without approval, scope mismatch, and future leakage detection.

---

# Part 3 — Machine-Readable Execution Contract

```json
{
  "contractVersion": "2.5.1",
  "executionBackend": "postgres",
  "project": {
    "name": "v7-alphaforge-xgb",
    "rootPath": ".",
    "type": "repo",
    "tags": [
      "v7",
      "alpha",
      "xgboost",
      "p9"
    ]
  },
  "planExecution": {
    "phase": "P9",
    "title": "Deployment, Monitoring, Drift, Promotion & Rollback",
    "mode": "autonomous",
    "maxParallelWorkspaces": 3,
    "scheduling": {
      "continuous": true,
      "slotCount": 3,
      "priorityStrategy": "critical_path_first"
    },
    "stateBackend": "postgres",
    "jsonFallbackEnabled": true,
    "dashboardEnabled": true,
    "autoCommit": true,
    "autoPush": false,
    "scale": {
      "defaultMode": "experimental_6",
      "selectedMode": "stable_3",
      "modes": {
        "stable_3": {
          "maxParallelWorkspaces": 3,
          "worktreeRequired": false,
          "integrationQueueRequired": false
        },
        "experimental_6": {
          "maxParallelWorkspaces": 6,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true
        },
        "scale_8": {
          "maxParallelWorkspaces": 8,
          "worktreeRequired": true,
          "integrationQueueRequired": true,
          "validationLockRequired": true,
          "archiveRequired": true,
          "completionGateRequired": true,
          "dogfoodPassRequired": true,
          "explicitApprovalRequired": true
        }
      }
    },
    "worktree": {
      "enabled": false,
      "enabledByDefault": false,
      "root": ".pi/worktrees",
      "prewarmCount": 3,
      "statePersistencePath": ".pi/worktree-state.json",
      "crashRecoveryEnabled": true,
      "quarantineFailedByDefault": true,
      "rawRmRfForbidden": true,
      "pathScopeRequired": true,
      "diffPreservationPath": ".pi/executions/{planExecId}/worktrees/{wsId}.patch"
    },
    "integrationQueue": {
      "enabled": true,
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
        "strategy": "critical_path_first",
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
        "markdown_fallback"
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
      "scope_mismatch",
      "future_leakage_detected"
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
          "required": false,
          "met": true,
          "message": "Required for experimental_6 and scale_8."
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
    "expectedDagEffectiveParallelismMin": 3,
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
      "worktree_state"
    ]
  },
  "workspaces": [
    {
      "id": "P9.A",
      "title": "Monitoring Surfaces",
      "dependencies": [],
      "parallelGroup": "batch_1",
      "dependencyReason": "Foundation workspace for this phase.",
      "parallelism": {
        "expectedBatch": "batch_1",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/monitoring/**",
          "src/v7/alpha/deployment/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**",
          "tests/v7/alpha/regression/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
      },
      "worktree": {
        "required": false,
        "isolationMode": "shared_or_worktree",
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/monitoring/**",
        "src/v7/alpha/deployment/**",
        "configs/v7/alpha/**",
        "docs/v7/alpha/**",
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
        "Track confidence, expected-R, action mix, no-trade rate, drift, finality lag.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/monitoring/**",
          "src/v7/alpha/deployment/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**",
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
    },
    {
      "id": "P9.B",
      "title": "Promotion Registry",
      "dependencies": [
        "P9.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [
          "P9.C",
          "P9.D"
        ],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/monitoring/**",
          "src/v7/alpha/deployment/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**",
          "tests/v7/alpha/regression/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
      },
      "worktree": {
        "required": false,
        "isolationMode": "shared_or_worktree",
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/monitoring/**",
        "src/v7/alpha/deployment/**",
        "configs/v7/alpha/**",
        "docs/v7/alpha/**",
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
        "Store per-mode model/calibration/policy bundle eligibility.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/monitoring/**",
          "src/v7/alpha/deployment/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**",
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
    },
    {
      "id": "P9.C",
      "title": "Rollback Playbook",
      "dependencies": [
        "P9.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/monitoring/**",
          "src/v7/alpha/deployment/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**",
          "tests/v7/alpha/regression/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
      },
      "worktree": {
        "required": false,
        "isolationMode": "shared_or_worktree",
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/monitoring/**",
        "src/v7/alpha/deployment/**",
        "configs/v7/alpha/**",
        "docs/v7/alpha/**",
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
        "Revert compatible artifact bundles per mode.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/monitoring/**",
          "src/v7/alpha/deployment/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**",
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
    },
    {
      "id": "P9.D",
      "title": "Live Eligibility Gate",
      "dependencies": [
        "P9.A"
      ],
      "parallelGroup": "batch_2",
      "dependencyReason": "Depends on phase-local foundation workstream A to establish shared contracts or base modules.",
      "parallelism": {
        "expectedBatch": "batch_2",
        "canRunWith": [],
        "cannotRunWith": [],
        "conflictScope": [
          "src/v7/alpha/monitoring/**",
          "src/v7/alpha/deployment/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**",
          "tests/v7/alpha/regression/**"
        ],
        "sameFileParallelismAllowed": false,
        "safeParallelismNotes": "Use worktree isolation. Same-file edits should not run concurrently unless Pi optimizer explicitly approves a split."
      },
      "worktree": {
        "required": false,
        "isolationMode": "shared_or_worktree",
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
        "watchModeForbidden": true
      },
      "allowedFiles": [
        "src/v7/alpha/monitoring/**",
        "src/v7/alpha/deployment/**",
        "configs/v7/alpha/**",
        "docs/v7/alpha/**",
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
        "Require paper/shadow evidence, kill switch, and baseline comparison.",
        "Relevant unit/integration tests pass.",
        "No hidden fallback or future leakage introduced."
      ],
      "targetCommand": "pytest tests/v7/alpha -q",
      "roleBudget": "worker",
      "maxRetries": 3,
      "riskLevel": "high",
      "capabilityManifest": {
        "canEdit": [
          "src/v7/alpha/monitoring/**",
          "src/v7/alpha/deployment/**",
          "configs/v7/alpha/**",
          "docs/v7/alpha/**",
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
  "phase": "P9",
  "title": "Deployment, Monitoring, Drift, Promotion & Rollback",
  "model_name": "V7 AlphaForge XGB",
  "model_slug": "v7_alphaforge_xgb",
  "depends_on": [
    "P8"
  ],
  "next_phase": "NONE",
  "scale_mode": "stable_3",
  "requested_max_workers": 3,
  "expected_safe_parallelism": 2,
  "primary_focus": "Deployment safety, drift monitoring, kill switch, rollback bundles, and live eligibility gates",
  "done_when": "Phase acceptance criteria pass and Part 3 JSON validates."
}
```


## 12. Review Hardening Requirements

* [ ] Monitoring exposes anomaly feature drift by artifact family and fold lineage.
* [ ] Monitoring exposes regime-forced vs model-preferred no-trade rates.
* [ ] Symbol universe changes are blocked unless feature schema or encoding-family version changes are approved.
* [ ] Promotion gate fails if any interval mismatch or anomaly leakage check fails.

---

