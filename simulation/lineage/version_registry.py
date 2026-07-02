"""
Version registry for simulation lineage.

Central source of truth for all hardcoded version strings and family labels
used in SimulationLineage construction. Every string constant that was
previously inlined in engine.py lives here.
"""

# ── Shared semver component ───────────────────────────────────────────────
VERSION: str = "1.0.0"

# ── Family version strings (prefix + VERSION) ────────────────────────────
SIMULATION_FAMILY_VERSION: str = f"simfam-{VERSION}"
COST_MODEL_VERSION: str = f"cost-{VERSION}"

# ── Standalone version strings ───────────────────────────────────────────
FEE_MODEL_VERSION: str = f"fee-{VERSION}"
SLIPPAGE_MODEL_VERSION: str = f"slippage-{VERSION}"
FUNDING_MODEL_VERSION: str = f"funding-{VERSION}"

# ── Horizon family template ──────────────────────────────────────────────
HORIZON_FAMILY_SUFFIX: str = "_horizon"

# ── Static families ──────────────────────────────────────────────────────
TIME_EXIT_FAMILY: str = "hold_then_exit"
ADAPTER_KIND: str = "TRAINING"
