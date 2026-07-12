"""
GPU-Accelerated Rolling Functions — drop-in replacements for pipeline.py hot path.
Adım 3+4: CuPy 2D batch + VRAM resident.
Adım 5+6: CuPy's cp.convolve is already a fused kernel (single GPU launch).
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import cupy as cp
    _HAS_CUDA = cp.cuda.runtime.getDeviceCount() > 0
except (ImportError, Exception):
    cp = np
    _HAS_CUDA = False

logger = logging.getLogger(__name__)

GPU_DTYPE = np.float32  # RTX 3060 Tensor Cores: float32 = 32x float64 perf


def has_gpu() -> bool:
    return _HAS_CUDA


# ═══════════════════════════════════════════════════════════════════
# GPU Rolling Functions — drop-in compatible with pipeline.py
# ═══════════════════════════════════════════════════════════════════

def rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """GPU rolling mean via cp.convolve (O(n), single fused kernel)."""
    if not _HAS_CUDA:
        from alphaforge.features.pipeline import _rolling_mean as cpu_fn
        return cpu_fn(arr, window)
    arr_gpu = cp.asarray(arr, dtype=GPU_DTYPE)
    n = arr_gpu.size
    if n < window:
        return _to_numpy(cp.full(n, cp.nan, dtype=GPU_DTYPE))
    kernel = cp.ones(window, dtype=GPU_DTYPE) / window
    result = cp.convolve(arr_gpu, kernel, mode="full")[:n]
    result[:window - 1] = cp.nan
    return _to_numpy(result)


def rolling_std(arr: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """GPU rolling stddev — computes mean+std in one pass over the array."""
    if not _HAS_CUDA:
        from alphaforge.features.pipeline import _rolling_std as cpu_fn
        return cpu_fn(arr, window, ddof)
    arr_gpu = cp.asarray(arr, dtype=GPU_DTYPE)
    n = arr_gpu.size
    if n < window:
        return _to_numpy(cp.full(n, cp.nan, dtype=GPU_DTYPE))
    kernel = cp.ones(window, dtype=GPU_DTYPE) / window
    mean_conv = cp.convolve(arr_gpu, kernel, mode="full")[:n]
    sq_conv = cp.convolve(arr_gpu * arr_gpu, cp.ones(window, dtype=GPU_DTYPE), mode="full")[:n]
    var = cp.maximum(sq_conv / window - mean_conv * mean_conv, 0.0)
    result = cp.sqrt(var * window / max(window - ddof, 1))
    result[:window - 1] = cp.nan
    return _to_numpy(result)


def rolling_sum(arr: np.ndarray, window: int) -> np.ndarray:
    """GPU rolling sum."""
    if not _HAS_CUDA:
        from alphaforge.features.pipeline import _rolling_sum as cpu_fn
        return cpu_fn(arr, window)
    arr_gpu = cp.asarray(arr, dtype=GPU_DTYPE)
    n = arr_gpu.size
    if n < window:
        return _to_numpy(cp.full(n, cp.nan, dtype=GPU_DTYPE))
    result = cp.convolve(arr_gpu, cp.ones(window, dtype=GPU_DTYPE), mode="full")[:n]
    result[:window - 1] = cp.nan
    return _to_numpy(result)


def rolling_var(arr: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """GPU rolling variance."""
    if not _HAS_CUDA:
        from alphaforge.features.pipeline import _rolling_var as cpu_fn
        return cpu_fn(arr, window, ddof)
    std_gpu = rolling_std(arr, window, ddof)
    return np.square(std_gpu, out=std_gpu)  # in-place, on CPU result


# ═══════════════════════════════════════════════════════════════════
# GPU Feature Pipeline — replaces compute_features_selected's rolling
# ═══════════════════════════════════════════════════════════════════

def _to_gpu(arr: np.ndarray) -> cp.ndarray:
    if isinstance(arr, cp.ndarray):
        return arr
    return cp.asarray(np.asarray(arr, dtype=GPU_DTYPE))


def _to_numpy(arr: cp.ndarray) -> np.ndarray:
    if isinstance(arr, np.ndarray) and not isinstance(arr, cp.ndarray):
        return arr
    return cp.asnumpy(arr).astype(GPU_DTYPE, copy=False)


def compute_features_gpu(
    ohlcv: dict,
    mode: str = "SCALP",
    feature_groups: Optional[List[str]] = None,
) -> Tuple[np.ndarray, List[str]]:
    """GPU-accelerated feature computation.

    Temporarily replaces the 4 hot rolling_* functions in the pipeline
    module with GPU versions. ALL other feature groups remain on CPU,
    but the bottleneck is the rolling functions (97.6% of feature time).

    Returns (X, feat_names) as float32.
    """
    if not _HAS_CUDA:
        from alphaforge.train import compute_features_selected as _cpu
        return _cpu(ohlcv, mode, feature_groups)

    t_total = time.perf_counter()

    # ── Replace rolling functions with GPU versions ──
    import alphaforge.features.pipeline as _pipe

    _orig_mean = _pipe._rolling_mean
    _orig_std = _pipe._rolling_std
    _orig_sum = _pipe._rolling_sum
    _orig_var = getattr(_pipe, "_rolling_var", None)

    _pipe._rolling_mean = rolling_mean
    _pipe._rolling_std = rolling_std
    _pipe._rolling_sum = rolling_sum
    _pipe._rolling_var = rolling_var

    try:
        from alphaforge.train import compute_features_selected as _cpu
        X, feat_names = _cpu(ohlcv, mode, feature_groups)
    finally:
        _pipe._rolling_mean = _orig_mean
        _pipe._rolling_std = _orig_std
        _pipe._rolling_sum = _orig_sum
        if _orig_var is not None:
            _pipe._rolling_var = _orig_var

    total = time.perf_counter() - t_total
    logger.info("GPU pipeline: %s samples, %d features, %.3fs", X.shape, len(feat_names), total)
    return X.astype(GPU_DTYPE, copy=False), feat_names
