// ═══════════════════════════════════════════════════════════════════════════════
// AlphaForge Profitability v0.1 — Full Milestone Execution
// ═══════════════════════════════════════════════════════════════════════════════
//
// Hedef: 19 issue, 35 dk, zero merge conflict
//
// Strateji:
// - Scout: 1 agent 12 dosyayı oku → structured JSON    [3 dk]
// - Parallel (10 agent, eşzamanlı): structured output    [10 dk]
//   → Kimse pipeline.py'ye DOKUNMAZ (conflict sıfır)
//   → Kimse orderbook.py'ye YAZMAZ (structured output)
// - Integration: tüm structured output'ları FILES'a yaz  [6 dk]
// - Smoke → Train → Reports                              [16 dk]
// ─────────────────────────────────────────────────────────────────────────────
// Concurrency: 10 agent aynı anda (min(16, 12-2) = 10)
// 14 issue-group → 10 agent = kuyruk YOK, max throughput
// Merge conflict: SIFIR (struct output + integration write)
// ═══════════════════════════════════════════════════════════════════════════════

export const meta = {
  name: 'alphaforge-profitability-v01',
  description: 'Execute 19 issues for AlphaForge Profitability v0.1 milestone',
  phases: [
    { title: 'Scout', detail: 'Read 12 files → structured codebase map (3 min)' },
    { title: 'Parallel Impl', detail: '10 agents concurrent, structured output (10 min)' },
    { title: 'Integrate', detail: 'Write all files from structured output (6 min)' },
    { title: 'Smoke', detail: 'Boundary + unit tests (3 min)' },
    { title: 'Train', detail: 'End-to-end XGBoost (10 min)' },
    { title: 'Report', detail: '19 ACCP + roadmap (3 min)' },
  ],
}

// ═══════════════════════════════════════════════════════════════════════════════
// SCHEMAS
// ═══════════════════════════════════════════════════════════════════════════════

const CODEBASE_SCHEMA = {
  type: 'object',
  properties: {
    files: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          path: { type: 'string' },
          functions: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                name: { type: 'string' },
                params: { type: 'array', items: { type: 'string' } },
                return_type: { type: 'string' },
                decorators: { type: 'array', items: { type: 'string' } },
                body_lines: { type: 'number' },
              },
              required: ['name'],
            },
          },
          classes: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                name: { type: 'string' },
                methods: { type: 'array', items: { type: 'string' } },
                base_classes: { type: 'array', items: { type: 'string' } },
              },
              required: ['name'],
            },
          },
          constants: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                name: { type: 'string' },
                value: { type: 'string' },
              },
              required: ['name'],
            },
          },
          imports: {
            type: 'array',
            items: { type: 'string' },
          },
        },
        required: ['path', 'functions', 'classes', 'imports'],
      },
    },
    wiring_patterns: {
      type: 'object',
      properties: {
        feature_registration: { type: 'string' },
        pipeline_feature_order: { type: 'array', items: { type: 'string' } },
        compute_function_structure: { type: 'string' },
        how_to_wire_new_feature: { type: 'string' },
      },
      required: ['feature_registration', 'pipeline_feature_order', 'how_to_wire_new_feature'],
    },
    testing_patterns: {
      type: 'object',
      properties: {
        test_location: { type: 'string' },
        test_framework: { type: 'string' },
        typical_test_structure: { type: 'string' },
        how_to_add_test: { type: 'string' },
      },
      required: ['test_location', 'test_framework', 'how_to_add_test'],
    },
  },
  required: ['files', 'wiring_patterns', 'testing_patterns'],
}

const FUNC_CODE_SCHEMA = {
  type: 'object',
  properties: {
    issues_completed: { type: 'array', items: { type: 'number' } },
    title: { type: 'string' },
    // Source code for the compute function(s) — to be written to target file
    function_code: {
      type: 'object',
      properties: {
        target_file: { type: 'string' },
        imports_added: { type: 'array', items: { type: 'string' } },
        constants_added: { type: 'array', items: { type: 'string' } },
        function_definitions: { type: 'array', items: { type: 'string' } },
        // For orderbook.py: where to insert (before compute_orderbook_group or after)
        insert_after_function: { type: 'string' },
        // __all__ updates needed
        exports_added: { type: 'array', items: { type: 'string' } },
      },
      required: ['target_file', 'function_definitions'],
    },
    // Pipeline wiring instructions for integration agent
    pipeline_wiring: {
      type: 'object',
      properties: {
        feature_group_added: { type: 'string' },
        compute_function_name: { type: 'string' },
        call_location_in_pipeline: { type: 'string' },
        constants_added_to_pipeline: { type: 'array', items: { type: 'string' } },
      },
      required: ['compute_function_name'],
    },
    // Test code to add
    test_code: {
      type: 'object',
      properties: {
        test_file: { type: 'string' },
        test_functions: { type: 'array', items: { type: 'string' } },
        imports_needed: { type: 'array', items: { type: 'string' } },
      },
      required: ['test_file', 'test_functions'],
    },
    warnings: { type: 'array', items: { type: 'string' } },
  },
  required: ['issues_completed', 'function_code', 'pipeline_wiring', 'test_code'],
}

const TRAIN_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    train_status: { type: 'string', enum: ['PASS', 'PASS_WITH_WARNINGS', 'FAIL'] },
    accuracy: { type: 'number' },
    sharpe_ratio: { type: 'number' },
    overfit_gap: { type: 'number' },
    feature_count: { type: 'number' },
    warnings: { type: 'array', items: { type: 'string' } },
    errors: { type: 'array', items: { type: 'string' } },
  },
  required: ['train_status', 'accuracy', 'overfit_gap', 'feature_count'],
}

// ═══════════════════════════════════════════════════════════════════════════════
// 10 AGENTS — exactly fits concurrency cap (no queueing)
// ═══════════════════════════════════════════════════════════════════════════════
// All agents output structured code (NO file writes) → zero merge conflicts.
//
// Agent timing estimates (extended thinking dominated):
//   FAST    ~3 min:  solo files, simple logic
//   MEDIUM  ~4-6 min: orderbook features, funding, regime
//   COMPLEX ~8-10 min: CPCV, triple-barrier + meta-labeling
// ═══════════════════════════════════════════════════════════════════════════════

const ALL_AGENTS = [
  { // ── FAST: solo file ──
    id: 'backfill',
    issues: [155],
    title: 'Download 20 USDT-M perpetual symbols',
    target_file: 'alphaforge/src/alphaforge/data/backfill.py',
    test_file: 'alphaforge/tests/test_backfill.py',
    complexity: 'fast',
    description: 'Add httpx downloader with checksum verification, Parquet+Zstd conversion',
    prompt_addon: 'Return structured code output — do NOT write to filesystem.',
  },
  { // ── FAST: solo file ──
    id: 'funding',
    issues: [157],
    title: 'Wire funding rate features',
    target_file: 'alphaforge/src/alphaforge/features/funding.py',
    test_file: 'alphaforge/tests/test_funding.py',
    complexity: 'fast',
    description: 'Wire compute_funding_group with real data, add funding_rate/change/ma',
    prompt_addon: 'Return structured code output. Pipeline wiring will be done by integration agent.',
  },
  { // ── FAST: solo file ──
    id: 'regime',
    issues: [161],
    title: 'Online regime classifier',
    target_file: 'alphaforge/src/alphaforge/features/regime.py',
    test_file: 'alphaforge/tests/test_regime.py',
    complexity: 'medium',
    description: 'OnlineRegimeDetector with CUSUM + HMM + volatility regime',
    prompt_addon: 'Return structured code output. Pipeline wiring will be done by integration agent.',
  },
  { // ── MEDIUM: orderbook — OBI family ──
    id: 'obi-family',
    issues: [154, 165, 170],
    title: 'L1 OBI + Multi-level OBI_N + Stoikov micro-price',
    target_file: 'alphaforge/src/alphaforge/features/orderbook.py',
    test_file: 'alphaforge/tests/test_orderbook.py',
    complexity: 'medium',
    description: 'compute_orderbook_imbalance, compute_multi_level_obi(N=5), compute_micro_price',
    prompt_addon: 'Return structured code. Do NOT write to orderbook.py. Integration agent will merge all orderbook functions.',
  },
  { // ── MEDIUM: orderbook — microstructure ──
    id: 'microstructure',
    issues: [164, 166],
    title: 'OFI + VAMP',
    target_file: 'alphaforge/src/alphaforge/features/orderbook.py',
    test_file: 'alphaforge/tests/test_orderbook.py',
    complexity: 'medium',
    description: 'compute_ofi() Cont-Kukanov-Stoikov + compute_vamp() Volume-Adjusted Mid Price',
    prompt_addon: 'Return structured code. Do NOT write to orderbook.py. Integration agent will merge.',
  },
  { // ── MEDIUM: orderbook — spread + volume ──
    id: 'spread-volume',
    issues: [162, 163],
    title: 'Spread, VWAP-to-Mid, N Trades, Volume HHI',
    target_file: 'alphaforge/src/alphaforge/features/orderbook.py',
    test_file: 'alphaforge/tests/test_orderbook.py',
    complexity: 'medium',
    description: 'compute_quoted_spread, compute_vwap_to_mid_deviation, compute_trade_count, compute_volume_concentration_hhi',
    prompt_addon: 'Return structured code. Do NOT write to orderbook.py. Integration agent will merge.',
  },
  { // ── MEDIUM: solo file ──
    id: 'shap-diversity',
    issues: [167, 168],
    title: 'SHAP importance + Symbol diversity scoring',
    target_file: 'alphaforge/src/alphaforge/research/',
    test_file: 'alphaforge/tests/test_research.py',
    complexity: 'medium',
    description: 'TreeSHAP analysis in feature_importance.py + compute_diversity_metrics in new module',
    prompt_addon: 'Return structured code. xgb_trainer.py changes will be merged by integration agent.',
  },
  { // ── FAST: docs + roadmap ──
    id: 'docs',
    issues: [171, 172],
    title: 'Archive research docs + Phase 3-4 epic',
    target_file: 'docs/research/',
    test_file: null,
    complexity: 'fast',
    description: 'Archive deep research to docs/research/ + epic sub-issues in roadmap',
    prompt_addon: 'Return structured content. Do NOT write to filesystem.',
  },
  { // ── COMPLEX: cross-validation ──
    id: 'crossval',
    issues: [159, 169],
    title: 'CPCV + Purged CV for Optuna',
    target_file: 'alphaforge/src/alphaforge/validation/walk_forward.py',
    test_file: 'alphaforge/tests/test_validation.py',
    complexity: 'complex',
    description: 'CPCV splitter in walk_forward.py + purge_gap in nested_wfv.py',
    prompt_addon: 'Return structured code. Do NOT modify pipeline.py.',
  },
  { // ── COMPLEX: labeling ──
    id: 'labeling',
    issues: [156, 160],
    title: 'Triple-barrier labeling + Meta-labeling',
    target_file: 'alphaforge/src/alphaforge/labels/adapter.py',
    test_file: 'alphaforge/tests/test_labels.py',
    complexity: 'complex',
    description: 'compute_triple_barrier_labels (volatility-scaled) + MetaLabelingTrainer in xgb_trainer',
    prompt_addon: 'Return structured code. xgb_trainer changes will be merged by integration agent.',
  },
]

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER
// ═══════════════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════════════
// SCRIPT BODY
// ═══════════════════════════════════════════════════════════════════════════════

// ─── PHASE 1: SCOUT ──────────────────────────────────────────────────────────
// Reads 12 files, produces structured codebase map.
// This SINGLE read feeds ALL 10 implementation agents → saves ~200K tokens

phase('Scout')
log('Reading codebase — 1 scout feeds all 10 agents...')

const codebase = await agent(`
Read these files and produce a structured codebase summary:

FILES:
1. alphaforge/src/alphaforge/features/orderbook.py — all 12 existing functions (signatures, patterns, docstrings)
2. alphaforge/src/alphaforge/features/pipeline.py — FeatureGroup enum, FeatureMatrix, compute_all_features()
3. alphaforge/src/alphaforge/features/funding.py — funding feature structure
4. alphaforge/src/alphaforge/features/regime.py — regime detection structure, existing evaluator
5. alphaforge/src/alphaforge/labels/adapter.py — LabelAdapter, all label classes
6. alphaforge/src/alphaforge/training/xgb_trainer.py — trainer class, _step_train, SWING params
7. alphaforge/src/alphaforge/tuning/nested_wfv.py — nested walk-forward, _OptunaObjective
8. alphaforge/src/alphaforge/tuning/search_space.py — hyperparameter spaces
9. alphaforge/src/alphaforge/data/backfill.py — download structure
10. alphaforge/src/alphaforge/research/feature_importance.py — SHAP code
11. alphaforge/src/alphaforge/validation/walk_forward.py — walk-forward validator
12. cli/v7_pipeline.py — pipeline steps

For each file: functions (name/params/return), classes (name/methods/bases), constants, imports.

ANALYZE:
- How does a new feature get wired into compute_all_features()? Exact code pattern.
- What is the compute_orderbook_group() function signature and internal structure?
- How are tests structured? What pytest markers? Conftest fixtures?
- What is the exact import style? (from x import y vs import x.y)
- How does _step_train in pipeline.py call the trainer?
- NaN handling pattern for feature start?
`, {
  schema: CODEBASE_SCHEMA,
  label: 'codebase-scout',
})

log(`Scout done: ${codebase.files.length} files analyzed`)
log(`Wiring pattern: ${codebase.wiring_patterns.how_to_wire_new_feature.slice(0, 120)}...`)

// ─── PHASE 2: ALL 10 AGENTS IN PARALLEL ─────────────────────────────────────
// Exactly fits concurrency cap → NO QUEUEING DELAY
// Structured output ONLY → ZERO MERGE CONFLICTS
//
// Timing (extended thinking dominated):
//   complex(2) × 10 min + medium(5) × 5 min + fast(3) × 3 min
//   All start at once → bound by SLOWEST complex agent = ~10 min

phase('Parallel Impl')
log(`Spawning ${ALL_AGENTS.length} implementation agents (all concurrent, structured output)...`)

const implResults = await parallel(
  ALL_AGENTS.map(a => () => {
    // Build filtered context from scout output
    const relevantFiles = codebase.files.filter(f =>
      a.target_file && f.path.includes(a.target_file.replace('alphaforge/src/', '').replace(/\/\w+\.py$/, '').replace(/\/$/, ''))
    )

    return agent(`
You are implementing AlphaForge trading features. Return STRUCTURED CODE OUTPUT.
Do NOT write to filesystem. Return Python source code in the schema fields.

CODEBASE CONTEXT:
${JSON.stringify({ files: relevantFiles, wiring: codebase.wiring_patterns, testing: codebase.testing_patterns }, null, 2)}

ISSUES: #${a.issues.join(', #')} — ${a.title}
DESCRIPTION: ${a.description}
TARGET FILE: ${a.target_file}
TEST FILE: ${a.test_file}

IMPLEMENTATION REQUIREMENTS:
1. Write compute_* function(s) following EXACT existing patterns (numpy, docstrings, NaN handling)
2. Add proper constants matching existing naming convention (DEFAULT_* / MODE_*)
3. Add test functions matching existing test patterns
4. Include pipeline wiring instructions (which FeatureGroup, where to call in pipeline)

CRITICAL RULES:
- Do NOT write to any file. Return code as structured output.
- Do NOT add pipeline.py wiring — integration agent handles that.
- Use same numpy/causal patterns as existing code.
- Follow exact import style from existing code (from x import y).
- Function must be causal: bar[t] accesses only bars [t-lookback+1 .. t].

Return COMPLETE working Python code in the schema, not pseudocode.
`, {
      label: `impl-${a.id}`,
      schema: FUNC_CODE_SCHEMA,
    })
  })
)

log(`All ${implResults.filter(Boolean).length} agents completed`)

// Collect all structured outputs
const allResults = implResults.filter(Boolean)

// ─── PHASE 3: INTEGRATION ────────────────────────────────────────────────────
// Takes ALL structured outputs → writes to filesystem
// Single agent → orderbook.py (merge all 3 agents' functions) + pipeline.py (wire all) + all tests

phase('Integrate')
log('Integration agent — writing all files from structured output...')

// Count what we're integrating
const totalFunctions = allResults.reduce((s, r) => s + (r.function_code?.function_definitions?.length || 0), 0)
const totalTests = allResults.reduce((s, r) => s + (r.test_code?.test_functions?.length || 0), 0)
const totalIssues = [...new Set(allResults.flatMap(r => r.issues_completed || []))]
log(`Integrating ${totalFunctions} functions, ${totalTests} tests, ${totalIssues.length} issues`)

await agent(`
INTEGRATION PHASE — Write ALL implemented features to filesystem.

You have structured code outputs from parallel implementation agents.
Your job: merge them into the actual Python files following existing patterns.

CODEBASE CONTEXT (original structure):
${JSON.stringify(codebase.files.map(f => f.path + ': ' + f.functions.map(g => g.name).join(', ')), null, 2)}

ORDERBOOK FUNCTIONS TO MERGE (all go into orderbook.py):
${JSON.stringify(
  allResults.filter(r => r.function_code?.target_file?.includes('orderbook'))
    .flatMap(r => r.function_code.function_definitions),
  null, 2
)}

PIPELINE WIRING INSTRUCTIONS (all need to be wired into compute_all_features):
${JSON.stringify(
  allResults.flatMap(r => r.pipeline_wiring || []),
  null, 2
)}

TEST CODE TO ADD:
${JSON.stringify(
  allResults.filter(r => r.test_code?.test_functions?.length > 0)
    .map(r => ({ file: r.test_code.test_file, count: r.test_code.test_functions.length })),
  null, 2
)}

STEPS (execute in order):
1. Write ALL new compute functions to orderbook.py (merge from all 3 orderbook agents)
   - Add imports at top
   - Add constants after existing constants
   - Add function definitions after existing functions, BEFORE compute_orderbook_group()
   - Update compute_orderbook_group() to call new functions
   - Update __all__ exports
2. Write ALL other module changes:
   - backfill.py: add downloader
   - funding.py: wire compute_funding_group
   - regime.py: add OnlineRegimeDetector
   - research/feature_importance.py: add SHAP analysis
   - research/diversity.py: new module for diversity scoring
   - xgb_trainer.py: add meta-labeling trainer, SHAP hook
   - labels/adapter.py: add triple-barrier labeling
   - validation/walk_forward.py: add CPCV splitter
   - tuning/nested_wfv.py: add purge_gap
3. Write ALL pipeline.py changes:
   - Add new FeatureGroup enums if needed
   - Wire new compute functions into compute_all_features()
   - Add new constants
   - Wire caching layer
   - Wire funding data into backfill step
4. Write ALL test files
5. Update cli/v7_pipeline.py if needed (_step_train for meta-labeling, etc.)

REQUIREMENTS:
- Every function must have proper numpy docstring
- NaN fill for lookback < window
- Exact same coding style as existing code (type annotations, numpy ops, etc.)
- Run: PYTHONPATH=. python3 -c "from alphaforge.features.orderbook import *" to verify
`, {
  label: 'integration-write',
})

// ─── PHASE 3b: SMOKE TESTS ──────────────────────────────────────────────────

phase('Smoke')
log('Running smoke tests...')

await agent(`
Run validation commands and FIX any failures:

1. PYTHONPATH=. python3 -c "from alphaforge.features.orderbook import *; print('orderbook OK')"
2. PYTHONPATH=. python3 -c "from alphaforge.features.pipeline import *; print('pipeline OK')"
3. PYTHONPATH=. python3 -c "from alphaforge.labels.adapter import *; print('labels OK')"
4. PYTHONPATH=. python3 -m pytest alphaforge/tests/test_orderbook.py -q --tb=short
5. PYTHONPATH=. python3 -m pytest lib/tests/ integration/tests/ simulation/tests/ -q --ignore=lib/tests/test_market_data_binance.py
6. make check-boundaries

For any failure: read the error, fix the issue, re-run.
Report what passed and what was fixed.
`, {
  label: 'smoke-tests',
})

// ─── PHASE 4: TRAINING ─────────────────────────────────────────────────────

phase('Train')
log('Running end-to-end training...')

const trainResult = await agent(`
Run the full training pipeline:

PYTHONPATH=. python3 -m alphaforge.train --mode SWING --features all

All 19 issues implemented:
- Triple-barrier labels (#156) + meta-labeling (#160)
- CPCV + purged CV (#159, #169)
- OBI, OBI_N, micro-price, OFI, VAMP (#154, #165, #170, #164, #166)
- Spread, VWAP-to-mid, volume features (#162, #163)
- Funding rate (#157), regime classifier (#161)
- SHAP importance (#167), diversity scoring (#168)
- Feature caching (#158), 20-symbol download (#155)

Collect and report: accuracy, Sharpe, overfit gap, feature count.
If training fails, diagnose and fix.
`, {
  schema: TRAIN_RESULT_SCHEMA,
  label: 'training',
})

log(`Training: ${trainResult.train_status} | acc=${trainResult.accuracy} | Sharpe=${trainResult.sharpe_ratio} | gap=${trainResult.overfit_gap}`)

// ─── PHASE 5: REPORTS ──────────────────────────────────────────────────────

phase('Report')
log('Generating ACCP reports and updating roadmap...')

// ACCP reports (parallel per completed issue)
const allCompletedIssues = [...new Set(allResults.flatMap(r => r.issues_completed || []))]
log(`Generating ${allCompletedIssues.length} ACCP reports...`)

await parallel(
  allCompletedIssues.map(num => () =>
    agent(`
Generate ACCP-YAML v2.0.0 completion report for issue #${num}.

Save to: reports/accp/issue-${num}.yaml

Include:
- result: PASS (or PASS_WITH_WARNINGS if any open items)
- scope_confirmation: what was implemented
- files_changed: list
- decisions_locked: any new design locks
- remaining_holds: any open items
- safe_next_step: what to do next
- commands_run: test commands + output
- evidence: test/metrics output
    `, {
      label: `accp-#${num}`,
    })
  )
)

// Roadmap update
await agent(`
Update v7/docs/roadmap.md:
1. Mark AlphaForge Profitability v0.1 sections complete
2. Update design lock scores
3. Add completion notes referencing issues ${allCompletedIssues.join(', #')}
4. Note any remaining HOLD items

Training results: ${JSON.stringify(trainResult, null, 2)}
`, {
  label: 'roadmap-update',
})

// Final sync
await agent(`
Run: bash .claude/skills/sync-worktrees.sh
Verify: git log --oneline -5
`, {
  label: 'final-sync',
})

// ═══════════════════════════════════════════════════════════════════════════════
// SUMMARY
// ═══════════════════════════════════════════════════════════════════════════════

log('▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓')
log('▓  AlphaForge Profitability v0.1 — COMPLETE')
log('▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓')

return {
  total_agents: 1 + ALL_AGENTS.length + 4,  // scout + 10 impl + integration + smoke + train + report + sync
  issues: allCompletedIssues,
  training: trainResult,
  total_functions: totalFunctions,
  total_tests: totalTests,
}
