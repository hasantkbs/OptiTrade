# Dashboard Layout Declutter — Design

Date: 2026-07-23

## Context

`DashboardView` (the "Tarama" tab) currently stacks five full-width elements
above any real content: `SessionBannerCard`, `MarketNewsTicker`, the
Piyasa Taraması/AI Önerileri mode `Picker`, a full-width Hisse/Kripto market
`Picker`, and a sort-menu-plus-timestamp row. On a typical phone this chrome
can occupy close to half the visible screen before a single scan result is
shown. User feedback: too many stacked controls, unclear where to look.

## Goal

Reduce the *fixed* (always-visible, non-scrolling) header to two rows, by
moving `SessionBannerCard` and `MarketNewsTicker` into the scrollable
content area, and by compacting the market picker + sort row into one line
instead of two.

## Target layout

**Fixed header (scan mode):**
1. Mode `Picker` — "Piyasa Taraması" / "AI Önerileri" (unchanged, full width)
2. One row: compact (non-full-width) Hisse/Kripto segmented control on the
   left, sort menu capsule on the right — replaces the current two-row
   `headerControls` (market picker row + sort/timestamp row)

**Scrollable content (scan mode), top to bottom:**
1. `SessionBannerCard` (if `sessionInfo` is loaded)
2. `MarketNewsTicker` (self-hides when there's no news, unchanged component)
3. State-dependent body:
   - Loading: existing `SkeletonResultCard` x5
   - Error: existing error icon/message/retry button
   - Empty (no scan yet): existing `EmptyStateView`
   - Results: `ScanSummaryBanner`, a small "Son tarama: HH:mm" caption
     (moved out of the fixed header, shown only when `lastScanned` is set),
     `SectorOpportunityMiniCard`, then the AL/SAT/Nötr sections exactly as
     today
4. Footer (scanned-count line, disclaimer, branding) — unchanged, results
   state only

**Unchanged:** `AdBannerPlaceholder` stays pinned below the scroll view for
non-premium users (standard ad-banner placement, not part of the reported
clutter). AI Hub mode (`AIHubView`), `ResultCardView`, and the result cards'
internal content are untouched.

## Structural change

`DashboardView.content` currently branches into four independent
top-level containers (a `ScrollView` for loading, a bare `VStack`+`Spacer`
for error, `resultsView`'s own `ScrollView`, a bare `VStack`+`Spacer` for
empty) — each state owns its own scroll or lack of one. `SessionBannerCard`
and `MarketNewsTicker` need to appear consistently above all four without
duplicating them four times or having them flicker in/out as state
transitions (e.g. loading → results). `content` becomes a single outer
`ScrollView` that always renders session banner + news ticker first, then
switches on `vm.isLoading` / `vm.errorMessage` / `vm.scanResult` for the
rest. `resultsView`'s existing `.refreshable { await vm.scan() }` moves to
this new outer `ScrollView`.

## Compact market picker

The current `Picker(..., selection: $vm.selectedMarket) { ... }
.pickerStyle(.segmented)` has no width constraint, so it stretches to fill
the horizontal space (`.padding(.horizontal)` only constrains its margins,
not its width) — that's why it currently occupies a full row. Giving it a
fixed `.frame(width:)` (roughly 160pt — wide enough for both segment
labels, narrow enough to leave room for the sort menu beside it) keeps its
existing behavior (`onChange` triggers `vm.scan()`, `.pickerStyle(.segmented)`,
same `L()` labels) while letting it share a row with the sort menu via an
`HStack` with a `Spacer()` between them.

## Out of scope

- Any change to `SessionBannerCard`, `MarketNewsTicker`,
  `ScanSummaryBanner`, `SectorOpportunityMiniCard`, or `ResultCardView`'s
  internal layout/content — only their position moves.
- AI Hub mode's layout (already addressed in the prior AI Hub integration
  work).
- The Analiz (SearchView) and Analiz Detayı (AnalysisDetailView) screens —
  separate follow-up work, not part of this pass.
- Making `SessionBannerCard` dismissible/collapsible — out of scope per
  this session's chosen approach (session banner stays, just relocates).

## Testing

No XCTest target exists for this project — verification is `xcodebuild
build` (compile correctness) plus a manual/simulator visual check: confirm
the fixed header is exactly two rows in scan mode, confirm session banner
and news ticker appear at the top of the scroll and scroll away with the
rest of the content, confirm pull-to-refresh still works, confirm the
compact market picker still switches between Hisse/Kripto and re-scans,
confirm AI Hub mode (fixed header: one row, the mode picker) is unaffected.
