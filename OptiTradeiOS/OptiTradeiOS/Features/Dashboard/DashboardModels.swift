import Foundation

// Dashboard introduces no new backend contract of its own — every value
// it shows comes from types Steps 3/4 already defined against the real
// backend (`PortfolioSummary`, `WatchlistSummary`, `WatchlistAssetItem`,
// `AssetSelection`). This file holds only Dashboard-local presentation
// mappings, never a new wire DTO.

/// One watchlist symbol presented as a candidate for Quant analysis / AI
/// Analyst on the Dashboard. Carries only what the real Watchlist data
/// actually has (`WatchlistAssetItem.symbol`) — no invented price,
/// score, or signal.
struct DashboardQuantCandidate: Sendable, Equatable, Identifiable {
    var id: String { symbol }
    let symbol: String

    init(item: WatchlistAssetItem) {
        symbol = item.symbol
    }

    /// The strongly-typed navigation payload for both Asset Detail and
    /// AI Analyst — same `AssetSelection` Step 4 established, not a
    /// second selection mechanism.
    var assetSelection: AssetSelection {
        AssetSelection(symbol: symbol)
    }
}

/// Pure, deterministic time-of-day greeting — client-side UI copy, not
/// financial data, so it isn't subject to the "never fabricate" rules
/// that govern portfolio/watchlist/quant values elsewhere on this screen.
enum DashboardGreeting {
    static func salutation(hour: Int) -> String {
        switch hour {
        case 5..<12: "Good morning"
        case 12..<17: "Good afternoon"
        case 17..<22: "Good evening"
        default: "Welcome back"
        }
    }
}
