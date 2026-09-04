import Foundation
import Testing
@testable import OptiTradeiOS

/// Verifies `AssetDetailService` speaks the *real* backend contract
/// (`backend/pipeline/models.py`'s `PipelineResponse` via
/// `POST /quant/analyze`, plus `GET /price/{symbol}` and
/// `GET /chart/{symbol}`) using a mock transport — never the live
/// backend. Uses `RoutingHTTPTransport` (path-keyed, not FIFO) because
/// the service fires all three requests concurrently.
struct AssetDetailServiceTests {
    private static let pipelineJSON = Data("""
    {
      "symbol": "AAPL",
      "decision": "BUY",
      "confidence": 0.82,
      "expected_return": 0.045,
      "expected_volatility": 0.12,
      "engine_breakdown": [
        {
          "engine_name": "TechnicalEngine", "engine_version": "1.0.0", "status": "success",
          "prediction": "BUY", "confidence": 0.8, "expected_return": 0.05, "volatility": 0.11,
          "evidence": ["RSI at 62.1 signals bullish momentum"]
        },
        {
          "engine_name": "FundamentalEngine", "engine_version": "1.0.0", "status": "failed",
          "prediction": null, "confidence": null, "expected_return": null, "volatility": null,
          "evidence": []
        },
        {
          "engine_name": "NewsEngine", "engine_version": "1.0.0", "status": "success",
          "prediction": "HOLD", "confidence": 0.55, "expected_return": 0.01, "volatility": 0.09,
          "evidence": ["[Reuters] \\"Apple ships new product\\" - sentiment +0.20, impact 0.40, relevance 0.90 (2026-09-01)"]
        }
      ],
      "evidence": ["Technical and News agree on upward bias; Fundamental unavailable"],
      "risk": {"risk_level": "MEDIUM", "expected_volatility": 0.12, "data_sufficiency": 0.67},
      "explanation": "This is an LLM-generated explanation that must never be decoded.",
      "metadata": {
        "pipeline_version": "1.0.0", "total_duration_ms": 120.5, "stage_durations_ms": {},
        "engines_available": 3, "engines_succeeded": 2, "degraded": true,
        "timestamp": "2026-09-04T00:00:00Z"
      }
    }
    """.utf8)

    private static let priceJSON = Data("""
    {"symbol": "AAPL", "price": 227.5, "change_pct": 1.25, "timestamp": "2026-09-04T20:00:00+00:00"}
    """.utf8)

    private static let chartJSON = Data("""
    {"symbol": "AAPL", "period": "3mo", "points": [{"date": "2026-08-01", "close": 220.0, "volume": 1000000, "rsi": 55.0}], "change_pct": 3.4, "high": 230.0, "low": 210.0}
    """.utf8)

    private static func fullTransport() -> RoutingHTTPTransport {
        RoutingHTTPTransport(stubsByPath: [
            "/quant/analyze": .raw(200, pipelineJSON),
            "/price/AAPL": .raw(200, priceJSON),
            "/chart/AAPL": .raw(200, chartJSON),
        ])
    }

    @Test
    func fetchesAssetDetailByCombiningQuantPriceAndChart() async throws {
        let transport = Self.fullTransport()
        let service = AssetDetailService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let summary = try await service.fetchAssetDetail(symbol: "AAPL", assetType: "stock")

        #expect(summary.symbol == "AAPL")
        #expect(summary.quant.decision == .buy)
        #expect(summary.quant.confidence == 0.82)
        #expect(summary.quant.engineVotes.count == 3)
        #expect(summary.quant.technical?.prediction == .buy)
        #expect(summary.quant.fundamental?.status == .failed)
        #expect(summary.quant.fundamental?.prediction == nil)
        #expect(summary.quant.news?.prediction == .hold)
        #expect(summary.quant.risk.riskLevel == "MEDIUM")
        #expect(summary.quant.degraded == true)
        #expect(summary.quant.enginesSucceeded == 2)
        #expect(summary.marketData?.price == 227.5)
        #expect(summary.chart?.points.count == 1)

        let recorded = await transport.recordedRequests
        #expect(recorded.contains { $0.url?.path == "/quant/analyze" && $0.httpMethod == "POST" })
        #expect(recorded.contains { $0.url?.path == "/price/AAPL" })
        #expect(recorded.contains { $0.url?.path == "/chart/AAPL" })
    }

    @Test
    func marketDataAndChartFailuresAreAbsorbedAsNilWithoutFailingTheFetch() async throws {
        let transport = RoutingHTTPTransport(stubsByPath: [
            "/quant/analyze": .raw(200, Self.pipelineJSON),
            "/price/AAPL": .raw(500, Data()),
            "/chart/AAPL": .raw(500, Data()),
        ])
        let service = AssetDetailService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let summary = try await service.fetchAssetDetail(symbol: "AAPL", assetType: "stock")

        #expect(summary.quant.decision == .buy) // core payload still present
        #expect(summary.marketData == nil)
        #expect(summary.chart == nil)
    }

    @Test
    func quantFailureFailsTheWholeFetch() async {
        let transport = RoutingHTTPTransport(stubsByPath: [
            "/quant/analyze": .json(503, ["detail": "Quant pipeline henuz hazir degil."]),
            "/price/AAPL": .raw(200, Self.priceJSON),
            "/chart/AAPL": .raw(200, Self.chartJSON),
        ])
        let service = AssetDetailService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchAssetDetail(symbol: "AAPL", assetType: "stock")
        }
    }

    @Test
    func unauthorizedResponseSurfacesAsTypedError() async {
        let transport = RoutingHTTPTransport(stubsByPath: [
            "/quant/analyze": .json(401, ["detail": "Yetkilendirme tokeni eksik."]),
            "/price/AAPL": .raw(200, Self.priceJSON),
            "/chart/AAPL": .raw(200, Self.chartJSON),
        ])
        let service = AssetDetailService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchAssetDetail(symbol: "AAPL", assetType: "stock")
        }
    }

    @Test
    func malformedQuantResponseSurfacesAsDecodingError() async {
        let transport = RoutingHTTPTransport(stubsByPath: [
            "/quant/analyze": .raw(200, Data("not json".utf8)),
            "/price/AAPL": .raw(200, Self.priceJSON),
            "/chart/AAPL": .raw(200, Self.chartJSON),
        ])
        let service = AssetDetailService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchAssetDetail(symbol: "AAPL", assetType: "stock")
        }
    }

    @Test
    func requestBodySendsSymbolAndAssetType() async throws {
        let transport = Self.fullTransport()
        let service = AssetDetailService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        _ = try await service.fetchAssetDetail(symbol: "AAPL", assetType: "stock")

        let recorded = await transport.recordedRequests
        let quantRequest = try #require(recorded.first { $0.url?.path == "/quant/analyze" })
        let body = try #require(quantRequest.httpBody)
        let decoded = try JSONDecoder().decode([String: String].self, from: body)
        #expect(decoded["symbol"] == "AAPL")
        #expect(decoded["asset_type"] == "stock")
    }
}
