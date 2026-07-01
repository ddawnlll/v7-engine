"""Active trade metric computations for AlphaForge research reports.

Provides ``compute_oos_metrics`` which translates label decisions and
per-decision gross R-multiple values into the canonical 12-metric suite
for OOS (out-of-sample) reporting.

All 12 metrics (plus derived ``oos_trade_count``):

  +--------------------------+------------------------------------------+
  | Metric                   | Description                              |
  +==========================+==========================================+
  | active_trade_count       | Long + short decision count              |
  | long_trade_count         | LONG_NOW decision count                  |
  | short_trade_count        | SHORT_NOW decision count                 |
  | no_trade_count           | NO_TRADE decision count                  |
  | exposure_pct             | active_trade_count / total_decisions *100|
  | total_gross_R            | Sum of gross R-multiple over all bars    |
  | total_fee_cost_R         | fee_pct * active_trade_count             |
  | total_slippage_cost_R    | slippage_pct * active_trade_count        |
  | total_funding_cost_R     | funding_pct * active_trade_count         |
  | total_net_R              | gross_R - fee_cost_R - slippage_cost_R   |
  |                          |   - funding_cost_R                       |
  | avg_net_R_per_active_trade  | net_R / active_trade_count            |
  | avg_net_R_per_decision   | net_R / total_decisions                  |
  | turnover                 | active_trade_count / total_decisions     |
  | avg_hold_bars            | Mean hold duration in bars (when data    |
  |                          | available, else 0.0)                     |
  | oos_trade_count          | == active_trade_count (same concept)     |
  +--------------------------+------------------------------------------+

No profitability claims. No real market data. All values are descriptive
metrics computed from decision labels and gross R-multiples.
"""

from __future__ import annotations


def compute_oos_metrics(
    labels: list[str],
    gross_r_list: list[float],
    fee_pct: float = 0.0,
    slippage_pct: float = 0.0,
    funding_pct: float = 0.0,
) -> dict:
    """Compute the full 12-metric active trade suite from label decisions.

    Args:
        labels:
            List of decision labels (``'LONG_NOW'``, ``'SHORT_NOW'``,
            ``'NO_TRADE'``).  Same length as *gross_r_list*.
        gross_r_list:
            Gross R-multiple for each decision.  0.0 for NO_TRADE bars.
        fee_pct:
            Per-trade fee cost as a fraction of R (default 0.0).
        slippage_pct:
            Per-trade slippage cost as a fraction of R (default 0.0).
        funding_pct:
            Per-trade funding cost as a fraction of R (default 0.0).

    Returns:
        Dict with all 12 metrics plus derived ``oos_trade_count``:

        - ``active_trade_count`` (int)
        - ``long_trade_count`` (int)
        - ``short_trade_count`` (int)
        - ``no_trade_count`` (int)
        - ``exposure_pct`` (float)
        - ``total_gross_R`` (float)
        - ``total_fee_cost_R`` (float)
        - ``total_slippage_cost_R`` (float)
        - ``total_funding_cost_R`` (float)
        - ``total_net_R`` (float)
        - ``avg_net_R_per_active_trade`` (float)
        - ``avg_net_R_per_decision`` (float)
        - ``turnover`` (float)
        - ``avg_hold_bars`` (float)
        - ``oos_trade_count`` (int)

    All values are deterministic and rounded to 6 decimal places where
    appropriate.
    """
    total_decisions = len(labels)

    # --- Counts ---
    long_trade_count = sum(1 for l in labels if l == "LONG_NOW")
    short_trade_count = sum(1 for l in labels if l == "SHORT_NOW")
    no_trade_count = sum(1 for l in labels if l == "NO_TRADE")
    active_trade_count = long_trade_count + short_trade_count

    # --- R sums ---
    total_gross_R = sum(gross_r_list)

    total_fee_cost_R = fee_pct * active_trade_count
    total_slippage_cost_R = slippage_pct * active_trade_count
    total_funding_cost_R = funding_pct * active_trade_count

    total_net_R = (
        total_gross_R
        - total_fee_cost_R
        - total_slippage_cost_R
        - total_funding_cost_R
    )

    # --- Derived fractions ---
    exposure_pct = (
        round(active_trade_count / total_decisions * 100, 2)
        if total_decisions > 0
        else 0.0
    )

    turnover = (
        round(active_trade_count / total_decisions, 6)
        if total_decisions > 0
        else 0.0
    )

    avg_net_R_per_active_trade = (
        round(total_net_R / active_trade_count, 6)
        if active_trade_count > 0
        else 0.0
    )

    avg_net_R_per_decision = (
        round(total_net_R / total_decisions, 6)
        if total_decisions > 0
        else 0.0
    )

    # avg_hold_bars: mean hold duration in bars.
    # When per-bar hold duration data is not available, defaults to 0.0.
    # This is a metric that requires simulation output to be computed
    # accurately; the function accepts it as a passthrough parameter in
    # future extensions.
    avg_hold_bars = 0.0

    return {
        "active_trade_count": active_trade_count,
        "long_trade_count": long_trade_count,
        "short_trade_count": short_trade_count,
        "no_trade_count": no_trade_count,
        "total_gross_R": round(total_gross_R, 6),
        "total_fee_cost_R": round(total_fee_cost_R, 6),
        "total_slippage_cost_R": round(total_slippage_cost_R, 6),
        "total_funding_cost_R": round(total_funding_cost_R, 6),
        "total_net_R": round(total_net_R, 6),
        "avg_net_R_per_active_trade": avg_net_R_per_active_trade,
        "avg_net_R_per_decision": avg_net_R_per_decision,
        "exposure_pct": exposure_pct,
        "turnover": turnover,
        "avg_hold_bars": avg_hold_bars,
        "oos_trade_count": active_trade_count,
    }
