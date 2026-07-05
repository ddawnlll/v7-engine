"""
Shadow critic runtime — runs critic alongside live execution in advisory mode.

The ShadowCriticRunner wires a trained Policy Critic (V2 supervised or V3 IQL)
into the scan runtime loop in **shadow-only mode**. The critic records a
PolicyCriticReview for every decision but has **zero influence** on execution.

Key principles:
  - Advisory output ONLY (no override of gates, confidence, or actions).
  - All reviews are persisted for offline analysis.
  - Disagreement patterns vs V7 policy are logged and aggregated.
  - Safe degrade: if the critic is unavailable, execution continues unchanged.

Flow (Phase 4, per ai_summary §Staged Rollout):
  DecisionEvent -> ShadowCriticRunner.review()
    -> IQLTrainer.review() (or supervised v2 equivalent)
    -> PolicyCriticReview dict
    -> persisted + logged

Domain boundaries (never violated):
  - Cannot override HARD_BLOCK gates (ai_summary §Action Mapping rule 1)
  - Cannot change recommended_action, confidence, or any execution field
  - Is the LOWEST authority in simulation > realized > contract > runtime > model
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from v7.policy_critic.replay_buffer import (
    CRITIC_ACTION_LONG,
    CRITIC_ACTION_NO_TRADE,
    CRITIC_ACTION_SHORT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Disagreement tracking
# ---------------------------------------------------------------------------


@dataclass
class DisagreementLog:
    """Aggregated disagreement statistics between critic and V7 policy.

    Attributes:
        total_reviews:          Total number of reviews performed.
        verdict_counts:         Distribution of critic verdicts.
        disagreements:          Number of times critic verdict != V7 policy outcome.
        disagreement_rate:      disagreements / total_reviews.
        veto_shadow_count:      Number of shadow VETO_TO_NO_TRADE verdicts.
        veto_shadow_rate:       veto_shadow_count / total_reviews.
        last_reset:             ISO 8601 timestamp of last statistics reset.
    """
    total_reviews: int = 0
    verdict_counts: dict[str, int] = field(default_factory=lambda: {
        "ALLOW": 0, "DOWNWEIGHT_CONFIDENCE": 0, "VETO_TO_NO_TRADE": 0, "REQUIRE_REVIEW": 0,
    })
    disagreements: int = 0
    disagreement_rate: float = 0.0
    veto_shadow_count: int = 0
    veto_shadow_rate: float = 0.0
    last_reset: str = ""


# ---------------------------------------------------------------------------
# ShadowCriticRunner
# ---------------------------------------------------------------------------


class ShadowCriticRunner:
    """Runs the Policy Critic alongside live execution in shadow/advisory mode.

    The runner is invoked for every decision in the scan loop (after hard gates,
    before execution). It:
      1. Checks whether the hard-gate result is a HARD_BLOCK — if so, the critic
         is NOT consulted (per ai_summary §Action Mapping rule 1).
      2. Calls the active critic's review function to produce a review dict.
      3. Logs disagreements between the critic verdict and V7's enacted action.
      4. Persists every review for offline analysis.
      5. Reports aggregated disagreement statistics.

    Usage (in scan_runtime.py):
        runner = ShadowCriticRunner(review_fn=my_critic.review)
        review = runner.review(decision_event, hard_gate_result)
        # review is advisory only — execution proceeds unchanged.
    """

    def __init__(
        self,
        review_fn: Callable[..., dict[str, Any]] | None = None,
        *,
        persist_fn: Callable[[dict[str, Any]], None] | None = None,
        critic_name: str = "shadow_iql_v3",
        enabled: bool = True,
    ):
        """Initialise the shadow critic runner.

        Args:
            review_fn:     Function that takes (state, proposed_action, ...)
                           and returns a PolicyCriticReview dict. If None, the
                           runner operates in degrade-safe mode (returns default
                           review with is_advisory=True, no errors).
            persist_fn:    Optional function to persist a review dict (e.g. write
                           to database). If None, reviews are logged but not
                           persisted beyond in-memory stats.
            critic_name:   Human-readable name for this critic instance (logged).
            enabled:       If False, review() is a no-op that returns a default
                           review. Toggled by POLICY_CRITIC_ACTIVE setting.
        """
        self._review_fn = review_fn
        self._persist_fn = persist_fn
        self.critic_name = critic_name
        self._enabled = enabled
        self._stats = DisagreementLog(
            last_reset=datetime.now(timezone.utc).isoformat(),
        )

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def stats(self) -> DisagreementLog:
        """Current disagreement statistics (snapshot)."""
        return DisagreementLog(
            total_reviews=self._stats.total_reviews,
            verdict_counts=dict(self._stats.verdict_counts),
            disagreements=self._stats.disagreements,
            disagreement_rate=self._stats.disagreement_rate,
            veto_shadow_count=self._stats.veto_shadow_count,
            veto_shadow_rate=self._stats.veto_shadow_rate,
            last_reset=self._stats.last_reset,
        )

    def enable(self) -> None:
        """Enable the shadow critic."""
        self._enabled = True
        logger.info("ShadowCriticRunner enabled.")

    def disable(self) -> None:
        """Disable the shadow critic (safe degrade)."""
        self._enabled = False
        logger.info("ShadowCriticRunner disabled — safe degrade mode.")

    def reset_stats(self) -> None:
        """Reset all disagreement statistics."""
        self._stats = DisagreementLog(
            last_reset=datetime.now(timezone.utc).isoformat(),
        )

    def review(
        self,
        *,
        state: dict[str, Any],
        proposed_action: str,
        hard_gate_result: dict[str, Any] | None = None,
        v7_enacted_action: str | None = None,
        **critic_kwargs: Any,
    ) -> dict[str, Any]:
        """Run critic review for a single decision point.

        This is the main entry point called from the scan loop.

        Args:
            state:              Canonical feature vector at decision time.
            proposed_action:    The action proposed by hard gates (LONG/SHORT).
            hard_gate_result:   Optional dict from hard gate evaluation. If
                                present and contains HARD_BLOCK, the critic is
                                skipped (per rule 1).
            v7_enacted_action:  The action that V7 actually enacted (for
                                disagreement tracking). If None, disagreement
                                is not computed.
            **critic_kwargs:    Additional kwargs passed through to the review_fn.

        Returns:
            PolicyCriticReview dict (always with is_advisory=True).
        """
        # Rule 1: Hard gate fail -> critic NOT consulted
        if _is_hard_block(hard_gate_result):
            default_review = self._default_review(
                state, proposed_action,
                skip_reason="hard_gate_blocked",
                critic_verdict="NOT_EVALUATED",
            )
            return default_review

        if not self._enabled or self._review_fn is None:
            # Safe degrade: critic unavailable
            return self._default_review(
                state, proposed_action,
                skip_reason="critic_unavailable",
                critic_verdict="NOT_EVALUATED",
            )

        try:
            review = self._review_fn(
                state=state,
                proposed_action=proposed_action,
                **critic_kwargs,
            )
        except Exception as exc:
            logger.error(
                "ShadowCriticRunner: review_fn raised %s: %s",
                type(exc).__name__, exc,
            )
            return self._default_review(
                state, proposed_action,
                skip_reason=f"critic_error: {type(exc).__name__}",
                critic_verdict="NOT_EVALUATED",
            )

        # Ensure is_advisory is always True
        review["is_advisory"] = True

        # Track disagreement with V7 policy
        self._track_disagreement(review, v7_enacted_action)

        # Persist if a persistence function is configured
        if self._persist_fn is not None:
            try:
                self._persist_fn(review)
            except Exception as exc:
                logger.warning(
                    "ShadowCriticRunner: persist_fn raised %s: %s",
                    type(exc).__name__, exc,
                )

        logger.debug(
            "ShadowCriticRunner: %s | verdict=%s | action=%s",
            self.critic_name, review.get("critic_verdict"), proposed_action,
        )

        return review

    def get_disagreement_report(self) -> dict[str, Any]:
        """Return a human-readable disagreement report."""
        s = self._stats
        return {
            "critic_name": self.critic_name,
            "enabled": self._enabled,
            "total_reviews": s.total_reviews,
            "verdict_counts": dict(s.verdict_counts),
            "disagreements": s.disagreements,
            "disagreement_rate": round(s.disagreement_rate, 4),
            "veto_shadow_count": s.veto_shadow_count,
            "veto_shadow_rate": round(s.veto_shadow_rate, 4),
            "last_reset": s.last_reset,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _default_review(
        self,
        state: dict[str, Any],
        proposed_action: str,
        *,
        skip_reason: str = "",
        critic_verdict: str = "NOT_EVALUATED",
    ) -> dict[str, Any]:
        """Produce a default review when the critic is unavailable or skipped."""
        return {
            "critic_value_LONG": 0.0,
            "critic_value_SHORT": 0.0,
            "critic_value_NO_TRADE": 0.0,
            "critic_verdict": critic_verdict,
            "critic_confidence_adjustment": 1.0,
            "critic_veto_reason": skip_reason,
            "is_advisory": True,
            "conformal_p_value": 0.0,
            "regret_r": 0.0,
            "expected_R": 0.0,
            "review_id": f"shadow_{self.critic_name}_{datetime.now(timezone.utc).timestamp():.0f}",
            "critic_name": self.critic_name,
        }

    def _track_disagreement(
        self,
        review: dict[str, Any],
        v7_enacted_action: str | None,
    ) -> None:
        """Update disagreement statistics."""
        self._stats.total_reviews += 1
        verdict = review.get("critic_verdict", "NOT_EVALUATED")
        self._stats.verdict_counts[verdict] = (
            self._stats.verdict_counts.get(verdict, 0) + 1
        )

        if verdict == "VETO_TO_NO_TRADE":
            self._stats.veto_shadow_count += 1

        # Disagreement: critic says VETO but V7 enacted LONG/SHORT
        if v7_enacted_action is not None and verdict == "VETO_TO_NO_TRADE":
            if v7_enacted_action in (CRITIC_ACTION_LONG, CRITIC_ACTION_SHORT):
                self._stats.disagreements += 1

        # Disagreement: critic says DOWNWEIGHT but V7 enacted full confidence
        if v7_enacted_action is not None and verdict == "DOWNWEIGHT_CONFIDENCE":
            if v7_enacted_action in (CRITIC_ACTION_LONG, CRITIC_ACTION_SHORT):
                self._stats.disagreements += 1

        # Update rates
        n = self._stats.total_reviews
        self._stats.disagreement_rate = self._stats.disagreements / n if n > 0 else 0.0
        self._stats.veto_shadow_rate = self._stats.veto_shadow_count / n if n > 0 else 0.0

    def __repr__(self) -> str:
        return (
            f"ShadowCriticRunner(critic_name={self.critic_name!r}, "
            f"enabled={self._enabled}, reviews={self._stats.total_reviews})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_hard_block(hard_gate_result: dict[str, Any] | None) -> bool:
    """Check if a hard gate result represents a HARD_BLOCK.

    Per ai_summary §Action Mapping rule 1: hard gate fail (e.g. HARD_BLOCK
    at inference_engine) means NO_TRADE and critic is NOT consulted.

    Args:
        hard_gate_result: Dict from hard gate evaluation, or None.

    Returns:
        True if the hard gate produced a block.
    """
    if hard_gate_result is None:
        return False

    # Check for HARD_BLOCK indicator
    block = hard_gate_result.get("hard_block", False)
    if block:
        return True

    # Check constraint_level for HARD_BLOCK
    constraint = hard_gate_result.get("constraint_level", "")
    if isinstance(constraint, str) and constraint.upper() == "HARD_BLOCK":
        return True

    # Check decision field for hard gate failure patterns
    decision = hard_gate_result.get("decision", "")
    if isinstance(decision, str) and decision.upper() in ("HARD_BLOCK", "BLOCKED"):
        return True

    return False
