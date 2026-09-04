import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct AIAnalystViewModelTests {
    private static func explanation(symbol: String, text: String = "Technical is bullish.") -> AIAnalystExplanation {
        AIAnalystExplanation(
            context: AIAnalystContext(dto: AIAnalystPipelineResponseDTO(
                symbol: symbol, decision: .buy, confidence: 0.8, expectedReturn: 0.05, expectedVolatility: 0.1,
                evidence: ["evidence line"],
                risk: RiskAssessmentDTO(riskLevel: "MEDIUM", expectedVolatility: 0.1, dataSufficiency: 0.7),
                explanation: text
            )),
            message: AIAnalystMessage(role: .assistant, text: text)
        )
    }

    @Test
    func initialStateIsIdle() {
        let viewModel = AIAnalystViewModel(service: StubAIAnalystService(result: .success(Self.explanation(symbol: "AAPL"))), logger: TestLogger())
        #expect(viewModel.state == .idle)
    }

    @Test
    func loadTransitionsToLoadedOnSuccess() async throws {
        let service = StubAIAnalystService(result: .success(Self.explanation(symbol: "AAPL")))
        let viewModel = AIAnalystViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .loaded(Self.explanation(symbol: "AAPL")))
    }

    @Test
    func loadTransitionsToEmptyWhenBackendHasNoExplanation() async throws {
        let service = StubAIAnalystService(result: .success(nil))
        let viewModel = AIAnalystViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .empty)
    }

    @Test
    func loadTransitionsToFailedOnServerError() async throws {
        let service = StubAIAnalystService(result: .failure(APIClientError.server(statusCode: 500, payload: nil)))
        let viewModel = AIAnalystViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .failed("The server is having trouble. Please try again shortly."))
    }

    @Test
    func loadTransitionsToFailedOnNetworkFailure() async throws {
        let service = StubAIAnalystService(result: .failure(APIClientError.transport("offline")))
        let viewModel = AIAnalystViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .failed("Couldn't reach the server. Check your connection and try again."))
    }

    @Test
    func loadTransitionsToFailedOnUnauthorized() async throws {
        let service = StubAIAnalystService(result: .failure(APIClientError.unauthorized(nil)))
        let viewModel = AIAnalystViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .failed("Incorrect email or password."))
    }

    /// Doubles as "duplicate submission prevention" — this screen's one
    /// request is the initial load, so re-entering with the same symbol
    /// while already loaded must not fire a second network call.
    @Test
    func sameSymbolLoadWhileAlreadyLoadedIsANoOp() async throws {
        let service = StubAIAnalystService(result: .success(Self.explanation(symbol: "AAPL")))
        let viewModel = AIAnalystViewModel(service: service, logger: TestLogger())
        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(await service.callCount == 1)
    }

    /// Section 14: "AAPL request followed by TSLA request must never allow
    /// AAPL's response to overwrite TSLA's screen." AAPL is slow, TSLA is
    /// instant — without the guard, AAPL's late response would land after
    /// TSLA's and silently replace it.
    @Test
    func switchingSymbolsCancelsTheStaleRequestAndTheNewerSymbolWins() async throws {
        let service = StubAIAnalystService(result: .success(Self.explanation(symbol: "AAPL")))
        await service.setResult(.success(Self.explanation(symbol: "AAPL")), forSymbol: "AAPL")
        await service.setDelay(80_000_000, forSymbol: "AAPL")
        await service.setResult(.success(Self.explanation(symbol: "TSLA")), forSymbol: "TSLA")

        let viewModel = AIAnalystViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 10_000_000)
        viewModel.load(symbol: "TSLA", assetType: "stock")

        try await Task.sleep(nanoseconds: 150_000_000)

        #expect(viewModel.state == .loaded(Self.explanation(symbol: "TSLA")))
        #expect(viewModel.symbol == "TSLA")
    }

    /// Section 14: leaving the screen must cancel an in-flight request so
    /// its late completion can never update `state`.
    @Test
    func cancelStopsAPendingRequestFromEverUpdatingState() async throws {
        let service = StubAIAnalystService(result: .success(Self.explanation(symbol: "AAPL")), delayNanoseconds: 60_000_000)
        let viewModel = AIAnalystViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 10_000_000) // let the request actually start
        viewModel.cancel()

        try await Task.sleep(nanoseconds: 100_000_000) // long enough for the stub's delay to have elapsed
        #expect(viewModel.state == .loading) // never advanced to .loaded
    }
}
