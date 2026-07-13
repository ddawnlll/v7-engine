"""Strict V7-Lite preregistration contract for one untouched holdout run."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


PREREGISTRATION_VERSION = "v7-lite-preregistered-holdout-1.0"


class PreregistrationValidationError(ValueError):
    """Raised when a pre-registered holdout specification is malformed."""


@dataclass(frozen=True)
class FrozenHoldoutPreregistration:
    """Non-tunable parameters for the next independent candidate evaluation."""

    candidate_id: str
    cutoff: datetime
    mode: str
    symbols: tuple[str, ...]
    features: str
    normalization: str
    confidence_threshold: float
    position_size_pct: float
    portfolio_config: Mapping[str, Any]
    output_trace_name: str


def _required_string(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PreregistrationValidationError(f"{field} must be a non-empty string")
    return value


def _parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PreregistrationValidationError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise PreregistrationValidationError(f"{field} must include a UTC offset")
    return parsed


def parse_frozen_holdout_preregistration(data: Mapping[str, Any]) -> FrozenHoldoutPreregistration:
    """Validate a minimal configuration-freeze contract."""
    if data.get("preregistration_version") != PREREGISTRATION_VERSION:
        raise PreregistrationValidationError("unsupported preregistration_version")
    mode = _required_string(data, "mode").upper()
    if mode != "SCALP":
        raise PreregistrationValidationError("this preregistration is SCALP-only")
    symbols_raw = data.get("symbols")
    if not isinstance(symbols_raw, list) or not symbols_raw or not all(isinstance(item, str) and item for item in symbols_raw):
        raise PreregistrationValidationError("symbols must be a non-empty string list")
    features = _required_string(data, "features")
    if features != "volume":
        raise PreregistrationValidationError("features must remain exactly 'volume'")
    normalization = _required_string(data, "normalization")
    if normalization != "none":
        raise PreregistrationValidationError("normalization must remain exactly 'none'")
    threshold = data.get("confidence_threshold")
    position_size = data.get("position_size_pct")
    if not isinstance(threshold, (float, int)) or not 0.0 < float(threshold) <= 1.0:
        raise PreregistrationValidationError("confidence_threshold must be in (0, 1]")
    if not isinstance(position_size, (float, int)) or float(position_size) <= 0.0:
        raise PreregistrationValidationError("position_size_pct must be positive")
    config = data.get("portfolio_config")
    if not isinstance(config, Mapping):
        raise PreregistrationValidationError("portfolio_config must be an object")
    output_name = _required_string(data, "output_trace_name")
    if "/" in output_name or not output_name.endswith(".jsonl"):
        raise PreregistrationValidationError("output_trace_name must be a JSONL basename")
    return FrozenHoldoutPreregistration(
        candidate_id=_required_string(data, "candidate_id"),
        cutoff=_parse_utc(_required_string(data, "cutoff"), "cutoff"),
        mode=mode,
        symbols=tuple(symbols_raw),
        features=features,
        normalization=normalization,
        confidence_threshold=float(threshold),
        position_size_pct=float(position_size),
        portfolio_config=dict(config),
        output_trace_name=output_name,
    )


def load_frozen_holdout_preregistration(path: str | Path) -> FrozenHoldoutPreregistration:
    """Load and validate a preregistration JSON document."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PreregistrationValidationError("invalid preregistration JSON") from exc
    if not isinstance(data, dict):
        raise PreregistrationValidationError("preregistration must be an object")
    return parse_frozen_holdout_preregistration(data)


def frozen_holdout_cli_arguments(spec: FrozenHoldoutPreregistration, *, data_dir: str, output_dir: str) -> list[str]:
    """Build exact canonical CLI arguments; caller executes them at most once."""
    return [
        "--mode", spec.mode,
        "--symbols", ",".join(spec.symbols),
        "--features", spec.features,
        "--normalization", spec.normalization,
        "--data-dir", data_dir,
        "--holdout-cutoff", spec.cutoff.isoformat(),
        "--frozen-confidence-threshold", str(spec.confidence_threshold),
        "--frozen-holdout-trace", str(Path(output_dir) / spec.output_trace_name),
    ]
