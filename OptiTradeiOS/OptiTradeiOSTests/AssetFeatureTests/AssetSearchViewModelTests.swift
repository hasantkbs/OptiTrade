import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct AssetSearchViewModelTests {
    private static func result(symbol: String, name: String) -> AssetSearchResult {
        AssetSearchResult(symbol: symbol, name: name, market: "US", currency: "USD")
    }

    @Test
    func initialStateIsIdle() {
        let viewModel = AssetSearchViewModel(market: "US", service: StubAssetSearchService(), logger: TestLogger(), debounceNanoseconds: 0)
        #expect(viewModel.state == .idle)
    }

    @Test
    func blankQueryResetsToIdleWithoutSearching() async throws {
        let service = StubAssetSearchService()
        let viewModel = AssetSearchViewModel(market: "US", service: service, logger: TestLogger(), debounceNanoseconds: 0)

        viewModel.query = "   "
        try await Task.sleep(nanoseconds: 20_000_000)

        #expect(viewModel.state == .idle)
        #expect(await service.callCount == 0)
    }

    @Test
    func successfulSearchTransitionsToLoaded() async throws {
        let service = StubAssetSearchService(result: .success([Self.result(symbol: "AAPL", name: "Apple")]))
        let viewModel = AssetSearchViewModel(market: "US", service: service, logger: TestLogger(), debounceNanoseconds: 0)

        viewModel.query = "AAPL"
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .loaded([Self.result(symbol: "AAPL", name: "Apple")]))
    }

    @Test
    func searchWithNoMatchesTransitionsToEmpty() async throws {
        let service = StubAssetSearchService(result: .success([]))
        let viewModel = AssetSearchViewModel(market: "US", service: service, logger: TestLogger(), debounceNanoseconds: 0)

        viewModel.query = "ZZZZ"
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .empty)
    }

    @Test
    func searchFailureTransitionsToFailed() async throws {
        let service = StubAssetSearchService(result: .failure(APIClientError.server(statusCode: 500, payload: nil)))
        let viewModel = AssetSearchViewModel(market: "US", service: service, logger: TestLogger(), debounceNanoseconds: 0)

        viewModel.query = "AAPL"
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .failed("The server is having trouble. Please try again shortly."))
    }

    /// User types "A" then quickly "AAP" — the slow first search must not
    /// overwrite the fast second one. Exercises `Task` cancellation, not
    /// just debounce collapsing: the first search is already in flight
    /// (past its debounce) when the second keystroke lands.
    @Test
    func staleSearchIsCancelledAndTheLatestQueryWins() async throws {
        let service = StubAssetSearchService()
        let viewModel = AssetSearchViewModel(market: "US", service: service, logger: TestLogger(), debounceNanoseconds: 0)

        await service.setDelay(60_000_000)
        await service.setResult(.success([Self.result(symbol: "A", name: "Agilent")]))
        viewModel.query = "A"
        try await Task.sleep(nanoseconds: 10_000_000) // let the first search actually start

        await service.setDelay(0)
        await service.setResult(.success([Self.result(symbol: "AAPL", name: "Apple")]))
        viewModel.query = "AAPL" // cancels the first task before its 60ms delay elapses

        try await Task.sleep(nanoseconds: 100_000_000)

        #expect(viewModel.state == .loaded([Self.result(symbol: "AAPL", name: "Apple")]))
        #expect(await service.callCount == 2)
    }

    @Test
    func clearResetsQueryAndState() async throws {
        let service = StubAssetSearchService(result: .success([Self.result(symbol: "AAPL", name: "Apple")]))
        let viewModel = AssetSearchViewModel(market: "US", service: service, logger: TestLogger(), debounceNanoseconds: 0)
        viewModel.query = "AAPL"
        try await Task.sleep(nanoseconds: 30_000_000)
        #expect(viewModel.state == .loaded([Self.result(symbol: "AAPL", name: "Apple")]))

        viewModel.clear()

        #expect(viewModel.query == "")
        #expect(viewModel.state == .idle)
    }
}
