"""Simulation engine — comparative path simulation, exits, costs, interface."""

from simulation.engine.interface import (
    ADAPTER_KIND_EVALUATION,
    ADAPTER_KIND_MONTE_CARLO,
    ADAPTER_KIND_PAPER,
    ADAPTER_KIND_REPLAY,
    ADAPTER_KIND_TRAINING,
    STANDARD_ADAPTER_KINDS,
    AdapterRegistry,
    AdapterRegistryError,
    SideEffectFreeCheck,
    SimulationEngine,
)

__all__ = [
    "ADAPTER_KIND_EVALUATION",
    "ADAPTER_KIND_MONTE_CARLO",
    "ADAPTER_KIND_PAPER",
    "ADAPTER_KIND_REPLAY",
    "ADAPTER_KIND_TRAINING",
    "STANDARD_ADAPTER_KINDS",
    "AdapterRegistry",
    "AdapterRegistryError",
    "SideEffectFreeCheck",
    "SimulationEngine",
]
