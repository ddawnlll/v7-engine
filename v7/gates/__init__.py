"""
G0-G10 Promotion Gate Framework.

Each gate is a named check-point that a candidate must pass before
promotion to the next level. The framework follows
v7/docs/pipeline/evaluation.md.

Gate levels (canonical G0-G10 per TR-07 plan):
  G0  — DOC_READY             Authority docs, schemas, data integrity
  G1  — RESEARCH_BACKTEST     Initial cost-honest backtest metrics
  G2  — WALK_FORWARD_OOS      6-fold walk-forward, expectancy R
  G3  — COST_STRESS           Fee×multiplier, slippage stress, funding
  G4  — REGIME_BREAKDOWN      Per-regime performance (no catastrophic collapse)
  G5  — SYMBOL_STABILITY      Per-symbol contribution ≤40%
  G6  — CALIBRATION_RELIABILITY  ECE, MCE within bounds
  G7  — SHADOW                Live-market observation, no orders
  G8  — PAPER                 Paper forward simulation, full trade lifecycle
  G9  — TINY_LIVE             Small real-capital, strict kill switches
  G10 — LIVE                  Production-eligible, all prior gates passed

Only SWING mode is currently evaluable (LOCKED_INITIAL_BASELINE).
SCALP/AGGRESSIVE_SCALP are HOLD — they will be evaluable after
empirical evidence gates are satisfied.

Sub-modules:
    evaluator:  Canonical gate implementations (G0-G10)
    config:     Gate configuration (GateConfig, DEFAULT_GATE_CONFIG, loader)
    runner:     Automated gate runner (run_gates, to_json_report, write_report)
"""

from v7.gates.evaluator import (
    CANONICAL_GATE_NAMES,
    GATE_DEFINITIONS,
    GateResult,
    GateStatus,
    evaluate_candidate,
    evaluate_gate,
    get_promotion_summary,
)

from v7.gates.config import (
    DEFAULT_GATE_CONFIG,
    GateConfig,
    load_gate_config,
    resolve_gate_configs,
)

from v7.gates.runner import (
    run_gates,
    to_json_report,
    write_report,
)
