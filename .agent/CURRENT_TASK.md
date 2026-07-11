# Current Task

> **Purpose:** This file contains the SINGLE task the next worker agent must execute.
> Only one task at a time. Update this when scoping new work.

---

## Task ID: SETUP-AUDIT-MEMORY-LAYER

**Status:** ✅ COMPLETED

### Objective

Set up the Audit Memory / Handoff Layer infrastructure — a set of machine-readable context files that serve as the shared memory layer between different AI agents working on this repository.

### Scope

- Create `.agent/` directory with protocol, handoff, task, and evidence files
- Create `docs/decisions/`, `docs/audits/` directories with locked decisions and findings
- Populate all files with real v7-engine data from existing docs, audits, and reports
- Build `scripts/build_agent_context.py` context compiler

### Deliverables

- [x] `.agent/CONTEXT_INDEX.md` — Reading order + worker protocol
- [x] `.agent/CURRENT_TASK.md` — This file
- [x] `.agent/HANDOFF.md` — Session handoff
- [x] `.agent/EVIDENCE_REQUIREMENTS.md` — Evidence standard
- [x] `docs/project_context.md` — Project overview
- [x] `docs/decisions/DECISIONS.md` — Locked decisions
- [x] `docs/audits/FINDINGS_LEDGER.md` — Verified findings
- [x] `docs/audits/OPEN_QUESTIONS.md` — Open investigations
- [x] `docs/audits/ASSUMPTIONS.md` — Assumptions register
- [x] `docs/audits/audit_runs/` — Directory for per-session reports
- [x] `scripts/build_agent_context.py` — Context compiler

### Evidence

All files created and populated with repo-specific data drawn from:
- AGENTS.md (design lock semantics, domain boundaries, protocols)
- governance.md (domain ownership, truth hierarchy)
- verify_summary.md (test results, performance metrics)
- alphaforge-audit-2026-07-06.yaml (BTC duplicates, NaN, gaps)
- research_run_real_10sym.json (training performance)
- ai_summary.md (subsystem authority map)

### Handoff

See `.agent/HANDOFF.md` for full working summary and recommended next task.
