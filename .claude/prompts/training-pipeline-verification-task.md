# Training Pipeline Optimization — Verification Task

## Mission

Prove that the W1–W6 optimizations changed nothing about the alpha (for W1–W4: exact artifact identity; for W5–W6: bounded tolerance) and everything about the speed. Then gate the 57-symbol launch behind that proof.

## Core constraint

W1–W4 are **refactors of identical math** — their standard is exact artifact identity:

- `np.array_equal` on the feature matrix (not `allclose` — ties must match exactly)
- Identical fold metrics (accuracy, Net R, active trades per fold)
- Identical discovery decision (promote/reject)

Any delta at all in W1–W4 means a bug. No rationalizing, no "close enough".

W5 (QuantileDMatrix) and W6 (chronological early-stop) intentionally change behavior, so they get a tolerance band: |Δaccuracy| ≤ 0.005, Net R same sign ±20%. Warn: W6 may *lower* validation metrics slightly — that's the leakage fix working, not a regression.

## Fail-fast gauntlet (≤ 90 min total)

### Phase 0 — Pre-flight (5 min)

1. `PYTHONPATH=alphaforge/src python3 -m pytest alphaforge/tests/test_cross_sectional_rank_normalize.py alphaforge/tests/test_xgb_trainer.py -v` — all pass
2. `git log --oneline -5` — all 6 commit messages present
3. `ALPHAFORGE_XGB_DEVICE=cpu` is exported (CPU forced for equivalence)

**Hard stop:** any test failure → NO-GO, report which test.

### Phase 1 — 2-symbol artifact comparison vs baseline (10 min)

1. Create a baseline worktree: `git worktree add ../v7-baseline HEAD~6` (pre-W1 commit)
2. Run baseline with 2 symbols, 3 folds:
   ```
   ALPHAFORGE_XGB_DEVICE=cpu PYTHONPATH=alphaforge/src python3 -m alphaforge.train \
     --mode SCALP --symbols BTCUSDT,ETHUSDT --synthetic --folds 3 \
     --output /tmp/baseline_metrics.json --dump-features /tmp/baseline_X
   ```
3. Run optimized version with same args:
   ```
   ALPHAFORGE_XGB_DEVICE=cpu PYTHONPATH=alphaforge/src python3 -m alphaforge.train \
     --mode SCALP --symbols BTCUSDT,ETHUSDT --synthetic --folds 3 \
     --output /tmp/opt_metrics.json --dump-features /tmp/opt_X
   ```
4. Compare:
   - `np.array_equal(np.load('/tmp/baseline_X.npy'), np.load('/tmp/opt_X.npy'))` — **exact identity**
   - Compare `accuracy`, `net_expectancy_r`, `feature_count`, `n_samples` from JSON outputs
5. Remove worktree: `git worktree remove ../v7-baseline`

**Hard stop:** any mismatch → NO-GO, investigate cause.

### Phase 2 — Cache staleness attack (10 min)

1. Run once to warm the feature cache:
   ```
   PYTHONPATH=alphaforge/src python3 -c "
   from alphaforge.features.pipeline import cached_compute_features, _compute_data_fingerprint
   import numpy as np
   ohlcv = {'close': np.arange(100.0), 'high': np.arange(100.0)+1, 'low': np.arange(100.0)-1,
            'open': np.arange(100.0), 'volume': np.ones(100)*1000, 'symbol': 'BTCUSDT'}
   r = cached_compute_features(ohlcv, mode='SWING', interval='1h', cache_dir='/tmp/test_cache_w2')
   print('MISS' if r is not None else 'ERROR')
   " 2>&1
   ```
2. Mutate the data (change last close value):
   ```
   ohlcv['close'][-1] = 99999.0
   r = cached_compute_features(ohlcv, mode='SWING', interval='1h', cache_dir='/tmp/test_cache_w2')
   ```
3. Assert cache MISS (fingerprint changed → different cache key)

**Hard stop:** cache HIT on mutated data → NO-GO unconditional. This is the only way the optimization can silently lose alpha.

### Phase 3 — 4-symbol/6-fold smoke gate (20 min)

Run the official smoke gate from the spec:

```
ALPHAFORGE_XGB_DEVICE=cpu PYTHONPATH=alphaforge/src python3 -m alphaforge.train \
  --mode SCALP --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT --synthetic --folds 6 \
  --output /tmp/smoke_metrics.json
```

Check:
- `accuracy`, `net_expectancy_r`, `total_net_R`, `feature_count`, `n_samples` match baseline (within W5–W6 tolerance if applicable)
- No warnings or errors in output
- Log shows cross-sectional rank normalization applied

### Phase 4 — Synthetic 57-symbol probe (10 min)

1. Generate 57-symbol × 3000-bar synthetic data and time the rank stage:
   ```
   ALPHAFORGE_XGB_DEVICE=cpu PYTHONPATH=alphaforge/src python3 -c "
   import time, numpy as np
   from alphaforge.train import cross_sectional_rank_normalize
   n_ts, n_sym, n_feat = 3000, 57, 89
   ts = np.sort(np.repeat(np.arange(n_ts, dtype=np.int64), n_sym))
   X = np.random.RandomState(42).randn(len(ts), n_feat)
   t0 = time.monotonic()
   Xr = cross_sectional_rank_normalize(X, ts)
   dt = time.monotonic() - t0
   print(f'Rank stage: {dt:.3f}s (target: ≤30s)')
   assert dt < 30, f'Rank stage too slow: {dt:.1f}s'
   " 2>&1
   ```

2. **On SSH box only** — Run one GPU WFV fold:
   ```
   ALPHAFORGE_XGB_DEVICE=cuda PYTHONPATH=alphaforge/src python3 -c "
   import numpy as np, time, xgboost as xgb
   from alphaforge.training.xgb_trainer import XGBoostTrainer
   n, nf = 50000, 89
   X = np.random.RandomState(42).randn(n, nf).astype(np.float32)
   y = np.random.RandomState(42).randint(0, 3, n).astype(np.int32)
   trainer = XGBoostTrainer(mode='SCALP')
   t0 = time.monotonic()
   r = trainer.train(X, y)
   dt = time.monotonic() - t0
   print(f'GPU fold: {dt:.2f}s (target: ≤60s per fold)')
   " 2>&1
   ```

### Phase 5 — GO/No-GO

| Phase | Result | Notes |
|-------|--------|-------|
| 0 | PASS/FAIL | |
| 1 | PASS/FAIL | |
| 2 | PASS/FAIL | |
| 3 | PASS/FAIL | |
| 4 | PASS/FAIL | |

**GO** if all 5 phases PASS.

**No-GO** on first failure. Report:
1. Which phase failed
2. The exact delta (mismatched value, timing, decision)
3. Root cause hypothesis
4. Whether the delta is a real alpha risk or a false alarm

## Launch protocol (only after GO)

```
ALPHAFORGE_XGB_DEVICE=cuda PYTHONPATH=alphaforge/src python3 -m alphaforge.train \
  --mode SCALP --symbols <57-symbol-list> --panel-cache cache/factor_sprint --folds 6 \
  --output artifacts/reports/57sym_scalp_run1.json 2>&1 | tee logs/57sym_scalp_run1.log
```

### Abort criteria (monitor in real-time):
- **Rank stage** > 5 min → kill (should be ≤ 30 s after W1)
- **Any single WFV fold** > 15 min → kill (investigate memory/swap)
- **Total wall time** > 45 min → kill
- **`n_samples`** < 500k → kill (panel intersection truncated by young listing, B4 unfixed)

If killed, investigate the bottleneck before re-launching.
