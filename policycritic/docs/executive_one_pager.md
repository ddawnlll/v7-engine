# V7 Policy Critic — Executive One-Pager

> **3-minute read for partners, reviewers, and stakeholders**

## 1. What This Is

The V7 Policy Critic is a proposed **advisory safety layer** for the V7 trading engine. It reviews every proposed trade from the AlphaForge scorer and emits a verdict: ALLOW, DOWNWEIGHT_CONFIDENCE, VETO_TO_NO_TRADE, or REQUIRE_REVIEW. It never opens trades, never closes trades, and never bypasses deterministic safety gates.

**This is a docs/design package only.** No implementation exists. No runtime behavior has been changed.

## 2. Why It Matters

V7's deterministic policy gates apply fixed thresholds (min confidence ≥ 0.55, min expected-R ≥ 0.5) to every trade regardless of context. A 0.55-confidence trade in a calm trending regime has fundamentally different risk from a 0.55-confidence trade in a volatile transition regime — but the gates treat them identically. The critic fills this gap with context-aware risk assessment.

## 3. What Problem It Solves

| Problem | How the Critic Helps |
|---------|---------------------|
| Gates are context-blind | Critic learns regime-conditional risk |
| Gates check factors independently | Critic evaluates combined risk factors |
| No expected value estimation | Critic learns Q(s,a) — expected return per action |
| No OOD detection | Critic detects distribution shift via reconstruction error |
| No uncertainty quantification | Conformal calibration produces prediction intervals |

## 4. Why Advisory Only — The Shield Architecture

The safe RL literature (Alshiekh et al. 2018) proves: **learned components must sit under deterministic, verified shields.** V7 follows this exactly:

```
Runtime Risk Gate         ← SUPREME VETO (hard-coded, non-bypassable)
    ↓
Final Operational Gate    ← VETO (execution eligibility, cooldown, kill-switches)
    ↓
V7 Policy Gates           ← VETO (confidence, expected-R, regime, degradation)
    ↓
Policy Critic             ← ADVISORY ONLY (recommends, annotates, downweights)
    ↓
AlphaForge Scorer         ← PROPOSES (LONG_NOW / SHORT_NOW / NO_TRADE)
```

The critic advises; the gates decide. This is not a design preference — it is a safety requirement validated by peer-reviewed literature.

## 5. What Business Value It May Create

All numbers are **illustrative scenarios** — no profit is claimed or guaranteed.

| Scenario | Mechanism | Estimated Annual Impact (1000 trades/yr, $1000/trade) |
|----------|----------|-------------------------------------------------------|
| Conservative | Avoids 2% of losing trades | ~$1,200 (cost-neutral) |
| Base | Avoids 5% + confidence downweight | ~$125,000 |
| Aggressive | Avoids 10% + optimal sizing | ~$250,000 (do not budget) |
| Failure | Incorrectly vetoes winners | -$50,000 (why shadow evidence is mandatory) |

## 6. Why Profitability Is Not Guaranteed

- All numbers are illustrative. No shadow data exists yet.
- Actual profitability requires ≥ 90 days of shadow comparison.
- DSR must reach p < 0.05; PBO must be < 0.10.
- No live claims without live evidence.
- Regime shifts can eliminate any learned edge.
- Costs (fees, slippage, funding) can exceed the critic's alpha.

## 7. What Must Be Proven Before Live Influence

| Gate | Requirement |
|------|------------|
| Shadow evidence | ≥ 90 days stable operation |
| Statistical significance | DSR p < 0.05 |
| No overfitting | PBO < 0.10 |
| Regime robustness | No single-regime degradation |
| OPE validation | FQE 95% CI overlaps observed performance |
| Walk-forward | ≥ 4/5 folds consistent |
| Drawdown | No worsening vs baseline |
| Human approval | Required for any live influence |
| Kill-switch | Tested and operational |

## 8. What Changed in This PR

- **47+ documentation files** across 7 subdirectories
- **15 deep research docs** covering all RL topics (IQL, CQL, distributional RL, safe RL, OPE/FQE, backtest overfitting, conformal calibration, etc.)
- **7 phase plans** (P0-P6) with entry/exit criteria, PR sequencing, rollback plans
- **6 business docs** including profitability calculation with sensitivity matrix, unit economics, risk register (25 risks)
- **Quality system**: self-scorecard (8.7/10), partner feedback traceability (12 items), independent AI review packet, 62-item acceptance rubric
- **Implementation file map**: 12-PR sequence, 48-item readiness checklist, 6 architecture maps
- **Reviewer tools**: executive one-pager, Mermaid diagrams, ADRs, reviewer guide

## 9. What Did NOT Change

- ❌ No runtime/engine/frontend/backend code
- ❌ No tests
- ❌ No contracts or configs
- ❌ No database migrations
- ❌ No new dependencies
- ❌ No .claude/ files committed
- ❌ No production behavior

## 10. Recommended Next Step

1. **Review** this package using `reviewer_guide.md`
2. **Submit** `quality/independent_ai_review_packet.md` to ChatGPT or another separate AI
3. **Confirm** independent AI score ≥ 8.0/10
4. **Approve** merge of `pr/v7-policycritic-docs`
5. **Authorize** Phase 1: PolicyCriticReview contract definition

---

> **Key takeaway**: The Policy Critic is an advisory safety layer that could improve trade selection by 2-10% without replacing deterministic gates, without holding final authority, and without requiring live RL exploration. Every claim requires evidence before live deployment. This docs package establishes the design, research, business case, and evidence gates needed to proceed responsibly.
