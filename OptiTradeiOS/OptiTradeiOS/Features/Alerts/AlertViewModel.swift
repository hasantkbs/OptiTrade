import Foundation
import Observation

@MainActor
@Observable
final class AlertViewModel {
    enum State: Sendable, Equatable {
        case idle
        case loading
        case loaded([AlertRule])
        case empty
        case failed(String)
    }

    private(set) var state: State = .idle
    private(set) var isRefreshing = false

    /// Set only when a *refresh* fails while good data is already on
    /// screen — same pattern as `PortfolioViewModel.refreshError`.
    private(set) var refreshError: String?

    /// Alert ids with an enable/disable/delete request currently in
    /// flight — guards against duplicate requests and races on the same
    /// alert, same pattern as `WatchlistScreenViewModel.pendingSymbols`.
    private(set) var pendingAlertIDs: Set<Int> = []
    private(set) var mutationError: String?

    private(set) var isCreating = false
    private(set) var createError: String?

    private(set) var isScanning = false
    private(set) var scanError: String?
    private(set) var lastScanSummary: AlertScanSummary?

    private let service: AlertServicing
    private let logger: AppLogging

    init(service: AlertServicing, logger: AppLogging) {
        self.service = service
        self.logger = logger
    }

    func loadIfNeeded() async {
        guard case .idle = state else { return }
        state = .loading
        do {
            state = try await fetchState()
        } catch {
            state = .failed(AuthPresentableError.message(for: error))
            logger.warning("Alert list load failed.", category: .alerts)
        }
    }

    func refresh() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        refreshError = nil

        do {
            state = try await fetchState()
        } catch {
            let message = AuthPresentableError.message(for: error)
            logger.warning("Alert list refresh failed.", category: .alerts)
            if case .loaded = state {
                refreshError = message
            } else {
                state = .failed(message)
            }
        }
    }

    /// Creates an alert and reloads the list from the backend afterwards
    /// — the backend remains authoritative, this never inserts the new
    /// alert into `state` optimistically.
    @discardableResult
    func createAlert(
        category: AlertCategoryDTO,
        alertType: AlertTypeDTO,
        symbol: String?,
        parameters: [String: Double],
        cooldownMinutes: Int
    ) async -> Bool {
        guard !isCreating else { return false }
        isCreating = true
        defer { isCreating = false }
        createError = nil

        do {
            _ = try await service.createAlert(
                category: category, alertType: alertType, symbol: symbol,
                parameters: parameters, cooldownMinutes: cooldownMinutes
            )
            state = try await fetchState()
            return true
        } catch {
            createError = AuthPresentableError.message(for: error)
            logger.warning("Alert creation failed.", category: .alerts)
            return false
        }
    }

    func setEnabled(_ enabled: Bool, alertID: Int) async {
        guard !pendingAlertIDs.contains(alertID) else { return }
        pendingAlertIDs.insert(alertID)
        defer { pendingAlertIDs.remove(alertID) }
        mutationError = nil

        do {
            _ = try await service.setEnabled(enabled, alertID: alertID)
            state = try await fetchState()
        } catch {
            mutationError = AuthPresentableError.message(for: error)
            logger.warning("Setting alert enabled state failed.", category: .alerts)
        }
    }

    func deleteAlert(alertID: Int) async {
        guard !pendingAlertIDs.contains(alertID) else { return }
        pendingAlertIDs.insert(alertID)
        defer { pendingAlertIDs.remove(alertID) }
        mutationError = nil

        do {
            try await service.deleteAlert(alertID: alertID)
            state = try await fetchState()
        } catch {
            mutationError = AuthPresentableError.message(for: error)
            logger.warning("Deleting an alert failed.", category: .alerts)
        }
    }

    func scanNow() async {
        guard !isScanning else { return }
        isScanning = true
        defer { isScanning = false }
        scanError = nil

        do {
            lastScanSummary = try await service.scanNow()
        } catch {
            scanError = AuthPresentableError.message(for: error)
            logger.warning("On-demand alert scan failed.", category: .alerts)
        }
    }

    private func fetchState() async throws -> State {
        let alerts = try await service.fetchAlerts()
        return alerts.isEmpty ? .empty : .loaded(alerts)
    }
}
