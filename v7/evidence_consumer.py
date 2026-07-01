"""
V7 Evidence Consumer — consumes ``EvidencePassport`` produced by AlphaForge
and produces V7 gate statuses and policy decisions.

This is the V7-side adapter.  It complements ``alphaforge.evidence_adapter``
which produces passports from the training pipeline.

Usage::

    from v7.evidence_consumer import consume_evidence_passport

    gate_results = consume_evidence_passport(passport)
    for gname, gr in gate_results.items():
        print(f"{gname} ({gr.gate_label}): {gr.status}")
"""

from __future__ import annotations

from lib.evidence_engine.evidence_passport import EvidencePassport
from lib.evidence_engine.gate_mapping import GateMapper, GateResult


def consume_evidence_passport(
    passport: EvidencePassport,
) -> dict[str, GateResult]:
    """Map an ``EvidencePassport`` to V7 gate statuses (G0-G10).

    Parameters
    ----------
    passport:
        The passport produced by ``EvidencePassportBuilder`` or
        ``build_alphaforge_passport``.

    Returns
    -------
    dict[str, GateResult]
        Gate name -> result mapping.  Also writes the statuses back
        to ``passport.v7_gates`` as a side effect.
    """
    mapper = GateMapper()
    gate_results = mapper.map_passport_to_gates(passport)

    # Write results back into the passport so subsequent calls to
    # DecisionEngine can read them.
    passport.v7_gates = {
        gname: gr.status for gname, gr in gate_results.items()
    }

    return gate_results


def get_blocking_gates(
    gate_results: dict[str, GateResult],
) -> list[GateResult]:
    """Convenience: return only gates that are FAILED or BLOCKED."""
    mapper = GateMapper()
    return mapper.get_blocked_gates(gate_results)


def get_gate_progress(
    gate_results: dict[str, GateResult],
) -> dict:
    """Convenience: return a summary dict of gate-passing progress."""
    mapper = GateMapper()
    return mapper.get_overall_progress(gate_results)
