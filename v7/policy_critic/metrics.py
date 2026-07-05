"""
Metrics pipeline for Policy Critic.

Extracts critic metrics from DecisionEvent review, produces CriticMetrics
dataclass instances, and converts them to PolicyCriticReview contract schema
for downstream consumption (runtime logging, operator UI, audit trail).

Flow:
  DecisionEvent (with critic_review payload)
    -> CriticMetricsPipeline.ingest()
    -> CriticMetrics dataclass
    -> CriticMetricsPipeline.to_review_schema()
    -> PolicyCriticReview contract dict
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Valid critic verdicts per PolicyCriticReview contract enum
VALID_VERDICTS = {"CORRECT", "WRONG", "AMBIGUOUS", "NOT_EVALUATED"}

# Minimum set of fields required for a valid ingest
_REQUIRED_INGEST_FIELDS = {"decision_event_id", "symbol"}


@dataclass(frozen=True)
class CriticMetrics:
    """Canonical metrics produced by the Policy Critic at a single decision point.

    All fields are populated from the critic's review of a DecisionEvent,
    combining RL value estimates, regret, expected return, and conformal
    calibration metadata.

    Attributes:
        critic_value_long:   IQL lower-quantile Q-value for LONG action.
        critic_value_short:  IQL lower-quantile Q-value for SHORT action.
        critic_verdict:      One of CORRECT, WRONG, AMBIGUOUS, NOT_EVALUATED.
        conformal_p_value:   Conformal prediction p-value for the critic's
                             verdict reliability (0-1). 0.0 if not calibrated.
        regret_r:            Regret R for the chosen action (see regret.py).
        expected_r:          Expected R from critic ensemble (see expected_return.py).
        timestamp_utc:       ISO 8601 UTC timestamp of the critic review.
        symbol:              Trading symbol (e.g. BTCUSDT).
        model_scope:         Critic model scope identifier (e.g. "v1_swing",
                             "v1_scalp", "shadow").
    """

    critic_value_long: float = 0.0
    critic_value_short: float = 0.0
    critic_verdict: str = "NOT_EVALUATED"
    conformal_p_value: float = 0.0
    regret_r: float = 0.0
    expected_r: float = 0.0
    timestamp_utc: str = ""
    symbol: str = ""
    model_scope: str = "shadow"


class CriticMetricsPipeline:
    """Pipeline that ingests a DecisionEvent, produces CriticMetrics, and
    converts to the PolicyCriticReview contract schema.

    This is the canonical entry point for all critic metric production.
    Downstream consumers (runtime logger, operator UI, audit store) should
    call ``to_review_schema()`` on the resulting metrics.
    """

    @staticmethod
    def ingest(decision_event: dict[str, Any]) -> CriticMetrics:
        """Extract critic metrics from a DecisionEvent dict.

        The DecisionEvent is expected to contain a top-level ``critic_review``
        dict with the critic's output fields. If absent, all critic values
        default to zero/NOT_EVALUATED (shadow mode).

        Args:
            decision_event: A DecisionEvent-compatible dict. Expected keys:
                - decision_event_id (str)
                - symbol (str)
                - critic_review (dict, optional) with sub-keys:
                    - critic_value_LONG (float)
                    - critic_value_SHORT (float)
                    - critic_verdict (str)
                    - conformal_p_value (float)
                    - regret_r (float)
                    - expected_r (float)
                    - model_scope (str)

        Returns:
            CriticMetrics with extracted values (or defaults).

        Raises:
            ValueError: If required top-level keys (decision_event_id, symbol)
                        are missing.
        """
        missing = _REQUIRED_INGEST_FIELDS - decision_event.keys()
        if missing:
            raise ValueError(
                f"DecisionEvent missing required fields: {sorted(missing)}. "
                f"Got keys: {sorted(decision_event.keys())}"
            )

        review = decision_event.get("critic_review")
        if not isinstance(review, dict):
            # No critic_review payload -> shadow mode defaults
            return CriticMetrics(
                timestamp_utc=_now_iso(),
                symbol=decision_event.get("symbol", ""),
                model_scope="shadow",
            )

        cr = review
        return CriticMetrics(
            critic_value_long=cr.get("critic_value_LONG", 0.0),
            critic_value_short=cr.get("critic_value_SHORT", 0.0),
            critic_verdict=cr.get("critic_verdict", "NOT_EVALUATED"),
            conformal_p_value=cr.get("conformal_p_value", 0.0),
            regret_r=cr.get("regret_r", 0.0),
            expected_r=cr.get("expected_r", 0.0),
            timestamp_utc=_now_iso(),
            symbol=decision_event.get("symbol", ""),
            model_scope=cr.get("model_scope", "shadow"),
        )

    @staticmethod
    def to_review_schema(metrics: CriticMetrics) -> dict[str, Any]:
        """Convert CriticMetrics to a PolicyCriticReview contract dict.

        The output dict matches the ``policy_critic_review.schema.json``
        contract, suitable for:
          - Writing to the audit store.
          - Attaching to a DecisionEvent as ``critic_review_output``.
          - Serialising to JSON for downstream consumers.

        Args:
            metrics: A CriticMetrics instance (frozen dataclass).

        Returns:
            A dict conforming to the PolicyCriticReview schema.
        """
        return {
            "review_id": _generate_review_id(metrics.symbol),
            "symbol": metrics.symbol,
            "model_scope": metrics.model_scope,
            "timestamp": metrics.timestamp_utc,
            "critic_value_LONG": metrics.critic_value_long,
            "critic_value_SHORT": metrics.critic_value_short,
            "critic_verdict": metrics.critic_verdict,
            "conformal_p_value": metrics.conformal_p_value,
            "regret_r": metrics.regret_r,
            "expected_r": metrics.expected_r,
        }

    @staticmethod
    def validate(metrics: CriticMetrics) -> list[str]:
        """Validate a CriticMetrics instance and return a list of issues.

        Returns an empty list if the metrics are valid. Each string is a
        human-readable description of one validation issue.

        Validation rules:
          - critic_verdict must be one of VALID_VERDICTS.
          - symbol must be non-empty.
          - model_scope must be non-empty.
          - conformal_p_value must be in [0.0, 1.0].
          - timestamp_utc must parse as ISO 8601 if non-empty.

        Args:
            metrics: CriticMetrics to validate.

        Returns:
            List of validation issue strings (empty = valid).
        """
        issues: list[str] = []

        if metrics.critic_verdict not in VALID_VERDICTS:
            issues.append(
                f"Invalid critic_verdict '{metrics.critic_verdict}'. "
                f"Must be one of {sorted(VALID_VERDICTS)}."
            )

        if not metrics.symbol:
            issues.append("symbol must be non-empty.")

        if not metrics.model_scope:
            issues.append("model_scope must be non-empty.")

        if not (0.0 <= metrics.conformal_p_value <= 1.0):
            issues.append(
                f"conformal_p_value {metrics.conformal_p_value} out of range [0.0, 1.0]."
            )

        if metrics.timestamp_utc:
            try:
                # Python 3.10 does not support "Z" suffix; normalise to +00:00
                ts = metrics.timestamp_utc.replace("Z", "+00:00")
                datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                issues.append(
                    f"timestamp_utc '{metrics.timestamp_utc}' is not valid ISO 8601."
                )

        return issues


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _generate_review_id(symbol: str) -> str:
    """Generate a unique review identifier incorporating the symbol."""
    short_id = uuid.uuid4().hex[:12]
    return f"pcr-{symbol}-{short_id}"
