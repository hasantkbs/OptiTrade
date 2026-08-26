import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct SessionManagerTests {
    @Test
    func restoringWithNoStoredTokenEndsUnauthenticated() async {
        let manager = makeSessionManager(tokenStore: InMemoryTokenStore())
        await manager.restoreSession()
        #expect(manager.state == .unauthenticated)
    }

    @Test
    func restoringWithStoredTokenEndsAuthenticated() async {
        let store = InMemoryTokenStore(tokens: AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let manager = makeSessionManager(tokenStore: store)
        await manager.restoreSession()
        #expect(manager.state == .authenticated)
    }

    @Test
    func concurrentRestoreCallsShareOneRestoration() async {
        let store = InMemoryTokenStore(tokens: AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let manager = makeSessionManager(tokenStore: store)

        async let first: Void = manager.restoreSession()
        async let second: Void = manager.restoreSession()
        _ = await [first, second]

        #expect(manager.state == .authenticated)
    }

    @Test
    func establishSessionPersistsTokensAndTransitionsToAuthenticated() async throws {
        let store = InMemoryTokenStore()
        let manager = makeSessionManager(tokenStore: store)

        try await manager.establishSession(with: AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))

        #expect(manager.state == .authenticated)
        #expect(await store.accessToken() == "a")
    }

    @Test
    func endSessionClearsTokensAndTransitionsToUnauthenticated() async throws {
        let store = InMemoryTokenStore(tokens: AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let manager = makeSessionManager(tokenStore: store)
        await manager.restoreSession()

        await manager.endSession()

        #expect(manager.state == .unauthenticated)
        #expect(await store.accessToken() == nil)
    }

    @Test
    func handleSessionExpiredBehavesLikeEndSession() async {
        let store = InMemoryTokenStore(tokens: AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let manager = makeSessionManager(tokenStore: store)
        await manager.restoreSession()

        await manager.handleSessionExpired()

        #expect(manager.state == .unauthenticated)
        #expect(await store.refreshToken() == nil)
    }

    @Test
    func staleRefreshCompletingAfterLogoutCannotResurrectTheSession() async throws {
        let store = InMemoryTokenStore(tokens: AuthTokens(accessToken: "old-a", refreshToken: "old-r", tokenType: "bearer", expiresIn: 3600))
        let refresher = CountingTokenRefreshing(
            delayNanoseconds: 30_000_000,
            result: .success(AuthTokens(accessToken: "new-a", refreshToken: "new-r", tokenType: "bearer", expiresIn: 3600))
        )
        let refreshCoordinator = TokenRefreshCoordinator(refresher: refresher, tokenStore: store)
        let manager = makeSessionManager(tokenStore: store, refreshCoordinator: refreshCoordinator)
        await manager.restoreSession()

        // A refresh starts (e.g. triggered by a 401 elsewhere in the app)...
        async let refreshResult: Result<AuthTokens, Error> = {
            do {
                return .success(try await refreshCoordinator.refreshedTokens())
            } catch {
                return .failure(error)
            }
        }()

        // Give the refresh a head start so it has genuinely captured its
        // generation snapshot and is inside the (slower) network call below
        // before logout races it — otherwise this test's own ordering,
        // not the coordinator, would decide who "wins".
        try await Task.sleep(nanoseconds: 5_000_000)

        // ...but the user logs out before that refresh finishes.
        await manager.endSession()

        _ = await refreshResult

        #expect(manager.state == .unauthenticated)
        #expect(await store.accessToken() == nil)
        #expect(await store.refreshToken() == nil)
    }
}
