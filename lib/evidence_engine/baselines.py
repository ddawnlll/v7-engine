from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import mean, stdev

from lib.evidence_engine.metrics import compute_net_expectancy, compute_net_sharpe

# ------------------------------------------------------------------
# Baseline label conventions (mirrors AlphaForge label semantics)
# ------------------------------------------------------------------

_LONG_NOW = "LONG_NOW"
_SHORT_NOW = "SHORT_NOW"
_NO_TRADE = "NO_TRADE"
_VALID_LABELS = frozenset({_LONG_NOW, _SHORT_NOW, _NO_TRADE})

# Cost adjustment for non-trade baselines that must pay at least one
# round-trip fee to be comparable.
_MIN_ROUND_TRIP_FEE_MULTIPLIER = 2.0


@dataclass
class BaselineResult:
    """Result of evaluating a single baseline strategy."""

    baseline_name: str
    net_expectancy_R: float
    net_sharpe: float
    net_profit_factor: float
    active_trade_count: int
    exposure_pct: float


# ------------------------------------------------------------------
# Baseline implementations
# ------------------------------------------------------------------


def _no_trade(labels: list[str]) -> list[str]:
    """Always predict NO_TRADE."""
    return [_NO_TRADE] * len(labels)


def _random_action(labels: list[str]) -> list[str]:
    """Random long/short/no_trade proportional to observed label distribution."""
    counts: dict[str, int] = {_NO_TRADE: 0, _LONG_NOW: 0, _SHORT_NOW: 0}
    for lbl in labels:
        if lbl in counts:
            counts[lbl] += 1
    total = sum(counts.values())
    if total == 0:
        # Degenerate: uniform
        choices = [_NO_TRADE, _LONG_NOW, _SHORT_NOW]
        return [random.choice(choices) for _ in labels]

    dist = [counts.get(_NO_TRADE, 0) / total,
            counts.get(_LONG_NOW, 0) / total,
            counts.get(_SHORT_NOW, 0) / total]
    choices = [_NO_TRADE, _LONG_NOW, _SHORT_NOW]
    return [random.choices(choices, weights=dist, k=1)[0] for _ in labels]


def _always_long(labels: list[str]) -> list[str]:
    """Always predict LONG_NOW."""
    return [_LONG_NOW] * len(labels)


def _always_short(labels: list[str]) -> list[str]:
    """Always predict SHORT_NOW."""
    return [_SHORT_NOW] * len(labels)


def _buy_and_hold(labels: list[str]) -> list[str]:
    """Passive holding return -- LONG_NOW on first bar, then NO_TRADE."""
    if not labels:
        return []
    return [_LONG_NOW] + [_NO_TRADE] * (len(labels) - 1)


def _naive_momentum(labels: list[str],
                    lookback: int = 5,
                    gross_r: list[float] | None = None) -> list[str]:
    """If mean of last N bar returns > 0 -> LONG_NOW else SHORT_NOW.

    Falls back to _always_long when no gross_r is available.
    """
    if gross_r is None or len(gross_r) < lookback + 1:
        return _always_long(labels)

    preds: list[str] = []
    for i in range(len(labels)):
        if i < lookback:
            # Warm-up: no trade
            preds.append(_NO_TRADE)
        else:
            window = gross_r[i - lookback: i]
            if mean(window) > 0:
                preds.append(_LONG_NOW)
            else:
                preds.append(_SHORT_NOW)
    return preds


def _cost_only_null(labels: list[str], fee_pct: float) -> list[str]:
    """Worst-case: trade every bar so net R is purely negative cost."""
    return _always_long(labels)  # trade every bar, net expect = -fee_pct each


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _simulate_trades(predictions: list[str],
                     labels: list[str],
                     gross_r: list[float],
                     fee_pct: float) -> tuple[list[float], list[float], list[float], int]:
    """Simulate a baseline against ground-truth labels.

    Returns ``(net_r_values, gross_r_values, cost_values, active_count)``.
    """
    net_r: list[float] = []
    gross_r_vals: list[float] = []
    cost_vals: list[float] = []
    active_count = 0

    for pred, true_label, gr in zip(predictions, labels, gross_r):
        if pred == true_label and true_label != _NO_TRADE:
            # Correct directional prediction
            gross_ret = gr
            cost = fee_pct * 2.0  # round-trip
            net_ret = gross_ret - cost
            net_r.append(net_ret)
            gross_r_vals.append(gross_ret)
            cost_vals.append(cost)
            active_count += 1
        elif pred != _NO_TRADE and true_label != _NO_TRADE:
            # Wrong direction
            gross_ret = -gr
            cost = fee_pct * 2.0
            net_ret = gross_ret - cost
            net_r.append(net_ret)
            gross_r_vals.append(gross_ret)
            cost_vals.append(cost)
            active_count += 1
        elif pred != _NO_TRADE and true_label == _NO_TRADE:
            # False positive trade
            cost = fee_pct * 2.0
            net_r.append(-cost)
            gross_r_vals.append(0.0)
            cost_vals.append(cost)
            active_count += 1
        # NO_TRADE prediction: no active trade

    return net_r, gross_r_vals, cost_vals, active_count


# ------------------------------------------------------------------
# BaselineLibrary
# ------------------------------------------------------------------


class BaselineLibrary:
    """Computes standard baseline metrics for model comparison."""

    BASELINE_FUNCS: dict[str, callable] = {
        "NO_TRADE": _no_trade,
        "RANDOM_ACTION": _random_action,
        "ALWAYS_LONG": _always_long,
        "ALWAYS_SHORT": _always_short,
        "BUY_AND_HOLD": _buy_and_hold,
        "COST_ONLY_NULL": None,  # handled specially in compute_baselines
    }

    def compute_baselines(
        self,
        labels: list[str],
        gross_r: list[float],
        fee_pct: float,
    ) -> dict[str, BaselineResult]:
        """Compute all standard baselines and return a name-keyed dict.

        Parameters
        ----------
        labels:
            Ground-truth label sequence (LONG_NOW / SHORT_NOW / NO_TRADE).
        gross_r:
            Per-bar gross return in R units.
        fee_pct:
            Round-trip fee fraction (e.g. 0.001 for 10 bps).

        Returns
        -------
        dict[str, BaselineResult]
            Baseline name -> result mapping.  Always includes NAIVE_MOMENTUM
            in addition to the hard-coded BASELINE_FUNCS.
        """
        results: dict[str, BaselineResult] = {}

        # --- Hard-coded baselines ---
        for name, func in self.BASELINE_FUNCS.items():
            if name == "COST_ONLY_NULL":
                preds = _cost_only_null(labels, fee_pct)
            elif func is None:
                continue
            else:
                preds = func(labels)

            net_r, gross_r_vals, cost_vals, active_count = _simulate_trades(
                preds, labels, gross_r, fee_pct,
            )
            results[name] = self._build_result(name, net_r, gross_r_vals,
                                                cost_vals, active_count,
                                                len(labels), fee_pct)

        # --- NAIVE_MOMENTUM ---
        preds = _naive_momentum(labels, lookback=5, gross_r=gross_r)
        net_r, gross_r_vals, cost_vals, active_count = _simulate_trades(
            preds, labels, gross_r, fee_pct,
        )
        results["NAIVE_MOMENTUM"] = self._build_result(
            "NAIVE_MOMENTUM", net_r, gross_r_vals, cost_vals,
            active_count, len(labels), fee_pct,
        )

        # Cache for model_beats_baseline()
        self._last_baselines = results
        self._last_fee_pct = fee_pct

        return results

    def model_beats_baseline(
        self,
        model_metrics: dict,
        baseline_name: str,
    ) -> tuple[bool, str]:
        """Compare model net_expectancy_R against a baseline.

        Parameters
        ----------
        model_metrics:
            Dict with at least ``"net_expectancy_R"`` and ``"net_sharpe"``.
        baseline_name:
            Name of the baseline to compare against (e.g. ``"ALWAYS_LONG"``).

        Returns
        -------
        tuple[bool, str]
            ``(True, reason)`` if model beats baseline, else
            ``(False, reason)``.
        """
        # In practice the caller would pass the pre-computed BaselineResult,
        # but this convenience method accepts a name and looks up results
        # from a previously run ``compute_baselines`` call stored on self.
        if not hasattr(self, "_last_baselines"):
            return False, "No baselines computed yet; call compute_baselines first."

        baseline: BaselineResult | None = self._last_baselines.get(baseline_name)
        if baseline is None:
            return False, f"Baseline '{baseline_name}' not found in last run."

        model_expect = model_metrics.get("net_expectancy_R", -float("inf"))
        model_sharpe = model_metrics.get("net_sharpe", -float("inf"))

        expect_beats = model_expect > baseline.net_expectancy_R
        sharpe_beats = model_sharpe > baseline.net_sharpe

        if expect_beats and sharpe_beats:
            return True, (
                f"Model net_expectancy_R {model_expect:.4f} > baseline "
                f"{baseline_name} {baseline.net_expectancy_R:.4f} AND "
                f"net_sharpe {model_sharpe:.4f} > {baseline.net_sharpe:.4f}"
            )
        reasons: list[str] = []
        if not expect_beats:
            reasons.append(
                f"Model net_expectancy_R {model_expect:.4f} <= "
                f"baseline {baseline_name} {baseline.net_expectancy_R:.4f}"
            )
        if not sharpe_beats:
            reasons.append(
                f"Model net_sharpe {model_sharpe:.4f} <= "
                f"baseline {baseline_name} {baseline.net_sharpe:.4f}"
            )
        return False, "; ".join(reasons)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_result(
        self,
        name: str,
        net_r: list[float],
        gross_r_vals: list[float],
        cost_vals: list[float],
        active_count: int,
        total_bars: int,
        fee_pct: float,
    ) -> BaselineResult:
        exposure_pct = (active_count / max(total_bars, 1)) * 100.0
        expect = compute_net_expectancy(net_r) if net_r else 0.0

        # Net sharpe across per-bar returns (empty -> 0)
        if len(net_r) > 1 and stdev(net_r) > 0:
            sharpe = compute_net_sharpe(net_r)
        else:
            sharpe = 0.0

        # Profit factor
        total_gross = sum(gross_r_vals)
        total_cost = sum(cost_vals)
        if total_cost > 0:
            pf = (total_gross + abs(total_cost)) / max(abs(total_cost), 1e-12)
        else:
            pf = 0.0 if total_gross == 0 else float("inf")

        return BaselineResult(
            baseline_name=name,
            net_expectancy_R=expect,
            net_sharpe=sharpe,
            net_profit_factor=pf,
            active_trade_count=active_count,
            exposure_pct=exposure_pct,
        )

    def __repr__(self) -> str:
        return f"<BaselineLibrary baselines={len(self.BASELINE_FUNCS) + 1}>"
