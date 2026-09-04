import Foundation
import Testing
@testable import OptiTradeiOS

/// Verifies `WatchlistService` speaks the *real* backend contract
/// (`backend/watchlist/models.py` + `backend/main.py`'s `/watchlists`
/// routes) using a mock transport — never the live backend.
struct WatchlistServiceTests {
    private static let watchlistsJSON = Data("""
    [{"id": 1, "owner": "trader@optitrade.app", "name": "My Watchlist", "created_at": "2026-01-01T00:00:00Z"}]
    """.utf8)

    private static let itemsJSON = Data("""
    [{"id": 1, "watchlist_id": 1, "symbol": "AAPL", "is_favorite": false, "folder": null, "tags": [], "notes": "", "added_at": "2026-01-01T00:00:00Z"}]
    """.utf8)

    @Test
    func fetchesPrimaryWatchlistByCombiningWatchlistsAndItemsCalls() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Self.watchlistsJSON), .raw(200, Self.itemsJSON)])
        let service = WatchlistService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let summary = try #require(try await service.fetchPrimaryWatchlist())

        #expect(summary.watchlistID == 1)
        #expect(summary.name == "My Watchlist")
        #expect(summary.items.count == 1)
        #expect(summary.items.first?.symbol == "AAPL")

        let recorded = await transport.recordedRequests
        #expect(recorded[0].url?.path == "/watchlists")
        #expect(recorded[1].url?.path == "/watchlists/1/items")
    }

    @Test
    func emptyWatchlistListReturnsNilWithoutCallingItems() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("[]".utf8))])
        let service = WatchlistService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let summary = try await service.fetchPrimaryWatchlist()

        #expect(summary == nil)
        #expect(await transport.recordedRequests.count == 1)
    }

    @Test
    func createWatchlistPostsNameAndReturnsTheNewId() async throws {
        let createdJSON = Data("""
        {"id": 7, "owner": "trader@optitrade.app", "name": "My Watchlist", "created_at": "2026-01-01T00:00:00Z"}
        """.utf8)
        let transport = MockHTTPTransport(stubs: [.raw(200, createdJSON)])
        let service = WatchlistService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let id = try await service.createWatchlist(name: "My Watchlist")

        #expect(id == 7)
        let recorded = await transport.recordedRequests
        #expect(recorded[0].url?.path == "/watchlists")
        #expect(recorded[0].httpMethod == "POST")
    }

    @Test
    func addSymbolPostsToTheItemsEndpoint() async throws {
        let itemJSON = Data("""
        {"id": 5, "watchlist_id": 1, "symbol": "AAPL", "is_favorite": false, "folder": null, "tags": [], "notes": "", "added_at": "2026-01-01T00:00:00Z"}
        """.utf8)
        let transport = MockHTTPTransport(stubs: [.raw(200, itemJSON)])
        let service = WatchlistService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let item = try await service.addSymbol("AAPL", toWatchlist: 1)

        #expect(item.symbol == "AAPL")
        let recorded = await transport.recordedRequests
        #expect(recorded[0].url?.path == "/watchlists/1/items")
        #expect(recorded[0].httpMethod == "POST")
    }

    @Test
    func removeSymbolDeletesTheItemBySymbol() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("""
        {"status": "deleted"}
        """.utf8))])
        let service = WatchlistService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        try await service.removeSymbol("AAPL", fromWatchlist: 1)

        let recorded = await transport.recordedRequests
        #expect(recorded[0].url?.path == "/watchlists/1/items/AAPL")
        #expect(recorded[0].httpMethod == "DELETE")
    }

    @Test
    func unauthorizedResponseSurfacesAsTypedError() async {
        let transport = MockHTTPTransport(stubs: [.json(401, ["detail": "Yetkilendirme tokeni eksik."])])
        let service = WatchlistService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchPrimaryWatchlist()
        }
    }

    @Test
    func transportFailureSurfacesAsTypedError() async {
        let transport = MockHTTPTransport(stubs: [.failure(APIClientError.transport("offline"))])
        let service = WatchlistService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchPrimaryWatchlist()
        }
    }

    @Test
    func malformedResponseSurfacesAsDecodingError() async {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("not json".utf8))])
        let service = WatchlistService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchPrimaryWatchlist()
        }
    }
}
