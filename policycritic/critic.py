"""
Policy Critic — advisory offline-RL component for V7.

The critic sits between V7's hard gates and the final gate.
It reviews proposed actions using a learned value function and
returns a verdict: ALLOW, DOWNWEIGHT_CONFIDENCE, VETO_TO_NO_TRADE,
or REQUIRE_REVIEW.

This is a minimal IQL-based starter implementation.
"""

from __future__ import annotations

import math
import random
from typing import Any

import numpy as np

POLICY_CRITIC_VERSION = "pc-1.0.0"
ACTIONS = ["LONG_NOW", "SHORT_NOW", "NO_TRADE"]


class CriticBuffer:
    """Replay buffer of (state, action, reward, next_state) tuples."""

    def __init__(self, max_size: int = 10_000):
        self.max_size = max_size
        self.states: list[dict[str, float]] = []
        self.actions: list[int] = []
        self.rewards: list[float] = []
        self.next_states: list[dict[str, float]] = []
        self.dones: list[bool] = []

    def add(
        self,
        state: dict[str, float],
        action: int,
        reward: float,
        next_state: dict[str, float],
        done: bool = False,
    ) -> None:
        if len(self.states) >= self.max_size:
            self.states.pop(0)
            self.actions.pop(0)
            self.rewards.pop(0)
            self.next_states.pop(0)
            self.dones.pop(0)
        self.states.append(state)
        self.actions.append(action)
        self.rewards.append(reward)
        self.next_states.append(next_state)
        self.dones.append(done)

    def sample(self, batch_size: int) -> dict[str, Any]:
        n = min(batch_size, len(self.states))
        indices = random.sample(range(len(self.states)), n)
        return {
            "states": [self.states[i] for i in indices],
            "actions": [self.actions[i] for i in indices],
            "rewards": [self.rewards[i] for i in indices],
            "next_states": [self.next_states[i] for i in indices],
            "dones": [self.dones[i] for i in indices],
        }

    def __len__(self) -> int:
        return len(self.states)


class IQLCritic:
    """Implicit Q-Learning critic with expectile regression.

    Uses Ridge regression as a stand-in for the gradient-boosted
    quantile regressor ensemble described in the full design.
    """

    def __init__(self, expectile: float = 0.8):
        from sklearn.linear_model import Ridge

        self.expectile = expectile
        self.q_data: dict[int, list] = {i: [] for i in range(3)}
        self.q_models: dict[int, Ridge] = {i: Ridge(alpha=1.0) for i in range(3)}
        self._fitted = False

    def _feature_vector(self, state: dict[str, float]) -> np.ndarray:
        return np.array([float(state.get(k, 0.0)) for k in sorted(state.keys())])

    def update(self, buffer: CriticBuffer, batch_size: int = 64) -> dict[str, float]:
        if len(buffer) < max(batch_size, 5):
            return {"samples": len(buffer), "loss": 0.0}

        batch = buffer.sample(batch_size)

        for i in range(len(batch["actions"])):
            a = batch["actions"][i]
            self.q_data[a].append({
                "features": self._feature_vector(batch["states"][i]),
                "reward": batch["rewards"][i],
            })

        for a in range(3):
            if len(self.q_data[a]) < 5:
                continue
            X = np.array([d["features"] for d in self.q_data[a]])
            y = np.array([d["reward"] for d in self.q_data[a]])
            self.q_models[a].fit(X, y)
            self._fitted = True

        return {"samples": len(batch["actions"]), "loss": 0.0, "expectile": self.expectile}

    def predict(self, state: dict[str, float]) -> dict[str, float]:
        q_values = {}
        x = self._feature_vector(state).reshape(1, -1)
        for i, action in enumerate(ACTIONS):
            try:
                q_values[action] = round(float(self.q_models[i].predict(x)[0]), 4)
            except Exception:
                q_values[action] = 0.0
        return q_values


def review_action(
    critic: IQLCritic,
    state: dict[str, float],
    proposed_action: str,
    base_confidence: float,
) -> dict[str, Any]:
    """Review a proposed action using the critic.

    Args:
        critic: Fitted IQLCritic instance.
        state: Current market state features.
        proposed_action: Action proposed by policy.
        base_confidence: Confidence from calibrated model.

    Returns:
        PolicyCriticReview dict with verdict.
    """
    q_values = critic.predict(state)
    action_idx = ACTIONS.index(proposed_action) if proposed_action in ACTIONS else 2
    q_proposed = q_values.get(proposed_action, 0.0)
    q_no_trade = q_values.get("NO_TRADE", 0.0)

    if not critic._fitted:
        return {
            "critic_version": POLICY_CRITIC_VERSION,
            "q_values": q_values,
            "critic_confidence_adjustment": 1.0,
            "critic_veto_reason": "critic_not_ready",
            "critic_verdict": "ALLOW",
            "is_advisory": True,
        }

    if q_proposed < q_no_trade:
        return {
            "critic_version": POLICY_CRITIC_VERSION,
            "q_values": q_values,
            "critic_confidence_adjustment": 0.5,
            "critic_veto_reason": "critic_no_trade_dominant",
            "critic_verdict": "VETO_TO_NO_TRADE",
            "is_advisory": True,
        }

    if q_proposed < 0:
        return {
            "critic_version": POLICY_CRITIC_VERSION,
            "q_values": q_values,
            "critic_confidence_adjustment": 0.3,
            "critic_veto_reason": "critic_calibrated_lower_bound_negative",
            "critic_verdict": "VETO_TO_NO_TRADE",
            "is_advisory": True,
        }

    return {
        "critic_version": POLICY_CRITIC_VERSION,
        "q_values": q_values,
        "critic_confidence_adjustment": 1.0,
        "critic_veto_reason": "",
        "critic_verdict": "ALLOW",
        "is_advisory": True,
    }
