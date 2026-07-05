"""
V7 Policy Critic — Advisory Offline-RL Component.

Sits between V7 hard gates and the final operational gate. Reviews proposed
actions (LONG/SHORT from hard gates) using a learned value function and returns
a verdict: ALLOW, DOWNWEIGHT_CONFIDENCE, VETO_TO_NO_TRADE, or REQUIRE_REVIEW.

The critic is the LOWEST authority in V7's truth hierarchy
(simulation > realized > contract > runtime > model). It can DOWNGRADE but
never UPGRADE execution — hard-gate failure always wins, and a critic ALLOW
does not grant execution eligibility.

Submodules:
  - replay_buffer:    Build (state, action, reward, next_state) tuples from
                      DecisionEvents for offline RL training.
  - regret:           Compute regret_r using simulation/engine/costs.py.
  - expected_return:  Per-direction expected_R (LONG vs SHORT).
"""

__version__ = "0.1.0"
