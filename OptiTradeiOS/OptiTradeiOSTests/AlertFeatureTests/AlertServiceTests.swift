import Foundation
import Testing
@testable import OptiTradeiOS

/// Verifies `AlertService` speaks the *real* backend contract
/// (`backend/watchlist/models.py` + `backend/main.py`'s `/alerts`
/// routes) using a mock transport — never the live backend.
struct AlertServiceTests {
    private static let alertsJSON = Data("""
    [
      {
        "id": 1, "owner": "trader@optitrade.app", "watchlist_id": null, "symbol": "AAPL",
        "portfolio_id": null, "category": "price", "alert_type": "price_above",
        "parameters": {"threshold": 200.0}, "cooldown_minutes": 60, "enabled": true,
        "last_state": {}, "last_checked_at": null, "last_triggered_at": null,
        "created_at": "2026-01-01T00:00:00Z"
      },
      {
        "id": 2, "owner": "trader@optitrade.app", "watchlist_id": null, "symbol": "TSLA",
        "portfolio_id": null, "category": "decision", "alert_type": "decision_buy",
        "parameters": {}, "cooldown_minutes": 30, "enabled": false,
        "last_state": {}, "last_checked_at": null, "last_triggered_at": null,
        "created_at": "2026-01-01T00:00:00Z"
      }
    ]
    """.utf8)

    private static let oneAlertJSON = Data("""
    {
      "id": 5, "owner": "trader@optitrade.app", "watchlist_id": null, "symbol": "AAPL",
      "portfolio_id": null, "category": "price", "alert_type": "price_above",
      "parameters": {"threshold": 210.0}, "cooldown_minutes": 60, "enabled": true,
      "last_state": {}, "last_checked_at": null, "last_triggered_at": null,
      "created_at": "2026-01-01T00:00:00Z"
    }
    """.utf8)

    @Test
    func fetchAlertsDecodesEveryRealField() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Self.alertsJSON)])
        let service = AlertService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let alerts = try await service.fetchAlerts()

        #expect(alerts.count == 2)
        #expect(alerts[0].id == 1)
        #expect(alerts[0].symbol == "AAPL")
        #expect(alerts[0].category == .price)
        #expect(alerts[0].alertType == .priceAbove)
        #expect(alerts[0].parameters["threshold"] == 200.0)
        #expect(alerts[0].cooldownMinutes == 60)
        #expect(alerts[0].enabled == true)
        #expect(alerts[1].category == .decision)
        #expect(alerts[1].alertType == .decisionBuy)
        #expect(alerts[1].enabled == false)

        let recorded = await transport.recordedRequests
        #expect(recorded[0].url?.path == "/alerts")
        #expect(recorded[0].httpMethod == "GET")
    }

    @Test
    func emptyAlertListDecodesToAnEmptyArray() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("[]".utf8))])
        let service = AlertService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let alerts = try await service.fetchAlerts()

        #expect(alerts.isEmpty)
    }

    @Test
    func createAlertPostsTheRealRequestShape() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Self.oneAlertJSON)])
        let service = AlertService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let alert = try await service.createAlert(category: .price, alertType: .priceAbove, symbol: "AAPL", parameters: ["threshold": 210], cooldownMinutes: 60)

        #expect(alert.id == 5)
        let recorded = await transport.recordedRequests
        #expect(recorded[0].url?.path == "/alerts")
        #expect(recorded[0].httpMethod == "POST")
        let body = try #require(recorded[0].httpBody)
        let decoded = try JSONSerialization.jsonObject(with: body) as? [String: Any]
        #expect(decoded?["category"] as? String == "price")
        #expect(decoded?["alert_type"] as? String == "price_above")
        #expect(decoded?["symbol"] as? String == "AAPL")
        #expect(decoded?["cooldown_minutes"] as? Int == 60)
        let parameters = decoded?["parameters"] as? [String: Double]
        #expect(parameters?["threshold"] == 210)
    }

    @Test
    func setEnabledSendsAPatchToTheEnabledEndpoint() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Self.oneAlertJSON)])
        let service = AlertService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        _ = try await service.setEnabled(false, alertID: 5)

        let recorded = await transport.recordedRequests
        #expect(recorded[0].url?.path == "/alerts/5/enabled")
        #expect(recorded[0].httpMethod == "PATCH")
        let body = try #require(recorded[0].httpBody)
        let decoded = try JSONSerialization.jsonObject(with: body) as? [String: Any]
        #expect(decoded?["enabled"] as? Bool == false)
    }

    @Test
    func deleteAlertSendsADeleteToTheAlertEndpoint() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("""
        {"status": "deleted"}
        """.utf8))])
        let service = AlertService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        try await service.deleteAlert(alertID: 5)

        let recorded = await transport.recordedRequests
        #expect(recorded[0].url?.path == "/alerts/5")
        #expect(recorded[0].httpMethod == "DELETE")
    }

    @Test
    func scanNowPostsToTheScanEndpointAndDecodesTheSummary() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("""
        {"started_at": "2026-01-01T00:00:00Z", "total_alerts": 3, "checked_count": 3, "triggered_count": 1, "outcomes": []}
        """.utf8))])
        let service = AlertService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let summary = try await service.scanNow()

        #expect(summary.totalAlerts == 3)
        #expect(summary.checkedCount == 3)
        #expect(summary.triggeredCount == 1)
        let recorded = await transport.recordedRequests
        #expect(recorded[0].url?.path == "/alerts/scan")
        #expect(recorded[0].httpMethod == "POST")
    }

    @Test
    func unauthorizedResponseSurfacesAsTypedError() async {
        let transport = MockHTTPTransport(stubs: [.json(401, ["detail": "Yetkilendirme tokeni eksik."])])
        let service = AlertService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchAlerts()
        }
    }

    @Test
    func serverFailureSurfacesAsTypedError() async {
        let transport = MockHTTPTransport(stubs: [.json(500, ["detail": "internal error"])])
        let service = AlertService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchAlerts()
        }
    }

    @Test
    func malformedResponseSurfacesAsDecodingError() async {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("not json".utf8))])
        let service = AlertService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.fetchAlerts()
        }
    }
}
