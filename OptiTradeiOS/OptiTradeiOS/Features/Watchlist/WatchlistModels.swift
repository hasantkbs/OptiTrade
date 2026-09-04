import Foundation

// MARK: - Wire DTOs
//
// Match `backend/watchlist/models.py` exactly. No custom `CodingKeys` —
// plain camelCase property names, relying on `APICoding`'s
// `convertFromSnakeCase`/`convertToSnakeCase` (see PortfolioModels.swift
// for why mixing in custom snake_case CodingKeys breaks decoding).
// `created_at`/`added_at` are intentionally not modeled — this feature
// never needs them, same call Step 3 made for `Portfolio.created_at`.

/// Wire shape of `watchlist.models.Watchlist`.
struct WatchlistDTO: Decodable, Sendable {
    let id: Int?
    let owner: String
    let name: String
}

/// Wire shape of `watchlist.models.WatchlistItem`.
struct WatchlistItemDTO: Decodable, Sendable {
    let id: Int?
    let watchlistId: Int
    let symbol: String
    let isFavorite: Bool
    let folder: String?
    let tags: [String]
    let notes: String
}

/// Wire shape of `watchlist.models.CreateWatchlistRequest`.
struct CreateWatchlistRequestDTO: Encodable, Sendable {
    let name: String
}

/// Wire shape of `watchlist.models.AddWatchlistItemRequest`. Only `symbol`
/// is exposed by this feature — favorites/folders/tags/notes aren't part
/// of Step 4's scope, so they're sent as the backend's own defaults.
struct AddWatchlistItemRequestDTO: Encodable, Sendable {
    let symbol: String
    let isFavorite: Bool
    let folder: String?
    let tags: [String]
    let notes: String

    init(symbol: String) {
        self.symbol = symbol
        self.isFavorite = false
        self.folder = nil
        self.tags = []
        self.notes = ""
    }
}

// MARK: - Domain models

/// One tracked symbol, as actually returned by
/// `GET /watchlists/{id}/items`. No company name, market, or currency —
/// the backend doesn't return them at this endpoint, so none is invented.
struct WatchlistAssetItem: Sendable, Equatable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let isFavorite: Bool

    init(dto: WatchlistItemDTO) {
        symbol = dto.symbol
        isFavorite = dto.isFavorite
    }
}

/// Everything `WatchlistView` needs to render — assembled from one
/// `Watchlist` (for its id/name) and its items.
struct WatchlistSummary: Sendable, Equatable {
    let watchlistID: Int
    let name: String
    let items: [WatchlistAssetItem]

    init(watchlistID: Int, name: String, items: [WatchlistItemDTO]) {
        self.watchlistID = watchlistID
        self.name = name
        self.items = items.map(WatchlistAssetItem.init(dto:))
    }
}
