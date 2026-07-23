# SearchView Premium Visual Refresh — Design

Date: 2026-07-23

## Context

`OnboardingView` and `PremiumUpgradeView` already established a "premium"
visual language in this app: glowing gradient icon circles (`RadialGradient`
fill + stroked ring + `LinearGradient` icon `foregroundStyle` + soft
`shadow`), pill/card surfaces with a subtle `accentColor`-tinted
`strokeBorder` + shadow (e.g. `AIHubView`'s `TradeRecommendationCard`), and
buttons with a taller frame, rounded-28 corners, and an accent-colored glow
shadow (`OnboardingView.nextButton`). `SearchView` (the "Analiz" tab) still
uses flat `Color(.tertiarySystemBackground)`/`Color(.secondarySystemBackground)`
fills with no depth or accent treatment, so it reads as visually older/flatter
than the rest of the app.

## Goal

Bring `SearchView`'s visual surfaces up to the app's established premium
language — depth via subtle glow/shadow, gradient accents on the primary
action — while preserving full light/dark adaptivity (unlike
`OnboardingView`, which is a fixed-dark screen, `SearchView` must keep
using semantic system colors so it still respects `session.appTheme`).

## Scope

Touches only `SearchView.swift` and the three components it exclusively
uses (confirmed via `grep -rln "QuickSymbolButton(\|SearchHistoryTag(\|SectorChip("`
across `Views/*.swift` — all three matches are in `SearchView.swift`, so
these components are safe to restyle without affecting other screens):
`QuickSymbolButton`, `SearchHistoryTag`, `SectorChip` (all defined in
`OptiTradeiOS/OptiTradeiOS/Components/Components.swift`).

**Explicitly out of scope:** `ResultCardView` (shared with `DashboardView`
and `PortfolioAnalysisView` — restyling it is a separate, app-wide decision,
not part of this pass), `SearchViewModel`'s logic, search/filter/history
behavior, `AnalysisDetailView`.

## Visual changes

**1. Search card magnifying-glass icon** (`searchCard`, currently a plain
`Image(systemName: "magnifyingglass").foregroundColor(.accentColor)` next
to the text field): wrap in a small glow treatment — a `Circle` with a
`RadialGradient` fill (`accentColor.opacity(0.15)` → `.clear`) behind the
icon, icon itself using `LinearGradient` `foregroundStyle` (`accentColor` →
`accentColor.opacity(0.7)`) instead of a flat color. Scaled down from
`OnboardingView`'s 140pt version to fit inline (~36pt circle).

**2. "Analiz Et" button** (`searchCard`'s primary action): replace the flat
`Color.accentColor` fill with a subtle `LinearGradient`
(`accentColor` → `accentColor.opacity(0.8)`), and replace the existing flat
`shadow(color: ... .opacity(0.3), radius: 8, y: 4)` with a slightly softer,
larger glow (`radius: 10, y: 5`) matching `OnboardingView.nextButton`'s
values — button's disabled state (`vm.symbol.isEmpty`) keeps its current
flat gray, no gradient/glow (glow implies "actionable").

**3. `QuickSymbolButton`**: add a `strokeBorder(Color.accentColor.opacity(0.15), lineWidth: 1)`
overlay and a very soft `shadow(color: .black.opacity(0.08), radius: 4, y: 2)`
to the existing `Color(.tertiarySystemBackground)` fill — adds depth without
changing the semantic background (still adapts to light/dark).

**4. `SearchHistoryTag`**: add a `strokeBorder` using the tag's existing
per-decision `color` (already computed for the leading dot) at low opacity
(`color.opacity(0.25)`), tying the border tint to BUY/SELL/neutral the same
way the dot already does — no new color logic, just apply the existing
`color` property to the capsule's border too.

**5. `SectorChip`**: when selected, add the same soft glow shadow pattern
(`shadow(color: Color.accentColor.opacity(0.3), radius: 6, y: 3)`) so the
active sector filter has the same "lit up" feel as other selected/primary
elements. Unselected state unchanged.

**6. `suggestionsSection`**: the row container (currently flat
`Color(.secondarySystemBackground)` with no border/shadow) gets the same
treatment as `QuickSymbolButton` — subtle border + soft shadow — for
consistency with the rest of the empty/browsing state.

## Testing

No XCTest target exists for this project — verification is `xcodebuild
build` (compile correctness) plus a manual/simulator visual check in both
light and dark appearance (simulator's `xcrun simctl ui <UDID> appearance
light|dark`) to confirm the glow/gradient/border treatments read correctly
in both themes, not just dark.
