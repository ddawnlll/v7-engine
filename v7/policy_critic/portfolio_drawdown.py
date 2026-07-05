"""
Portfolio drawdown integration for Policy Critic.

Computes portfolio-level drawdown metrics per decision and feeds them into the
critic as context features, making the critic more conservative when the
portfolio is underwater.

Key concepts:
  - Drawdown = peak_to_trough decline in cumulative portfolio R (realised_r_net).
  - Per-decision drawdown = the drawdown level at the time of each decision.
  - Critic becomes more conservative (lower Q-values) as drawdown increases.
  - Incorporates mode-specific drawdown penalty weights (matching regret.py).

Flow (HOLD #6, per ai_summary §Open HOLDs):
  DecisionEvent (with realised outcomes)
    -> PortfolioDrawdownTracker.update()
    -> drawdown context feature
    -> Feed into IQLTrainer.review() as state feature
    -> Critic applies drawdown-aware penalty to Q-values

Domain boundaries:
  - Drawdown is only advisory (a feature, not a gate).
  - Does NOT bypass or override drawdown limits from runtime risk gates.
  - Portfolio-level (all symbols), not per-symbol.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Drawdown Tracking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DrawdownSnapshot:
    """Portfolio drawdown state at a single point in time.

    Attributes:
        timestamp:           ISO 8601 UTC.
        cumulative_r:        Cumulative portfolio R-net at this point.
        peak_r:              Peak cumulative R-net observed so far.
        current_drawdown_r:  Current drawdown in R-units (peak - current).
        current_drawdown_pct: Current drawdown as a fraction of peak
                              (0.0 = no drawdown, 1.0 = total loss from peak).
        max_drawdown_r:      Maximum drawdown in R-units observed so far.
        max_drawdown_pct:    Maximum drawdown fraction observed so far.
        drawdown_duration:   Number of decisions since the last peak.
        is_underwater:       True if current_drawdown_r > 0.
    """
    timestamp: str
    cumulative_r: float
    peak_r: float
    current_drawdown_r: float
    current_drawdown_pct: float
    max_drawdown_r: float
    max_drawdown_pct: float
    drawdown_duration: int
    is_underwater: bool


class PortfolioDrawdownTracker:
    """Tracks portfolio-level drawdown from per-decision R-net outcomes.

    The tracker maintains cumulative portfolio R-net, identifies the peak,
    and computes drawdown metrics after each update.

    This is the source of drawdown context features consumed by the critic.
    """

    def __init__(self, initial_r: float = 0.0):
        """Initialise the drawdown tracker.

        Args:
            initial_r: Starting cumulative portfolio R-net (default 0.0).
        """
        self._cumulative_r = initial_r
        self._peak_r = initial_r
        self._max_dd_r = 0.0
        self._max_dd_pct = 0.0
        self._drawdown_duration = 0
        self._is_underwater = False
        self._history: list[DrawdownSnapshot] = []

    @property
    def cumulative_r(self) -> float:
        return self._cumulative_r

    @property
    def peak_r(self) -> float:
        return self._peak_r

    @property
    def current_drawdown_r(self) -> float:
        return max(0.0, self._peak_r - self._cumulative_r)

    @property
    def max_drawdown_r(self) -> float:
        return self._max_dd_r

    @property
    def drawdown_duration(self) -> int:
        return self._drawdown_duration

    @property
    def is_underwater(self) -> bool:
        return self._is_underwater

    @property
    def snapshot(self) -> DrawdownSnapshot:
        """Current drawdown snapshot."""
        peak = self._peak_r
        current = self._cumulative_r
        dd_r = max(0.0, peak - current)
        dd_pct = dd_r / abs(peak) if peak > 0 else 0.0
        max_dd_pct = max(self._max_dd_pct, dd_pct)

        return DrawdownSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            cumulative_r=current,
            peak_r=peak,
            current_drawdown_r=dd_r,
            current_drawdown_pct=dd_pct,
            max_drawdown_r=self._max_dd_r,
            max_drawdown_pct=max_dd_pct,
            drawdown_duration=self._drawdown_duration,
            is_underwater=self._is_underwater,
        )

    def update(self, realized_r_net: float, *, timestamp: str = "") -> DrawdownSnapshot:
        """Update drawdown state with a new realised outcome.

        Args:
            realized_r_net: R-net from the most recent decision.
            timestamp:      Optional ISO 8601 timestamp.

        Returns:
            DrawdownSnapshot after the update.
        """
        self._cumulative_r += realized_r_net

        if self._cumulative_r > self._peak_r:
            self._peak_r = self._cumulative_r
            self._drawdown_duration = 0
            self._is_underwater = False
        else:
            self._drawdown_duration += 1
            self._is_underwater = True

        current_dd = max(0.0, self._peak_r - self._cumulative_r)
        if current_dd > self._max_dd_r:
            self._max_dd_r = current_dd

        # Max drawdown % (relative to peak)
        if self._peak_r > 0:
            current_dd_pct = current_dd / abs(self._peak_r)
        else:
            current_dd_pct = 0.0
        if current_dd_pct > self._max_dd_pct:
            self._max_dd_pct = current_dd_pct

        snap = self.snapshot
        self._history.append(snap)
        return snap

    def get_drawdown_context(self) -> dict[str, Any]:
        """Return drawdown metrics as a context feature dict for the critic.

        This is the main bridge: the returned dict is merged into the
        state feature vector (via build_state_feature_vector kwargs) so the
        critic's Q-function can react to drawdown conditions.

        Returns:
            Dict suitable for merging into state features.
        """
        snap = self.snapshot
        return {
            "portfolio_drawdown_r": round(snap.current_drawdown_r, 6),
            "portfolio_drawdown_pct": round(snap.current_drawdown_pct, 6),
            "portfolio_max_drawdown_r": round(snap.max_drawdown_r, 6),
            "portfolio_drawdown_duration": snap.drawdown_duration,
            "portfolio_is_underwater": int(snap.is_underwater),
        }

    def get_underwater_adjustment(
        self,
        *,
        mode: str = "SWING",
        base_dd_lambda: float = 0.5,
        severity_scale: float = 2.0,
    ) -> float:
        """Compute a drawdown severity adjustment factor.

        When the portfolio is underwater, the critic should be more
        conservative (lower Q-values). This factor is the multiplier:

          adjustment = 1.0 - severity * (current_dd_pct * dd_lambda)

        where severity_scale amplifies the effect during deep drawdowns.

        Args:
            mode:             Trading mode (for lambda lookup).
            base_dd_lambda:   Base drawdown penalty weight.
            severity_scale:   Multiplier for drawdown severity effect.

        Returns:
            Adjustment factor in (0, 1] — multiply Q-values by this.
            1.0 means no drawdown penalty; near 0 means severe penalty.
        """
        if not self._is_underwater:
            return 1.0

        snap = self.snapshot
        penalty = severity_scale * snap.current_drawdown_pct * base_dd_lambda
        return max(0.1, 1.0 - penalty)

    def reset(self, initial_r: float = 0.0) -> None:
        """Reset the tracker to initial state."""
        self._cumulative_r = initial_r
        self._peak_r = initial_r
        self._max_dd_r = 0.0
        self._max_dd_pct = 0.0
        self._drawdown_duration = 0
        self._is_underwater = False
        self._history.clear()


# ---------------------------------------------------------------------------
# Drawdown-Aware Critic Modifier
# ---------------------------------------------------------------------------


class DrawdownCriticModifier:
    """Applies drawdown context to critic Q-values as a post-hoc modifier.

    This modifier wraps a trained critic and adjusts its Q-values based on
    the current portfolio drawdown state. The adjustment is:

      Q_dd(s, a) = Q(s, a) * drawdown_factor * underwater_adjustment

    where drawdown_factor is the severity-based penalty and
    underwater_adjustment is the mode-specific penalty weight.

    The modifier is advisory only — the underlying Q-values are preserved
    for comparison.
    """

    def __init__(self, tracker: PortfolioDrawdownTracker):
        """Initialise with a drawdown tracker.

        Args:
            tracker: PortfolioDrawdownTracker instance.
        """
        self._tracker = tracker

    def adjust_q_values(
        self,
        q_values: dict[str, float],
        *,
        mode: str = "SWING",
        base_dd_lambda: float = 0.5,
        severity_scale: float = 2.0,
    ) -> dict[str, float]:
        """Apply drawdown-aware penalty to Q-values.

        Args:
            q_values:       Dict of {action: Q-value} (LONG, SHORT, NO_TRADE).
            mode:           Trading mode.
            base_dd_lambda: Base drawdown penalty weight.
            severity_scale: Severity multiplier for underwater effect.

        Returns:
            Adjusted Q-values with drawdown penalty applied.
        """
        adjustment = self._tracker.get_underwater_adjustment(
            mode=mode,
            base_dd_lambda=base_dd_lambda,
            severity_scale=severity_scale,
        )
        # NO_TRADE gets less penalty (it represents not trading, which is
        # naturally conservative)
        adjusted: dict[str, float] = {}
        for action, qv in q_values.items():
            if action == "NO_TRADE":
                adj = qv  # NO_TRADE not penalised
            else:
                adj = qv * adjustment
            adjusted[action] = round(adj, 6)

        return adjusted

    def adjust_review(
        self,
        review: dict[str, Any],
        *,
        mode: str = "SWING",
    ) -> dict[str, Any]:
        """Apply drawdown adjustment to a critic review dict.

        Modifies critic_value_LONG and critic_value_SHORT by the
        drawdown penalty, and potentially escalates the verdict if the
        drawdown is severe.

        Args:
            review: PolicyCriticReview dict (from IQLTrainer.review()).
            mode:   Trading mode.

        Returns:
            Adjusted review with drawdown-aware values.
        """
        q_values = {
            "LONG": review.get("critic_value_LONG", 0.0),
            "SHORT": review.get("critic_value_SHORT", 0.0),
            "NO_TRADE": review.get("critic_value_NO_TRADE", 0.0),
        }

        adjusted_q = self.adjust_q_values(q_values, mode=mode)

        result = dict(review)
        result["critic_value_LONG"] = adjusted_q["LONG"]
        result["critic_value_SHORT"] = adjusted_q["SHORT"]
        result["critic_value_NO_TRADE"] = adjusted_q["NO_TRADE"]

        # If drawdown is severe and the trade is LONG/SHORT, escalate verdict
        snap = self._tracker.snapshot
        if snap.current_drawdown_pct > 0.3 and snap.is_underwater:
            verdict = result.get("critic_verdict", "ALLOW")
            if verdict in ("ALLOW", "DOWNWEIGHT_CONFIDENCE"):
                # During severe drawdown, escalate to downweight or veto
                if result.get("critic_value_LONG", 0) < 0.1 or result.get("critic_value_SHORT", 0) < 0.1:
                    result["critic_verdict"] = "VETO_TO_NO_TRADE"
                    result["critic_veto_reason"] = "portfolio_deep_drawdown_escalation"
                    result["critic_confidence_adjustment"] = 0.0
                else:
                    result["critic_verdict"] = "DOWNWEIGHT_CONFIDENCE"
                    result["critic_veto_reason"] = "portfolio_drawdown_downweight"
                    result["critic_confidence_adjustment"] = max(
                        0.2,
                        result.get("critic_confidence_adjustment", 1.0) * (1.0 - snap.current_drawdown_pct),
                    )

        result["drawdown_adjusted"] = True
        result["drawdown_penalty_factor"] = round(
            self._tracker.get_underwater_adjustment(mode=mode), 4,
        )

        return result
