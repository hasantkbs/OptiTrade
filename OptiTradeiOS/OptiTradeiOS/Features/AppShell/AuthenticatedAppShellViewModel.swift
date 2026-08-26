import Foundation
import Observation

@MainActor
@Observable
final class AuthenticatedAppShellViewModel {
    private(set) var currentUser: CurrentUser?
    private(set) var isLoadingUser = false
    private(set) var userLoadError: String?
    private(set) var isLoggingOut = false

    private let authenticationService: Authenticating
    private let sessionManager: SessionManager
    private let tokenStore: TokenStore
    private let logger: AppLogging

    init(
        authenticationService: Authenticating,
        sessionManager: SessionManager,
        tokenStore: TokenStore,
        logger: AppLogging
    ) {
        self.authenticationService = authenticationService
        self.sessionManager = sessionManager
        self.tokenStore = tokenStore
        self.logger = logger
    }

    func loadCurrentUserIfNeeded() async {
        guard currentUser == nil, !isLoadingUser else { return }
        isLoadingUser = true
        defer { isLoadingUser = false }

        do {
            currentUser = try await authenticationService.currentUser()
        } catch {
            userLoadError = AuthPresentableError.message(for: error)
            logger.warning("Failed to load current user.", category: .authentication)
        }
    }

    /// Guarded by `isLoggingOut` for the same reason `LoginViewModel.login()`
    /// guards on `isLoading` — a repeated tap must not fire a second
    /// revocation request.
    ///
    /// Local credentials are cleared unconditionally: if the backend call
    /// fails (offline, timeout, server error), the user is still logged out
    /// on this device.
    func logout() async {
        guard !isLoggingOut else { return }
        isLoggingOut = true
        defer { isLoggingOut = false }

        if let refreshToken = await tokenStore.refreshToken() {
            do {
                try await authenticationService.logout(refreshToken: refreshToken)
            } catch {
                logger.warning("Logout network call failed; clearing local session anyway.", category: .authentication)
            }
        }
        await sessionManager.endSession()
    }
}
