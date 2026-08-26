import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct SessionManagerTests {
    @Test
    func restoringWithNoStoredTokenEndsUnauthenticated() async {
        let manager = SessionManager(tokenStore: InMemoryTokenStore(), logger: TestLogger())
        await manager.restoreSession()
        #expect(manager.state == .unauthenticated)
    }

    @Test
    func restoringWithStoredTokenEndsAuthenticated() async {
        let store = InMemoryTokenStore(tokens: AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let manager = SessionManager(tokenStore: store, logger: TestLogger())
        await manager.restoreSession()
        #expect(manager.state == .authenticated)
    }

    @Test
    func establishSessionPersistsTokensAndTransitionsToAuthenticated() async throws {
        let store = InMemoryTokenStore()
        let manager = SessionManager(tokenStore: store, logger: TestLogger())

        try await manager.establishSession(with: AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))

        #expect(manager.state == .authenticated)
        #expect(await store.accessToken() == "a")
    }

    @Test
    func endSessionClearsTokensAndTransitionsToUnauthenticated() async throws {
        let store = InMemoryTokenStore(tokens: AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let manager = SessionManager(tokenStore: store, logger: TestLogger())
        await manager.restoreSession()

        await manager.endSession()

        #expect(manager.state == .unauthenticated)
        #expect(await store.accessToken() == nil)
    }

    @Test
    func handleSessionExpiredBehavesLikeEndSession() async {
        let store = InMemoryTokenStore(tokens: AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let manager = SessionManager(tokenStore: store, logger: TestLogger())
        await manager.restoreSession()

        await manager.handleSessionExpired()

        #expect(manager.state == .unauthenticated)
        #expect(await store.refreshToken() == nil)
    }
}
