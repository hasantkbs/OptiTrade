import Foundation
@testable import OptiTradeiOS

/// Configurable `WatchlistServicing` fake — no network, no `APIClient`.
actor StubWatchlistService: WatchlistServicing {
    private(set) var fetchCallCount = 0
    private(set) var createCallCount = 0
    private(set) var addCallCount = 0
    private(set) var removeCallCount = 0
    private(set) var recordedAddedSymbols: [String] = []
    private(set) var recordedRemovedSymbols: [String] = []

    var fetchResult: Result<WatchlistSummary?, Error>
    var createResult: Result<Int, Error>
    var addResult: Result<WatchlistAssetItem, Error>
    var removeResult: Result<Void, Error>

    init(
        fetchResult: Result<WatchlistSummary?, Error> = .success(nil),
        createResult: Result<Int, Error> = .success(1),
        addResult: Result<WatchlistAssetItem, Error> = .success(WatchlistAssetItem(dto: WatchlistItemDTO(id: 1, watchlistId: 1, symbol: "AAPL", isFavorite: false, folder: nil, tags: [], notes: ""))),
        removeResult: Result<Void, Error> = .success(())
    ) {
        self.fetchResult = fetchResult
        self.createResult = createResult
        self.addResult = addResult
        self.removeResult = removeResult
    }

    func fetchPrimaryWatchlist() async throws -> WatchlistSummary? {
        fetchCallCount += 1
        return try fetchResult.get()
    }

    func createWatchlist(name: String) async throws -> Int {
        createCallCount += 1
        return try createResult.get()
    }

    func addSymbol(_ symbol: String, toWatchlist watchlistID: Int) async throws -> WatchlistAssetItem {
        addCallCount += 1
        recordedAddedSymbols.append(symbol)
        return try addResult.get()
    }

    func removeSymbol(_ symbol: String, fromWatchlist watchlistID: Int) async throws {
        removeCallCount += 1
        recordedRemovedSymbols.append(symbol)
        try removeResult.get()
    }

    func setFetchResult(_ newResult: Result<WatchlistSummary?, Error>) {
        fetchResult = newResult
    }

    func setAddResult(_ newResult: Result<WatchlistAssetItem, Error>) {
        addResult = newResult
    }

    func setRemoveResult(_ newResult: Result<Void, Error>) {
        removeResult = newResult
    }
}
