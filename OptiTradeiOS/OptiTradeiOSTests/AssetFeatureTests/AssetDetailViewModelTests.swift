import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct AssetDetailViewModelTests {
    private static func engineVote(
        name: String,
        status: EngineExecutionStatus = .success,
        prediction: QuantDecision? = .buy,
        confidence: Double? = 0.8
    ) -> EngineVoteSummary {
        EngineVoteSummary(dto: EngineBreakdownItemDTO(
            engineName: name, engineVersion: "1.0.0", status: status, prediction: prediction,
            confidence: confidence, expectedReturn: status == .success ? 0.05 : nil,
            volatility: status == .success ? 0.1 : nil,
            evidence: status == .success ? ["evidence line"] : []
        ))
    }

    private static func summary(symbol: String, decision: QuantDecision = .buy) -> AssetDetailSummary {
        AssetDetailSummary(
            symbol: symbol,
            quant: QuantAnalysis(dto: PipelineResponseDTO(
                symbol: symbol, decision: decision, confidence: 0.8, expectedReturn: 0.04, expectedVolatility: 0.1,
                engineBreakdown: [
                    EngineBreakdownItemDTO(engineName: "TechnicalEngine", engineVersion: "1.0.0", status: .success, prediction: decision, confidence: 0.8, expectedReturn: 0.05, volatility: 0.1, evidence: ["technical evidence"]),
                    EngineBreakdownItemDTO(engineName: "FundamentalEngine", engineVersion: "1.0.0", status: .failed, prediction: nil, confidence: nil, expectedReturn: nil, volatility: nil, evidence: []),
                    EngineBreakdownItemDTO(engineName: "NewsEngine", engineVersion: "1.0.0", status: .success, prediction: .hold, confidence: 0.5, expectedReturn: 0.01, volatility: 0.08, evidence: ["news evidence"]),
                ],
                evidence: ["top-level evidence"],
                risk: RiskAssessmentDTO(riskLevel: "MEDIUM", expectedVolatility: 0.1, dataSufficiency: 0.7),
                metadata: PipelineMetadataDTO(pipelineVersion: "1.0.0", enginesAvailable: 3, enginesSucceeded: 2, degraded: true)
            )),
            marketData: nil,
            chart: nil
        )
    }

    @Test
    func initialStateIsIdle() {
        let viewModel = AssetDetailViewModel(service: StubAssetDetailService(result: .success(Self.summary(symbol: "AAPL"))), logger: TestLogger())
        #expect(viewModel.state == .idle)
    }

    @Test
    func loadTransitionsToLoadedOnSuccess() async throws {
        let service = StubAssetDetailService(result: .success(Self.summary(symbol: "AAPL")))
        let viewModel = AssetDetailViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .loaded(Self.summary(symbol: "AAPL")))
    }

    @Test
    func loadTransitionsToFailedOnServerError() async throws {
        let service = StubAssetDetailService(result: .failure(APIClientError.server(statusCode: 500, payload: nil)))
        let viewModel = AssetDetailViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .failed("The server is having trouble. Please try again shortly."))
    }

    @Test
    func loadTransitionsToFailedOnNetworkFailure() async throws {
        let service = StubAssetDetailService(result: .failure(APIClientError.transport("offline")))
        let viewModel = AssetDetailViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .failed("Couldn't reach the server. Check your connection and try again."))
    }

    @Test
    func loadTransitionsToFailedOnUnauthorized() async throws {
        let service = StubAssetDetailService(result: .failure(APIClientError.unauthorized(nil)))
        let viewModel = AssetDetailViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .failed("Incorrect email or password."))
    }

    @Test
    func loadTransitionsToFailedOnDecodingError() async throws {
        let service = StubAssetDetailService(result: .failure(APIClientError.decoding("bad shape")))
        let viewModel = AssetDetailViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(viewModel.state == .failed("Unexpected response from the server."))
    }

    @Test
    func partiallyUnavailableAnalysisIsSurfacedNotFailed() async throws {
        let service = StubAssetDetailService(result: .success(Self.summary(symbol: "AAPL")))
        let viewModel = AssetDetailViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        guard case .loaded(let summary) = viewModel.state else {
            Issue.record("expected .loaded")
            return
        }
        #expect(summary.quant.technical?.status == .success)
        #expect(summary.quant.fundamental?.status == .failed)
        #expect(summary.quant.fundamental?.prediction == nil) // never backfilled with a fake value
        #expect(summary.quant.news?.status == .success)
    }

    @Test
    func sameSymbolLoadWhileAlreadyLoadedIsANoOp() async throws {
        let service = StubAssetDetailService(result: .success(Self.summary(symbol: "AAPL")))
        let viewModel = AssetDetailViewModel(service: service, logger: TestLogger())
        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 30_000_000)

        #expect(await service.callCount == 1)
    }

    @Test
    func refreshReplacesLoadedDataOnSuccess() async {
        let service = StubAssetDetailService(result: .success(Self.summary(symbol: "AAPL", decision: .hold)))
        let viewModel = AssetDetailViewModel(service: service, logger: TestLogger())
        viewModel.load(symbol: "AAPL", assetType: "stock")
        try? await Task.sleep(nanoseconds: 30_000_000)

        await service.setResult(.success(Self.summary(symbol: "AAPL", decision: .buy)))
        await viewModel.refresh(assetType: "stock")

        #expect(viewModel.state == .loaded(Self.summary(symbol: "AAPL", decision: .buy)))
        #expect(viewModel.refreshError == nil)
    }

    @Test
    func refreshFailurePreservesExistingLoadedDataAndSurfacesABanner() async {
        let summary = Self.summary(symbol: "AAPL")
        let service = StubAssetDetailService(result: .success(summary))
        let viewModel = AssetDetailViewModel(service: service, logger: TestLogger())
        viewModel.load(symbol: "AAPL", assetType: "stock")
        try? await Task.sleep(nanoseconds: 30_000_000)

        await service.setResult(.failure(APIClientError.transport("offline")))
        await viewModel.refresh(assetType: "stock")

        #expect(viewModel.state == .loaded(summary)) // unchanged — not replaced by .failed
        #expect(viewModel.refreshError == "Couldn't reach the server. Check your connection and try again.")
    }

    /// Section 17: "AAPL request followed by TSLA request must never allow
    /// AAPL's response to overwrite TSLA's screen." AAPL is given a long
    /// delay, TSLA none — if the guard were missing, AAPL's late response
    /// would land after TSLA's and silently replace it.
    @Test
    func switchingSymbolsCancelsTheStaleRequestAndTheNewerSymbolWins() async throws {
        let service = StubAssetDetailService(result: .success(Self.summary(symbol: "AAPL")))
        await service.setResult(.success(Self.summary(symbol: "AAPL")), forSymbol: "AAPL")
        await service.setDelay(80_000_000, forSymbol: "AAPL")
        await service.setResult(.success(Self.summary(symbol: "TSLA")), forSymbol: "TSLA")

        let viewModel = AssetDetailViewModel(service: service, logger: TestLogger())

        viewModel.load(symbol: "AAPL", assetType: "stock")
        try await Task.sleep(nanoseconds: 10_000_000) // let AAPL's request actually start
        viewModel.load(symbol: "TSLA", assetType: "stock") // cancels AAPL before its 80ms delay elapses

        try await Task.sleep(nanoseconds: 150_000_000)

        #expect(viewModel.state == .loaded(Self.summary(symbol: "TSLA")))
        #expect(viewModel.symbol == "TSLA")
    }
}
