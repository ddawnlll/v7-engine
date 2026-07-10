"""V7-Lite Calibration Control Plane — typed gate registry for alpha promotion.

Each gate is a typed, evaluatable condition with:
- Unique gate_id
- Weight and passing threshold
- evaluate() function that checks conditions using outcome cache data
- Status tracking (PASS/PARTIAL_PASS/FAIL/NOT_EVALUATED)

This is the control plane for the V7-Lite completion gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional
import uuid

import pandas as pd
import numpy as np


class GateStatus(Enum):
    PASS = "PASS"
    PARTIAL_PASS = "PARTIAL_PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"
    NOT_STARTED = "NOT_STARTED"


@dataclass
class GateEvaluator:
    """A single evaluatable gate with weight and scoring function."""

    gate_id: str
    name: str
    weight_pct: float  # Contribution to overall score (0-100)
    description: str
    status: GateStatus = GateStatus.NOT_EVALUATED
    score_pct: float = 0.0  # 0.0 to 1.0
    weighted_score: float = 0.0  # weight_pct * score_pct / 100
    evidence: list[str] = field(default_factory=list)
    blocking_files: list[str] = field(default_factory=list)
    next_action: str = ""

    def evaluate(self, eval_fn: Callable[[dict[str, Any]], tuple[GateStatus, float, list[str]]],
                 context: dict[str, Any] | None = None) -> None:
        """Evaluate this gate against a scoring function."""
        ctx = context or {}
        self.status, self.score_pct, new_evidence = eval_fn(ctx)
        self.evidence.extend(new_evidence)
        self.weighted_score = self.weight_pct * self.score_pct

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "name": self.name,
            "weight_pct": self.weight_pct,
            "status": self.status.value,
            "score_pct": round(self.score_pct * 100, 1),
            "weighted_score": round(self.weighted_score, 2),
            "evidence": self.evidence,
            "blocking_files": self.blocking_files,
            "next_action": self.next_action,
        }


@dataclass
class GateRegistry:
    """Registry of all V7-Lite gates with scoring and reporting."""

    gates: dict[str, GateEvaluator] = field(default_factory=dict)
    name: str = "V7-Lite AlphaForge Completion Gate"
    version: str = "v0.2"
    generated: str = ""

    def __post_init__(self):
        self.generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def add_gate(self, gate: GateEvaluator) -> None:
        self.gates[gate.gate_id] = gate

    def evaluate_all(self, context: dict[str, Any] | None = None) -> None:
        """Evaluate all gates that have an evaluate function registered."""
        for gate in self.gates.values():
            if hasattr(gate, '_eval_fn') and gate._eval_fn:
                gate.evaluate(gate._eval_fn, context)

    def register_evaluator(self, gate_id: str, 
                           eval_fn: Callable[[dict[str, Any]], tuple[GateStatus, float, list[str]]]) -> None:
        """Register an evaluation function for a gate."""
        if gate_id in self.gates:
            self.gates[gate_id]._eval_fn = eval_fn

    @property
    def total_score(self) -> float:
        return sum(g.weighted_score for g in self.gates.values())

    @property
    def status_summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "generated": self.generated,
            "total_score": round(self.total_score, 1),
            "gates": [g.to_dict() for g in self.gates.values()],
            "hard_blockers": [
                g.gate_id for g in self.gates.values()
                if g.status == GateStatus.FAIL
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.status_summary, indent=indent)

    def to_dict(self) -> dict[str, Any]:
        return self.status_summary

    def report_md(self) -> str:
        """Generate a Markdown gate report."""
        lines = [
            f"# {self.name} {self.version}",
            f"",
            f"**Generated:** {self.generated}",
            f"**Overall Score:** {self.total_score:.1f}%",
            f"",
            f"## Gate Summary",
            f"",
            f"| Gate | Weight | Score | Weighted | Status |",
            f"|------|--------|-------|----------|--------|",
        ]
        for g in self.gates.values():
            s = g.to_dict()
            lines.append(
                f"| {g.gate_id} {g.name} | {g.weight_pct}% | "
                f"{s['score_pct']}% | {s['weighted_score']}% | {s['status']} |"
            )
        lines.extend([
            f"| **Total** | **100%** | | **{self.total_score:.1f}%** | |",
            f"",
            f"## Hard Blockers",
        ])
        blockers = [g for g in self.gates.values() if g.status in (GateStatus.FAIL, GateStatus.NOT_EVALUATED)]
        if blockers:
            for g in blockers:
                lines.append(f"- **{g.gate_id}** ({g.status.value}): {g.next_action}")
        else:
            lines.append("- None")

        return "\n".join(lines)


def build_default_registry() -> GateRegistry:
    """Build default V7-Lite gate registry with weights."""
    registry = GateRegistry()

    registry.add_gate(GateEvaluator(
        gate_id="G0", name="Alpha Discovery Exists",
        weight_pct=10, description="Inventory of alpha concepts tested on real data",
    ))
    registry.add_gate(GateEvaluator(
        gate_id="G1", name="Minimum Alpha Viability",
        weight_pct=10, description="At least one candidate with positive raw expectancy",
    ))
    registry.add_gate(GateEvaluator(
        gate_id="G2", name="Cost-Adjusted Survival",
        weight_pct=15, description="At least one candidate survives realistic costs at 0.10R",
    ))
    registry.add_gate(GateEvaluator(
        gate_id="G3", name="OOS / Walk-Forward / Holdout",
        weight_pct=15, description="OOS evaluation with walk-forward or holdout",
    ))
    registry.add_gate(GateEvaluator(
        gate_id="G4", name="Regime/Symbol/Session Robustness",
        weight_pct=10, description="Edge persists across regimes, symbols, sessions",
    ))
    registry.add_gate(GateEvaluator(
        gate_id="G5", name="Baseline Dominance",
        weight_pct=10, description="Beats simple baselines (ATR, momentum, random)",
    ))
    registry.add_gate(GateEvaluator(
        gate_id="G6", name="Replay Infrastructure",
        weight_pct=15, description="Outcome cache, simulation parity, replay pipeline",
    ))
    registry.add_gate(GateEvaluator(
        gate_id="G7", name="Calibration Control Plane",
        weight_pct=10, description="Typed gate registry, bounded mutation, champion/challenger",
    ))
    registry.add_gate(GateEvaluator(
        gate_id="G8", name="Revenue / Live Readiness",
        weight_pct=5, description="Promoted alpha clusters, paper/shadow pass",
    ))

    return registry
