# Agent Context Index — Reading Order

> **Purpose:** This file defines the exact reading order an AI agent must follow when entering this repository.
> Every new worker **must** read these files in sequence before analyzing or modifying anything.
>
> **Rule:** Chat history is NOT source of truth. These files ARE source of truth.

## Mandatory Reading Order

| # | File | What It Contains |
|---|------|-----------------|
| 1 | `.agent/CONTEXT_INDEX.md` | (this file) Entry point and protocol |
| 2 | `docs/project_context.md` | Project purpose, scope, architecture, goals |
| 3 | `docs/decisions/DECISIONS.md` | Locked design decisions and rationale |
| 4 | `docs/audits/FINDINGS_LEDGER.md` | All verified audit findings with evidence |
| 5 | `docs/audits/OPEN_QUESTIONS.md` | Unverified suspicions and open investigations |
| 6 | `.agent/HANDOFF.md` | Last agent's working summary |
| 7 | `.agent/CURRENT_TASK.md` | Single task to execute now |
| 8 | `.agent/EVIDENCE_REQUIREMENTS.md` | Evidence standard for task completion |

## Subsystem Entry Points

After the core context, read the relevant subsystem documentation:

| Subsystem | Entry Point |
|-----------|-------------|
| **Repo root** | `ai_summary.md` |
| **V7 Pipeline** | `v7/docs/ai_summary.md` |
| **Runtime** | `runtime/docs/ai_summary.md` |
| **Simulation** | `simulation/docs/ai_summary.md` |
| **AlphaForge** | `alphaforge/docs/ai_summary__v7_alphaforge_xgb.md` |
| **Policy Critic** | `v7/docs/policy_critic/ai_summary.md` |
| **Interface** | `interface/docs/ai_summary.md` |
| **Contracts** | `contracts/registry.json` + `contracts/schemas/` |

## Worker Protocol

### Before Analysis

1. Read all 8 mandatory files above.
2. Read relevant subsystem `ai_summary.md`.
3. Read `AGENTS.md` for working instructions (design lock semantics, domain boundaries).

### During Analysis

- Treat **confirmed findings** and **locked decisions** as prior knowledge.
- Do NOT repeat previously completed analysis unless new evidence contradicts it.
- Do NOT silently override a locked decision.
- When you disagree with an existing finding, record the contradiction with **file:line, command output, benchmark, or test evidence**.
- Distinguish clearly between: `CONFIRMED FACT` / `STRONG INFERENCE` / `HYPOTHESIS` / `UNKNOWN`
- Inspect the repository directly. Never rely only on supplied summaries.
- Keep scope limited to `.agent/CURRENT_TASK.md`.
- Do NOT make unrelated refactors.

### Before Claiming Completion

- Satisfy all items in `.agent/EVIDENCE_REQUIREMENTS.md`.
- Update `docs/audits/FINDINGS_LEDGER.md` with new or revised findings.
- Update `docs/audits/OPEN_QUESTIONS.md` with remaining unknowns.
- Rewrite `.agent/HANDOFF.md` with:
  - Work completed
  - Files inspected
  - Files modified
  - Commands executed
  - Tests and benchmarks run
  - Unresolved blockers
  - Exact recommended next action

### Final Response Format

```
status: PASS / PASS_WITH_HOLDS / HOLD / FAIL
confirmed_findings:
  - id: F-NNN
    summary: ...
changes:
  - file: ...
    summary: ...
evidence:
  - ...
remaining_risks:
  - ...
recommended_next_task: ...
```

## Task-Based Context Compilation

For focused tasks, run the context compiler to build a minimal context file:

```bash
python scripts/build_agent_context.py --task TASK_ID --output /tmp/agent-context.md
```

This selects only relevant decisions, findings, and evidence for the given task scope.
