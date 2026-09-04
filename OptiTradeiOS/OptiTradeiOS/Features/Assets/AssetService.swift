import Foundation

/// Networking for asset discovery. Talks to the *real* backend contract:
///   - `GET /market/watchlist/{market}` -> {market, info, watchlist, symbols}
///
/// There is no arbitrary-text search endpoint on the backend, so "search"
/// here means: fetch the real per-market symbol directory (cached for the
/// life of this instance) and filter it in-memory by symbol/name substring.
protocol AssetSearchServicing: Sendable {
    /// Empty/blank `query` returns `[]` without a network call.
    func search(query: String, market: String) async throws -> [AssetSearchResult]
}

actor AssetService: AssetSearchServicing {
    private let apiClient: APIClient
    private var directories: [String: MarketWatchlistDTO] = [:]

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func search(query: String, market: String) async throws -> [AssetSearchResult] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }

        let directory = try await directory(for: market)
        let needle = trimmed.uppercased()
        return directory.symbols
            .filter { symbol, name in
                symbol.uppercased().contains(needle) || name.uppercased().contains(needle)
            }
            .map { symbol, name in
                AssetSearchResult(symbol: symbol, name: name, market: directory.market, currency: directory.info.currency)
            }
            .sorted { $0.symbol < $1.symbol }
    }

    private func directory(for market: String) async throws -> MarketWatchlistDTO {
        if let cached = directories[market] {
            return cached
        }
        let dto = try await apiClient.send(APIRequest<MarketWatchlistDTO>(path: "market/watchlist/\(market)"))
        directories[market] = dto
        return dto
    }
}
