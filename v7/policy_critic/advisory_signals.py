"""
Advisory signals for Policy Critic — bad_trade_probability, model disagreement,
prediction error synthesis.

This module synthesises three advisory signals that the critic uses as context
features, helping it calibrate its confidence and detect when it may be operating
outside its reliable regime:

  1. bad_trade_probability:   Probability (0-1) that a proposed trade would
                              result in a net loss. Derived from the critic's
                              distributional Q-values.
  2. model_disagreement:      Score (0-1) measuring disagreement between the
                              AlphaForge output and the critic's assessment.
                              High disagreement -> low trust regime.
  3. recent_prediction_error: Rolling measure of how well the critic's
                              predictions matched realised outcomes over the
                              last N decisions.

  synthesize_signals:        Composites all three into a single advisory review
                              dict with an overall reliability assessment.

All three signals are ADVISORY only — they are not gate overrides. They feed
into the critic's state representation and may influence verdict escalation
(via ShadowCriticRunner), but never bypass hard gates.

Per ai_summary §Open HOLDs #7:
  "bad_trade_probability, model_disagreement, recent_prediction_error don't
   exist live — must be synthesized (v2+) or wait for P9"
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Signal data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdvisorySignalReview:
    """Consolidated advisory signal review.

    Attributes:
        bad_trade_probability:  Probability (0-1) the proposed trade will lose.
        model_disagreement:     Score (0-1) measuring AlphaForge vs critic
                                disagreement. 0 = full agreement, 1 = complete
                                disagreement.
        recent_prediction_error: Mean absolute error over the recent window
                                (R-units).
        prediction_error_window: Window size used for the error computation.
        reliability:            Overall reliability assessment:
                                "HIGH", "MODERATE", "LOW", or "DEGRADED".
        signal_timestamp:       ISO 8601 UTC.
        is_advisory:            Always True.
    """
    bad_trade_probability: float = 0.5
    model_disagreement: float = 0.0
    recent_prediction_error: float = 0.0
    prediction_error_window: int = 20
    reliability: str = "MODERATE"
    signal_timestamp: str = ""
    is_advisory: bool = True


# ---------------------------------------------------------------------------
# Signal functions
# ---------------------------------------------------------------------------


def compute_bad_trade_probability(
    critic_value: float,
    *,
    lower_quantile: float | None = None,
    conformal_p_value: float | None = None,
) -> float:
    """Compute the probability (0-1) that a proposed trade will be a net loser.

    Uses the critic's value estimate and optional calibration info:

      p_bad = P(Q(s,a) <= 0) approximated by:
        - If conformal_p_value is available: 1.0 - conformal_p_value
        - If lower_quantile is available: fraction of quantile mass <= 0
        - Otherwise: sigmoid(-critic_value * 2.0) — a soft proxy

    Args:
        critic_value:     The critic's point estimate Q(s, a) for the proposed
                          action. Higher = more confident in positive outcome.
        lower_quantile:   Optional lower quantile of Q(s, a). If the lower
                          quantile is positive, the bad-trade probability is
                          low. If it is negative, the probability is high.
        conformal_p_value: Optional conformal p-value (0-1, higher = more
                          reliable positive). Used as (1 - p) for loss prob.

    Returns:
        Bad trade probability in [0, 1].
    """
    if conformal_p_value is not None:
        # Conformal p-value is our most reliable indicator:
        # low p-value -> Q(s,a) likely <= 0 -> high bad-trade probability
        return max(0.0, min(1.0, 1.0 - conformal_p_value))

    if lower_quantile is not None:
        # Lower quantile: how far below zero is the pessimistic estimate?
        # If lower_quantile >= 0, low probability.
        # If lower_quantile < 0, probability scales with distance below 0.
        p = 1.0 / (1.0 + math.exp(lower_quantile * 3.0))
        return max(0.0, min(1.0, p))

    # Fallback: sigmoid soft proxy
    # critic_value > 0 -> p_bad < 0.5; critic_value < 0 -> p_bad > 0.5
    p = 1.0 / (1.0 + math.exp(critic_value * 2.0))
    return max(0.0, min(1.0, p))


def compute_model_disagreement(
    af_output: dict[str, Any] | None,
    critic_output: dict[str, Any] | None,
) -> float:
    """Compute a disagreement score between AlphaForge and the critic.

    Measures how much the AlphaForge scorer's recommendation disagrees with
    the critic's assessment. Score is 0 (full agreement) to 1 (complete
    disagreement).

    Disagreement is computed from:
      - Direction disagreement: AF recommends LONG, critic says NO_TRADE.
      - Magnitude disagreement: AF confidence vs critic value magnitude.
      - Verdict disagreement: AF output vs critic verdict.

    Args:
        af_output:     AlphaForge scorer output dict. Expected keys:
                        - best_direction (str): "LONG", "SHORT", "NO_TRADE"
                        - confidence (float): 0-1
                        - expected_return (float)
        critic_output: Critic review dict. Expected keys:
                        - critic_verdict (str)
                        - critic_value_LONG (float)
                        - critic_value_SHORT (float)
                        - critic_value_NO_TRADE (float)

    Returns:
        Disagreement score in [0, 1].
    """
    if af_output is None or critic_output is None:
        return 0.5  # Unknown -> moderate disagreement

    # Direction disagreement (weight: 0.5)
    af_direction = af_output.get("best_direction", "").upper()
    critic_verdict = critic_output.get("critic_verdict", "NOT_EVALUATED")
    direction_d = 0.0

    if af_direction in ("LONG", "SHORT") and critic_verdict == "VETO_TO_NO_TRADE":
        direction_d = 1.0
    elif af_direction == "NO_TRADE" and critic_verdict in ("ALLOW", "DOWNWEIGHT_CONFIDENCE"):
        direction_d = 0.5
    elif af_direction == "LONG" and critic_verdict == "DOWNWEIGHT_CONFIDENCE":
        direction_d = 0.3  # Partial disagreement
    elif af_direction == "SHORT" and critic_verdict == "DOWNWEIGHT_CONFIDENCE":
        direction_d = 0.3
    else:
        direction_d = 0.0

    # Magnitude disagreement (weight: 0.3)
    af_conf = af_output.get("confidence", 0.5)
    if isinstance(af_conf, (int, float)):
        if af_direction == "LONG":
            critic_val = critic_output.get("critic_value_LONG", 0.0)
        elif af_direction == "SHORT":
            critic_val = critic_output.get("critic_value_SHORT", 0.0)
        else:
            critic_val = critic_output.get("critic_value_NO_TRADE", 0.0)
        # Map critic value (unbounded) to [0,1] for comparison
        critic_norm = 1.0 / (1.0 + math.exp(-critic_val))
        magnitude_d = abs(af_conf - critic_norm)
    else:
        magnitude_d = 0.0

    # Verdict disagreement (weight: 0.2)
    # "REQUIRE_REVIEW" from critic indicates concern
    if critic_verdict == "REQUIRE_REVIEW":
        verdict_d = 0.7
    elif critic_verdict == "NOT_EVALUATED":
        verdict_d = 0.3
    else:
        verdict_d = 0.0

    total = 0.5 * direction_d + 0.3 * magnitude_d + 0.2 * verdict_d
    return max(0.0, min(1.0, total))


def compute_recent_prediction_error(
    predictions: list[float],
    actuals: list[float],
    window: int = 20,
) -> float:
    """Compute the critic's recent prediction error over a rolling window.

    Measures mean absolute error (MAE) between critic predictions and
    realised outcomes for the recent window of decisions.

    A high prediction error indicates the critic is operating in a regime
    where its value estimates are unreliable.

    Args:
        predictions: List of critic predicted values (e.g. expected_R).
        actuals:     List of realised outcomes (e.g. realized_r_net).
        window:      Rolling window size (default 20).

    Returns:
        Mean absolute error in R-units. Returns 0.0 if window cannot be
        populated.
    """
    if not predictions or not actuals:
        return 0.0

    # Use the most recent `window` pairs
    n = min(window, len(predictions), len(actuals))
    if n < 1:
        return 0.0

    errors: list[float] = []
    for i in range(-n, 0):
        pred = predictions[i]
        actual = actuals[i]
        errors.append(abs(pred - actual))

    return sum(errors) / len(errors)


def synthesize_signals(
    bad_trade_probability: float,
    model_disagreement: float,
    recent_prediction_error: float,
    *,
    bad_trade_threshold: float = 0.7,
    disagreement_threshold: float = 0.6,
    error_threshold: float = 0.5,
) -> AdvisorySignalReview:
    """Synthesise advisory signals into a consolidated reliability review.

    Combines the three signals (bad_trade_probability, model_disagreement,
    recent_prediction_error) into a single reliability assessment.

    Args:
        bad_trade_probability:  Probability (0-1) that the proposed trade
                                would be a net loser.
        model_disagreement:     Disagreement score (0-1) between AlphaForge
                                and critic.
        recent_prediction_error: Mean absolute error (R-units) over the
                                recent window.
        bad_trade_threshold:    Above this, the trade is flagged as risky.
        disagreement_threshold: Above this, signals are downweighted.
        error_threshold:        Above this, critic reliability is degraded.

    Returns:
        AdvisorySignalReview with reliability assessment.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Determine reliability
    if recent_prediction_error > error_threshold:
        reliability = "DEGRADED"
    elif bad_trade_probability > bad_trade_threshold and model_disagreement > disagreement_threshold:
        reliability = "LOW"
    elif bad_trade_probability > bad_trade_threshold or model_disagreement > disagreement_threshold:
        reliability = "MODERATE"
    else:
        reliability = "HIGH"

    return AdvisorySignalReview(
        bad_trade_probability=round(bad_trade_probability, 4),
        model_disagreement=round(model_disagreement, 4),
        recent_prediction_error=round(recent_prediction_error, 6),
        prediction_error_window=20,  # matches default window in compute fn
        reliability=reliability,
        signal_timestamp=timestamp,
        is_advisory=True,
    )


# ---------------------------------------------------------------------------
# AdvisorySignalTracker — keeps rolling history for prediction error
# ---------------------------------------------------------------------------


class AdvisorySignalTracker:
    """Tracks predictions and actuals for rolling error computation.

    Maintains a sliding window of (prediction, actual) pairs and provides
    the three advisory signals for the critic.
    """

    def __init__(self, max_window: int = 100):
        """Initialise the tracker.

        Args:
            max_window: Maximum number of (prediction, actual) pairs to
                        retain. The default 100 is larger than the typical
                        error window of 20, allowing warm-up.
        """
        self._predictions: deque[float] = deque(maxlen=max_window)
        self._actuals: deque[float] = deque(maxlen=max_window)

    def record_outcome(self, prediction: float, actual: float) -> None:
        """Record a single (prediction, actual) pair after the outcome is known.

        Args:
            prediction: Critic's predicted value (e.g. expected_R).
            actual:     Realised outcome (e.g. realized_r_net).
        """
        self._predictions.append(prediction)
        self._actuals.append(actual)

    def get_signals(
        self,
        critic_value: float,
        *,
        af_output: dict[str, Any] | None = None,
        critic_output: dict[str, Any] | None = None,
        lower_quantile: float | None = None,
        conformal_p_value: float | None = None,
        error_window: int = 20,
    ) -> AdvisorySignalReview:
        """Compute all three advisory signals from tracked data.

        Args:
            critic_value:     Current critic Q-value for the proposed action.
            af_output:        AlphaForge output (optional).
            critic_output:    Critic review dict (optional).
            lower_quantile:   Lower quantile of Q(s,a) (optional).
            conformal_p_value: Conformal p-value (optional).
            error_window:     Window size for prediction error.

        Returns:
            AdvisorySignalReview with all signals.
        """
        btp = compute_bad_trade_probability(
            critic_value,
            lower_quantile=lower_quantile,
            conformal_p_value=conformal_p_value,
        )
        dis = compute_model_disagreement(af_output, critic_output)

        preds = list(self._predictions)
        actuals = list(self._actuals)
        err = compute_recent_prediction_error(preds, actuals, window=error_window)

        return synthesize_signals(btp, dis, err)

    def reset(self) -> None:
        """Clear all tracked data."""
        self._predictions.clear()
        self._actuals.clear()

    @property
    def n_tracked(self) -> int:
        """Number of (prediction, actual) pairs tracked."""
        return len(self._predictions)
