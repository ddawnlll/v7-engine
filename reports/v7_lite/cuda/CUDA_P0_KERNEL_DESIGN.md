# CUDA P0 Kernel Design — DEFERRED

**Status:** `DEFERRED` — see CUDA_FEASIBILITY_REPORT.md for rationale
**Generated:** 2026-07-08

---

## Design Reference Only

This document defines the **theoretical first CUDA kernel** that would be needed
if CUDA becomes worthwhile. **Do not implement now.**

## Kernel Specification

### Purpose
Vectorized candidate outcome simulation: given OHLCV arrays and entry parameters,
compute exit bar, exit reason, and gross R for ALL candidates in one GPU grid launch.

### Thread Model
- 1 thread per candidate
- Block size: 128 or 256 threads (experimentally optimal for Tesla T4)
- Grid size: ceil(n_candidates / block_size)

### Memory Model
- Global memory: OHLCV arrays (shared across all candidates)
- Shared memory: None needed (each thread reads independently)
- Register pressure: Low (~20 registers, stop/target/bar index only)

### Input Arrays (global memory, read-only)
```
high[n_cand, max_bars]   — float32
low[n_cand, max_bars]    — float32  
close[n_cand, max_bars]  — float32
entry_bar[n_cand]        — int32
direction[n_cand]        — int8 (1=LONG, -1=SHORT)
stop_price[n_cand]       — float32
target_price[n_cand]     — float32
atr_at_entry[n_cand]     — float32
max_bars[n_cand]         — int32
```

### Output Arrays (global memory, write-once)
```
exit_bar[n_cand]         — int32
exit_reason[n_cand]      — int8 (0=STOP, 1=TARGET, 2=TIME)
gross_R[n_cand]          — float32
```

### Algorithm (per thread)
```
1. eb = entry_bar[tid]
2. For bar = eb+1 to eb+max_bars[tid]:
   If direction[tid] == LONG:
     If low[bar] <= stop_price[tid]: STOP_HIT, return
     If high[bar] >= target_price[tid]: TARGET_HIT, return
   If direction[tid] == SHORT:
     If high[bar] >= stop_price[tid]: STOP_HIT, return
     If low[bar] <= target_price[tid]: TARGET_HIT, return
3. If no exit: TIME_EXIT at last bar
4. gross_R = (exit_price - entry_price) * direction / (entry_price * atr)
```

### Performance Expectation (Estimated)

| Scale | CPU (existing) | GPU (theoretical) | Notes |
|-------|---------------|-------------------|-------|
| 1K candidates | < 0.001s | ~0.01s | CPU wins (no transfer overhead) |
| 10K candidates | ~3.2s | ~3.5s | CPU still wins |
| 100K candidates | ~10s | ~8s | GPU might start winning |
| 1M candidates | ~95s | ~30s | GPU wins by 3x |
| 10M candidates | ~950s | ~250s | GPU wins by 3.8x |

**Crossover point:** ~200K candidates. Below this, CPU is faster due to
PCIe transfer overhead and kernel launch latency.

### Why This Is Deferred

The existing `simulation/` cuda.jit already implements this exact kernel design.
It was benchmarked and found **2-3x slower than CPU-parallel at ALL scales up to 2M paths**.

The explanation: short holding periods (5-30 bars) mean each GPU thread
does very little work. The overhead of launching the kernel and transferring
data back dominates.

If holding periods grow to 100+ bars (SWING mode), GPU would start to win.
But for SCALP mode (5-12 bars), CPU-parallel is optimal.
