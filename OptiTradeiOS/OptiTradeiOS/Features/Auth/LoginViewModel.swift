import Foundation
import Observation

@MainActor
@Observable
final class LoginViewModel {
    enum FieldValidationError: Sendable, Equatable {
        case emptyEmail
        case emptyPassword
    }

    var email: String = ""
    var password: String = ""
    private(set) var isLoading = false
    private(set) var validationError: FieldValidationError?
    private(set) var authError: String?

    var isLoginButtonDisabled: Bool { isLoading }

    private let authenticationService: Authenticating
    private let sessionManager: SessionManager
    private let logger: AppLogging

    init(authenticationService: Authenticating, sessionManager: SessionManager, logger: AppLogging) {
        self.authenticationService = authenticationService
        self.sessionManager = sessionManager
        self.logger = logger
    }

    /// Guarded by `isLoading` so repeated taps (or a fast double-tap) only
    /// ever produce one network request — the check-and-set happens
    /// synchronously before the first `await`, so two calls made
    /// "concurrently" on this `@MainActor` type can't both pass the guard.
    func login() async {
        guard !isLoading else { return }
        authError = nil
        guard validate() else { return }

        isLoading = true
        defer { isLoading = false }

        do {
            let tokens = try await authenticationService.login(email: email, password: password)
            try await sessionManager.establishSession(with: tokens)
            logger.info("Login succeeded.", category: .authentication)
        } catch {
            authError = AuthPresentableError.message(for: error)
            logger.warning("Login failed.", category: .authentication)
        }
    }

    private func validate() -> Bool {
        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedEmail.isEmpty else {
            validationError = .emptyEmail
            return false
        }
        guard !password.isEmpty else {
            validationError = .emptyPassword
            return false
        }
        validationError = nil
        return true
    }
}
