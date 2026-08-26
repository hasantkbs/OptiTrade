import Foundation
@testable import OptiTradeiOS

/// Configurable `Authenticating` fake — no network, no `APIClient`. Records
/// call counts so tests can assert "only one request" guarantees.
actor StubAuthenticationService: Authenticating {
    private(set) var loginCallCount = 0
    private(set) var logoutCallCount = 0
    private(set) var currentUserCallCount = 0

    var loginResult: Result<AuthTokens, Error>
    var logoutResult: Result<Void, Error>
    var currentUserResult: Result<CurrentUser, Error>

    /// Optional artificial delay so concurrent callers in tests genuinely
    /// overlap instead of a single-threaded runner serializing them by luck.
    var delayNanoseconds: UInt64

    init(
        loginResult: Result<AuthTokens, Error> = .failure(APIClientError.unauthorized(nil)),
        logoutResult: Result<Void, Error> = .success(()),
        currentUserResult: Result<CurrentUser, Error> = .failure(APIClientError.unauthorized(nil)),
        delayNanoseconds: UInt64 = 0
    ) {
        self.loginResult = loginResult
        self.logoutResult = logoutResult
        self.currentUserResult = currentUserResult
        self.delayNanoseconds = delayNanoseconds
    }

    func login(email: String, password: String) async throws -> AuthTokens {
        loginCallCount += 1
        if delayNanoseconds > 0 { try? await Task.sleep(nanoseconds: delayNanoseconds) }
        return try loginResult.get()
    }

    func logout(refreshToken: String) async throws {
        logoutCallCount += 1
        if delayNanoseconds > 0 { try? await Task.sleep(nanoseconds: delayNanoseconds) }
        try logoutResult.get()
    }

    func currentUser() async throws -> CurrentUser {
        currentUserCallCount += 1
        if delayNanoseconds > 0 { try? await Task.sleep(nanoseconds: delayNanoseconds) }
        return try currentUserResult.get()
    }
}
