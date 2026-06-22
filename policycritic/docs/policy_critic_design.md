# Policy Critic Design

> Status: Docs/Design Only — No implementation exists
> Created: 2026-06-23 (adapted from old repo source material)

## 1. One-Sentence Design Position

> V7 Policy Critic is an **advisory layer** that reviews proposed actions, scores risk, reduces confidence, recommends NO_TRADE veto, and produces shadow-mode audit evidence — it does not open trades, close trades, bypass gates, or hold live veto authority.

## 2. Authority Hierarchy

The V7 authority architecture follows a strict shield pattern: deterministic, verified components sit above any learned component.

```
┌─────────────────────────────────────────────────────────────────┐
│                    V7 AUTHORITY HIERARCHY                        │
│                                                                   │
│  LAYER 1: Runtime Risk Gate                    ← HARD VETO       │
│  ├─ Max daily loss limit                                          │
│  ├─ Max drawdown limit                                            │
│  └─ Circuit breaker                                               │
│                                                                   │
│  LAYER 2: Final Operational Gate               ← HARD VETO       │
│  ├─ Execution eligibility (execution_orchestrator.py)             │
│  ├─ Exchange health, cooldown, exposure limits                    │
│  └─ Kill switches                                                 │
│                                                                   │
│  LAYER 3: V7 Policy Gates                      ← HARD VETO       │
│  ├─ Confidence gate (min_confidence)                               │
│  ├─ Expected-R gate (min_expected_r)                               │
│  ├─ Regime consistency gate                                       │
│  ├─ Degradation/fallback gate                                     │
│  └─ Portfolio + Risk gates                                        │
│                                                                   │
│  LAYER 4: Policy Critic                        ← ADVISORY ONLY    │
│  ├─ Risk score                                                    │
│  ├─ Confidence downweight                                         │
│  ├─ NO_TRADE recommendation                                       │
│  └─ PolicyCriticReview audit record                               │
│                                                                   │
│  LAYER 5: AlphaForge Scorer (planned)           ← PROPOSES        │
│  ├─ LONG alpha score (long_alpha_R)                                │
│  ├─ SHORT alpha score (short_alpha_R)                              │
│  └─ recommended_alpha_action                                      │
│                                                                   │
│  LAYER 6: Execution Layer                        ← EXECUTES       │
│  └─ ExecutionOrchestrator (only gate-cleared actions)             │
└─────────────────────────────────────────────────────────────────┘
```

**Shield principle**: Layers 1-3 are deterministic, rule-based, and verified. Layer 4 may become learned (offline RL) but always sits UNDER the shields. The critic advises; the gate decides.

## 3. Data Flow

### 3.1 Per-Decision Flow (V7-Native Target)

```
SimulationOutput (economic truth)
    │
    ▼
┌──────────────────────┐
│  AlphaForge Scorer   │  proposes: LONG_NOW/SHORT_NOW/NO_TRADE + alpha scores
│  (P5/P6, planned)    │  produces: calibrated_p, expected_R, long_alpha_R, short_alpha_R
└──────┬───────────────┘
       │  alpha_prediction_row
       ▼
┌──────────────────────┐
│  V7 Policy Gates     │  HARD GATE: confidence, expected-R, regime, degradation
│  (v7/docs/pipeline/  │
│   policy.md)         │
└──────┬───────────────┘
       │  gated candidate
       ▼
┌──────────────────────┐
│  Policy Critic       │  ADVISORY: risk score, confidence adjustment, NO_TRADE rec
│  (NOT IMPLEMENTED)   │  Produces PolicyCriticReview (shadow mode only)
└──────┬───────────────┘
       │  annotated decision + review record
       ▼
┌──────────────────────┐
│  Portfolio + Risk    │  Portfolio pressure, risk limits
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Runtime Execution   │  Execution eligibility, operational hard gate
│  Eligibility         │
└──────┬───────────────┘
       │  cleared action
       ▼
┌──────────────────────┐
│  ExecutionOrchestrator│  Executes or routes to paper/simulation
└──────────────────────┘
```

### 3.2 Interim Flow (Today)

The V6 inference engine (sibling repo) is the live decision path today. The V7-native flow (AlphaForge scorer → V7 policy gates → V7 policy critic → execution) is planned but not implemented. For interim critic integration, the adapter path in `runtime/services/analyzer_engine_adapter.py` would bridge V6 AnalysisResult to critic input.

### 3.3 What Happens On Disagreement

If the Policy Critic recommends NO_TRADE but the gates pass:

1. The critic's NO_TRADE recommendation is **recorded** in the PolicyCriticReview
2. The trade proceeds as cleared by the gates (critic is advisory only)
3. The disagreement is surfaced in dashboards as a "critic-gate divergence"
4. After sufficient shadow evidence, divergence patterns inform threshold calibration

If any gate (Layers 1-3) blocks: the action is vetoed regardless of critic recommendation.

## 4. PolicyCriticReview Contract Sketch

This contract does not yet exist. When implemented, it should:
- Follow the 6-step contract registration procedure in `contracts/README.md`
- Be registered in `contracts/registry.json` with `owner_domain: v7`
- Have a JSON schema in `contracts/schemas/`
- Have a compatibility entry in `contracts/compatibility.json`

```python
# Proposed: PolicyCriticReview — DO NOT IMPLEMENT, design sketch only

@dataclass
class PolicyCriticReview:
    """Advisory review produced by Policy Critic — shadow mode only."""

    # Identity
    review_id: str
    decision_event_id: str
    generated_at_utc: str

    # Proposed action (from AlphaForge scorer)
    proposed_action: str          # LONG_NOW / SHORT_NOW / NO_TRADE
    proposed_confidence: float    # 0.0–1.0

    # Critic assessment
    risk_score: float             # 0.0–1.0, higher = riskier
    expected_value_r: float       # Expected return in R-multiples
    value_uncertainty: float      # Standard error of expected_value_r
    confidence_multiplier: float  # 0.0–1.0, applied to model confidence
    recommended_action: str       # LONG_NOW / SHORT_NOW / NO_TRADE (critic's preference)
    veto_recommended: bool        # True if critic recommends NO_TRADE

    # Explanation
    reason_summary: str
    top_risk_factors: list[str]

    # Lineage
    critic_version: str           # e.g. "v7_critic_v1_rule_based"
    critic_mode: str              # SHADOW (always for V1)
    model_artifact_version: str
    calibration_artifact_version: str

    # Evidence
    support_samples: int          # Similar historical cases found
    regime_label: str
    metadata: dict

    # Non-negotiable
    is_advisory: bool = True      # Always True — critic is advisory only
```

**Verdict enum** (advisory only, does not change action enum):
- `ALLOW` — critic agrees with proposed action
- `DOWNWEIGHT_CONFIDENCE` — reduce confidence, re-trip confidence gate
- `VETO_TO_NO_TRADE` — recommend NO_TRADE (policy enacts, not critic)
- `REQUIRE_REVIEW` — IQL/CQL disagreement or reliability concern

## 5. Advisory-Only Design

### 5.1 What "Advisory-Only" Means

The Policy Critic's output is a **recommendation with evidence**, not a decision. It:

- Produces a `PolicyCriticReview` record
- May reduce the confidence value passed to downstream gates
- May recommend NO_TRADE with reasons
- Records disagreement when gates override its recommendation

It does NOT:
- Change the final action enum directly
- Block execution directly
- Override gate decisions
- Have any code path that prevents a gate-cleared action from executing

### 5.2 NO_TRADE Veto Recommendation Semantics

When the critic recommends NO_TRADE:

1. The recommendation is **recorded** with reasons and risk factors
2. Confidence is downweighted by `confidence_multiplier`
3. The action continues through gates (critic cannot veto)
4. If gates also block → normal gate behavior (critic agreed)
5. If gates pass → the trade executes with reduced confidence, and the divergence is tracked

**Key invariant**: The critic's NO_TRADE recommendation is a signal, not a veto. Only Layers 1-3 (Runtime Risk Gate, Final Operational Gate, V7 Policy Gates) can veto.

### 5.3 Why Advisory-Only Is Correct

- **No replay buffer exists**: The critic has no training data
- **No OPE validation exists**: Cannot distinguish skill from luck
- **No shadow evidence exists**: Cannot calibrate critic behavior
- **v7/src/ is greenfield**: No V7-native decision infrastructure
- **Safe RL literature requires shielding**: Learned components must sit under verified components (Alshiekh et al. 2018)

## 6. No Final Authority

The Policy Critic **never** holds final authority. The authority chain is:

```
Runtime Risk Gate > Final Operational Gate > V7 Policy Gates > Policy Critic
```

The critic can be overridden by any gate above it. The critic cannot override any gate above it.

## 7. No Trade Execution Authority

The Policy Critic has **zero** execution authority:

- Cannot call ExecutionOrchestrator
- Cannot create orders
- Cannot modify position sizes (except via confidence downweight → gate size_multiplier)
- Cannot close positions
- Cannot cancel orders
- Cannot trigger emergency actions

Execution authority remains exclusively with:
- `runtime/runtime/scan_runtime.py` — scan and execution orchestration
- `runtime/runtime/execution_orchestrator.py` — operational hard gate
- V7 Policy Gates — sizing and eligibility

## 8. No Runtime Risk Bypass

The Policy Critic cannot:
- Disable or modify daily loss limits
- Disable or modify max drawdown limits
- Disable or modify circuit breakers
- Route around the Final Operational Gate
- Change execution mode (SHADOW/PAPER/TINY_LIVE/LIVE)
- Suppress risk gate violations

Runtime risk gates are **non-bypassable** and sit **above** the critic in the authority hierarchy.

## 9. V1 Implementation Scope (When Authorized)

The first implementation will be a **shadow-only rule-based critic**:

- Applies heuristic risk scoring rules
- Records `PolicyCriticReview` via `ShadowPolicyRepository`
- Always passes through the proposed action
- Zero live influence
- ~200 lines of code
- 1–2 weeks estimated effort

This V1 critic is **not yet authorized for implementation**. Current scope is docs/design only.

## 10. Key Design Invariants

These must be preserved in every version (V1 through V4):

| Invariant | Rationale |
|---|---|
| Critic is advisory only | Safe RL shielding principle (Alshiekh et al. 2018) |
| Gates retain hard veto | Deterministic safety barriers |
| No execution authority | Separation of concerns |
| No gate bypass capability | Defense in depth |
| Shadow mode before any live influence | Evidence-gated progression |
| Every decision recorded with lineage | Audit trail for calibration |
| Confidence intervals on all estimates | Prevent over-trust |
| Human approval for any live authority | Governance requirement |
| No hidden veto | Every critic verdict visible in runtime_interpretation |
| V7 owns final trade decisions | Per CLAUDE.md domain boundaries |

## 11. Related Documents

- [[ai_summary.md]] — Agent context and repo facts
- [[authority_and_boundaries.md]] — Detailed boundary specification
- [[pipeline.md]] — Versioned implementation pipeline
- [[rl_intro_for_v7.md]] — RL concepts for V7
- [[replay_buffer_design.md]] — Prerequisite infrastructure
- [[rollout_plan.md]] — Staged deployment plan
- [[source_inventory.md]] — Research bibliography
- `v7/docs/policy_critic/design.md` — Canonical design (authority for conflicts)

## 12. References

- Alshiekh et al. 2018, "Safe Reinforcement Learning via Shielding", AAAI 2018 — [arXiv:1708.08611](https://arxiv.org/abs/1708.08611)
- Garcia & Fernandez 2015, "A Comprehensive Survey on Safe Reinforcement Learning", JMLR
- Kostrikov et al. 2021, "Offline Reinforcement Learning with Implicit Q-Learning", ICLR 2022 — [arXiv:2110.06169](https://arxiv.org/abs/2110.06169)
- Kumar et al. 2020, "Conservative Q-Learning for Offline Reinforcement Learning", NeurIPS 2020 — [arXiv:2006.04779](https://arxiv.org/abs/2006.04779)
- Levine et al. 2020, "Offline Reinforcement Learning: Tutorial, Review, and Perspectives" — [arXiv:2005.01643](https://arxiv.org/abs/2005.01643)
- `CLAUDE.md` — Domain boundaries and truth hierarchy
- `contracts/registry.json` — Canonical contract registry
- `v7/docs/policy_critic/design.md` — Canonical critic design
