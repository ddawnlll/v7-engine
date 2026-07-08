"""
CUDA kernels for simulation engine backtest acceleration.

One thread per signal-direction pair. OHLC data is padded to a uniform
max_holding_bars (30) so each thread reads from fixed-size 2D arrays.

Architecture:
  1. Host flattens all SimulationInput data into device arrays (one H→D copy)
  2. CUDA kernel processes N_signals × 2 directions in parallel
  3. Host copies results back (one D→H copy)
  4. Host reconstructs Python dataclass objects from raw results

Fallback: CPU @njit(parallel=True) path when CUDA unavailable.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from numba import cuda, njit, prange

logger = logging.getLogger(__name__)

# Exit reason codes (match ExitReason enum)
EXIT_STOP_HIT = 0
EXIT_TARGET_HIT = 1
EXIT_TIME_EXIT = 2


# ═══════════════════════════════════════════════════════════════════════
# CUDA kernel — one thread per signal-direction
# ═══════════════════════════════════════════════════════════════════════


@cuda.jit
def batch_path_kernel(
    # Inputs: shape (N,) where N = n_signals × 2 (1 per direction)
    directions: np.ndarray,          # int32, 0=LONG 1=SHORT
    entry_prices: np.ndarray,        # float64
    stop_prices: np.ndarray,         # float64
    target_prices: np.ndarray,       # float64
    entry_risks: np.ndarray,         # float64
    close_prices: np.ndarray,        # float64
    available_bars_arr: np.ndarray,  # int32
    # OHLC data: shape (N, MAX_BARS) padded with 0s
    high_data: np.ndarray,           # float64
    low_data: np.ndarray,            # float64
    # Outputs: shape (N,)
    out_realized_gross: np.ndarray,  # float64
    out_exit_price: np.ndarray,      # float64
    out_exit_idx: np.ndarray,        # int32
    out_hold_dur: np.ndarray,        # int32
    out_mfe: np.ndarray,             # float64
    out_mae: np.ndarray,             # float64
    out_mfe_r: np.ndarray,           # float64
    out_mae_r: np.ndarray,           # float64
    out_t_mfe: np.ndarray,           # int32
    out_t_mae: np.ndarray,           # int32
    out_exit_reason: np.ndarray,     # int32
    MAX_BARS: int,                   # compile-time known max holding bars
):
    """CUDA kernel: one thread per signal-direction pair.

    Launch with threads = N (total signal×directions).
    Each thread reads its own OHLC data from the 2D arrays,
    simulates the path, and writes results.
    """
    idx = cuda.grid(1)
    if idx >= directions.shape[0]:
        return

    n_avail = available_bars_arr[idx]
    is_long = (directions[idx] == 0)
    ep = entry_prices[idx]
    sp = stop_prices[idx]
    tp = target_prices[idx]
    er = entry_risks[idx]
    cp = close_prices[idx]

    if n_avail <= 0:
        out_realized_gross[idx] = 0.0
        out_exit_price[idx] = ep
        out_exit_idx[idx] = 0
        out_hold_dur[idx] = 0
        out_mfe[idx] = 0.0
        out_mae[idx] = 0.0
        out_mfe_r[idx] = 0.0
        out_mae_r[idx] = 0.0
        out_t_mfe[idx] = 0
        out_t_mae[idx] = 0
        out_exit_reason[idx] = EXIT_TIME_EXIT
        return

    # Scan bars — find first stop/target hit
    first_stop = n_avail
    first_target = n_avail
    for i in range(n_avail):
        if is_long:
            if low_data[idx, i] <= sp and first_stop == n_avail:
                first_stop = i
            if high_data[idx, i] >= tp and first_target == n_avail:
                first_target = i
        else:
            if high_data[idx, i] >= sp and first_stop == n_avail:
                first_stop = i
            if low_data[idx, i] <= tp and first_target == n_avail:
                first_target = i

    # Determine exit (stop wins same-candle)
    exit_reason = EXIT_TIME_EXIT
    exit_idx = n_avail - 1
    exit_price = cp
    realized_gross = 0.0

    if first_stop <= first_target and first_stop < n_avail:
        exit_reason = EXIT_STOP_HIT
        exit_idx = first_stop
        exit_price = sp
        if er > 0.0:
            realized_gross = (sp - ep) / er if is_long else (ep - sp) / er
    elif first_target < n_avail:
        exit_reason = EXIT_TARGET_HIT
        exit_idx = first_target
        exit_price = tp
        if er > 0.0:
            realized_gross = (tp - ep) / er if is_long else (ep - tp) / er
    else:
        if er > 0.0:
            realized_gross = (cp - ep) / er if is_long else (ep - cp) / er

    hold_dur = exit_idx + 1 if exit_reason != EXIT_TIME_EXIT else n_avail

    # MFE/MAE computation
    # For STOP/TARGET: bars 0..exit_idx-1 (pre-exit only, matching simulate_path_from_arrays)
    # For TIME_EXIT: bars 0..available_bars-1 (including exit bar, matching original code
    #   which passes highs[:available_bars] to _compute_path_metrics)
    if exit_reason == EXIT_TIME_EXIT:
        pre_bars = n_avail  # include exit bar in MFE/MAE
    else:
        pre_bars = exit_idx
    mfe = 0.0; mae = 0.0; t_mfe = 0; t_mae = 0
    if pre_bars > 0:
        if is_long:
            best_gain = -1e18
            worst_loss = 1e18
            t_mae_raw = 0  # track raw index even when mae=0
            for j in range(pre_bars):
                gain = high_data[idx, j] - ep
                if gain > best_gain:
                    best_gain = gain
                    t_mfe = j
                loss = low_data[idx, j] - ep
                if loss < worst_loss:
                    worst_loss = loss
                    t_mae_raw = j
            mfe = best_gain  # NO clamping — matches original _compute_path_metrics
            if worst_loss < 0:
                mae = worst_loss
                t_mae = t_mae_raw
            else:
                mae = 0.0
                t_mae = 0  # match original: return 0 when no adverse move
        else:
            best_gain = -1e18
            worst_loss = 1e18
            t_mae_raw = 0
            for j in range(pre_bars):
                gain = ep - low_data[idx, j]
                if gain > best_gain:
                    best_gain = gain
                    t_mfe = j
                loss = high_data[idx, j] - ep
                if loss < worst_loss:
                    worst_loss = loss
                    t_mae_raw = j
            mfe = best_gain  # NO clamping — matches original _compute_path_metrics
            if worst_loss < 0:
                mae = worst_loss
                t_mae = t_mae_raw
            else:
                mae = 0.0
                t_mae = 0  # match original: return 0 when no adverse move

    if er > 0.0:
        mfe_r = mfe / er
        mae_r = mae / er
    else:
        mfe_r = 0.0; mae_r = 0.0

    # Write outputs
    out_realized_gross[idx] = realized_gross
    out_exit_price[idx] = exit_price
    out_exit_idx[idx] = exit_idx
    out_hold_dur[idx] = hold_dur
    out_mfe[idx] = mfe
    out_mae[idx] = mae
    out_mfe_r[idx] = mfe_r
    out_mae_r[idx] = mae_r
    out_t_mfe[idx] = t_mfe
    out_t_mae[idx] = t_mae
    out_exit_reason[idx] = exit_reason


# ═══════════════════════════════════════════════════════════════════════
# CPU parallel fallback (njit + prange)
# ═══════════════════════════════════════════════════════════════════════


@njit(parallel=True)
def batch_path_cpu_parallel(
    directions: np.ndarray,
    entry_prices: np.ndarray,
    stop_prices: np.ndarray,
    target_prices: np.ndarray,
    entry_risks: np.ndarray,
    close_prices: np.ndarray,
    available_bars_arr: np.ndarray,
    high_data: np.ndarray,
    low_data: np.ndarray,
    out_realized_gross: np.ndarray,
    out_exit_price: np.ndarray,
    out_exit_idx: np.ndarray,
    out_hold_dur: np.ndarray,
    out_mfe: np.ndarray,
    out_mae: np.ndarray,
    out_mfe_r: np.ndarray,
    out_mae_r: np.ndarray,
    out_t_mfe: np.ndarray,
    out_t_mae: np.ndarray,
    out_exit_reason: np.ndarray,
):
    """CPU parallel batch path simulation (identical logic)."""
    n = len(directions)
    for idx in prange(n):
        n_avail = available_bars_arr[idx]
        is_long = (directions[idx] == 0)
        ep = entry_prices[idx]
        sp = stop_prices[idx]
        tp = target_prices[idx]
        er = entry_risks[idx]
        cp = close_prices[idx]

        if n_avail <= 0:
            out_realized_gross[idx] = 0.0
            out_exit_price[idx] = ep
            out_exit_idx[idx] = 0
            out_hold_dur[idx] = 0
            out_mfe[idx] = 0.0; out_mae[idx] = 0.0
            out_mfe_r[idx] = 0.0; out_mae_r[idx] = 0.0
            out_t_mfe[idx] = 0; out_t_mae[idx] = 0
            out_exit_reason[idx] = EXIT_TIME_EXIT
            continue

        first_stop = n_avail; first_target = n_avail
        for i in range(n_avail):
            if is_long:
                if low_data[idx, i] <= sp and first_stop == n_avail:
                    first_stop = i
                if high_data[idx, i] >= tp and first_target == n_avail:
                    first_target = i
            else:
                if high_data[idx, i] >= sp and first_stop == n_avail:
                    first_stop = i
                if low_data[idx, i] <= tp and first_target == n_avail:
                    first_target = i

        exit_reason = EXIT_TIME_EXIT
        exit_idx = n_avail - 1
        exit_price = cp
        rg = 0.0

        if first_stop <= first_target and first_stop < n_avail:
            exit_reason = EXIT_STOP_HIT
            exit_idx = first_stop
            exit_price = sp
            if er > 0.0:
                rg = (sp - ep) / er if is_long else (ep - sp) / er
        elif first_target < n_avail:
            exit_reason = EXIT_TARGET_HIT
            exit_idx = first_target
            exit_price = tp
            if er > 0.0:
                rg = (tp - ep) / er if is_long else (ep - tp) / er
        else:
            if er > 0.0:
                rg = (cp - ep) / er if is_long else (ep - cp) / er

        hd = exit_idx + 1 if exit_reason != EXIT_TIME_EXIT else n_avail

        mfe = 0.0; mae = 0.0; t_mfe = 0; t_mae = 0
        if exit_reason == EXIT_TIME_EXIT:
            pre = n_avail   # include exit bar (matching original _compute_path_metrics)
        else:
            pre = exit_idx  # stop/target: bars before exit
        if pre > 0:
            t_mae_raw = 0
            if is_long:
                best_g = -1e18; worst_l = 1e18
                for j in range(pre):
                    g = high_data[idx, j] - ep
                    if g > best_g: best_g = g; t_mfe = j
                    l = low_data[idx, j] - ep
                    if l < worst_l: worst_l = l; t_mae_raw = j
                mfe = best_g  # NO clamping — matches original _compute_path_metrics
                if worst_l < 0:
                    mae = worst_l; t_mae = t_mae_raw
                else:
                    mae = 0.0; t_mae = 0  # match original: 0 when no adverse move
            else:
                best_g = -1e18; worst_l = 1e18
                for j in range(pre):
                    g = ep - low_data[idx, j]
                    if g > best_g: best_g = g; t_mfe = j
                    l = high_data[idx, j] - ep
                    if l < worst_l: worst_l = l; t_mae_raw = j
                mfe = best_g  # NO clamping — matches original _compute_path_metrics
                if worst_l < 0:
                    mae = worst_l; t_mae = t_mae_raw
                else:
                    mae = 0.0; t_mae = 0  # match original: 0 when no adverse move

        if er > 0.0:
            mfe_r = mfe / er; mae_r = mae / er
        else:
            mfe_r = 0.0; mae_r = 0.0

        out_realized_gross[idx] = rg
        out_exit_price[idx] = exit_price
        out_exit_idx[idx] = exit_idx
        out_hold_dur[idx] = hd
        out_mfe[idx] = mfe; out_mae[idx] = mae
        out_mfe_r[idx] = mfe_r; out_mae_r[idx] = mae_r
        out_t_mfe[idx] = t_mfe; out_t_mae[idx] = t_mae
        out_exit_reason[idx] = exit_reason


# ═══════════════════════════════════════════════════════════════════════
# Public API — host-side orchestration
# ═══════════════════════════════════════════════════════════════════════


def is_cuda_available() -> bool:
    """Check if CUDA GPU is available for acceleration."""
    try:
        return cuda.is_available()
    except Exception:
        return False


def prepare_batch_arrays(
    signals_data: list[dict],
    max_bars: int = 30,
) -> dict:
    """Flatten signal data into host arrays ready for device copy.

    Args:
        signals_data: list of dicts with keys:
            direction, entry_price, stop_price, target_price,
            entry_risk, close_price, available_bars, highs, lows
        max_bars: padded OHLC length (default 30 for SCALP max_hold=12,
                  SWING max_hold=30 — safe upper bound)

    Returns:
        dict of numpy arrays suitable for GPU or CPU batch processing.
    """
    n = len(signals_data)

    directions = np.empty(n, dtype=np.int32)
    entry_prices = np.empty(n, dtype=np.float64)
    stop_prices = np.empty(n, dtype=np.float64)
    target_prices = np.empty(n, dtype=np.float64)
    entry_risks = np.empty(n, dtype=np.float64)
    close_prices = np.empty(n, dtype=np.float64)
    available_bars_arr = np.empty(n, dtype=np.int32)
    high_data = np.zeros((n, max_bars), dtype=np.float64)
    low_data = np.zeros((n, max_bars), dtype=np.float64)

    for i, sd in enumerate(signals_data):
        directions[i] = 0 if sd["direction"].upper() == "LONG" else 1
        entry_prices[i] = sd["entry_price"]
        stop_prices[i] = sd["stop_price"]
        target_prices[i] = sd["target_price"]
        entry_risks[i] = sd["entry_risk"]
        close_prices[i] = sd["close_price"]
        n_avail = sd["available_bars"]
        available_bars_arr[i] = n_avail
        n_copy = min(n_avail, max_bars)
        if n_copy > 0:
            high_data[i, :n_copy] = np.asarray(sd["highs"])[:n_copy]
            low_data[i, :n_copy] = np.asarray(sd["lows"])[:n_copy]

    return {
        "directions": directions,
        "entry_prices": entry_prices,
        "stop_prices": stop_prices,
        "target_prices": target_prices,
        "entry_risks": entry_risks,
        "close_prices": close_prices,
        "available_bars": available_bars_arr,
        "high_data": high_data,
        "low_data": low_data,
        "max_bars": max_bars,
    }


def run_batch_gpu(
    arrays: dict,
    stream: Optional[cuda.stream] = None,
) -> dict:
    """Run batch path simulation on GPU.

    Args:
        arrays: output of prepare_batch_arrays()
        stream: optional CUDA stream for async execution

    Returns:
        dict of output arrays (still on host, copied back from device)
    """
    n = len(arrays["directions"])
    max_bars = arrays["max_bars"]

    # Allocate output arrays on device
    d_out_rg = cuda.device_array(n, dtype=np.float64)
    d_out_ep = cuda.device_array(n, dtype=np.float64)
    d_out_ei = cuda.device_array(n, dtype=np.int32)
    d_out_hd = cuda.device_array(n, dtype=np.int32)
    d_out_mfe = cuda.device_array(n, dtype=np.float64)
    d_out_mae = cuda.device_array(n, dtype=np.float64)
    d_out_mfe_r = cuda.device_array(n, dtype=np.float64)
    d_out_mae_r = cuda.device_array(n, dtype=np.float64)
    d_out_tmfe = cuda.device_array(n, dtype=np.int32)
    d_out_tmae = cuda.device_array(n, dtype=np.int32)
    d_out_reason = cuda.device_array(n, dtype=np.int32)

    # Copy inputs to device
    d_directions = cuda.to_device(arrays["directions"], stream=stream)
    d_entry = cuda.to_device(arrays["entry_prices"], stream=stream)
    d_stop = cuda.to_device(arrays["stop_prices"], stream=stream)
    d_target = cuda.to_device(arrays["target_prices"], stream=stream)
    d_risk = cuda.to_device(arrays["entry_risks"], stream=stream)
    d_close = cuda.to_device(arrays["close_prices"], stream=stream)
    d_avail = cuda.to_device(arrays["available_bars"], stream=stream)
    d_high = cuda.to_device(arrays["high_data"], stream=stream)
    d_low = cuda.to_device(arrays["low_data"], stream=stream)

    # Launch kernel
    threads_per_block = 256
    blocks = (n + threads_per_block - 1) // threads_per_block

    batch_path_kernel[blocks, threads_per_block, stream](
        d_directions, d_entry, d_stop, d_target, d_risk, d_close, d_avail,
        d_high, d_low,
        d_out_rg, d_out_ep, d_out_ei, d_out_hd,
        d_out_mfe, d_out_mae, d_out_mfe_r, d_out_mae_r,
        d_out_tmfe, d_out_tmae, d_out_reason,
        max_bars,
    )

    # Copy results back
    out = {
        "realized_gross": d_out_rg.copy_to_host(stream=stream),
        "exit_price": d_out_ep.copy_to_host(stream=stream),
        "exit_idx": d_out_ei.copy_to_host(stream=stream),
        "hold_dur": d_out_hd.copy_to_host(stream=stream),
        "mfe": d_out_mfe.copy_to_host(stream=stream),
        "mae": d_out_mae.copy_to_host(stream=stream),
        "mfe_r": d_out_mfe_r.copy_to_host(stream=stream),
        "mae_r": d_out_mae_r.copy_to_host(stream=stream),
        "t_mfe": d_out_tmfe.copy_to_host(stream=stream),
        "t_mae": d_out_tmae.copy_to_host(stream=stream),
        "exit_reason": d_out_reason.copy_to_host(stream=stream),
    }

    return out


def run_batch_cpu(
    arrays: dict,
) -> dict:
    """Run batch path simulation on CPU (njit parallel fallback)."""
    n = len(arrays["directions"])
    out_rg = np.empty(n, dtype=np.float64)
    out_ep = np.empty(n, dtype=np.float64)
    out_ei = np.empty(n, dtype=np.int32)
    out_hd = np.empty(n, dtype=np.int32)
    out_mfe = np.empty(n, dtype=np.float64)
    out_mae = np.empty(n, dtype=np.float64)
    out_mfe_r = np.empty(n, dtype=np.float64)
    out_mae_r = np.empty(n, dtype=np.float64)
    out_tmfe = np.empty(n, dtype=np.int32)
    out_tmae = np.empty(n, dtype=np.int32)
    out_reason = np.empty(n, dtype=np.int32)

    batch_path_cpu_parallel(
        arrays["directions"], arrays["entry_prices"], arrays["stop_prices"],
        arrays["target_prices"], arrays["entry_risks"], arrays["close_prices"],
        arrays["available_bars"], arrays["high_data"], arrays["low_data"],
        out_rg, out_ep, out_ei, out_hd,
        out_mfe, out_mae, out_mfe_r, out_mae_r,
        out_tmfe, out_tmae, out_reason,
    )

    return {
        "realized_gross": out_rg,
        "exit_price": out_ep,
        "exit_idx": out_ei,
        "hold_dur": out_hd,
        "mfe": out_mfe,
        "mae": out_mae,
        "mfe_r": out_mfe_r,
        "mae_r": out_mae_r,
        "t_mfe": out_tmfe,
        "t_mae": out_tmae,
        "exit_reason": out_reason,
    }
