# Dashboard Layout Declutter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `DashboardView`'s fixed (non-scrolling) header from five stacked rows to two, by compacting the market picker + sort row into one line and moving `SessionBannerCard`/`MarketNewsTicker` into the scrollable content.

**Architecture:** `headerControls` becomes a single `HStack` (compact-width market picker + sort menu). `content` becomes a single outer `ScrollView` that always renders the session banner and news ticker first, then switches on loading/error/results/empty state for the rest — replacing today's four independent per-state containers (a `ScrollView` for loading, bare `VStack`s for error/empty, `resultsView`'s own `ScrollView`).

**Tech Stack:** SwiftUI. No XCTest target exists for `OptiTradeiOS` — verification in every task is `xcodebuild build` (compile-time correctness) plus, in the final task, a manual simulator screenshot check.

## Global Constraints

- `SessionBannerCard`, `MarketNewsTicker`, `ScanSummaryBanner`, `SectorOpportunityMiniCard`, and `ResultCardView`'s internal layout/content must not change — only their position in the view tree moves.
- AI Hub mode (`mode == .aiHub`) must be unaffected — its fixed header stays exactly one row (the mode `Picker`).
- `AdBannerPlaceholder` stays pinned below the scroll view for non-premium users — do not move it into scrollable content.
- Every string already wrapped in `L(...)` must stay wrapped; no new user-facing strings are introduced by this plan.
- Build command for every verification step:
  ```
  cd "OptiTradeiOS" && xcodebuild -project OptiTradeiOS.xcodeproj -scheme OptiTradeiOS -destination 'generic/platform=iOS Simulator' -configuration Debug build
  ```
  Run from repo root `/Users/hasantekbas/Downloads/Algorix Project Doc/OptiTrade/OptiTradeCode`. Expected final line: `** BUILD SUCCEEDED **`.

---

## Task 1: Compact the market picker + sort row into one line

**Files:**
- Modify: `OptiTradeiOS/OptiTradeiOS/Views/DashboardView.swift` (`headerControls`, currently lines 96-146)

**Interfaces:**
- Consumes: `DashboardViewModel.selectedMarket: String` (`@Published`, unchanged), `DashboardViewModel.sortBy: ScanSort` (`@Published`, unchanged), `DashboardViewModel.scan() async` (unchanged)
- Produces: `headerControls: some View` — same property name/type, callers (`body`) don't change

- [ ] **Step 1: Replace `headerControls` with a one-row layout**

Find:

```swift
    private var headerControls: some View {
        VStack(spacing: 8) {
            Picker(L("Piyasa"), selection: $vm.selectedMarket) {
                Text(L("Hisse")).tag("bist")
                Text(L("Kripto")).tag("crypto")
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .onChange(of: vm.selectedMarket) { Task { await vm.scan() } }

            HStack {
                Menu {
                    ForEach(ScanSort.allCases, id: \.self) { s in
                        Button {
                            vm.sortBy = s
                        } label: {
                            if vm.sortBy == s {
                                Label(L(s.rawValue), systemImage: "checkmark")
                            } else {
                                Text(L(s.rawValue))
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.up.arrow.down")
                            .font(.caption)
                        Text(L(vm.sortBy.rawValue))
                            .font(.caption)
                    }
                    .foregroundColor(.accentColor)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Color.accentColor.opacity(0.1))
                    .clipShape(Capsule())
                }

                Spacer()

                if let t = vm.lastScanned {
                    Text("\(L("Son tarama")): \(t, style: .time)")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
            .padding(.horizontal)
            .padding(.bottom, 8)
        }
        .padding(.top, 8)
        .background(Color(.systemBackground))
    }
```

Replace with:

```swift
    private var headerControls: some View {
        HStack(spacing: 12) {
            Picker(L("Piyasa"), selection: $vm.selectedMarket) {
                Text(L("Hisse")).tag("bist")
                Text(L("Kripto")).tag("crypto")
            }
            .pickerStyle(.segmented)
            .frame(width: 160)
            .onChange(of: vm.selectedMarket) { Task { await vm.scan() } }

            Menu {
                ForEach(ScanSort.allCases, id: \.self) { s in
                    Button {
                        vm.sortBy = s
                    } label: {
                        if vm.sortBy == s {
                            Label(L(s.rawValue), systemImage: "checkmark")
                        } else {
                            Text(L(s.rawValue))
                        }
                    }
                }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "arrow.up.arrow.down")
                        .font(.caption)
                    Text(L(vm.sortBy.rawValue))
                        .font(.caption)
                }
                .foregroundColor(.accentColor)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(Color.accentColor.opacity(0.1))
                .clipShape(Capsule())
            }

            Spacer()
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color(.systemBackground))
    }
```

Note: the `"Son tarama"` (last-scanned time) `Text` that used to sit in this row is intentionally dropped here — Task 2 re-adds it inside the scrollable results content instead, right above `ScanSummaryBanner`. Do not delete `DashboardViewModel.lastScanned` — it's still set by `scan()` and still read in Task 2.

- [ ] **Step 2: Build to verify it compiles**

Run the build command from Global Constraints.
Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 3: Commit**

```bash
git add OptiTradeiOS/OptiTradeiOS/Views/DashboardView.swift
git commit -m "$(cat <<'EOF'
Compact Dashboard's market picker + sort menu into one row

Was two full-width rows (segmented market picker, then a separate
sort-menu/timestamp row). The market picker now has a fixed width
so it can share a row with the sort menu, cutting the scan tab's
fixed header from three rows to two (market/sort + the mode picker
above it).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Move session banner + news ticker into scrollable content

**Files:**
- Modify: `OptiTradeiOS/OptiTradeiOS/Views/DashboardView.swift` (`body`, `content`, `resultsView` → renamed `resultsContent`)

**Interfaces:**
- Consumes: `SessionBannerCard(session: SessionInfo)` (`OptiTradeiOS/OptiTradeiOS/Views/SessionInfoView.swift`, unchanged init), `MarketNewsTicker()` (`OptiTradeiOS/OptiTradeiOS/Views/MarketNewsView.swift`, unchanged, no-arg, self-hides when there's no news), `DashboardView.sessionInfo: SessionInfo?` (`@State`, unchanged, still populated by `body`'s `.task`)
- Produces: `content: some View` (same name, now a single `ScrollView` instead of `@ViewBuilder` branching over four containers — drop the `@ViewBuilder` attribute since it now has one unconditional return), a new `private func resultsContent(_ scan: ScanResult) -> some View` (replaces `resultsView(_:)` — same parameter, but `@ViewBuilder`-returns bare content instead of owning its own `ScrollView`, since the `ScrollView` now lives in `content`)

- [ ] **Step 1: Remove the session banner + news ticker block from `body`**

Find:

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
```

Replace with:

```swift
    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker(L("Görünüm"), selection: $mode) {
```

(Everything else in `body` — the rest of the `Picker`, the `if mode == .scan { ... } else { ... }` block, `.navigationTitle`, `.toolbar`, `.task` — is unchanged.)

- [ ] **Step 2: Replace `content` and `resultsView` with a unified `content` + `resultsContent`**

Find (this spans the current `content` and `resultsView`, ending right before `// MARK: - SectorOpportunityMiniCard`):

```swift
    @ViewBuilder
    private var content: some View {
        if vm.isLoading {
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(0..<5, id: \.self) { _ in
                        SkeletonResultCard()
                            .padding(.horizontal)
                    }
                }
                .padding(.vertical, 8)
            }
        } else if let error = vm.errorMessage {
            Spacer()
            VStack(spacing: 12) {
                Image(systemName: "wifi.exclamationmark")
                    .font(.system(size: 44))
                    .foregroundColor(.orange)
                Text(error)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
                Button(L("Tekrar Dene")) { Task { await vm.scan() } }
                    .foregroundColor(.accentColor)
            }
            Spacer()
        } else if let scan = vm.scanResult {
            resultsView(scan)
        } else {
            Spacer()
            EmptyStateView(
                icon: "chart.bar.xaxis",
                title: "Tarama Başlatılıyor",
                subtitle: "Veriler yükleniyor..."
            )
            Spacer()
        }
    }

    private func resultsView(_ scan: ScanResult) -> some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                ScanSummaryBanner(scan: scan)
                    .padding(.horizontal)
                    .padding(.top, 4)

                // Sektör Fırsat Kartı
                NavigationLink(destination: SectorOpportunityView()
                    .environmentObject(preferences)) {
                    SectorOpportunityMiniCard()
                }
                .buttonStyle(.plain)
                .padding(.horizontal)

                if !scan.topBuys.isEmpty {
                    SectionHeaderView(title: "AL Sinyalleri", count: scan.topBuys.count, color: .green)
                        .padding(.horizontal)
                    ForEach(vm.sorted(scan.topBuys)) { r in
                        NavigationLink(destination: AnalysisDetailView(result: r)) {
                            ResultCardView(result: r)
                        }
                        .buttonStyle(.plain)
                        .padding(.horizontal)
                    }
                }

                if !scan.topSells.isEmpty {
                    SectionHeaderView(title: "SAT Sinyalleri", count: scan.topSells.count, color: .red)
                        .padding(.horizontal)
                    ForEach(vm.sorted(scan.topSells)) { r in
                        NavigationLink(destination: AnalysisDetailView(result: r)) {
                            ResultCardView(result: r)
                        }
                        .buttonStyle(.plain)
                        .padding(.horizontal)
                    }
                }

                let showNeutral = session.showNeutralInScan || (scan.topBuys.isEmpty && scan.topSells.isEmpty)
                if showNeutral && !scan.neutral.isEmpty {
                    let title = (scan.topBuys.isEmpty && scan.topSells.isEmpty)
                        ? L("En Yüksek Puanlı Hisseler") : L("Nötr")
                    let color: Color = (scan.topBuys.isEmpty && scan.topSells.isEmpty) ? .blue : .orange
                    let neutralSorted = scan.neutral.sorted { $0.score > $1.score }
                    let displayed = (scan.topBuys.isEmpty && scan.topSells.isEmpty)
                        ? Array(neutralSorted.prefix(8)) : neutralSorted
                    SectionHeaderView(title: title, count: displayed.count, color: color)
                        .padding(.horizontal)
                    ForEach(displayed) { r in
                        NavigationLink(destination: AnalysisDetailView(result: r)) {
                            ResultCardView(result: r)
                        }
                        .buttonStyle(.plain)
                        .padding(.horizontal)
                    }
                }

                Text("\(scan.totalScanned) \(L("sembol tarandı"))")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.vertical, 4)

                VStack(spacing: 4) {
                    Divider()
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.caption2)
                            .foregroundColor(.orange)
                        Text(L("Gösterilen sinyaller yatırım tavsiyesi değildir."))
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    HStack(spacing: 4) {
                        Text("Product by AlgorixStudio  •")
                            .foregroundColor(.secondary.opacity(0.5))
                        Link("algorixstudio.com", destination: URL(string: "https://algorixstudio.com")!)
                            .foregroundColor(.secondary.opacity(0.8))
                    }
                    .font(.caption2)
                    .tracking(0.5)
                }
                .padding(.bottom, 16)
            }
            .padding(.vertical, 8)
        }
        .refreshable { await vm.scan() }
    }
```

Replace with:

```swift
    private var content: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                if let info = sessionInfo {
                    SessionBannerCard(session: info)
                        .padding(.horizontal)
                        .padding(.top, 8)
                }
                MarketNewsTicker()

                if vm.isLoading {
                    ForEach(0..<5, id: \.self) { _ in
                        SkeletonResultCard()
                            .padding(.horizontal)
                    }
                } else if let error = vm.errorMessage {
                    VStack(spacing: 12) {
                        Image(systemName: "wifi.exclamationmark")
                            .font(.system(size: 44))
                            .foregroundColor(.orange)
                        Text(error)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                        Button(L("Tekrar Dene")) { Task { await vm.scan() } }
                            .foregroundColor(.accentColor)
                    }
                    .padding(.top, 60)
                } else if let scan = vm.scanResult {
                    resultsContent(scan)
                } else {
                    EmptyStateView(
                        icon: "chart.bar.xaxis",
                        title: "Tarama Başlatılıyor",
                        subtitle: "Veriler yükleniyor..."
                    )
                    .padding(.top, 60)
                }
            }
            .padding(.vertical, 8)
        }
        .refreshable { await vm.scan() }
    }

    @ViewBuilder
    private func resultsContent(_ scan: ScanResult) -> some View {
        ScanSummaryBanner(scan: scan)
            .padding(.horizontal)
            .padding(.top, 4)

        if let t = vm.lastScanned {
            Text("\(L("Son tarama")): \(t, style: .time)")
                .font(.caption2)
                .foregroundColor(.secondary)
                .padding(.horizontal)
        }

        // Sektör Fırsat Kartı
        NavigationLink(destination: SectorOpportunityView()
            .environmentObject(preferences)) {
            SectorOpportunityMiniCard()
        }
        .buttonStyle(.plain)
        .padding(.horizontal)

        if !scan.topBuys.isEmpty {
            SectionHeaderView(title: "AL Sinyalleri", count: scan.topBuys.count, color: .green)
                .padding(.horizontal)
            ForEach(vm.sorted(scan.topBuys)) { r in
                NavigationLink(destination: AnalysisDetailView(result: r)) {
                    ResultCardView(result: r)
                }
                .buttonStyle(.plain)
                .padding(.horizontal)
            }
        }

        if !scan.topSells.isEmpty {
            SectionHeaderView(title: "SAT Sinyalleri", count: scan.topSells.count, color: .red)
                .padding(.horizontal)
            ForEach(vm.sorted(scan.topSells)) { r in
                NavigationLink(destination: AnalysisDetailView(result: r)) {
                    ResultCardView(result: r)
                }
                .buttonStyle(.plain)
                .padding(.horizontal)
            }
        }

        let showNeutral = session.showNeutralInScan || (scan.topBuys.isEmpty && scan.topSells.isEmpty)
        if showNeutral && !scan.neutral.isEmpty {
            let title = (scan.topBuys.isEmpty && scan.topSells.isEmpty)
                ? L("En Yüksek Puanlı Hisseler") : L("Nötr")
            let color: Color = (scan.topBuys.isEmpty && scan.topSells.isEmpty) ? .blue : .orange
            let neutralSorted = scan.neutral.sorted { $0.score > $1.score }
            let displayed = (scan.topBuys.isEmpty && scan.topSells.isEmpty)
                ? Array(neutralSorted.prefix(8)) : neutralSorted
            SectionHeaderView(title: title, count: displayed.count, color: color)
                .padding(.horizontal)
            ForEach(displayed) { r in
                NavigationLink(destination: AnalysisDetailView(result: r)) {
                    ResultCardView(result: r)
                }
                .buttonStyle(.plain)
                .padding(.horizontal)
            }
        }

        Text("\(scan.totalScanned) \(L("sembol tarandı"))")
            .font(.caption)
            .foregroundColor(.secondary)
            .padding(.vertical, 4)

        VStack(spacing: 4) {
            Divider()
            HStack(spacing: 6) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.caption2)
                    .foregroundColor(.orange)
                Text(L("Gösterilen sinyaller yatırım tavsiyesi değildir."))
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            HStack(spacing: 4) {
                Text("Product by AlgorixStudio  •")
                    .foregroundColor(.secondary.opacity(0.5))
                Link("algorixstudio.com", destination: URL(string: "https://algorixstudio.com")!)
                    .foregroundColor(.secondary.opacity(0.8))
            }
            .font(.caption2)
            .tracking(0.5)
        }
        .padding(.bottom, 16)
    }
```

- [ ] **Step 3: Build to verify it compiles**

Run the build command from Global Constraints.
Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 4: Commit**

```bash
git add OptiTradeiOS/OptiTradeiOS/Views/DashboardView.swift
git commit -m "$(cat <<'EOF'
Move session banner + news ticker into Dashboard's scrollable content

They used to sit above the fixed header (visible in every state:
loading, error, results, empty) as two more stacked rows. content
is now a single ScrollView with them as its first items, so they
scroll away with the rest of the content instead of permanently
occupying screen space above it. The "Son tarama" timestamp moves
from the (now one-row) header into the results content, next to
ScanSummaryBanner.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Manual verification pass

**Files:** none (verification only)

- [ ] **Step 1: Full clean build**

```bash
cd "OptiTradeiOS" && xcodebuild -project OptiTradeiOS.xcodeproj -scheme OptiTradeiOS -destination 'generic/platform=iOS Simulator' -configuration Debug clean build
```

Expected: `** BUILD SUCCEEDED **`, zero warnings referencing `DashboardView.swift`.

- [ ] **Step 2: Boot a simulator, run the app, screenshot the Tarama tab**

```bash
xcrun simctl list devices available | grep -m1 "iPhone"
```

Pick a UDID, then:

```bash
xcrun simctl boot <UDID> 2>/dev/null
xcrun simctl bootstatus <UDID> -b
cd OptiTradeiOS && xcodebuild -project OptiTradeiOS.xcodeproj -scheme OptiTradeiOS -destination "id=<UDID>" -configuration Debug build
xcrun simctl install <UDID> "$(find ~/Library/Developer/Xcode/DerivedData -name 'OptiTradeiOS.app' -path '*Debug-iphonesimulator*' | head -1)"
xcrun simctl launch <UDID> com.algorix.optitrade
xcrun simctl io <UDID> screenshot /tmp/dashboard-declutter.png
```

- [ ] **Step 3: Visually confirm from the screenshot (and describe what you see)**

Check:
1. Fixed header (everything above the first `Divider()`) is exactly two rows: the "Piyasa Taraması / AI Önerileri" mode picker, then a single row with a compact (not full-width) Hisse/Kripto segmented control and the sort-menu capsule beside it.
2. `SessionBannerCard` and any news ticker content are NOT in the fixed header — they should appear as the first items inside the scrollable area below the divider (visible on initial load if the backend responds in time, or absent if `sessionInfo`/news are still loading — either is correct, since they're now conditionally rendered inside the scroll like everything else).
3. Tab bar still shows exactly 5 items (`grep -c "\.tabItem" OptiTradeiOS/OptiTradeiOS/Views/ContentView.swift` → `5`) — this plan doesn't touch the tab bar, this is a regression guard.
4. Switch to "AI Önerileri" mode (if interactive tapping is available in this environment) and confirm its fixed header is still exactly one row (the mode picker) — Task 2 didn't touch anything under `mode == .aiHub`, so this should be unaffected, but confirm no compile-time interaction broke it.

If interactive tapping isn't possible in this environment (no GUI-automation/accessibility access), note that explicitly and report what was verified automatically (build, tab count, screenshot of the default scan-mode state) versus what needs a human to confirm by hand (mode switch, pull-to-refresh, scrolling to confirm session banner/ticker scroll away).

- [ ] **Step 4: Record the outcome**

No commit for this task — it's verification only. If any check fails, fix the specific file/line involved and re-run the affected task's build-verification step before re-testing.
