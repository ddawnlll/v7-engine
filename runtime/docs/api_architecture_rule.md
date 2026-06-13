# Runtime API Architecture Rule

## Purpose

This note defines the boundary that must hold before Phase 7 work continues.

The system has two separate layers:

1. a **public HTTP API** consumed by the interface and operators
2. an **internal analyzer engine boundary** consumed by runtime services

These layers must not be confused.

## Rule 1: Public API paths are capability-based, not engine-version-based

Public routes must describe what the system does, not which engine generation is active.

Allowed examples:

- `/api/v3/health`
- `/api/v3/analyze`
- `/api/v3/scans`
- `/api/v3/orders`
- `/api/v3/portfolio`
- future capability families like `/api/v3/review/*`, `/api/v3/operate/*`, `/api/v3/system/*`

Disallowed examples:

- `/v6/analyze`
- `/v6/decision-events`
- `/v6/engine-behavior`
- any public route that forces the client to know which internal engine generation is active

## Rule 2: Engine generation belongs in metadata, not in route namespaces

Engine identity may be surfaced through payload fields such as:

- `engine_name`
- `engine_version`
- `model_artifact_version`
- `fallback_used`
- `fallback_reason`
- `comparison_group_id`

That information is useful for diagnostics, review, and observability.
It is not a route versioning strategy.

## Rule 3: `/api/v3/*` remains the compatibility contract

The existing interface and tests already depend on `/api/v3/*`.
That remains the canonical compatibility surface until a migration-safe alias strategy is intentionally introduced.

If versionless aliases are added later, they must:

- map to the same handlers
- preserve response contracts
- not replace `/api/v3/*` abruptly

## Rule 4: Engine switching is internal

The active engine must be selected internally through runtime services such as:

- `AnalyzerEngineAdapter`
- `AnalyzerEngineRegistryService`
- engine manager / registry / config

The frontend must not be responsible for switching base paths by engine generation.

## Rule 5: The adapter is the normalization boundary

`runtime/services/analyzer_engine_adapter.py` is the compatibility boundary between:

- runtime and route consumers that need stable analysis payloads
- engine implementations that may evolve independently

The adapter may validate, translate, fallback, shadow, and normalize.
Public routes should depend on normalized outputs rather than engine-native structures.

## Rule 6: Future Phase 7 routes must be capability-centered

Future review and operate routes should be introduced under capability-oriented families, for example:

- `/api/v3/review/*`
- `/api/v3/operate/*`
- `/api/v3/system/*`

These may coexist with current routes by using aliases or read-model wrappers.
They must not introduce engine-generation namespaces as the primary public contract.

## Immediate implication for Phase 7 planning

Any document or prompt that proposes public `/v6/*` endpoints must be treated as outdated architectural guidance.
Those endpoints should instead be mapped onto:

- existing `/api/v3/*` surfaces,
- new capability-based `/api/v3/...` families, or
- internal engine/service boundaries.
