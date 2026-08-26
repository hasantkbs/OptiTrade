import Foundation
import Observation

@MainActor
@Observable
final class PortfolioViewModel {
    enum State: Sendable, Equatable {
        case idle
        case loading
        case loaded(PortfolioSummary)
        case empty
        case failed(String)
    }

    private(set) var state: State = .idle
    private(set) var isRefreshing = false

    /// Set only when a *refresh* (not the initial load) fails while good
    /// data is already on screen — the existing `PortfolioSummary` in
    /// `.loaded` is deliberately left in place rather than being replaced
    /// by `.failed`, so a flaky network blip doesn't blank out real numbers
    /// the user was already looking at.
    private(set) var refreshError: String?

    private let portfolioService: PortfolioServicing
    private let logger: AppLogging

    init(portfolioService: PortfolioServicing, logger: AppLogging) {
        self.portfolioService = portfolioService
        self.logger = logger
    }

    /// Called from the view's `.task` — safe to call on every appearance
    /// since it's a no-op once loading has started, avoiding a request
    /// storm if the view re-appears.
    func loadIfNeeded() async {
        guard case .idle = state else { return }
        state = .loading
        do {
            state = try await fetchState()
        } catch {
            state = .failed(AuthPresentableError.message(for: error))
            logger.warning("Initial portfolio load failed.", category: .portfolio)
        }
    }

    /// Pull-to-refresh. Guarded against overlapping refreshes the same way
    /// `LoginViewModel.login()`/`AuthenticatedAppShellViewModel.logout()`
    /// guard against duplicate submissions.
    func refresh() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        refreshError = nil

        do {
            state = try await fetchState()
        } catch {
            let message = AuthPresentableError.message(for: error)
            logger.warning("Portfolio refresh failed.", category: .portfolio)
            if case .loaded = state {
                refreshError = message
            } else {
                state = .failed(message)
            }
        }
    }

    private func fetchState() async throws -> State {
        if let summary = try await portfolioService.fetchPrimaryPortfolio() {
            return .loaded(summary)
        }
        return .empty
    }
}
