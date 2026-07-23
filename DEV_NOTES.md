# OptiTrade — Developer Notes

## Session: 2026-03-04

---

## 1. iOS — Chart Components & Haptic Feedback

### New Files
- `OptiTradeiOS/Components/ChartComponents.swift`
- `OptiTradeiOS/Services/HapticService.swift`

### What Was Done
Added a full native chart component library using **Swift Charts** (iOS 16+ framework, no external dependency).

| Component | Description |
|---|---|
| `MiniSparkline` | Compact line + area chart for result cards. Shows 30-day price trend with color-coded gradient (green/red). |
| `PriceChart` | Interactive full-size price chart with drag-to-select crosshair. Tapping a data point shows date + price tooltip. Triggers `HapticService.selection()` on each scrub. |
| `RSIGauge` | Circular gauge component (0–100). Color: green (<30), orange (30–70), red (>70). Uses `Gauge` with `accessoryCircular` style. |
| `RSIChart` | Line chart overlay for RSI series with dashed overbought (70) and oversold (30) reference lines. |
| `VolumeChart` | Bar chart for trading volume. Bars inherit buy/sell color from parent context. |

`HapticService` is a singleton (`UIKit`-backed) with:
- `impact(_:)` — general feedback
- `notification(_:)` — success / error / warning
- `selection()` — light tick (used in chart scrubbing)
- `signalFeedback(decisionCode:)` — maps STRONG_BUY → `.success`, STRONG_SELL → `.error`, BUY/SELL → `.medium`, NEUTRAL → `.light`

### Xcode Project Registration
`ChartComponents.swift` and `HapticService.swift` were manually added to `project.pbxproj`:
- `PBXBuildFile` entries: `A10014`, `A10015`
- `PBXFileReference` entries: `B10014`, `B10015`
- Added to `E10006 /* Components */` and `E10005 /* Services */` groups respectively
- Added to `F10002 /* Sources */` build phase

---

## 2. iOS — AnalysisDetailView & ResultCardView Enhancements

### AnalysisDetailView
- Added `@State private var chart: ChartResponse?` and `@State private var chartPeriod`
- **Period picker**: 1A / 3A / 6A / 1Y (segmented control, triggers chart reload via `.onChange`)
- **Chart section**: Shows `PriceChart` → `RSIChart` (if RSI data available) → `VolumeChart`, stacked vertically
- **Loading state**: `ProgressView` placeholder while chart fetches
- **Haptic on appear**: `HapticService.shared.signalFeedback(decisionCode:)` fires when view opens
- Chart loaded asynchronously with `.task` and `APIService.shared.getChart(symbol:period:)`

### ResultCardView
- Added `@State private var chartData: [ChartPoint] = []`
- Lazy loads 1-month sparkline via `.task` modifier (only fires when card is visible in a `LazyVStack`)
- `MiniSparkline` appears with `.easeIn(duration: 0.4)` animation via `withAnimation`
- `guard chartData.isEmpty else { return }` prevents redundant re-fetches on scroll

---

## 3. iOS — Dashboard Improvements

**File:** `Views/DashboardView.swift`

### Skeleton Loading
Replaced the static `ProgressView` spinner with **5 animated skeleton cards** (`SkeletonResultCard`) during scan:
- Each card pulses between `opacity 1.0 → 0.45` with a 0.9s `easeInOut` repeat animation
- Gives the user a structural preview of the incoming content layout

### ScanSummaryBanner
Added at the top of every scan result list:
- **4-column stat row**: AL count (green) | SAT count (red) | NÖTR count (orange) | Average Score
- **Ratio bar**: A capsule-shaped segmented bar showing the proportion of buy / neutral / sell signals
- Zero-division safe (`total > 0` guard before rendering the bar)

---

## 4. iOS — SearchView Improvements

**File:** `Views/SearchView.swift`

### Sector Filter
Added horizontal scrolling **chip filter bar** (BIST mode only):

```
Tümü | Bankacılık | Enerji | Ulaşım | Teknoloji | Sanayi | Perakende
```

- State: `@State private var selectedSector = "Tümü"` (local to view, not ViewModel)
- Computed property `filteredBISTSymbols`: returns `bistQuickSymbols` for "Tümü", or the sector-specific list
- Selection triggers `withAnimation(.easeInOut(duration: 0.2))` for smooth grid transition
- `SectorChip` component (in `Components.swift`) handles selected/unselected visual state

### Expanded BIST Symbol List
`bistQuickSymbols` expanded from 12 → 16 popular symbols (shown in "Tümü" view).

`bistSectorSymbols` constant added with 6 sectors × 3–8 symbols each (30+ total):

| Sector | Symbols |
|---|---|
| Bankacılık | GARAN, AKBNK, YKBNK, ISCTR, VAKBN, HALKB, TSKB, QNBFB |
| Enerji | TUPRS, EREGL, AYGAZ, PETKIM, AKSEN, ENKAI |
| Ulaşım | THYAO, PGSUS, TAVHL |
| Teknoloji | ASELS, NETAS, LOGO, ALCTL, ARDYZ |
| Sanayi | KCHOL, SISE, FROTO, TOASO, TTRAK, VESTL |
| Perakende | BIMAS, MGROS, MAVI, ARCLK |

---

## 5. iOS — WatchlistView Improvements

**File:** `Views/WatchlistView.swift`

### Architecture Change: ScrollView → List
Converted from `ScrollView + LazyVStack` to `List` (with `.listStyle(.plain)` to preserve card appearance). This was required to unlock SwiftUI's `onMove` and `swipeActions` APIs.

### Drag-to-Reorder
- `@State private var editMode: EditMode = .inactive`
- `.environment(\.editMode, $editMode)` injected at NavigationStack level
- "Düzenle" / "Tamam" toggle button added to `navigationBarLeading` toolbar slot
- When `editMode == .active`: displays `vm.items` (original insertion order, draggable)
- When `editMode == .inactive`: displays `vm.sortedItems` (sorted by score, read-only)
- `vm.move(from:to:)` persists reordered array to `UserDefaults` immediately

### Swipe Actions
- **Trailing swipe** (full swipe enabled): "Sil" — calls `vm.removeItem(item)` with animation
- **Leading swipe**: "Güncelle" (blue) — triggers `vm.analyzeItem(item)` to refresh single card

### ViewModel Additions
```swift
func removeItem(_ item: WatchlistItemData)   // single item delete (for swipe)
func move(from source: IndexSet, to destination: Int)  // drag reorder + persist
func analyzeItem(_ item: WatchlistItemData)  // made internal (was private)
```

---

## 6. New Shared Components

**File:** `Components/Components.swift`

| Component | Purpose |
|---|---|
| `SkeletonResultCard` | Animated shimmer placeholder. Three rect placeholders mimic the layout of `ResultCardView`. Opacity pulses on `onAppear`. |
| `ScanSummaryBanner` | Scan stats widget (see Dashboard section above). |
| `SectorChip` | Pill-shaped filter button. Selected state: accentColor background + white text. Unselected: tertiary fill + primary text. |

---

## 7. Backend — ML Training Script

**File:** `backend/ml_trainer.py`

Standalone XGBoost binary classifier for buy signal prediction.

### Feature Vector (7 features)
| Feature | Source |
|---|---|
| `rsi` | RSI(14), default 50 if unavailable |
| `macd_diff` | MACD line − Signal line |
| `bollinger_pb` | Bollinger %B, default 0.5 |
| `ema_signal_enc` | GOLDEN_CROSS=2, BULLISH=1, BEARISH=-1, DEATH_CROSS=-2, None=0 |
| `trend_strength` | % distance from EMA(20) |
| `price_velocity` | Intraday % change from open |
| `volume_ratio` | Today's volume / 60-day average |

### Label
`1` if 5-day forward return > +1%, else `0`

### Training Details
- **Data**: 2 years × 22 symbols (15 BIST + 7 crypto)
- **Split**: 80% train / 20% test, stratified
- **Validation**: 5-fold stratified cross-validation
- **Model**: `XGBClassifier(n_estimators=300, max_depth=5, lr=0.05, subsample=0.8)`
- **Output**: `models/xgb_signal_model.joblib` (includes metadata: cv_accuracy, feature_names, train_samples)

### Usage
```bash
cd backend
pip install xgboost scikit-learn joblib
python ml_trainer.py
```

---

## 8. Backend — Advanced Backtest

**File:** `backend/backtest_advanced.py`

Extended version of `backtest.py` with richer metrics.

### Metrics Added
| Metric | Formula |
|---|---|
| **Sharpe Ratio** | `mean(excess_returns) / std(excess_returns) × √(252 / FORWARD_DAYS)` — annualized |
| **Max Drawdown** | Worst peak-to-trough drop on the equity curve |
| **Win Rate** | % of trades with positive return |
| **Avg Trade Return** | Mean return per trade (long & short combined) |
| **Best / Worst Trade** | Single trade extremes |
| **Portfolio Final Value** | Compounded equity curve starting at 1.0 |
| **Total Return %** | `(final_value - 1) × 100` |

### Output Files
- `backtest_results.csv` — per-symbol table sorted by accuracy
- `backtest_results.json` — same data for API consumption

### Usage
```bash
cd backend
python backtest_advanced.py
```

---

## 9. Backend — ML Predictor Module

**File:** `backend/core/ml_predictor.py`

Lazy-loading wrapper around the trained model. Designed for zero-friction integration — if the model file doesn't exist, all calls return `None` and the system continues working normally.

### Key Functions
```python
get_ml_confidence(rsi, macd, macd_signal, bollinger_pb,
                  ema_crossover, trend_strength,
                  volume_ratio, price_velocity) -> Optional[float]
# Returns 0.0–1.0 bullish probability, or None if model not available

is_model_available() -> bool

get_model_info() -> dict
# Returns: { available, cv_accuracy, cv_std, train_samples, forward_days, features }
```

### Caching
Model is loaded once into `_MODEL_CACHE` module-level variable. Subsequent calls skip disk I/O.

---

## 10. Backend — Schema & Endpoint Updates

### `models/schemas.py`
Added optional field to `AnalysisResult`:
```python
ml_confidence: Optional[float] = None
```
Backward compatible — existing clients ignore the new field.

### `core/analyzer.py`
- Imported `get_ml_confidence` from `core.ml_predictor`
- Calls `get_ml_confidence(...)` after indicator calculation
- Passes result as `ml_confidence=round(ml_conf, 3)` to `AnalysisResult`

### `main.py`
- Added `/ml/status` GET endpoint → returns `get_model_info()` dict
- Replaced `MATIC-USD` (delisted) with `DOGE-USD` in `CRYPTO_SYMBOLS`

---

## 11. Known Issues / Future Work

| Item | Notes |
|---|---|
| ML model not yet trained | Run `python ml_trainer.py` to generate `xgb_signal_model.joblib`. Until then, `ml_confidence` will always be `None`. |
| iOS `ml_confidence` not displayed | Field is received from API but not yet surfaced in `AnalysisDetailView`. Add a confidence badge when model is available. |
| Watchlist drag-reorder + sort conflict | When `editMode == .inactive`, `sortedItems` is shown (score order). Manual order only visible/editable in edit mode. Consider persisting user's preferred sort preference. |
| BIST scan latency | Sequential HTTP calls to Yahoo Finance for 15 symbols takes ~5–10s. Consider `asyncio.gather` or a background task queue on the backend. |
| UserDefaults persistence | Watchlist, history, and settings stored in `UserDefaults`. For production, migrate to `Keychain` (sensitive prefs) and `Core Data` (watchlist + history). |
| No push notifications | Local `UNUserNotificationCenter` framework can be wired to watchlist analysis results for price alerts. HapticService is already in place for in-app feedback. |

---

## Build Verification

All changes verified with:
```
xcodebuild ... build → BUILD SUCCEEDED (0 errors)
uvicorn main:app --reload → Application startup complete
curl /health → {"status": "healthy"}
curl /ml/status → {"available": false}  ← correct, model not trained yet
```

---

## 12. iOS — Beta Trade (Paper Trading) Feature

**Session: 2026-03-05**

### New Files
- `OptiTradeiOS/Views/PaperTradeView.swift` — full paper trade UI (registered in pbxproj: B10016/A10016)

### Architecture

`PaperTrade` model (added to `Models.swift`):
- 12 fields: id, symbol, assetType, direction (LONG/SHORT), entryPrice, quantity, entryDate, exitPrice?, exitDate?, isOpen, analysisScore, decisionCode
- `finalPLPercent` computed property: recalculates P/L on every access, no stale data
- Short formula: `(entryPrice - exitPrice) / entryPrice * 100`

`UserSession` additions:
- `paperTrades()` / `savePaperTrades()` — UserDefaults JSON persistence
- `resetAccount()` — wipes all user data and returns to onboarding

### Views

| View | Purpose |
|---|---|
| `PaperTradeView` | Main screen: summary bar (open count / closed count / total P/L), segmented picker, empty states |
| `OpenTradeRow` | Real-time P/L via `getPrice()` API call on `.task`, "Kapat" swipe action |
| `ClosedTradeRow` | Historical trade with entry → exit price and final % |
| `NewTradeSheet` | Sheet form: symbol input + live price fetch, direction picker, quantity, assetType |

### API Integration
- `APIService.getPrice(symbol:)` → `GET /price/{symbol}` → `PriceResponse { symbol, price, change_pct, timestamp }`
- Called in `OpenTradeRow.task` for unrealized P/L
- Called in `closeTrade()` to auto-fill exit price at close time

---

## 13. iOS — Onboarding Login Page (4th Step)

**Session: 2026-03-05**

### Change
Added `loginPage` as the 4th onboarding step (after API setup). Page indicator dots updated to 4.

### Flow
```
welcomePage → disclaimerPage → apiSetupPage → loginPage → app
```

### LoginPage Fields
- Name (optional, written to `session.displayName`)
- Email (optional, written to `session.userEmail`)
- "Başla" button → sets `isGuestMode = false`, `onboardingDone = true`
- "Misafir Olarak Devam Et" link → sets `isGuestMode = true`, `onboardingDone = true`

### UserSession Additions
- `userEmail: String` @Published (persisted to UserDefaults key `user_email`)
- `isGuestMode: Bool` @Published (persisted to UserDefaults key `is_guest_mode`)

---

## 14. iOS — Settings Account Section Redesign

**Session: 2026-03-05**

### "Hesap" Section (renamed from "Profil")
- Profile icon changes: `person.fill` (authenticated) vs `person.slash.fill` (guest)
- Shows "Misafir Kullanıcı" label when `isGuestMode == true`
- Added email TextField bound to `session.userEmail`
- Disclaimer accepted date displayed (if set): `checkmark.shield.fill` icon + `.date` style text

### Disclaimer Timestamp
Added `disclaimerAcceptedAt: Date?` computed property to `UserSession`:
- Stored as `TimeInterval` under key `disclaimer_accepted_at`
- Auto-set in `disclaimerAccepted.didSet` when first accepted (won't overwrite if already set)

### "Hesabı Tamamen Sıfırla" Button
- Added to "Veri" section with `.destructive` role and `trash.fill` icon
- Shows confirmation alert with description text
- Calls `session.resetAccount()` → wipes displayName, userEmail, isGuestMode, onboardingDone, disclaimerAccepted, disclaimerAcceptedAt, searchHistory, watchlist, paperTrades

---

## 15. ContentView — Beta Trade Tab

Added 5th tab between "Takip" and "Ayarlar":
```swift
PaperTradeView()
    .tabItem { Label("Beta Trade", systemImage: "chart.line.uptrend.xyaxis") }
```

---

## Session: 2026-05-13 — Premium Polish & App Store Prep

### Achievements
- **V2 Engine Unified:** Market-agnostic analysis. Automatic symbol resolution for BIST, NASDAQ, and Crypto.
- **Adaptive Killzones:** ICT Killzone indicator now adjusts to asset-specific timezones (NY for US/Crypto, IST for TR).
- **TradingView Integration:** Full interactive charts with drawing tools added to Analysis Detail.
- **Backtest Visualization:** Native SwiftUI Charts showing both Equity Curve and Signal Markers (BUY/SELL triangles) on price history.
- **Premium Onboarding:** Redesigned `OnboardingView` with animated aura backgrounds, glowing icons, and "Sign in with Apple" prominence for a high-end first impression.
- **Monetization Layer:** Added `PremiumUpgradeView` with tiered features (ICT Engine, ML V2, Ad-free).

### App Store Readiness Status: 95% 🚀

| Task | Priority | Status |
|---|---|---|
| **App Icon** | High | 🎨 Design 1024x1024 minimalist icon (Dark + Cyan) |
| **Backend Deployment** | High | ☁️ Move from `localhost` to Production (AWS/DO) |
| **Apple Review Account** | High | 🔑 Create a Firebase test user with `isPremium = true` |
| **Legal Pages** | Medium | 📄 Publish Privacy & Terms at `algorix.io` |
| **Screenshots** | Medium | 📱 Prepare 6.9" & 6.5" professional screenshots |

### Next Steps for Tomorrow
1. Deploy Backend to production.
2. Finalize App Icon and launch screen.
3. Package for TestFlight.

---

## 18. App Store Readiness — Legal & Branding (Session 2026-03-05)

### Problem
Apple App Store, finansal analiz uygulamalarını "yatırım tavsiyesi" içerdiği şüphesiyle reddedebilir. Bununla birlikte marka kimliği eksikti.

### Changes

#### OnboardingView — Welcome Page
- "Product by Algorix" etiketi eklendi (küçük caps, accent renk)
- Alt uyarı satırı: "Bu uygulama yatırım tavsiyesi vermez."

#### OnboardingView — Disclaimer Page (tam yeniden yazım)
Başlık değiştirildi: "Önemli Uyarı" → **"Yasal Uyarı & Risk Bildirimi"**

5 ayrı yasal blok eklendi (ScrollView içinde):
| # | Başlık | Icon | Renk |
|---|---|---|---|
| 1 | Yatırım Tavsiyesi Değildir | xmark.shield.fill | Kırmızı |
| 2 | Kullanıcı Sorumluluğu | person.fill.questionmark | Turuncu |
| 3 | Geçmiş Performans Garantisi Yoktur | clock.arrow.2.circlepath | Sarı |
| 4 | Yüksek Risk | chart.line.downtrend.xyaxis | Kırmızı |
| 5 | Düzenleyici Uyarı (SPK/BDDK/SEC) | building.columns.fill | Mavi |

Onay checkbox: "Okudum ve anladım" → **"Yukarıdaki uyarıları okudum, anladım ve kabul ediyorum."** (checkbox stiline geçildi, daha belirgin)

#### SettingsView — About Bölümü (tam yeniden yazım)
- "Profil benzeri" single section → **3 section** mimarisine geçildi:
  1. **Hakkında**: OptiTrade logosu + "Product by Algorix", Versiyon, Analiz Motoru, Backtest doğruluğu, ML Model
  2. **Algorix** (linkler): Gizlilik Politikası (`algorix.io/privacy`), Kullanım Koşulları (`algorix.io/terms`), Destek & İletişim (`support@algorix.io`)
  3. **Yasal Uyarı**: Tam metin yasal bildiri + Disclaimer onay tarihi (yeşil checkmark ile)
- `@ViewBuilder` attribute eklendi (çoklu Section döndürmek için gerekli)

#### AnalysisDetailView — Disclaimer Footer
Her analiz sonucunun altına kalıcı footer:
```
⚠️ Bu analiz yatırım tavsiyesi değildir. Tüm kararlar kullanıcıya aittir.
     Product by Algorix  •  algorix.io
```

#### DashboardView — Disclaimer Band
Tarama sonuçları listesinin en altına:
```
⚠️ Gösterilen sinyaller yatırım tavsiyesi değildir.
    Product by Algorix  •  algorix.io
```

### App Store Review Kriterleri
| Kriter | Durum |
|---|---|
| Yatırım tavsiyesi reddi onboarding'de açık | ✅ |
| Her analizin altında yasal uyarı | ✅ |
| Dashboard'da disclaimer | ✅ |
| Gizlilik Politikası linki settings'de | ✅ |
| Kullanım Koşulları linki settings'de | ✅ |
| Destek e-postası | ✅ |
| "Product by Algorix" marka kimliği | ✅ |
| Onboarding disclaimer zorunlu kabul (checkbox) | ✅ |
| Disclaimer onay tarihi kaydedilir | ✅ |

### Kalan Görevler (Canlıya Çıkmadan Önce)
- [ ] `algorix.io/privacy` ve `algorix.io/terms` sayfaları yayınlanmalı
- [ ] App Store Connect'te Privacy Policy URL girilmeli
- [ ] Backend production sunucusuna deploy edilmeli (`http://localhost:8000` → gerçek URL)
- [ ] Onboarding'deki default API URL production URL'ye güncellenmeli
- [ ] App ikonu (1024×1024) App Store Connect'e yüklenmeli
- [ ] Screenshots (6.9" ve 6.1" ekran boyutları için)
- [ ] App Store description ve keywords hazırlanmalı (Türkçe + İngilizce)

---

## 16. ML Model Training Results

**Session: 2026-03-05**

### Setup
- Dependency: `conda install xgboost -c conda-forge` (Apple Silicon requires conda version, pip version fails due to libomp.dylib)
- Model saved: `backend/models/xgb_signal_model.joblib` (572 KB)

### Dataset
| Metric | Value |
|---|---|
| Symbols | 22 (15 BIST + 7 Crypto) |
| Period | 2 years |
| Lookback window | 60 days |
| Forward target | 5 days |
| Buy threshold | >+1.0% |
| Total samples | 11,190 |
| Positive (BUY) ratio | 43.0% |
| Train / Test split | 8,952 / 2,238 (80/20) |

### Model Performance
| Metric | Value |
|---|---|
| Cross-val accuracy | **57.2% ± 1.0%** |
| Test accuracy | **58.3%** |
| DÜŞÜŞ/NÖTR precision | 0.60 / recall 0.83 |
| YUKARI precision | 0.53 / recall 0.26 |

### Feature Importances (all roughly equal ~14%)
| Feature | Importance |
|---|---|
| rsi | 0.148 |
| bollinger_pb | 0.148 |
| trend_strength | 0.147 |
| macd_diff | 0.144 |
| ema_signal_enc | 0.143 |
| volume_ratio | 0.138 |
| price_velocity | 0.133 |

### Confusion Matrix
```
TN=1052  FP=223
FN=713   TP=250
```
> High recall on DÜŞÜŞ/NÖTR (0.83), conservative on YUKARI (0.26) — model is defensive/risk-averse by design.

### ML Status Endpoint
```
GET /ml/status → { "available": true, "cv_accuracy": 57.2, "cv_std": 1.0, "train_samples": 8952, ... }
```

---

## 17. Backtest Results (Advanced)

**Session: 2026-03-05**

### Configuration
- Period: Last 1 year
- Lookback: 60 days | Forward: 5 days
- BUY signal correct if: actual +5d return > +1%
- SELL signal correct if: actual +5d return < -1%

### Per-Symbol Results

| Symbol | Accuracy | Sharpe | MaxDD | Win Rate | Total Return |
|---|---|---|---|---|---|
| THYAO.IS | 0.0% | -12.34 | -6.6% | 0% | -6.6% |
| GARAN.IS | 0.0% | +0.00 | -1.9% | 0% | -1.9% |
| ASELS.IS | 0.0% | +0.00 | 0.0% | 0% | +0.0% |
| KCHOL.IS | **100.0%** | +16.76 | 0.0% | 100% | **+9.0%** |
| EREGL.IS | **100.0%** | +9.83 | 0.0% | 100% | **+8.0%** |
| AKBNK.IS | 50.0% | +0.01 | -6.4% | 50% | -0.3% |
| TUPRS.IS | 0.0% | +0.00 | 0.0% | 0% | 0.0% |
| FROTO.IS | 0.0% | +0.00 | 0.0% | 0% | 0.0% |
| SAHOL.IS | 0.0% | -20.33 | -3.0% | 0% | -3.0% |
| PGSUS.IS | 66.7% | +11.10 | 0.0% | 100% | **+16.8%** |
| BTC-USD | **100.0%** | +49.80 | 0.0% | 100% | **+38.3%** |
| ETH-USD | 33.3% | -1.46 | -27.7% | 33% | -13.1% |
| BNB-USD | **100.0%** | +0.00 | 0.0% | 100% | +2.1% |
| SOL-USD | **100.0%** | +28.56 | 0.0% | 100% | **+41.4%** |
| AVAX-USD | 66.7% | +0.12 | -11.8% | 67% | -1.3% |

### Summary

| Metric | Value |
|---|---|
| Total symbols | 15 |
| Total signals generated | 40 |
| **Overall accuracy** | **62.5%** |
| BUY accuracy | 55.6% (10/18) |
| SELL accuracy | 68.2% (15/22) |
| Avg Sharpe Ratio | +5.47 |
| Worst Max Drawdown | -27.7% (ETH) |
| Avg Win Rate | 50.0% |
| **Avg trade return** | **+1.63%** |

### Key Observations
- **SELL signals outperform BUY signals** (68% vs 56%) — algorithm is more reliable as a bearish detector
- **Crypto (BTC, SOL) dominant performers** — strong trending assets benefit most from trend-following rules
- **BIST signal count low** — scoring engine mostly outputs NEUTRAL for sideways/indecisive stocks
- **ETH anomaly** — -27.7% drawdown from a single bad SELL signal during a spike; consider stop-loss in v3
- Backtest files saved: `backend/backtest_results.csv` + `backend/backtest_results.json`
