"""
Funding cost model for perpetual swap positions.

Implements the per-bar funding cost formula:
  funding_cost_r = notional * funding_rate * holding_bars

This is a simple model where:
  - *notional* is the position size in quote currency.
  - *funding_rate* is the per-bar rate (e.g. 0.0001 = 1 bp per bar).
  - *holding_bars* is the number of bars the position is held.

For Binance perpetual swaps the funding interval is 8 hours.  If the
simulation runs on 1h bars, *funding_rate* should be the per-1h rate
and *holding_bars* is the number of 1h bars held.  Equivalently, on 8h
bars the rate is the raw Binance funding rate and *holding_bars* is the
number of 8h windows.

Status: IMPLEMENTED
  Classification: IMPLEMENTED
  The simple perpetual-swap model covers the baseline simulation need.
  A more sophisticated model could account for:
    - Premium index vs. mark price divergence
    - Maximum funding rate caps per exchange
    - Interest rate component (current Base API uses 0%)
    - Variable funding intervals across symbols
"""

funding_status = "IMPLEMENTED"


def funding_cost_r(
    notional: float,
    funding_rate: float,
    holding_bars: int,
) -> float:
    """Compute funding cost in R-multiples for a perpetual swap position.

    Args:
        notional: Position size in quote currency (positive for long,
                  negative for short).
        funding_rate: Per-bar funding rate (e.g. 0.0001 for 1 bp/bar).
                      Positive means longs pay shorts; negative means
                      shorts pay longs.
        holding_bars: Number of bars the position is held.

    Returns:
        Funding cost in quote currency (positive = cost, negative = gain).
        A long position paying positive funding yields a positive cost.
        A short position receiving positive funding yields a negative cost
        (a gain).

    Formula:
        cost = notional * funding_rate * holding_bars

    Examples:
        >>> funding_cost_r(100_000.0, 0.0001, 8)   # 1 bp over 8 bars
        80.0
        >>> funding_cost_r(50_000.0, -0.0001, 4)    # negative rate, short
        -20.0
        >>> funding_cost_r(0.0, 0.0001, 10)
        0.0
        >>> funding_cost_r(100_000.0, 0.0, 10)
        0.0
    """
    if notional == 0.0 or funding_rate == 0.0 or holding_bars == 0:
        return 0.0
    return notional * funding_rate * holding_bars


def funding_cost_r_from_events(
    notional: float,
    events: list,
    entry_timestamp: int,
    exit_timestamp: int,
    risk: float,
) -> float:
    """Compute funding cost from timestamped events between entry and exit.

    Funding only applies to events where:
      entry_timestamp < event.timestamp <= exit_timestamp

    Uses notional sign convention (positive long, negative short):
      cost = rate * notional
      → LONG at positive rate: positive cost
      → SHORT at positive rate: negative cost (gain)

    Args:
        notional: Position size (positive long, negative short).
        events: List of FundingEvent objects with .timestamp and .rate.
        entry_timestamp: Entry time in ms.
        exit_timestamp: Exit time in ms.
        risk: 1R risk amount in quote currency (for R conversion).

    Returns:
        Funding cost in R-multiples (positive = cost, negative = gain).
    """
    if risk <= 0 or notional == 0:
        return 0.0
    total_funding_quote = 0.0
    for evt in events:
        if entry_timestamp < evt.timestamp <= exit_timestamp:
            # Long: cost = -rate * notional  (pays when rate > 0)
            # Short: cost = +rate * notional (receives when rate > 0)
            total_funding_quote += evt.rate * notional
    return total_funding_quote / risk
