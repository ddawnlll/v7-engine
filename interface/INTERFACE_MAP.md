# Interface Architecture Update

This document replaces the old page inventory with a rework plan for the V4 interface.

The current UI has three structural problems:

1. Control surfaces are duplicated.
   `Admin` owns runtime settings and execution controls, while `Settings` owns local interface preferences. Both are called "settings" in practice, which creates operator confusion.
2. Analysis is fragmented.
   Scan diagnostics, performance diagnostics, failure analytics, learning analytics, and dashboard summaries each expose partial engine truth with overlapping KPIs and repeated cards.
3. The shell is overloaded.
   `App.tsx`, `Navbar.tsx`, and several route files each own too much data loading and too many responsibilities.

This update defines a cleaner information architecture, component ownership model, and migration path.

## 1. Goals

- separate operator controls from personal UI preferences
- reduce the number of top-level destinations
- stop repeating the same engine metrics across multiple pages
- make each page answer one primary question
- push data ownership down to feature modules instead of the app shell
- make future engine work (`v5`, registry-based engines, shadow mode, gate metrics) fit naturally into the interface

## 2. Current State

## 2.1 Routing

Current workspaces from [workspaces.ts](/Users/hootie/src/trading-bot/interface/src/lib/workspaces.ts):

- `Trading`
  - `Dashboard`
  - `Markets`
  - `Scans`
  - `Trades`
  - `Portfolio`
- `Intelligence`
  - `Failures`
  - `Analytics`
  - `Learning`
  - `Performance`
- `Operations`
  - `Admin`
  - `Alerts`
  - `Logs`
  - `Settings`
- `Data`
  - `Storage`
- `Lab`
  - `Simulations`

This is already grouped better than the original flat nav, but it still leaves the operator with too many parallel destinations.

## 2.2 Shell Ownership Problems

Current shell in [App.tsx](/Users/hootie/src/trading-bot/interface/src/App.tsx):

- fetches health, jobs, alerts, portfolio, settings, symbols, breaker state
- computes navbar props
- owns route registration
- acts as an implicit global dashboard cache

Problems:

- shell-level queries are too broad
- route pages become dependent on top-nav data contracts
- adding a new workspace or engine metric tends to expand `App.tsx`

Current navbar in [Navbar.tsx](/Users/hootie/src/trading-bot/interface/src/components/navigation/Navbar.tsx):

- mixes navigation, alerts, command palette, refresh, scan-now, engine status, queue status, breaker status, and theme toggle

Problem:

- it is both navigation and operator control center

## 2.3 Page-Level Ownership Problems

### Admin

Current [AdminRoute.tsx](/Users/hootie/src/trading-bot/interface/src/routes/AdminRoute.tsx) owns:

- queue controls
- scan controls
- runtime settings
- learning presets
- circuit breaker controls
- paper balance controls
- failure / learning / calibration summaries
- alerts-adjacent information

Problem:

- `Admin` is effectively a mixed runtime cockpit, settings editor, budget console, and diagnostics page

### Settings

Current [SettingsRoute.tsx](/Users/hootie/src/trading-bot/interface/src/routes/SettingsRoute.tsx) owns:

- terminology mode
- number precision
- time format
- dashboard refresh interval
- KPI delta window
- debug display preferences

Problem:

- the page is technically "personal preferences", but the name `Settings` conflicts with runtime settings in `Admin`

### Dashboard

Current [DashboardRoute.tsx](/Users/hootie/src/trading-bot/interface/src/routes/DashboardRoute.tsx):

- queue posture
- engine health
- recent failures
- recent events
- refresh controls
- handoff summaries

Problem:

- it mixes executive summary, event feed, runtime health, and operator actions

### Scans / Analytics / Failures / Learning / Performance

Problems across these pages:

- repeated confidence / suppression / failure metrics
- scan diagnostics split across several places
- no single canonical "engine audit" surface
- no clear separation between:
  - live execution monitoring
  - historical scan audit
  - model / learning evaluation

## 3. Target Information Architecture

The interface should be reduced to four product areas:

1. `Trade`
   Live operation and market decision surfaces.
2. `Review`
   Historical audits, failures, performance, and learning analysis.
3. `Operate`
   Runtime controls, queue controls, alerts, logs, and system state.
4. `System`
   Data management, simulations, and personal preferences.

Recommended top-level navigation:

- `Trade`
- `Review`
- `Operate`
- `System`

## 3.1 Proposed Route Map

### Trade

- `/trade/overview`
  - replaces current `Dashboard`
  - live operator snapshot only
- `/trade/markets`
  - current `Markets`
- `/trade/scans`
  - current `Scans`
- `/trade/trades`
  - current `Trades`
- `/trade/portfolio`
  - current `Portfolio`

### Review

- `/review/engine/performance`
  - cross-run decision quality
  - calibration, suppression value, rescue value, expectancy
- `/review/engine/behavior`
  - mechanical correctness
  - fallback, timeout, timing, threshold-gap, shadow comparison
- `/review/failures`
  - current `FailureAnalytics`
- `/review/learning`
  - current `SelfLearningRoute`
- `/review/experiments`
  - optional future home for simulation comparisons if lab output becomes decision-relevant

### Operate

- `/operate/control`
  - replaces `Admin`
  - queue control, scan control, runtime control, breaker control
- `/operate/alerts`
  - current `Alerts`
- `/operate/logs`
  - current `Logging`
- `/operate/config`
  - runtime config only
  - moved out of `Admin`

### System

- `/system/preferences`
  - replaces current `Settings`
  - purely local UI preferences
- `/system/storage`
  - current `Storage`
- `/system/simulations`
  - current `Simulations`

## 3.2 Page Naming Rules

- `Preferences` means local UI-only choices
- `Config` means runtime / backend settings
- `Control` means actions that change live execution state
- `Review` pages are read-heavy and historical
- `Trade` pages are action-heavy and current-state focused

This removes the current "two settings pages" ambiguity.

## 4. Canonical Page Responsibilities

## 4.1 Trade Overview

Primary question:

`What needs operator attention right now?`

Allowed content:

- engine health summary
- queue health summary
- breaker state
- next scan state
- open risk posture
- recent critical alerts
- latest scan outcome summary

Not allowed:

- full settings editors
- deep failure analytics
- long-form event audit tables
- duplicate per-stage suppression charts already owned by review pages

Priority order on Trade Overview:

1. Critical alerts
   shown as banner, never buried in a list
2. Breaker state
   can the system trade or is it halted
3. Engine health
   is the active engine healthy, and has it fallen back recently
4. Queue state
   what is running, queued, blocked, or stuck
5. Open risk
   current exposure and posture
6. Last scan outcome
   did the latest scan emit, skip, stall, or fail

Anything below priority 6 belongs in `Review` or `Operate`, not here.

## 4.2 Trade Scans

Primary question:

`What happened in this scan run, and why did it emit or skip signals?`

Owned here:

- scan list
- scan detail
- skip breakdown
- per-symbol drill-down
- drill-down export
- compact summary export

Not owned here:

- cross-run performance benchmarking
- learning model validation
- generic runtime health cards

## 4.3 Review Engine Performance

Primary question:

`Is the engine making good decisions across runs?`

Owned here:

- win rate
- expectancy delta
- trade frequency delta
- suppression accuracy
- rescue accuracy
- calibration curve
- AUC and evaluation metrics
- per-regime quality breakdown
- model version history

This page is about decision quality, not runtime mechanics.

It should absorb the quality-oriented parts of:

- `Analytics`
- `Performance`
- parts of `Learning`

## 4.4 Review Engine Behavior

Primary question:

`Is the engine behaving correctly mechanically?`

Owned here:

- fallback rate
- timeout rate
- gate disagreement rate
- threshold gap distribution
- shadow comparison report
- analyzer timing
- scan funnel
- circuit breaker event history
- engine version behavior comparisons

This page is about system behavior, not model quality.

It should absorb the behavior-oriented parts of:

- `Analytics`
- `Performance`
- parts of `Scans`
- parts of `Admin`

## 4.5 Operate Control

Primary question:

`Can the operator safely change live runtime behavior right now?`

Owned here:

- pause / resume / stop / force stop
- scan now
- manual queue actions
- breaker reset and breaker mode
- paper balance controls
- engine registry table
- engine activation toggle
- shadow engine selector
- promote button with confirmation modal
- rollback button with reason modal
- circuit breaker manual reset
- engine activation / shadow controls when registry work lands

Not owned here:

- long-form runtime setting forms
- local UI preferences
- failure intelligence
- shadow evidence reports

Promotion and rollback are action surfaces. They live here.

The evidence used to justify promotion lives in `Review Engine Behavior`, not on this page.

## 4.6 Operate Config

Primary question:

`What runtime configuration is active, and what can be safely changed?`

Owned here:

- runtime settings editor
- grouped config sections
- presets
- validation warnings
- save audit trail
- environment / engine metadata

Config groups should be explicit:

- `Execution`
- `Risk`
- `Universe`
- `Learning`
- `Circuit Breaker`
- `Paper Trading`
- `Engine Binding`

The current `Admin` settings tab should be moved here.

## 4.7 System Preferences

Primary question:

`How should this interface behave for this user on this machine?`

Owned here:

- theme
- terminology mode
- number precision
- time format
- auto-refresh preference
- developer UI toggles

It should never expose runtime engine behavior.

## 5. Component Architecture

## 5.1 Layer Model

The interface should follow this structure:

- `app`
  - router
  - providers
  - shell
- `features`
  - route-owned business modules
- `entities`
  - reusable domain renderers
- `shared`
  - generic UI, formatting, export, table utilities

Translated to this repo:

- `src/app`
  - future home for `App.tsx`, router, workspace shell, navbar shell
- `src/features`
  - `scan-review`
  - `runtime-control`
  - `runtime-config`
  - `engine-review`
  - `trade-portfolio`
  - `market-analysis`
- `src/entities`
  - `job`
  - `signal`
  - `trade`
  - `alert`
  - `engine`
- `src/shared`
  - current `components/ui`
  - `lib/format`
  - `lib/export`
  - generic hooks

## 5.2 Route File Rules

Route files should become composition files, not implementation dumps.

A route file should only:

- read route params / search params
- assemble feature sections
- own page-level layout
- avoid large helper-function blocks

A route file should not:

- contain 20+ formatting helper functions
- define export serializers inline
- define domain transformations inline
- contain large settings catalogs inline

Current candidates for splitting:

- [AdminRoute.tsx](/Users/hootie/src/trading-bot/interface/src/routes/AdminRoute.tsx)
- [ScansRoute.tsx](/Users/hootie/src/trading-bot/interface/src/routes/ScansRoute.tsx)
- [DashboardRoute.tsx](/Users/hootie/src/trading-bot/interface/src/routes/DashboardRoute.tsx)

## 5.3 Query Ownership Rules

Current issue:

- app shell and route files both fetch overlapping data

Target rule:

- app shell fetches only shell-critical data:
  - current alert count
  - breaker state summary
  - next scan timestamp
  - engine label/version
- pages fetch their own detail data
- shared feature hooks own the query contracts for their domain

Examples:

- `useShellStatusQuery()`
- `useRuntimeControlQuery()`
- `useScanRunQuery(runId)`
- `useScanTraceQuery(runId)`
- `useEngineReviewQuery(filters)`
- `useRuntimeConfigQuery()`

## 5.4 Navigation Rules

Navbar should be simplified to:

- top-level workspace switching
- global alerts indicator
- theme / user preference access
- command palette entry

Move out of navbar:

- `Scan now`
- heavy runtime status ribbons
- dense queue metrics
- fallback counters

Those belong in `Trade Overview` or `Operate Control`.

## 5.5 Data Freshness Model

Polling and staleness must be intentional per area.

- shell-critical data
  - examples: alert summary, breaker state summary, active engine label/version, next scan timestamp
  - refresh every `15s`
  - never treated as long-lived stale data
- Trade Overview
  - refresh every `30s`
  - optimized for live operator posture
- Trade pages outside overview
  - refresh on mount, then use page-specific cadence only where necessary
- Review pages
  - refresh on mount
  - manual refresh only afterward
  - these are historical and should not poll continuously
- Operate Control
  - refresh every `10s`
  - optimistic updates on actions
- Operate Config
  - load once on mount
  - refetch after successful save
- System Preferences
  - no polling
  - local state only

Suggested hooks:

- `useShellStatusQuery()`
- `useTradeOverviewQuery()`
- `useOperateControlQuery()`
- `useRuntimeConfigQuery()`
- `useEnginePerformanceReviewQuery()`
- `useEngineBehaviorReviewQuery()`

## 5.6 Navbar Specification

Navbar contents are fixed:

- four workspace tabs only
  - `Trade`
  - `Review`
  - `Operate`
  - `System`
- alerts badge
  - shows count of `CRITICAL` alerts
  - hover or click popover shows top 3 alerts
  - links to `/operate/alerts`
- theme toggle
- command palette trigger

Explicitly forbidden in the navbar:

- scan controls
- queue metrics
- engine status ribbon
- fallback counters
- refresh controls
- scan-now button
- breaker controls
- paper account actions

## 6. Domain Consolidation

## 6.1 Settings Split

The split must be explicit:

- `Preferences`
  - local only
  - stored in browser / local machine
- `Runtime Config`
  - backend settings
  - affects trading behavior

No page should mix the two.

## 6.2 Analytics Split

Three distinct analytics concerns exist today and should stop overlapping:

### Scan Audit

- per-run drill-down
- skip reasons
- emitted signals
- scan exports

Owner:

- `Trade Scans`

### Engine Review

- engine quality metrics
- engine behavior metrics
- shadow comparison evidence
- calibration and gate metrics

Owner:

- `Review Engine Performance`
- `Review Engine Behavior`

### Failure Review

- losses
- missed opportunities
- weakness patterns
- improvement suggestions

Owner:

- `Review Failures`

## 6.3 Learning Split

Learning views should be split into:

- `Review Learning`
  - model quality, calibration, suppression value, rescue value
- `Operate Config`
  - learning-related flags and thresholds

Do not combine learning evaluation with live operator controls.

## 7. Proposed File Reorganization

This does not need to happen all at once, but this is the target shape:

```text
interface/src/
  app/
    AppShell.tsx
    router.tsx
    providers/
  features/
    trade-overview/
    market-analysis/
    scan-review/
    trade-ledger/
    portfolio-review/
    engine-review/
    failure-review/
    learning-review/
    runtime-control/
    runtime-config/
    system-preferences/
    storage-admin/
    simulations/
  entities/
    alert/
    engine/
    job/
    signal/
    trade/
  shared/
    ui/
    hooks/
    lib/
```

## 8. Migration Plan

## Phase 0: Metric ownership audit

- audit every metric that appears on more than one page
- assign a single canonical owner to each metric
- create a metric ownership table before code changes
- remove any metric from pages that are not its owner

This phase prevents the refactor from merely moving duplication around.

## Phase 1: Clarify naming and ownership

- rename `Settings` page to `Preferences`
- move runtime settings UI out of `Admin` into a dedicated `Runtime Config` page
- keep routes working with redirects

## Phase 2: Reduce shell weight

- extract shell query hook from `App.tsx`
- reduce navbar to navigation + global status only
- move `scan now` and runtime controls out of navbar

## Phase 3: Split oversized routes into features

- split `AdminRoute.tsx` into:
  - `runtime-control`
  - `runtime-config`
- split `ScansRoute.tsx` into:
  - scan list
  - scan detail
  - trace / skip review
  - exports
- split `DashboardRoute.tsx` into:
  - live posture
  - queue health
  - recent alerts
  - operator handoff

## Phase 4: Consolidate analytics

- merge duplicated quality metrics into `Review Engine Performance`
- merge duplicated behavior metrics into `Review Engine Behavior`
- remove repeated KPI cards from pages that do not own them
- keep scan pages run-specific and review pages cross-run

## Phase 5: Prepare for engine registry and v5

- add engine selector/status surfaces to `Operate Control`
- add engine registry table to `Operate Control`
- add shadow/gate comparison evidence to `Review Engine Behavior`
- keep all v5-specific analytics in `Review`, not `Trade`

## 9. Immediate Fixes

These should happen first because they remove the most confusion:

1. Rename current `Operations > Settings` to `Preferences`.
2. Create `Operations > Runtime Config` and move runtime settings out of `Admin`.
3. Remove duplicated engine metric cards from `Admin` once `Review Engine Performance` and `Review Engine Behavior` exist.
4. Move `Scan now` out of the navbar into `Operate Control` and `Trade Overview`.
5. Consolidate scan/engine/failure KPIs so each metric has one canonical owner.

## 10. Definition of Done

The interface rework is successful when:

- operators no longer ask which settings page changes trading behavior
- each top-level page answers one main question
- the navbar is navigation-first, not cockpit-first
- `App.tsx` no longer owns broad domain data loading
- no route file acts as both page and feature library
- analytics metrics have one canonical home
- engine registry and v5 shadow flows fit into the UI without adding one-off pages
- no metric card appears on more than one page
- `Review Engine` is split into `Performance` and `Behavior`
- promote and rollback actions live in `Operate Control`
- shadow evidence lives in `Review Engine Behavior`
- navbar contains exactly four workspace tabs, alerts badge, theme toggle, and command palette trigger
- data freshness behavior is implemented and documented per area

## 11. Recommended First Implementation Slice

If this rework is done incrementally, start here:

1. Introduce new route names:
   - `Operate > Control`
   - `Operate > Config`
   - `System > Preferences`
2. Move runtime settings UI out of `AdminRoute.tsx`.
3. Rename the current preferences page.
4. Strip navbar controls down to navigation and indicators.
5. Create new `Review Engine Performance` and `Review Engine Behavior` pages and migrate duplicated metrics into them.

That sequence fixes the highest-friction problems first without requiring a full rewrite in one pass.
