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
