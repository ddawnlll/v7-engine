# V7 Engine — CLAUDE.md

## META

This file tells Claude Code how to work in this repo. Read it first.

**Repo language:** English (code, docs, identifiers). Turkish may appear in ACCP-YAML prompt blocks and reports — preserve it; don't translate it.

---

## Start Here: The ai_summary Pattern

Every subsystem has an `ai_summary.md` that is the canonical dense-synthesis entry point. **Always read the relevant ai_summary before touching any file in that subsystem.**

| Subsystem | ai_summary | When to read |
|-----------|-----------|-------------|
| Repo root | `ai_summary.md` | Any task — thin meta-hub, orients you to subsystems |
| V7 Pipeline | `v7/docs/ai_summary.md` | V7 docs, pipeline, contracts, mode config, evaluation |
| Simulation | `simulation/docs/ai_summary.md` | Simulation engine, cost model, exits, profiles |
| Runtime | `runtime/docs/ai_summary.md` | Python backend, API, schema, scan loop |
| Interface | `interface/docs/ai_summary.md` | React UI, components, pages |
| AlphaForge | `alphaforge/docs/ai_summary__v7_alphaforge_xgb.md` | Alpha discovery, label engine, XGBoost training |
| V7 Policy Critic | `v7/docs/policy_critic/ai_summary.md` | Policy Critic RL architecture, offline IQL critic, codebase maps, literature |

**Rule:** If an ai_summary exists for a subsystem, read it before reading any individual doc in that subsystem. The ai_summary is the dense synthesis; individual docs are authority details.

---

## Task Completion Protocol

After EVERY non-trivial task (design patch, implementation, audit, fix), you MUST:

### 1. Update related docs
- If a task changes design decisions, update the relevant domain docs to reflect the new state.
- Preserve existing decisions unless explicitly overridden by the task.
- Never rewrite large docs from scratch; prefer surgical patches.

### 2. Update `v7/docs/roadmap.md`
The roadmap is the project's state ledger. After every task, add:
- What changed (brief)
- Current lock status (LOCKED / LOCKABLE_WITH_HOLDS / HOLD / DEFERRED)
- Remaining holds and their release conditions
- Updated design lock score if applicable

### 3. Write an ACCP-YAML report
Every task produces a machine-readable completion report:
- Place in `reports/` directory
- Follow `accp_version: "2.0.0"` and `source_format: "ACCP-YAML"` format
- Required keys: `result`, `scope_confirmation`, `files_changed`, `decisions_locked`, `remaining_holds`, `safe_next_step`, `commands_run`, `evidence`
- **Accp-YAML files are the canonical task completion evidence.** They make progress machine-auditable.

### 4. Update relevant ai_summary.md if scope changed
If a task materially changes a subsystem's architecture, decisions, or contract surface, the subsystem's `ai_summary.md` must reflect it. The ai_summary is NOT auto-generated — it must be manually patched to stay current.

### 5. Sync worktrees to main (MANDATORY)
When worktree-isolated agents complete work, their commits exist ONLY in the worktree branch — they are **not visible on main** until synced. After EVERY task that runs in a worktree:

```bash
# Run the auto-sync script to cherry-pick worktree commits into main:
bash .claude/skills/sync-worktrees.sh

# Verify sync worked:
git log --oneline -5
find v7 -name "*.py" ! -path "*__pycache__*" | wc -l  # should match expected
```

**Rule:** Never claim a task complete until `sync-worktrees.sh` has run and main branch contains the worktree's commits. If cherry-pick conflicts, fall back to direct file copy (the script handles this). If sync fails, mark the issue as HOLD.

---

## Design Lock Semantics

The project uses a lock-based governance model:

| Status | Meaning |
|--------|---------|
| `LOCKED` | Authoritative, do not change without explicit evidence of contradiction |
| `LOCKED_INITIAL_BASELINE` | Implementation-ready conservative baseline; recalibrate after first evidence |
| `LOCKABLE_WITH_HOLDS` | Architecture locked; specific holds scoped and explicit |
| `HOLD` | Cannot lock yet — requires empirical evidence, owner review, or external condition |
| `DEFERRED` | Explicitly postponed with documented formula and blocking rule |
| `LOCK_CANDIDATE` | Conservative default requiring owner review before becoming LOCKED |

**Rules:**
- Never lock a numeric threshold without empirical evidence.
- HOLD means "research required" — not "low priority."
- LOCKED_INITIAL_BASELINE means "safe starting point" — not "highest priority."
- If existing docs conflict, mark the conflict and choose the least invasive patch that preserves canonical authority.

---

## Domain Boundaries (NEVER VIOLATE)

```
lib/              → shared primitives only; must NOT import v7/alphaforge/simulation
simulation/       → economic truth authority; owns cost/horizon/exit semantics
alphaforge/       → alpha discovery authority; owns feature/label/model research
v7/               → policy acceptance authority; owns final trade decisions
runtime/          → execution eligibility; owns lifecycle, orchestration, safety
contracts/        → cross-domain schemas; registry.json is canonical list
interface/        → operator UI; observes runtime API only
```

**Truth hierarchy:** `simulation > realized > contract > runtime > model`

**Critical ownership rules:**
- V7 does NOT invent alpha. AlphaForge discovers.
- AlphaForge does NOT own final trade decisions. V7 owns policy acceptance.
- Simulation owns economic truth. No component bypasses simulation costs.
- Runtime does NOT override policy with model confidence.

---

## Mode Priority

| Mode | Business Priority | Research Priority | Threshold Status |
|------|------------------|-------------------|-----------------|
| SCALP | PRIMARY | PRIMARY | LOCKED_INITIAL_BASELINE |
| AGGRESSIVE_SCALP | PRIMARY | PRIMARY | HOLD |
| SWING | SECONDARY_BASELINE | SECONDARY_BASELINE | LOCKED_INITIAL_BASELINE |

SWING is implemented first as a control baseline to validate the architecture — NOT because it is the primary product.

---

## Forbidden Actions

- Do NOT modify source code in docs-only tasks.
- Do NOT run tests in design-lock tasks.
- Do NOT create root-level architecture docs (everything lives under its domain).
- Do NOT add new trading modes or actions.
- Do NOT change locked timeframe stacks without direct contradiction evidence.
- Do NOT claim completion without running relevant verification commands.
- Do NOT treat backtest pass as live promotion evidence.
- Do NOT allow model confidence to override risk gates.

---

## Key Files to Know

| File | Purpose |
|------|---------|
| `ai_summary.md` | Repo-level meta-hub |
| `contracts/registry.json` | Canonical cross-domain contract list |
| `contracts/compatibility.json` | Version compatibility rules |
| `v7/docs/roadmap.md` | Implementation phases, lock status, holds |
| `v7/docs/profitability_thesis.md` | How V7 expects to achieve positive expectancy |
| `v7/docs/v7_mode_centric_architecture.md` | Mode-specific architecture spec |
| `v7/docs/pipeline/evaluation.md` | G0-G10 promotion gates |
| `v7/docs/runtime/runtime_integration.md` | Per-mode readiness states |
| `v7/docs/policy_critic/ai_summary.md` | Policy Critic RL architecture, design, codebase maps, research |
| `simulation/docs/cost_model.md` | Fee, slippage, funding cost model |
| `simulation/docs/profiles.md` | Mode-specific simulation profiles |
| `.github/workflows/ci.yml` | CI: contract+boundary+tests |
| `Makefile` | `make check-contracts`, `make check-boundaries`, `make test-all` |

---

## Test Commands

```bash
# Simulation tests
PYTHONPATH=. python3 -m pytest simulation/tests/ -q

# Contract registry + schema parity
PYTHONPATH=. python3 -m pytest integration/tests/test_contract_registry.py integration/tests/test_schema_parity.py -q

# Import boundaries
PYTHONPATH=. python3 -m pytest lib/tests/test_import_boundary.py integration/tests/test_cross_domain_boundaries.py simulation/tests/test_import_boundary.py -q

# Full local suite (excludes CI-only binance tests)
PYTHONPATH=. python3 -m pytest lib/tests/ integration/tests/ simulation/tests/ -q --ignore=lib/tests/test_market_data_binance.py
```
