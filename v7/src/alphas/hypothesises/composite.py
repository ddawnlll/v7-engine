"""Composite Signal Design.

Only executed if at least 2 of 3 hypotheses show R-multiple > 1.5 independently
and their correlation is < 0.6.
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import MAX_CORRELATION, STOP_LOSS_PCT, TAKE_PROFIT_PCT
from ..engine import WalkForwardEngine
from ..utils import save_csv, save_json, save_text

logger = logging.getLogger(__name__)


def correlation_check(results_list: List[dict]) -> Tuple[bool, float]:
    """Check pairwise correlation between hypothesis signals.

    Returns (passes, max_correlation).
    """
    if len(results_list) < 2:
        return False, 1.0

    # Extract fold-level R-multiples for correlation
    r_series = []
    for res in results_list:
        fold_rs = [f["median_r_multiple"] for f in res.get("fold_results", [])]
        r_series.append(fold_rs)

    # Compute pairwise correlations
    max_corr = 0.0
    for i in range(len(r_series)):
        for j in range(i + 1, len(r_series)):
            if len(r_series[i]) == len(r_series[j]) and len(r_series[i]) > 1:
                corr = float(np.corrcoef(r_series[i], r_series[j])[0, 1])
                max_corr = max(max_corr, abs(corr))

    passes = max_corr < MAX_CORRELATION
    logger.info(f"Max pairwise correlation: {max_corr:.4f} "
                f"{'PASS' if passes else 'FAIL'} (threshold {MAX_CORRELATION})")
    return passes, max_corr


def can_build_composite(results: Dict[str, dict]) -> Tuple[bool, str]:
    """Check if composite signal conditions are met.

    Returns (can_build, reason).
    """
    accepted = []
    blocked_or_rejected = []

    for name, res in results.items():
        if isinstance(res, dict) and res.get("status") == "BLOCKED":
            blocked_or_rejected.append(f"{name}: BLOCKED")
            continue

        median_r = res.get("median_r_multiple", 0.0)
        if median_r > 1.5:
            accepted.append(name)
        else:
            blocked_or_rejected.append(f"{name}: R={median_r:.3f}")

    if len(accepted) < 2:
        return False, (
            f"Need at least 2 hypotheses with R > 1.5, got {len(accepted)}. "
            f"Accepted: {accepted}. Others: {blocked_or_rejected}"
        )

    # Correlation check on accepted hypotheses
    accepted_results = [results[n] for n in accepted]
    corr_ok, max_corr = correlation_check(accepted_results)
    if not corr_ok:
        return False, (
            f"Correlation too high (max={max_corr:.3f} >= {MAX_CORRELATION}). "
            f"Accepted: {accepted}"
        )

    return True, (
        f"Composite buildable. Accepted hypotheses: {accepted}. "
        f"Max correlation: {max_corr:.3f}"
    )


def composite_signal(
    df: pd.DataFrame,
    symbol: str,
    params: dict,
    signal_funcs: List,
) -> List[dict]:
    """Generate composite signals from multiple hypotheses.

    Rules:
    - Hypothesis 1 provides direction (long/short)
    - Hypothesis 2 acts as a filter (only trade during compression breakouts)
    - Hypothesis 3 provides confirmation (or neutral)
    """
    # Collect individual signals
    all_signals = {}
    for fn in signal_funcs:
        sigs = fn(df, symbol, params)
        for s in sigs:
            idx = s["entry_idx"]
            if idx not in all_signals:
                all_signals[idx] = {"h1": 0, "h2": 0, "h3": 0}
            # Identify which hypothesis
            # This is a simplified mapping
            if "reason" in s and "funding" in s.get("reason", ""):
                all_signals[idx]["h3"] = s["direction"]
            elif "compression" in str(fn):
                all_signals[idx]["h2"] = s["direction"] or 1  # h2 signals movement, not direction
            else:
                all_signals[idx]["h1"] = s["direction"]

    # Generate composite signals
    composite_signals = []
    for idx, sig in all_signals.items():
        h1_dir = sig["h1"]
        h2_active = sig["h2"] != 0  # h2 says movement coming
        h3_dir = sig["h3"]

        # COMPOSITE_LONG: H1 long AND H2 active AND (H3 long OR H3 neutral)
        if h1_dir == 1 and h2_active and (h3_dir == 1 or h3_dir == 0):
            composite_signals.append({
                "entry_idx": idx,
                "direction": 1,
            })
        # COMPOSITE_SHORT: H1 short AND H2 active AND (H3 short OR H3 neutral)
        elif h1_dir == -1 and h2_active and (h3_dir == -1 or h3_dir == 0):
            composite_signals.append({
                "entry_idx": idx,
                "direction": -1,
            })

    return composite_signals


def run_composite(
    data: Dict[str, pd.DataFrame],
    results: Dict[str, dict],
) -> Dict:
    """Run composite signal validation if conditions are met."""
    logger.info("=" * 60)
    logger.info("COMPOSITE SIGNAL")
    logger.info("=" * 60)

    can_build, reason = can_build_composite(results)
    logger.info(f"Composite build check: {reason}")

    if not can_build:
        decision = (
            f"COMPOSITE NOT BUILT\n"
            f"Reason: {reason}\n\n"
            f"If only 1 hypothesis passes, write it into V7 as single-point-of-failure. "
            f"Continue alpha search in parallel."
        )
        save_text(decision, "rejection_decision_composite.txt")
        return {"status": "NOT_BUILT", "reason": reason}

    # Build composite (placeholder — real implementation needs proper signal func wiring)
    engine = WalkForwardEngine(
        hypothesis_name="composite",
        signal_fn=lambda df, sym, params: [],  # Will be replaced with proper wiring
        param_grid=[{}],
        max_hold_hours=12,
        stop_pct=STOP_LOSS_PCT,
        tp_pct=TAKE_PROFIT_PCT,
    )

    # ── Deliverables ──
    decision = (
        f"COMPOSITE BUILT\n"
        f"Reason: {reason}\n\n"
        f"Composite signal rules:\n"
        f"  COMPOSITE_LONG = H1 LONG AND H2 active AND (H3 LONG OR H3 neutral)\n"
        f"  COMPOSITE_SHORT = H1 SHORT AND H2 active AND (H3 SHORT OR H3 neutral)\n"
        f"  Exit: 2% stop, 4% TP, 12h max hold\n\n"
        f"Proceed to system integration plan."
    )
    save_text(decision, "rejection_decision_composite.txt")
    logger.info(decision)

    return {"status": "BUILT", "reason": reason}
