# Agent Task — Evidence Requirements

> **Purpose:** Every task claiming completion must satisfy ALL applicable requirements below.
> The worker MUST provide the specified evidence types before marking the task as PASS.

---

## Universal Requirements (ALL tasks)

- [ ] **Task scope** matches `.agent/CURRENT_TASK.md` exactly
- [ ] **No unrelated changes** were made outside task scope
- [ ] **No locked decisions** were silently overridden
- [ ] **FINDINGS_LEDGER.md** updated with new or revised findings
- [ ] **OPEN_QUESTIONS.md** updated with remaining unknowns
- [ ] **HANDOFF.md** rewritten with complete work summary
- [ ] **Real data used** — no synthetic/mocked results claimed as evidence

---

## Code Change Requirements

- [ ] **Tests pass** — full relevant test suite output provided
- [ ] **No import boundary violations** — `make check-boundaries` passes
- [ ] **Contracts updated** if schema changed — `make check-contracts` passes
- [ ] **Types correct** — no new type errors introduced
- [ ] **Existing behavior preserved** — no regressions in passing tests

---

## Research / Analysis Requirements

- [ ] **Concrete evidence** — file:line references, command output, benchmark numbers
- [ ] **Confidence score** — 0.00–1.00 for every finding
- [ ] **Severity classification** — CRITICAL / HIGH / MEDIUM / LOW / INFO
- [ ] **Reproduction steps** — exact commands to reproduce the result
- [ ] **Limitations stated** — what the analysis does NOT cover

---

## Performance / Benchmark Requirements

- [ ] **Before/after comparison** — timing, resource utilization, or throughput
- [ ] **Hardware context** — CPU model, RAM, GPU (if applicable), data size
- [ ] **Statistical significance** — multiple runs if variance > 5%
- [ ] **Profiling data** — stage-level breakdown, not just end-to-end

---

## Report / Documentation Requirements

- [ ] **ACCP-YAML report** written to `reports/` with structured results
- [ ] **ai_summary.md** updated if subsystem architecture changed
- [ ] **Affected docs** updated to reflect new state
- [ ] **DECISIONS.md updated** if new locked decision or changed status

---

## Handoff Requirements

- [ ] **HANDOFF.md** contains:
  - [ ] Work completed
  - [ ] Files inspected (full paths)
  - [ ] Files modified (full paths)
  - [ ] Commands executed
  - [ ] Tests and benchmarks run
  - [ ] Unresolved blockers
  - [ ] Exact recommended next action
- [ ] **Final response** in standard format:
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

---

## Task-Specific Requirements

These are set per-task in `.agent/CURRENT_TASK.md`. Check that file for additional requirements.
