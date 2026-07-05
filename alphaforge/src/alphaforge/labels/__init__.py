"""AlphaForge Label Adapter — deterministic SimulationOutput-to-AlphaForgeLabel transformer.

Exposes:
    LabelAdapter     — class with adapt_simulation_output and classify_no_trade_quality
    adapt_simulation_output — top-level convenience function
    classify_no_trade_quality — top-level convenience function

Domain boundary:
    alphaforge.labels must NOT import from simulation/, v7/, runtime/, or interface/.
    Allowed imports: stdlib, alphaforge.contracts.loader, alphaforge.paths, alphaforge.errors.
"""

from .adapter import LabelAdapter, adapt_simulation_output, classify_no_trade_quality

__all__ = [
    "LabelAdapter",
    "adapt_simulation_output",
    "classify_no_trade_quality",
]
