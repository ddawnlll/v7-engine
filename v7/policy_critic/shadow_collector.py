"""
Shadow replay buffer collector for Policy Critic.

Collects (state, action, reward, next_state, terminal) tuples from live
paper-trading decisions and their realized outcomes, without interfering
with V7's hard gates or execution.

This is the v1 shadow collector — it observes, never enacts. The collected
tuples are subsampled for class imbalance and fed to offline RL training.

Flow:
  DecisionEvent + TradeOutcome
    -> ShadowCollector.collect_from_paper()
    -> (s, a, r, s', t) tuple
    -> SubsamplingStrategy.rebalance()
    -> ShadowIntegration.observe()
    -> buffer stats
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from v7.policy_critic.replay_buffer import (
    CRITIC_ACTION_LONG,
    CRITIC_ACTION_NO_TRADE,
    CRITIC_ACTION_SHORT,
    map_decision_to_critic_action,
)

logger = logging.getLogger(__name__)

# Default target ratios for subsampling (action -> proportion).
# Prevents the NO_TRADE majority from dominating the training set.
_DEFAULT_TARGET_RATIOS: dict[str, float] = {
    CRITIC_ACTION_LONG: 0.35,
    CRITIC_ACTION_SHORT: 0.35,
    CRITIC_ACTION_NO_TRADE: 0.30,
}


@dataclass(frozen=True)
class ShadowTuple:
    """A single (state, action, reward, next_state, terminal) transition
    collected from paper trading.

    Attributes:
        state:      Feature vector dict at decision time.
        action:     Critic action space — LONG, SHORT, or NO_TRADE.
        reward:     Realized R-net from trade outcome.
        next_state: Feature vector at next decision point, or empty dict
                    if terminal.
        terminal:   True if episode ended.
        symbol:     Trading symbol.
        event_id:   Source DecisionEvent ID.
    """
    state: dict[str, Any]
    action: str
    reward: float
    next_state: dict[str, Any]
    terminal: bool
    symbol: str = ""
    event_id: str = ""


class ShadowCollector:
    """Collects (state, action, reward, next_state, terminal) tuples from
    paper-trading DecisionEvents and their realised TradeOutcomes.

    This is a passive observer — it never enacts or overrides decisions.
    """

    @staticmethod
    def collect_from_paper(
        decision_event: dict[str, Any],
        trade_outcome: dict[str, Any] | None = None,
        *,
        next_state_override: dict[str, Any] | None = None,
    ) -> ShadowTuple | None:
        """Build a ShadowTuple from a DecisionEvent and optional TradeOutcome.

        Args:
            decision_event: DecisionEvent-compatible dict. Expected keys:
                request (dict with decision, confidence, etc.),
                event_id (str), symbol (str), mode (str).
            trade_outcome: Optional TradeOutcome dict with realised costs.
                If None, reward defaults to 0.0 (unresolved trade).
            next_state_override: Optional next-state dict. When the collector
                runs after the next decision, the caller provides the new
                state here. If None, next_state is empty dict.

        Returns:
            ShadowTuple if the event can be collected, or None if the event
            should be skipped (e.g. invalid event type, missing fields).
        """
        request = decision_event.get("request") or decision_event.get("analysis_result") or {}
        if not isinstance(request, dict) or not request:
            logger.warning("ShadowCollector: no request/analysis_result in decision_event")
            return None

        state = ShadowCollector.extract_state(request)
        action = ShadowCollector.extract_action(decision_event)
        reward = ShadowCollector.extract_reward(trade_outcome)
        terminal = ShadowCollector.is_terminal(trade_outcome)
        next_state = next_state_override if next_state_override is not None else {}

        if action is None:
            logger.debug("ShadowCollector: skipping event with no valid action")
            return None

        return ShadowTuple(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            terminal=terminal,
            symbol=decision_event.get("symbol", ""),
            event_id=decision_event.get("event_id", "") or decision_event.get("decision_event_id", ""),
        )

    @staticmethod
    def extract_state(request: dict[str, Any]) -> dict[str, Any]:
        """Extract a canonical feature vector from an AnalysisResult/request dict.

        Args:
            request: An AnalysisResult or request dict (contract shape).

        Returns:
            Flat feature dict with market context and decision features.
        """
        state: dict[str, Any] = {
            "symbol": request.get("symbol", ""),
            "mode": request.get("mode", ""),
            "confidence": request.get("confidence", 0.0),
            "decision": request.get("decision", "HOLD"),
            "entry_price": request.get("entry_price", 0.0),
            "stop_loss_price": request.get("stop_loss_price", 0.0),
            "take_profit_price": request.get("take_profit_price", 0.0),
            "position_size_pct": request.get("position_size_pct", 0.0),
        }

        # Merge execution eligibility if present
        eligibility = request.get("execution_eligibility", {})
        if isinstance(eligibility, dict):
            state["gate_overall"] = eligibility.get("overall_eligible", False)

        # Merge any market context from the analysis
        context = request.get("market_context", {})
        if isinstance(context, dict):
            state["atr"] = context.get("atr", 0.0)
            state["spread_bps"] = context.get("spread_bps", 0.0)
            state["volatility"] = context.get("volatility", 0.0)

        return state

    @staticmethod
    def extract_action(event: dict[str, Any]) -> str | None:
        """Map a DecisionEvent to critic action space.

        Looks for the decision in ``request.decision`` or a top-level
        ``decision`` key. If neither is found, falls back to
        ``event_type``.

        Args:
            event: DecisionEvent-compatible dict.

        Returns:
            LONG, SHORT, NO_TRADE, or None if the decision is unrecognised.
        """
        # Prefer top-level 'decision' key, then request sub-dict, then event_type
        decision = event.get("decision", "")
        if not decision:
            request = event.get("request") or event.get("analysis_result") or {}
            decision = request.get("decision", "")
        if not decision:
            decision = event.get("event_type", "")

        if not decision:
            return None

        try:
            return map_decision_to_critic_action(decision)
        except ValueError:
            return None

    @staticmethod
    def extract_reward(outcome: dict[str, Any] | None) -> float:
        """Extract realised reward from a TradeOutcome dict.

        Uses ``realized_r_net`` as the primary reward signal. If the
        outcome is None or missing the field, returns 0.0.

        Args:
            outcome: TradeOutcome-compatible dict or None.

        Returns:
            Realised reward value (float).
        """
        if not isinstance(outcome, dict):
            return 0.0
        return float(outcome.get("realized_r_net", 0.0))

    @staticmethod
    def is_terminal(outcome: dict[str, Any] | None) -> bool:
        """Determine if the episode is terminal from the TradeOutcome.

        An episode is terminal if:
          - outcome is not None and outcome.exit_reason == "COMPLETE", or
          - outcome is not None and outcome.get("terminal", False) is True.

        Args:
            outcome: TradeOutcome-compatible dict or None.

        Returns:
            True if the episode has ended, False otherwise.
        """
        if not isinstance(outcome, dict):
            return False
        exit_reason = outcome.get("exit_reason", "")
        if isinstance(exit_reason, str) and exit_reason.upper() == "COMPLETE":
            return True
        return bool(outcome.get("terminal", False))


class SubsamplingStrategy:
    """Rebalances a list of ShadowTuples to mitigate class imbalance.

    The typical paper-trading distribution is heavily skewed toward
    NO_TRADE (~70-80%). The strategy downsamples the majority class(es)
    to match target ratios while preserving all minority tuples.
    """

    def __init__(self, target_ratios: dict[str, float] | None = None):
        """Initialise with per-action target ratios.

        Args:
            target_ratios: Map of action -> target proportion after
                subsampling. Defaults to LONG=0.35, SHORT=0.35,
                NO_TRADE=0.30. Keys not in the map default to their
                original proportion (not downsampled).
        """
        self._target_ratios = dict(_DEFAULT_TARGET_RATIOS)
        if target_ratios:
            self._target_ratios.update(target_ratios)

    @property
    def target_ratios(self) -> dict[str, float]:
        """Current target ratios (read-only view)."""
        return dict(self._target_ratios)

    def rebalance(self, tuples: list[ShadowTuple]) -> list[ShadowTuple]:
        """Rebalance a list of ShadowTuples to the configured target ratios.

        The smallest class determines the absolute count; other classes
        are downsampled to match the ratio proportion. All tuples from
        classes not in ``target_ratios`` are kept unchanged.

        Args:
            tuples: List of ShadowTuples to rebalance.

        Returns:
            Subsampled list preserving the relative order of kept tuples.
        """
        if not tuples:
            return []

        # Group by action
        by_action: dict[str, list[ShadowTuple]] = {}
        for t in tuples:
            by_action.setdefault(t.action, []).append(t)

        # Count per action
        counts = {action: len(group) for action, group in by_action.items()}

        # Determine classes that have target ratios and are present
        scoped_actions = [a for a in self._target_ratios if a in by_action]
        if not scoped_actions:
            # No target ratios match -> return as-is
            return list(tuples)

        # The smallest class (among those with target ratios) determines scale
        min_count = min(counts[a] for a in scoped_actions)
        ideal_count = {
            a: max(1, round(min_count * self._target_ratios[a] / min(
                self._target_ratios[sa] for sa in scoped_actions
            )))
            for a in scoped_actions
        }

        # Cap by available count
        sample_sizes: dict[str, int] = {}
        for a in scoped_actions:
            available = counts[a]
            desired = ideal_count[a]
            sample_sizes[a] = min(desired, available)

        # Build result: sample from each class, preserve order
        result: list[ShadowTuple] = []
        for a in scoped_actions:
            n = sample_sizes[a]
            group = by_action[a]
            if n >= len(group):
                result.extend(group)
            else:
                # Take evenly spaced samples to preserve temporal distribution
                step = len(group) / n
                sampled = [group[int(i * step)] for i in range(n)]
                result.extend(sampled)

        # Add tuples from actions not covered by target ratios
        for action, group in by_action.items():
            if action not in scoped_actions:
                result.extend(group)

        return result


class ShadowIntegration:
    """Ties together the shadow collection pipeline.

    Observes live decision events and trade outcomes, stores collected
    tuples, and provides buffer statistics for monitoring and training
    readiness assessment.
    """

    def __init__(self, max_buffer_size: int = 50_000):
        """Initialise the shadow buffer.

        Args:
            max_buffer_size: Maximum number of ShadowTuples to retain
                (FIFO eviction). Default 50,000.
        """
        self._buffer: list[ShadowTuple] = []
        self._max_buffer_size = max_buffer_size
        self._collector = ShadowCollector()
        self._subsampler = SubsamplingStrategy()

    @property
    def buffer(self) -> list[ShadowTuple]:
        """Read-only view of the current buffer."""
        return list(self._buffer)

    @property
    def size(self) -> int:
        """Number of tuples currently in the buffer."""
        return len(self._buffer)

    def observe(
        self,
        decision_event: dict[str, Any],
        trade_outcome: dict[str, Any] | None = None,
        *,
        next_state_override: dict[str, Any] | None = None,
    ) -> ShadowTuple | None:
        """Observe a single decision event and optional trade outcome.

        The resulting ShadowTuple is added to the internal buffer (with
        FIFO eviction).

        Args:
            decision_event: DecisionEvent-compatible dict.
            trade_outcome: Optional TradeOutcome dict.
            next_state_override: Optional next-state dict.

        Returns:
            The ShadowTuple if collected, None if skipped.
        """
        shadow = self._collector.collect_from_paper(
            decision_event,
            trade_outcome,
            next_state_override=next_state_override,
        )
        if shadow is None:
            return None

        self._buffer.append(shadow)
        if len(self._buffer) > self._max_buffer_size:
            excess = len(self._buffer) - self._max_buffer_size
            self._buffer = self._buffer[excess:]

        return shadow

    def get_statistics(self) -> dict[str, Any]:
        """Return summary statistics about the current buffer.

        Returns:
            Dict with:
              - total_tuples: int
              - action_distribution: dict[str, int] (raw counts per action)
              - unique_symbols: int
              - symbols: list[str] (sorted)
              - terminal_count: int
              - terminal_ratio: float
              - buffer_fill_pct: float (0-100)
              - mean_reward: float
              - median_reward: float
        """
        if not self._buffer:
            return {
                "total_tuples": 0,
                "action_distribution": {},
                "unique_symbols": 0,
                "symbols": [],
                "terminal_count": 0,
                "terminal_ratio": 0.0,
                "buffer_fill_pct": 0.0,
                "mean_reward": 0.0,
                "median_reward": 0.0,
            }

        counts = Counter(t.action for t in self._buffer)
        symbols = sorted({t.symbol for t in self._buffer if t.symbol})
        terminal_count = sum(1 for t in self._buffer if t.terminal)
        rewards = [t.reward for t in self._buffer]
        mean_reward = sum(rewards) / len(rewards) if rewards else 0.0
        sorted_rewards = sorted(rewards)
        n = len(sorted_rewards)
        median_reward = (
            sorted_rewards[n // 2]
            if n % 2 == 1
            else (sorted_rewards[n // 2 - 1] + sorted_rewards[n // 2]) / 2.0
        ) if n > 0 else 0.0

        return {
            "total_tuples": len(self._buffer),
            "action_distribution": dict(counts),
            "unique_symbols": len(symbols),
            "symbols": symbols,
            "terminal_count": terminal_count,
            "terminal_ratio": round(terminal_count / len(self._buffer), 4) if self._buffer else 0.0,
            "buffer_fill_pct": round(len(self._buffer) / self._max_buffer_size * 100, 2),
            "mean_reward": round(mean_reward, 6),
            "median_reward": round(median_reward, 6),
        }

    def get_subsampled(self, target_ratios: dict[str, float] | None = None) -> list[ShadowTuple]:
        """Return a subsampled view of the current buffer.

        Args:
            target_ratios: Optional override for target ratios. If None,
                          uses the SubsamplingStrategy defaults.

        Returns:
            Rebalanced list of ShadowTuples.
        """
        if target_ratios is not None:
            sampler = SubsamplingStrategy(target_ratios)
        else:
            sampler = self._subsampler
        return sampler.rebalance(self._buffer)

    def clear(self) -> None:
        """Clear all collected tuples."""
        self._buffer.clear()
