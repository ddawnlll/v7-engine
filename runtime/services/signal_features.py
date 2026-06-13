"""Persisted feature-vector helpers for analyzer calibration.

This module defines the compact feature set we want to keep per signal so the
probability model can be calibrated later against real outcomes.
"""

from __future__ import annotations

from typing import Any


def build_signal_feature_vector(signal: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    probability_model = dict((signal.get("advanced_analysis") or {}).get("probability_model") or {})
    component_scores = dict(probability_model.get("component_scores") or {})
    return {
        "symbol": signal.get("symbol"),
        "interval": signal.get("interval"),
        "mode": signal.get("mode"),
        "direction": signal.get("direction"),
        "regime": signal.get("regime"),
        "trend": signal.get("trend"),
        "trend_strength": signal.get("trend_strength"),
        "confidence_raw": signal.get("confidence_raw"),
        "confidence_final": signal.get("confidence"),
        "probability_raw": signal.get("probability_raw"),
        "probability_final": signal.get("probability"),
        "expected_value": signal.get("expected_value"),
        "risk_reward": signal.get("risk_reward"),
        "return_mean": snapshot.get("return_mean"),
        "return_vol": snapshot.get("return_vol"),
        "return_skew": snapshot.get("return_skew"),
        "return_kurt": snapshot.get("return_kurt"),
        "return_zscore": snapshot.get("return_zscore"),
        "return_trend_ratio": snapshot.get("return_trend_ratio"),
        "vol_cluster_ratio": snapshot.get("vol_cluster_ratio"),
        "volatility_regime": snapshot.get("volatility_regime"),
        "atr": snapshot.get("atr"),
        "atr_5bar_avg": snapshot.get("atr_5bar_avg"),
        "atr_expanding": snapshot.get("atr_expanding"),
        "flow_imbalance": snapshot.get("flow_imbalance"),
        "buy_volume_share": snapshot.get("buy_volume_share"),
        "trade_intensity": snapshot.get("trade_intensity"),
        "orderbook_imbalance": snapshot.get("orderbook_imbalance"),
        "orderbook_spread_bps": snapshot.get("orderbook_spread_bps"),
        "orderbook_microprice_deviation_bps": snapshot.get("orderbook_microprice_deviation_bps"),
        "microstructure_source": snapshot.get("microstructure_source"),
        "rsi": snapshot.get("rsi"),
        "adx": snapshot.get("adx"),
        "vol_ratio": snapshot.get("vol_ratio"),
        "component_scores": component_scores,
    }


def merge_labeled_outcome(features: dict[str, Any] | None, outcome: dict[str, Any]) -> dict[str, Any]:
    base = dict(features or {})
    realized_r = outcome.get("realized_r")
    label = "OPEN"
    if realized_r is not None:
        try:
            value = float(realized_r)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            label = "WIN"
        elif value < 0:
            label = "LOSS"
        else:
            label = "FLAT"

    base["outcome"] = {
        "status": outcome.get("status"),
        "label": label,
        "close_reason": outcome.get("close_reason"),
        "realized_r": outcome.get("realized_r"),
        "realized_pnl": outcome.get("realized_pnl"),
        "close_price": outcome.get("close_price"),
        "closed_at_utc": outcome.get("closed_at_utc"),
    }
    base["outcome_status"] = outcome.get("status")
    base["outcome_label"] = label
    base["realized_r"] = outcome.get("realized_r")
    base["realized_pnl"] = outcome.get("realized_pnl")
    base["close_reason"] = outcome.get("close_reason")
    return base
