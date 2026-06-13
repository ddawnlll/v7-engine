# V4 Docs Index

`v4` is the active architecture track.

The `v4` plan keeps the React interface and moves the operational engine back to Python. The goal is a simpler, more operable system with one primary backend/runtime path.

## Start Here

- [`/Users/hootie/src/trading-bot/v4/docs/architecture.md`](/Users/hootie/src/trading-bot/v4/docs/architecture.md)
  Target `v4` component map and ownership boundaries.
- [`/Users/hootie/src/trading-bot/TODO_V4.md`](/Users/hootie/src/trading-bot/TODO_V4.md)
  Active `v4` delivery plan.
- [`/Users/hootie/src/trading-bot/v4/docs/analyzer.md`](/Users/hootie/src/trading-bot/v4/docs/analyzer.md)
  Python analyzer and trade decision flow.
- [`/Users/hootie/src/trading-bot/v4/docs/learning.md`](/Users/hootie/src/trading-bot/v4/docs/learning.md)
  Adaptive learning, self-correction, and effectiveness tracking.
- [`/Users/hootie/src/trading-bot/v4/docs/api.md`](/Users/hootie/src/trading-bot/v4/docs/api.md)
  Current and target API contract baseline.
- [`/Users/hootie/src/trading-bot/v4/docs/schema.md`](/Users/hootie/src/trading-bot/v4/docs/schema.md)
  Current PostgreSQL schema baseline.
- [`/Users/hootie/src/trading-bot/v4/docs/runtime.md`](/Users/hootie/src/trading-bot/v4/docs/runtime.md)
  Scan loop and autonomous runtime flow.
- [`/Users/hootie/src/trading-bot/v4/docs/runbook.md`](/Users/hootie/src/trading-bot/v4/docs/runbook.md)
  Startup, DB, exchange, and stuck-scan recovery notes.

## Reference Material

- [`/Users/hootie/src/trading-bot/v1/CURRENT_API_SURFACE.md`](/Users/hootie/src/trading-bot/v1/CURRENT_API_SURFACE.md)
  Current Python API reference surface.
- [`/Users/hootie/src/trading-bot/v1/PERSISTENCE_POLICY.md`](/Users/hootie/src/trading-bot/v1/PERSISTENCE_POLICY.md)
  Existing persistence expectations and rules.
- [`/Users/hootie/src/trading-bot/v3/docs/README.md`](/Users/hootie/src/trading-bot/v3/docs/README.md)
  Archived `v3` Rust-first architecture notes.

## Intent

`v4` should:

- keep the existing operator interface
- restore one Python-first operational engine path
- keep PostgreSQL as the operational store
- keep MongoDB as the archive/artifact store
- reduce startup, debugging, and maintenance complexity
