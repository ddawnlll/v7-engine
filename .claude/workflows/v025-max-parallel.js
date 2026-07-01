export const meta = {
  name: 'v025-max-parallel',
  description: 'Max-parallel execution of all 25 P0-P3 AlphaForge diagnostics issues',
  phases: [
    { title: 'P0 Core Fixes', detail: '5 measurement bug fixes (critical path)' },
    { title: 'P1 Implementation', detail: '9 feature implementations' },
    { title: 'P2-P3 Deep', detail: '11 remaining issues' },
    { title: 'Sync & Verify', detail: 'Merge worktrees and run integration tests' },
  ],
}

// ─── ALL 25 ISSUES ────────────────────────────────────────────────────────
// P0: measurement bugs — independent, all run concurrently
// P1: feature impls — no code dependency on P0 (output dependency only)
// P2: diagnostics fixes — standalone
// P3: research backlog — lowest priority

const ALL = [
  // ═══ P0 — Measurement Layer Fixes (WAVE 1) ═══
  {
    num: 125, prio: 'P0',
    title: `6-Fold WFV Enforcement`,
    keyFiles: `alphaforge/src/validation/`,
    detail: `WFV minimum 6 fold with ANCHORED expanding window. Each fold: train/val/OOS metrics, fold stability score, majority fold PASS criteria. Apply embargo + purge correctly. Overfit detection per fold. Add comprehensive tests.`,
  },
  {
    num: 129, prio: 'P0',
    title: `Labels bypass SimulationOutput — generate_labels() must call simulate() instead of reimplementing from OHLCV`,
    keyFiles: `alphaforge/src/label_engine/`,
    detail: `Fix generate_labels() to call simulation engine simulate() instead of reimplementing from raw OHLCV. Labels must include: best_action_label with AMBIGUOUS_STATE, no_trade_quality classification (4 types), label_validity flag, cost decomposition (fee_r, slippage_r), funding_status: DEFERRED. Return type must be LabelDatasetSpec-compatible. All existing tests must pass.`,
  },
  {
    num: 130, prio: 'P0',
    title: `WFV simulates trades instead of measuring prediction quality`,
    keyFiles: `alphaforge/src/validation/walk_forward.py`,
    detail: `Remove all simulate_path() calls from walk_forward_validate(). WFV must consume pre-computed R values from labels, not re-simulate. Report: accuracy, confusion matrix, logloss, feature importance, per-fold R expectancy from label data. Zero trade simulation code in AlphaForge validation.`,
  },
  {
    num: 131, prio: 'P0',
    title: `Per-fold field name mismatch — verdict always REJECT`,
    keyFiles: `alphaforge/src/reporting/ alphaforge/src/validation/`,
    detail: `Fix field name mismatch between writer and reader. Ensure _fold_metrics_present() returns True when per-fold data exists. Verdict must reflect actual model performance (PASS if edge, REJECT if none). All schema validation tests must pass.`,
  },

  // ═══ P0.5 ═══
  {
    num: 126, prio: 'P0.5',
    title: `Report Consistency + Stale Placeholder Text Repair`,
    keyFiles: `alphaforge/src/reporting/`,
    detail: `Fix: edge yok ama edge_only_in_rare_regime=true, single symbol limitation yaziyor ama 10 symbol var, duplicate report_id, cost stress fail ama stress levels bos, placeholder text uretimi. Ensure report_id uniqueness, stale text removal, regime verdict consistency, cost stress empty-level handling.`,
  },

  // ═══ P1 — Feature Implementations (WAVE 1-2) ═══
  {
    num: 127, prio: 'P1',
    title: `Research Artifact Registry + Canonical Run Index`,
    keyFiles: `alphaforge/src/ (new file: research_run_index.json builder)`,
    detail: `Single index file: alphaforge_report/research_run_index.json. Fields: run_id, mode, timestamp, canonical_report_path, candidate_count, trial_count, verdict, artifact paths, superseded reports, duplicate reports. Update on every run. Clear canonical vs superseded distinction.`,
  },
  {
    num: 128, prio: 'P1',
    title: `Feature/Label Leakage + Causality Audit`,
    keyFiles: `alphaforge/src/ (read-only audit)`,
    detail: `AUDIT ONLY — no code changes. Check: features using future data, label/feature timestamp separation, WFV purge/embargo correctness, cross-symbol lead-lag leakage, feature pipeline staying in canonical state, roll/ewm lookahead. Produce audit report.`,
  },
  {
    num: 132, prio: 'P1',
    title: `V7HandoffPackage not produced — no G0-G10 gate evidence delivery`,
    keyFiles: `alphaforge/src/handoff/`,
    detail: `Assemble V7HandoffPackage from ModeResearchReport + metadata. All 11 gates mapped with evidence references. Full lineage chain. Recommended status matches verdict. Schema validation passes.`,
  },
  {
    num: 133, prio: 'P1',
    title: `AlphaForgeResearchReport not implemented — missing cross-mode aggregate report`,
    keyFiles: `alphaforge/src/reporting/`,
    detail: `Builder consumes 3 ModeResearchReports. Promoted/rejected candidates listed with evidence. Global limitations documented. V7HandoffPackage references included. Schema validation passes.`,
  },
  {
    num: 134, prio: 'P1',
    title: `Regime breakdown is placeholder — G4 gate has no real regime detection`,
    keyFiles: `alphaforge/src/regime/`,
    detail: `Regime detection computing TREND_UP/DOWN/RANGE/TRANSITION from OHLCV. Per-regime OOS expectancy from label data. Rare regime check and flag. Symbol × regime stability matrix.`,
  },

  // ═══ P2 — Diagnostics Fixes (WAVE 2-3) ═══
  {
    num: 135, prio: 'P2',
    title: `Alpha thesis lifecycle not implemented — no state machine`,
    keyFiles: `alphaforge/src/`,
    detail: `State machine with all 8 states (PROPOSED→REJECTED, PROPOSED→ACTIVE→PENDING_REVIEW→V7_CANDIDATE→PROMOTED, etc.). Entry/exit conditions per state. Rejection criteria tracking. Integration with WFV pipeline.`,
  },
  {
    num: 136, prio: 'P2',
    title: `CalibrationCandidate not produced — G6 gate empty`,
    keyFiles: `alphaforge/src/calibration/`,
    detail: `CalibrationCandidate produced after training. ECE, MCE, confidence bins reported. Calibration status assigned. Per-fold degradation tracked. Schema validation passes.`,
  },
  {
    num: 137, prio: 'P2',
    title: `Cost stress uses blended fee+slippage multiplier instead of independent dimensions`,
    keyFiles: `alphaforge/src/validation/`,
    detail: `Independent fee stress (1.5x, 2x, 3x). Independent slippage stress (1.5x, 2x, 3x). Spread sensitivity (1.5x, 2x). Combined worst-case stress. Break-even cost calculation.`,
  },
  {
    num: 138, prio: 'P2',
    title: `MHT pipeline/builder contradiction — NONE_APPLIED vs Bonferroni conflict`,
    keyFiles: `alphaforge/src/validation/`,
    detail: `Pipeline and builder must agree on correction_method. PBO assessment when sufficient data. Deflated Sharpe from actual data. blocking_hold when NONE_APPLIED. rejected_candidate_count tracks actual rejections.`,
  },
  {
    num: 139, prio: 'P2',
    title: `Mode-specific purge/embargo not implemented — all modes use same formula`,
    keyFiles: `alphaforge/src/config/`,
    detail: `SCALP: purge=100, embargo=50. AGGRESSIVE_SCALP: purge=200, embargo=100. SWING: purge=20, embargo=10. Mode-specific defaults in MODE_CONFIG.`,
  },

  // ═══ P3 — Backlog Research (WAVE 3) ═══
  {
    num: 140, prio: 'P3',
    title: `SHAP + Feature Ablation Framework`,
    keyFiles: `alphaforge/src/research/`,
    detail: `SHAP values computed per fold. Top-5 features reported in ModeResearchReport. Ablation results: per-group accuracy delta. Noise features flagged for removal.`,
  },
  {
    num: 141, prio: 'P3',
    title: `Funding Rate Feature Integration`,
    keyFiles: `alphaforge/src/features/`,
    detail: `3+ funding features in pipeline. Ablation: funding features improve OOS expectancy. DEFERRED block removed after validation.`,
  },
  {
    num: 142, prio: 'P3',
    title: `Order Book Microstructure Expansion`,
    keyFiles: `alphaforge/src/features/`,
    detail: `5+ new microstructure features. Ablation: microstructure improves OOS. SCALP/AGGRESSIVE_SCALP specific.`,
  },
  {
    num: 143, prio: 'P3',
    title: `Multi-Timeframe Alpha Tuning`,
    keyFiles: `alphaforge/src/`,
    detail: `SCALP full pipeline operational. AGGRESSIVE_SCALP full pipeline operational. Cross-timeframe edge comparison. Thresholds updated with empirical evidence.`,
  },
  {
    num: 144, prio: 'P3',
    title: `Model Evolution Research — XGBoost vs LSTM vs Transformer`,
    keyFiles: `alphaforge/src/research/`,
    detail: `2+ alternative architectures implemented. Head-to-head on identical data. Best architecture per mode. Inference cost benchmark.`,
  },
]

// ─── WORKFLOW ──────────────────────────────────────────────────────────────

phase('P0 Core Fixes')
log(`Launching ${ALL.length} issues across 10 concurrent slots via pipeline`)

// Pipeline: each item flows independently through stages
// Stage 1: implement in worktree
// Stage 2: verify (runs as soon as stage 1 finishes for that item)
// Items start immediately as slots free up — NO BARRIERS

const completed = await pipeline(
  ALL,

  // Stage 1: Implement
  async (issue) => {
    const prompt = `You are implementing GitHub issue #${issue.num} (${issue.prio}) in the v7-engine repo.

TITLE: ${issue.title}

KEY FILES: ${issue.keyFiles}

REQUIREMENTS:
${issue.detail}

TASK:
1. Read the relevant source files in ${issue.keyFiles}
2. Understand the current implementation
3. Implement the fix/feature according to the requirements
4. Run: PYTHONPATH=. python3 -m pytest alphaforge/tests/ -q -x --timeout=60
5. Run: PYTHONPATH=. python3 -m pytest integration/tests/ -q -x --timeout=60
6. Run: PYTHONPATH=. python3 -m pytest lib/tests/ simulation/tests/ -q -x --timeout=60
7. Fix any test failures
8. Commit with message: "feat: #${issue.num} ${issue.title.split(' — ')[0]}"

IMPORTANT:
- Work in this worktree, do not touch other branches
- Preserve existing code unless it conflicts with the requirements
- Follow existing patterns in the codebase
- ALL existing tests MUST pass after your changes
- Add new tests for the new functionality
- Report what you changed, what tests passed/failed`

    const result = await agent(prompt, {
      label: `#${issue.num}`,
      phase: issue.prio.startsWith('P0') ? 'P0 Core Fixes'
           : issue.prio.startsWith('P1') ? 'P1 Implementation'
           : 'P2-P3 Deep',
      isolation: 'worktree',
      model: 'haiku',
    })
    return { issue, result, status: result ? 'done' : 'skipped' }
  },
)

// ─── FILTER RESULTS ─────────────────────────────────────────────────────
const succeeded = completed.filter(r => r && r.status === 'done')
const failed = completed.filter(r => r && r.status === 'skipped')
const total = ALL.length
const done = succeeded.length
const pct = Math.round(done / total * 100)

log(`Progress: ${done}/${total} (${pct}%) — ${failed.length} skipped`)

// ─── SYNC & VERIFY ──────────────────────────────────────────────────────
phase('Sync & Verify')
log('Syncing all worktree commits to main...')

const syncResult = await agent(`
All worktree implementations are complete. Now:

1. Run the auto-sync script: bash .claude/skills/sync-worktrees.sh
2. Verify sync: git log --oneline -5
3. Run full test suite: PYTHONPATH=. python3 -m pytest alphaforge/tests/ integration/tests/ lib/tests/ simulation/tests/ -q --ignore=lib/tests/test_market_data_binance.py --timeout=120
4. Report results: how many passed, how many failed, any regressions
5. If any tests fail, report which ones and why
`, { label: 'sync+verify', phase: 'Sync & Verify', model: 'fable' })

return {
  total_issues: total,
  completed: done,
  failed: failed.length,
  completion_pct: pct,
  sync_result: syncResult,
}
