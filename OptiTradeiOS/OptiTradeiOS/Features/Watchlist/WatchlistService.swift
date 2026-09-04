import Foundation

/// Networking for the Watchlist feature. Talks to the *real* backend
/// contract (`backend/watchlist/models.py` + `backend/main.py`'s
/// `/watchlists` routes):
///   - `POST /watchlists`                          -> Watchlist
///   - `GET /watchlists`                            -> [Watchlist]
///   - `GET /watchlists/{id}/items`                 -> [WatchlistItem]
///   - `POST /watchlists/{id}/items`                -> WatchlistItem
///   - `DELETE /watchlists/{id}/items/{symbol}`
///
/// All already work with the existing `APIClient`'s Bearer-token injection
/// and 401->refresh handling from Step 1/2 — nothing new was needed there.
///
/// The backend's `add_symbol` upserts on `(watchlist_id, symbol)` conflict
/// (see `watchlist/repository.py`) rather than erroring on a duplicate, so
/// there is no "duplicate item" HTTP error to map — duplicate *requests*
/// are instead prevented client-side by `WatchlistScreenViewModel`'s
/// `pendingSymbols` guard and by disabling "Add" once a symbol is already
/// a member.
protocol WatchlistServicing: Sendable {
    /// The signed-in user's primary watchlist, fully assembled with its
    /// items. `nil` means the user genuinely has no watchlist yet — a real
    /// state (mirrors `PortfolioServicing.fetchPrimaryPortfolio()`), not an
    /// error. A user can have multiple watchlists; Step 4 shows exactly one
    /// (the first returned by the backend), same simplification Step 3 made
    /// for portfolios.
    func fetchPrimaryWatchlist() async throws -> WatchlistSummary?

    /// Creates a new watchlist and returns its id. Used lazily the first
    /// time the user adds an asset while they have no watchlist yet.
    func createWatchlist(name: String) async throws -> Int

    func addSymbol(_ symbol: String, toWatchlist watchlistID: Int) async throws -> WatchlistAssetItem
    func removeSymbol(_ symbol: String, fromWatchlist watchlistID: Int) async throws
}

struct WatchlistService: WatchlistServicing {
    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func fetchPrimaryWatchlist() async throws -> WatchlistSummary? {
        let watchlists = try await apiClient.send(APIRequest<[WatchlistDTO]>(path: "watchlists"))
        guard let watchlist = watchlists.first, let id = watchlist.id else {
            return nil
        }
        let items = try await apiClient.send(APIRequest<[WatchlistItemDTO]>(path: "watchlists/\(id)/items"))
        return WatchlistSummary(watchlistID: id, name: watchlist.name, items: items)
    }

    func createWatchlist(name: String) async throws -> Int {
        let request = try APIRequest<WatchlistDTO>(path: "watchlists", method: .post, body: CreateWatchlistRequestDTO(name: name))
        let created = try await apiClient.send(request)
        guard let id = created.id else {
            throw APIClientError.decoding("Created watchlist did not include an id.")
        }
        return id
    }

    func addSymbol(_ symbol: String, toWatchlist watchlistID: Int) async throws -> WatchlistAssetItem {
        let request = try APIRequest<WatchlistItemDTO>(
            path: "watchlists/\(watchlistID)/items",
            method: .post,
            body: AddWatchlistItemRequestDTO(symbol: symbol)
        )
        let dto = try await apiClient.send(request)
        return WatchlistAssetItem(dto: dto)
    }

    func removeSymbol(_ symbol: String, fromWatchlist watchlistID: Int) async throws {
        let request = APIRequest<EmptyResponse>(path: "watchlists/\(watchlistID)/items/\(symbol)", method: .delete)
        _ = try await apiClient.send(request)
    }
}
