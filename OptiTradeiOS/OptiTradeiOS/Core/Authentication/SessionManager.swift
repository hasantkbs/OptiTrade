import Foundation
import Observation

/// Client-side authentication state. Owns no networking — it only reacts to
/// what `TokenStore` holds and what `APIClient` reports back via
/// `handleSessionExpired()`.
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
    private let logger: AppLogging

    init(tokenStore: TokenStore, logger: AppLogging) {
        self.tokenStore = tokenStore
        self.logger = logger
    }

    /// Called once at launch. Does not validate the token against the
    /// backend — it only checks whether one is present locally.
    func restoreSession() async {
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
