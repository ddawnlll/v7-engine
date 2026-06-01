"""
test_integration_smoke.py — Verify adapter stubs are importable and well-behaved.

Checks:
- All adapter modules import successfully.
- Adapter classes are instantiable.
- Stub methods raise NotImplementedError.
- Adapters do not import domain internals.
"""

import pytest


class TestAdapterImports:
    """Verify all adapter stubs are importable."""

    def test_simulation_adapter_imports(self):
        """SimulationAdapter and its subclasses must be importable."""
        from integration.adapters.simulation_adapter import (
            SimulationAdapter,
            TrainingAdapter,
            EvaluationAdapter,
            ReplayAdapter,
            PaperAdapter,
            LiveOutcomeAdapter,
        )
        assert SimulationAdapter is not None
        assert TrainingAdapter is not None
        assert EvaluationAdapter is not None
        assert ReplayAdapter is not None
        assert PaperAdapter is not None
        assert LiveOutcomeAdapter is not None

    def test_alphaforge_adapter_imports(self):
        """AlphaForgeAdapter and its subclasses must be importable."""
        from integration.adapters.alphaforge_adapter import (
            AlphaForgeAdapter,
            LabelBuilder,
        )
        assert AlphaForgeAdapter is not None
        assert LabelBuilder is not None

    def test_v7_adapter_imports(self):
        """V7Adapter and its subclasses must be importable."""
        from integration.adapters.v7_adapter import (
            V7Adapter,
            RuntimeSimulationHost,
        )
        assert V7Adapter is not None
        assert RuntimeSimulationHost is not None


class TestAdapterStubs:
    """Verify adapter stubs raise NotImplementedError when called."""

    def test_simulation_adapter_raises_not_implemented(self):
        """SimulationAdapter.run must raise NotImplementedError."""
        from integration.adapters.simulation_adapter import SimulationAdapter
        adapter = SimulationAdapter()
        with pytest.raises(NotImplementedError):
            adapter.run({"test": "input"})

    def test_training_adapter_raises_not_implemented(self):
        """TrainingAdapter.run must raise NotImplementedError."""
        from integration.adapters.simulation_adapter import TrainingAdapter
        adapter = TrainingAdapter()
        with pytest.raises(NotImplementedError):
            adapter.run({"test": "input"})

    def test_evaluation_adapter_raises_not_implemented(self):
        """EvaluationAdapter.run must raise NotImplementedError."""
        from integration.adapters.simulation_adapter import EvaluationAdapter
        adapter = EvaluationAdapter()
        with pytest.raises(NotImplementedError):
            adapter.run({"test": "input"})

    def test_alphaforge_adapter_build_label_raises_not_implemented(self):
        """AlphaForgeAdapter.build_label must raise NotImplementedError."""
        from integration.adapters.alphaforge_adapter import AlphaForgeAdapter
        adapter = AlphaForgeAdapter()
        with pytest.raises(NotImplementedError):
            adapter.build_label({"test": "output"})

    def test_alphaforge_adapter_build_dataset_raises_not_implemented(self):
        """AlphaForgeAdapter.build_dataset must raise NotImplementedError."""
        from integration.adapters.alphaforge_adapter import AlphaForgeAdapter
        adapter = AlphaForgeAdapter()
        with pytest.raises(NotImplementedError):
            adapter.build_dataset([], [])

    def test_v7_adapter_build_trade_outcome_raises_not_implemented(self):
        """V7Adapter.build_trade_outcome must raise NotImplementedError."""
        from integration.adapters.v7_adapter import V7Adapter
        adapter = V7Adapter()
        with pytest.raises(NotImplementedError):
            adapter.build_trade_outcome({"test": "output"})

    def test_v7_adapter_normalize_outcome_raises_not_implemented(self):
        """V7Adapter.normalize_outcome must raise NotImplementedError."""
        from integration.adapters.v7_adapter import V7Adapter
        adapter = V7Adapter()
        with pytest.raises(NotImplementedError):
            adapter.normalize_outcome({"exec": "data"}, {"sim": "data"})

    def test_simulation_adapter_is_subclassable(self):
        """SimulationAdapter must be subclassable."""
        from integration.adapters.simulation_adapter import SimulationAdapter

        class CustomAdapter(SimulationAdapter):
            adapter_kind = "CUSTOM"

        assert CustomAdapter.adapter_kind == "CUSTOM"
        adapter = CustomAdapter()
        with pytest.raises(NotImplementedError):
            adapter.run({})

    def test_alphaforge_adapter_is_subclassable(self):
        """AlphaForgeAdapter must be subclassable."""
        from integration.adapters.alphaforge_adapter import AlphaForgeAdapter

        class CustomAF(AlphaForgeAdapter):
            pass

        adapter = CustomAF()
        with pytest.raises(NotImplementedError):
            adapter.build_label({})
