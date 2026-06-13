# Interface AI Summary — Machine-Readable Authority Reference

## META

This document is a lossless dense synthesis of every documentation file in `/interface/`. It is designed for LLM code agents and AI-assisted engineering workflows. It is **NOT** for human reading. The entire interface doc set has been compressed into this single reference preserving all architecture decisions, workspace structure, page ownership rules, component layer model, migration plans, and current-state analysis.

**Reading order for an AI:** Read this entire file first. Then consult specific authority docs for implementation details. This file is authoritative only where it directly quotes or faithfully restates authority docs; in case of conflict, the original doc wins.

**File count synthesized:** 5 documentation files
**Source tree:** /home/erfolg/src/v7-engine/interface/

### Cross-Domain Authority Notice

This document is the **interface-local** authority summary for the React + TypeScript + Vite operator UI.

- The root cross-domain contract authority lives in **`contracts/`** at the repo root.
- The root cross-domain governance lives in **`docs/architecture/governance.md`**.
- For the backend API surface consumed by this interface: see **`runtime/docs/ai_summary.md`** (R.7 API Surface, R.6 Route Groups).
- For V7-local pipeline semantics: see **`v7/docs/ai_summary.md`**.
- For simulation truth semantics (stop/target/horizon/fee/slippage): see **`simulation/docs/ai_summary.md`**.
- For the repo-wide entry point: see **`ai_summary.md`** at the repo root.

The V4 interface has been promoted into the V7 authority tree. Cross-doc links within this tree still reference the legacy V4 layout (e.g. `/Users/hootie/src/trading-bot/interface/...`); those are legacy anchors awaiting path normalization.

---

## I.1 Interface README (interface/README.md)

The interface is a **React + TypeScript + Vite** project. It uses React Compiler for build/performance optimization. ESLint with type-aware lint rules is configured via `eslint.config.js`. Testing uses Vitest.

**Stack:**
- React 18+ with React Compiler
- TypeScript (strict mode via `tsconfig.app.json`)
- Vite (dev server + build)
- Vitest (unit testing)
- ESLint with `typescript-eslint` recommended configs

**Source layout:** `interface/src/{App.tsx, main.tsx, index.css, assets, components, contexts, hooks, lib, modules, routes, test}`.

---

## I.2 Current Information Architecture (interface/INTERFACE_MAP.md + interface-current-state-report.md)

### Current Workspace Structure (`interface/src/lib/workspaces.ts`)

```
Trading
  Dashboard
  Markets
  Scans
  Trades
  Portfolio
Intelligence
  Failures
  Analytics
  Learning
  Performance
Operations
  Admin
  Alerts
  Logs
  Settings
Data
  Storage
Lab
  Simulations
```

### Assessment
The workspace model is already a strong improvement over the original flat nav. It gives the interface a coherent top-level mental model — but the actual data ownership inside the shell and some pages still behaves more like an older monolithic admin UI.

### Current Shell Ownership Problems

**`App.tsx`** fetches at shell level: engine health, jobs, operator alerts, portfolio, runtime settings, symbols, circuit breaker state. This makes it a hidden global dashboard controller. Route-specific concerns bleed into shell concerns. Shell payload contracts expand over time.

`App.tsx` owns too much:
- Engine health, jobs, alerts, portfolio, settings, symbols, breaker state
- Computes navbar props
- Owns route registration
- Acts as an implicit global dashboard cache

**`Navbar.tsx`** mixes: workspace navigation, status display, scan trigger, refresh action, alerts panel, command palette, theme toggle, engine/circuit/queue information. It is both navigation and operator control center.

**`WorkspaceShell.tsx`** is clean and reusable — provides workspace title, description, and icon.

### Current Page-Level Ownership Problems

| Page | Problem |
|---|---|
| **Admin** | Mixed runtime cockpit, settings editor, budget console, and diagnostics page |
| **Settings** | Named "settings" but is personal preferences; name conflicts with runtime settings in Admin |
| **Dashboard** | Mixes executive summary, event feed, runtime health, and operator actions |
| **Scans / Analytics / Failures / Learning / Performance** | Repeated confidence/suppression/failure metrics; scan diagnostics split across places; no single canonical "engine audit" surface |

---

## I.3 Target Information Architecture

### Four Product Areas

1. **Trade** — Live operation and market decision surfaces
2. **Review** — Historical audits, failures, performance, and learning analysis
3. **Operate** — Runtime controls, queue controls, alerts, logs, and system state
4. **System** — Data management, simulations, and personal preferences

### Proposed Route Map

#### Trade
- `/trade/overview` — replaces Dashboard; live operator snapshot only
- `/trade/markets` — current Markets
- `/trade/scans` — current Scans
- `/trade/trades` — current Trades
- `/trade/portfolio` — current Portfolio

#### Review
- `/review/engine/performance` — cross-run decision quality, calibration, suppression value, rescue value, expectancy
- `/review/engine/behavior` — mechanical correctness, fallback, timeout, timing, threshold-gap, shadow comparison
- `/review/failures` — current FailureAnalytics
- `/review/learning` — current SelfLearningRoute
- `/review/experiments` — optional future home for simulation comparisons

#### Operate
- `/operate/control` — replaces Admin; queue control, scan control, runtime control, breaker control
- `/operate/alerts` — current Alerts
- `/operate/logs` — current Logging
- `/operate/config` — runtime config only (moved out of Admin)

#### System
- `/system/preferences` — replaces Settings; purely local UI preferences
- `/system/storage` — current Storage
- `/system/simulations` — current Simulations

### Page Naming Rules
- `Preferences` = local UI-only choices
- `Config` = runtime / backend settings
- `Control` = actions that change live execution state
- `Review` pages = read-heavy and historical
- `Trade` pages = action-heavy and current-state focused

---

## I.4 Canonical Page Responsibilities

### Trade Overview
**Primary question:** *What needs operator attention right now?*
Allowed: engine health summary, queue health summary, breaker state, next scan state, open risk posture, recent critical alerts, latest scan outcome summary.
**Not allowed:** full settings editors, deep failure analytics, long-form event audit tables, duplicate per-stage suppression charts.
**Priority order:** (1) Critical alerts (banner, never buried), (2) Breaker state, (3) Engine health, (4) Queue state, (5) Open risk, (6) Last scan outcome.

### Trade Scans
**Primary question:** *What happened in this scan run, and why did it emit or skip signals?*
Owns: scan list, scan detail, skip breakdown, per-symbol drill-down, drill-down export, compact summary export.
**Not owned:** cross-run performance benchmarking, learning model validation, generic runtime health cards.

### Review Engine Performance
**Primary question:** *Is the engine making good decisions across runs?*
Owns: win rate, expectancy delta, trade frequency delta, suppression accuracy, rescue accuracy, calibration curve, AUC and evaluation metrics, per-regime quality breakdown, model version history.
**Absorbs quality-oriented parts of:** Analytics, Performance, Learning.

### Review Engine Behavior
**Primary question:** *Is the engine behaving correctly mechanically?*
Owns: fallback rate, timeout rate, gate disagreement rate, threshold gap distribution, shadow comparison report, analyzer timing, scan funnel, circuit breaker event history, engine version behavior comparisons.
**Absorbs behavior-oriented parts of:** Analytics, Performance, Scans, Admin.

### Operate Control
**Primary question:** *Can the operator safely change live runtime behavior right now?*
Owns: pause/resume/stop/force stop, scan now, manual queue actions, breaker reset and breaker mode, paper balance controls, engine registry table, engine activation toggle, shadow engine selector, promote/rollback buttons with confirmation modals.
**Not owned:** long-form runtime setting forms, local UI preferences, failure intelligence, shadow evidence reports.

### Operate Config
**Primary question:** *What runtime configuration is active, and what can be safely changed?*
Owns: runtime settings editor, grouped config sections, presets, validation warnings, save audit trail, environment/engine metadata.
Config groups: `Execution`, `Risk`, `Universe`, `Learning`, `Circuit Breaker`, `Paper Trading`, `Engine Binding`.

### System Preferences
**Primary question:** *How should this interface behave for this user on this machine?*
Owns: theme, terminology mode, number precision, time format, auto-refresh preference, developer UI toggles.
**Must never expose runtime engine behavior.**

---

## I.5 Proposed Component Architecture

### Layer Model
```
app/
  router, providers, shell
features/
  route-owned business modules (scan-review, runtime-control, runtime-config, engine-review, trade-portfolio, market-analysis)
entities/
  reusable domain renderers (job, signal, trade, alert, engine)
shared/
  generic UI, formatting, export, table utilities
```

### Target File Layout
```
interface/src/
  app/AppShell.tsx, router.tsx, providers/
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
    alert/, engine/, job/, signal/, trade/
  shared/
    ui/, hooks/, lib/
```

### Route File Rules
Route files should become **composition files, not implementation dumps**. A route file should only:
- Read route params / search params
- Assemble feature sections
- Own page-level layout
- Avoid large helper-function blocks

Candidates for splitting: `AdminRoute.tsx`, `ScansRoute.tsx`, `DashboardRoute.tsx`.

### Query Ownership Rules
- App shell fetches only shell-critical data: current alert count, breaker state summary, next scan timestamp, engine label/version
- Pages fetch their own detail data
- Shared feature hooks own the query contracts for their domain

Examples: `useShellStatusQuery()`, `useRuntimeControlQuery()`, `useScanRunQuery(runId)`, `useScanTraceQuery(runId)`, `useEngineReviewQuery(filters)`, `useRuntimeConfigQuery()`.

### Navbar Specification
Fixed contents:
- Four workspace tabs only: `Trade`, `Review`, `Operate`, `System`
- Alerts badge (count of CRITICAL alerts, hover/popover shows top 3, links to `/operate/alerts`)
- Theme toggle
- Command palette trigger

**Explicitly forbidden in navbar:** scan controls, queue metrics, engine status ribbon, fallback counters, refresh controls, scan-now button, breaker controls, paper account actions.

### Data Freshness Model
| Area | Refresh Cadence |
|---|---|
| Shell-critical data (alert summary, breaker state, engine label, next scan) | Every 15s, never treated as long-lived stale |
| Trade Overview | Every 30s |
| Trade pages outside overview | On mount + page-specific cadence |
| Review pages | On mount + manual refresh only (historical, no polling) |
| Operate Control | Every 10s, optimistic updates on actions |
| Operate Config | Once on mount, refetch after successful save |
| System Preferences | No polling, local state only |

---

## I.6 Domain Consolidation Plans

### Settings Split
- **Preferences** = local only, stored in browser/local machine
- **Runtime Config** = backend settings, affects trading behavior
- No page may mix the two

### Analytics Split (three distinct concerns)
1. **Scan Audit** — per-run drill-down, skip reasons, emitted signals, exports → owned by `Trade Scans`
2. **Engine Review** — quality metrics, behavior metrics, shadow comparison, calibration/gate metrics → owned by `Review Engine Performance` + `Review Engine Behavior`
3. **Failure Review** — losses, missed opportunities, weakness patterns, improvement suggestions → owned by `Review Failures`

### Learning Split
- **Review Learning** — model quality, calibration, suppression value, rescue value
- **Operate Config** — learning-related flags and thresholds
- Never combine learning evaluation with live operator controls

---

## I.7 Migration Plan

### Phase 0: Metric ownership audit
- Audit every metric appearing on more than one page
- Assign one canonical owner per metric
- Create metric ownership table before code changes

### Phase 1: Clarify naming and ownership
- Rename `Settings` → `Preferences`
- Move runtime settings UI out of `Admin` into dedicated `Runtime Config` page
- Keep routes working with redirects

### Phase 2: Reduce shell weight
- Extract shell query hook from `App.tsx`
- Reduce navbar to navigation + global status only
- Move `scan now` and runtime controls out of navbar

### Phase 3: Split oversized routes into features
- Split `AdminRoute.tsx`: `runtime-control` + `runtime-config`
- Split `ScansRoute.tsx`: scan list, scan detail, trace/skip review, exports
- Split `DashboardRoute.tsx`: live posture, queue health, recent alerts, operator handoff

### Phase 4: Consolidate analytics
- Merge duplicated quality metrics into `Review Engine Performance`
- Merge duplicated behavior metrics into `Review Engine Behavior`
- Remove repeated KPI cards from non-owner pages
- Keep scan pages run-specific, review pages cross-run

### Phase 5: Prepare for engine registry and V5+
- Add engine selector/status surfaces to `Operate Control`
- Add engine registry table to `Operate Control`
- Add shadow/gate comparison evidence to `Review Engine Behavior`
- Keep V5-specific analytics in `Review`, not `Trade`

---

## I.8 Immediate Fixes (Highest Priority)

1. Rename current `Operations > Settings` to `Preferences`
2. Create `Operations > Runtime Config` and move runtime settings out of `Admin`
3. Remove duplicated engine metric cards from `Admin` once `Review` pages exist
4. Move `Scan now` out of navbar into `Operate Control` and `Trade Overview`
5. Consolidate scan/engine/failure KPIs so each metric has one canonical owner

---

## I.9 Definition of Done

The interface rework is successful when:
- Operators no longer ask which settings page changes trading behavior
- Each top-level page answers one main question
- Navbar is navigation-first, not cockpit-first
- `App.tsx` no longer owns broad domain data loading
- No route file acts as both page and feature library
- Analytics metrics have one canonical home
- Engine registry and V5 shadow flows fit without one-off pages
- No metric card appears on more than one page
- `Review Engine` is split into `Performance` and `Behavior`
- Promote/rollback actions live in `Operate Control`
- Shadow evidence lives in `Review Engine Behavior`
- Navbar contains exactly four workspace tabs, alerts badge, theme toggle, command palette trigger
- Data freshness behavior is implemented and documented per area

---

## I.10 Current-State Weaknesses (interface-current-state-report.md)

### Remaining Structural Issues
1. **Global shell ownership still too heavy** — App.tsx and Navbar.tsx still load/display too much global state
2. **Execution UI still paper-centric** — Portfolio and trades assume single-account paper worldview
3. **Profile-awareness does not exist** — No concept of `paper profile`, `binance profile`, or `bybit profile` in navigation, data contracts, or display state
4. **Page intent cleaner but not fully enforced** — Overlap between overview, control, config, and analytics surfaces persists
5. **Interface ready for profile-aware evolution** — But needs explicit backend fields and UI contract cleanup first

### Overall Assessment
> The interface is a good operational foundation, but before live execution lands it needs a profile-aware execution model and some shell/data-contract cleanup.

---

## I.11 Adjacent Interface Documents

| Document | Purpose |
|---|---|
| `interface/INTERFACE_MAP_proposed.md` | Phase 21 proposal: reduces top-level page sprawl into 6 workspaces (Trading, Intelligence, Operations, Data, Research, Preferences) |
| `interface/INTERFACE_MAP proposed.phase21.md` | Earlier rework proposal iteration |
| `interface/interface-current-state-report.md` | Current-state audit report (2026-04-23) with shell analysis, page ownership review, and evolution recommendations |

---

## END OF INTERFACE AI SUMMARY

This document contains the complete lossless synthesis of every documentation file in `/interface/`. Every architecture decision, workspace structure, page ownership rule, component layer model, migration plan phase, and current-state finding has been preserved.

**When to use this file:**
- Initial AI context loading for any interface work
- Quick reference for route design rules, page ownership, data freshness cadences
- Understanding the target architecture before implementing UI changes
- Cross-checking migration phase dependencies

**When to consult original docs:**
- When implementing specific route files or feature modules
- When the summary's condensed form loses nuance
- For exact component file paths, TypeScript types, or test configurations

**Canonical file paths for original interface docs:**
- interface/README.md
- interface/INTERFACE_MAP.md
- interface/INTERFACE_MAP_proposed.md
- interface/INTERFACE_MAP proposed.phase21.md
- interface/interface-current-state-report.md
