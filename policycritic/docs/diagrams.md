# Architecture Diagrams — V7 Policy Critic

> All diagrams use Mermaid syntax. Render with any Mermaid-compatible viewer (GitHub, VS Code, mermaid.live).

## 1. Authority Hierarchy

The critic is the **lowest authority** — it advises, gates decide.

```mermaid
graph TD
    subgraph "V7 Authority Hierarchy"
        A["Runtime Risk Gate<br/>max daily loss, max drawdown, circuit breaker<br/>SUPREME VETO — non-bypassable"]
        B["Final Operational Gate<br/>execution eligibility, cooldown, exposure, kill-switches<br/>VETO"]
        C["V7 Policy Gates<br/>confidence, expected-R, regime, degradation, portfolio, risk<br/>VETO"]
        D["Policy Critic<br/>risk score, confidence downweight, NO_TRADE recommendation<br/>ADVISORY ONLY"]
        E["AlphaForge Scorer<br/>XGBoost: LONG_NOW / SHORT_NOW / NO_TRADE + alpha scores<br/>PROPOSES"]
        F["Execution Layer<br/>ExecutionOrchestrator<br/>EXECUTES only gate-cleared actions"]
    end

    A -->|vetoes all below| B
    B -->|vetoes all below| C
    C -->|vetoes critic + model| D
    D -->|advisory verdict| E
    E -->|proposes actions| C
    C -->|cleared actions| F

    style A fill:#ff4444,color:#fff
    style B fill:#ff6644,color:#fff
    style C fill:#ff8844,color:#fff
    style D fill:#44aaff,color:#fff
    style E fill:#44cc44,color:#fff
    style F fill:#888888,color:#fff
```

**Key rule**: Red boxes (gates) can override the blue box (critic). The critic can never override any red box.

## 2. Data Flow — Per-Decision Pipeline

```mermaid
flowchart TD
    A["AnalysisRequest<br/>symbol, mode, interval, canonical state"] --> B
    B["AlphaForge Scorer<br/>XGBoost: p_long/short/no_trade, expected_R, alpha scores"] --> C
    C{"V7 Policy Gates<br/>confidence ≥ min? expected_R ≥ min?<br/>regime consistent? not degraded?"}
    C -->|FAIL| Z["NO_TRADE<br/>critic NOT consulted"]
    C -->|PASS| D
    D["Policy Critic<br/>IQL Q(s,a) → risk score<br/>conformal lower-quantile check"] --> E
    E{"Critic Verdict"}
    E -->|ALLOW| F["Confidence unchanged<br/>policy_passed = true"]
    E -->|DOWNWEIGHT| G["Multiply confidence<br/>re-trip confidence gate"]
    E -->|VETO_TO_NO_TRADE| H["Policy sets NO_TRADE<br/>policy_passed = false<br/>suppression_reason = 'critic_veto'"]
    E -->|REQUIRE_REVIEW| I["should_surface_to_review = true<br/>IQL/CQL disagreement"]
    F --> J
    G --> J
    H --> J
    I --> J
    J["Portfolio + Risk Gates"] --> K
    K["Runtime Execution Eligibility<br/>operational hard gate"] --> L
    L["ExecutionOrchestrator<br/>executes or routes to paper"]

    style C fill:#ff8844,color:#fff
    style D fill:#44aaff,color:#fff
    style K fill:#ff6644,color:#fff
    style Z fill:#ff4444,color:#fff
```

**Critical detail**: When the critic says VETO_TO_NO_TRADE, **V7 policy enacts the veto** — the critic does not directly change `recommended_action`. The verdict is recorded in `runtime_interpretation.suppression_reason`.

## 3. Phase Rollout — Evidence-Gated Progression

```mermaid
graph LR
    P0["Phase 0<br/>Docs & Design<br/>← WE ARE HERE"] -->|"docs approved<br/>partner sign-off"| P1
    P1["Phase 1<br/>Contract & Schema"] -->|"schema validated<br/>registry entry"| P2
    P2["Phase 2<br/>Replay Buffer"] -->|"≥1000 tuples<br/>no leakage"| P3A
    P3A["Phase 3A<br/>V2 Supervised"] -->|"DSR p<0.05<br/>PBO<0.10"| P3B
    P3B["Phase 3B<br/>OPE/FQE"] -->|"FQE CI overlaps"| P3C
    P3C["Phase 3C<br/>V3 IQL Critic"] -->|"Bellman stable<br/>CQL bounded"| P4
    P4["Phase 4<br/>Shadow Runtime"] -->|"30 days stable<br/>zero influence"| P5
    P5["Phase 5<br/>Guarded Influence"] -->|"60 days<br/>human approval"| P6
    P6["Phase 6<br/>Business Validation"] -->|"≥90 days<br/>all metrics held"| LIVE
    LIVE["Live Consideration<br/>human approval required"]

    style P0 fill:#44aaff,color:#fff
    style LIVE fill:#ff4444,color:#fff
```

**Each transition requires evidence.** No phase may begin before predecessor exit criteria are met. Human approval is required for Phase 5+.

## 4. Shadow-Mode Lifecycle

```mermaid
sequenceDiagram
    participant SR as Scan Runtime
    participant AF as AlphaForge Scorer
    participant PG as V7 Policy Gates
    participant PC as Policy Critic (shadow)
    participant SP as ShadowPolicyRepository
    participant EX as ExecutionOrchestrator

    SR->>AF: Request analysis (symbol, mode, interval)
    AF-->>SR: AnalysisResult (LONG_NOW, confidence=0.72)
    SR->>PG: Apply policy gates
    PG-->>SR: PASS (confidence ≥ 0.55, expected_R ≥ 0.5)
    SR->>PC: Review (state, proposed_action, confidence)
    PC-->>SR: PolicyCriticReview (verdict=ALLOW, is_advisory=true)
    SR->>SP: Persist PolicyCriticReview
    Note over SR,EX: Critic verdict is ADVISORY — gates decide
    SR->>EX: Execute if gates pass (critic verdict does NOT control execution)
    EX-->>SR: Execution result
```

**Critical invariant**: The critic verdict is persisted for audit but does NOT control the execution path. Execution follows gate decisions, not critic recommendations. During shadow mode, even VETO_TO_NO_TRADE verdicts do not block execution.

## 5. Business Validation Loop

```mermaid
flowchart TD
    A["Deploy critic in shadow mode<br/>Phase 4"] --> B
    B["Record PolicyCriticReview<br/>for every scan decision<br/>30 days minimum"] --> C
    C["Compare shadow verdicts<br/>vs actual outcomes"] --> D
    D{"Metrics check"}
    D -->|"DSR p<0.05<br/>PBO<0.10<br/>no drawdown worsening"| E
    D -->|"FAIL"| X["HOLD — investigate<br/>recalibrate or rollback"]
    E["Enable guarded influence<br/>Phase 5 — SWING only"] --> F
    F["Continue recording<br/>60 days minimum"] --> G
    G{"Metrics check"}
    G -->|"DSR maintained<br/>FQE CI overlaps<br/>human approval"| H
    G -->|"FAIL"| X
    H["Business validation<br/>Phase 6 — ≥90 days"] --> I
    I{"Final check"}
    I -->|"All metrics held<br/>all stakeholders signed off"| J
    I -->|"FAIL"| X
    J["Live consideration<br/>human approval required"]

    style A fill:#44aaff,color:#fff
    style J fill:#ff4444,color:#fff
    style X fill:#ff8844,color:#fff
```

**The loop never shortcuts.** Shadow evidence must precede influence. Influence evidence must precede live consideration. Failure at any gate returns to shadow-only mode.
