import Foundation

/// Networking for the auth feature. Talks to the *real* backend contract:
///   - `POST /auth/login`  {email, password}       -> TokenPairResponse
///   - `POST /auth/logout` {refresh_token}          -> {"status": "ok"}
///   - `GET  /users/me`    (Bearer access token)    -> UserResponse
///
/// Deliberately thin: it only shapes requests/responses. Session state
/// (`SessionManager`) and token persistence (`TokenStore`) stay exactly
/// where Step 1 put them — this type never touches either directly.
protocol Authenticating: Sendable {
    func login(email: String, password: String) async throws -> AuthTokens
    func logout(refreshToken: String) async throws
    func currentUser() async throws -> CurrentUser
}

struct AuthenticationService: Authenticating {
    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func login(email: String, password: String) async throws -> AuthTokens {
        let request = try APIRequest<TokenPairDTO>(
            path: "auth/login",
            method: .post,
            body: LoginRequestBody(email: email, password: password),
            requiresAuth: false
        )
        return try await apiClient.send(request).tokens
    }

    /// Best-effort revocation. Callers must clear local credentials
    /// regardless of whether this throws — the backend's `/auth/logout` is
    /// idempotent and never fails on an already-invalid token, but the
    /// network call itself can still fail (offline, timeout, etc.).
    func logout(refreshToken: String) async throws {
        let request = try APIRequest<EmptyResponse>(
            path: "auth/logout",
            method: .post,
            body: RefreshRequestDTO(refreshToken: refreshToken),
            requiresAuth: false
        )
        _ = try await apiClient.send(request)
    }

    func currentUser() async throws -> CurrentUser {
        let request = APIRequest<CurrentUserDTO>(path: "users/me", method: .get)
        return try await apiClient.send(request).user
    }
}
