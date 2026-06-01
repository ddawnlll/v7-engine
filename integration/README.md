# integration/ — Cross-Domain Active Skeleton

## Purpose

This directory is the **active but minimal** integration layer for the
V7 Engine monorepo. It provides:

1. **Adapter stubs** — interface definitions for cross-domain communication
   between simulation, alphaforge, and v7. Stubs raise `NotImplementedError`
   until real implementation phases complete.
2. **Integration tests** — contract registry validation, schema parity
   checks, cross-domain import boundary enforcement, and adapter smoke tests.

## Adapter Stubs

All adapters live under `adapters/` and follow these rules:

- **Importable** without importing simulation, alphaforge, or v7 source code.
- **Side-effect-free** — no live execution effects.
- **Deterministic** — same input produces same output.
- **NotImplementedError** — all stub methods raise this until real
  implementation phases.

| Adapter | File | Purpose | Real Implementation Phase |
|---|---|---|---|
| `SimulationAdapter` | `simulation_adapter.py` | Wrap simulation engine for training/eval/replay/paper/live | simulation S3 |
| `AlphaForgeAdapter` | `alphaforge_adapter.py` | Consume simulation outputs into labels/datasets | alphaforge P2 |
| `V7Adapter` | `v7_adapter.py` | Host simulation and normalize TradeOutcome records | v7 phase 2 |

## Tests

All tests live under `tests/`:

| Test File | Validates |
|---|---|
| `test_contract_registry.py` | contracts/registry.json integrity, schema file existence, fixture existence |
| `test_schema_parity.py` | Cross-domain field mapping correctness between SimulationOutput, AlphaForgeLabel, TradeOutcome |
| `test_cross_domain_boundaries.py` | Import boundary enforcement for all 5 domain pairs |
| `test_integration_smoke.py` | Adapter stubs are importable and raise NotImplementedError |

Run all integration tests:

```bash
make test-system
```

Or directly:

```bash
python -m pytest integration/tests/ -v
```

## Adding New Adapters

1. Create a new adapter stub in `adapters/`.
2. Follow the stub pattern: importable, side-effect-free, raises NotImplementedError.
3. Must NOT import from simulation, alphaforge, or v7.
4. Add smoke tests in `tests/test_integration_smoke.py`.
5. Update this README.

## Adding New Integration Tests

1. Add test file in `tests/`.
2. Follow existing patterns: use stdlib only, no new dependencies.
3. Update `Makefile` targets if the test should be included in `make test-system`.
