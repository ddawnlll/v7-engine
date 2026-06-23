# Architecture Decision Records — V7 Policy Critic

> Status: Docs/Design Only
> Format: ADR (Context, Decision, Why, Alternatives, Consequences, Review Trigger)

---

## ADR-001: Policy Critic Is Advisory Only

**Context**: V7 needs a component that can assess trade risk beyond what deterministic gates express. The component could be designed as a gate with veto power, or as an advisor that recommends but does not decide.

**Decision**: The Policy Critic is **advisory only**. It produces a PolicyCriticReview with verdict (ALLOW / DOWNWEIGHT_CONFIDENCE / VETO_TO_NO_TRADE / REQUIRE_REVIEW) and `is_advisory=true`. V7 policy gates **enact** the verdict — the critic never directly changes `recommended_action` or controls execution.

**Why**:
1. Safe RL literature (Alshiekh et al. 2018) proves learned components must sit under deterministic shields.
2. The critic will initially be uncalibrated and untested — giving it veto power would be irresponsible.
3. Deterministic gates are verifiable, auditable, and have known failure modes. Learned components do not.
4. Advisory design allows shadow-mode evidence gathering before any influence.

**Alternatives considered**:
- **Critic with hard veto**: Rejected — unsafe for an unproven learned component. Violates shielding principle.
- **Critic as primary decision engine**: Rejected — RL overfits financial data. Trees beat deep RL on tabular data (Grinsztajn et al. 2022).
- **No critic, gates only**: Rejected — gates cannot express regime-conditional risk, multi-factor interactions, or expected value estimation.

**Consequences**:
- Critic outputs are audit records, not execution commands.
- Every verdict is visible in `runtime_interpretation.suppression_reason`.
- Critic can be disabled via config (`POLICY_CRITIC_ACTIVE=false`) without architectural change.
- The system degrades safely: if critic unavailable, gates proceed unchanged.

**Review trigger**: If any stakeholder proposes giving the critic direct veto or execution authority.

---

## ADR-002: RL Is Not the Main Decision Engine

**Context**: Reinforcement learning could theoretically be used as the primary trade decision engine. Some trading systems explore this approach.

**Decision**: RL is used **only for the advisory Policy Critic**, not for the primary decision engine. The primary engine remains AlphaForge's XGBoost supervised scorer with V7 deterministic policy gates.

**Why**:
1. Tree-based models (XGBoost) consistently outperform deep RL on tabular financial data at realistic sample sizes (Grinsztajn et al. 2022).
2. RL agents are prone to backtest overfitting (DSR/PBO), reward hacking, and silent regime-shift failure.
3. Supervised models with deterministic gates are interpretable, auditable, and have known failure boundaries.
4. The advisory critic provides the benefits of RL (context-aware risk, learned value functions) without the risks of RL as primary decision-maker.

**Alternatives considered**:
- **RL as primary engine**: Rejected — unsafe, unproven on financial data, uninterpretable.
- **No RL anywhere**: Rejected — RL provides unique capability for expected value estimation that supervised models alone cannot.

**Consequences**:
- AlphaForge XGBoost remains the primary scorer.
- RL research and training is scoped to the advisory critic only.
- All RL model artifacts are registered separately from scorer artifacts.

**Review trigger**: If empirical evidence emerges that RL consistently outperforms XGBoost on V7's specific data at V7's scale.

---

## ADR-003: Shadow Mode Before Any Live Influence

**Context**: The critic could be deployed with immediate influence on trade decisions, or first deployed in shadow mode (recording verdicts without influencing execution).

**Decision**: The critic operates in **shadow mode only** until all evidence gates are passed. Shadow mode means: critic reviews every decision, records PolicyCriticReview, but has **zero influence on execution**.

**Why**:
1. Without shadow data, critic accuracy cannot be measured. Deploying with influence would be gambling.
2. Shadow mode provides ground-truth comparison: "what would the critic have done vs what actually happened."
3. False veto rate, false allow rate, and true positive veto rate can only be measured in shadow.
4. DSR/PBO/FQE require outcome data that only exists after shadow operation.

**Alternatives considered**:
- **Immediate influence**: Rejected — cannot measure accuracy without shadow data.
- **Paper-only influence**: Rejected — paper execution ≠ live execution; cost models diverge.

**Consequences**:
- Phase 4 (shadow runtime) is mandatory before Phase 5 (guarded influence).
- Shadow burn-in periods: 30 days (V1→V2), 30 days (V2→V3), 60 days (V4→V5), 90 days (live consideration).
- Every transition requires DSR significance + PBO + FQE + human approval.

**Review trigger**: If shadow period durations prove insufficient or excessive based on actual data characteristics.

---

## ADR-004: NO_TRADE Is First-Class Baseline

**Context**: The critic must learn when NOT trading is correct. If the training data only contains LONG_NOW/SHORT_NOW actions, the critic learns "always take some action" — the opposite of what we want.

**Decision**: NO_TRADE is a **first-class action** in the replay buffer with explicit reward semantics: `saved_loss_r` (avoided loss when directional trade would have lost) and `missed_opportunity_r` (foregone gain when directional trade would have won). The simulation engine already computes these via `NoTradeOutcome`.

**Why**:
1. Without NO_TRADE records, the critic cannot learn to recommend NO_TRADE — it would degrade to a pass-through.
2. NO_TRADE has zero cost (no fees, no slippage, no funding) — it is the correct baseline.
3. The simulation engine already evaluates NO_TRADE as a first-class action — the infrastructure exists.

**Alternatives considered**:
- **Implicit NO_TRADE via threshold**: Rejected — a threshold on Q(s,LONG) doesn't capture NO_TRADE's value.
- **NO_TRADE as negative reward for action**: Rejected — NO_TRADE should have its own reward signal, not be a penalty on other actions.

**Consequences**:
- Replay buffer must include NO_TRADE records (≥ 20% of total).
- Critic training must use NO_TRADE's reward components (saved_loss_r, missed_opportunity_r).
- The Q(s, NO_TRADE) value is compared against Q(s, LONG_NOW) and Q(s, SHORT_NOW) for verdict decisions.

**Review trigger**: If NO_TRADE quality metrics (saved_loss_r, missed_opportunity_r) show systematic bias.

---

## ADR-005: Profitability Claims Require Evidence

**Context**: The business case describes potential profitability scenarios. Without guardrails, these scenarios could be misinterpreted as promises.

**Decision**: **No profitability is claimed or guaranteed.** All numbers in `profitability_calculation.md` are explicitly labeled as illustrative scenarios. Actual profitability claims require: ≥ 90 days shadow evidence, DSR p < 0.05, PBO < 0.10, FQE CI overlap, no drawdown worsening, multi-regime validation, and human approval.

**Why**:
1. Backtest profitability is not live profitability (Bailey & Lopez de Prado 2014).
2. Regime shifts can eliminate any learned edge.
3. Costs (fees, slippage, funding) can exceed the critic's alpha.
4. Premature profitability claims undermine credibility with partners and regulators.

**Alternatives considered**:
- **No profitability discussion**: Rejected — stakeholders need to understand potential value to approve investment.
- **Committed ROI projections**: Rejected — dishonest without evidence.

**Consequences**:
- All profitability docs include explicit disclaimers.
- Every scenario table includes "DO NOT BUDGET AGAINST THIS" for aggressive scenarios.
- Business invalidation conditions are documented (7 specific kill criteria).

**Review trigger**: If shadow evidence becomes available and DSR reaches significance.

---

## ADR-006: IQL/CQL Are Future Offline Candidates, Not Immediate Runtime Logic

**Context**: IQL and CQL are recommended for V3 (offline RL critic). They could be misinterpreted as something to implement now.

**Decision**: IQL and CQL are **research recommendations for V3**, not immediate implementation targets. They require: replay buffer ≥ 10,000 tuples, FQE validation, DSR/PBO gates, and V2 supervised critic operating in shadow. V1 is rule-based. V2 is supervised XGBoost. V3 is IQL/CQL.

**Why**:
1. No replay buffer exists — prerequisite for any offline RL.
2. IQL/CQL are untested on financial data (all published results are on D4RL game/simulator tasks).
3. V1 (heuristic) and V2 (supervised) provide necessary baselines and infrastructure before complex RL.
4. Premature RL implementation risks overfitting, wasted engineering, and credibility loss.

**Alternatives considered**:
- **Skip V1-V2, go directly to IQL**: Rejected — no infrastructure, no baseline, no evidence.
- **Skip RL entirely**: Rejected — IQL provides unique OOD-safe value estimation that supervised models cannot.

**Consequences**:
- IQL/CQL research docs clearly state "USE LATER (V3)".
- Phase plans explicitly sequence: V1 → V2 → V3.
- Training infrastructure for IQL is specified but not started.

**Review trigger**: When replay buffer reaches 10,000 tuples and V2 is stable in shadow for 30 days.

---

## ADR-007: XGBoost/GBDT Stays Primary Supervised Baseline

**Context**: The model class for V2 supervised critic and AlphaForge scorer must be chosen. Options include XGBoost, CatBoost, LightGBM, or neural networks.

**Decision**: **XGBoost is the primary model class** for supervised components. This follows the AlphaForge design (`ai_summary__v7_alphaforge_xgb.md`) which specifies XGBoost for the V7-native scorer.

**Why**:
1. Tree-based models outperform deep learning on tabular data at realistic sample sizes (Grinsztajn et al. 2022).
2. XGBoost supports quantile regression (`objective='reg:quantileerror'`) for distributional Q-function.
3. XGBoost supports custom objectives (expectile regression for IQL value function).
4. XGBoost is more sample-efficient, interpretable, and faster to train than neural networks.
5. The AlphaForge design already commits to XGBoost — consistency reduces integration risk.

**Alternatives considered**:
- **CatBoost**: The old trading-bot-pr repo claimed CatBoost as primary. This claim cannot be verified in v7-engine (V6 lives in sibling repo). AlphaForge design specifies XGBoost.
- **Neural networks**: Rejected — sample-inefficient on tabular data at V7's expected scale (10^4-10^6 transitions).
- **LightGBM**: Viable alternative but XGBoost has better quantile regression support.

**Consequences**:
- V2 supervised critic uses XGBoost regressor.
- V3 IQL critic uses XGBoost expectile/quantile regression.
- Model artifacts follow AlphaForge's artifact format.

**Review trigger**: If empirical benchmarks on V7's actual data show another model family significantly outperforming XGBoost.

---

## ADR-008: Funding Remains Deferred Until Explicit Evidence Exists

**Context**: Perpetual futures incur funding rate costs. The simulation engine's cost model currently defers funding (`DEFERRED_FOR_SPOT_OR_NON_PERP_FIRST_PHASE`). The critic could be designed assuming funding will be added later.

**Decision**: **Funding cost remains DEFERRED.** The critic is **spot-only-valid** until funding is implemented in the simulation cost model. Perpetual futures trading is blocked at G3 promotion gate. Critic models trained without funding must be explicitly marked as spot-only and must be retrained when funding is added.

**Why**:
1. Funding cost formula is `LOCK_CANDIDATE` in `cost_model.md` but not implemented in `costs.py`.
2. Training a critic without funding and then applying it to perps would silently overestimate expected returns.
3. The G3 gate already blocks perp promotion until funding is implemented — the critic inherits this constraint.

**Alternatives considered**:
- **Implement funding now**: Rejected — outside docs-only scope; requires simulation engine changes.
- **Ignore funding**: Rejected — would produce misleading expected value estimates for perps.

**Consequences**:
- All docs state "funding DEFERRED — spot-only valid."
- Critic model artifacts must include `funding_included: false` metadata.
- Perp retraining is a documented requirement before G3 promotion.
- Business case acknowledges funding will reduce net expectancy.

**Review trigger**: When funding cost is implemented in `simulation/engine/costs.py`.
