"""
G0-G10 Promotion Gate Framework.

Each gate is a named check-point that a candidate must pass before
promotion to the next level. The framework follows
v7/docs/pipeline/evaluation.md.

Gate levels:
  G0  — Structural validity (contracts, schemas)
  G1  — Data quality (no leakage, completeness)
  G2  — Label quality (simulation truth, no unresolved rows)
  G3  — Feature quality (no lookahead, canonical-state only)
  G4  — Model training (training succeeded, no silent failures)
  G5  — Calibration quality (ECE, MCE within bounds)
  G6  — Walk-forward OOS (positive expectancy R, acceptable drawdown)
  G7  — Regime stability (per-regime performance)
  G8  — Symbol stability (not carried by 1-2 symbols)
  G9  — Cost stress (passes cost stress scenarios)
  G10 — Live readiness (monitoring, rollback, kill-switch in place)

Only SWING mode is currently evaluable (LOCKED_INITIAL_BASELINE).
SCALP/AGGRESSIVE_SCALP are HOLD — they will be evaluable after
empirical evidence gates are satisfied.
"""

from v7.gates.evaluator import (
    GATE_DEFINITIONS,
    GateResult,
    GateStatus,
    evaluate_candidate,
    evaluate_gate,
)
