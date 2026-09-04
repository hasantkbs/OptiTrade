import Foundation
import Observation

@MainActor
@Observable
final class WatchlistScreenViewModel {
    enum State: Sendable, Equatable {
        case idle
        case loading
        case loaded(WatchlistSummary)
        /// No watchlist exists for this user yet — a real state (mirrors
        /// `PortfolioViewModel.State.empty`), not an error. A watchlist
        /// that exists but has zero items is still `.loaded`, rendered
        /// with an inline "no items yet" message — same split Step 3 made
        /// between "no portfolio" (`.empty`) and "portfolio with no
        /// positions" (inline, inside `.loaded`).
        case empty
        case failed(String)
    }

    private(set) var state: State = .idle
    private(set) var isRefreshing = false

    /// Set only when a *refresh* fails while good data is already on
    /// screen — same pattern as `PortfolioViewModel.refreshError`.
    private(set) var refreshError: String?

    /// Set when an add/remove mutation fails. Cleared at the start of the
    /// next mutation attempt.
    private(set) var mutationError: String?

    /// Symbols with an add/remove request currently in flight. Guards
    /// against duplicate add/delete requests and against an add and a
    /// remove for the same symbol racing each other — a second mutation
    /// for a pending symbol is a no-op until the first completes.
    private(set) var pendingSymbols: Set<String> = []

    private let watchlistService: WatchlistServicing
    private let logger: AppLogging

    init(watchlistService: WatchlistServicing, logger: AppLogging) {
        self.watchlistService = watchlistService
        self.logger = logger
    }

    func loadIfNeeded() async {
        guard case .idle = state else { return }
        state = .loading
        do {
            state = try await fetchState()
        } catch {
            state = .failed(AuthPresentableError.message(for: error))
            logger.warning("Initial watchlist load failed.", category: .watchlist)
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
            logger.warning("Watchlist refresh failed.", category: .watchlist)
            if case .loaded = state {
                refreshError = message
            } else {
                state = .failed(message)
            }
        }
    }

    func isInWatchlist(_ symbol: String) -> Bool {
        guard case .loaded(let summary) = state else { return false }
        let target = symbol.uppercased()
        return summary.items.contains { $0.symbol == target }
    }

    /// Adds `symbol` to the user's primary watchlist, creating one first if
    /// they don't have one yet. Reloads the full summary from the backend
    /// afterwards — the backend remains authoritative, this never edits
    /// `state` optimistically.
    func add(symbol: String) async {
        let symbol = symbol.uppercased()
        guard !pendingSymbols.contains(symbol) else { return }
        pendingSymbols.insert(symbol)
        defer { pendingSymbols.remove(symbol) }
        mutationError = nil

        do {
            let watchlistID = try await resolveWatchlistID()
            _ = try await watchlistService.addSymbol(symbol, toWatchlist: watchlistID)
            state = try await fetchState()
        } catch {
            mutationError = AuthPresentableError.message(for: error)
            logger.warning("Adding a symbol to the watchlist failed.", category: .watchlist)
        }
    }

    /// Removes `symbol` from the user's primary watchlist. A no-op if there
    /// is no loaded watchlist to remove from.
    func remove(symbol: String) async {
        let symbol = symbol.uppercased()
        guard !pendingSymbols.contains(symbol) else { return }
        guard case .loaded(let summary) = state else { return }
        pendingSymbols.insert(symbol)
        defer { pendingSymbols.remove(symbol) }
        mutationError = nil

        do {
            try await watchlistService.removeSymbol(symbol, fromWatchlist: summary.watchlistID)
            state = try await fetchState()
        } catch {
            mutationError = AuthPresentableError.message(for: error)
            logger.warning("Removing a symbol from the watchlist failed.", category: .watchlist)
        }
    }

    private func resolveWatchlistID() async throws -> Int {
        if case .loaded(let summary) = state {
            return summary.watchlistID
        }
        return try await watchlistService.createWatchlist(name: "My Watchlist")
    }

    private func fetchState() async throws -> State {
        if let summary = try await watchlistService.fetchPrimaryWatchlist() {
            return .loaded(summary)
        }
        return .empty
    }
}
