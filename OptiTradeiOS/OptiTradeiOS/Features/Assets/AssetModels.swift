import Foundation

// MARK: - Wire DTOs
//
// The backend has no dedicated free-text asset search endpoint (verified
// against `backend/main.py` + `backend/core/market_config.py`). The closest
// real contract is `GET /market/watchlist/{market}`, which returns a
// per-market symbol directory (`core.market_config.get_symbols_for_market`)
// alongside that market's metadata. Step 4 adapts to this real contract by
// fetching the directory once per market and filtering it client-side,
// rather than inventing a `/search` endpoint that doesn't exist.
//
// Response shape (no `response_model` on the FastAPI route, so this mirrors
// the handler's literal return dict):
//   {"market": str, "info": {...MARKETS[market]}, "watchlist": [str], "symbols": {SYMBOL: NAME}}

struct MarketInfoDTO: Decodable, Sendable {
    let name: String
    let currency: String
    let indexSymbol: String
    let indexName: String
}

struct MarketWatchlistDTO: Decodable, Sendable {
    let market: String
    let info: MarketInfoDTO
    /// Symbol -> company/asset name, e.g. `"AAPL": "Apple"`. None of the
    /// keys in `core.market_config`'s symbol dictionaries contain an
    /// underscore, so `APICoding.decoder`'s `.convertFromSnakeCase` (which
    /// also normalizes dictionary keys, not just struct properties) is a
    /// no-op here and every ticker decodes unchanged.
    let symbols: [String: String]
}

// MARK: - Domain models

/// One asset as surfaced by search — assembled from `MarketWatchlistDTO`.
/// Only fields the backend actually returns: no exchange/asset-type field
/// exists in the contract, so none is invented here.
struct AssetSearchResult: Sendable, Equatable, Identifiable, Hashable {
    var id: String { symbol }
    let symbol: String
    let name: String
    let market: String
    let currency: String
}

/// Strongly-typed navigation payload for "the user selected an asset,"
/// carried from either Asset Search (fully populated) or a Watchlist row
/// (symbol only — `GET /watchlists/{id}/items` doesn't return a name,
/// market, or currency, so those are honestly `nil` rather than guessed).
struct AssetSelection: Sendable, Equatable, Hashable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let name: String?
    let market: String?
    let currency: String?

    init(symbol: String, name: String? = nil, market: String? = nil, currency: String? = nil) {
        self.symbol = symbol
        self.name = name
        self.market = market
        self.currency = currency
    }

    init(searchResult: AssetSearchResult) {
        symbol = searchResult.symbol
        name = searchResult.name
        market = searchResult.market
        currency = searchResult.currency
    }

    /// Maps `market` (from Step 4's real per-market symbol directory) to
    /// the backend's own `asset_type` request values
    /// (`AnalysisRequest`/`QuantAnalysisRequest`: `"stock" | "crypto"`).
    /// A selection with no `market` (e.g. from a bare Watchlist row) falls
    /// back to the backend's own default, `"stock"` — not a guess, the
    /// same default `QuantAnalysisRequest.asset_type` already declares.
    /// Shared by `AssetDetailView` and `DashboardView` so this mapping
    /// exists in exactly one place.
    var assetType: String {
        market == "CRYPTO" ? "crypto" : "stock"
    }
}
