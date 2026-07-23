# SearchView News Section — Design

Date: 2026-07-23

## Context

`SearchView` (Analiz tab) currently has no news content. `MarketNewsTicker`
(`OptiTradeiOS/OptiTradeiOS/Views/MarketNewsView.swift`) already exists,
already renders general market news (`APIService.shared.fetchMarketNews()`,
not symbol-specific), already self-hides when there's no news, and is
already used the same way at the top of `DashboardView`. No new component
or backend call is needed.

## Goal

Give the user something useful to see in `SearchView`'s empty/browsing
state (before they've typed a symbol), reusing the existing ticker.

## Placement

`MarketNewsTicker()` is added directly below `searchCard`, only in the
same branch that currently shows `historySection`/`quickAccessSection` —
i.e. only when `vm.symbol.isEmpty` (user hasn't started typing/searching).
It does not appear during loading, error, result, or suggestions states —
those are the "user is actively doing something" states, where market-wide
news is a distraction, not while just browsing.

## Testing

No XCTest target exists — verification is `xcodebuild build` plus a manual
check: with an empty search field, confirm the ticker appears between the
search card and the history/quick-access sections (or is silently absent
if there's no news, matching its existing self-hiding behavior); confirm
it disappears once the user types a symbol or a result appears.
