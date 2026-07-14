# Agent Handoff — Faz 0+1+3 Completion (2026-07-14)

## Current state

Three task phases completed and committed:

### Faz 0: Branch Reconciliation ✅
- Cherry-picked `be186bd` (V7-Lite deterministic readiness gate) from `fix/306-holdout-cutoff-tests` to `main`
- Resolved merge conflicts (8 files: docs, contracts, simulation, roadmap)
- Commit: `50ac3ce`
- Verification: `v7/tests/test_lite_readiness_gate.py` → 22/22 passed
- `v7/lite/readiness_gate.py` now on main with `compute_readiness()` function

### Faz 1: G3 Relabeling ✅
- Added F-021 retraction to `docs/audits/FINDINGS_LEDGER.md`
- Documents that oracle ceiling R (+0.8439) must NOT be reported as model G3 performance
- Retracts previous session's "G3 PASS MeanR=0.8439" claim
- Actual model G3 = UNMEASURED on full 56-symbol panel
- Commit: `2dde994`

### Faz 3: Factor Selection A/B Test ✅ (Infrastructure)
- Extended `alphaforge/src/alphaforge/reports/ic_metrics.py` with 4 new functions:
  - `compute_per_feature_ic()` — per-feature IC/RankIC/|IC| computation
  - `compute_feature_correlation_matrix()` — pairwise Pearson correlation
  - `select_features_greedy_ic()` — greedy IC-based selection with redundancy removal
  - `compute_dynamic_weights()` — fold-wise IC-proportional dynamic weighting
- Created `alphaforge/src/alphaforge/factor_selection.py`:
  - `FactorSelectionConfig` dataclass (max_features, corr_threshold, min_ic, enable_dynamic_weighting)
  - `FactorSelectionResult` dataclass
  - `run_factor_selection()` — full pipeline
  - `apply_feature_mask()` — column selection
  - `apply_dynamic_weighting_to_fold()` — fold-wise weighting
  - `format_ic_table_for_logging()` — human-readable IC table
- Integrated A/B comparison into `walk_forward_validate`:
  - New params: `feature_selection_config`, `feature_names`
  - New helper: `_run_fold_ab_comparison()` — runs Config A (full) vs Config B (selected) each fold
  - New aggregator: `collect_ab_comparison_metrics()` — summarizes A/B across all folds
  - Results appear in `fold_payload["ab_comparison"]`
- Commit: `0418f0d`
- Tests: 25 tests across 2 test files (test_factor_selection.py + test_ab_factor_selection.py)

## What changed

| File | Change |
|------|--------|
| `v7/lite/readiness_gate.py` | NEW — deterministic V7-Lite readiness gate (from be186bd) |
| `v7/tests/test_lite_readiness_gate.py` | NEW — 22 tests |
| `docs/audits/FINDINGS_LEDGER.md` | +F-021 retraction entry |
| `alphaforge/src/alphaforge/reports/ic_metrics.py` | +4 factor selection functions (238 lines) |
| `alphaforge/src/alphaforge/factor_selection.py` | NEW — factor selection module (217 lines) |
| `alphaforge/src/alphaforge/train.py` | +feature_selection_config param, +_run_fold_ab_comparison, +collect_ab_comparison_metrics (244 lines) |
| `alphaforge/tests/test_factor_selection.py` | NEW — 18 tests |
| `alphaforge/tests/test_ab_factor_selection.py` | NEW — 7 tests |

## Next action

1. **Remote GPU validation**: Run `test_factor_selection.py` and `test_ab_factor_selection.py` on remote (needs numpy/scipy/xgboost)
2. **Real data A/B test**: Run full 56-symbol panel with `feature_selection_config` to get actual Config A vs Config B comparison
3. **Faz 2** (Gα0 oracle decomposition) and **Faz 4** (meta-labeling gating) — per previous task descriptions

## Commands to verify

```bash
# Local syntax check (already passed)
python3 -c "import ast; [ast.parse(open(f).read()) for f in ['alphaforge/src/alphaforge/reports/ic_metrics.py', 'alphaforge/src/alphaforge/factor_selection.py', 'alphaforge/src/alphaforge/train.py']]"

# Remote GPU test (needs full deps)
PYTHONPATH=alphaforge/src:. python3 -m pytest alphaforge/tests/test_factor_selection.py alphaforge/tests/test_ab_factor_selection.py -v

# Remote full A/B comparison run
PYTHONPATH=. python3 -c "
from alphaforge.train import main
# Will need feature_selection_config=FactorSelectionConfig() passed to main()
"
```
