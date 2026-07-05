"""
Shared validation helpers for simulation adapters.

Cross-cutting validation logic shared by all adapters. Keeps individual
adapter files focused on their specific concerns.

No dependency on v7, alphaforge, runtime, or interface.
"""

from __future__ import annotations

from simulation.contracts.models import SimulationInput, SimulationOutput, MonteCarloOutput


def validate_simulation_input(input: SimulationInput) -> list[str]:
    """Validate a SimulationInput, returning list of error messages.

    If the input is valid, returns an empty list.
    """
    errors: list[str] = []

    if not input.symbol or not input.symbol.strip():
        errors.append("symbol must be non-empty")

    if input.entry_price <= 0:
        errors.append("entry_price must be positive")

    if input.atr <= 0:
        errors.append("atr must be positive")

    if not input.decision_timestamp:
        errors.append("decision_timestamp must be non-empty")

    if not input.future_path or not input.future_path.candles:
        errors.append("future_path must contain at least one candle")

    if not input.profile:
        errors.append("profile must be set")

    if not input.mode:
        errors.append("mode must be set")

    if not input.primary_interval:
        errors.append("primary_interval must be non-empty")

    return errors


def validate_simulation_output(output: SimulationOutput) -> list[str]:
    """Validate a SimulationOutput, returning list of error messages."""
    errors: list[str] = []

    if not output.simulation_run_id:
        errors.append("simulation_run_id must be non-empty")

    if not output.symbol:
        errors.append("symbol must be non-empty")

    if not output.decision_timestamp:
        errors.append("decision_timestamp must be non-empty")

    valid_resolutions = {"COMPLETE", "UNRESOLVED", "INVALIDATED"}
    if output.resolution_status not in valid_resolutions:
        errors.append(
            f"resolution_status must be one of {valid_resolutions}, "
            f"got '{output.resolution_status}'"
        )

    valid_actions = {"LONG_NOW", "SHORT_NOW", "NO_TRADE", "AMBIGUOUS_STATE"}
    if output.best_action not in valid_actions:
        errors.append(
            f"best_action must be one of {valid_actions}, "
            f"got '{output.best_action}'"
        )

    if output.long_outcome is None:
        errors.append("long_outcome must not be None")

    if output.short_outcome is None:
        errors.append("short_outcome must not be None")

    if output.no_trade_outcome is None:
        errors.append("no_trade_outcome must not be None")

    if not output.lineage.adapter_kind:
        errors.append("lineage.adapter_kind must be non-empty")

    return errors


def validate_monte_carlo_output(output: MonteCarloOutput) -> list[str]:
    """Validate a MonteCarloOutput, returning list of error messages."""
    errors: list[str] = []

    if not output.monte_carlo_run_id:
        errors.append("monte_carlo_run_id must be non-empty")

    if output.baseline_output is None:
        errors.append("baseline_output must not be None")

    if not output.perturbed_outputs:
        errors.append("perturbed_outputs must not be empty")

    if not output.perturbation_params:
        errors.append("perturbation_params must be non-empty")

    if not output.aggregate_stats:
        errors.append("aggregate_stats must be non-empty")

    # Validate underlying simulation outputs
    base_errors = validate_simulation_output(output.baseline_output)
    errors.extend(f"baseline_output.{e}" for e in base_errors)

    for i, po in enumerate(output.perturbed_outputs):
        po_errors = validate_simulation_output(po)
        errors.extend(f"perturbed_outputs[{i}].{e}" for e in po_errors)

    return errors
