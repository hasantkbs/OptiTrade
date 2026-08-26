import Foundation
import Testing
@testable import OptiTradeiOS

/// Verifies `PortfolioService` speaks the *real* backend contract
/// (`backend/portfolio/models.py` + `backend/main.py`'s `/portfolios`
/// routes) using a mock transport — never the live backend.
struct PortfolioServiceTests {
    private static let portfolioJSON = Data("""
    [{"id": 1, "owner": "trader@optitrade.app", "name": "Main", "base_currency": "USD", "created_at": "2026-01-01T00:00:00Z"}]
    """.utf8)

    private static let dashboardJSON = Data("""
    {
      "portfolio_id": 1,
      "as_of": "2026-01-01T00:00:00Z",
      "cash_balance": 500.0,
      "total_value": 10500.0,
      "realized_pnl": 100.0,
      "unrealized_pnl": 250.0,
      "positions": [
        {
          "symbol": "AAPL", "quantity": 10, "average_cost": 150.0, "current_price": 175.0,
          "cost_basis": 1500.0, "current_value": 1750.0, "unrealized_pnl": 250.0,
          "unrealized_pnl_pct": 16.67, "realized_pnl": 0.0, "weight_pct": 16.7,
          "sector": "Technology", "country": "US", "currency": "USD"
        }
      ],
      "allocation": {"by_symbol_pct": {}, "by_sector_pct": {}, "by_country_pct": {}, "by_currency_pct": {}, "cash_weight_pct": 4.8},
      "risk": null,
      "recommendations": []
    }
    """.utf8)

    @Test
    func fetchesPrimaryPortfolioByCombiningPortfoliosAndDashboardCalls() async throws {
        let transport = MockHTTPTransport(stubs: [
            .raw(200, Self.portfolioJSON),
            .raw(200, Self.dashboardJSON),
        ])
        let service = PortfolioService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let summary = try #require(try await service.fetchPrimaryPortfolio())

        #expect(summary.portfolioID == 1)
        #expect(summary.name == "Main")
        #expect(summary.baseCurrency == "USD")
        #expect(summary.totalValue == 10500.0)
        #expect(summary.cashBalance == 500.0)
        #expect(summary.positions.count == 1)
        #expect(summary.positions.first?.symbol == "AAPL")
        #expect(summary.positions.first?.unrealizedPnLPct == 16.67)

        let recorded = await transport.recordedRequests
        #expect(recorded[0].url?.path == "/portfolios")
        #expect(recorded[1].url?.path == "/portfolios/1/dashboard")
    }

    @Test
    func emptyPortfolioListReturnsNilWithoutCallingDashboard() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("[]".utf8))])
        let service = PortfolioService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let summary = try await service.fetchPrimaryPortfolio()

        #expect(summary == nil)
        #expect(await transport.recordedRequests.count == 1)
    }

    @Test
    func unauthorizedResponseSurfacesAsTypedError() async {
        let transport = MockHTTPTransport(stubs: [.json(401, ["detail": "Yetkilendirme tokeni eksik."])])
        let service = PortfolioService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchPrimaryPortfolio()
        }
    }

    @Test
    func transportFailureSurfacesAsTypedError() async {
        let transport = MockHTTPTransport(stubs: [.failure(APIClientError.transport("offline"))])
        let service = PortfolioService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchPrimaryPortfolio()
        }
    }

    @Test
    func malformedResponseSurfacesAsDecodingError() async {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("not json".utf8))])
        let service = PortfolioService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchPrimaryPortfolio()
        }
    }
}
