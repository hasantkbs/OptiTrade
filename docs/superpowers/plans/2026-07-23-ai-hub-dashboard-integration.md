# AI Hub Dashboard Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `AIHubView` (AI-generated trade recommendations screen) reachable in the app by folding it into `DashboardView` as a second, premium-gated mode selected via a segmented control, driven by the user's watchlist instead of a hardcoded symbol list.

**Architecture:** `DashboardView` gains a `DashboardMode` (`scan` / `aiHub`) state and a segmented `Picker` above its existing content. `AIHubViewModel` becomes externally owned (by `DashboardView`) instead of self-owned, so the shared toolbar refresh button can drive it. `AIHubView` loses its own `NavigationStack`/title/toolbar (now supplied by `DashboardView`) and gains self-contained premium gating (shows an upgrade card when `!session.isPremium`).

**Tech Stack:** SwiftUI, no XCTest target exists for `OptiTradeiOS` (confirmed via `grep -n "com.apple.product-type.bundle.unit-test" OptiTradeiOS.xcodeproj/project.pbxproj` returning nothing) — verification in every task is `xcodebuild build` (compile-time correctness) plus manual simulator checks, not automated unit tests.

## Global Constraints

- Every new user-facing static string must be wrapped in `L(...)` (project's TR/EN localization helper, `OptiTradeiOS/OptiTradeiOS/Localization.swift`). Dynamic/AI-generated text (`traderCommentary`, `marketRegimeDisplayName`, `signal.displayName`) is NOT wrapped in `L()` — it's free text from the backend, not a fixed dictionary string.
- Tab bar must stay at exactly 5 items — this feature adds no new tab.
- Backend `POST /api/v1/signals/analyze` caps `symbols` at 20 (`backend/api/v1/endpoints/signals.py`, `max_length=20`); the client-side symbol cap chosen here (10) must stay under that.
- Build command for every verification step:
  ```
  cd "OptiTradeiOS" && xcodebuild -project OptiTradeiOS.xcodeproj -scheme OptiTradeiOS -destination 'generic/platform=iOS Simulator' -configuration Debug build
  ```
  Run from repo root `/Users/hasantekbas/Downloads/Algorix Project Doc/OptiTrade/OptiTradeCode`. Expected final line: `** BUILD SUCCEEDED **`.

---

## Task 1: Symbol source — pull from watchlist instead of hardcoded list

**Files:**
- Modify: `OptiTradeiOS/OptiTradeiOS/Views/AIHubView.swift:6-26` (`AIHubViewModel`)

**Interfaces:**
- Consumes: `UserSession.shared.watchlist() -> [WatchlistItemData]` (`OptiTradeiOS/OptiTradeiOS/Models/Models.swift:1053`), `WatchlistItemData.symbol: String` (`Models.swift:722`)
- Produces: `AIHubViewModel.analyze() async` (unchanged signature — Task 4/5 call this), `AIHubViewModel.isLoading: Bool`, `AIHubViewModel.recommendations: [TradeRecommendation]`, `AIHubViewModel.errorMessage: String?` (all unchanged, still `@Published`)

- [ ] **Step 1: Replace the hardcoded `symbols` property with a private, watchlist-derived computed property**

Open `OptiTradeiOS/OptiTradeiOS/Views/AIHubView.swift`. Replace lines 6-26:

```swift
@MainActor
final class AIHubViewModel: ObservableObject {
    @Published var recommendations: [TradeRecommendation] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var symbols: [String] = ["BTC-USD", "AAPL", "THYAO.IS"]

    func analyze() async {
        isLoading = true
        errorMessage = nil
        do {
            recommendations = try await APIService.shared.analyzeSignals(symbols: symbols)
            if recommendations.isEmpty {
                errorMessage = APIError.noRecommendations.localizedDescription
            }
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
```

with:

```swift
@MainActor
final class AIHubViewModel: ObservableObject {
    @Published var recommendations: [TradeRecommendation] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let fallbackSymbols = ["BTC-USD", "AAPL", "THYAO.IS"]
    private let maxSymbols = 10

    /// Re-read on every `analyze()` call so a symbol added to the watchlist
    /// mid-session shows up on the next refresh without recreating the view.
    private var watchlistSymbols: [String] {
        let symbols = UserSession.shared.watchlist().map(\.symbol)
        return symbols.isEmpty ? fallbackSymbols : Array(symbols.prefix(maxSymbols))
    }

    func analyze() async {
        isLoading = true
        errorMessage = nil
        do {
            recommendations = try await APIService.shared.analyzeSignals(symbols: watchlistSymbols)
            if recommendations.isEmpty {
                errorMessage = APIError.noRecommendations.localizedDescription
            }
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
```

- [ ] **Step 2: Build to verify it compiles**

Run the build command from Global Constraints.
Expected: `** BUILD SUCCEEDED **`. (The `#Preview { AIHubView() }` at the bottom of the file still works — `AIHubView`'s own `init` isn't touched in this task.)

- [ ] **Step 3: Commit**

```bash
git add OptiTradeiOS/OptiTradeiOS/Views/AIHubView.swift
git commit -m "$(cat <<'EOF'
Derive AI Hub symbols from the user's watchlist

Falls back to the previous 3-symbol default when the watchlist is
empty, so a new user never sees a blank state.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Localize AIHubView's static strings

**Files:**
- Modify: `OptiTradeiOS/OptiTradeiOS/Views/AIHubView.swift` (lines listed below — line numbers refer to the file as it stands after Task 1, i.e. before Task 3's restructuring)

**Interfaces:**
- Consumes: global `L(_ turkish: String) -> String` helper (`OptiTradeiOS/OptiTradeiOS/Localization.swift`)
- Produces: no new symbols — string-literal wrapping only, no signature changes

- [ ] **Step 1: Wrap the loading-state strings**

In `loadingState`, replace:

```swift
                Text("AI piyasayı analiz ediyor...")
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(.secondary)
                Text("İlk analiz birkaç saniye sürebilir")
                    .font(.caption)
                    .foregroundColor(.secondary.opacity(0.7))
```

with:

```swift
                Text(L("AI piyasayı analiz ediyor..."))
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(.secondary)
                Text(L("İlk analiz birkaç saniye sürebilir"))
                    .font(.caption)
                    .foregroundColor(.secondary.opacity(0.7))
```

- [ ] **Step 2: Wrap the error-state retry label**

In `errorState(_:)`, replace:

```swift
                Label("Tekrar Dene", systemImage: "arrow.clockwise")
                    .font(.subheadline.weight(.semibold))
```

with:

```swift
                Label(L("Tekrar Dene"), systemImage: "arrow.clockwise")
                    .font(.subheadline.weight(.semibold))
```

- [ ] **Step 3: Wrap the price-row labels in `TradeRecommendationCard.priceRiskBand`**

Replace:

```swift
    private var priceRiskBand: some View {
        VStack(spacing: 10) {
            priceRow(label: "Take-Profit 2", value: recommendation.takeProfit2,
                     color: .green, icon: "arrow.up.circle.fill", emphasis: true)
            priceRow(label: "Take-Profit 1", value: recommendation.takeProfit1,
                     color: Color(red: 0.2, green: 0.8, blue: 0.4), icon: "arrow.up.circle")
            priceRow(label: "Giriş Fiyatı", value: recommendation.entryPrice,
                     color: .primary, icon: "scope", emphasis: true)
            priceRow(label: "Stop-Loss", value: recommendation.stopLoss,
                     color: .red, icon: "arrow.down.circle.fill", emphasis: true)
        }
        .padding(16)
    }
```

with:

```swift
    private var priceRiskBand: some View {
        VStack(spacing: 10) {
            priceRow(label: L("Take-Profit 2"), value: recommendation.takeProfit2,
                     color: .green, icon: "arrow.up.circle.fill", emphasis: true)
            priceRow(label: L("Take-Profit 1"), value: recommendation.takeProfit1,
                     color: Color(red: 0.2, green: 0.8, blue: 0.4), icon: "arrow.up.circle")
            priceRow(label: L("Giriş Fiyatı"), value: recommendation.entryPrice,
                     color: .primary, icon: "scope", emphasis: true)
            priceRow(label: L("Stop-Loss"), value: recommendation.stopLoss,
                     color: .red, icon: "arrow.down.circle.fill", emphasis: true)
        }
        .padding(16)
    }
```

- [ ] **Step 4: Build to verify it compiles**

Run the build command from Global Constraints.
Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 5: Commit**

```bash
git add OptiTradeiOS/OptiTradeiOS/Views/AIHubView.swift
git commit -m "$(cat <<'EOF'
Wrap AIHubView's static UI strings in L()

Brings the screen in line with the project's TR/EN localization
convention. Dynamic AI-generated text (commentary, regime/signal
names) is left unwrapped — it's free text from the backend, not a
fixed dictionary string.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Strip AIHubView's own navigation chrome, make it embeddable

**Files:**
- Modify: `OptiTradeiOS/OptiTradeiOS/Views/AIHubView.swift` (`struct AIHubView`, roughly lines 28-67 as of the end of Task 2)

**Interfaces:**
- Consumes: nothing new
- Produces: `AIHubView(vm: AIHubViewModel)` — **new public init parameter**. Task 5 (`DashboardView`) constructs and owns the `AIHubViewModel` instance and passes it in.

- [ ] **Step 1: Change `AIHubView` from owning its own `NavigationStack`/title/toolbar to a plain, externally-driven content view**

Replace:

```swift
struct AIHubView: View {
    @StateObject private var vm = AIHubViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    if vm.isLoading && vm.recommendations.isEmpty {
                        loadingState
                    } else if let error = vm.errorMessage, vm.recommendations.isEmpty {
                        errorState(error)
                    } else {
                        ForEach(vm.recommendations) { rec in
                            TradeRecommendationCard(recommendation: rec)
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 24)
            }
            .background(Color(.systemGroupedBackground).ignoresSafeArea())
            .navigationTitle("AI Hub")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        Task { await vm.analyze() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(vm.isLoading)
                }
            }
            .refreshable { await vm.analyze() }
            .task {
                if vm.recommendations.isEmpty { await vm.analyze() }
            }
        }
    }
```

with:

```swift
struct AIHubView: View {
    @ObservedObject var vm: AIHubViewModel

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if vm.isLoading && vm.recommendations.isEmpty {
                    loadingState
                } else if let error = vm.errorMessage, vm.recommendations.isEmpty {
                    errorState(error)
                } else {
                    ForEach(vm.recommendations) { rec in
                        TradeRecommendationCard(recommendation: rec)
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 24)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .refreshable { await vm.analyze() }
        .task {
            if vm.recommendations.isEmpty { await vm.analyze() }
        }
    }
```

(The rest of `struct AIHubView` — `loadingState`, `errorState(_:)`, and the closing `}` — is unchanged.)

- [ ] **Step 2: Fix the now-broken `#Preview` at the bottom of the file**

Find:

```swift
#Preview {
    AIHubView()
}
```

Replace with:

```swift
#Preview {
    AIHubView(vm: AIHubViewModel())
}
```

- [ ] **Step 3: Build to verify it compiles**

Run the build command from Global Constraints. `grep -rn "AIHubView(" OptiTradeiOS/OptiTradeiOS` confirms the only call site at this point is the `#Preview` fixed in Step 2, so this should build cleanly. Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 4: Commit**

```bash
git add OptiTradeiOS/OptiTradeiOS/Views/AIHubView.swift
git commit -m "$(cat <<'EOF'
Make AIHubView embeddable: drop its own NavigationStack/title/toolbar

AIHubViewModel is now passed in rather than self-owned, so a parent
view can share one instance between its content and its own toolbar
(needed for the upcoming DashboardView integration).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add premium gating to AIHubView

**Files:**
- Modify: `OptiTradeiOS/OptiTradeiOS/Views/AIHubView.swift` (`struct AIHubView`, top of file after Task 3's changes)

**Interfaces:**
- Consumes: `UserSession.isPremium: Bool` (`@EnvironmentObject`, same flag `AnalysisDetailView` already gates `v2AnalysisSection`/`BacktestPerformanceView` on — `OptiTradeiOS/OptiTradeiOS/Views/AnalysisDetailView.swift`), `PremiumUpgradeView()` (`OptiTradeiOS/OptiTradeiOS/Views/PremiumUpgradeView.swift`, no-arg init, already used the same way in `SettingsView.swift:120-122`)
- Produces: nothing new for other tasks — this is the leaf of the gating logic

- [ ] **Step 1: Wrap `AIHubView`'s body in a premium check, add the upgrade prompt**

Replace the `struct AIHubView` declaration (as left by Task 3) — specifically its stored properties and `var body`:

```swift
struct AIHubView: View {
    @ObservedObject var vm: AIHubViewModel

    var body: some View {
        ScrollView {
```

with:

```swift
struct AIHubView: View {
    @ObservedObject var vm: AIHubViewModel
    @EnvironmentObject private var session: UserSession
    @State private var showPremiumSheet = false

    var body: some View {
        Group {
            if session.isPremium {
                content
            } else {
                upgradePrompt
            }
        }
        .sheet(isPresented: $showPremiumSheet) {
            PremiumUpgradeView()
        }
    }

    private var content: some View {
        ScrollView {
```

Then find the closing of the (now renamed) content `ScrollView` block — it ends right before `// MARK: - Loading`:

```swift
        .refreshable { await vm.analyze() }
        .task {
            if vm.recommendations.isEmpty { await vm.analyze() }
        }
    }

    // MARK: - Loading
```

Insert the new `upgradePrompt` view right after that closing `}` and before `// MARK: - Loading`:

```swift
        .refreshable { await vm.analyze() }
        .task {
            if vm.recommendations.isEmpty { await vm.analyze() }
        }
    }

    private var upgradePrompt: some View {
        VStack(spacing: 16) {
            Image(systemName: "sparkles")
                .font(.system(size: 40))
                .foregroundColor(.yellow)
            Text(L("AI Önerileri Premium Özelliktir"))
                .font(.headline)
                .multilineTextAlignment(.center)
            Text(L("Takip listenizdeki semboller için giriş, stop-loss ve take-profit seviyeleriyle AI destekli ticaret önerileri alın."))
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)
            Button {
                showPremiumSheet = true
            } label: {
                Text(L("Avantajları Gör ve Yükselt"))
                    .font(.subheadline.weight(.bold))
                    .frame(maxWidth: .infinity)
                    .frame(height: 44)
                    .background(Color.accentColor)
                    .foregroundColor(.black)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .padding(.horizontal, 40)
        }
        .padding(.top, 60)
    }

    // MARK: - Loading
```

- [ ] **Step 2: Build to verify it compiles**

Run the build command from Global Constraints.
Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 3: Commit**

```bash
git add OptiTradeiOS/OptiTradeiOS/Views/AIHubView.swift
git commit -m "$(cat <<'EOF'
Gate AI Hub recommendations behind premium, add upgrade prompt

Mirrors the session.isPremium check AnalysisDetailView already uses
for v2AnalysisSection/BacktestPerformanceView. Unlike that inline
card, AI Hub is now a full segment, so non-premium users get an
upgrade card instead of an empty screen.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Wire the segmented control into DashboardView

**Files:**
- Modify: `OptiTradeiOS/OptiTradeiOS/Views/DashboardView.swift`

**Interfaces:**
- Consumes: `AIHubViewModel` (class, `OptiTradeiOS/OptiTradeiOS/Views/AIHubView.swift`, `@Published var isLoading: Bool`, `func analyze() async`), `AIHubView(vm: AIHubViewModel)` (`AIHubView.swift`, from Task 4)
- Produces: `enum DashboardMode` (new top-level type in `DashboardView.swift`) — local to this file, nothing downstream depends on it

- [ ] **Step 1: Add the `DashboardMode` enum above `DashboardViewModel`**

In `OptiTradeiOS/OptiTradeiOS/Views/DashboardView.swift`, find:

```swift
import SwiftUI

enum ScanSort: String, CaseIterable {
```

Replace with:

```swift
import SwiftUI

enum DashboardMode {
    case scan, aiHub
}

enum ScanSort: String, CaseIterable {
```

- [ ] **Step 2: Add `aiHubVM` and `mode` state to `DashboardView`**

Find:

```swift
struct DashboardView: View {
    @StateObject private var vm = DashboardViewModel()
    @EnvironmentObject private var session: UserSession
    @EnvironmentObject private var preferences: UserPreferences
    @State private var sessionInfo: SessionInfo?
```

Replace with:

```swift
struct DashboardView: View {
    @StateObject private var vm = DashboardViewModel()
    @StateObject private var aiHubVM = AIHubViewModel()
    @EnvironmentObject private var session: UserSession
    @EnvironmentObject private var preferences: UserPreferences
    @State private var sessionInfo: SessionInfo?
    @State private var mode: DashboardMode = .scan
```

- [ ] **Step 3: Add the segmented control and switch the body between scan content and AI Hub**

Find the whole `body`:

```swift
    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Seans banner — her zaman üstte görünür
                if let info = sessionInfo {
                    SessionBannerCard(session: info)
                        .padding(.horizontal)
                        .padding(.top, 8)
                        .padding(.bottom, 4)
                }
                MarketNewsTicker()
                headerControls
                Divider()
                content
                
                if !session.isPremium {
                    AdBannerPlaceholder()
                }
            }
            .navigationTitle(L("Piyasa Taraması"))
            .navigationBarTitleDisplayMode(.large)
            .toolbar { toolbarItems }
            .task {
                await vm.scan()
                sessionInfo = try? await APIService.shared.getSessionInfo()
            }
        }
    }
```

Replace with:

```swift
    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Seans banner — her zaman üstte görünür
                if let info = sessionInfo {
                    SessionBannerCard(session: info)
                        .padding(.horizontal)
                        .padding(.top, 8)
                        .padding(.bottom, 4)
                }
                MarketNewsTicker()

                Picker(L("Görünüm"), selection: $mode) {
                    Text(L("Piyasa Taraması")).tag(DashboardMode.scan)
                    Text(L("AI Önerileri")).tag(DashboardMode.aiHub)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                .padding(.vertical, 8)
                .background(Color(.systemBackground))

                if mode == .scan {
                    headerControls
                    Divider()
                    content

                    if !session.isPremium {
                        AdBannerPlaceholder()
                    }
                } else {
                    AIHubView(vm: aiHubVM)
                }
            }
            .navigationTitle(mode == .scan ? L("Piyasa Taraması") : L("AI Önerileri"))
            .navigationBarTitleDisplayMode(.large)
            .toolbar { toolbarItems }
            .task {
                await vm.scan()
                sessionInfo = try? await APIService.shared.getSessionInfo()
            }
        }
    }
```

- [ ] **Step 4: Make the toolbar refresh button mode-aware**

Find:

```swift
    @ToolbarContentBuilder
    private var toolbarItems: some ToolbarContent {
        ToolbarItem(placement: .navigationBarTrailing) {
            if vm.isLoading {
                ProgressView().tint(.accentColor)
            } else {
                Button { Task { await vm.scan() } } label: {
                    Image(systemName: "arrow.clockwise")
                }
            }
        }
    }
```

Replace with:

```swift
    @ToolbarContentBuilder
    private var toolbarItems: some ToolbarContent {
        ToolbarItem(placement: .navigationBarTrailing) {
            if mode == .scan {
                if vm.isLoading {
                    ProgressView().tint(.accentColor)
                } else {
                    Button { Task { await vm.scan() } } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            } else {
                if aiHubVM.isLoading {
                    ProgressView().tint(.accentColor)
                } else {
                    Button { Task { await aiHubVM.analyze() } } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
        }
    }
```

- [ ] **Step 5: Build to verify it compiles**

Run the build command from Global Constraints.
Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 6: Commit**

```bash
git add OptiTradeiOS/OptiTradeiOS/Views/DashboardView.swift
git commit -m "$(cat <<'EOF'
Add AI Önerileri segment to DashboardView, wiring in AIHubView

Piyasa Taraması / AI Önerileri picker replaces what used to be a
single fixed scan screen. Tab bar item count is unchanged (still 5)
— AI Hub is reachable without pushing Settings into the overflow
"More" tab.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Manual verification pass

**Files:** none (verification only)

- [ ] **Step 1: Full clean build**

```bash
cd "OptiTradeiOS" && xcodebuild -project OptiTradeiOS.xcodeproj -scheme OptiTradeiOS -destination 'generic/platform=iOS Simulator' -configuration Debug clean build
```

Expected: `** BUILD SUCCEEDED **`, zero warnings referencing `AIHubView.swift` or `DashboardView.swift`.

- [ ] **Step 2: Confirm the tab bar still shows exactly 5 items**

```bash
grep -c "\.tabItem" OptiTradeiOS/OptiTradeiOS/Views/ContentView.swift
```

Expected: `5`.

- [ ] **Step 3: Boot a simulator and run the app**

```bash
xcrun simctl list devices available | grep -m1 "iPhone"
```

Pick a UDID from the output, then:

```bash
xcrun simctl boot <UDID> 2>/dev/null; open -a Simulator
cd OptiTradeiOS && xcodebuild -project OptiTradeiOS.xcodeproj -scheme OptiTradeiOS -destination "id=<UDID>" -configuration Debug build
xcrun simctl install <UDID> "$(find ~/Library/Developer/Xcode/DerivedData -name 'OptiTradeiOS.app' -path '*Debug-iphonesimulator*' | head -1)"
xcrun simctl launch <UDID> com.algorix.optitrade
```

- [ ] **Step 4: Manually verify all three states**

In the running simulator, on the "Tarama" tab:
1. Confirm the new "Piyasa Taraması / AI Önerileri" segmented control appears below the news ticker.
2. Tap "AI Önerileri" with a non-premium test account (or a fresh account, since `isPremium` defaults to `false`). Confirm the upgrade card appears (sparkles icon, "AI Önerileri Premium Özelliktir", working "Avantajları Gör ve Yükselt" button that opens the `PremiumUpgradeView` sheet).
3. Toggle premium on (e.g. via a debug path already used to test premium features elsewhere, or via Settings if a manual toggle exists) and switch to "AI Önerileri" again. Confirm it loads real recommendation cards (or the existing loading/error state if the backend isn't reachable) instead of the upgrade card.
4. With an empty watchlist, confirm AI Hub still loads recommendations for the 3 fallback symbols (BTC-USD, AAPL, THYAO.IS) rather than erroring out.
5. Add a symbol to the watchlist (via the "Analiz" tab's search flow), return to "AI Önerileri", pull to refresh, and confirm the new symbol's recommendation appears.
6. Switch back to "Piyasa Taraması" and confirm the original scan list, sort menu, and market picker still work exactly as before.

- [ ] **Step 5: Record the outcome**

No commit for this task — it's verification only. If any manual check fails, fix the specific file/line involved and re-run the affected task's build-verification step before re-testing.
