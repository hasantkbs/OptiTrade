import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct WatchlistScreenViewModelTests {
    private static func makeSummary(watchlistID: Int = 1, symbols: [String] = ["AAPL"]) -> WatchlistSummary {
        WatchlistSummary(
            watchlistID: watchlistID,
            name: "My Watchlist",
            items: symbols.map { symbol in
                WatchlistItemDTO(id: 1, watchlistId: watchlistID, symbol: symbol, isFavorite: false, folder: nil, tags: [], notes: "")
            }
        )
    }

    @Test
    func initialStateIsIdleBeforeLoading() {
        let viewModel = WatchlistScreenViewModel(watchlistService: StubWatchlistService(), logger: TestLogger())
        #expect(viewModel.state == .idle)
    }

    @Test
    func loadIfNeededTransitionsToLoadedOnSuccess() async {
        let summary = Self.makeSummary()
        let service = StubWatchlistService(fetchResult: .success(summary))
        let viewModel = WatchlistScreenViewModel(watchlistService: service, logger: TestLogger())

        await viewModel.loadIfNeeded()

        #expect(viewModel.state == .loaded(summary))
    }

    @Test
    func loadIfNeededTransitionsToEmptyWhenNoWatchlistExists() async {
        let service = StubWatchlistService(fetchResult: .success(nil))
        let viewModel = WatchlistScreenViewModel(watchlistService: service, logger: TestLogger())

        await viewModel.loadIfNeeded()

        #expect(viewModel.state == .empty)
    }

    @Test
    func loadIfNeededTransitionsToFailedOnError() async {
        let service = StubWatchlistService(fetchResult: .failure(APIClientError.server(statusCode: 500, payload: nil)))
        let viewModel = WatchlistScreenViewModel(watchlistService: service, logger: TestLogger())

        await viewModel.loadIfNeeded()

        #expect(viewModel.state == .failed("The server is having trouble. Please try again shortly."))
    }

    @Test
    func refreshFailurePreservesExistingLoadedDataAndSurfacesABanner() async {
        let summary = Self.makeSummary()
        let service = StubWatchlistService(fetchResult: .success(summary))
        let viewModel = WatchlistScreenViewModel(watchlistService: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setFetchResult(.failure(APIClientError.transport("offline")))
        await viewModel.refresh()

        #expect(viewModel.state == .loaded(summary))
        #expect(viewModel.refreshError == "Couldn't reach the server. Check your connection and try again.")
    }

    @Test
    func addingASymbolWhenAWatchlistAlreadyExistsSkipsCreateAndReloads() async {
        let service = StubWatchlistService(fetchResult: .success(Self.makeSummary(symbols: ["AAPL"])))
        let viewModel = WatchlistScreenViewModel(watchlistService: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setFetchResult(.success(Self.makeSummary(symbols: ["AAPL", "MSFT"])))
        await viewModel.add(symbol: "MSFT")

        #expect(await service.createCallCount == 0)
        #expect(await service.addCallCount == 1)
        #expect(viewModel.isInWatchlist("MSFT"))
        #expect(viewModel.mutationError == nil)
    }

    @Test
    func addingTheFirstSymbolWhenNoWatchlistExistsCreatesOneFirst() async {
        let service = StubWatchlistService(fetchResult: .success(nil))
        let viewModel = WatchlistScreenViewModel(watchlistService: service, logger: TestLogger())
        await viewModel.loadIfNeeded()
        #expect(viewModel.state == .empty)

        await service.setFetchResult(.success(Self.makeSummary(watchlistID: 9, symbols: ["AAPL"])))
        await viewModel.add(symbol: "AAPL")

        #expect(await service.createCallCount == 1)
        #expect(await service.addCallCount == 1)
        #expect(viewModel.isInWatchlist("AAPL"))
    }

    @Test
    func removingASymbolReloadsFromTheBackend() async {
        let service = StubWatchlistService(fetchResult: .success(Self.makeSummary(symbols: ["AAPL", "MSFT"])))
        let viewModel = WatchlistScreenViewModel(watchlistService: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setFetchResult(.success(Self.makeSummary(symbols: ["MSFT"])))
        await viewModel.remove(symbol: "AAPL")

        #expect(await service.removeCallCount == 1)
        #expect(!viewModel.isInWatchlist("AAPL"))
        #expect(viewModel.isInWatchlist("MSFT"))
    }

    @Test
    func removeIsANoOpWhenNothingIsLoaded() async {
        let service = StubWatchlistService()
        let viewModel = WatchlistScreenViewModel(watchlistService: service, logger: TestLogger())

        await viewModel.remove(symbol: "AAPL")

        #expect(await service.removeCallCount == 0)
    }

    @Test
    func addFailureSurfacesAMutationErrorWithoutChangingState() async {
        let summary = Self.makeSummary(symbols: ["AAPL"])
        let service = StubWatchlistService(fetchResult: .success(summary))
        let viewModel = WatchlistScreenViewModel(watchlistService: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setAddResult(.failure(APIClientError.server(statusCode: 500, payload: nil)))
        await viewModel.add(symbol: "MSFT")

        #expect(viewModel.state == .loaded(summary))
        #expect(viewModel.mutationError == "The server is having trouble. Please try again shortly.")
    }

    @Test
    func removeFailureSurfacesAMutationError() async {
        let summary = Self.makeSummary(symbols: ["AAPL"])
        let service = StubWatchlistService(fetchResult: .success(summary))
        let viewModel = WatchlistScreenViewModel(watchlistService: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setRemoveResult(.failure(APIClientError.transport("offline")))
        await viewModel.remove(symbol: "AAPL")

        #expect(viewModel.mutationError == "Couldn't reach the server. Check your connection and try again.")
    }

    /// Duplicate-add and add/remove-race protection: a slow first `add`
    /// still in flight must block a second mutation for the *same* symbol,
    /// so a stale completion can never leave the UI in an inconsistent
    /// state — same "single request in flight" guarantee Step 3 verified
    /// for `PortfolioViewModel.refresh()`.
    @Test
    func concurrentMutationsForTheSameSymbolOnlyProduceOneRequest() async {
        let service = StubWatchlistService(fetchResult: .success(Self.makeSummary(symbols: [])))
        let viewModel = WatchlistScreenViewModel(watchlistService: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        async let first: Void = viewModel.add(symbol: "AAPL")
        async let second: Void = viewModel.add(symbol: "AAPL")
        _ = await [first, second]

        #expect(await service.addCallCount == 1)
    }
}
