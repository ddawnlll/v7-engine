"""Symbol + Regime Stability Metrics — Issue #116.

Replaces placeholder stability metrics with real data:
  - Per-symbol: expectancy_r, win_rate, trade_count
  - Per-regime (TREND_UP/DOWN/RANGE/TRANSITION): expectancy_r, win_rate
  - Symbol concentration ratio (top symbol %)
  - Regime concentration ratio
  - Regime classification from OHLCV (ma_50 > ma_200, atr_ratio)

Design:
  - Pure computation functions: given structured trade/price data, produce
    stability metrics.
  - No ML imports (numpy only for regime classification).
  - Each function is independently testable.

Authority: AlphaForge / reporting.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from alphaforge.features.regime import classify_regime, regime_counts
from alphaforge.features.regime import Regime, RegimeSignal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STABILITY_REGIME_LABELS: List[str] = ["TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION"]


# ---------------------------------------------------------------------------
# Per-symbol metrics
# ---------------------------------------------------------------------------

def compute_symbol_metrics(
    per_symbol_oos: Dict[str, Dict[str, float]],
) -> Dict[str, Dict[str, float]]:
    """Compute per-symbol stability metrics from per-symbol OOS data.

    Args:
        per_symbol_oos: Dict mapping symbol -> dict with keys:
            - "oos_expectancy_r": float (mean expectancy_r for that symbol)
            - "oos_win_rate": float (win rate for that symbol)
            - "oos_trade_count": int (trade count for that symbol)

    Returns:
        Dict mapping symbol -> {
            "expectancy_r": float,
            "win_rate": float,
            "trade_count": int,
        }
    """
    result: Dict[str, Dict[str, float]] = {}
    for symbol, data in per_symbol_oos.items():
        result[symbol] = {
            "expectancy_r": float(data.get("oos_expectancy_r", 0.0)),
            "win_rate": float(data.get("oos_win_rate", 0.0)),
            "trade_count": int(data.get("oos_trade_count", 0)),
        }
    return result


# ---------------------------------------------------------------------------
# Concentration ratios
# ---------------------------------------------------------------------------

def compute_symbol_concentration(
    symbol_metrics: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    """Compute symbol concentration ratio.

    The concentration ratio is the fraction of total trades accounted for
    by the top-N symbols.  Returns both the top-1 share (max fraction) and
    a Herfindahl-Hirschman-like index (sum of squared shares).

    Args:
        symbol_metrics: Output of compute_symbol_metrics().

    Returns:
        Dict with keys:
            num_symbols: int
            total_trades: int
            top_symbol: str (or "NONE" if no trades)
            top_symbol_share: float (0.0-1.0)
            top_symbol_trade_count: int
            symbol_concentration_hhi: float (sum of squared trade shares)
            per_symbol_shares: Dict[str, float] (trade share per symbol)
    """
    if not symbol_metrics:
        return {
            "num_symbols": 0,
            "total_trades": 0,
            "top_symbol": "NONE",
            "top_symbol_share": 0.0,
            "top_symbol_trade_count": 0,
            "symbol_concentration_hhi": 0.0,
            "per_symbol_shares": {},
        }

    # Compute trade counts and shares
    trade_counts: Dict[str, int] = {
        sym: data.get("trade_count", 0)
        for sym, data in symbol_metrics.items()
    }
    total_trades = sum(trade_counts.values())

    if total_trades == 0:
        shares = {sym: 0.0 for sym in trade_counts}
        return {
            "num_symbols": len(symbol_metrics),
            "total_trades": 0,
            "top_symbol": "NONE",
            "top_symbol_share": 0.0,
            "top_symbol_trade_count": 0,
            "symbol_concentration_hhi": 0.0,
            "per_symbol_shares": shares,
        }

    shares = {
        sym: cnt / total_trades
        for sym, cnt in trade_counts.items()
    }

    # Top symbol
    top_symbol = max(trade_counts, key=lambda k: trade_counts[k])  # type: ignore[arg-type]
    top_share = shares[top_symbol]
    top_count = trade_counts[top_symbol]

    # Herfindahl-Hirschman Index (sum of squared shares)
    hhi = sum(s ** 2 for s in shares.values())

    return {
        "num_symbols": len(symbol_metrics),
        "total_trades": total_trades,
        "top_symbol": top_symbol,
        "top_symbol_share": round(top_share, 6),
        "top_symbol_trade_count": top_count,
        "symbol_concentration_hhi": round(hhi, 6),
        "per_symbol_shares": {sym: round(sh, 6) for sym, sh in shares.items()},
    }


def compute_feature_concentration(
    importance_dict: Dict[str, float],
) -> Dict[str, Any]:
    """Compute feature concentration from a feature importance dict.

    Same HHI/top-1 share pattern as compute_symbol_concentration, but for
    feature importance shares instead of trade shares.

    Args:
        importance_dict: Dict mapping feature_name -> importance (gain/weight).

    Returns:
        Dict with keys:
            num_features, total_importance, top_feature, top_feature_share,
            feature_concentration_hhi, per_feature_shares, top3_features, top3_share.
    """
    if not importance_dict:
        return {
            "num_features": 0,
            "total_importance": 0.0,
            "top_feature": "NONE",
            "top_feature_share": 0.0,
            "feature_concentration_hhi": 0.0,
            "per_feature_shares": {},
            "top3_features": [],
            "top3_share": 0.0,
        }

    total = sum(importance_dict.values())
    if total == 0:
        features = list(importance_dict.keys())
        return {
            "num_features": len(features),
            "total_importance": 0.0,
            "top_feature": "NONE",
            "top_feature_share": 0.0,
            "feature_concentration_hhi": 0.0,
            "per_feature_shares": {f: 0.0 for f in features},
            "top3_features": features[:3],
            "top3_share": 0.0,
        }

    shares = {name: val / total for name, val in importance_dict.items()}
    top_feature = max(shares, key=lambda k: shares[k])
    top_share = shares[top_feature]
    hhi = sum(s ** 2 for s in shares.values())
    sorted_by_share = sorted(shares.items(), key=lambda x: -x[1])
    top3 = [name for name, _ in sorted_by_share[:3]]
    top3_share_sum = sum(shares[n] for n in top3)

    return {
        "num_features": len(importance_dict),
        "total_importance": total,
        "top_feature": top_feature,
        "top_feature_share": round(top_share, 6),
        "feature_concentration_hhi": round(hhi, 6),
        "per_feature_shares": {name: round(sh, 6) for name, sh in shares.items()},
        "top3_features": top3,
        "top3_share": round(top3_share_sum, 6),
    }


def compute_regime_concentration(
    regime_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute regime concentration from regime breakdown entries.

    Args:
        regime_entries: List of regime dicts, each with "regime" and
            "sample_pct" (or "trade_count") keys.  Values are treated as
            fractions (not percentages).

    Returns:
        Dict with keys:
            num_regimes: int
            top_regime: str (or "NONE")
            top_regime_share: float
            regime_concentration_hhi: float
            per_regime_shares: Dict[str, float]
    """
    if not regime_entries:
        return {
            "num_regimes": 0,
            "top_regime": "NONE",
            "top_regime_share": 0.0,
            "regime_concentration_hhi": 0.0,
            "per_regime_shares": {},
        }

    # Extract shares
    shares: Dict[str, float] = {}
    for entry in regime_entries:
        regime = entry.get("regime", "UNKNOWN")
        # Use sample_pct if available, otherwise equal share
        share = float(entry.get("sample_pct", 1.0 / len(regime_entries)))
        shares[regime] = share

    # Normalise to sum to 1.0 (in case sample_pct values are raw counts
    # or don't sum exactly)
    total = sum(shares.values())
    if total > 0:
        shares = {k: v / total for k, v in shares.items()}
    else:
        shares = {k: 0.0 for k in shares}

    top_regime = max(shares, key=lambda k: shares[k])  # type: ignore[arg-type]
    top_share = shares[top_regime]

    hhi = sum(s ** 2 for s in shares.values())

    return {
        "num_regimes": len(regime_entries),
        "top_regime": top_regime,
        "top_regime_share": round(top_share, 6),
        "regime_concentration_hhi": round(hhi, 6),
        "per_regime_shares": {r: round(s, 6) for r, s in shares.items()},
    }


# ---------------------------------------------------------------------------
# Combined stability section builder
# ---------------------------------------------------------------------------

def build_stability_section(
    wfv_results: dict,
) -> Dict[str, Any]:
    """Build a stability metrics section from WFV results.

    Reads per-symbol OOS data from ``wfv_results["per_symbol_oos"]``
    when available.  Falls back to single-symbol aggregate from
    ``wfv_results["oos_summary"]``.

    Reads regime breakdown from ``wfv_results["regime_breakdown"]`` and
    adds concentration ratios.

    Args:
        wfv_results: Walk-forward validation results dict.

    Returns:
        Dict with keys:
            symbol_metrics: dict of per-symbol metrics (or empty).
            symbol_concentration: dict of symbol concentration ratios.
            regime_concentration: dict of regime concentration ratios.
            num_symbols: int
    """
    # --- Per-symbol OOS metrics ---------------------------------------
    per_symbol_oos = wfv_results.get("per_symbol_oos", {})
    if per_symbol_oos:
        symbol_metrics = compute_symbol_metrics(per_symbol_oos)
    else:
        # Fall back to single-symbol aggregate from oos_summary
        oos_summary = wfv_results.get("oos_summary", {})
        data_scope = wfv_results.get("data_scope", {})
        symbols = data_scope.get("symbols", ["BTCUSDT"])
        symbol_metrics = {}
        for sym in symbols:
            symbol_metrics[sym] = {
                "expectancy_r": oos_summary.get("oos_expectancy_r", 0.0),
                "win_rate": oos_summary.get("oos_win_rate", 0.5),
                "trade_count": oos_summary.get("oos_trade_count", 0),
            }

    # --- Symbol concentration -----------------------------------------
    symbol_concentration = compute_symbol_concentration(symbol_metrics)

    # --- Regime concentration -----------------------------------------
    regime_data = wfv_results.get("regime_breakdown", {})
    regime_entries = regime_data.get("regimes", [])
    regime_concentration = compute_regime_concentration(regime_entries)

    return {
        "symbol_metrics": symbol_metrics,
        "symbol_concentration": symbol_concentration,
        "regime_concentration": regime_concentration,
        "num_symbols": len(symbol_metrics),
    }


# ---------------------------------------------------------------------------
# OHLCV regime classification (Issue #116)
# ---------------------------------------------------------------------------

def classify_symbol_regimes_from_ohlcv(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
) -> Dict[str, Any]:
    """Classify a single-symbol price series into V7 regimes.

    Uses the existing ``classify_regime`` from
    ``alphaforge.features.regime`` (ma_50 > ma_200 slope, ATR ratio).

    Args:
        closes: Close prices (oldest first).
        highs: High prices (same length).
        lows: Low prices (same length).

    Returns:
        Dict with keys:
            regime_counts: Dict[str, int] — count per regime.
            regime_fractions: Dict[str, float] — fraction per regime.
            total_bars: int — number of classified bars (excludes
                insufficient-lookback prefix).
            last_regime: str — predominant regime at the last bar.
            classification_rate: float — fraction of total bars that
                received a non-TRANSITION classification.
    """
    if len(closes) == 0:
        return {
            "regime_counts": {r: 0 for r in STABILITY_REGIME_LABELS},
            "regime_fractions": {r: 0.0 for r in STABILITY_REGIME_LABELS},
            "total_bars": 0,
            "last_regime": "NONE",
            "classification_rate": 0.0,
        }

    try:
        signals = classify_regime(closes, highs, lows)
    except ValueError:
        return {
            "regime_counts": {r: 0 for r in STABILITY_REGIME_LABELS},
            "regime_fractions": {r: 0.0 for r in STABILITY_REGIME_LABELS},
            "total_bars": 0,
            "last_regime": "NONE",
            "classification_rate": 0.0,
        }

    total_bars = len(signals)

    counts = regime_counts(signals)

    # Fraction of total bars (including insufficient-lookback prefix)
    fractions = {
        r: counts.get(r, 0) / total_bars
        for r in STABILITY_REGIME_LABELS
    }

    # Classification rate: non-TRANSITION bars / total bars
    non_transition = total_bars - counts.get("TRANSITION", 0)
    classification_rate = non_transition / total_bars if total_bars > 0 else 0.0

    # Last bar's regime
    last_signal = signals[-1]
    last_regime = last_signal.regime.value if last_signal else "NONE"

    return {
        "regime_counts": {r: counts.get(r, 0) for r in STABILITY_REGIME_LABELS},
        "regime_fractions": fractions,
        "total_bars": total_bars,
        "last_regime": last_regime,
        "classification_rate": round(classification_rate, 6),
    }
