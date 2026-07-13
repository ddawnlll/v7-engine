"""#277: Paper accounting bridge — R/cost accounting for paper trades.

Computes simulation-equivalent R using authority formula:
  1R = ATR × stop_multiplier

Wire AlphaRunner signals here to produce paper trades with cost accounting.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def compute_with_simulation_r(
    entry_price: float,
    exit_price: float,
    atr: float,
    stop_multiplier: float,
    direction: str,
    fee_bps: float = 8.0,
) -> dict:
    """Compute paper trade metrics using simulation R formula.

    Args:
        entry_price: Entry price
        exit_price: Exit price
        atr: ATR value at entry
        stop_multiplier: Stop multiplier from profile
        direction: "LONG" or "SHORT"
        fee_bps: Round-trip fee in bps (default 8.0)

    Returns:
        dict with realized_r, fee_cost_r, net_r
    """
    one_r = atr * stop_multiplier
    if one_r <= 0:
        return {"realized_r": 0.0, "fee_cost_r": 0.0, "net_r": 0.0}

    if direction.upper() == "LONG":
        realized_r = (exit_price - entry_price) / one_r
    else:
        realized_r = (entry_price - exit_price) / one_r

    fee_cost_r = (fee_bps / 10000.0) * entry_price / one_r
    net_r = realized_r - fee_cost_r

    return {
        "realized_r": round(realized_r, 6),
        "fee_cost_r": round(fee_cost_r, 6),
        "net_r": round(net_r, 6),
    }


def wire_alpha_runner_signal(signal: dict, mode: str = "SCALP") -> Optional[dict]:
    """Wire an AlphaRunner signal dict into paper accounting.

    Args:
        signal: AlphaRunner signal with keys: symbol, entry_price, atr, direction
        mode: Trading mode for profile lookup

    Returns:
        Paper trade result dict, or None if signal is invalid.
    """
    try:
        from lib.config_training import load_training_config
        cfg = load_training_config(mode)
        result = compute_with_simulation_r(
            entry_price=signal["entry_price"],
            exit_price=signal.get("exit_price", signal["entry_price"] * 1.01),
            atr=signal.get("atr", signal["entry_price"] * 0.01),
            stop_multiplier=cfg.stop_multiplier,
            direction=signal.get("direction", "LONG"),
        )
        result["symbol"] = signal["symbol"]
        result["mode"] = mode
        result["leverage"] = cfg.get("leverage", 1) if hasattr(cfg, "get") else 1
        return result
    except Exception as e:
        logger.warning("Paper accounting failed for signal: %s", e)
        return None
