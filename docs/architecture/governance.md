# governance.md — System Governance & Authority Model

## Purpose

This document defines the **root governance model** for the V7 Engine monorepo.
It specifies domain ownership, authority boundaries, conflict resolution,
contract governance, and import discipline.

Every domain authority doc (simulation/README.md, v7/docs/README.md, etc.)
must be consistent with this document. If a domain doc conflicts with this
document, this document wins for cross-domain rules; the domain doc wins for
domain-internal rules.

## Domain Ownership Table

| Domain | Owner | Owns | Must NOT Own |
|---|---|---|---|
| `lib/` | Shared Primitives | Market data client, indicators (ATR, returns, volatility, rolling), costs (fees, slippage), time (folds, intervals) | Regime, R-multiple semantics, IO/serialization, adapters, simulation, alphaforge, v7 |
| `simulation/` | Economic Truth Authority | SimulationInput/Output contracts, action family semantics (LONG_NOW/SHORT_NOW/NO_TRADE), profiles, costs, exits, horizons, path metrics, no-trade quality, Monte Carlo, lineage, golden tests | Runtime orchestration (v7), policy/risk interpretation (v7), TradeOutcome normalization (v7), training/research pipeline (alphaforge), dataset assembly (alphaforge), feature generation (alphaforge), model training (alphaforge), raw market data storage (data) |
| `alphaforge/` | Training/Research Authority | Labels, datasets, feature engineering, model training, calibration, evaluation, prediction schema | Simulation truth (simulation), runtime hosting (v7), raw market data service (lib) |
| `v7/` | Runtime/Semantic/Policy Authority | Runtime orchestration, execution, persistence, lifecycle, AnalysisRequest/Result, DecisionEvent, TradeOutcome, policy, risk, portfolio | Economic simulation truth (simulation), model training (alphaforge), feature engineering (alphaforge), market data service (lib) |
| `data/` | Canonical Data Root | Raw data, processed data, cache, results, models (storage only) | Computation, transformation logic, schema definitions |
| `contracts/` | Passive Contract Authority | Contract registry, compatibility matrix, JSON schemas, field mappings, minimal fixtures | Python code, implementation logic, runtime execution |
| `integration/` | Active Skeleton | Adapter stubs, cross-domain boundary tests, contract validation tests, schema parity tests | Domain implementation logic, simulation engine, model training, runtime execution |

## Conflict Resolution Order

When two authority documents conflict on the same concept:

1. **Root contracts/** — passive schemas and mappings define canonical field shapes.
2. **Domain README** — simulation/README.md, etc. define ownership boundaries.
3. **Domain contract docs** — simulation/docs/contracts.md, v7/docs/contracts/trade_outcome.md.
4. **Domain authoritative summary** — simulation/docs/ai_summary.md, etc.
5. **Implementation code** — the actual behavior (only when code exists).

For cross-domain conflicts, resolution steps:

1. Check `contracts/` for schema/mapping definitions.
2. Check `governance.md` (this file) for ownership rules.
3. Check domain-specific authority docs.
4. If still unresolved, raise a governance conflict issue.
5. The resolution must update `contracts/` schemas/mappings and this document.

## Contracts as Passive Authority

`contracts/` is the **passive root authority** for all cross-domain contract
objects. It defines what exists, who owns it, and how fields map between domains.

Rules:

- `contracts/` contains NO Python code.
- Every cross-domain contract object must have a registry entry in `registry.json`.
- Every cross-domain field mapping must be defined in `mappings/`.
- Compatibility rules between contract versions are in `compatibility.json`.
- Schema changes must follow the version bump rules defined in `compatibility.json`.
- `test_contract_registry.py` and `test_schema_parity.py` enforce these rules.

## Integration as Active Skeleton

`integration/` is the **active but minimal** cross-domain layer:

- Adapter stubs define interfaces between domains.
- Integration tests gate all future implementation.
- Adapters must NOT import domain internals.
- Real adapter implementation belongs to domain phases (simulation S3,
  alphaforge P2, v7 phase 2).

## Forbidden Import Relationships

The following import relationships are FORBIDDEN and enforced by
`integration/tests/test_cross_domain_boundaries.py`:

| From | Must NOT Import |
|---|---|
| `lib` | `simulation`, `alphaforge`, `v7` |
| `simulation` | `alphaforge`, `v7` |
| `alphaforge` | `simulation`, `v7` |
| `v7` | `simulation`, `alphaforge` |
| `integration/adapters` | `simulation`, `alphaforge`, `v7` |
| `contracts/` | Any Python code at all |

Allowed imports:

- All domains may import `lib` primitives.
- All domains may import stdlib and pip-installed packages.
- `integration/tests/` may read `contracts/` as data (JSON/Markdown files).
- Domains may reference `contracts/` schemas as data files (not Python imports).

## How Future Features Must Update Contracts and Tests

When a new feature is added that crosses domain boundaries:

1. Update or add JSON schemas in `contracts/schemas/`.
2. Update or add registry entries in `contracts/registry.json`.
3. Update compatibility rules in `contracts/compatibility.json`.
4. Update or add field mappings in `contracts/mappings/`.
5. Update or add fixtures in `contracts/fixtures/`.
6. Run `make check-contracts` — must pass.
7. Run `make check-boundaries` — must pass.
8. Run `make test-system` — must pass.
9. Run `make test-all` — must pass.

## Version Bump Policy

| Change | Version Bump | Example |
|---|---|---|
| New optional field added | MINOR | 1.0.0 → 1.1.0 |
| Field renamed or removed | MAJOR | 1.0.0 → 2.0.0 |
| Field semantics changed | MAJOR | 1.0.0 → 2.0.0 |
| New contract added | MINOR | 1.0.0 → 1.1.0 |
| Contract removed | MAJOR | 1.0.0 → 2.0.0 |

All version bumps must update `compatibility.json` compatibility rules.
