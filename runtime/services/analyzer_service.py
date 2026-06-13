"""Compatibility wrapper for analyzer access through the Phase 25 adapter."""

from __future__ import annotations

from runtime.services.analyzer_engine_adapter import AnalyzerEngineAdapter


def analyze_snapshot(symbol: str, interval: str, mode: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    result = AnalyzerEngineAdapter().analyze(
        symbol=symbol,
        interval=interval,
        mode=mode,
        snapshot=snapshot,
    )
    signal = dict(result.get("signal") or {})
    signal["engine_name"] = result.get("engine_name")
    signal["engine_version"] = result.get("engine_version")
    signal["engine_schema_version"] = result.get("schema_version")
    signal["engine_fallback_used"] = bool(result.get("fallback_used"))
    return signal
