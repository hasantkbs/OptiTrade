import Foundation
import Testing
@testable import OptiTradeiOS

/// End-to-end (mock-transport) proof of the "expired access token, valid
/// refresh token" restoration path: `SessionManager.restoreSession()` is
/// optimistic (only checks a token is *present*), and the real refresh
/// happens transparently the first time an authenticated call — here,
/// `AuthenticatedAppShellViewModel.loadCurrentUserIfNeeded()` — hits a 401.
/// No second refresh mechanism is introduced; this exercises the exact
/// `APIClient` → `TokenRefreshCoordinator` path from Step 1.
struct SessionRestorationIntegrationTests {
    private actor ExpiredAccessTokenTransport: HTTPTransport {
        private(set) var usersMeAttempts = 0

        func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
            if request.url?.path == "/auth/refresh" {
                let dto = TokenPairDTO(accessToken: "fresh-access", refreshToken: "fresh-refresh", tokenType: "bearer", expiresIn: 3600)
                let data = try APICoding.encoder.encode(dto)
                return (data, HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!)
            }

            precondition(request.url?.path == "/users/me")
            usersMeAttempts += 1
            if usersMeAttempts == 1 {
                let errorBody = try APICoding.encoder.encode(["detail": "Token expired."])
                return (errorBody, HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: nil)!)
            }
            let userJSON = Data("""
            {"id": 7, "email": "trader@optitrade.app", "display_name": "Trader"}
            """.utf8)
            return (userJSON, HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!)
        }
    }

    @Test
    @MainActor
    func expiredAccessTokenIsTransparentlyRefreshedWhenLoadingCurrentUserAfterRestoration() async throws {
        let tokenStore = InMemoryTokenStore(tokens: AuthTokens(accessToken: "stale-access", refreshToken: "stale-refresh", tokenType: "bearer", expiresIn: 3600))
        let transport = ExpiredAccessTokenTransport()
        let apiClient = makeClient(transport: transport, tokenStore: tokenStore)
        let authenticationService = AuthenticationService(apiClient: apiClient)
        let sessionManager = makeSessionManager(tokenStore: tokenStore)

        await sessionManager.restoreSession()
        #expect(sessionManager.state == .authenticated) // optimistic: a token was present

        let shellViewModel = AuthenticatedAppShellViewModel(
            authenticationService: authenticationService,
            sessionManager: sessionManager,
            tokenStore: tokenStore,
            logger: TestLogger()
        )
        await shellViewModel.loadCurrentUserIfNeeded()

        #expect(shellViewModel.currentUser == CurrentUser(id: 7, email: "trader@optitrade.app", displayName: "Trader"))
        #expect(await tokenStore.accessToken() == "fresh-access")
        #expect(sessionManager.state == .authenticated)
    }

    @Test
    @MainActor
    func failedRefreshDuringRestorationEndsTheSession() async throws {
        let tokenStore = InMemoryTokenStore(tokens: AuthTokens(accessToken: "stale-access", refreshToken: "invalid-refresh", tokenType: "bearer", expiresIn: 3600))
        let transport = MockHTTPTransport(stubs: [
            .json(401, ["detail": "Token expired."]),      // /users/me first attempt
            .json(401, ["detail": "Refresh token revoked."]), // /auth/refresh
        ])
        let sessionManager = makeSessionManager(tokenStore: tokenStore)
        let apiClient = makeClient(
            transport: transport,
            tokenStore: tokenStore,
            onSessionExpired: { await sessionManager.handleSessionExpired() }
        )
        let authenticationService = AuthenticationService(apiClient: apiClient)

        await sessionManager.restoreSession()
        #expect(sessionManager.state == .authenticated)

        let shellViewModel = AuthenticatedAppShellViewModel(
            authenticationService: authenticationService,
            sessionManager: sessionManager,
            tokenStore: tokenStore,
            logger: TestLogger()
        )
        await shellViewModel.loadCurrentUserIfNeeded()

        #expect(sessionManager.state == .unauthenticated)
        #expect(await tokenStore.accessToken() == nil)
        #expect(shellViewModel.currentUser == nil)
    }
}
