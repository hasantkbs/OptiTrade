import Foundation
import Observation

@MainActor
@Observable
final class AssetDetailViewModel {
    enum State: Sendable, Equatable {
        case idle
        case loading
        case loaded(AssetDetailSummary)
        case failed(String)
    }

    private(set) var state: State = .idle
    private(set) var isRefreshing = false

    /// Set only when a *refresh* fails while good data is already on
    /// screen — same pattern as `PortfolioViewModel.refreshError`.
    private(set) var refreshError: String?

    /// The symbol currently loaded/loading. `nil` before the first
    /// `load(symbol:)` call.
    private(set) var symbol: String?

    private let service: AssetDetailServicing
    private let logger: AppLogging
    private var loadTask: Task<Void, Never>?

    init(service: AssetDetailServicing, logger: AppLogging) {
        self.service = service
        self.logger = logger
    }

    /// Loads `symbol`'s Quant analysis. A call for a *different* symbol
    /// than the one currently loaded/loading cancels the in-flight
    /// request first and immediately resets to `.loading` for the new
    /// symbol — so a slow response for a symbol the user has already
    /// navigated away from can never populate this screen (Section 17).
    /// A call for the *same* symbol while already loaded/loading is a
    /// no-op, matching `PortfolioViewModel.loadIfNeeded()`'s
    /// re-appearance guard.
    func load(symbol: String, assetType: String) {
        if self.symbol == symbol {
            switch state {
            case .loading, .loaded: return
            case .idle, .failed: break
            }
        }

        loadTask?.cancel()
        self.symbol = symbol
        state = .loading

        loadTask = Task { [weak self, service, logger] in
            do {
                let summary = try await service.fetchAssetDetail(symbol: symbol, assetType: assetType)
                guard !Task.isCancelled, let self, self.symbol == symbol else { return }
                self.state = .loaded(summary)
            } catch {
                guard !Task.isCancelled, let self, self.symbol == symbol else { return }
                self.state = .failed(AuthPresentableError.message(for: error))
                logger.warning("Asset detail load failed.", category: .assets)
            }
        }
    }

    func refresh(assetType: String) async {
        guard !isRefreshing, let symbol else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        refreshError = nil

        do {
            let summary = try await service.fetchAssetDetail(symbol: symbol, assetType: assetType)
            guard self.symbol == symbol else { return } // switched away mid-refresh
            state = .loaded(summary)
        } catch {
            guard self.symbol == symbol else { return }
            let message = AuthPresentableError.message(for: error)
            logger.warning("Asset detail refresh failed.", category: .assets)
            if case .loaded = state {
                refreshError = message
            } else {
                state = .failed(message)
            }
        }
    }
}
