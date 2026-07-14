"""Interval-aware, shadow-only replay of policy-approved candidate signals.

The replay is deliberately conservative: it delegates admission at each entry
timestamp to ``V7 PortfolioManager`` with currently open positions included.
``realized_r_net`` is never used to rank or admit a signal; it is recognized
only when the selected signal's supplied exit timestamp is reached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping

from v7.portfolio import PortfolioManager


@dataclass(frozen=True)
class ReplaySignal:
    """One already-policy-approved shadow candidate with a known OOS outcome."""

    candidate_id: str
    symbol: str
    direction: str
    entry_timestamp: datetime
    exit_timestamp: datetime
    expected_r_net: float
    confidence: float
    position_size_pct: float
    realized_r_net: float


@dataclass(frozen=True)
class ReplayAdmission:
    """Portfolio decision at one entry timestamp."""

    timestamp: datetime
    admitted_candidate_ids: tuple[str, ...]
    suppressed_symbols: tuple[str, ...]
    active_position_count: int


@dataclass(frozen=True)
class PortfolioReplayResult:
    """Observational replay result; it is not a live or paper execution result."""

    admissions: tuple[ReplayAdmission, ...] = ()
    selected_candidate_ids: tuple[str, ...] = ()
    realized_candidate_ids: tuple[str, ...] = ()
    suppressed_symbols: tuple[str, ...] = ()
    realized_r_sum: float = 0.0
    max_active_positions: int = 0
    detail: str = ""


def _validate_signal(signal: ReplaySignal) -> None:
    if not signal.candidate_id or not signal.symbol:
        raise ValueError("candidate_id and symbol are required")
    if signal.entry_timestamp.tzinfo is None or signal.exit_timestamp.tzinfo is None:
        raise ValueError("entry_timestamp and exit_timestamp must be timezone-aware")
    if signal.exit_timestamp <= signal.entry_timestamp:
        raise ValueError("exit_timestamp must be after entry_timestamp")
    if signal.position_size_pct <= 0.0:
        raise ValueError("position_size_pct must be positive")


def replay_shadow_portfolio(
    signals: Iterable[ReplaySignal],
    *,
    portfolio_config: Mapping[str, object] | None = None,
) -> PortfolioReplayResult:
    """Replay signals under V7's existing interval-aware portfolio limits.

    Signals sharing an entry timestamp are evaluated as one batch. Positions
    that exit at that timestamp are released first, which permits a new entry
    only after the prior exposure is no longer open.
    """
    ordered = sorted(signals, key=lambda item: (item.entry_timestamp, item.symbol, item.candidate_id))
    if not ordered:
        return PortfolioReplayResult(detail="No signals supplied")
    for signal in ordered:
        _validate_signal(signal)

    seen_entry_symbol: set[tuple[datetime, str]] = set()
    for signal in ordered:
        key = (signal.entry_timestamp, signal.symbol)
        if key in seen_entry_symbol:
            raise ValueError("at most one signal per symbol at an entry timestamp")
        seen_entry_symbol.add(key)

    manager = PortfolioManager(dict(portfolio_config or {}))
    active: dict[str, ReplaySignal] = {}
    selected: list[str] = []
    realized: list[str] = []
    suppressed: list[str] = []
    admissions: list[ReplayAdmission] = []
    realized_sum = 0.0
    max_active = 0

    cursor = 0
    while cursor < len(ordered):
        entry_time = ordered[cursor].entry_timestamp
        group: list[ReplaySignal] = []
        while cursor < len(ordered) and ordered[cursor].entry_timestamp == entry_time:
            group.append(ordered[cursor])
            cursor += 1

        # Close first: a position ending at time T consumes no exposure for a
        # candidate entering at T.
        for symbol, existing in list(active.items()):
            if existing.exit_timestamp <= entry_time:
                realized.append(existing.candidate_id)
                realized_sum += existing.realized_r_net
                del active[symbol]

        # A canonical trace represents one candidate stream per symbol, not a
        # scale-in instruction.  Never overwrite an open trace position with
        # a second same-symbol observation: doing so would drop the first
        # position's future realization from replay accounting.
        same_symbol_open = [signal for signal in group if signal.symbol in active]
        eligible_group = [signal for signal in group if signal.symbol not in active]
        same_symbol_suppressed = [signal.symbol for signal in same_symbol_open]

        positions = {
            symbol: {"size_pct": signal.position_size_pct, "side": signal.direction}
            for symbol, signal in active.items()
        }
        requests = [{"symbol": signal.symbol, "direction": signal.direction} for signal in eligible_group]
        results = [
            {
                "symbol": signal.symbol,
                "passed": True,
                "decision": signal.direction,
                "expected_r_net": signal.expected_r_net,
                "confidence": signal.confidence,
                "position_size_pct": signal.position_size_pct,
            }
            for signal in eligible_group
        ]
        portfolio_result = manager.evaluate_portfolio(requests, results, positions)
        by_symbol = {signal.symbol: signal for signal in eligible_group}
        admitted_signals = [by_symbol[item["symbol"]] for item in portfolio_result.ranked]
        for signal in admitted_signals:
            active[signal.symbol] = signal
            selected.append(signal.candidate_id)
        suppressed.extend(same_symbol_suppressed)
        suppressed.extend(portfolio_result.suppressed)
        max_active = max(max_active, len(active))
        admissions.append(ReplayAdmission(
            timestamp=entry_time,
            admitted_candidate_ids=tuple(signal.candidate_id for signal in admitted_signals),
            suppressed_symbols=tuple(same_symbol_suppressed + portfolio_result.suppressed),
            active_position_count=len(active),
        ))

    for _, signal in sorted(active.items(), key=lambda item: (item[1].exit_timestamp, item[0])):
        realized.append(signal.candidate_id)
        realized_sum += signal.realized_r_net

    return PortfolioReplayResult(
        admissions=tuple(admissions),
        selected_candidate_ids=tuple(selected),
        realized_candidate_ids=tuple(realized),
        suppressed_symbols=tuple(suppressed),
        realized_r_sum=round(realized_sum, 10),
        max_active_positions=max_active,
        detail=(
            "Observational shadow replay: ranking used expected_r_net/confidence; "
            "realized_r_net was recognized only at position exit."
        ),
    )
