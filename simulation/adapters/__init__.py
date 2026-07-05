"""Simulation adapters -- bridge external data into simulation engine.

Export conventions
-------------------
All adapter classes are exported at package level. Each implements the
SimulationEngine ABC (from ``simulation.engine.interface``), except
MonteCarloAdapter which returns MonteCarloOutput and has its own interface.

Usage::

    from simulation.adapters import (
        TrainingAdapter,
        EvaluationAdapter,
        PaperDriver,
        ReplayDriver,
        MonteCarloAdapter,
        register_all_adapters,
        ADAPTER_KIND_TRAINING,
    )

    registry = AdapterRegistry()
    register_all_adapters(registry)
    engine = registry.get(ADAPTER_KIND_TRAINING)
    output = engine.run(sim_input)
"""

from __future__ import annotations

from simulation.adapters.training_adapter import TrainingAdapter
from simulation.adapters.evaluation_adapter import EvaluationAdapter
from simulation.adapters.paper_driver import PaperDriver
from simulation.adapters.replay_driver import ReplayDriver
from simulation.adapters.monte_carlo_adapter import MonteCarloAdapter
from simulation.adapters._validation import (
    validate_simulation_input,
    validate_simulation_output,
    validate_monte_carlo_output,
)
from simulation.engine.interface import (
    # Kind constants
    ADAPTER_KIND_TRAINING,
    ADAPTER_KIND_EVALUATION,
    ADAPTER_KIND_PAPER,
    ADAPTER_KIND_REPLAY,
    ADAPTER_KIND_MONTE_CARLO,
    STANDARD_ADAPTER_KINDS,
    # Registry
    AdapterRegistry,
    AdapterRegistryError,
    # Side-effect check
    SideEffectFreeCheck,
)

# Re-export for convenience
__all__ = [
    # Adapter classes
    "TrainingAdapter",
    "EvaluationAdapter",
    "PaperDriver",
    "ReplayDriver",
    "MonteCarloAdapter",
    # Registration
    "register_all_adapters",
    # Kind constants
    "ADAPTER_KIND_TRAINING",
    "ADAPTER_KIND_EVALUATION",
    "ADAPTER_KIND_PAPER",
    "ADAPTER_KIND_REPLAY",
    "ADAPTER_KIND_MONTE_CARLO",
    "STANDARD_ADAPTER_KINDS",
    # Registry
    "AdapterRegistry",
    "AdapterRegistryError",
    # Side-effect check
    "SideEffectFreeCheck",
    # Validation helpers
    "validate_simulation_input",
    "validate_simulation_output",
    "validate_monte_carlo_output",
]


def register_all_adapters(registry: AdapterRegistry) -> None:
    """Register all standard adapter instances in *registry*.

    Registers:
      - ``ADAPTER_KIND_TRAINING``  -> TrainingAdapter()
      - ``ADAPTER_KIND_EVALUATION`` -> EvaluationAdapter()
      - ``ADAPTER_KIND_PAPER``      -> PaperDriver()
      - ``ADAPTER_KIND_REPLAY``     -> ReplayDriver()

    MonteCarloAdapter is **not** registered because it does not implement
    the SimulationEngine ABC (its ``run()`` returns ``MonteCarloOutput``,
    not ``SimulationOutput``). To use Monte Carlo, import it directly::

        from simulation.adapters import MonteCarloAdapter
        mc = MonteCarloAdapter(n_perturbations=50)
        result = mc.run(sim_input)

    Args:
        registry: An ``AdapterRegistry`` instance.

    Raises:
        AdapterRegistryError: If any adapter kind is already registered.
    """
    registry.register(ADAPTER_KIND_TRAINING, TrainingAdapter())
    registry.register(ADAPTER_KIND_EVALUATION, EvaluationAdapter())
    registry.register(ADAPTER_KIND_PAPER, PaperDriver())
    registry.register(ADAPTER_KIND_REPLAY, ReplayDriver())
