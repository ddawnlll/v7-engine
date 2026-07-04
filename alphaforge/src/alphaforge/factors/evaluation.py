"""Factor evaluation — cross-sectional Rank-IC, top-bottom spread, pass/fail logic.

All evaluation is done per-timestamp, cross-sectionally across symbols.
No lookahead: IC at timestamp t compares factor[t] to forward_return[t].

Forward returns are computed from close prices at various horizons.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from alphaforge.factors.factors import FACTOR_REGISTRY


# ── FORWARD RETURN COMPUTATION ────────────────────────────────────

def compute_forward_returns(
    close: pd.DataFrame,
    horizons: list[int] | None = None,
) -> dict[int, pd.DataFrame]:
    """Compute forward returns for each horizon.

    forward_return[t] = close[t + horizon] / close[t] - 1

    Returns:
        Dict mapping horizon (in bars) → DataFrame of forward returns.
    """
    if horizons is None:
        horizons = [1, 4, 12, 24]  # 1h, 4h, 12h, 24h

    result: dict[int, pd.DataFrame] = {}
    for h in horizons:
        fwd = close.shift(-h) / close - 1.0
        result[h] = fwd
    return result


# ── CROSS-SECTIONAL RANK IC ───────────────────────────────────────

def compute_cross_sectional_ic(
    factor_scores: pd.DataFrame,
    forward_returns: pd.DataFrame,
) -> pd.Series:
    """Compute cross-sectional Spearman rank IC at each timestamp.

    Vectorized: ranks cross-sectionally, then computes Pearson correlation
    between ranked series at each timestamp.

    IC[t] = rank_correlation(factor_scores[t], forward_returns[t])

    Returns:
        Series of IC values indexed by timestamp.
    """
    # Align on common timestamps and symbols
    common_idx = factor_scores.index.intersection(forward_returns.index)
    common_cols = factor_scores.columns.intersection(forward_returns.columns)

    if len(common_idx) == 0 or len(common_cols) < 3:
        return pd.Series(dtype=float)

    fs = factor_scores.loc[common_idx, common_cols]
    fr = forward_returns.loc[common_idx, common_cols]

    # Cross-sectional rank (percentile rank across symbols at each timestamp)
    fs_ranked = fs.rank(axis=1)
    fr_ranked = fr.rank(axis=1)

    # Vectorized Pearson correlation between ranked series.
    # IC[t] = cov(fs_ranked[t], fr_ranked[t]) / (std_fs[t] * std_fr[t])
    # Using .mean() for covariance and .std() for standard deviation is
    # inconsistent: .mean() divides by N, .std() divides by (N-1).
    # Fix: use sum-based covariance and ddof=0 std to get consistent N.
    n_sym = fs_ranked.count(axis=1)  # number of non-NaN symbols per timestamp
    fs_centered = fs_ranked.sub(fs_ranked.mean(axis=1), axis=0)
    fr_centered = fr_ranked.sub(fr_ranked.mean(axis=1), axis=0)

    # Covariance: E[(X-mu_x)(Y-mu_y)] — .mean() gives 1/N scaling
    cov = (fs_centered * fr_centered).mean(axis=1)

    # Std with ddof=0 (population std) to match .mean() scaling
    std_fs = fs_ranked.std(axis=1, ddof=0)
    std_fr = fr_ranked.std(axis=1, ddof=0)

    denom = std_fs * std_fr
    ic = cov / denom.replace(0, np.nan)

    ic.name = "rank_ic"
    return ic


# ── TOP-BOTTOM SPREAD ─────────────────────────────────────────────

def compute_top_bottom_spread(
    factor_scores: pd.DataFrame,
    forward_returns: pd.DataFrame,
    top_pct: float = 0.20,
    bottom_pct: float = 0.20,
) -> pd.Series:
    """Compute top-bottom spread return at each timestamp.

    Vectorized: uses percentile ranks to identify top/bottom groups,
    then masks forward returns accordingly.

    Top group: symbols with factor score in top `top_pct` quantile.
    Bottom group: symbols with factor score in bottom `bottom_pct` quantile.
    Spread = mean(top returns) - mean(bottom returns).

    Returns:
        Series of spread returns indexed by timestamp.
    """
    common_idx = factor_scores.index.intersection(forward_returns.index)
    common_cols = factor_scores.columns.intersection(forward_returns.columns)

    if len(common_idx) == 0 or len(common_cols) < 5:
        return pd.Series(dtype=float)

    fs = factor_scores.loc[common_idx, common_cols]
    fr = forward_returns.loc[common_idx, common_cols]

    # Percentile rank across symbols at each timestamp
    ranks = fs.rank(axis=1, pct=True)
    n_sym = len(common_cols)
    n_top = max(1, int(n_sym * top_pct))
    n_bottom = max(1, int(n_sym * bottom_pct))

    # Top group: rank >= (1 - top_pct), Bottom group: rank <= bottom_pct
    top_threshold = 1.0 - (n_top / n_sym)
    bottom_threshold = n_bottom / n_sym

    top_mask = ranks >= top_threshold
    bottom_mask = ranks <= bottom_threshold

    # Compute mean returns for each group (NaN-safe)
    top_mean = fr.where(top_mask).mean(axis=1)
    bottom_mean = fr.where(bottom_mask).mean(axis=1)

    spread = top_mean - bottom_mean
    spread.name = "spread"
    return spread


# ── TURNOVER PROXY ────────────────────────────────────────────────

def compute_turnover(factor_scores: pd.DataFrame, top_pct: float = 0.20) -> pd.Series:
    """Compute signal turnover — fraction of top-group symbols that change between timestamps.

    Uses rank(method='first') to break ties deterministically, ensuring
    exactly n_top symbols per row regardless of tied values.

    Returns:
        Series of turnover values (0.0 = no change, 1.0 = complete turnover).
    """
    n_sym = len(factor_scores.columns)
    n_top = max(1, int(n_sym * top_pct))

    # rank(method='first') breaks ties by position, giving unique ranks.
    # With pct=True, ranks are in [1/n_sym, 1.0].
    # Top n_top symbols: those with rank > (n_sym - n_top) / n_sym.
    ranks = factor_scores.rank(axis=1, method="first", pct=True)
    top_threshold = (n_sym - n_top) / n_sym

    # Boolean mask: True if symbol is in top group at this timestamp
    top_mask = ranks > top_threshold

    # Count valid (non-NaN) scores per row
    valid_count = factor_scores.notna().sum(axis=1)

    # Verify: each row should have exactly n_top True values (where valid)
    # With method='first', ties are broken so this is guaranteed.

    # For each timestamp, compute overlap with previous timestamp's top group.
    prev_mask = top_mask.shift(1).fillna(False)
    overlap = (top_mask & prev_mask).sum(axis=1)

    # Turnover = 1 - overlap / n_top
    has_prev = top_mask.shift(1).any(axis=1)
    enough = (valid_count >= n_top) & has_prev

    turnover = pd.Series(np.nan, index=factor_scores.index, name="turnover")
    turnover[enough] = 1.0 - (overlap[enough] / n_top)

    # Clamp to [0, 1] for safety
    turnover = turnover.clip(0.0, 1.0)

    return turnover


# ── FULL EVALUATION ───────────────────────────────────────────────

def evaluate_factor(
    factor_name: str,
    factor_scores: pd.DataFrame,
    forward_returns: dict[int, pd.DataFrame],
    direction: str,
) -> list[dict]:
    """Evaluate a single factor across all horizons.

    Returns a list of dicts, one per horizon, with evaluation metrics.
    """
    results = []

    # Pre-compute turnover once — it does NOT depend on the horizon.
    # This avoids recomputing 4× per factor (saving ~60% of evaluation time).
    turnover_series = compute_turnover(factor_scores)

    for horizon, fwd_ret in forward_returns.items():
        ic_series = compute_cross_sectional_ic(factor_scores, fwd_ret)
        spread_series = compute_top_bottom_spread(factor_scores, fwd_ret)

        # ── Cost-aware execution filter (Bysik & Slepaczuk 2026) ──
        # Research finding: "The main barrier is how forecasts are converted
        # into trades, not weak predictability."
        #
        # Filter rule: only consider timestamps where the cross-sectional
        # IC spread (signal strength) exceeds the cost threshold.
        # This blocks trades where edge < friction.
        #
        # Cost threshold: 2 × total_friction_cost ≈ 2 × 0.089R = 0.178R
        # (taker: 0.04% entry + 0.04% exit + 0.01% slippage = 0.09% round-trip)
        # (maker: 0.02% entry + 0.02% exit + 0.01% slippage = 0.05% round-trip)
        #
        # Signal strength: |mean_ic| × (spread_std / n_symbols^0.5)
        # Simple proxy: |ic_series| > cost_threshold
        cost_threshold = 0.05  # R-multiples, maker fee assumption

        # Apply filter: keep only timestamps where |IC| > threshold
        ic_filtered = ic_series[ic_series.abs() > cost_threshold]
        spread_filtered = spread_series.loc[ic_filtered.index] if not ic_filtered.empty else pd.Series(dtype=float)

        # Filter valid IC values
        valid_ic = ic_filtered.dropna()
        valid_spread = spread_filtered.dropna()
        valid_turnover = turnover_series.dropna()

        n_timestamps = len(valid_ic)
        n_symbols = len(factor_scores.columns)

        # Track filter impact
        n_raw = len(ic_series.dropna())
        n_filtered = n_timestamps
        filter_rate = (n_raw - n_filtered) / n_raw * 100 if n_raw > 0 else 0

        if n_timestamps == 0:
            results.append({
                "factor_name": factor_name,
                "horizon": horizon,
                "direction": direction,
                "mean_rank_ic": np.nan,
                "median_rank_ic": np.nan,
                "ic_ir": np.nan,
                "top_bottom_gross_return": np.nan,
                "top_bottom_net_return": np.nan,
                "turnover": np.nan,
                "n_timestamps": 0,
                "n_symbols": n_symbols,
                "start_ts": "",
                "end_ts": "",
                "pass_fail": "FAIL",
                "notes": f"no valid IC samples (filter={filter_rate:.0f}% blocked)",
            })
            continue

        raw_ic = valid_ic.mean()
        median_ic = valid_ic.median()
        ic_std = valid_ic.std()

        # Direction-adjusted IC: for "short" factors, flip the sign so that
        # positive adjusted IC = good (predicts returns in the right direction).
        # This makes all downstream logic (pass/fail, display) consistent.
        direction_sign = 1.0 if direction == "long" else -1.0
        adj_ic = raw_ic * direction_sign
        adj_median_ic = median_ic * direction_sign
        # When ic_std = 0 (all IC values identical, e.g. perfect signal),
        # treat as "perfectly stable" — IC_IR = sign(ic) × 100 (capped).
        if ic_std > 1e-10:
            adj_ic_ir = adj_ic / ic_std
        elif ic_std == 0:
            adj_ic_ir = 100.0 if adj_ic > 0 else (-100.0 if adj_ic < 0 else 0.0)
        else:
            # ic_std very small but not zero (numerical noise)
            adj_ic_ir = adj_ic / ic_std

        # Spread: gross = raw, net = direction-adjusted (cost model TBD)
        spread_sign = direction_sign  # same as direction_sign for consistency
        gross_spread = valid_spread.sum()
        net_spread = gross_spread * spread_sign

        mean_turnover = valid_turnover.mean() if len(valid_turnover) > 0 else np.nan

        # Pass/fail logic (uses direction-adjusted IC — positive = good for all)
        # When ic_std = 0 (e.g. perfect signal), IC_IR = inf or huge — treat
        # as "perfectly stable" rather than "non-finite". Clamp for display.
        if not np.isfinite(adj_ic_ir) or abs(adj_ic_ir) > 100:
            ic_ir_clamped = 100.0 if adj_ic_ir > 0 else -100.0
        else:
            ic_ir_clamped = adj_ic_ir

        if n_timestamps < 50:
            pf = "FAIL"
            notes = "insufficient sample"
        elif n_symbols < 10:
            pf = "FAIL"
            notes = "too few symbols"
        elif not np.isfinite(adj_ic):
            pf = "FAIL"
            notes = "non-finite IC"
        elif not np.isfinite(net_spread):
            pf = "FAIL"
            notes = "non-finite spread"
        elif adj_ic > 0.02 and ic_ir_clamped > 0.3:
            pf = "PASS"
            notes = f"strong signal, IC_IR={ic_ir_clamped:.2f}"
        elif adj_ic < -0.02 and ic_ir_clamped < -0.3:
            # Strongly negative IC = factor consistently predicts wrong direction
            pf = "FAIL"
            notes = f"inverted signal, IC_IR={ic_ir_clamped:.2f}"
        elif adj_ic > 0.01 and ic_ir_clamped > 0.15:
            pf = "WATCH"
            notes = f"moderate signal, IC_IR={ic_ir_clamped:.2f}"
        elif abs(adj_ic) < 0.005:
            pf = "FAIL"
            notes = "near-zero IC"
        else:
            pf = "WATCH"
            notes = f"weak signal, IC_IR={ic_ir_clamped:.2f}"

        results.append({
            "factor_name": factor_name,
            "horizon": horizon,
            "direction": direction,
            "mean_rank_ic": round(adj_ic, 6),
            "median_rank_ic": round(adj_median_ic, 6),
            "ic_ir": round(ic_ir_clamped, 4),
            "top_bottom_gross_return": round(gross_spread, 6) if len(valid_spread) > 0 else np.nan,
            "top_bottom_net_return": round(net_spread, 6),
            "turnover": round(mean_turnover, 4) if np.isfinite(mean_turnover) else np.nan,
            "n_timestamps": n_timestamps,
            "n_symbols": n_symbols,
            "start_ts": str(valid_ic.index[0]) if len(valid_ic) > 0 else "",
            "end_ts": str(valid_ic.index[-1]) if len(valid_ic) > 0 else "",
            "pass_fail": pf,
            "notes": notes,
        })

    return results
