import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct PortfolioViewModelTests {
    private static func makeSummary(totalValue: Double = 10_500) -> PortfolioSummary {
        PortfolioSummary(
            portfolio: PortfolioDTO(id: 1, owner: "trader@optitrade.app", name: "Main", baseCurrency: "USD"),
            dashboard: PortfolioDashboardDTO(
                portfolioId: 1,
                cashBalance: 500,
                totalValue: totalValue,
                realizedPnl: 100,
                unrealizedPnl: 250,
                positions: [
                    PositionAnalyticsDTO(
                        symbol: "AAPL", quantity: 10, averageCost: 150, currentPrice: 175,
                        costBasis: 1500, currentValue: 1750, unrealizedPnl: 250, unrealizedPnlPct: 16.67,
                        realizedPnl: 0, weightPct: 16.7, sector: "Technology", country: "US", currency: "USD"
                    ),
                ]
            )
        )
    }

    @Test
    func initialStateIsIdleBeforeLoading() {
        let viewModel = PortfolioViewModel(portfolioService: StubPortfolioService(), logger: TestLogger())
        #expect(viewModel.state == .idle)
    }

    @Test
    func loadIfNeededTransitionsToLoadedOnSuccess() async {
        let summary = Self.makeSummary()
        let service = StubPortfolioService(result: .success(summary))
        let viewModel = PortfolioViewModel(portfolioService: service, logger: TestLogger())

        await viewModel.loadIfNeeded()

        #expect(viewModel.state == .loaded(summary))
    }

    @Test
    func loadIfNeededTransitionsToEmptyWhenNoPortfolioExists() async {
        let service = StubPortfolioService(result: .success(nil))
        let viewModel = PortfolioViewModel(portfolioService: service, logger: TestLogger())

        await viewModel.loadIfNeeded()

        #expect(viewModel.state == .empty)
    }

    @Test
    func loadIfNeededTransitionsToFailedOnError() async {
        let service = StubPortfolioService(result: .failure(APIClientError.server(statusCode: 500, payload: nil)))
        let viewModel = PortfolioViewModel(portfolioService: service, logger: TestLogger())

        await viewModel.loadIfNeeded()

        #expect(viewModel.state == .failed("The server is having trouble. Please try again shortly."))
    }

    @Test
    func loadIfNeededIsANoOpOnceLoadingHasStarted() async {
        let service = StubPortfolioService(result: .success(Self.makeSummary()), delayNanoseconds: 20_000_000)
        let viewModel = PortfolioViewModel(portfolioService: service, logger: TestLogger())

        async let first: Void = viewModel.loadIfNeeded()
        async let second: Void = viewModel.loadIfNeeded()
        _ = await [first, second]

        #expect(await service.callCount == 1)
    }

    @Test
    func refreshReplacesLoadedDataOnSuccess() async {
        let service = StubPortfolioService(result: .success(Self.makeSummary(totalValue: 10_500)))
        let viewModel = PortfolioViewModel(portfolioService: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setResult(.success(Self.makeSummary(totalValue: 11_000)))
        await viewModel.refresh()

        #expect(viewModel.state == .loaded(Self.makeSummary(totalValue: 11_000)))
        #expect(viewModel.refreshError == nil)
    }

    @Test
    func refreshFailurePreservesExistingLoadedDataAndSurfacesABanner() async {
        let summary = Self.makeSummary()
        let service = StubPortfolioService(result: .success(summary))
        let viewModel = PortfolioViewModel(portfolioService: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setResult(.failure(APIClientError.transport("offline")))
        await viewModel.refresh()

        #expect(viewModel.state == .loaded(summary)) // unchanged — not replaced by .failed
        #expect(viewModel.refreshError == "Couldn't reach the server. Check your connection and try again.")
    }

    @Test
    func repeatedRefreshTapsOnlyProduceOneRequest() async {
        let service = StubPortfolioService(result: .success(Self.makeSummary()), delayNanoseconds: 20_000_000)
        let viewModel = PortfolioViewModel(portfolioService: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        async let first: Void = viewModel.refresh()
        async let second: Void = viewModel.refresh()
        _ = await [first, second]

        #expect(await service.callCount == 2) // one from loadIfNeeded, exactly one from the two racing refreshes
    }
}

private extension StubPortfolioService {
    func setResult(_ newResult: Result<PortfolioSummary?, Error>) {
        result = newResult
    }
}
