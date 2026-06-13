# V4 API

This document defines how the `v4` Python backend should bind to the React interface quickly, with minimal contract overhead.

The goal is not to design a large API platform. The goal is to expose a stable, documented interface contract so the backend can replace the `v3` engine without rewriting the UI.

## Binding Strategy

`v4` should use:

- FastAPI
- Pydantic request and response models
- built-in OpenAPI generation

This gives three things immediately:

- one typed backend contract
- automatic validation
- OpenAPI schema at runtime without a separate contract system

The intended workflow is:

1. define Pydantic models in Python
2. expose FastAPI routes
3. keep the interface fetch layer thin
4. generate TypeScript types from OpenAPI later only if useful

This is the standardization layer. No extra gateway or schema registry is needed.

## Versioning Rule

For speed, `v4` should keep the interface route namespace under:

- `/api/v3/*`

This is a compatibility choice, not an architectural statement.

Reason:

- the current interface already expects `/api/v3/*`
- keeping the route prefix avoids a large frontend rename during the backend rewrite
- the engine can change without forcing the UI to change first

Internally, this is still the `v4` backend.

## API Shape Rule

The API should be page-oriented, not storage-oriented.

That means:

- return page-ready payloads when practical
- avoid forcing the frontend to stitch together many endpoints just to render one screen
- keep raw lower-level endpoints only when they are genuinely reusable

Good:

- `GET /api/v3/dashboard`
- `GET /api/v3/market/overview`
- `GET /api/v3/portfolio`

Bad:

- one page calling 7 endpoints and rebuilding legacy state client-side

## Contract Rule

The backend owns the final response shape.

The frontend should not:

- reconstruct dashboard aggregates
- fabricate counters
- infer missing state from unrelated endpoints
- treat placeholder zeros as real data

The frontend should:

- render the backend’s typed response
- show empty states explicitly
- show degraded states explicitly

## FastAPI And OpenAPI

The recommended `v4` API setup is:

- FastAPI app in `v4/api/main.py`
- route modules in `v4/api/routes/*.py`
- Pydantic models in `v4/api/models/*.py`

FastAPI should expose:

- OpenAPI JSON: `/openapi.json`
- Swagger UI: `/docs`
- ReDoc: `/redoc`

That is enough standardization for this project.

Optional later step:

- generate TypeScript types from `/openapi.json`

That should be a convenience step, not a prerequisite for backend work.

## Route Groups

The interface should bind to a small set of clear route groups.

### Health And Runtime

- `GET /api/v3/health`
- `GET /api/v3/engine/health`
- `GET /api/v3/calibration/status`
- `GET /api/v3/learning/profile`
- `GET /api/v3/learning/effectiveness`
- `GET /api/v3/settings`
- `POST /api/v3/settings`

Purpose:

- process health
- DB health
- exchange health
- runtime settings
- calibration readiness counts for persisted labeled outcomes
- adaptive learning profile, calibration buckets, and effectiveness status

### Dashboard

- `GET /api/v3/dashboard`

Purpose:

- one response for the dashboard page

Expected contents:

- top-level KPIs
- recent scans
- market movers
- alerts summary
- runtime summary

The dashboard page should not rebuild this from several unrelated endpoints.

### Markets

- `GET /api/v3/market/overview`
- `GET /api/v3/market/signals`
- `GET /api/v3/klines`
- `GET /api/v3/analyze`

Purpose:

- market list
- ranked signals
- chart candles
- one-shot analyzer output for selected market and mode

Current analyzer response highlights:

- `direction`
- `confidence`
- `probability`
- `probability_up`
- `probability_down`
- `expected_value`
- `regime`
- `trend`
- `risk_reward`
- `summary`
- `snapshot`
- `advanced_analysis`

### Scans

- `GET /api/v3/scans`
- `POST /api/v3/scans`
- `GET /api/v3/scans/control`
- `POST /api/v3/scans/control/pause`
- `POST /api/v3/scans/control/resume`
- `POST /api/v3/scans/control/stop`
- `GET /api/v3/jobs`

Purpose:

- list persisted scan runs
- start manual scan
- inspect active scan control state
- pause the active scan cooperatively
- resume a paused scan
- stop the active scan cooperatively
- inspect background job state when needed

Rule:

- scan actions must update visible UI state through persisted backend records
- not through optimistic placeholder counters
- pause and stop are cooperative; the runtime checks control state between symbol/interval/mode tasks
- list responses now include a top-level `control` block with the active run id, active status, desired state, and current task

### Orders And Portfolio

- `GET /api/v3/orders`
- `GET /api/v3/portfolio`
- `GET /api/v3/paper/balance`

Optional action routes:

- `POST /api/v3/orders`
- `PATCH /api/v3/orders/{order_id}`
- `POST /api/v3/orders/{order_id}/close`
- `POST /api/v3/paper/deposit`
- `POST /api/v3/paper/reset`
- `POST /api/v3/paper/reconcile`

Purpose:

- order ledger
- open positions
- equity and realized performance
- paper cash balance and budget control
- one-time reconciliation of legacy open paper trades that never reserved cash

### Failure Analysis

- `GET /api/v3/failures`
- `GET /api/v3/failures/{order_id}`
- `GET /api/v3/failures/summary`
- `GET /api/v3/failures/weakness-profile`

Admin aliases:

- `GET /api/admin/failures`
- `GET /api/admin/failures/{order_id}`
- `GET /api/admin/failures/summary`
- `GET /api/admin/failures/weakness-profile`

Purpose:

- list persisted trade failure classifications
- filter failures by `failure_source`, `blamed_component`, `severity_score`, and date range
- fetch the classified failure record for one order
- aggregate counts and averages for operator dashboards
- rank the most damaging recurring weakness patterns

List query parameters:

- `limit`
- `offset`
- `failure_source`
- `blamed_component`
- `severity_score`
- `date_from`
- `date_to`

Summary response includes:

- counts per `failure_source`
- counts per `blamed_component`
- average `severity_score`
- average `confidence`
- `top_weakness` grouped by source and blamed component

Weakness profile query parameters:

- `lookback_days` default `30`
- `min_confidence` default `0.6`

Weakness profile includes:

- `generated_at`
- `lookback_days`
- `total_losses_analyzed`
- `top_failure_source`
- `top_blamed_component`
- `ranked_sources`
- `ranked_components`

Ranking rule:

- source and component groups are ranked by `count × avg_severity_score`
- each group surfaces the highest-confidence `improvement` suggestion

### Learning

- `GET /api/v3/learning/profile`
- `GET /api/v3/learning/effectiveness`

Admin aliases:

- `GET /api/admin/learning/profile`
- `GET /api/admin/learning/effectiveness`

Purpose:

- expose the active adaptive learning profile
- show confidence calibration buckets
- show top penalties and active adjustments
- report whether each adjustment is improving or degrading outcomes

`/learning/profile` includes:

- `active`
- `sample_size`
- `top_penalties`
- `calibration_data`
- `effectiveness_summary`
- full `profile`

`/learning/effectiveness` includes:

- per-adjustment status
- adjusted vs baseline counts
- average `R` delta
- win-rate delta
- overall health score

Portfolio response highlights now include:

- `summary.today_pnl`
- `summary.today_pnl_pct`
- `summary.three_day_pnl`
- `summary.three_day_pnl_pct`
- `summary.performance_windows.today`
- `summary.performance_windows.three_day`

### Simulations

- no active simulation routes are bound in the current interface

Purpose:

- the interface route is explicitly disabled until the v4 simulation backend is reimplemented

### Storage And Admin

- `GET /api/v3/storage/status`
- `POST /api/v3/storage/export`
- `POST /api/v3/storage/import`
- `POST /api/v3/storage/seed`
- `GET /api/v3/alerts`
- `GET /api/v3/operator/alerts`
- `GET /api/v3/logs`

Purpose:

- operational storage inspection
- backup and restore actions
- development seeding
- operator alerts
- runtime logs

## Minimal Page Binding Map

This is the intended interface-to-backend mapping.

### Dashboard page

Primary route:

- `GET /api/v3/dashboard`

### Markets page

Primary routes:

- `GET /api/v3/market/overview`
- `GET /api/v3/market/signals`
- `GET /api/v3/klines`
- `GET /api/v3/analyze`

### Scans page

Primary routes:

- `GET /api/v3/scans`
- `POST /api/v3/scans`
- `GET /api/v3/scans/control`
- `POST /api/v3/scans/control/pause`
- `POST /api/v3/scans/control/resume`
- `POST /api/v3/scans/control/stop`

Secondary:

- `GET /api/v3/jobs`

### Trades / Orders page

Primary route:

- `GET /api/v3/orders`

### Portfolio page

Primary route:

- `GET /api/v3/portfolio`

Supporting paper-budget route:

- `GET /api/v3/paper/balance`

### Simulations page

Current state:

- explicitly disabled in the interface until the v4 simulation backend is implemented

### Storage page

Primary routes:

- `GET /api/v3/storage/status`
- `POST /api/v3/storage/export`
- `POST /api/v3/storage/import`
- `POST /api/v3/storage/seed`

### Admin page

Primary routes:

- `GET /api/v3/engine/health`
- `GET /api/v3/scans`
- `GET /api/v3/alerts`
- `GET /api/v3/operator/alerts`
- `GET /api/v3/logs`
- `GET /api/v3/settings`
- `POST /api/v3/settings`
- `GET /api/v3/paper/balance`
- `POST /api/v3/paper/deposit`
- `POST /api/v3/paper/reset`

### Alerts page

Primary route:

- `GET /api/v3/alerts`

## Final Interface Map

This is the current page-to-route mapping after the integration sweep.

- Dashboard: `GET /api/v3/dashboard`
- Markets: `GET /api/v3/market/overview`, `GET /api/v3/market/signals`, `GET /api/v3/klines`, `GET /api/v3/analyze`
- Scans: `GET /api/v3/scans`, `POST /api/v3/scans`
- Trades: `GET /api/v3/orders`
- Portfolio: `GET /api/v3/portfolio`, `GET /api/v3/paper/balance`
- Admin: `GET /api/v3/engine/health`, `GET /api/v3/scans`, `GET /api/v3/alerts`, `GET /api/v3/logs`, `GET /api/v3/settings`, `POST /api/v3/settings`, `GET /api/v3/paper/balance`, `POST /api/v3/paper/deposit`, `POST /api/v3/paper/reset`
- Alerts: `GET /api/v3/alerts`
- Storage: `GET /api/v3/storage/status`, `POST /api/v3/storage/export`, `POST /api/v3/storage/import`, `POST /api/v3/storage/seed`
- Logs: `GET /api/v3/logs`, `GET /api/v3/scans`, `GET /api/v3/dashboard`
- Simulations: disabled in the interface until the backend contract exists

## Response Modeling Rules

Each route should have an explicit Pydantic response model.

Examples:

- `DashboardResponse`
- `MarketOverviewResponse`
- `SignalListResponse`
- `ScanRunListResponse`
- `PortfolioResponse`
- `OrderListResponse`
- `StorageStatusResponse`
- `EngineHealthResponse`

Rules:

- response models should match what the page needs to render
- avoid optional chaos when the page always expects a field
- use explicit empty arrays instead of omitted fields
- use explicit degraded-state fields instead of silent partial failure

## Error Handling Rules

The API should make degraded behavior visible.

Use:

- `200` with explicit degraded fields when partial data is still useful
- `4xx` for bad client input
- `5xx` for real backend failures

Examples:

- storage status can return a healthy Postgres section and an explicit degraded state
- dashboard can return partial data only if the degraded state is explicit in the payload

The interface should never have to guess whether zeros mean:

- empty state
- degraded state
- failure

## What Not To Build

Do not add:

- GraphQL
- a second gateway layer
- a separate contract service
- a custom code generation pipeline before the backend is working
- a microservice split for routine page data

The system only needs one Python backend with a stable typed interface.

## Implementation Rule For Speed

When choosing between two endpoint designs:

- prefer the one that lets the interface bind directly with less client-side shaping

When choosing between two contract systems:

- prefer the built-in FastAPI and Pydantic path

When choosing whether to rename routes:

- keep `/api/v3/*` until the backend replacement is stable

## Recommended First Deliverables

The first backend routes to implement for interface binding should be:

1. `GET /api/v3/health`
2. `GET /api/v3/settings`
3. `POST /api/v3/settings`
4. `GET /api/v3/dashboard`
5. `GET /api/v3/market/overview`
6. `GET /api/v3/klines`
7. `GET /api/v3/analyze`
8. `GET /api/v3/scans`
9. `POST /api/v3/scans`
10. `GET /api/v3/orders`
11. `GET /api/v3/portfolio`

This is the shortest path to making the interface usable with the new backend.
