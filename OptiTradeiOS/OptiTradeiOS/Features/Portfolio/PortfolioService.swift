import Foundation

/// Networking for the Portfolio feature. Talks to the *real* backend
/// contract:
///   - `GET /portfolios`                    -> [Portfolio]
///   - `GET /portfolios/{id}/dashboard`      -> PortfolioDashboard
///
/// Both already work with the existing `APIClient`'s Bearer-token
/// injection and 401→refresh handling from Step 1/2 — nothing new was
/// needed there.
protocol PortfolioServicing: Sendable {
    /// The signed-in user's primary portfolio, fully assembled with its
    /// dashboard (summary + holdings). `nil` means the user genuinely has
    /// no portfolio yet — a real, valid state, not an error.
    ///
    /// A user can have multiple portfolios; Step 3 shows exactly one
    /// (the first returned by the backend). Multi-portfolio selection is
    /// not part of this task.
    func fetchPrimaryPortfolio() async throws -> PortfolioSummary?
}

struct PortfolioService: PortfolioServicing {
    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func fetchPrimaryPortfolio() async throws -> PortfolioSummary? {
        let portfolios = try await apiClient.send(APIRequest<[PortfolioDTO]>(path: "portfolios"))
        guard let portfolio = portfolios.first, let id = portfolio.id else {
            return nil
        }
        let dashboard = try await apiClient.send(APIRequest<PortfolioDashboardDTO>(path: "portfolios/\(id)/dashboard"))
        return PortfolioSummary(portfolio: portfolio, dashboard: dashboard)
    }
}
