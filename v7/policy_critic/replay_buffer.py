"""
Replay buffer for Policy Critic offline RL training.

Builds (state, action, reward, next_state, terminal) tuples from DecisionEvents
routed through the simulation engine for authoritative realized_r_net.

Each tuple contains:
  - state:        Canonical feature vector at decision time (dictionary of
                  market/alpha features from AnalysisResult + context).
  - action:       The action taken — ENTER_LONG, ENTER_SHORT, or HOLD (mapped
                  to NO_TRADE for the critic's 3-action space).
  - reward:       Realized R-net from simulation engine (economic truth).
  - next_state:   Feature vector at the next decision point (same symbol/mode).
  - terminal:     True if exit_reason is COMPLETE and episode ended; False if
                  more decisions follow.

Route: DecisionEvent -> simulate via /simulation engine -> realized_r_net.
Only COMPLETE-resolution episodes contribute terminal=True; UNRESOLVED/
INVALIDATED entries are excluded.

Per design.md section 4: "Route through /simulation engine, not the runtime
historical engine (which has separate fee/slippage — parity divergence)."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Action space for critic (locked per DEC-002: {LONG, SHORT, NO_TRADE})
CRITIC_ACTION_LONG = "LONG"
CRITIC_ACTION_SHORT = "SHORT"
CRITIC_ACTION_NO_TRADE = "NO_TRADE"


# Map DecisionEvent/V7 decisions to critic action space
_DECISION_TO_CRITIC = {
    "ENTER_LONG": CRITIC_ACTION_LONG,
    "ENTER_SHORT": CRITIC_ACTION_SHORT,
    "EXIT_LONG": CRITIC_ACTION_NO_TRADE,
    "EXIT_SHORT": CRITIC_ACTION_NO_TRADE,
    "HOLD": CRITIC_ACTION_NO_TRADE,
}


def map_decision_to_critic_action(decision: str) -> str:
    """Map a V7 DecisionEvent decision to critic action space.

    Args:
        decision: One of ENTER_LONG, ENTER_SHORT, EXIT_LONG, EXIT_SHORT, HOLD.

    Returns:
        One of LONG, SHORT, NO_TRADE.

    Raises:
        ValueError: If decision is not in the known set.
    """
    action = _DECISION_TO_CRITIC.get(decision)
    if action is None:
        raise ValueError(
            f"Unknown decision '{decision}'. "
            f"Valid: {sorted(_DECISION_TO_CRITIC.keys())}"
        )
    return action


@dataclass(frozen=True)
class ReplayTuple:
    """A single (state, action, reward, next_state, terminal) transition.

    Attributes:
        state: Dictionary of features at decision time.
        action: Critic action — LONG, SHORT, or NO_TRADE.
        reward: Realized R-net (float). For NO_TRADE, this is 0.0.
        next_state: Dictionary of features at next decision point, or empty
                    dict if terminal.
        terminal: True if episode ended (resolution COMPLETE), False if more
                  decisions follow.
        decision_event_id: Source DecisionEvent.event_id.
        symbol: Trading symbol for grouping/lookup.
        mode: Trading mode for mode-specific replay.
        timestamp: ISO 8601 UTC timestamp of the decision.
            used as ``kwargs`` to ``build_state_feature_vector``.
    """

    state: dict[str, Any]
    action: str
    reward: float
    next_state: dict[str, Any]
    terminal: bool
    decision_event_id: str
    symbol: str
    mode: str
    timestamp: str = ""
    realized_r_gross: float = 0.0
    fee_cost_r: float = 0.0
    slippage_cost_r: float = 0.0
    funding_cost_r: float = 0.0


@dataclass
class ReplayBuffer:
    """Fixed-size FIFO replay buffer for offline RL training.

    Holds ReplayTuple entries keyed by symbol+mode. Supports insertion,
    sequential retrieval, and sampling.

    NOT thread-safe — intended for single-process offline training.
    """

    capacity: int = 100_000
    _storage: list[ReplayTuple] = field(default_factory=list, init=False)

    def __len__(self) -> int:
        """Number of tuples currently stored."""
        return len(self._storage)

    def add(
        self,
        state: dict[str, Any],
        action: str,
        reward: float,
        next_state: dict[str, Any],
        terminal: bool,
        *,
        decision_event_id: str = "",
        symbol: str = "",
        mode: str = "",
        timestamp: str = "",
        realized_r_gross: float = 0.0,
        fee_cost_r: float = 0.0,
        slippage_cost_r: float = 0.0,
        funding_cost_r: float = 0.0,
    ) -> ReplayTuple:
        """Add a transition tuple to the buffer.

        When capacity is exceeded, the oldest entry is evicted (FIFO).
        """
        entry = ReplayTuple(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            terminal=terminal,
            decision_event_id=decision_event_id,
            symbol=symbol,
            mode=mode,
            timestamp=timestamp,
            realized_r_gross=realized_r_gross,
            fee_cost_r=fee_cost_r,
            slippage_cost_r=slippage_cost_r,
            funding_cost_r=funding_cost_r,
        )
        self._storage.append(entry)
        if len(self._storage) > self.capacity:
            self._storage.pop(0)
        return entry

    def sample(self, n: int) -> list[ReplayTuple]:
        """Return the most recent *n* tuples (FIFO tail).

        If fewer than *n* tuples exist, returns all available.
        """
        return self._storage[-n:] if n < len(self._storage) else list(self._storage)

    def sample_by_mode(self, mode: str, n: int) -> list[ReplayTuple]:
        """Return the most recent *n* tuples for a specific mode."""
        filtered = [t for t in self._storage if t.mode == mode]
        return filtered[-n:] if n < len(filtered) else filtered

    def clear(self) -> None:
        """Remove all entries."""
        self._storage.clear()


def build_state_feature_vector(*, analysis_result: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Build a state feature vector from an AnalysisResult + optional context.

    Extracts the canonical feature set for the Policy Critic from the
    AnalysisResult contract fields. Additional context (market data,
    regime flags) can be passed via kwargs.

    Args:
        analysis_result: A contract-valid AnalysisResult dict.
        **kwargs: Additional context features (e.g. regime_label, atr,
                  volatility, spread_bps).

    Returns:
        A flat feature dictionary suitable as a state representation.
    """
    state: dict[str, Any] = {
        "symbol": analysis_result.get("symbol", ""),
        "mode": analysis_result.get("mode", ""),
        "confidence": analysis_result.get("confidence", 0.0),
        "position_size_pct": analysis_result.get("position_size_pct", 0.0),
        "entry_price": analysis_result.get("entry_price", 0.0),
        "stop_loss_price": analysis_result.get("stop_loss_price", 0.0),
        "take_profit_price": analysis_result.get("take_profit_price", 0.0),
        "decision": analysis_result.get("decision", "HOLD"),
    }

    # Merge execution eligibility gate scores if present
    eligibility = analysis_result.get("execution_eligibility", {})
    if isinstance(eligibility, dict):
        state["gate_confidence"] = eligibility.get("confidence_gate", False)
        state["gate_risk"] = eligibility.get("risk_gate", False)
        state["gate_regime"] = eligibility.get("regime_gate", False)
        state["gate_cost"] = eligibility.get("cost_gate", False)
        state["gate_overall"] = eligibility.get("overall_eligible", False)

    # Merge any additional context passed as kwargs
    state.update(kwargs)

    return state


def build_replay_tuple(
    *,
    analysis_result: dict[str, Any],
    simulation_output: dict[str, Any] | None = None,
    realized_r_net: float = 0.0,
    next_state: dict[str, Any] | None = None,
    terminal: bool = False,
    decision_event: dict[str, Any] | None = None,
    realized_r_gross: float = 0.0,
    fee_cost_r: float = 0.0,
    slippage_cost_r: float = 0.0,
    funding_cost_r: float = 0.0,
    **context_kwargs: Any,
) -> ReplayTuple:
    """Build a single ReplayTuple from V7 contract objects.

    Args:
        analysis_result: A contract-valid AnalysisResult dict (the state
                         source).
        simulation_output: Optional SimulationOutput dict (provides realized
                           costs when available). Overrides explicit cost
                           params if both given.
        realized_r_net: Realized R-net reward. If simulation_output is
                        provided, this is ignored in favor of the per-action
                        outcome from the simulation.
        next_state: Feature dict at the next decision point (empty for
                    terminal).
        terminal: True if this is the last transition in the episode.
        decision_event: Optional DecisionEvent dict for event metadata.
        realized_r_gross: Pre-cost realized R from the actual outcome.
        fee_cost_r: Fee cost in R terms for the actual outcome.
        slippage_cost_r: Slippage cost in R terms for the actual outcome.
        funding_cost_r: Funding cost in R terms for the actual outcome.
        **context_kwargs: Passed to build_state_feature_vector.

    Returns:
        A ReplayTuple with state, action, reward, and metadata.
    """
    # Determine which action was taken
    decision = analysis_result.get("decision", "HOLD")
    action = map_decision_to_critic_action(decision)

    # Determine reward: prefer simulation output if available
    reward = realized_r_net
    gross = realized_r_gross
    fcr = fee_cost_r
    scr = slippage_cost_r
    fund_r = funding_cost_r

    if simulation_output is not None:
        # Extract per-action outcome from simulation output
        if action == CRITIC_ACTION_LONG:
            lo = simulation_output.get("long_outcome", {})
            if isinstance(lo, dict):
                reward = lo.get("realized_r_net", 0.0)
                gross = lo.get("realized_r_gross", 0.0)
                fcr = lo.get("fee_cost_r", 0.0)
                scr = lo.get("slippage_cost_r", 0.0)
                fund_r = lo.get("funding_cost_r", 0.0)
        elif action == CRITIC_ACTION_SHORT:
            so = simulation_output.get("short_outcome", {})
            if isinstance(so, dict):
                reward = so.get("realized_r_net", 0.0)
                gross = so.get("realized_r_gross", 0.0)
                fcr = so.get("fee_cost_r", 0.0)
                scr = so.get("slippage_cost_r", 0.0)
                fund_r = so.get("funding_cost_r", 0.0)
        # NO_TRADE reward: 0.0 (first-class zero-cost baseline)

    # Build state
    state = build_state_feature_vector(analysis_result=analysis_result, **context_kwargs)

    # Build next_state
    ns = next_state if next_state is not None else {}

    # Event metadata
    event_id = (
        decision_event.get("event_id", "")
        if decision_event is not None
        else ""
    )
    symbol = analysis_result.get("symbol", "")
    mode = analysis_result.get("mode", "")
    timestamp = analysis_result.get("analysis_timestamp", "")

    return ReplayTuple(
        state=state,
        action=action,
        reward=reward,
        next_state=ns,
        terminal=terminal,
        decision_event_id=event_id,
        symbol=symbol,
        mode=mode,
        timestamp=timestamp,
        realized_r_gross=gross,
        fee_cost_r=fcr,
        slippage_cost_r=scr,
        funding_cost_r=fund_r,
    )
