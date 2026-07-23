# AI Hub Dashboard Integration — Design

Date: 2026-07-23

## Context

`AIHubView.swift` (iOS) is a fully built screen that calls
`APIService.shared.analyzeSignals(symbols:)` → backend `POST /api/v1/signals/analyze`
→ `HybridTradingEngine`/`AITraderPersona` (see
`2026-07-22-hybrid-quant-trading-design.md`) and renders AI-generated trade
recommendations (`TradeRecommendationCard`: confidence score, signal badge,
entry/stop-loss/take-profit levels, AI commentary). It compiles and is part
of the Xcode target, but no screen navigates to it — it is unreachable in
the shipped app. This spec wires it in.

## Goal

Make AI Hub reachable without growing the tab bar past 5 items, gate it
behind the existing premium tier, and drive it off the user's real
watchlist instead of a hardcoded 3-symbol list.

## Approach

Fold `AIHubView`'s content into `DashboardView` as a second mode, selected
by a segmented control placed above the existing market picker:

```
┌─────────────────────────────────┐
│ SessionBannerCard (unchanged)    │
│ MarketNewsTicker (unchanged)     │
│ [ Piyasa Taraması | AI Önerileri ]  <- new Picker(.segmented)
├─────────────────────────────────┤
│ Piyasa Taraması:                 │  AI Önerileri:
│   market picker (Hisse/Kripto)   │    if isPremium:
│   sort menu                      │      AI Hub content (loading/
│   scan result list               │      error/recommendation cards)
│   ad banner (non-premium)        │    else:
│                                   │      upgrade prompt card
└─────────────────────────────────┘
```

- `DashboardView` gains `@State private var mode: DashboardMode = .scan`
  (`enum DashboardMode { case scan, aiHub }`).
- `AIHubView`'s body is split: drop its own `NavigationStack` and toolbar
  title: `DashboardView` already owns the `NavigationStack` and
  `.navigationTitle`. The refresh toolbar button becomes conditional —
  shown when `mode == .aiHub`, calling `aiHubVM.analyze()` instead of
  `vm.scan()`.
- `AIHubViewModel` stays a separate `@StateObject` owned by `DashboardView`
  (`aiHubVM`), not merged into `DashboardViewModel` — different backend
  call, different loading/error state, no reason to couple them.
- Navigation title switches with the mode: `L("Piyasa Taraması")` /
  `L("AI Önerileri")`.

## Symbol source

`AIHubViewModel.symbols` changes from the hardcoded
`["BTC-USD", "AAPL", "THYAO.IS"]` to a computed pull from
`UserSession.shared.watchlist()` (`[WatchlistItemData].map(\.symbol)`),
capped at a reasonable count (10) to bound backend/LLM call cost. If the
watchlist is empty, fall back to the same 3 hardcoded symbols so a new user
never sees a blank state before adding anything to their watchlist.

`AIHubViewModel.analyze()` re-reads the watchlist each time it runs (not
just at init) so a symbol added mid-session shows up on next refresh
without restarting the view.

## Premium gating

Mirrors the existing pattern in `AnalysisDetailView` (`if session.isPremium
{ v2AnalysisSection }`), but since AI Hub is now a full segment rather than
an inline card, silently showing nothing would look broken. Non-premium
users instead see a compact upgrade card (icon + one-line pitch + button)
that opens the existing `PremiumUpgradeView` sheet — same sheet already
wired in `SettingsView`, no new purchase-flow code.

## Localization

`AIHubView` currently has zero `L()` wraps (all strings hardcoded Turkish).
Per the project's established convention, every user-facing string touched
in this change gets wrapped in `L(...)` (falls back to Turkish under
English mode if not yet in `Localization.swift`'s dictionary — consistent
with how other recently-added screens were handled during the last merge).

## Out of scope

- Redesigning `DashboardView`'s visual style or the scan-list cards.
- Any change to `AIHubViewModel`'s backend call, `TradeRecommendationCard`,
  or `HybridTradingEngine`/`AITraderPersona`.
- Watchlist management UI changes.
- The other three improvement areas from this session's broader scope
  (Tarama, Analiz, Analiz Detayı visual/functional redesign) — separate
  specs, one at a time.

## Testing

Manual: run the app with an empty watchlist (confirm 3-symbol fallback),
with a populated watchlist (confirm real symbols used, capped at 10), and
toggle premium on/off (confirm upgrade card vs. real content). Confirm tab
bar still shows exactly 5 items.
