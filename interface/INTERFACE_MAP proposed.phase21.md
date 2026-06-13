# Interface Map Proposed for Phase 21

This document records the Phase 21 interface audit and the proposed information architecture used for the regrouped workspace model.

It is intentionally interface-only:
- no backend route changes
- no schema changes
- no runtime changes
- no response reshaping

## 1. Current Interface Audit

### Current top-level routes

- `/dashboard`
- `/markets`
- `/portfolio`
- `/trades`
- `/analytics`
- `/failures`
- `/performance`
- `/scans`
- `/admin`
- `/alerts`
- `/logs`
- `/settings`
- `/storage`
- `/simulations`

### Current nav clutter

The previous navigation was flat and page-per-feature:
- primary nav mixed operator work with analysis work
- related pages were split apart at top level
- low-frequency pages sat beside daily-use pages
- future additions would have kept increasing top-level sprawl

### Current page role classification

#### Primary operator surfaces

- `Dashboard`
- `Markets`
- `Scans`
- `Trades`
- `Portfolio`

#### Secondary analysis surfaces

- `Failures`
- `Analytics`
- `Performance`

#### Admin / operational control surfaces

- `Admin`
- `Alerts`
- `Logs`
- `Settings`

#### Storage / data management surfaces

- `Storage`

#### Experimental / low-frequency surfaces

- `Simulations`

### Current page overlap

#### Dashboard vs Markets

- `Dashboard` is monitoring-first
- `Markets` is symbol analysis and decision support
- they belong to the same operator workspace, not separate top-level concepts

#### Admin vs Alerts

- both are operational control and system-state views
- `Alerts` is a narrower operational subset
- keeping them separate at top level made the mental model worse

#### Failures vs Learning vs Analytics

- all are intelligence surfaces
- `Failures` explains why trades lost
- `Analytics` explains where edge exists
- `Performance` explains runtime/scan timing behavior
- these belong together under one analysis-oriented workspace

#### Trades vs signal / audit drilldowns

- `Trades` is still the right main ledger
- but audit-heavy drilldowns are intelligence-oriented
- Phase 21 keeps the trade ledger under Trading while preserving direct links into Intelligence surfaces

### Current task mapping

#### Monitoring

- `Dashboard`
- `Scans`
- `Portfolio`
- `Admin`
- `Alerts`

#### Action-taking

- `Markets`
- `Scans`
- `Trades`
- `Admin`
- `Storage`

#### Diagnosis

- `Failures`
- `Analytics`
- `Performance`
- `Logs`
- `Trades`

#### Configuration

- `Admin`
- `Settings`
- `Storage`

#### Research

- `Simulations`
- `Failures`
- `Analytics`

### Pages that should not stay top-level

- `Performance`
- `Alerts`
- `Logs`
- `Settings`
- `Storage`
- `Simulations`

These are still useful, but they are not strong enough as independent top-level destinations.

### Pages too large to merge directly

- `Admin`
- `Trades`
- `Scans`

These are large and should remain dedicated pages inside a parent workspace, not be force-merged into one screen.

## 2. Proposed Information Architecture

### Top-level workspaces

- `Trading`
- `Intelligence`
- `Operations`
- `Data`
- `Lab`

### Naming rationale

Domain names are clearer than feature names because they tell the operator what kind of work happens there:
- `Trading` = live activity and execution-facing work
- `Intelligence` = analyzer insight and edge diagnosis
- `Operations` = runtime control, health, and administrative actions
- `Data` = persistence, reset, export/import, and storage state
- `Lab` = experimental and low-frequency research

This scales better than adding a new top-level page every time a subsystem is introduced.

### Workspace grouping

#### Trading

- `Dashboard`
- `Markets`
- `Scans`
- `Trades`
- `Portfolio`

#### Intelligence

- `Failures`
- `Analytics`
- `Performance`

Future fit:
- learning-specific views
- audit-specific drilldowns

#### Operations

- `Admin`
- `Alerts`
- `Logs`
- `Settings`

Future fit:
- circuit breaker admin surface
- runtime/health subviews

#### Data

- `Storage`

Future fit:
- export/import
- seed/reset
- data status

#### Lab

- `Simulations`

Decision:
- `Lab` remains exposed, but only as a low-frequency workspace instead of a primary operator destination

## 3. Final Route Grouping

### Workspace routes

- `/trading/dashboard`
- `/trading/markets`
- `/trading/scans`
- `/trading/trades`
- `/trading/portfolio`

- `/intelligence/failures`
- `/intelligence/analytics`
- `/intelligence/performance`

- `/operations/admin`
- `/operations/alerts`
- `/operations/logs`
- `/operations/settings`

- `/data/storage`

- `/lab/simulations`

### Compatibility redirects

Old routes remain reachable through redirects:

- `/dashboard` → `/trading/dashboard`
- `/markets` → `/trading/markets`
- `/scans` → `/trading/scans`
- `/trades` → `/trading/trades`
- `/portfolio` → `/trading/portfolio`
- `/failures` → `/intelligence/failures`
- `/analytics` → `/intelligence/analytics`
- `/performance` → `/intelligence/performance`
- `/admin` → `/operations/admin`
- `/alerts` → `/operations/alerts`
- `/logs` → `/operations/logs`
- `/settings` → `/operations/settings`
- `/storage` → `/data/storage`
- `/simulations` → `/lab/simulations`

Search params and hashes are preserved by the compatibility redirects.

## 4. Navigation Consolidation Decision

### Chosen navigation model

- top nav = domain-level workspaces
- workspace page header = sub-navigation tabs
- `More` menu = page-level shortcuts

### Why this model

- keeps the top nav stable
- reduces page sprawl
- preserves direct page access
- avoids inventing another permanent side rail
- works with existing page implementations and route structure

## 5. UX Consistency Rules for Phase 21

- all grouped workspace pages use a shared workspace shell
- each workspace gets:
  - title
  - description
  - tab navigation
- deep page implementations stay intact inside that shell
- old deep links still resolve
- drilldown links continue to work because legacy routes redirect into the grouped structure

## 6. Expected Operator Benefits

- fewer top-level concepts to scan
- clearer separation between:
  - trading activity
  - analyzer intelligence
  - operational controls
  - data tools
- future pages can be added inside a workspace instead of expanding the top nav
- page discovery improves because related pages now sit beside each other

## 7. Phase 21 Deliverables

- written interface audit
- proposed IA document
- final route/group mapping
- grouped workspace shell
- updated top navigation
- compatibility redirect list
- rationale for naming and grouping choices
