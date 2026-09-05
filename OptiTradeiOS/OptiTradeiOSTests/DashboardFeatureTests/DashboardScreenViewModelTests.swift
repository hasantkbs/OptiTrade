import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct DashboardScreenViewModelTests {
    private static func summary(totalValue: Double = 10_500) -> PortfolioSummary {
        PortfolioSummary(
            portfolio: PortfolioDTO(id: 1, owner: "trader@optitrade.app", name: "Main", baseCurrency: "USD"),
            dashboard: PortfolioDashboardDTO(
                portfolioId: 1, cashBalance: 500, totalValue: totalValue, realizedPnl: 100, unrealizedPnl: 250, positions: []
            )
        )
    }

    @Test
    func initialStateIsIdleBeforeLoading() {
        let viewModel = DashboardScreenViewModel(service: StubDashboardService(), logger: TestLogger())
        #expect(viewModel.portfolioState == .idle)
    }

    @Test
    func loadIfNeededTransitionsToLoadedOnSuccess() async {
        let summary = Self.summary()
        let service = StubDashboardService(result: .success(summary))
        let viewModel = DashboardScreenViewModel(service: service, logger: TestLogger())

        await viewModel.loadIfNeeded()

        #expect(viewModel.portfolioState == .loaded(summary))
    }

    @Test
    func loadIfNeededTransitionsToEmptyWhenNoPortfolioExists() async {
        let service = StubDashboardService(result: .success(nil))
        let viewModel = DashboardScreenViewModel(service: service, logger: TestLogger())

        await viewModel.loadIfNeeded()

        #expect(viewModel.portfolioState == .empty)
    }

    @Test
    func loadIfNeededTransitionsToFailedOnServerError() async {
        let service = StubDashboardService(result: .failure(APIClientError.server(statusCode: 500, payload: nil)))
        let viewModel = DashboardScreenViewModel(service: service, logger: TestLogger())

        await viewModel.loadIfNeeded()

        #expect(viewModel.portfolioState == .failed("The server is having trouble. Please try again shortly."))
    }

    @Test
    func loadIfNeededIsANoOpOnceLoadingHasStarted() async {
        let service = StubDashboardService(result: .success(Self.summary()), delayNanoseconds: 20_000_000)
        let viewModel = DashboardScreenViewModel(service: service, logger: TestLogger())

        async let first: Void = viewModel.loadIfNeeded()
        async let second: Void = viewModel.loadIfNeeded()
        _ = await [first, second]

        #expect(await service.callCount == 1)
    }

    @Test
    func refreshReplacesLoadedDataOnSuccess() async {
        let service = StubDashboardService(result: .success(Self.summary(totalValue: 10_500)))
        let viewModel = DashboardScreenViewModel(service: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setResult(.success(Self.summary(totalValue: 11_000)))
        await viewModel.refresh()

        #expect(viewModel.portfolioState == .loaded(Self.summary(totalValue: 11_000)))
        #expect(viewModel.portfolioRefreshError == nil)
    }

    @Test
    func refreshFailurePreservesExistingLoadedDataAndSurfacesABanner() async {
        let summary = Self.summary()
        let service = StubDashboardService(result: .success(summary))
        let viewModel = DashboardScreenViewModel(service: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setResult(.failure(APIClientError.transport("offline")))
        await viewModel.refresh()

        #expect(viewModel.portfolioState == .loaded(summary)) // unchanged — not replaced by .failed
        #expect(viewModel.portfolioRefreshError == "Couldn't reach the server. Check your connection and try again.")
    }

    @Test
    func repeatedRefreshTapsOnlyProduceOneRequest() async {
        let service = StubDashboardService(result: .success(Self.summary()), delayNanoseconds: 20_000_000)
        let viewModel = DashboardScreenViewModel(service: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        async let first: Void = viewModel.refresh()
        async let second: Void = viewModel.refresh()
        _ = await [first, second]

        #expect(await service.callCount == 2) // one from loadIfNeeded, exactly one from the two racing refreshes
    }

    /// Section 16: cancelling the load must not leave the Portfolio
    /// section permanently stuck showing a spinner.
    @Test
    func cancellingTheLoadTaskDoesNotLeaveTheStateStuckLoading() async throws {
        let service = StubDashboardService(result: .success(Self.summary()), delayNanoseconds: 60_000_000)
        let viewModel = DashboardScreenViewModel(service: service, logger: TestLogger())

        let task = Task { await viewModel.loadIfNeeded() }
        try await Task.sleep(nanoseconds: 10_000_000) // let the request actually start
        task.cancel()

        try await Task.sleep(nanoseconds: 150_000_000) // long enough for the stub's delay to have elapsed
        #expect(viewModel.portfolioState != .loading)
    }

    /// Section 5/6: Portfolio and Watchlist are two independent view
    /// models (Dashboard's own `DashboardScreenViewModel` plus the
    /// shared `WatchlistScreenViewModel` from Step 4) specifically so one
    /// section's failure can never affect the other's rendering.
    @Test
    func portfolioSucceedingWhileWatchlistFailsLeavesPortfolioUnaffected() async {
        let dashboardService = StubDashboardService(result: .success(Self.summary()))
        let dashboardViewModel = DashboardScreenViewModel(service: dashboardService, logger: TestLogger())

        let watchlistService = StubWatchlistService(fetchResult: .failure(APIClientError.server(statusCode: 500, payload: nil)))
        let watchlistViewModel = WatchlistScreenViewModel(watchlistService: watchlistService, logger: TestLogger())

        await dashboardViewModel.loadIfNeeded()
        await watchlistViewModel.loadIfNeeded()

        #expect(dashboardViewModel.portfolioState == .loaded(Self.summary()))
        #expect(watchlistViewModel.state == .failed("The server is having trouble. Please try again shortly."))
    }
}
