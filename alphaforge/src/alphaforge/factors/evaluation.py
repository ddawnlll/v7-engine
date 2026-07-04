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

    # Vectorized Pearson correlation between ranked series
    # IC[t] = cov(fs_ranked[t], fr_ranked[t]) / (std(fs_ranked[t]) * std(fr_ranked[t]))
    fs_centered = fs_ranked.sub(fs_ranked.mean(axis=1), axis=0)
    fr_centered = fr_ranked.sub(fr_ranked.mean(axis=1), axis=0)

    cov = (fs_centered * fr_centered).mean(axis=1)
    std_fs = fs_ranked.std(axis=1)
    std_fr = fr_ranked.std(axis=1)

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

    Returns:
        Series of turnover values (0.0 = no change, 1.0 = complete turnover).
    """
    common_cols = factor_scores.columns
    n = len(common_cols)
    n_top = max(1, int(n * top_pct))

    prev_top = set()
    turnovers = []
    for ts in factor_scores.index:
        row = factor_scores.loc[ts].dropna()
        if len(row) < n_top:
            turnovers.append(np.nan)
            continue
        curr_top = set(row.nlargest(n_top).index)
        if prev_top:
            overlap = len(curr_top & prev_top)
            turnover = 1.0 - overlap / n_top
        else:
            turnover = np.nan
        turnovers.append(turnover)
        prev_top = curr_top

    return pd.Series(turnovers, index=factor_scores.index, name="turnover")


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
    close_proxy = None  # for spread return calculation

    for horizon, fwd_ret in forward_returns.items():
        ic_series = compute_cross_sectional_ic(factor_scores, fwd_ret)
        spread_series = compute_top_bottom_spread(factor_scores, fwd_ret)
        turnover_series = compute_turnover(factor_scores)

        # Filter valid IC values
        valid_ic = ic_series.dropna()
        valid_spread = spread_series.dropna()
        valid_turnover = turnover_series.dropna()

        n_timestamps = len(valid_ic)
        n_symbols = len(factor_scores.columns)

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
                "notes": "no valid IC samples",
            })
            continue

        mean_ic = valid_ic.mean()
        median_ic = valid_ic.median()
        ic_std = valid_ic.std()
        ic_ir = mean_ic / ic_std if ic_std > 0 else 0.0

        # For "short" direction factors, flip the sign of spread
        spread_sign = -1.0 if direction == "short" else 1.0
        mean_spread = valid_spread.mean() * spread_sign
        cumulative_spread = valid_spread.sum() * spread_sign

        mean_turnover = valid_turnover.mean() if len(valid_turnover) > 0 else np.nan

        # Pass/fail logic
        if n_timestamps < 50:
            pf = "FAIL"
            notes = "insufficient sample"
        elif n_symbols < 10:
            pf = "FAIL"
            notes = "too few symbols"
        elif not np.isfinite(mean_ic):
            pf = "FAIL"
            notes = "non-finite IC"
        elif not np.isfinite(cumulative_spread):
            pf = "FAIL"
            notes = "non-finite spread"
        elif mean_ic > 0.02 and ic_ir > 0.3:
            pf = "PASS"
            notes = f"strong signal, IC_IR={ic_ir:.2f}"
        elif mean_ic > 0.01 and ic_ir > 0.15:
            pf = "WATCH"
            notes = f"moderate signal, IC_IR={ic_ir:.2f}"
        elif abs(mean_ic) < 0.005:
            pf = "FAIL"
            notes = "near-zero IC"
        else:
            pf = "WATCH"
            notes = f"weak signal, IC_IR={ic_ir:.2f}"

        # Direction check: for "long" factors, positive IC is good;
        # for "short" factors, negative raw IC (before sign flip) is good
        if direction == "short" and mean_ic > 0 and pf == "PASS":
            pf = "WATCH"
            notes += " (direction mismatch: short factor has positive IC)"
        elif direction == "long" and mean_ic < 0 and pf == "PASS":
            pf = "WATCH"
            notes += " (direction mismatch: long factor has negative IC)"

        # Adjust IC sign for display based on direction
        display_ic = mean_ic if direction == "long" else -mean_ic

        results.append({
            "factor_name": factor_name,
            "horizon": horizon,
            "direction": direction,
            "mean_rank_ic": round(display_ic, 6),
            "median_rank_ic": round(median_ic * (1 if direction == "long" else -1), 6),
            "ic_ir": round(ic_ir * (1 if direction == "long" else -1), 4),
            "top_bottom_gross_return": round(valid_spread.sum(), 6) if len(valid_spread) > 0 else np.nan,
            "top_bottom_net_return": round(cumulative_spread, 6),
            "turnover": round(mean_turnover, 4) if np.isfinite(mean_turnover) else np.nan,
            "n_timestamps": n_timestamps,
            "n_symbols": n_symbols,
            "start_ts": str(valid_ic.index[0]) if len(valid_ic) > 0 else "",
            "end_ts": str(valid_ic.index[-1]) if len(valid_ic) > 0 else "",
            "pass_fail": pf,
            "notes": notes,
        })

    return results
