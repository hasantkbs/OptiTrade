import Foundation

/// Networking for Alert management. Talks to the *real* backend contract
/// (`backend/watchlist/models.py` + `backend/main.py`'s `/alerts`
/// routes):
///   - `GET /alerts`                 -> [AlertRule]
///   - `POST /alerts`                -> AlertRule
///   - `PATCH /alerts/{id}/enabled`  -> AlertRule
///   - `DELETE /alerts/{id}`
///   - `POST /alerts/scan`           -> ScanReport (on-demand scan of
///                                      just the caller's own alerts)
///
/// All already work with the existing `APIClient`'s Bearer-token
/// injection and 401->refresh handling from Step 1/2 — nothing new was
/// needed there. There is no push-notification backend to integrate
/// (see the Step 8 final report).
protocol AlertServicing: Sendable {
    /// Every alert the user owns, across all symbols/categories —
    /// `GET /alerts` with no `watchlist_id` filter.
    func fetchAlerts() async throws -> [AlertRule]

    func createAlert(
        category: AlertCategoryDTO,
        alertType: AlertTypeDTO,
        symbol: String?,
        parameters: [String: Double],
        cooldownMinutes: Int
    ) async throws -> AlertRule

    func setEnabled(_ enabled: Bool, alertID: Int) async throws -> AlertRule
    func deleteAlert(alertID: Int) async throws
    func scanNow() async throws -> AlertScanSummary
}

struct AlertService: AlertServicing {
    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func fetchAlerts() async throws -> [AlertRule] {
        let dtos = try await apiClient.send(APIRequest<[AlertDTO]>(path: "alerts"))
        return dtos.compactMap(AlertRule.init(dto:))
    }

    func createAlert(
        category: AlertCategoryDTO,
        alertType: AlertTypeDTO,
        symbol: String?,
        parameters: [String: Double],
        cooldownMinutes: Int
    ) async throws -> AlertRule {
        let body = CreateAlertRequestDTO(
            category: category,
            alertType: alertType,
            parameters: parameters,
            watchlistId: nil,
            symbol: symbol,
            portfolioId: nil,
            cooldownMinutes: cooldownMinutes
        )
        let request = try APIRequest<AlertDTO>(path: "alerts", method: .post, body: body)
        let dto = try await apiClient.send(request)
        guard let alert = AlertRule(dto: dto) else {
            throw APIClientError.decoding("Created alert did not include an id.")
        }
        return alert
    }

    func setEnabled(_ enabled: Bool, alertID: Int) async throws -> AlertRule {
        let request = try APIRequest<AlertDTO>(
            path: "alerts/\(alertID)/enabled",
            method: .patch,
            body: SetAlertEnabledRequestDTO(enabled: enabled)
        )
        let dto = try await apiClient.send(request)
        guard let alert = AlertRule(dto: dto) else {
            throw APIClientError.decoding("Updated alert did not include an id.")
        }
        return alert
    }

    func deleteAlert(alertID: Int) async throws {
        let request = APIRequest<EmptyResponse>(path: "alerts/\(alertID)", method: .delete)
        _ = try await apiClient.send(request)
    }

    func scanNow() async throws -> AlertScanSummary {
        let dto = try await apiClient.send(APIRequest<ScanReportDTO>(path: "alerts/scan", method: .post))
        return AlertScanSummary(dto: dto)
    }
}
