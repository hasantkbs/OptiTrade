import Foundation
import Observation

@MainActor
@Observable
final class AssetSearchViewModel {
    enum State: Sendable, Equatable {
        case idle
        case loading
        case loaded([AssetSearchResult])
        case empty
        case failed(String)
    }

    private(set) var state: State = .idle

    /// Bound to the search field via a manual `Binding` in `WatchlistView`
    /// (an `@Observable` class's properties are tracked regardless of the
    /// property wrapper the *caller* holds it with — no `@Bindable` needed
    /// here). Every write reschedules the debounced search.
    var query: String = "" {
        didSet {
            guard oldValue != query else { return }
            scheduleSearch()
        }
    }

    private let market: String
    private let service: AssetSearchServicing
    private let logger: AppLogging
    private let debounceNanoseconds: UInt64
    private var searchTask: Task<Void, Never>?

    init(
        market: String,
        service: AssetSearchServicing,
        logger: AppLogging,
        debounceNanoseconds: UInt64 = 300_000_000
    ) {
        self.market = market
        self.service = service
        self.logger = logger
        self.debounceNanoseconds = debounceNanoseconds
    }

    /// Resets search back to its initial, un-searched state (e.g. when the
    /// search field is cleared or dismissed).
    func clear() {
        searchTask?.cancel()
        searchTask = nil
        query = ""
        state = .idle
    }

    /// Cancels any in-flight search before starting a new one, so a fast
    /// typist (A -> AP -> AAP -> AAPL) can never have an earlier keystroke's
    /// stale result overwrite a later one.
    private func scheduleSearch() {
        searchTask?.cancel()

        let currentQuery = query
        guard !currentQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            state = .idle
            return
        }

        state = .loading
        searchTask = Task { [weak self, debounceNanoseconds] in
            if debounceNanoseconds > 0 {
                try? await Task.sleep(nanoseconds: debounceNanoseconds)
            }
            guard !Task.isCancelled else { return }
            await self?.performSearch(currentQuery)
        }
    }

    private func performSearch(_ query: String) async {
        guard !Task.isCancelled else { return }
        do {
            let results = try await service.search(query: query, market: market)
            guard !Task.isCancelled else { return }
            state = results.isEmpty ? .empty : .loaded(results)
        } catch is CancellationError {
            // A newer search superseded this one — leave state to whatever
            // that newer search produces; don't surface a spurious error.
        } catch {
            guard !Task.isCancelled else { return }
            state = .failed(AuthPresentableError.message(for: error))
            logger.warning("Asset search failed.", category: .assets)
        }
    }
}
