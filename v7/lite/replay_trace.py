"""CLI adapter from canonical AlphaForge OOS JSONL traces to V7-Lite replay.

The training trace does not contain a forward-looking expected return estimate.
This adapter therefore passes ``expected_r_net=0`` for every signal and lets
the existing V7 tie-break use confidence only.  It never uses realized R for
selection.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from v7.lite.portfolio_replay import PortfolioReplayResult, ReplaySignal, replay_shadow_portfolio


_ACTION_TO_DIRECTION = {"LONG_NOW": "LONG", "SHORT_NOW": "SHORT"}


def _parse_epoch_timestamp(value: object) -> datetime:
    """Parse canonical ns/ms epoch timestamps or ISO-8601 timestamps as UTC."""
    if isinstance(value, (int, float)):
        numeric = float(value)
        # Canonical data is nanoseconds; accept milliseconds for old traces.
        divisor = 1_000_000_000 if abs(numeric) >= 1e15 else 1_000
        return datetime.fromtimestamp(numeric / divisor, tz=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError("timestamp must be epoch milliseconds/nanoseconds or ISO-8601")


def signals_from_trace(
    rows: Iterable[Mapping[str, object]],
    *,
    position_size_pct: float,
    candidate_prefix: str = "trace",
) -> list[ReplaySignal]:
    """Convert active trace rows to replay signals with strict interval checks."""
    signals: list[ReplaySignal] = []
    for line_number, row in enumerate(rows, start=1):
        direction = _ACTION_TO_DIRECTION.get(str(row.get("decision", "")))
        if direction is None:
            continue
        if "exit_timestamp" not in row:
            raise ValueError(f"trace row {line_number} lacks exit_timestamp")
        try:
            entry = _parse_epoch_timestamp(row.get("timestamp"))
            exit_time = _parse_epoch_timestamp(row.get("exit_timestamp"))
            symbol = str(row["symbol"])
            confidence = float(row["confidence"])
            realized_r = float(row["realized_r_net"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid trace row {line_number}") from exc
        signals.append(ReplaySignal(
            candidate_id=f"{candidate_prefix}:{line_number}",
            symbol=symbol,
            direction=direction,
            entry_timestamp=entry,
            exit_timestamp=exit_time,
            expected_r_net=0.0,
            confidence=confidence,
            position_size_pct=position_size_pct,
            realized_r_net=realized_r,
        ))
    return signals


def replay_trace_file(
    trace_path: str | Path,
    *,
    position_size_pct: float = 5.0,
    portfolio_config: Mapping[str, object] | None = None,
) -> PortfolioReplayResult:
    """Load a canonical JSONL trace and run the observational V7 replay."""
    source = Path(trace_path)
    rows: list[Mapping[str, object]] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on trace line {line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"trace line {line_number} must be an object")
        rows.append(row)
    return replay_shadow_portfolio(
        signals_from_trace(rows, position_size_pct=position_size_pct),
        portfolio_config=portfolio_config,
    )


def _main() -> None:
    parser = argparse.ArgumentParser(description="Replay canonical AlphaForge decision trace through V7 portfolio caps")
    parser.add_argument("trace_path")
    parser.add_argument("--position-size-pct", type=float, default=5.0)
    parser.add_argument("--portfolio-config-json", default="{}")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        config = json.loads(args.portfolio_config_json)
    except json.JSONDecodeError as exc:
        raise SystemExit("--portfolio-config-json must be valid JSON") from exc
    if not isinstance(config, dict):
        raise SystemExit("--portfolio-config-json must be an object")

    result = replay_trace_file(
        args.trace_path,
        position_size_pct=args.position_size_pct,
        portfolio_config=config,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "selected_candidate_count": len(result.selected_candidate_ids),
        "realized_candidate_count": len(result.realized_candidate_ids),
        "suppressed_signal_count": len(result.suppressed_symbols),
        "realized_r_sum_observational": result.realized_r_sum,
        "max_active_positions": result.max_active_positions,
        "detail": result.detail,
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    _main()
