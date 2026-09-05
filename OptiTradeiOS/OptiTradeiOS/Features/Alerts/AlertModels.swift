import Foundation

// MARK: - Wire DTOs
//
// Match `backend/watchlist/models.py` (the real "Watchlist & Alert
// Platform") exactly, via `backend/main.py`'s `/alerts` routes. Plain
// camelCase property names, no custom `CodingKeys` (see
// PortfolioModels.swift for why mixing in snake_case CodingKeys breaks
// `APICoding`'s `convertFromSnakeCase`).
//
// `Alert.parameters`/`.lastState` are `Dict[str, float]` on the backend —
// genuinely free-form, so their *keys* are real parameter names like
// `"threshold_pct"`. `APICoding.decoder`'s `.convertFromSnakeCase`
// mangles dictionary keys the same way it mangles struct property names
// (a well-known Foundation `JSONDecoder` behavior, not specific to this
// app), so a decoded key like `"threshold_pct"` arrives as
// `"thresholdPct"`. This only affects the *display spelling* of a
// parameter name for an alert this app didn't create (the numeric value
// is always exact) — `Alert.parameterSummary` prettifies whatever key it
// receives rather than pretending to recover the original wire spelling.
// It does not affect *creating* an alert: `APICoding.encoder`'s
// `.convertToSnakeCase` correctly turns a Swift key like `"thresholdPct"`
// back into the wire's `"threshold_pct"` on encode.

/// Wire shape of `watchlist.models.AlertCategory`.
enum AlertCategoryDTO: String, Codable, Sendable, Equatable, CaseIterable {
    case price
    case technical
    case decision
    case news
    case portfolio
}

/// Wire shape of `watchlist.models.AlertType` — every value the backend
/// actually defines, so decoding any existing alert (regardless of which
/// category/type created it) never fails. Only a subset is offered for
/// *creation* by this app (see `AlertComponents.swift`'s
/// `CreateAlertFormView`) because only that subset's exact parameter
/// contract was verified against `watchlist/price_alerts.py` and
/// `watchlist/alert_engine.py` — the rest (Technical/News/Portfolio, and
/// Decision's confidence/return/risk-change variants) have real backend
/// support but unverified parameter names, so this app does not guess at
/// them.
enum AlertTypeDTO: String, Codable, Sendable, Equatable, CaseIterable {
    case priceAbove = "price_above"
    case priceBelow = "price_below"
    case pricePercentMove = "price_percent_move"
    case priceGap = "price_gap"
    case rsiThreshold = "rsi_threshold"
    case macdCrossover = "macd_crossover"
    case emaCrossover = "ema_crossover"
    case bollingerBreakout = "bollinger_breakout"
    case volumeSpike = "volume_spike"
    case atrExpansion = "atr_expansion"
    case decisionBuy = "decision_buy"
    case decisionSell = "decision_sell"
    case confidenceChange = "confidence_change"
    case expectedReturnChange = "expected_return_change"
    case riskChange = "risk_change"
    case newsHighImpact = "news_high_impact"
    case newsSector = "news_sector"
    case newsBreaking = "news_breaking"
    case portfolioAllocationExceeded = "portfolio_allocation_exceeded"
    case portfolioVarExceeded = "portfolio_var_exceeded"
    case portfolioDrawdownExceeded = "portfolio_drawdown_exceeded"
    case portfolioConcentration = "portfolio_concentration"

    /// Human-readable label for every real value — a direct 1:1 naming
    /// of the backend's own taxonomy, not an invented one.
    var displayName: String {
        switch self {
        case .priceAbove: "Price Above"
        case .priceBelow: "Price Below"
        case .pricePercentMove: "Price % Move"
        case .priceGap: "Price Gap"
        case .rsiThreshold: "RSI Threshold"
        case .macdCrossover: "MACD Crossover"
        case .emaCrossover: "EMA Crossover"
        case .bollingerBreakout: "Bollinger Breakout"
        case .volumeSpike: "Volume Spike"
        case .atrExpansion: "ATR Expansion"
        case .decisionBuy: "Decision: Buy"
        case .decisionSell: "Decision: Sell"
        case .confidenceChange: "Confidence Change"
        case .expectedReturnChange: "Expected Return Change"
        case .riskChange: "Risk Change"
        case .newsHighImpact: "High-Impact News"
        case .newsSector: "Sector News"
        case .newsBreaking: "Breaking News"
        case .portfolioAllocationExceeded: "Allocation Exceeded"
        case .portfolioVarExceeded: "VaR Exceeded"
        case .portfolioDrawdownExceeded: "Drawdown Exceeded"
        case .portfolioConcentration: "Concentration"
        }
    }

    /// The subset offered for *creation* in this app — see this file's
    /// top-of-type doc comment for why the rest aren't (real backend
    /// support, unverified parameter contract).
    static let creatable: [AlertTypeDTO] = [.priceAbove, .priceBelow, .pricePercentMove, .priceGap, .decisionBuy, .decisionSell]

    /// The category each creatable type belongs to, per the backend's own
    /// `CATEGORY_TYPES` grouping in `watchlist/models.py`.
    var category: AlertCategoryDTO {
        switch self {
        case .priceAbove, .priceBelow, .pricePercentMove, .priceGap:
            .price
        case .decisionBuy, .decisionSell:
            .decision
        default:
            .price
        }
    }

    /// `price_alerts.py._threshold_check`: `parameters["threshold"]` is
    /// required for these two types (missing it raises `InvalidAlertError`
    /// server-side).
    var requiresThresholdParameter: Bool {
        self == .priceAbove || self == .priceBelow
    }

    /// `price_alerts.py._percent_move_check`/`._gap_check`:
    /// `parameters["threshold_pct"]` is optional for these two — the
    /// backend applies its own default (5% / 3%) when omitted.
    var hasOptionalThresholdPctParameter: Bool {
        self == .pricePercentMove || self == .priceGap
    }
}

/// Wire shape of `watchlist.models.Alert`. `last_checked_at`/
/// `last_triggered_at`/`created_at` are intentionally not modeled — same
/// "only what this screen needs" call Step 3 made for
/// `Portfolio.created_at`.
struct AlertDTO: Decodable, Sendable {
    let id: Int?
    let owner: String
    let watchlistId: Int?
    let symbol: String?
    let portfolioId: Int?
    let category: AlertCategoryDTO
    let alertType: AlertTypeDTO
    let parameters: [String: Double]
    let cooldownMinutes: Int
    let enabled: Bool
}

/// Wire shape of `watchlist.models.CreateAlertRequest`.
struct CreateAlertRequestDTO: Encodable, Sendable {
    let category: AlertCategoryDTO
    let alertType: AlertTypeDTO
    let parameters: [String: Double]
    let watchlistId: Int?
    let symbol: String?
    let portfolioId: Int?
    let cooldownMinutes: Int
}

/// Wire shape of `watchlist.models.SetAlertEnabledRequest`.
struct SetAlertEnabledRequestDTO: Encodable, Sendable {
    let enabled: Bool
}

/// Wire shape of `watchlist.models.ScanReport` — only the summary counts
/// this app's "Check Now" action needs. `started_at` and the per-alert
/// `outcomes` (each carrying an `Optional<AlertTriggerEvent>` with a
/// nested Decision Engine `Prediction`) are not modeled; not needed for
/// a one-line "N of M alerts triggered" result.
struct ScanReportDTO: Decodable, Sendable {
    let totalAlerts: Int
    let checkedCount: Int
    let triggeredCount: Int
}

// MARK: - Domain models

/// One alert, as actually returned by `GET /alerts`. Requires a real
/// server-assigned `id` — an `Alert` the backend hasn't saved yet isn't
/// representable here (mirrors `PortfolioDTO`/`WatchlistDTO`'s own
/// `guard let id` pattern at the service boundary).
///
/// Named `AlertRule`, not `Alert` — `SwiftUI.Alert` already exists (still
/// present in the SDK despite being deprecated in favor of the `.alert`
/// modifier), and any file with `import SwiftUI` would make a bare
/// `Alert` ambiguous. Same category of fix as Step 4/5's
/// `WatchlistScreenViewModel`/`AssetPriceChart` renames for a legacy-code
/// collision — this one is an SDK collision instead.
struct AlertRule: Sendable, Equatable, Identifiable {
    let id: Int
    let watchlistID: Int?
    let symbol: String?
    let portfolioID: Int?
    let category: AlertCategoryDTO
    let alertType: AlertTypeDTO
    let parameters: [String: Double]
    let cooldownMinutes: Int
    let enabled: Bool

    init?(dto: AlertDTO) {
        guard let id = dto.id else { return nil }
        self.id = id
        watchlistID = dto.watchlistId
        symbol = dto.symbol
        portfolioID = dto.portfolioId
        category = dto.category
        alertType = dto.alertType
        parameters = dto.parameters
        cooldownMinutes = dto.cooldownMinutes
        enabled = dto.enabled
    }

    var displayName: String { alertType.displayName }

    /// Prettifies whatever parameter keys this alert actually has — see
    /// this file's top-of-file note on why a key like `"thresholdPct"`
    /// may not exactly match the backend's own `"threshold_pct"` spelling
    /// for an alert this app didn't create, while the value is always
    /// exact.
    var parameterSummary: String? {
        guard !parameters.isEmpty else { return nil }
        return parameters
            .sorted { $0.key < $1.key }
            .map { key, value in "\(Self.prettify(key)): \(value.formatted(.number.precision(.fractionLength(0...2))))" }
            .joined(separator: ", ")
    }

    private static func prettify(_ camelCaseKey: String) -> String {
        var result = ""
        for character in camelCaseKey {
            if character.isUppercase {
                result.append(" ")
            }
            result.append(character)
        }
        return result.prefix(1).uppercased() + result.dropFirst()
    }
}

/// Summary of an on-demand `/alerts/scan` run.
struct AlertScanSummary: Sendable, Equatable {
    let totalAlerts: Int
    let checkedCount: Int
    let triggeredCount: Int

    init(dto: ScanReportDTO) {
        totalAlerts = dto.totalAlerts
        checkedCount = dto.checkedCount
        triggeredCount = dto.triggeredCount
    }
}
