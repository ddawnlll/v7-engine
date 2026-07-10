"""Funding input resolver — common shared resolver for pipeline, discovery,
and backtest layers.

Provides a single deterministic ``resolve_funding_input()`` function that
all pipeline stages use, eliminating ad-hoc funding logic in each caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from simulation.contracts.models import (
    FundingDataStatus,
    FundingEvent,
    SimulationProfile,
)
from simulation.engine.funding import FUNDING_MODEL_VERSION, resolve_funding_status
from simulation.engine.time import normalize_timestamp_ms


# ---------------------------------------------------------------------------
# Resolution contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FundingInputResolution:
    """Canonical result of resolving funding for one position window.

    All pipeline stages consume this same contract.
    """
    events: list[FundingEvent] | None
    status: str  # FundingDataStatus value
    source: str  # "event", "legacy_scalar", "none"
    event_count: int
    window_start_ms: int
    window_end_ms: int
    model_version: str = FUNDING_MODEL_VERSION


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def resolve_funding_input(
    *,
    symbol: str,
    entry_timestamp: object,
    exit_timestamp: object,
    events_by_symbol: Mapping[str, Sequence[FundingEvent]] | None = None,
    legacy_scalar_rate: float | None = None,
    applicable: bool = True,
) -> FundingInputResolution:
    """Resolve the funding input for one position window.

    Priority:
      1. If ``events_by_symbol`` is provided and contains *symbol*:
         use those events (may be empty = ``AVAILABLE_EMPTY``).
      2. If ``legacy_scalar_rate`` is set and non-zero:
         ``LEGACY_SCALAR`` with no events.
      3. No data → ``MISSING_DATA``.

    Rules
    -----
    - Only events for the exact *symbol* are used.
    - Events outside the [entry_timestamp, exit_timestamp) window are excluded.
    - ``event_count`` reflects only *applied* events inside the window.
    - Pure/deterministic: no I/O, no random, no external state.

    Parameters
    ----------
    symbol : str
        Trading symbol.
    entry_timestamp : object
        Position entry time (any type accepted by ``normalize_timestamp_ms``).
    exit_timestamp : object
        Position exit time (any type accepted by ``normalize_timestamp_ms``).
    events_by_symbol : dict[str, Sequence[FundingEvent]] | None
        Pre-loaded funding events keyed by symbol.  ``None`` = no data.
    legacy_scalar_rate : float | None
        Explicit scalar funding rate for backward compatibility.
    applicable : bool
        Whether funding is applicable at all for this symbol/mode.
        When ``False``, always returns ``NOT_APPLICABLE``.

    Returns
    -------
    FundingInputResolution
        Resolution with events, status, source, and metadata.
    """
    if not applicable:
        return FundingInputResolution(
            events=None,
            status=FundingDataStatus.NOT_APPLICABLE.value,
            source="not_applicable",
            event_count=0,
            window_start_ms=0,
            window_end_ms=0,
        )

    entry_ms = normalize_timestamp_ms(entry_timestamp)
    exit_ms = normalize_timestamp_ms(exit_timestamp)

    # Check if we have events for this symbol
    symbol_events: Sequence[FundingEvent] | None = None
    if events_by_symbol is not None:
        symbol_events = events_by_symbol.get(symbol)

    if symbol_events is not None:
        # Filter to the position window: entry < event.timestamp <= exit
        matching = [
            evt for evt in symbol_events
            if entry_ms < evt.timestamp <= exit_ms
        ]
        matching.sort(key=lambda e: e.timestamp)

        has_legacy = (legacy_scalar_rate is not None and legacy_scalar_rate != 0.0)
        status = resolve_funding_status(
            events=symbol_events,
            has_legacy_scalar=has_legacy,
            matching_count=len(matching),
        )
        source = "event" if len(matching) > 0 else "event_empty"
        return FundingInputResolution(
            events=matching if matching else [],
            status=status,
            source=source,
            event_count=len(matching),
            window_start_ms=entry_ms,
            window_end_ms=exit_ms,
        )

    # No events_by_symbol provided — check legacy scalar
    if legacy_scalar_rate is not None and legacy_scalar_rate != 0.0:
        return FundingInputResolution(
            events=None,
            status=FundingDataStatus.LEGACY_SCALAR.value,
            source="legacy_scalar",
            event_count=0,
            window_start_ms=entry_ms,
            window_end_ms=exit_ms,
        )

    return FundingInputResolution(
        events=None,
        status=FundingDataStatus.MISSING_DATA.value,
        source="none",
        event_count=0,
        window_start_ms=entry_ms,
        window_end_ms=exit_ms,
    )


def build_events_by_symbol(
    records_by_symbol: Mapping[str, Sequence[FundingEvent]],
) -> dict[str, list[FundingEvent]]:
    """Normalise raw funding records into sorted deduplicated event lists.

    Deterministic policy:
    - Sorted ascending by timestamp.
    - Duplicate timestamps: last-write-wins (keep the last occurrence).

    Parameters
    ----------
    records_by_symbol : dict[str, Sequence[FundingEvent]]
        Raw funding events keyed by symbol.

    Returns
    -------
    dict[str, list[FundingEvent]]
        Cleaned event lists, one per symbol.
    """
    result: dict[str, list[FundingEvent]] = {}
    for symbol, events in records_by_symbol.items():
        # Sort by timestamp then deduplicate (keep last of equal ts)
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        deduped: list[FundingEvent] = []
        seen: set[int] = set()
        for evt in sorted_events:
            if evt.timestamp in seen:
                # Replace with later one (last-write-wins)
                for i, existing in enumerate(deduped):
                    if existing.timestamp == evt.timestamp:
                        deduped[i] = evt
                        break
            else:
                deduped.append(evt)
                seen.add(evt.timestamp)
        result[symbol] = deduped
    return result


def map_resolution_to_profile(
    profile: SimulationProfile,
    resolution: FundingInputResolution,
) -> SimulationProfile:
    """Apply a ``FundingInputResolution`` to a ``SimulationProfile``.

    Returns a new profile with ``funding_events`` and ``funding_rate`` set
    according to the resolution result.  The original profile is not mutated.

    Parameters
    ----------
    profile : SimulationProfile
        Base simulation profile.
    resolution : FundingInputResolution
        Resolved funding input.

    Returns
    -------
    SimulationProfile
        Updated profile suitable for ``simulate()``.
    """
    import dataclasses
    new_profile = dataclasses.replace(profile)
    if resolution.events is not None:
        new_profile.funding_events = resolution.events
        # Clear scalar when using events
        if resolution.status in (
            FundingDataStatus.APPLIED.value,
            FundingDataStatus.AVAILABLE_EMPTY.value,
        ):
            new_profile.funding_rate = 0.0
    else:
        new_profile.funding_events = []
        if resolution.status == FundingDataStatus.LEGACY_SCALAR.value:
            # Keep the existing funding_rate (scalar path)
            pass
        else:
            new_profile.funding_rate = 0.0
    return new_profile
