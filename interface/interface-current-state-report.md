# Interface Current-State Analysis Report

Date: 2026-04-23

## Purpose

This report analyzes the current interface inside the `interface/` folder, with emphasis on:

- current information architecture
- shell and routing structure
- page ownership and query patterns
- strengths of the current UI
- weaknesses relevant to upcoming live-trading + profile work
- recommended direction for interface evolution

This is a current-state report, not an implementation spec.

---

## Executive Summary

The interface is already significantly more structured than a flat admin panel.

It has:

- a workspace-based navigation model
- solid route grouping
- a consistent visual system
- strong React Query usage
- multiple mature operational pages for trades, portfolio, scans, and runtime control

However, it still has several important structural issues that matter for the next phase:

1. **Global shell ownership is still too heavy**
   `App.tsx` and `Navbar.tsx` still load and present too much global operational state.

2. **Execution UI is still paper-centric**
   Portfolio and trades assume a mostly single-account paper worldview.

3. **Profile-awareness does not exist yet**
   There is no concept of `paper profile`, `binance profile`, or `bybit profile` in navigation, data contracts, or display state.

4. **Some page intent is cleaner than before, but not fully enforced**
   There is still overlap between overview, control, config, and analytics surfaces.

5. **The interface is ready for profile-aware evolution**, but it needs explicit backend fields and some UI contract cleanup first.

Overall assessment:

> The interface is a good operational foundation, but before live execution lands it needs a profile-aware execution model and some shell/data-contract cleanup.

---

## Reviewed Files

### High-level docs
- `interface/README.md`
- `interface/INTERFACE_MAP.md`

### App shell / navigation
- `interface/src/App.tsx`
- `interface/src/components/navigation/Navbar.tsx`
- `interface/src/components/navigation/WorkspaceShell.tsx`
- `interface/src/lib/workspaces.ts`

### Key route surfaces
- `interface/src/routes/TradeOverviewRoute.tsx`
- `interface/src/routes/DashboardRoute.tsx`
- `interface/src/routes/TradesRoute.tsx`
- `interface/src/routes/PortfolioRoute.tsx`
- `interface/src/routes/SettingsRoute.tsx`
- `interface/src/routes/OperateConfigPageRoute.tsx`
- `interface/src/routes/OperateControlPageRoute.tsx`
- `interface/src/routes/RuntimeConfigRoute.tsx`
- `interface/src/routes/OperateControlRoute.tsx`

### Data contracts
- `interface/src/lib/api.ts`
- `interface/src/lib/apiRoutes.ts`
- `interface/src/lib/types.ts`

---

## 1. Current Information Architecture

## 1.1 Workspace structure is already a strong improvement
The current workspace model in `interface/src/lib/workspaces.ts` is:

- `Trade`
  - Overview
  - Markets
  - Scans
  - Trades
  - Portfolio
- `Review`
  - Engine Performance
  - Engine Behavior
  - Failures
  - Learning
- `Operate`
  - Control
  - Alerts
  - Logs
  - Config
- `System`
  - Preferences
  - Storage
  - Simulations

This is good.

It gives the interface a coherent top-level mental model:

- current operation
- historical review
- runtime control
- lower-frequency system actions

This is much better than the earlier mixed `Dashboard/Admin/Settings` style.

### Assessment
**Strength:** Good navigation taxonomy.

### Remaining issue
Even though the route structure is cleaner, the actual data ownership inside the shell and some pages still behaves more like an older monolithic admin UI.

---

## 1.2 The route map and naming are mostly aligned
The route naming rules are generally strong:

- `Trade` = current-state, action-oriented
- `Review` = historical / audit
- `Operate` = runtime control
- `System` = preferences + storage + lab-like surfaces

This is reinforced by:

- `WorkspaceShell`
- legacy redirects in `workspaces.ts`
- top-nav workspace destinations

### Assessment
**Strength:** The route taxonomy is already ready for scaling.

### Future relevance
This is a good foundation for adding profile-aware execution, because profiles can fit naturally into:

- Trade
- Operate
- Review

without redesigning the whole app.

---

## 2. Shell Architecture Analysis

## 2.1 `App.tsx` still owns too much global state
`interface/src/App.tsx` currently fetches at shell level:

- engine health
- jobs
- operator alerts
- portfolio
- runtime settings
- symbols
- circuit breaker state

It then passes a lot of this into `Navbar`.

### What this does well
- creates a responsive shell
- keeps top-nav metrics current
- gives the app a strong operational feel

### What this costs
- `App.tsx` becomes a hidden global dashboard controller
- route-specific concerns bleed into shell concerns
- shell payload contracts expand over time
- profile-specific state will become harder to manage here

### Why this matters for live profiles
If we add:

- active profile selection
- per-profile balances
- per-profile health
- venue connection status
- profile-specific alerts

then `App.tsx` will get even heavier unless the shell becomes more selective.

### Assessment
**Weakness:** shell-level data ownership is still too broad.

### Recommendation
Move toward:

- shell owns only truly global posture
- pages own page-specific query data
- navbar receives a smaller, more intentional status model

---

## 2.2 `Navbar.tsx` is still both navigation and control center
The navbar currently mixes:

- workspace navigation
- status display
- scan trigger
- refresh action
- alerts panel
- command palette
- theme toggle
- engine/circuit/queue information

### Positive side
This is convenient for operators.

### Negative side
It is still overloaded.

The navbar is functioning as:
- global navigation
- status HUD
- quick action surface
- notification center
- utility bar

That is a lot of responsibility for one component.

### Why this matters for profiles
If live trading profiles are added, the navbar may be asked to also show:

- active profile
- exchange connection state
- account health
- margin warnings
- venue-specific alert badges

That would make it too dense.

### Assessment
**Weakness:** navbar is useful but over-scoped.

### Recommendation
Keep quick actions, but avoid turning the navbar into the primary profile/account control surface.
Profile selection should likely live in page-level context bars or workspace headers, not only the navbar.

---

## 2.3 `WorkspaceShell` is clean and reusable
`WorkspaceShell.tsx` is one of the cleaner parts of the interface.

It provides:

- workspace title
- description
- icon
- tab navigation
- outlet layout

### Assessment
**Strength:** simple and scalable.

### Future relevance
This is a good place to eventually support optional context headers like:

- selected profile
- selected account scope
- selected exchange
- selected time window

without redesigning every page.

---

## 3. Page-Level Analysis

## 3.1 Trade Overview is intentionally summary-first
`TradeOverviewRoute.tsx` is focused on:

- active engine
- runtime state
- open trade count
- refresh cadence

This is directionally correct.

### Strengths
- short and focused
- operator-oriented
- not overloaded like the old dashboard

### Weaknesses
- still relies on multiple backend sources that overlap with shell data
- currently not profile-aware
- open trade count and cadence are global, not profile-scoped

### For live/profile future
Trade Overview will likely need to support:

- all profiles summary
- selected profile summary
- profile health cards
- live readiness posture

### Assessment
**Strength with future expansion need.**

---

## 3.2 Dashboard still looks like a legacy mixed surface
`DashboardRoute.tsx` is still quite large and mixes:

- queue pressure
- event feed
- failure summary
- refresh controls
- multiple hero and panel sections

It appears to be a legacy route that still acts like a broad dashboard cockpit.

### Observation
The newer workspace model points to `/trade/overview`, but this dashboard route still exists and contains a lot of broad operational content.

### Risk
This creates possible duplication/confusion between:

- old dashboard mental model
- new trade overview mental model

### Assessment
**Weakness:** legacy overlap still exists in codebase, even if nav has improved.

### Recommendation
Continue treating `TradeOverviewRoute` as canonical and reduce the strategic importance of `DashboardRoute` over time.

---

## 3.3 Trades page is one of the strongest current surfaces
`TradesRoute.tsx` is mature and feature-rich.

It already supports:

- overview tab
- ledger tab
- detail tab
- audit tab
- failures tab
- filters and sorting
- export
- manual close / close-all
- deep inspection patterns

### Strengths
- real operator utility
- good analytic layering
- strong use of supporting audit and failure data
- clear trade lifecycle display

### Weaknesses relevant to next phase
- no `profile_id` awareness
- no `execution_mode` awareness beyond weak source heuristics
- current grouping logic in API types is semantically shaky
- trade rows do not show a true venue/account dimension

### Important issue
The current UI contract derives categories using `source`, and the mapping in `api.ts` treats `LIVE` specially in a way that does not align with current backend source usage.

That means this area should be cleaned up before live profiles are added.

### Assessment
**Major strength**, but needs contract cleanup before live support.

---

## 3.4 Portfolio page is strong but paper-centric
`PortfolioRoute.tsx` is also mature and rich. It supports:

- KPI cards
- equity and drawdown
- distribution charts
- symbol attribution
- cadence views
- mode/interval breakdown
- open/closed tabbing

This is strong operator UX.

### But the current worldview is still paper-centered
Examples:
- direct use of `paper_account`
- explicit `Paper Cash` KPI
- one portfolio payload assumption
- no concept of multiple venue accounts

### Why this matters
As soon as profiles are introduced, the portfolio page must answer:

- is this portfolio for paper only?
- is this selected profile only?
- is this aggregated across profiles?
- are balances cash, margin, wallet, available, or equity?

The current page shape can survive, but the data model beneath it must change.

### Assessment
**Strong page, but strongly single-portfolio / paper-oriented.**

---

## 3.5 Preferences page is clean and correctly scoped
`SettingsRoute.tsx` has been reframed as personal interface preferences:

- terminology mode
- number precision
- time format
- refresh interval
- KPI delta window
- debug display preferences

This is clean and understandable.

### Assessment
**Strength:** one of the clearer page boundaries.

### Relevance to profile work
No major structural issue here. This page is largely unaffected by live profiles.

---

## 3.6 Operate Config is useful, but still generic/raw
`OperateConfigPageRoute.tsx` provides grouped runtime settings editing.

Strengths:
- grouped categories
- searchable settings
- editable values
- quick operator utility

Weaknesses:
- still a raw settings editor
- grouping is matcher-based and somewhat coarse
- not profile-aware
- settings model is global, not per execution profile

### Why this matters
Once profiles are introduced, runtime config likely needs separation between:

- global runtime settings
- profile settings
- exchange adapter settings
- risk/policy per profile

The current page would struggle if all of that stayed in one raw grid.

### Assessment
**Useful current tool, but not sufficient as the long-term config UX for multi-profile execution.**

---

## 3.7 Operate Control is model/runtime oriented, not execution-profile oriented
`OperateControlPageRoute.tsx` currently focuses on:

- champion registry
- runtime readiness
- shadow engine
- model promotion / rollback
- available models

This page is useful for engine operations, but it is not yet an execution-control surface in the live-trading sense.

### Gap for future
There is currently no dedicated UI concept for:

- execution profile health
- exchange connectivity
- profile enable/disable
- auto/manual/live mode per profile
- emergency trading disable per profile

### Assessment
**Good engine control page, but not yet a live execution control page.**

---

## 4. Data Contract Analysis

## 4.1 The API layer is centralized and pragmatic
`interface/src/lib/api.ts` and `apiRoutes.ts` provide a good centralized API access layer.

### Strengths
- one place for route wiring
- one place for fetch behavior and error handling
- React Query integration is straightforward

### Weaknesses for next phase
- some mapping logic is doing semantic work that belongs in backend contracts
- current order snapshot normalization is not profile-aware
- some legacy assumptions remain embedded in client transforms

### Assessment
**Strength overall**, but backend contracts should become more explicit before profile work expands.

---

## 4.2 Types are broad and flexible, but often too loose
`interface/src/lib/types.ts` uses many `JsonRecord`-heavy payloads.

This provides flexibility, but it also means:

- many UI assumptions are inferred instead of enforced
- contract drift is easier to miss
- live/profile additions may create more ad hoc field usage

### Why this matters
For profile-aware execution, some types should become more explicit, especially around:

- order identity
- execution mode
- venue
- profile id
- balance/account data
- connection state

### Assessment
**Flexible but under-typed in areas that are about to become more complex.**

---

## 4.3 Current order categorization is semantically fragile
This is one of the most important interface findings.

In `api.ts`, order groups are derived using `source` and a `LIVE` check in a way that does not reflect the backend’s actual current execution semantics.

This means:
- current UI categories are already somewhat misleading
- future live/profile work should not build on this heuristic

### Recommendation
The backend should explicitly return fields like:

- `profile_id`
- `execution_mode`
- `venue`
- `origin`

And the interface should group from those fields directly.

---

## 5. Visual / UX System Assessment

## 5.1 Visual consistency is strong
Across routes, the interface has a clear stylistic system:

- rounded cards
- layered panels
- consistent shadows
- status badges
- compact KPI framing
- polished operator UI look

### Assessment
**Strength:** UI consistency is already good enough for future expansion.

---

## 5.2 The app is optimized for an operator, not just an analyst
This is a strong product characteristic.

You can see it in:
- quick actions
- filters
- control buttons
- live-ish polling
- event feeds
- export paths
- status ribbons and badges

This is a good fit for the direction toward live profiles.

### Assessment
**Strength:** operational UX mindset is already present.

---

## 5.3 Density is high in some surfaces
A few pages and the navbar carry a lot of information density.

That is not automatically bad, but it means profile additions should be careful not to overload existing panels.

### Recommendation
Prefer:
- page-level profile context bars
- profile switchers
- scoped cards/tabs

over squeezing more context into the navbar.

---

## 6. Readiness for Live Profiles

## What is already ready
The interface is already ready for:

- profile filters
- profile badges in rows
- profile-level tabs/cards
- execution health pages
- expanded portfolio modes
- multi-scope trade review

because the app already has:
- workspace structure
- strong trade and portfolio pages
- stable query architecture
- reusable card and badge patterns

## What is not ready yet
The interface is not yet ready for live-profile support in these ways:

- no profile navigation or selection
- no profile-aware data contracts
- no venue/account semantics in core pages
- no live connection status surfaces
- no per-profile balance/risk widgets
- no clear execution profile control panel

---

## 7. Main Gaps Relative to Upcoming Work

For the upcoming paper/binance/bybit profile work, the biggest interface gaps are:

### 1. No profile context
The UI has no first-class concept of the active or selected execution profile.

### 2. No execution-mode distinction
There is no durable UI contract for:
- paper
- live
- hybrid / aggregate

### 3. Portfolio assumes one account model
The current portfolio page is built around one summary payload.

### 4. Trade ledger lacks venue/account semantics
Trade review is good, but it does not yet answer:
- which profile placed this?
- which venue filled it?
- was this paper or live?

### 5. Operate surfaces are not yet execution-profile control surfaces
They are engine/runtime controls, not live execution account controls.

---

## 8. Recommended Interface Direction

## Short-term
Before any UI-heavy live trading work:

1. clean up execution contracts returned by backend
2. add explicit profile-related fields to types
3. stop deriving trade categories from weak `source` heuristics

## Near-term
Introduce profile awareness in three places first:

1. `Trades`
   - profile filter
   - paper/live/venue badge
2. `Portfolio`
   - profile selector
   - profile vs aggregate scope
3. `Operate`
   - profile health and enable/disable posture

## Medium-term
Add a proper execution-profile control/reporting layer:

- profile list page or panel
- connection health
- last sync time
- profile status (`ACTIVE`, `DISABLED`, `READ_ONLY`, `ERROR`)
- auto/manual posture
- risk guardrails per profile

---

## 9. Suggested Future Interface Surfaces

These do not all need to be separate routes immediately, but they are useful conceptual surfaces.

### A. Profile Switcher / Scope Bar
Could appear on:
- Trades
- Portfolio
- Trade Overview
- Operate

Options:
- All profiles
- Paper
- Binance
- Bybit

### B. Execution Profile Status Panel
Could live under `Operate`.

Show:
- profile name
- venue
- mode
- connectivity
- last sync
- order health
- auto enabled
- errors/warnings

### C. Profile-aware Portfolio View
Modes:
- selected profile
- aggregate all profiles

### D. Profile-aware Trade Ledger
Each row should include:
- profile badge
- venue badge
- paper/live badge
- origin badge

---

## Final Assessment

## What is strong today
- route/workspace structure
- visual consistency
- trade and portfolio page maturity
- centralized API layer
- operator-focused UX
- cleaner separation of Preferences vs Config

## What needs attention before live-profile expansion
- shell data ownership
- navbar scope
- contract semantics for execution data
- paper-centric assumptions in portfolio
- lack of profile/account/venue identity

## Final conclusion

> The interface is already a solid operational frontend, but it is still built around a mostly single-profile, paper-oriented execution worldview.

For the next phase, the interface does **not** need a wholesale redesign.
It needs:

1. better execution contracts,
2. first-class profile context,
3. profile-aware trade and portfolio views,
4. dedicated execution-profile operational visibility.

That is a manageable evolution from the current state.

---

## Suggested Next Follow-ups

Useful next docs after this report:

1. `interface/interface-profile-ux-plan.md`
2. `interface/interface-trades-portfolio-profile-delta.md`
3. `interface/interface-shell-simplification-plan.md`
4. `docs/execution-profiles-api-contracts.md`
