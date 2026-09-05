import Foundation
import Testing
@testable import OptiTradeiOS

/// Verifies `DashboardService` is a faithful pass-through over the
/// *existing* `PortfolioServicing` (Step 3) — no new HTTP contract, no
/// remapping that could drop or alter a real value like `baseCurrency`.
struct DashboardServiceTests {
    private static func summary(totalValue: Double = 10_500, currency: String = "USD") -> PortfolioSummary {
        PortfolioSummary(
            portfolio: PortfolioDTO(id: 1, owner: "trader@optitrade.app", name: "Main", baseCurrency: currency),
            dashboard: PortfolioDashboardDTO(
                portfolioId: 1, cashBalance: 500, totalValue: totalValue, realizedPnl: 100, unrealizedPnl: 250, positions: []
            )
        )
    }

    @Test
    func fetchPortfolioSummaryPassesThroughTheLoadedSummaryUnchanged() async throws {
        let summary = Self.summary(currency: "TRY")
        let portfolioService = StubPortfolioService(result: .success(summary))
        let service = DashboardService(portfolioService: portfolioService)

        let result = try await service.fetchPortfolioSummary()

        #expect(result == summary)
        #expect(result?.baseCurrency == "TRY") // currency preserved, never assumed
        #expect(await portfolioService.callCount == 1)
    }

    @Test
    func fetchPortfolioSummaryPassesThroughNilForNoPortfolio() async throws {
        let portfolioService = StubPortfolioService(result: .success(nil))
        let service = DashboardService(portfolioService: portfolioService)

        let result = try await service.fetchPortfolioSummary()

        #expect(result == nil)
    }

    @Test
    func fetchPortfolioSummaryPropagatesFailure() async {
        let portfolioService = StubPortfolioService(result: .failure(APIClientError.server(statusCode: 500, payload: nil)))
        let service = DashboardService(portfolioService: portfolioService)

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchPortfolioSummary()
        }
    }
}
