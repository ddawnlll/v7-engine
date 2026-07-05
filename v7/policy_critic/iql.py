"""
Implicit Q-Learning (IQL) offline RL training + OPE/FQE for Policy Critic.

IQLTrainer implements Implicit Q-Learning (Kostrikov et al., 2021) for offline
RL on replay-buffer data. It learns three Q-functions — Q(s, LONG), Q(s, SHORT),
Q(s, NO_TRADE) — via expectile regression using the in-sample actions only,
avoiding distributional shift from out-of-sample actions.

Complementary evaluators:
  - OPEEvaluator:   Off-Policy Evaluation via importance sampling / WIS.
  - FQEEvaluator:   Fitted Q-Evaluation (Le et al., 2019) for model-based OPE.

Flow (Phase 3C, per ai_summary §Staged Rollout):
  ReplayBuffer -> IQLTrainer.train() -> trained Q-networks
                                      -> conformal calibration retrofit
                                      -> IQLTrainer.review() -> PolicyCriticReview

References:
  - Kostrikov et al., "Offline Reinforcement Learning with Implicit Q-Learning", 2021
  - Le et al., "Fitted Q-Evaluation", 2019
  - Precup et al., "Off-Policy Policy Evaluation", 2000 (WIS)
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable

from v7.policy_critic.replay_buffer import (
    CRITIC_ACTION_LONG,
    CRITIC_ACTION_NO_TRADE,
    CRITIC_ACTION_SHORT,
    ReplayTuple,
)

# ---------------------------------------------------------------------------
# Verdict contract (mirrors PolicyCriticReview enum)
# ---------------------------------------------------------------------------

VALID_VERDICTS = {"ALLOW", "DOWNWEIGHT_CONFIDENCE", "VETO_TO_NO_TRADE", "REQUIRE_REVIEW"}

# ---------------------------------------------------------------------------
# Trainable network abstractions
# ---------------------------------------------------------------------------


class QNetwork:
    """Abstract Q-network for IQL training.

    In production this would be an XGBoost quantile regressor ensemble
    (per ai_summary: per-action gradient-boosted quantile/expectile regressor).
    This class provides the interface contract that the IQLTrainer uses,
    with a simple tabular-mock implementation for offline development.
    """

    def __init__(self, quantiles: int = 16):
        self.quantiles = quantiles
        # Internal: maps (state_key, action) -> list of quantile estimates
        self._estimates: dict[tuple[str, str], list[float]] = {}
        self._is_trained = False

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def predict_quantiles(self, state: dict[str, Any], action: str) -> list[float]:
        """Return quantile estimates for Q(s, a).

        Args:
            state:  Feature dict.
            action: LONG, SHORT, or NO_TRADE.

        Returns:
            List of quantile values (length = self.quantiles).
        """
        key = (self._state_key(state), action)
        if key in self._estimates:
            return list(self._estimates[key])
        return [0.0] * self.quantiles

    def get_value(self, state: dict[str, Any], action: str) -> float:
        """Return the mean Q-value across quantiles (point estimate)."""
        qs = self.predict_quantiles(state, action)
        return sum(qs) / len(qs) if qs else 0.0

    def get_lower_quantile(self, state: dict[str, Any], action: str, tau: float = 0.2) -> float:
        """Return the tau-th quantile (used as calibrated lower bound)."""
        qs = sorted(self.predict_quantiles(state, action))
        idx = max(0, min(len(qs) - 1, int(tau * len(qs))))
        return qs[idx]

    def set_estimates(self, state: dict[str, Any], action: str, quantiles: list[float]) -> None:
        """Directly set quantile estimates (used by trainer)."""
        key = (self._state_key(state), action)
        self._estimates[key] = list(quantiles)

    def _state_key(self, state: dict[str, Any]) -> str:
        """Normalise state dict to a hashable key for lookups.

        Uses a small set of deterministic features so that similar states
        with identical features share the same key (tabular mock).
        """
        keys = ("symbol", "mode", "confidence", "decision", "entry_price")
        return "|".join(str(state.get(k, "")) for k in keys)

    def reset(self) -> None:
        """Clear all learned estimates."""
        self._estimates.clear()
        self._is_trained = False


class ValueNetwork:
    """Value network for IQL — approximates V(s) via expectile regression.

    The value network learns the expectile (e.g. tau=0.7-0.8) of the
    in-sample Q-values, acting as the baseline for advantage computation.
    """

    def __init__(self):
        self._estimates: dict[str, float] = {}
        self._is_trained = False

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def predict(self, state: dict[str, Any]) -> float:
        """Return V(s) — the expectile-estimated state value."""
        key = self._state_key(state)
        return self._estimates.get(key, 0.0)

    def set_value(self, state: dict[str, Any], v: float) -> None:
        key = self._state_key(state)
        self._estimates[key] = v

    def reset(self) -> None:
        self._estimates.clear()
        self._is_trained = False

    @staticmethod
    def _state_key(state: dict[str, Any]) -> str:
        keys = ("symbol", "mode", "confidence", "decision", "entry_price")
        return "|".join(str(state.get(k, "")) for k in keys)


class PolicyNetwork:
    """Policy network for IQL — extracts policy from the learned Q-function.

    In IQL, the policy is extracted via advantage-weighted regression (AWR):
      pi(a|s) = softmax(beta * (Q(s,a) - V(s)))
    where beta is the inverse temperature. This class implements the AWR
    policy interface.
    """

    def __init__(self, beta: float = 3.0):
        self.beta = beta
        self._action_probs: dict[str, dict[str, float]] = {}
        self._is_trained = False

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def predict_probs(self, state: dict[str, Any]) -> dict[str, float]:
        """Return action probabilities pi(·|s) over {LONG, SHORT, NO_TRADE}."""
        key = self._state_key(state)
        default = {CRITIC_ACTION_LONG: 0.33, CRITIC_ACTION_SHORT: 0.33, CRITIC_ACTION_NO_TRADE: 0.34}
        return dict(self._action_probs.get(key, default))

    def set_probs(self, state: dict[str, Any], probs: dict[str, float]) -> None:
        key = self._state_key(state)
        self._action_probs[key] = dict(probs)

    def reset(self) -> None:
        self._action_probs.clear()
        self._is_trained = False

    @staticmethod
    def _state_key(state: dict[str, Any]) -> str:
        keys = ("symbol", "mode", "confidence", "decision", "entry_price")
        return "|".join(str(state.get(k, "")) for k in keys)


# ---------------------------------------------------------------------------
# Training result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IQLTrainingResult:
    """Result of running IQLTrainer.train().

    Attributes:
        n_epochs:                Number of training epochs completed.
        n_tuples:                Number of replay tuples used.
        final_bellman_error:     Mean Bellman error on the training set
                                 (lower is better).
        bellman_error_history:   Per-epoch mean Bellman error for convergence
                                 monitoring.
        is_converged:            True if final_bellman_error < convergence_threshold.
        expectile_tau:           The expectile parameter used (0.7-0.8 typical).
        n_quantiles:             Number of quantiles in the distributional Q-head.
        training_mode:           Which mode(s) the trainer targeted.
    """

    n_epochs: int
    n_tuples: int
    final_bellman_error: float
    bellman_error_history: list[float] = field(default_factory=list)
    is_converged: bool = False
    expectile_tau: float = 0.75
    n_quantiles: int = 16
    training_mode: str = "SWING"


# ---------------------------------------------------------------------------
# IQL Trainer
# ---------------------------------------------------------------------------


class IQLTrainer:
    """Implicit Q-Learning (IQL) offline RL trainer for the Policy Critic.

    Trains three Q-functions (LONG, SHORT, NO_TRADE) via expectile regression
    on *in-sample* actions only (never evaluates unseen actions). Uses a
    separate value network V(s) as the expectile target, avoiding the need
    for a target Q-network.

    Training loop per epoch:
      1. Sample batch from replay buffer.
      2. Compute V(s) via expectile regression on Q(s, a_in_sample).
      3. Update Q(s, a_in_sample) toward r + gamma * V(s').
      4. If CQL cross-check enabled, add conservative regularisation.
      5. Log Bellman error and check convergence.
    """

    def __init__(
        self,
        *,
        expectile_tau: float = 0.75,
        gamma: float = 0.99,
        learning_rate_q: float = 0.01,
        learning_rate_v: float = 0.01,
        n_epochs: int = 100,
        batch_size: int = 256,
        convergence_threshold: float = 1e-3,
        cql_regularisation: float = 0.0,
        training_mode: str = "SWING",
    ):
        """Initialise the IQL trainer.

        Args:
            expectile_tau:         Expectile parameter; tau=0.75 means V(s) is
                                   the 75th expectile of Q(s,a). Range (0.5, 1.0).
                                   Higher = more pessimistic.
            gamma:                 Discount factor (0.99 for short-horizon trading).
            learning_rate_q:       Learning rate for Q-network updates.
            learning_rate_v:       Learning rate for V-network updates.
            n_epochs:              Maximum number of training epochs.
            batch_size:            Minibatch size per epoch.
            convergence_threshold: Stop when mean Bellman error < this value.
            cql_regularisation:    CQL penalty weight (0.0 = no CQL). When >0,
                                   IQL/CQL cross-check is active.
            training_mode:         Which mode to train for (SWING, SCALP, etc.).
        """
        if not 0.5 < expectile_tau < 1.0:
            raise ValueError(
                f"expectile_tau must be in (0.5, 1.0), got {expectile_tau}"
            )
        if not 0 < gamma < 1:
            raise ValueError(f"gamma must be in (0, 1), got {gamma}")
        if cql_regularisation < 0:
            raise ValueError(
                f"cql_regularisation must be >= 0, got {cql_regularisation}"
            )

        self.expectile_tau = expectile_tau
        self.gamma = gamma
        self.lr_q = learning_rate_q
        self.lr_v = learning_rate_v
        self.n_epochs = n_epochs
        self.batch_size = batch_size
        self.convergence_threshold = convergence_threshold
        self.cql_reg = cql_regularisation
        self.training_mode = training_mode

    def train(
        self,
        replay_buffer: list[ReplayTuple],
        q_network: QNetwork | None = None,
        value_network: ValueNetwork | None = None,
        policy_network: PolicyNetwork | None = None,
    ) -> IQLTrainingResult:
        """Run IQL training on the given replay tuples.

        Args:
            replay_buffer:  List of ReplayTuple transitions.
            q_network:      Q-network instance (created fresh if None).
            value_network:  Value-network instance (created fresh if None).
            policy_network: Policy-network instance (created fresh if None).

        Returns:
            IQLTrainingResult with convergence info and error history.
        """
        q = q_network if q_network is not None else QNetwork(quantiles=16)
        v = value_network if value_network is not None else ValueNetwork()
        pi = policy_network if policy_network is not None else PolicyNetwork()

        # Filter to training mode if any
        tuples = [
            t for t in replay_buffer
            if not self.training_mode or t.mode == self.training_mode
        ]
        if not tuples:
            return IQLTrainingResult(
                n_epochs=0,
                n_tuples=0,
                final_bellman_error=0.0,
                is_converged=False,
                expectile_tau=self.expectile_tau,
                training_mode=self.training_mode,
            )

        bellman_history: list[float] = []
        n_tuples = len(tuples)

        for epoch in range(1, self.n_epochs + 1):
            # Sample batch (deterministic: use epoch-based slice for reproducibility)
            batch = self._sample_batch(tuples, epoch)
            bellman_err = self._train_step(batch, q, v)

            bellman_history.append(bellman_err)

            # Early convergence check
            if bellman_err < self.convergence_threshold:
                break

        # Mark networks as trained
        q._is_trained = True
        v._is_trained = True
        pi._is_trained = True

        # Compute final error over all tuples
        final_err = self._compute_mean_bellman_error(tuples, q, v)

        # Build policy from Q-values via AWR
        self._extract_policy(pi, tuples, q, v)

        return IQLTrainingResult(
            n_epochs=len(bellman_history),
            n_tuples=n_tuples,
            final_bellman_error=round(final_err, 8),
            bellman_error_history=[round(e, 8) for e in bellman_history],
            is_converged=final_err < self.convergence_threshold,
            expectile_tau=self.expectile_tau,
            n_quantiles=q.quantiles,
            training_mode=self.training_mode,
        )

    def review(
        self,
        q_network: QNetwork,
        value_network: ValueNetwork,
        state: dict[str, Any],
        proposed_action: str = CRITIC_ACTION_LONG,
    ) -> dict[str, Any]:
        """Produce a critic review verdict for a single decision point.

        This is the inference entry point — called by ShadowCriticRunner
        after training.

        Args:
            q_network:       Trained Q-network.
            value_network:   Trained value-network.
            state:           Canonical feature vector at decision time.
            proposed_action: The action proposed by hard gates (LONG/SHORT).

        Returns:
            Dict matching PolicyCriticReview contract shape:
              - critic_value_LONG (float)
              - critic_value_SHORT (float)
              - critic_value_NO_TRADE (float)
              - critic_verdict (str)
              - critic_confidence_adjustment (float, 0-1)
              - critic_veto_reason (str)
              - is_advisory (bool, always True)
              - conformal_p_value (float)
              - regret_r (float)
              - expected_R (float)
        """
        q_long = q_network.get_value(state, CRITIC_ACTION_LONG)
        q_short = q_network.get_value(state, CRITIC_ACTION_SHORT)
        q_no_trade = q_network.get_value(state, CRITIC_ACTION_NO_TRADE)

        q_lower_long = q_network.get_lower_quantile(state, CRITIC_ACTION_LONG, tau=0.2)
        v_s = value_network.predict(state)

        # Determine verdict
        proposed_value = (
            q_long if proposed_action == CRITIC_ACTION_LONG
            else q_short if proposed_action == CRITIC_ACTION_SHORT
            else q_no_trade
        )
        proposed_lower = (
            q_lower_long if proposed_action == CRITIC_ACTION_LONG
            else q_network.get_lower_quantile(state, CRITIC_ACTION_SHORT, tau=0.2)
            if proposed_action == CRITIC_ACTION_SHORT
            else q_network.get_lower_quantile(state, CRITIC_ACTION_NO_TRADE, tau=0.2)
        )

        verdict = "ALLOW"
        adjustment = 1.0
        veto_reason = ""

        if proposed_lower <= 0 and proposed_action != CRITIC_ACTION_NO_TRADE:
            verdict = "VETO_TO_NO_TRADE"
            veto_reason = "critic_calibrated_lower_bound_negative"
            adjustment = 0.0
        elif proposed_value < q_no_trade:
            # NO_TRADE dominates
            if q_no_trade > proposed_value + 0.1:
                verdict = "VETO_TO_NO_TRADE"
                veto_reason = "critic_no_trade_dominant"
                adjustment = 0.0
            else:
                verdict = "DOWNWEIGHT_CONFIDENCE"
                veto_reason = "critic_no_trade_slightly_better"
                adjustment = max(0.2, 1.0 - (q_no_trade - proposed_value))
        elif proposed_value < 0.2:
            # Positive but very low expected value
            verdict = "DOWNWEIGHT_CONFIDENCE"
            veto_reason = "critic_low_expected_value"
            adjustment = max(0.3, proposed_value * 2.0)

        # Conformal p-value: approximated as the fraction of training quantiles
        # below zero. In production, this comes from a separate conformal
        # calibration retrofit (ai_summary §Calibration).
        qs_long = sorted(q_network.predict_quantiles(state, CRITIC_ACTION_LONG))
        n_below = sum(1 for qv in qs_long if qv <= 0)
        p_value = n_below / len(qs_long) if qs_long else 0.5

        # Regret_r approximation: max(Q_best - Q_chosen, 0)
        best_q = max(q_long, q_short, q_no_trade)
        regret_r = max(0.0, best_q - proposed_value)

        # Expected_R: use the proposed action's Q-value as point estimate
        expected_r = proposed_value

        return {
            "critic_value_LONG": round(q_long, 6),
            "critic_value_SHORT": round(q_short, 6),
            "critic_value_NO_TRADE": round(q_no_trade, 6),
            "critic_verdict": verdict,
            "critic_confidence_adjustment": round(adjustment, 4),
            "critic_veto_reason": veto_reason,
            "is_advisory": True,
            "conformal_p_value": round(p_value, 4),
            "regret_r": round(regret_r, 6),
            "expected_R": round(expected_r, 6),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sample_batch(self, tuples: list[ReplayTuple], epoch: int) -> list[ReplayTuple]:
        """Deterministic epoch-based batch sampling."""
        n = len(tuples)
        bs = min(self.batch_size, n)
        start = ((epoch - 1) * bs) % n
        end = start + bs
        if end <= n:
            return tuples[start:end]
        return tuples[start:] + tuples[: end - n]

    def _train_step(
        self,
        batch: list[ReplayTuple],
        q_network: QNetwork,
        value_network: ValueNetwork,
    ) -> float:
        """Execute one training step: update V, then Q.

        IQL update equations (simplified tabular):
          V(s) <- expectile_tau of { Q(s, a_i) for a_i in batch actions }
          Q(s,a) <- (1 - lr) * Q(s,a) + lr * (r + gamma * V(s'))
        """
        # Group batch by state for V-update
        state_qs: dict[str, list[float]] = {}
        for t in batch:
            sk = value_network._state_key(t.state)
            state_qs.setdefault(sk, []).append(
                q_network.get_value(t.state, t.action)
            )

        # V-update: set V(s) to the expectile of in-sample Q-values
        for sk, qs in state_qs.items():
            if len(qs) >= 3:
                v = self._expectile(qs, self.expectile_tau)
            else:
                v = sum(qs) / len(qs) if qs else 0.0
            # Store back via a representative state
            rep = next(t for t in batch if value_network._state_key(t.state) == sk)
            existing = value_network.predict(rep.state)
            updated = existing + self.lr_v * (v - existing)
            value_network.set_value(rep.state, updated)

        # Q-update: Bellman target = r + gamma * V(s')
        errors: list[float] = []
        for t in batch:
            current_q = q_network.get_value(t.state, t.action)
            next_v = value_network.predict(t.next_state) if t.next_state else 0.0
            target = t.reward + self.gamma * next_v * (0.0 if t.terminal else 1.0)
            error = abs(target - current_q)

            # Update quantiles
            qs = q_network.predict_quantiles(t.state, t.action)
            updated_qs = [qv + self.lr_q * (target - qv) for qv in qs]

            # CQL regularisation: penalise Q-values on out-of-sample actions
            if self.cql_reg > 0:
                for action_other in (CRITIC_ACTION_LONG, CRITIC_ACTION_SHORT, CRITIC_ACTION_NO_TRADE):
                    if action_other != t.action:
                        q_other = q_network.get_value(t.state, action_other)
                        updated_qs = [qv - self.cql_reg * q_other for qv in updated_qs]

            q_network.set_estimates(t.state, t.action, updated_qs)
            errors.append(error)

        return sum(errors) / len(errors) if errors else 0.0

    def _compute_mean_bellman_error(
        self,
        tuples: list[ReplayTuple],
        q_network: QNetwork,
        value_network: ValueNetwork,
    ) -> float:
        """Compute mean Bellman error over all tuples."""
        if not tuples:
            return 0.0
        errors: list[float] = []
        for t in tuples:
            current_q = q_network.get_value(t.state, t.action)
            next_v = value_network.predict(t.next_state) if t.next_state else 0.0
            target = t.reward + self.gamma * next_v * (0.0 if t.terminal else 1.0)
            errors.append(abs(target - current_q))
        return sum(errors) / len(errors)

    def _extract_policy(
        self,
        policy_network: PolicyNetwork,
        tuples: list[ReplayTuple],
        q_network: QNetwork,
        value_network: ValueNetwork,
    ) -> None:
        """Extract policy via advantage-weighted regression (AWR)."""
        state_advantages: dict[str, dict[str, float]] = {}
        for t in tuples:
            sk = policy_network._state_key(t.state)
            if sk not in state_advantages:
                v_s = value_network.predict(t.state)
                advantages = {}
                for act in (CRITIC_ACTION_LONG, CRITIC_ACTION_SHORT, CRITIC_ACTION_NO_TRADE):
                    q = q_network.get_value(t.state, act)
                    advantages[act] = q - v_s
                state_advantages[sk] = advantages

        for sk, advs in state_advantages.items():
            # Softmax over advantages with temperature beta
            exp_adv = {a: math.exp(policy_network.beta * adv) for a, adv in advs.items()}
            total = sum(exp_adv.values()) or 1.0
            probs = {a: v / total for a, v in exp_adv.items()}
            rep = next(t for t in tuples if policy_network._state_key(t.state) == sk)
            policy_network.set_probs(rep.state, probs)

    @staticmethod
    def _expectile(values: list[float], tau: float) -> float:
        """Compute the tau-th expectile of a list of values.

        The expectile is an asymmetric least-squares generalisation of the
        quantile: it minimises E[|tau - I(v < mu)| * (v - mu)^2].
        """
        if not values:
            return 0.0
        sorted_v = sorted(values)
        n = len(sorted_v)

        # Weighted mean: each point gets weight tau if above mean, (1-tau) if below
        # Iterative solution (converges quickly for small n)
        mu = statistics.mean(sorted_v)
        for _ in range(50):
            weights = [tau if v >= mu else (1.0 - tau) for v in sorted_v]
            total_w = sum(weights)
            if total_w == 0:
                break
            new_mu = sum(w * v for w, v in zip(weights, sorted_v)) / total_w
            if abs(new_mu - mu) < 1e-8:
                break
            mu = new_mu
        return mu


# ---------------------------------------------------------------------------
# OPE Evaluator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OPEVerdict:
    """Result of off-policy evaluation.

    Attributes:
        wis_estimate:      Weighted Importance Sampling estimate of policy value.
        cis_lower:         Lower bound of 95% confidence interval.
        cis_upper:         Upper bound of 95% confidence interval.
        effective_sample:  Effective sample size (ESS) ratio.
        is_reliable:       True if ESS ratio > 0.1 and CI does not contain 0.
        n_trajectories:    Number of trajectories evaluated.
    """
    wis_estimate: float
    cis_lower: float
    cis_upper: float
    effective_sample: float
    is_reliable: bool
    n_trajectories: int


class OPEEvaluator:
    """Off-Policy Evaluation via Weighted Importance Sampling (WIS).

    Estimates the expected return of a target policy pi_e using data
    collected from a behaviour policy pi_b. Uses per-decision WIS to
    reduce variance vs ordinary IS.

    Flow:
      1. For each trajectory, compute importance weights w = prod pi_e/pi_b.
      2. Weight observed returns by normalised importance weights (WIS).
      3. Estimate 95% CI via bootstrap or normal approximation.
      4. Report effective sample size ratio.
    """

    def __init__(self, n_bootstrap: int = 1000):
        """Initialise the OPE evaluator.

        Args:
            n_bootstrap: Number of bootstrap samples for CI estimation.
        """
        self.n_bootstrap = n_bootstrap

    def evaluate(
        self,
        trajectories: list[list[ReplayTuple]],
        target_action_probs: Callable[[dict[str, Any]], dict[str, float]],
        behaviour_action_probs: Callable[[dict[str, Any]], dict[str, float]] | None = None,
    ) -> OPEVerdict:
        """Run WIS off-policy evaluation.

        Args:
            trajectories:       List of trajectories, each a list of ReplayTuple.
            target_action_probs:  Function mapping state -> {action: prob} for
                                the target policy.
            behaviour_action_probs: Function mapping state -> {action: prob} for
                                  the behaviour policy. If None, uniform behaviour
                                  is assumed (equal-probability action selection).

        Returns:
            OPEVerdict with WIS estimate and reliability indicators.
        """
        if not trajectories:
            return OPEVerdict(
                wis_estimate=0.0,
                cis_lower=0.0,
                cis_upper=0.0,
                effective_sample=0.0,
                is_reliable=False,
                n_trajectories=0,
            )

        trajectory_values: list[float] = []
        importance_ratios: list[float] = []

        for episode in trajectories:
            if not episode:
                continue

            episode_return = sum(t.reward for t in episode)
            wis_ratio = 1.0

            for t in episode:
                pi_e = target_action_probs(t.state)
                pi_b = (
                    behaviour_action_probs(t.state)
                    if behaviour_action_probs is not None
                    else {CRITIC_ACTION_LONG: 1 / 3, CRITIC_ACTION_SHORT: 1 / 3, CRITIC_ACTION_NO_TRADE: 1 / 3}
                )

                p_e = pi_e.get(t.action, 0.0)
                p_b = pi_b.get(t.action, 1 / 3)
                wis_ratio *= (p_e / p_b) if p_b > 0 else 1.0

            trajectory_values.append(episode_return)
            importance_ratios.append(wis_ratio)

        if not trajectory_values:
            return OPEVerdict(
                wis_estimate=0.0, cis_lower=0.0, cis_upper=0.0,
                effective_sample=0.0, is_reliable=False, n_trajectories=0,
            )

        # Normalise importance weights (WIS)
        total_w = sum(importance_ratios)
        if total_w == 0:
            wis_estimate = sum(trajectory_values) / len(trajectory_values)
        else:
            wis_estimate = sum(
                w * v for w, v in zip(importance_ratios, trajectory_values)
            ) / total_w

        # Effective sample size (ESS) ratio
        n = len(importance_ratios)
        if n > 0 and total_w > 0:
            w_sq = sum(w ** 2 for w in importance_ratios)
            ess_ratio = (total_w ** 2 / w_sq) / n if w_sq > 0 else 0.0
        else:
            ess_ratio = 0.0

        # Bootstrap CI
        boot_estimates: list[float] = []
        for _ in range(self.n_bootstrap):
            idxs = [int(random_idxs()) for _ in range(n)]
            boot_weights = [importance_ratios[i] for i in idxs]
            boot_values = [trajectory_values[i] for i in idxs]
            bw_sum = sum(boot_weights)
            if bw_sum > 0:
                boot_est = sum(w * v for w, v in zip(boot_weights, boot_values)) / bw_sum
                boot_estimates.append(boot_est)

        if len(boot_estimates) >= 20:
            sorted_be = sorted(boot_estimates)
            lower = sorted_be[int(0.025 * len(sorted_be))]
            upper = sorted_be[int(0.975 * len(sorted_be))]
        else:
            lower = wis_estimate - 0.1
            upper = wis_estimate + 0.1

        is_reliable = ess_ratio > 0.1 and not (lower <= 0 <= upper)

        return OPEVerdict(
            wis_estimate=round(wis_estimate, 6),
            cis_lower=round(lower, 6),
            cis_upper=round(upper, 6),
            effective_sample=round(ess_ratio, 4),
            is_reliable=is_reliable,
            n_trajectories=n,
        )


# ---------------------------------------------------------------------------
# FQE Evaluator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FQEJuryVerdict:
    """Result of FQE evaluation against a known Q-estimate.

    Attributes:
        estimated_q:      Q-value estimated by FQE.
        target_q:         Target Q-value being evaluated against.
        fqe_error:        Absolute difference |estimated_q - target_q|.
        is_calibrated:    True if fqe_error < uncertainty_threshold.
        uncertainty_margin: The threshold used for calibration check.
        n_steps:          Number of FQE steps taken.
        fqe_errors:       Per-step error progression.
    """
    estimated_q: float
    target_q: float
    fqe_error: float
    is_calibrated: bool
    uncertainty_margin: float
    n_steps: int
    fqe_errors: list[float] = field(default_factory=list)


class FQEEvaluator:
    """Fitted Q-Evaluation (Le et al., 2019).

    FQE estimates the Q-function of a target policy pi_e by iteratively
    applying the Bellman operator to a Q-function approximator, using
    transitions from the replay buffer collected under pi_b.

    Unlike IQL's in-sample learning, FQE evaluates a *fixed* policy by
    bootstrapping from its own Q-estimates:

      Q_{k+1}(s, a) <- r + gamma * E_{a'~pi_e}[Q_k(s', a')]

    Convergence: FQE converges to Q^{pi_e} under standard conditions
    (contraction mapping). The per-step error trajectory indicates
    convergence quality.

    Use case: After IQL training, use FQE to independently verify the
    learned Q-values and detect overestimation or underestimation bias.
    """

    def __init__(
        self,
        *,
        gamma: float = 0.99,
        n_steps: int = 50,
        step_size: float = 0.05,
        uncertainty_margin: float = 0.1,
    ):
        """Initialise the FQE evaluator.

        Args:
            gamma:               Discount factor (must match trainer's gamma).
            n_steps:             Maximum number of FQE iterations.
            step_size:           Learning rate for Q-updates per FQE step.
            uncertainty_margin:  Threshold below which FQE error is considered
                                 acceptable.
        """
        if not 0 < gamma < 1:
            raise ValueError(f"gamma must be in (0, 1), got {gamma}")
        self.gamma = gamma
        self.n_steps = n_steps
        self.step_size = step_size
        self.uncertainty_margin = uncertainty_margin

    def evaluate(
        self,
        tuples: list[ReplayTuple],
        target_policy_probs: Callable[[dict[str, Any]], dict[str, float]],
        reference_q: QNetwork,
    ) -> FQEJuryVerdict:
        """Run FQE and compare to a reference Q-network.

        Args:
            tuples:               Replay tuples (state, action, reward, next_state).
            target_policy_probs:  Function mapping state -> {action: prob} for the
                                  policy being evaluated.
            reference_q:          Reference Q-network (e.g. from IQLTrainer) to
                                  compare against.

        Returns:
            FQEJuryVerdict with estimated Q-value, error, and calibration flag.
        """
        # Initialise a fresh Q-network for FQE estimation
        fqe_q = QNetwork(quantiles=16)

        # Use reference Q values as initialisation
        for t in tuples:
            ref_qs = reference_q.predict_quantiles(t.state, t.action)
            fqe_q.set_estimates(t.state, t.action, ref_qs)

        step_errors: list[float] = []

        for step in range(self.n_steps):
            total_err = 0.0
            count = 0

            for t in tuples:
                # Current FQE estimate
                current_q = fqe_q.get_value(t.state, t.action)

                # Bootstrapped target: E_{a'~pi_e}[Q(s', a')]
                if t.next_state:
                    pi_e = target_policy_probs(t.state)
                    next_q = 0.0
                    for action, prob in pi_e.items():
                        next_q += prob * fqe_q.get_value(t.next_state, action)
                else:
                    next_q = 0.0

                bellman_target = t.reward + self.gamma * next_q * (0.0 if t.terminal else 1.0)
                td_error = bellman_target - current_q
                total_err += abs(td_error)

                # Update FQE estimate
                qs = fqe_q.predict_quantiles(t.state, t.action)
                updated_qs = [qv + self.step_size * td_error for qv in qs]
                fqe_q.set_estimates(t.state, t.action, updated_qs)
                count += 1

            mean_err = total_err / count if count > 0 else 0.0
            step_errors.append(mean_err)

        # Compute final estimated Q vs reference Q across all tuples
        if tuples:
            estimated_q = sum(fqe_q.get_value(t.state, t.action) for t in tuples) / len(tuples)
            target_q = sum(reference_q.get_value(t.state, t.action) for t in tuples) / len(tuples)
        else:
            estimated_q = 0.0
            target_q = 0.0

        error = abs(estimated_q - target_q)

        return FQEJuryVerdict(
            estimated_q=round(estimated_q, 6),
            target_q=round(target_q, 6),
            fqe_error=round(error, 6),
            is_calibrated=error < self.uncertainty_margin,
            uncertainty_margin=self.uncertainty_margin,
            n_steps=len(step_errors),
            fqe_errors=[round(e, 8) for e in step_errors],
        )


# ---------------------------------------------------------------------------
# Conformal calibration helper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConformalCalibration:
    """Conformal prediction calibration result.

    Attributes:
        coverage:            Empirical coverage of the prediction sets.
        nominal_coverage:    Target coverage (e.g. 0.9).
        adjusted_threshold:  Adjusted quantile threshold to achieve nominal
                             coverage on held-out data.
        n_calib_points:      Number of calibration points used.
    """
    coverage: float
    nominal_coverage: float
    adjusted_threshold: float
    n_calib_points: int


def calibrate_conformal(
    q_network: QNetwork,
    calibration_tuples: list[ReplayTuple],
    *,
    nominal_coverage: float = 0.9,
) -> ConformalCalibration:
    """Retrofit conformal calibration on held-out replay tuples.

    Computes the nonconformity score |r - Q(s,a)| for each calibration
    point and finds the threshold that achieves nominal coverage.

    Args:
        q_network:           Trained Q-network.
        calibration_tuples:  Held-out ReplayTuples for calibration.
        nominal_coverage:    Target coverage rate (default 0.9).

    Returns:
        ConformalCalibration with adjusted threshold and empirical coverage.
    """
    if not calibration_tuples:
        return ConformalCalibration(
            coverage=0.0,
            nominal_coverage=nominal_coverage,
            adjusted_threshold=0.0,
            n_calib_points=0,
        )

    scores: list[float] = []
    for t in calibration_tuples:
        q_val = q_network.get_value(t.state, t.action)
        scores.append(abs(t.reward - q_val))

    scores.sort()
    n = len(scores)
    q_idx = min(n - 1, int(nominal_coverage * n))
    threshold = scores[q_idx]

    # Empirical coverage on calibration set
    covered = sum(1 for s in scores if s <= threshold)
    coverage = covered / n if n > 0 else 0.0

    return ConformalCalibration(
        coverage=round(coverage, 4),
        nominal_coverage=nominal_coverage,
        adjusted_threshold=round(threshold, 6),
        n_calib_points=n,
    )


# Inline helper to avoid import complexity
def random_idxs() -> int:
    """Return a non-negative integer for bootstrap indexing."""
    import os
    return int.from_bytes(os.urandom(4), "big") % (10 ** 6)
