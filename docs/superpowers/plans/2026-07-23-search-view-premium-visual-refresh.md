# SearchView Premium Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `SearchView`'s visual surfaces (search card icon, primary button, quick-symbol buttons, history tags, sector chips, suggestion rows) up to the app's established premium visual language (glow, gradient, soft shadow) while keeping full light/dark adaptivity.

**Architecture:** Purely additive `.overlay`/`.shadow`/`foregroundStyle` changes to existing views — no new files, no state/logic changes, no new components.

**Tech Stack:** SwiftUI. No XCTest target exists for `OptiTradeiOS` — verification in every task is `xcodebuild build` (compile-time correctness) plus, in the final task, a manual simulator screenshot check in both light and dark appearance.

## Global Constraints

- All background colors stay semantic/adaptive (`Color(.tertiarySystemBackground)`, `Color(.secondarySystemBackground)`, `.primary`, `.secondary`) — do not hardcode `Color.black` or other fixed colors; the screen must keep respecting `session.appTheme` (light/dark/system).
- `ResultCardView`, `SearchViewModel`'s logic, and all search/filter/history *behavior* are unchanged — this plan is visual-only.
- Every touched component keeps its existing `.accessibility(label:)` modifiers unchanged.
- Build command for every verification step:
  ```
  cd "OptiTradeiOS" && xcodebuild -project OptiTradeiOS.xcodeproj -scheme OptiTradeiOS -destination 'generic/platform=iOS Simulator' -configuration Debug build
  ```
  Run from repo root `/Users/hasantekbas/Downloads/Algorix Project Doc/OptiTrade/OptiTradeCode`. Expected final line: `** BUILD SUCCEEDED **`.

---

## Task 1: Search card icon glow + gradient Analiz Et button

**Files:**
- Modify: `OptiTradeiOS/OptiTradeiOS/Views/SearchView.swift` (`searchCard`, currently lines 169-257)

**Interfaces:** None — pure view-body changes inside `searchCard`, no new properties, no signature changes.

- [ ] **Step 1: Wrap the magnifying-glass icon in a glow circle**

Find:

```swift
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.accentColor)
                TextField(
                    "Sembol girin (örn: THYAO, BTC, AAPL...)",
                    text: $vm.symbol
                )
```

Replace with:

```swift
            HStack(spacing: 10) {
                ZStack {
                    Circle()
                        .fill(
                            RadialGradient(colors: [Color.accentColor.opacity(0.15), .clear], center: .center, startRadius: 0, endRadius: 18)
                        )
                        .frame(width: 36, height: 36)
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(
                            LinearGradient(colors: [Color.accentColor, Color.accentColor.opacity(0.7)], startPoint: .topLeading, endPoint: .bottomTrailing)
                        )
                }
                TextField(
                    "Sembol girin (örn: THYAO, BTC, AAPL...)",
                    text: $vm.symbol
                )
```

- [ ] **Step 2: Give the "Analiz Et" button a gradient fill and softer glow when enabled**

Find:

```swift
            Button {
                fieldFocused = false
                Task { await vm.analyze() }
            } label: {
                HStack(spacing: 8) {
                    if vm.isLoading {
                        ProgressView().tint(.white)
                    } else {
                        Image(systemName: "sparkles")
                    }
                    Text(vm.isLoading ? L("Analiz ediliyor...") : L("Analiz Et"))
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 52)
                .background(vm.symbol.isEmpty ? Color.gray.opacity(0.3) : Color.accentColor)
                .foregroundColor(vm.symbol.isEmpty ? .secondary : .white)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .shadow(color: vm.symbol.isEmpty ? .clear : Color.accentColor.opacity(0.3), radius: 8, y: 4)
            }
            .disabled(vm.symbol.isEmpty)
```

Replace with:

```swift
            Button {
                fieldFocused = false
                Task { await vm.analyze() }
            } label: {
                HStack(spacing: 8) {
                    if vm.isLoading {
                        ProgressView().tint(.white)
                    } else {
                        Image(systemName: "sparkles")
                    }
                    Text(vm.isLoading ? L("Analiz ediliyor...") : L("Analiz Et"))
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 52)
                .background(
                    vm.symbol.isEmpty
                        ? AnyShapeStyle(Color.gray.opacity(0.3))
                        : AnyShapeStyle(LinearGradient(colors: [Color.accentColor, Color.accentColor.opacity(0.8)], startPoint: .leading, endPoint: .trailing))
                )
                .foregroundColor(vm.symbol.isEmpty ? .secondary : .white)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .shadow(color: vm.symbol.isEmpty ? .clear : Color.accentColor.opacity(0.3), radius: 10, y: 5)
            }
            .disabled(vm.symbol.isEmpty)
```

(`AnyShapeStyle` type-erases `Color` and `LinearGradient` to a common type
so the ternary compiles — SwiftUI's `.background(_:)` needs both branches
of a conditional to be the same concrete type.)

- [ ] **Step 3: Build to verify it compiles**

Run the build command from Global Constraints.
Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 4: Commit**

```bash
git add OptiTradeiOS/OptiTradeiOS/Views/SearchView.swift
git commit -m "$(cat <<'EOF'
Add glow/gradient accents to SearchView's search card

Magnifying-glass icon gets a radial-gradient glow circle and
gradient foreground (matching OnboardingView's icon treatment,
scaled down for inline use); the "Analiz Et" button gets a
gradient fill and softer shadow when enabled, matching
OnboardingView.nextButton's glow values. Disabled state is
untouched (flat gray, no glow — glow implies actionable).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Depth treatment for QuickSymbolButton, SearchHistoryTag, SectorChip

**Files:**
- Modify: `OptiTradeiOS/OptiTradeiOS/Components/Components.swift` (`SearchHistoryTag`, `QuickSymbolButton`, `SectorChip`)

**Interfaces:** None — pure view-body changes, no property/init signature changes. These three components are confirmed used exclusively by `SearchView.swift` (`grep -rln "QuickSymbolButton(\|SearchHistoryTag(\|SectorChip(" OptiTradeiOS/OptiTradeiOS/Views/*.swift` returns only `SearchView.swift`), so these changes are scoped to the Analiz tab even though the components live in the shared `Components.swift` file.

- [ ] **Step 1: Add a decision-colored border to `SearchHistoryTag`**

Find:

```swift
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color(.tertiarySystemBackground))
        .clipShape(Capsule())
        .onTapGesture(perform: onTap)
        .animation(.spring(response: 0.3), value: item.id)
        .accessibility(label: Text("\(item.symbol) - Puan: \(item.score)"))
    }
}

struct QuickSymbolButton: View {
```

Replace with:

```swift
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color(.tertiarySystemBackground))
        .clipShape(Capsule())
        .overlay(
            Capsule()
                .strokeBorder(color.opacity(0.25), lineWidth: 1)
        )
        .onTapGesture(perform: onTap)
        .animation(.spring(response: 0.3), value: item.id)
        .accessibility(label: Text("\(item.symbol) - Puan: \(item.score)"))
    }
}

struct QuickSymbolButton: View {
```

- [ ] **Step 2: Add a border + soft shadow to `QuickSymbolButton`**

Find:

```swift
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(Color(.tertiarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(ScaleButtonStyle())
        .accessibility(label: Text("\(displayName) - \(symbol) \(L("sembolü"))"))
    }
}
```

Replace with:

```swift
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(Color(.tertiarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(Color.accentColor.opacity(0.15), lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.08), radius: 4, y: 2)
        }
        .buttonStyle(ScaleButtonStyle())
        .accessibility(label: Text("\(displayName) - \(symbol) \(L("sembolü"))"))
    }
}
```

- [ ] **Step 3: Add a glow shadow to `SectorChip` when selected**

Find:

```swift
    var body: some View {
        Button(action: onTap) {
            Text(L(title))
                .font(.caption.weight(.semibold))
                .foregroundColor(isSelected ? .white : .primary)
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .background(isSelected ? Color.accentColor : Color(.tertiarySystemBackground))
                .clipShape(Capsule())
        }
        .buttonStyle(ScaleButtonStyle())
        .accessibility(label: Text("\(L(title)) \(L("sektörü")) - \(isSelected ? L("seçili") : L("seçili değil"))"))
    }
}
```

Replace with:

```swift
    var body: some View {
        Button(action: onTap) {
            Text(L(title))
                .font(.caption.weight(.semibold))
                .foregroundColor(isSelected ? .white : .primary)
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .background(isSelected ? Color.accentColor : Color(.tertiarySystemBackground))
                .clipShape(Capsule())
                .shadow(color: isSelected ? Color.accentColor.opacity(0.3) : .clear, radius: 6, y: 3)
        }
        .buttonStyle(ScaleButtonStyle())
        .accessibility(label: Text("\(L(title)) \(L("sektörü")) - \(isSelected ? L("seçili") : L("seçili değil"))"))
    }
}
```

- [ ] **Step 4: Build to verify it compiles**

Run the build command from Global Constraints.
Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 5: Commit**

```bash
git add OptiTradeiOS/OptiTradeiOS/Components/Components.swift
git commit -m "$(cat <<'EOF'
Add depth (border/shadow) to SearchView's quick-access components

QuickSymbolButton and SearchHistoryTag get a subtle accent/decision-
colored border plus a soft shadow; SectorChip gets a glow shadow
when selected, matching the "lit up" treatment used elsewhere for
active/selected elements. All three are exclusively used by
SearchView, confirmed via grep, so this is scoped to the Analiz tab
despite living in the shared Components.swift file.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Depth treatment for the suggestions row container

**Files:**
- Modify: `OptiTradeiOS/OptiTradeiOS/Views/SearchView.swift` (`suggestionsSection`, currently lines 302-341)

**Interfaces:** None.

- [ ] **Step 1: Add a border + soft shadow to the suggestions container**

Find:

```swift
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    private var historySection: some View {
```

Replace with:

```swift
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(Color.accentColor.opacity(0.12), lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.06), radius: 4, y: 2)
        }
    }

    private var historySection: some View {
```

- [ ] **Step 2: Build to verify it compiles**

Run the build command from Global Constraints.
Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 3: Commit**

```bash
git add OptiTradeiOS/OptiTradeiOS/Views/SearchView.swift
git commit -m "$(cat <<'EOF'
Add depth to SearchView's suggestions row container

Matches the border+shadow treatment applied to QuickSymbolButton
and the suggestions section in the prior two commits, so the
autocomplete list reads consistently with the rest of the
browsing/empty state.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Manual verification pass (light + dark)

**Files:** none (verification only)

- [ ] **Step 1: Full clean build**

```bash
cd "OptiTradeiOS" && xcodebuild -project OptiTradeiOS.xcodeproj -scheme OptiTradeiOS -destination 'generic/platform=iOS Simulator' -configuration Debug clean build
```

Expected: `** BUILD SUCCEEDED **`, zero warnings referencing `SearchView.swift` or `Components.swift`.

- [ ] **Step 2: Boot a simulator, launch the app, capture the Analiz tab in both appearances**

```bash
xcrun simctl list devices available | grep -m1 "iPhone"
```

Pick a UDID, then:

```bash
xcrun simctl boot <UDID> 2>/dev/null
xcrun simctl bootstatus <UDID> -b
cd OptiTradeiOS && xcodebuild -project OptiTradeiOS.xcodeproj -scheme OptiTradeiOS -destination "id=<UDID>" -configuration Debug build
xcrun simctl install <UDID> "$(find ~/Library/Developer/Xcode/DerivedData -name 'OptiTradeiOS.app' -path '*Debug-iphonesimulator*' | head -1)"
xcrun simctl ui <UDID> appearance dark
xcrun simctl launch <UDID> com.algorix.optitrade
xcrun simctl io <UDID> screenshot /tmp/search-view-dark.png
xcrun simctl ui <UDID> appearance light
xcrun simctl terminate <UDID> com.algorix.optitrade
xcrun simctl launch <UDID> com.algorix.optitrade
xcrun simctl io <UDID> screenshot /tmp/search-view-light.png
```

Note: the app launches on the "Tarama" tab by default — if interactive
tapping isn't possible in this environment (no GUI-automation/accessibility
access), note that explicitly, report what the screenshots show for the
default tab, and hand off tapping into "Analiz" to the user for final
confirmation.

- [ ] **Step 3: Visually confirm from whichever screenshots are reachable**

Check in both light and dark:
1. Search-field magnifying-glass icon has a soft glow circle behind it (subtle, not a hard-edged shape).
2. The "Analiz Et" button has a visible gradient (not flat) fill and a soft glow shadow beneath it — text stays legible (white on accent) in both themes.
3. Quick-access symbol buttons (`QuickSymbolButton`, visible when the search field is empty) have a faint border and a very soft drop shadow — should read as "slightly raised," not as a hard outline.
4. If any sector chip is selected (`SectorChip`), it has a soft accent-colored glow beneath it.
5. If search history exists (`SearchHistoryTag`), tags show a thin colored border matching their BUY/SELL/neutral dot color.
6. None of the above breaks light-mode legibility — glow/shadow opacities should read as subtle in light mode, not muddy or overly dark.

- [ ] **Step 4: Record the outcome**

No commit for this task — it's verification only. If any check fails, fix the specific file/line involved and re-run the affected task's build-verification step before re-testing.
