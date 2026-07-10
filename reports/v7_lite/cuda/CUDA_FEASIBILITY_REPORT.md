# CUDA Feasibility Report for V7-Lite Candidate Outcome Cache

**Status:** `CUDA_NOT_NEEDED_YET`
**Generated:** 2026-07-08
**Source:** `simulation/docs/gpu_cuda_migration_plan.md`, `simulation/docs/ai_summary.md` §14

---

## Executive Summary

**GPU/CUDA acceleration for candidate outcome replay is already implemented,
tested, and found to be 2-3x SLOWER than CPU-parallel for this workload.**

The simulation team already built and benchmarked:
- CPU-parallel Numba path (default, production-wired)
- GPU cuda.jit path (opt-in, `force_gpu=True`)
- Tested at all scales from 100 to 2M paths on Tesla T4

Every scale showed CPU-parallel faster. CUDA is **not the bottleneck.**

---

## Existing Infrastructure

The following CUDA/GPU work already exists in the repo:

| Component | Location | Status |
|-----------|----------|--------|
| BatchSimulator | `simulation/src/simulation/batch.py` (inferred) | Production |
| CPU-parallel Numba | `backtest_signals()` → `run_batch_cpu()` | Default path |
| GPU cuda.jit | Opt-in `force_gpu=True` | Tested, 2-3x slower |
| Gold parity tests | 500 cases × 10 fields = 0.00e+00 max diff | PASS |
| Real bugs found by batch path | MFE clamp, time_to_mae | FIXED |

### Key Benchmark Numbers (from ai_summary.md §14)

| Scale | CPU-parallel | GPU (cuda.jit) | Winner |
|-------|-------------|----------------|--------|
| 100 paths | Fastest | Slower | CPU |
| 10K signals | 3.2s (1.58x vs original) | Slower | CPU |
| 69K signals | ~6.6s | N/A | CPU |
| 1M paths | Fastest | 2-3x slower | CPU |
| 2M paths | Fastest | 2-3x slower | CPU |

GPU utilization: 0-62% (never reaches saturation for short 5-30 bar paths).

---

## Why CUDA Is Not Needed Now

### 1. Bottleneck Is Not Compute

For V7-Lite candidate outcome caching, the bottleneck is:
- **I/O and memory bandwidth** — loading OHLCV data, writing parquet files
- **Python overhead** — orchestrating the simulation loop, not the inner loop
- **Data availability** — we don't even have trade data to cache yet

CUDA solves "I have too many matrix multiplications" — we have "I need to
simulate 870 trades and store the results."

### 2. CPU Is Already Fast Enough

The existing CPU-parallel BatchSimulator handles 69K signals in ~6.6 seconds.
For 870 Truth V6 trades: **~0.08 seconds**. Adding CUDA overhead would make
this take 2-3x longer.

### 3. True Bottleneck Is Elsewhere

The actual bottleneck in V7-Lite alpha validation is:
1. **Data generation** — running the full discovery pipeline takes minutes, not microseconds
2. **Caching infrastructure** — reading/writing parquet files is I/O-bound
3. **Analysis overhead** — computing distribution stats, regime splits, bootstrap CIs

None of these benefit from CUDA.

---

## What Would Make CUDA Worthwhile

| Condition | Current Status | Future Trigger |
|-----------|---------------|----------------|
| > 10 million candidates per evaluation | ❌ (870 now) | 100x more alpha concepts |
| > 100-bar holding periods | ❌ (5-30 bars now) | SWING mode expansion |
| Complex path-dependent barriers | ❌ (stop/target only now) | Trailing stops, multi-barrier |
| CPU bottleneck proven | ❌ (I/O is bottleneck) | After outcome cache is built and profiled |
| GPU parity with simulation truth | ❌ (needs validation) | Must match simulation outputs |

---

## Decision

| Decision Label | Verdict |
|----------------|---------|
| `CUDA_NOT_NEEDED_YET` | ✅ **CPU is fast enough for current workload** |
| `CUDA_PROMISING` | ❌ GPU is 2-3x slower at ALL scales |
| `CUDA_BLOCKED` | ❌ No GPU environment issue (Tesla T4 tested) |
| `CUDA_REJECTED_FOR_NOW` | ❌ Not rejected, just not the right tool |

### Recommended Action

1. **Do NOT build CUDA kernels now** — the existing cuda.jit path is slower
2. **Focus on CPU outcome cache** — the real bottleneck is no cache at all
3. **Re-evaluate CUDA only if:**
   - Candidate count exceeds 10M per evaluation
   - Holding period exceeds 100 bars
   - CPU profile shows >50% of time in simulation inner loop
   - A new GPU architecture (H100+) shows different characteristics for short paths

---

## First Kernel Worth Writing (When/If Needed)

If CUDA becomes worthwhile, the first kernel should be:

```python
@cuda.jit
def candidate_outcome_kernel(
    high: np.ndarray,    # [n_candidates, max_bars]
    low: np.ndarray,
    close: np.ndarray,
    entry_bar: np.ndarray,    # [n_candidates]
    direction: np.ndarray,    # [n_candidates]  1=LONG, -1=SHORT
    stop_price: np.ndarray,
    target_price: np.ndarray,
    max_bars: np.ndarray,
    # Outputs
    exit_bar: np.ndarray,
    exit_reason: np.ndarray,  # 0=STOP, 1=TARGET, 2=TIME
    gross_R: np.ndarray,
):
    """
    Minimal CUDA kernel: given arrays of OHLCV and entry params,
    compute exit bar, exit reason, and gross R per candidate.
    """
    tid = cuda.grid(1)
    if tid >= len(entry_bar):
        return
    
    eb = entry_bar[tid]
    dir_signal = direction[tid]
    stop = stop_price[tid]
    target = target_price[tid]
    max_hold = max_bars[tid]
    
    for bar in range(eb + 1, min(eb + max_hold + 1, len(high))):
        if dir_signal == 1:  # LONG
            if low[bar] <= stop:
                exit_bar[tid] = bar
                exit_reason[tid] = 0  # STOP_HIT
                gross_R[tid] = (stop - close[eb]) / (close[eb] * atr_estimate)
                return
            if high[bar] >= target:
                exit_bar[tid] = bar
                exit_reason[tid] = 1  # TARGET_HIT
                gross_R[tid] = (target - close[eb]) / (close[eb] * atr_estimate)
                return
        else:  # SHORT
            if high[bar] >= stop:
                exit_bar[tid] = bar
                exit_reason[tid] = 0
                gross_R[tid] = (close[eb] - stop) / (close[eb] * atr_estimate)
                return
            if low[bar] <= target:
                exit_bar[tid] = bar
                exit_reason[tid] = 1
                gross_R[tid] = (close[eb] - target) / (close[eb] * atr_estimate)
                return
    
    # Time exit
    exit_bar[tid] = min(eb + max_hold, len(close) - 1)
    exit_reason[tid] = 2  # TIME_EXIT
    gross_R[tid] = (close[exit_bar[tid]] - close[eb]) / (close[eb] * atr_estimate)
```

**But again: the existing cuda.jit in simulation/ already does this and is slower.
Do not re-implement.**
