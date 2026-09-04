import Foundation
import Testing
@testable import OptiTradeiOS

/// Verifies `AIAnalystService` speaks the *real* backend contract — the
/// same `POST /quant/analyze` (`backend/pipeline/models.py`'s
/// `PipelineResponse`), but decoding this feature's own DTO that also
/// includes `explanation` (Step 5's `PipelineResponseDTO` deliberately
/// excludes it — see `AIAnalystModels.swift`). Never calls a live LLM
/// provider or the live backend.
struct AIAnalystServiceTests {
    private static func pipelineJSON(explanation: String) -> Data {
        Data("""
        {
          "symbol": "AAPL",
          "decision": "BUY",
          "confidence": 0.82,
          "expected_return": 0.045,
          "expected_volatility": 0.12,
          "engine_breakdown": [],
          "evidence": ["Technical and News agree on upward bias"],
          "risk": {"risk_level": "MEDIUM", "expected_volatility": 0.12, "data_sufficiency": 0.67},
          "explanation": "\(explanation)",
          "metadata": {
            "pipeline_version": "1.0.0", "total_duration_ms": 120.5, "stage_durations_ms": {},
            "engines_available": 3, "engines_succeeded": 3, "degraded": false,
            "timestamp": "2026-09-04T00:00:00Z"
          }
        }
        """.utf8)
    }

    @Test
    func fetchesExplanationAndMapsItToAnAssistantMessage() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Self.pipelineJSON(explanation: "Technical is bullish while Fundamental is neutral."))])
        let service = AIAnalystService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let explanation = try #require(try await service.fetchExplanation(symbol: "AAPL", assetType: "stock"))

        #expect(explanation.context.symbol == "AAPL")
        #expect(explanation.context.decision == .buy)
        #expect(explanation.context.confidence == 0.82)
        #expect(explanation.context.risk.riskLevel == "MEDIUM")
        #expect(explanation.context.evidence == ["Technical and News agree on upward bias"])
        #expect(explanation.message.role == .assistant)
        #expect(explanation.message.text == "Technical is bullish while Fundamental is neutral.")

        let recorded = await transport.recordedRequests
        #expect(recorded[0].url?.path == "/quant/analyze")
        #expect(recorded[0].httpMethod == "POST")
    }

    @Test
    func emptyExplanationTextReturnsNilRatherThanAnEmptyMessage() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Self.pipelineJSON(explanation: "   "))])
        let service = AIAnalystService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let explanation = try await service.fetchExplanation(symbol: "AAPL", assetType: "stock")

        #expect(explanation == nil)
    }

    @Test
    func requestBodySendsSymbolAndAssetType() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Self.pipelineJSON(explanation: "text"))])
        let service = AIAnalystService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        _ = try await service.fetchExplanation(symbol: "TSLA", assetType: "stock")

        let recorded = await transport.recordedRequests
        let body = try #require(recorded[0].httpBody)
        let decoded = try JSONDecoder().decode([String: String].self, from: body)
        #expect(decoded["symbol"] == "TSLA")
        #expect(decoded["asset_type"] == "stock")
    }

    @Test
    func unauthorizedResponseSurfacesAsTypedError() async {
        let transport = MockHTTPTransport(stubs: [.json(401, ["detail": "Yetkilendirme tokeni eksik."])])
        let service = AIAnalystService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchExplanation(symbol: "AAPL", assetType: "stock")
        }
    }

    @Test
    func backendUnavailableSurfacesAsTypedError() async {
        // 503: pipeline service not ready (`_pipeline_service is None` in main.py).
        let transport = MockHTTPTransport(stubs: [.json(503, ["detail": "Quant pipeline henuz hazir degil."])])
        let service = AIAnalystService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchExplanation(symbol: "AAPL", assetType: "stock")
        }
    }

    @Test
    func networkFailureSurfacesAsTypedError() async {
        let transport = MockHTTPTransport(stubs: [.failure(APIClientError.transport("offline"))])
        let service = AIAnalystService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchExplanation(symbol: "AAPL", assetType: "stock")
        }
    }

    @Test
    func malformedResponseSurfacesAsDecodingError() async {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("not json".utf8))])
        let service = AIAnalystService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchExplanation(symbol: "AAPL", assetType: "stock")
        }
    }
}
