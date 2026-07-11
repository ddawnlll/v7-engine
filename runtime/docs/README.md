# V4 Docs Index

`v4` is the active architecture track.

The `v4` plan keeps the React interface and moves the operational engine back to Python. The goal is a simpler, more operable system with one primary backend/runtime path.

## Start Here

- [./architecture.md](./architecture.md)
  Runtime component map and ownership boundaries.
- [./analyzer.md](./analyzer.md)
  Python analyzer and trade decision flow.
- [./learning.md](./learning.md)
  Adaptive learning, self-correction, and effectiveness tracking.
- [./api.md](./api.md)
  Current and target API contract baseline.
- [./schema.md](./schema.md)
  Current PostgreSQL schema baseline.
- [./runtime.md](./runtime.md)
  Scan loop and autonomous runtime flow.
- [./runbook.md](./runbook.md)
  Startup, DB, exchange, and stuck-scan recovery notes.

## Reference Material

- *Legacy v1 and v3 references (CURRENT_API_SURFACE, PERSISTENCE_POLICY, v3 README) from the original trading-bot repo have been superseded by the documents above and the V7 authority tree.*

## Intent

`v4` should:

- keep the existing operator interface
- restore one Python-first operational engine path
- keep PostgreSQL as the operational store
- keep MongoDB as the archive/artifact store
- reduce startup, debugging, and maintenance complexity
