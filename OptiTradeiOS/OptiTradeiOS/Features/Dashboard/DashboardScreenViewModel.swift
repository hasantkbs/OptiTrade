import Foundation
import Observation

/// Owns only the Portfolio section's state — Watchlist/Quant-
/// Opportunities/AI-Analyst are rendered directly from the shared
/// `WatchlistScreenViewModel` the Dashboard is handed (see
/// `DashboardScreenView`), which already owns its own independent
/// idle/loading/loaded/empty/failed lifecycle. Keeping these as two
/// separate view models (rather than one that tries to track both) is
/// exactly what makes "Portfolio succeeds, Watchlist fails" a
/// non-event: each section's `.task` is independent, so one section's
/// failure can never affect the other's rendering.
@MainActor
@Observable
final class DashboardScreenViewModel {
    enum PortfolioSectionState: Sendable, Equatable {
        case idle
        case loading
        case loaded(PortfolioSummary)
        case empty
        case failed(String)
    }

    private(set) var portfolioState: PortfolioSectionState = .idle
    private(set) var isRefreshing = false

    /// Set only when a *refresh* fails while good data is already on
    /// screen — same pattern as `PortfolioViewModel.refreshError`.
    private(set) var portfolioRefreshError: String?

    private let service: DashboardServicing
    private let logger: AppLogging

    init(service: DashboardServicing, logger: AppLogging) {
        self.service = service
        self.logger = logger
    }

    func loadIfNeeded() async {
        guard case .idle = portfolioState else { return }
        portfolioState = .loading
        do {
            portfolioState = try await fetchPortfolioState()
        } catch {
            portfolioState = .failed(AuthPresentableError.message(for: error))
            logger.warning("Dashboard portfolio load failed.", category: .dashboard)
        }
    }

    func refresh() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        portfolioRefreshError = nil

        do {
            portfolioState = try await fetchPortfolioState()
        } catch {
            let message = AuthPresentableError.message(for: error)
            logger.warning("Dashboard portfolio refresh failed.", category: .dashboard)
            if case .loaded = portfolioState {
                portfolioRefreshError = message
            } else {
                portfolioState = .failed(message)
            }
        }
    }

    private func fetchPortfolioState() async throws -> PortfolioSectionState {
        if let summary = try await service.fetchPortfolioSummary() {
            return .loaded(summary)
        }
        return .empty
    }
}
