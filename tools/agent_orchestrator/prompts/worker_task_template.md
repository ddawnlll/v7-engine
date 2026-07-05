Implement the requested task below.

## Task

{{TASK}}

## Rules

- Implement only what is requested. Do not over-engineer.
- If the task asks for code changes, run relevant tests/checks afterward.
- Do NOT modify these authority files: evaluation.py, factors.py,
  simulation_adapter.py, fast_simulator.py, authority_map.md
- Never claim success without evidence.

## Required — Completion Summary

Your final output MUST include a completion summary with these fields:

```
## Completion Summary
- Files changed: [...]
- Commands run: [...]
- train_start: <date>
- train_end: <date>
- test_start: <date>
- test_end: <date>
- n_combinations: <number of trials>
- metric: <key metric value>
- Results: [...]
- Status: SUCCESS | FAILURE | BLOCKED
```

The gate checks for these fields. If they are missing, the iteration FAILs
and your work may be discarded.
