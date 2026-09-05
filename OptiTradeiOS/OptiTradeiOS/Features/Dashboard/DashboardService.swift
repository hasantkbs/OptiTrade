import Foundation

/// Orchestration for the Dashboard's own data needs. Deliberately thin:
/// the Dashboard's Watchlist/Quant-Opportunities/AI-Analyst sections all
/// read directly from the *shared* `WatchlistScreenViewModel` instance
/// (see `DashboardScreenView`'s doc comment) rather than fetching a
/// second copy of the same data here — this service exists only for the
/// one piece of data Dashboard needs independently: the Portfolio
/// summary, via Step 3's existing `PortfolioServicing`
/// (`GET /portfolios` + `GET /portfolios/{id}/dashboard`). No new
/// endpoint, no new HTTP client.
protocol DashboardServicing: Sendable {
    func fetchPortfolioSummary() async throws -> PortfolioSummary?
}

struct DashboardService: DashboardServicing {
    private let portfolioService: PortfolioServicing

    init(portfolioService: PortfolioServicing) {
        self.portfolioService = portfolioService
    }

    func fetchPortfolioSummary() async throws -> PortfolioSummary? {
        try await portfolioService.fetchPrimaryPortfolio()
    }
}
