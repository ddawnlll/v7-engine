"""Funding cost model for perpetual swap positions.

Two modes
---------
1. **Scalar funding** (legacy): ``funding_cost_r(notional, rate, holding_bars, side)``
   — per-bar rate applied over holding bars.  Side-aware: LONG pays positive
   rates, SHORT receives positive rates.

2. **Event-based funding**: ``funding_cost_r_from_events(...)``
   — timestamped events between entry/exit, each with a signed contribution.

Event authority rule
--------------------
    entry_timestamp < event.timestamp <= exit_timestamp

Sign convention
---------------
- Positive rate → LONG pays, SHORT receives.
- Negative rate → LONG receives, SHORT pays.
- ``funding_cost_r`` returns **positive = cost** (detracts from gross R),
  **negative = credit** (adds to gross R).

Status: IMPLEMENTED
  Classification: IMPLEMENTED
  The simple perpetual-swap model covers the baseline simulation need.
  A more sophisticated model could account for:
    - Premium index vs. mark price divergence
    - Maximum funding rate caps per exchange
    - Interest rate component (current Base API uses 0%)
    - Variable funding intervals across symbols
"""

from __future__ import annotations

import math
from typing import Sequence

from simulation.contracts.models import FundingEvent

funding_status = "IMPLEMENTED"
FUNDING_MODEL_VERSION = "funding-2.0.0"


def funding_cost_r(
    notional: float,
    funding_rate: float,
    holding_bars: int,
    side: str = "LONG",
) -> float:
    """Compute scalar funding cost in quote currency.

    Parameters
    ----------
    notional : float
        Position size in quote currency.  **Backward-compatible**: positive for
        LONG, can be negative for SHORT (old convention).  The ``side`` parameter
        adds explicit sign control on top of the notional sign.
    funding_rate : float
        Per-bar funding rate (e.g. 0.0001 for 1 bp/bar).
    holding_bars : int
        Number of bars the position is held.
    side : str
        ``"LONG"`` or ``"SHORT"``.  When ``side="SHORT"`` the raw result is
        negated (longs pay, shorts receive).

    Returns
    -------
    float
        Funding cost in quote currency (positive = cost, negative = gain).
    """
    if notional == 0.0 or funding_rate == 0.0 or holding_bars == 0:
        return 0.0
    raw = notional * funding_rate * holding_bars
    if side.upper() == "SHORT":
        raw = -raw
    return raw


def funding_cost_r_from_events(
    notional: float,
    events: Sequence[FundingEvent],
    entry_timestamp: int,
    exit_timestamp: int,
) -> float:
    """Compute funding cost from timestamped events between entry and exit.

    Each matching event contributes::

        contribution = event.rate * signed_notional

    where ``signed_notional = +notional`` for LONG and ``-notional`` for SHORT.
    The caller is responsible for passing the correct sign on *notional*.

    Parameters
    ----------
    notional : float
        Signed notional: **positive** for LONG, **negative** for SHORT.
    events : Sequence[FundingEvent]
        Timestamped funding events (must be sorted ascending).
    entry_timestamp : int
        Entry time in ms.
    exit_timestamp : int
        Exit time in ms.

    Returns
    -------
    float
        Total funding cost in **quote currency** (positive = cost, negative = credit).
    """
    if notional == 0:
        return 0.0
    total = 0.0
    for evt in events:
        if entry_timestamp < evt.timestamp <= exit_timestamp:
            total += evt.rate * notional
    return total


def resolve_funding_status(
    events: Sequence[FundingEvent] | None,
    has_legacy_scalar: bool,
    matching_count: int,
) -> str:
    """Derive the truthful ``FundingDataStatus`` for a simulation run.

    Parameters
    ----------
    events : list[FundingEvent] | None
        ``None`` = no funding data provided; ``[]`` = data available but empty.
    has_legacy_scalar : bool
        Whether a scalar fallback rate was explicitly configured.
    matching_count : int
        Number of events that matched the position interval.

    Returns
    -------
    str
        One of ``FundingDataStatus`` values.
    """
    from simulation.contracts.models import FundingDataStatus

    if events is None:
        if has_legacy_scalar:
            return FundingDataStatus.LEGACY_SCALAR.value
        return FundingDataStatus.MISSING_DATA.value
    if matching_count > 0:
        return FundingDataStatus.APPLIED.value
    # events is not None but no events in window
    return FundingDataStatus.AVAILABLE_EMPTY.value
