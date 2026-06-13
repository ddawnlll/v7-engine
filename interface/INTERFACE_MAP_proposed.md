# Proposed Interface Map — Phase 21

This document proposes a new `v4` interface map for **Phase 21**.

It is not a backend refactor map.
It is an **interface information architecture proposal** intended to reduce top-level page sprawl, clarify operator intent, and make future pages easier to place without continuously widening navigation. It is based on the current interface map and should be treated as a design direction for regrouping existing surfaces into larger workspaces. 

---

## 1. Phase 21 Design Objective

The current interface has many strong individual pages, but too many of them compete as first-class destinations:

* Dashboard
* Markets
* Portfolio
* Performance
* Trades
* Failures
* Scans
* Admin
* Simulations
* Storage
* Alerts
* Logs
* Settings

This is workable for development, but it does not scale well as more intelligence, learning, audit, and analytics surfaces are added. The next phase should therefore **reduce top-level navigation width** and regroup pages into a smaller number of domain-level workspaces. 

---

## 2. Proposed Top-Level Workspaces

The proposed interface should collapse the current flat page structure into these top-level workspaces:

* `Trading`
* `Intelligence`
* `Operations`
* `Data`
* `Research`
* `Preferences`

These should become the stable top-level destinations.

### Why this grouping

* `Trading` = live operator workflow
* `Intelligence` = understanding analyzer behavior and trade quality
* `Operations` = controlling runtime, alerts, and engine state
* `Data` = storage, exports, logs, and operational inspection
* `Research` = simulations and future experimental tooling
* `Preferences` = personal UI settings only

This gives the interface fewer first-level choices while still preserving all current capabilities. 

---

## 3. Proposed Top-Level Navigation

### Primary navigation

* Trading
* Intelligence
* Operations
* Data
* Research

### Utility / profile area

* Preferences
* Alerts indicator
* Theme toggle
* Command palette

### Remove from top-level direct nav

The following should no longer be first-level standalone destinations:

* Dashboard
* Markets
* Portfolio
* Performance
* Trades
* Failures
* Scans
* Admin
* Simulations
* Storage
* Logs
* Settings

These become workspace tabs or utility routes instead. 

---

## 4. Proposed Workspace Structure

## 4.1 Trading

**Purpose:**
The active operating surface for market review, scans, trade execution review, and portfolio state.

**Recommended route:**
`/trading`

**Tabs:**

* `Overview`
* `Markets`
* `Scans`
* `Trades`
* `Portfolio`

### Tab details

#### Overview

Replaces the current `Dashboard` as the default landing tab for trading activity.

Contains:

* hero / control room summary
* queue metric cards
* queue health strip
* operator handoff
* top movers / market movers
* important runtime status summary
* recent scan/trade highlights

This makes the dashboard clearly part of the trading workflow instead of a separate product area. 

#### Markets

Carries over the current `MarketsRoute`.

Contains:

* focused analysis header
* confidence / regime / direction summary
* market context
* order flow
* signal factors
* watchlist
* top match block
* trade plan and oscillator pulse
* heatmap
* analysis history

#### Scans

Carries over the current `ScansRoute`.

Contains:

* top summary cards
* trigger timeline
* scan list / grouped runs
* selected scan detail
* per-symbol drill-down

#### Trades

Carries over the current `TradesRoute`.

Contains:

* trade ledger header
* summary cards
* filters
* sort controls
* trade detail panel
* execution reasons
* timing progress
* loss/failure linkage
* future audit linkage

#### Portfolio

Carries over the current `PortfolioRoute`.

Contains:

* hero stat row
* KPI grid
* detail tabs
* performance and consistency sections
* open positions table
* holding / symbol breakdowns

---

## 4.2 Intelligence

**Purpose:**
The analyzer understanding surface — why trades fail, what works, how learning is adapting, and how signals were formed.

**Recommended route:**
`/intelligence`

**Tabs:**

* `Failures`
* `Performance`
* `Learning`
* `Audit`

This workspace should become the home for both current failure analysis and future Phase 20 trade analytics.

### Tab details

#### Failures

Uses the current `FailureAnalyticsRoute`.

Contains:

* stat card row
* source breakdown
* component breakdown
* source × component heatmap
* severity distribution
* top improvement suggestions
* recent analyzed losses

#### Performance

This is where **Phase 20** should live.

Contains:

* best trade modes
* worst trade modes
* best setup patterns
* worst setup patterns
* timing analytics
* symbol breakdowns
* regime breakdowns
* confidence bucket performance
* recommendations / edge ranking

This should replace the need for a separate top-level `Analytics` page.

#### Learning

Pulls learning-related material out of Admin concentration.

Contains:

* learning status
* confidence calibration
* active adjustments
* top penalties
* adjustment effectiveness
* calibration readiness
* future learning health summaries

This gives learning its own analysis home instead of burying it inside runtime operations. 

#### Audit

Reserved for signal explainability and replay surfaces from future phases.

Contains:

* signal audit detail
* factor scores
* threshold checks
* before/after learning confidence
* adjustment history
* circuit state at signal time
* trade-linked audit drilldown

This prevents signal explainability from becoming yet another top-level page later.

---

## 4.3 Operations

**Purpose:**
The runtime control center for engine operation, safety controls, operator actions, and alert handling.

**Recommended route:**
`/operations`

**Tabs:**

* `Overview`
* `Queue`
* `Budget`
* `Settings`
* `Alerts`
* `Safety`

This workspace absorbs the current `Admin`, `Alerts`, and future circuit breaker controls.

### Tab details

#### Overview

Reuses the strongest parts of `AdminRoute > Overview`.

Contains:

* persistent status bar
* queue metric cards
* scan controls
* engine runtime
* compact activity log
* health summaries
* quick operational actions

#### Queue

Pulls from `AdminRoute > Scan queue`.

Contains:

* queue overview cards
* active scan state
* daily cap warning
* mode availability panel
* scan builder
* job table

#### Budget

Pulls from `AdminRoute > Paper budget`.

Contains:

* paper budget summary
* deposit paper funds
* reset paper balance
* reconcile legacy open trades
* confidence sizing curve

#### Settings

Uses runtime/engine settings from current `AdminRoute > Settings`.

Contains:

* settings summary cards
* strategy mode roster
* unsaved changes banner
* risk / execution / filters / engine groups

This remains clearly separated from personal UI preferences.

#### Alerts

Absorbs the current standalone `AlertsRoute` and `AdminRoute > Alerts`.

Contains:

* alert list
* alert breakdown
* severity/status filters
* operator acknowledgement actions if needed

This removes the duplication of alerts existing both as a separate page and as an Admin sub-area. 

#### Safety

Reserved for future operational safety tooling.

Contains:

* circuit breaker status
* event history
* reset controls
* degraded/open state detail
* threshold settings

This is the correct future home for Phase 19 circuit breaker UI.

---

## 4.4 Data

**Purpose:**
Operational data management, export tools, raw payload inspection, and storage controls.

**Recommended route:**
`/data`

**Tabs:**

* `Storage`
* `Exports`
* `Logs`
* `State`

This workspace combines the current Storage and Logging surfaces into one data-oriented area.

### Tab details

#### Storage

Uses the current `StorageRoute`.

Contains:

* current DB state
* seed/live state
* current action status
* record counts
* preview
* seed/import/export/reset actions

#### Exports

Pulls export concerns out of the generic logging page.

Contains:

* export data
* format selection
* date range
* generated export history if needed

#### Logs

Uses current `LoggingRoute` trace-oriented content.

Contains:

* trace log viewer
* runtime trace history
* technical diagnostics

#### State

Uses raw inspection content currently mixed into multiple places.

Contains:

* engine snapshot
* raw JSON viewer
* payload inspection
* API response inspection where useful

This gives raw system inspection a clear home instead of scattering it between Dashboard, Logs, and Admin. 

---

## 4.5 Research

**Purpose:**
Experimental or lower-frequency tools that should stay available without cluttering the main operator workflow.

**Recommended route:**
`/research`

**Tabs:**

* `Simulations`
* `Experiments` (reserved)

### Simulations

Uses the current `SimulationsRoute`.

Contains:

* recent simulation runs
* selected run payload
* replay inspection

### Experiments

Reserved for future experimental surfaces if they appear.

This keeps simulations accessible without pretending they are part of the core operational loop.

---

## 4.6 Preferences

**Purpose:**
Personal UI and local client behavior only.

**Recommended route:**
`/preferences`

This should remain outside the domain workspaces because it is not part of trading or operations.

Contains:

* terminology mode
* number precision
* time format
* dashboard refresh interval
* KPI delta window
* debug preferences
* preview
* reset

This is the current `SettingsRoute`, renamed more clearly to avoid confusion with engine/runtime settings in Operations. 

---

## 5. Proposed Route Map

```text
/trading
  ?tab=overview
  ?tab=markets
  ?tab=scans
  ?tab=trades
  ?tab=portfolio

/intelligence
  ?tab=failures
  ?tab=performance
  ?tab=learning
  ?tab=audit

/operations
  ?tab=overview
  ?tab=queue
  ?tab=budget
  ?tab=settings
  ?tab=alerts
  ?tab=safety

/data
  ?tab=storage
  ?tab=exports
  ?tab=logs
  ?tab=state

/research
  ?tab=simulations
  ?tab=experiments

/preferences
```

This route strategy keeps grouping simple and still allows shareable URLs.

---

## 6. Proposed Current-to-New Mapping

| Current route  | Proposed new location                                                                    |
| -------------- | ---------------------------------------------------------------------------------------- |
| `/dashboard`   | `/trading?tab=overview`                                                                  |
| `/markets`     | `/trading?tab=markets`                                                                   |
| `/portfolio`   | `/trading?tab=portfolio`                                                                 |
| `/trades`      | `/trading?tab=trades`                                                                    |
| `/scans`       | `/trading?tab=scans`                                                                     |
| `/failures`    | `/intelligence?tab=failures`                                                             |
| `/performance` | `/intelligence?tab=performance` or `/operations?tab=overview` depending on meaning split |
| `/admin`       | `/operations?tab=overview`                                                               |
| `/alerts`      | `/operations?tab=alerts`                                                                 |
| `/storage`     | `/data?tab=storage`                                                                      |
| `/logs`        | `/data?tab=logs`                                                                         |
| `/simulations` | `/research?tab=simulations`                                                              |
| `/settings`    | `/preferences`                                                                           |

### Important note on `Performance`

The current `PerformanceRoute` is described as **scan timing and runtime analytics**, not trade-performance analytics. That means it may fit better under:

* `Operations` if it is mostly runtime timing/health
* `Intelligence` only if it becomes trade-quality/performance analytics

Based on the current map, I would place it in **Operations** unless its content is intentionally repurposed. 

---

## 7. Recommended Structural Rules

## 7.1 New top-level page rule

A new feature should only become a top-level workspace if it represents a new operator domain.

Do **not** create a new top-level page for:

* failures
* learning
* analytics
* audit
* circuit breaker
* logs
* storage variants

Those should live inside existing workspaces.

## 7.2 Tab rule

A page should become a tab inside a workspace when it:

* shares users with adjacent pages
* shares filters or context
* is often used in the same workflow
* does not justify independent product identity

## 7.3 Utility route rule

A page should stay outside workspaces only if it is:

* user-specific
* global
* non-domain
* infrequently used but universally accessible

This is why `Preferences` should remain separate.

---

## 8. Proposed App Shell Revision

Root shell should still own:

* top navigation
* health snapshot
* queue snapshot
* operator alerts
* portfolio summary
* runtime settings
* available symbols
* global toaster

But instead of routing directly to many independent pages, it should route primarily to:

* `TradingWorkspaceRoute`
* `IntelligenceWorkspaceRoute`
* `OperationsWorkspaceRoute`
* `DataWorkspaceRoute`
* `ResearchWorkspaceRoute`
* `PreferencesRoute`

Each workspace route then owns its internal tab switch and tab-level content mounting.

This would simplify `App.tsx` and make future additions easier to place. 

---

## 9. Proposed Component/Module Refactor Direction

This phase is still interface-only, but the new map suggests cleaner component boundaries.

### New route-level files

* `interface/src/routes/TradingWorkspaceRoute.tsx`
* `interface/src/routes/IntelligenceWorkspaceRoute.tsx`
* `interface/src/routes/OperationsWorkspaceRoute.tsx`
* `interface/src/routes/DataWorkspaceRoute.tsx`
* `interface/src/routes/ResearchWorkspaceRoute.tsx`

### Candidate co-located tab modules

#### Trading

* `modules/trading/OverviewTab.tsx`
* `modules/trading/MarketsTab.tsx`
* `modules/trading/ScansTab.tsx`
* `modules/trading/TradesTab.tsx`
* `modules/trading/PortfolioTab.tsx`

#### Intelligence

* `modules/intelligence/FailuresTab.tsx`
* `modules/intelligence/PerformanceTab.tsx`
* `modules/intelligence/LearningTab.tsx`
* `modules/intelligence/AuditTab.tsx`

#### Operations

* `modules/operations/OverviewTab.tsx`
* `modules/operations/QueueTab.tsx`
* `modules/operations/BudgetTab.tsx`
* `modules/operations/SettingsTab.tsx`
* `modules/operations/AlertsTab.tsx`
* `modules/operations/SafetyTab.tsx`

#### Data

* `modules/data/StorageTab.tsx`
* `modules/data/ExportsTab.tsx`
* `modules/data/LogsTab.tsx`
* `modules/data/StateTab.tsx`

#### Research

* `modules/research/SimulationsTab.tsx`
* `modules/research/ExperimentsTab.tsx`

This is consistent with the maintenance note that Admin is already overloaded and should eventually be split into co-located route modules. 

---

## 10. Proposed Simplified Hierarchy

```text
App
├── Navbar
├── Trading
│   ├── Overview
│   ├── Markets
│   ├── Scans
│   ├── Trades
│   └── Portfolio
├── Intelligence
│   ├── Failures
│   ├── Performance
│   ├── Learning
│   └── Audit
├── Operations
│   ├── Overview
│   ├── Queue
│   ├── Budget
│   ├── Settings
│   ├── Alerts
│   └── Safety
├── Data
│   ├── Storage
│   ├── Exports
│   ├── Logs
│   └── State
├── Research
│   ├── Simulations
│   └── Experiments
└── Preferences
```

---

## 11. Migration Recommendation

This should be done in two interface passes.

### Pass 1 — navigation consolidation

* add workspace routes
* move current pages behind tabs
* keep current routes as compatibility redirects
* preserve bookmarks and URL-driven state

### Pass 2 — cleanup and de-duplication

* remove duplicate alert surfaces
* split performance/runtime vs trade analytics clearly
* move raw inspection tools into Data
* simplify Admin by extracting its mixed responsibilities into Operations tabs

This keeps the reorganization manageable and avoids forcing a full visual rewrite in one step.

---

## 12. Final Recommendation

For Phase 21, the interface should stop growing as a flat set of pages and start behaving like a system with a few stable operator workspaces.

The strongest proposed structure is:

* `Trading`
* `Intelligence`
* `Operations`
* `Data`
* `Research`
* `Preferences`

And the most important placement decisions are:

* `Dashboard` becomes `Trading > Overview`
* `Failures` becomes `Intelligence > Failures`
* `Phase 20 analytics` becomes `Intelligence > Performance`
* `Learning` moves out of Admin and into `Intelligence`
* `Admin + Alerts + circuit breaker` consolidate into `Operations`
* `Storage + Logs + raw inspection` consolidate into `Data`
* `SettingsRoute` becomes `Preferences`
* `Simulations` moves to `Research`

That gives you a cleaner, more scalable interface map without requiring backend changes.
