import Foundation
import Testing
@testable import OptiTradeiOS

/// Verifies `AuthenticationService` speaks the *real* backend contract
/// (`backend/main.py` + `backend/users/schemas.py`) — exact paths, methods,
/// and JSON field names — using a mock transport, never the live backend.
struct AuthenticationServiceTests {
    @Test
    func loginPostsToAuthLoginWithEmailAndPasswordAndNoAuthHeader() async throws {
        let tokenJSON = Data("""
        {"access_token": "a", "refresh_token": "r", "token_type": "bearer", "expires_in": 3600}
        """.utf8)
        let transport = MockHTTPTransport(stubs: [.raw(200, tokenJSON)])
        let service = AuthenticationService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        let tokens = try await service.login(email: "trader@optitrade.app", password: "s3cret")

        #expect(tokens == AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let recorded = try #require(await transport.recordedRequests.first)
        #expect(recorded.url?.path == "/auth/login")
        #expect(recorded.httpMethod == "POST")
        #expect(recorded.value(forHTTPHeaderField: "Authorization") == nil)
        let body = try #require(recorded.httpBody)
        let object = try JSONSerialization.jsonObject(with: body) as? [String: String]
        #expect(object == ["email": "trader@optitrade.app", "password": "s3cret"])
    }

    @Test
    func loginSurfacesUnauthorizedOnInvalidCredentials() async {
        let transport = MockHTTPTransport(stubs: [.json(401, ["detail": "Invalid email or password."])])
        let service = AuthenticationService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        await #expect(throws: APIClientError.self) {
            _ = try await service.login(email: "trader@optitrade.app", password: "wrong")
        }
    }

    @Test
    func logoutPostsRefreshTokenToAuthLogout() async throws {
        let transport = MockHTTPTransport(stubs: [.json(200, ["status": "ok"])])
        let service = AuthenticationService(apiClient: makeClient(transport: transport, tokenStore: InMemoryTokenStore()))

        try await service.logout(refreshToken: "r-1")

        let recorded = try #require(await transport.recordedRequests.first)
        #expect(recorded.url?.path == "/auth/logout")
        #expect(recorded.httpMethod == "POST")
        let body = try #require(recorded.httpBody)
        let object = try JSONSerialization.jsonObject(with: body) as? [String: String]
        #expect(object == ["refresh_token": "r-1"])
    }

    @Test
    func currentUserGetsUsersMeWithBearerTokenAndDecodesDisplayName() async throws {
        let userJSON = Data("""
        {"id": 42, "email": "trader@optitrade.app", "display_name": "Trader", "is_email_verified": true, "is_active": true, "created_at": "2026-01-01T00:00:00Z"}
        """.utf8)
        let transport = MockHTTPTransport(stubs: [.raw(200, userJSON)])
        let tokenStore = InMemoryTokenStore(tokens: AuthTokens(accessToken: "abc", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let service = AuthenticationService(apiClient: makeClient(transport: transport, tokenStore: tokenStore))

        let user = try await service.currentUser()

        #expect(user == CurrentUser(id: 42, email: "trader@optitrade.app", displayName: "Trader"))
        let recorded = try #require(await transport.recordedRequests.first)
        #expect(recorded.url?.path == "/users/me")
        #expect(recorded.value(forHTTPHeaderField: "Authorization") == "Bearer abc")
    }
}
