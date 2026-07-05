# V7 Engine — MEMORY.md (Constitution)

## META

This is the **durable constitution** for the V7 Engine project. It encodes invariant rules that no agent, script, or workflow may override. Violations are design defects.

---

## Article 1 — Economic Source of Truth

**1.1** `simulation.engine` is the sole economic source of truth for cost, stop/target, label, and execution semantics.

**1.2** No component may define its own cost model, stop-loss, take-profit, horizon, or exit semantics. All such definitions must derive from simulation contracts.

**1.3** AlphaForge may wrap simulation outputs for feature engineering and label construction, but must NOT redefine:
- Fee/slippage/funding costs
- Stop/target/horizon parameters
- Label definitions or classification logic
- Execution eligibility rules

**1.4** Measurement trust and contract correctness ALWAYS precede profitability optimization. A profitable system with untrustworthy measurements is a liability.

---

## Article 2 — Authority Layer

**2.1** Hardcoded cost, stop/target, label, or execution constants outside `simulation/` authority files are FORBIDDEN. All constants must derive from `SimulationProfile` or simulation contracts via the authority layer.

**2.2** The authority layer at `simulation/authority.py` is the centralized gateway for cost and label resolution. Components that need cost or label data must call this authority; they must NOT re-derive or hardcode equivalents.

**2.3** Any change to simulation contracts (cost parameters, stop/target definitions, label schema) requires:
- PASS on all simulation golden tests
- PASS on all contract registry parity checks
- PASS on all import-boundary tests
- An ACCP-YAML report documenting the change

---

## Article 3 — No Auto-Promotion

**3.1** No agent, script, or workflow may auto-commit, auto-merge, or auto-promote code to main without explicit human review.

**3.2** No agent may disable tests, skip verification steps, or bypass CI gates.

**3.3** No agent may modify `.github/workflows/ci.yml`, `Makefile` verification targets, or test harnesses to weaken enforcement.

**3.4** No agent may modify secrets, credentials, or `.env` files unless explicitly directed by a human with documented approval.

**3.5** No agent may secretly modify `AGENTS.md`, `CLAUDE.md`, `MEMORY.md`, or other constitution-level documents without transparent reporting.

---

## Article 4 — Domain Boundaries (Immutable)

```
lib/             → shared primitives only; NO imports of v7/alphaforge/simulation
simulation/      → economic truth; owns cost/horizon/exit semantics
alphaforge/      → alpha discovery; owns feature/label/model research
v7/              → policy acceptance; owns final trade decisions & evaluation
runtime/         → execution eligibility; owns lifecycle, orchestration, safety
contracts/       → cross-domain schemas; registry.json is canonical list
interface/       → operator UI; observes runtime API only
```

**4.1** V7 does NOT invent alpha. AlphaForge discovers it.

**4.2** AlphaForge does NOT own final trade decisions. V7 owns policy acceptance.

**4.3** Simulation owns economic truth. No component may bypass simulation costs.

**4.4** Runtime does NOT override policy with model confidence.

---

## Article 5 — Workflow Integrity

**5.1** All experiment outputs must be saved under `data/runs/` or `.runs/` with timestamps and git HEAD commit. Untracked experiments have zero evidentiary value.

**5.2** Code changes by agents must be made in isolated git worktrees. No agent modifies the main working tree directly.

**5.3** After every task, the agent must produce an ACCP-YAML report in `reports/` documenting what was done, what evidence exists, and what remains.

**5.4** The Praxis Verifier must confirm all evidence before any system state is declared functional.

---

## Article 6 — Memory Provider

**6.1** ByteRover is the preferred external memory provider for cross-session knowledge persistence.

**6.2** Holographic is the safe fallback if ByteRover is unavailable.

**6.3** Memory must not store secrets, credentials, sensitive financial data, or task-completion bookkeeping (PR numbers, commits, "Phase N done").

---

## Article 7 — Amendment

**7.1** This constitution may only be amended by explicit human direction.

**7.2** Amendment requires an ACCP-YAML report documenting what changed, why, and which articles were affected.

**7.3** No agent may infer implied amendments from task instructions.
