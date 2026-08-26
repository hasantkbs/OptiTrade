import Foundation
import Observation

/// Client-side authentication state. Owns no networking of its own — it only
/// reacts to what `TokenStore` holds, what `APIClient` reports back via
/// `handleSessionExpired()`, and coordinates with `TokenRefreshCoordinator`
/// so a logout can never be undone by a refresh that was already in flight.
///
/// `@unchecked Sendable`: every stored property is only ever touched on
/// `MainActor` (the class itself is `@MainActor`-isolated), so it's safe to
/// hand a reference to non-isolated `@Sendable` closures (e.g. the
/// `APIClient` refresh-failure callback) that immediately hop back via
/// `await`.
@MainActor
@Observable
final class SessionManager: @unchecked Sendable {
    enum State: Sendable, Equatable {
        case restoring
        case unauthenticated
        case authenticated
    }

    private(set) var state: State = .restoring

    private let tokenStore: TokenStore
    private let refreshCoordinator: TokenRefreshCoordinator
    private let logger: AppLogging

    /// Ensures concurrent callers of `restoreSession()` (e.g. app launch
    /// racing a second call) share one restoration instead of each reading
    /// the token store independently.
    private var restorationTask: Task<Void, Never>?

    init(tokenStore: TokenStore, refreshCoordinator: TokenRefreshCoordinator, logger: AppLogging) {
        self.tokenStore = tokenStore
        self.refreshCoordinator = refreshCoordinator
        self.logger = logger
    }

    /// Called once at launch. Does not validate the token against the
    /// backend — it only checks whether one is present locally. If it turns
    /// out to be expired, the first authenticated request's normal 401 →
    /// refresh path (already handled by `APIClient`/`TokenRefreshCoordinator`)
    /// takes care of it without any extra logic here.
    func restoreSession() async {
        if let restorationTask {
            return await restorationTask.value
        }
        let task = Task {
            await self.performRestoration()
        }
        restorationTask = task
        await task.value
        restorationTask = nil
    }

    private func performRestoration() async {
        state = .restoring
        if await tokenStore.accessToken() != nil {
            state = .authenticated
            logger.info("Session restored from stored credentials.", category: .session)
        } else {
            state = .unauthenticated
            logger.info("No stored session found.", category: .session)
        }
    }

    func establishSession(with tokens: AuthTokens) async throws {
        try await tokenStore.save(tokens)
        state = .authenticated
        logger.info("Session established.", category: .session)
    }

    func endSession() async {
        await refreshCoordinator.invalidate()
        try? await tokenStore.clear()
        state = .unauthenticated
        logger.info("Session ended.", category: .session)
    }

    /// Invoked by `APIClient` when a coordinated token refresh fails.
    func handleSessionExpired() async {
        logger.warning("Session expired; clearing credentials.", category: .session)
        await endSession()
    }
}
