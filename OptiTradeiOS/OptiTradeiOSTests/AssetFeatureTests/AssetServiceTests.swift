import Foundation
import Testing
@testable import OptiTradeiOS

/// Verifies `AssetService` speaks the *real* backend contract
/// (`GET /market/watchlist/{market}` — `backend/core/market_config.py` +
/// `backend/main.py`) using a mock transport — never the live backend.
struct AssetServiceTests {
    private static let marketWatchlistJSON = Data("""
    {
      "market": "US",
      "info": {
        "name": "Amerika (NYSE/NASDAQ)",
        "flag": "🇺🇸",
        "currency": "USD",
        "timezone": "America/New_York",
        "session_open": "09:30",
        "session_close": "16:00",
        "index_symbol": "^GSPC",
        "index_name": "S&P 500",
        "description": "New York borsalari"
      },
      "watchlist": ["AAPL", "MSFT"],
      "symbols": {"AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA"}
    }
    """.utf8)

    @Test
    func successfulSearchFiltersDirectoryBySymbolOrName() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Self.marketWatchlistJSON)])
        let service = AssetService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let results = try await service.search(query: "app", market: "US")

        #expect(results.count == 1)
        #expect(results.first?.symbol == "AAPL")
        #expect(results.first?.name == "Apple")
        #expect(results.first?.market == "US")
        #expect(results.first?.currency == "USD")
    }

    @Test
    func emptyQueryReturnsNoResultsWithoutCallingTheNetwork() async throws {
        let transport = MockHTTPTransport()
        let service = AssetService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let results = try await service.search(query: "   ", market: "US")

        #expect(results.isEmpty)
        #expect(await transport.recordedRequests.isEmpty)
    }

    @Test
    func nonMatchingQueryReturnsEmptyResults() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Self.marketWatchlistJSON)])
        let service = AssetService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let results = try await service.search(query: "ZZZZ", market: "US")

        #expect(results.isEmpty)
    }

    @Test
    func secondSearchInTheSameMarketReusesTheCachedDirectory() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Self.marketWatchlistJSON)])
        let service = AssetService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        _ = try await service.search(query: "apple", market: "US")
        _ = try await service.search(query: "micro", market: "US")

        #expect(await transport.recordedRequests.count == 1)
    }

    @Test
    func transportFailureSurfacesAsTypedError() async {
        let transport = MockHTTPTransport(stubs: [.failure(APIClientError.transport("offline"))])
        let service = AssetService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.search(query: "aapl", market: "US")
        }
    }

    @Test
    func malformedResponseSurfacesAsDecodingError() async {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("not json".utf8))])
        let service = AssetService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.search(query: "aapl", market: "US")
        }
    }
}
