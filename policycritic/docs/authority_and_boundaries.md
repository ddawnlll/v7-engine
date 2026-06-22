# Authority and Boundaries

> Status: Docs/Design Only — Defines the authority model for the Policy Critic
> Created: 2026-06-23 (adapted from old repo source material)

## 1. Fundamental Principle

> The Policy Critic produces **reviews**, not **decisions**. It advises, it does not command.

All trade execution authority resides in deterministic, verified components that sit above the Policy Critic in the authority hierarchy. The critic can recommend, annotate, and downweight — but it can never veto, execute, or bypass.

---

## 2. The Veto Chain

### 2.1 Authority Hierarchy (Top = Supreme Veto)

```
┌──────────────────────────────────────────────────────────────────┐
│  LEVEL 1: Runtime Risk Gate                           ← SUPREME  │
│  Authority: VETO ALL BELOW                                        │
│  Rules: max_daily_loss, max_drawdown, circuit_breaker             │
│  Cannot be bypassed by: anyone                                    │
│  Override mechanism: none (hard coded)                            │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  LEVEL 2: Final Operational Gate                      ← VETO    │
│  Authority: VETO Policy Critic, AlphaForge Scorer                │
│  Rules: execution eligibility, exchange health, cooldown,        │
│         exposure limits, kill switches                            │
│  Cannot be bypassed by: Policy Critic, AlphaForge Scorer         │
│  Override mechanism: operator with audit trail                    │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  LEVEL 3: V7 Policy Gates                            ← VETO    │
│  Authority: VETO Policy Critic, modify alpha scores              │
│  Rules: confidence gate, expected-R gate, regime consistency,    │
│         degradation/fallback, portfolio pressure, risk limits     │
│  Cannot be bypassed by: Policy Critic                             │
│  Override mechanism: config change with audit trail               │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  LEVEL 4: Policy Critic (FUTURE)                     ← ADVISORY  │
│  Authority: RECOMMEND, ANNOTATE, DOWNWEIGHT                       │
│  Can: score risk, reduce confidence, recommend NO_TRADE           │
│  Cannot: veto, execute, bypass gates, change action enum         │
│  Override: any gate above it can ignore its recommendation       │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  LEVEL 5: AlphaForge Scorer (planned)                ← PROPOSE  │
│  Authority: PROPOSE action (LONG_NOW/SHORT_NOW/NO_TRADE)         │
│  Output consumed by: V7 policy gates                              │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  LEVEL 6: Execution Layer                             ← EXECUTE  │
│  Authority: EXECUTE gate-cleared actions only                     │
│  Only executes: actions that passed all gates above               │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Truth Hierarchy (from CLAUDE.md)

```
simulation > realized > contract > runtime > model
```

The Policy Critic is at the **lowest** level (model). It consumes simulation truth (`realized_r_net` from `simulation/engine/engine.py`) and runtime contract signals; it does not produce economic truth.

---

## 3. What The Critic Can Do (By Version)

| Capability | V1 | V2 | V3 | V4 |
|---|---|---|---|---|
| Review proposed actions | ✅ Shadow | ✅ Shadow | ✅ Shadow | ✅ Propose |
| Score action risk (heuristic) | ✅ | ✅ | ✅ | ✅ |
| Score action risk (supervised model) | — | ✅ | ✅ | ✅ |
| Score action risk (offline RL) | — | — | ✅ | ✅ |
| Reduce confidence on high risk | ✅ | ✅ | ✅ | ✅ |
| Recommend NO_TRADE veto | ✅ | ✅ | ✅ | ✅ |
| Record PolicyCriticReview | ✅ | ✅ | ✅ | ✅ |
| Propose sizing adjustments | — | — | — | ✅ Advisory |
| Propose exit timing | — | — | — | ✅ Advisory |

---

## 4. What The Critic Can NEVER Do (Any Version)

| Prohibition | Rationale | Enforced By |
|---|---|---|
| **Open trades** | Execution authority separation | ExecutionOrchestrator |
| **Close trades** | Outcome resolution separation | TradeOutcome lifecycle |
| **Make final decisions** | Advisory-only design | Gate hierarchy |
| **Bypass hard gates** | Shield principle | V7 policy gates |
| **Bypass runtime risk gates** | Defense in depth | Runtime Risk Gate |
| **Create new action enums** | Contract stability | Action space locked to LONG_NOW/SHORT_NOW/NO_TRADE |
| **Bypass cost/funding holds** | Cost integrity | Simulation cost model |
| **Amplify position sizes** | Risk control | Gate size_multiplier ceiling |
| **Change execution mode** | Mode routing integrity | Per-mode readiness states |
| **Hold live veto authority** | Advisory-only | Mode router + human approval gate |
| **Suppress gate violations** | Audit trail integrity | Event recorder |
| **Self-promote to higher authority** | Anti-regression | Human approval gate |
| **Bypass simulation economic truth** | Truth hierarchy | `simulation/engine/engine.py` |

---

## 5. Execution Modes and Authority

### 5.1 Per-Mode Readiness States (from `v7/docs/runtime/runtime_integration.md`)

Each mode (SWING, SCALP, AGGRESSIVE_SCALP) has an independent one-way readiness state:

```
DESIGN_LOCKED → RESEARCH → BACKTEST_ELIGIBLE → SHADOW_ELIGIBLE
→ PAPER_ELIGIBLE → TINY_LIVE_ELIGIBLE → LIVE_ELIGIBLE
```

DISABLED is enterable from any state on kill-switch.

### 5.2 Mode Authority Matrix

| Mode | AlphaForge Scorer | V7 Policy Gates | Policy Critic | Execution |
|---|---|---|---|---|
| **SHADOW** | Proposes | Evaluates | Records (future) | None |
| **PAPER** | Proposes | Gates + sizing | Records (future) | Paper fill |
| **TINY_LIVE** | Proposes | Gates + sizing | Records (future) | Live (tiny) |
| **LIVE** | Proposes | Gates + sizing | **Advisory only** | Live |

### 5.3 SWING Mode — First Live Veto Candidate

SWING mode **may** be the first candidate for live critic veto consideration, but only:
- After replay buffer ≥ 10,000 resolved outcomes
- After PBO < 0.10 and DSR p < 0.05
- After ≥ 90 days of stable shadow operation
- After multi-regime walk-forward validation
- After human approval

**Current status**: SWING live veto is NOT enabled. No timeline committed. This is `LOCKED_INITIAL_BASELINE` per the canonical design.

---

## 6. Simulation Truth Hierarchy

When the Policy Critic operates in simulation (backtest/replay) mode:

### 6.1 Sources of Truth (in order of authority)

1. **Actual market outcomes** (what really happened) ← GROUND TRUTH
2. **Simulation engine output** (`simulation/engine/engine.py`) ← AUTHORITATIVE ECONOMIC TRUTH
3. **Critic evaluation** (what the critic predicted) ← ADVISORY ESTIMATE
4. **Critic confidence** (how sure the critic was) ← META-ESTIMATE

### 6.2 Disagreement Resolution

When critic prediction ≠ simulated outcome:
1. The **outcome is truth** — critic was wrong
2. Disagreement is recorded for calibration analysis
3. Systematic disagreement triggers recalibration review
4. Critic confidence intervals are widened

When critic prediction ≠ gate decision:
1. The **gate decision stands** — critic is advisory
2. Disagreement is recorded as critic-gate divergence
3. Patterns inform future threshold calibration

### 6.3 Critical Boundary: Two Simulation Paths

The v7-engine has two simulation paths that **diverge**:

| Path | Location | Status |
|---|---|---|
| `/simulation` engine | `simulation/engine/engine.py` | AUTHORITATIVE economic truth |
| Runtime historical engine | `runtime/services/historical_simulation_engine.py` | Separate backtest harness, own fee/slippage |

**Rule**: The critic MUST train on `/simulation` engine output, not the runtime historical engine. The runtime engine applies its own fee/slippage settlement and does NOT produce ActionOutcome/NoTradeOutcome/PathMetrics.

---

## 7. Governance

### 7.1 Version Transition Authority

| Transition | Required Approvals |
|---|---|
| V1 shadow critic → active recording | ACCP acceptance + code review |
| V2 supervised critic → shadow mode | DSR/PBO pass + walk-forward pass + code review |
| V3 IQL critic → shadow mode | FQE pass + DSR/PBO pass + code review + architecture review |
| V4 optimizer → shadow proposals | Formal shield verification + adversarial simulation + architecture review |
| ANY version → live influence | All gates above + human approval |

### 7.2 Emergency Override

In emergency scenarios (flash crash, exchange halt, circuit breaker trigger):
- Runtime Risk Gate has **supreme authority** and can halt all trading
- Policy Critic recommendations are **ignored** during emergencies
- No learned component can override emergency halts

### 7.3 Audit Requirements

Every Policy Critic decision must be recorded with:
- Full PolicyCriticReview payload
- Critic version and mode
- All input features
- Risk score decomposition (which factors contributed)
- Confidence interval
- Disagreement flag (if gates overrode)
- Lineage (model_artifact_version, calibration_artifact_version)

### 7.4 No Hidden Veto

Per the canonical design: "No hidden deterministic veto. Deterministic influence visible and reviewable." Every critic verdict must be visible in `DecisionEvent.runtime_interpretation` with `suppression_reason` and `review_tags`.

---

## 8. Key Design Decisions

| Decision | Rationale | Locked? |
|---|---|---|
| Critic is advisory only | Safe RL shielding principle (Alshiekh et al. 2018) | ✅ YES |
| Gates retain hard veto | Deterministic safety barriers | ✅ YES |
| No execution authority for critic | Separation of concerns | ✅ YES |
| Shadow mode before any live influence | Evidence-gated progression | ✅ YES |
| Simulation engine is single economic truth | Truth hierarchy (CLAUDE.md) | ✅ YES |
| Human approval for all live transitions | Governance requirement | ✅ YES |
| Emergency override at Runtime Risk Gate | Defense in depth | ✅ YES |
| IQL as primary, CQL as cross-check | Validated offline RL approach | LOCK_CANDIDATE |
| Distributional + conformal for V3 | Risk-aware gating | LOCK_CANDIDATE |

---

## 9. Related Documents

- [[policy_critic_design.md]] — Architecture and data flow
- [[pipeline.md]] — Versioned implementation pipeline
- [[replay_buffer_design.md]] — Prerequisite infrastructure
- [[rollout_plan.md]] — Staged deployment plan
- [[rl_intro_for_v7.md]] — RL concepts (including safe RL)
- `v7/docs/policy_critic/design.md` — Canonical design
- `v7/docs/policy_critic/codebase_maps/contracts_runtime_map.md` — Runtime wiring map
- `v7/docs/policy_critic/codebase_maps/simulation_map.md` — Simulation truth map

## 10. References

- Alshiekh et al. 2018, "Safe Reinforcement Learning via Shielding", AAAI 2018 — [arXiv:1708.08611](https://arxiv.org/abs/1708.08611)
- Garcia & Fernandez 2015, "A Comprehensive Survey on Safe Reinforcement Learning", JMLR
- `CLAUDE.md` — Domain boundaries and forbidden actions
- `contracts/registry.json` — Canonical contract registry
- `v7/docs/runtime/runtime_integration.md` — Per-mode readiness states, execution eligibility
- `simulation/engine/engine.py` — Economic truth authority
- `simulation/engine/costs.py` — Authoritative cost model
