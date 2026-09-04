import Foundation
import Observation

@MainActor
@Observable
final class AIAnalystViewModel {
    enum State: Sendable, Equatable {
        case idle
        case loading
        case loaded(AIAnalystExplanation)
        /// The backend produced no explanation text — see
        /// `AIAnalystServicing.fetchExplanation`'s doc comment.
        case empty
        case failed(String)
    }

    private(set) var state: State = .idle
    private(set) var symbol: String?

    private let service: AIAnalystServicing
    private let logger: AppLogging
    private var loadTask: Task<Void, Never>?

    init(service: AIAnalystServicing, logger: AppLogging) {
        self.service = service
        self.logger = logger
    }

    /// Loads `symbol`'s explanation. Same guard shape as
    /// `AssetDetailViewModel.load(symbol:)`: a call for a *different*
    /// symbol cancels the in-flight request and immediately resets to
    /// `.loading`, and the `self.symbol == symbol` check at completion
    /// means a slow response for a symbol the user has navigated away
    /// from can never populate this screen (Section 14). A call for the
    /// *same* symbol while already loaded/loading is a no-op — also
    /// doubles as duplicate-submission protection, since this screen's
    /// one "request" is the initial load.
    func load(symbol: String, assetType: String) {
        if self.symbol == symbol {
            switch state {
            case .loading, .loaded, .empty: return
            case .idle, .failed: break
            }
        }

        loadTask?.cancel()
        self.symbol = symbol
        state = .loading

        loadTask = Task { [weak self, service, logger] in
            do {
                let explanation = try await service.fetchExplanation(symbol: symbol, assetType: assetType)
                guard !Task.isCancelled, let self, self.symbol == symbol else { return }
                self.state = explanation.map(State.loaded) ?? .empty
            } catch {
                guard !Task.isCancelled, let self, self.symbol == symbol else { return }
                self.state = .failed(AuthPresentableError.message(for: error))
                logger.warning("AI Analyst explanation load failed.", category: .aiAnalyst)
            }
        }
    }

    /// Cancels any in-flight request — called when the user leaves the
    /// screen (Section 14).
    func cancel() {
        loadTask?.cancel()
    }
}
