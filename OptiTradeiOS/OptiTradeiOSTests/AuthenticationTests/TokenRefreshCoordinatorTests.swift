import Foundation
import Testing
@testable import OptiTradeiOS

struct TokenRefreshCoordinatorTests {
    @Test
    func concurrentCallersShareASingleRefresh() async throws {
        let expectedTokens = AuthTokens(accessToken: "new-a", refreshToken: "new-r", tokenType: "bearer", expiresIn: 3600)
        let refresher = CountingTokenRefreshing(result: .success(expectedTokens))
        let tokenStore = InMemoryTokenStore(tokens: AuthTokens(accessToken: "old-a", refreshToken: "old-r", tokenType: "bearer", expiresIn: 3600))
        let coordinator = TokenRefreshCoordinator(refresher: refresher, tokenStore: tokenStore)

        // Three "requests" hit 401 concurrently and all ask for a refresh.
        async let first = coordinator.refreshedTokens()
        async let second = coordinator.refreshedTokens()
        async let third = coordinator.refreshedTokens()

        let results = try await [first, second, third]

        #expect(results.allSatisfy { $0 == expectedTokens })
        #expect(await refresher.callCount == 1)
        #expect(await tokenStore.accessToken() == "new-a")
    }

    @Test
    func sequentialRefreshesAfterCompletionEachRunOnce() async throws {
        let refresher = CountingTokenRefreshing(delayNanoseconds: 1, result: .success(
            AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600)
        ))
        let tokenStore = InMemoryTokenStore(tokens: AuthTokens(accessToken: "old", refreshToken: "old-r", tokenType: "bearer", expiresIn: 3600))
        let coordinator = TokenRefreshCoordinator(refresher: refresher, tokenStore: tokenStore)

        _ = try await coordinator.refreshedTokens()
        _ = try await coordinator.refreshedTokens()

        // Two refreshes that don't overlap in time are two legitimate,
        // separate refresh cycles — the single-flight guarantee only
        // collapses *concurrent* callers, not sequential ones.
        #expect(await refresher.callCount == 2)
    }

    @Test
    func missingRefreshTokenFailsWithoutCallingRefresher() async {
        let refresher = CountingTokenRefreshing(result: .success(
            AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600)
        ))
        let coordinator = TokenRefreshCoordinator(refresher: refresher, tokenStore: InMemoryTokenStore())

        await #expect(throws: APIClientError.self) {
            _ = try await coordinator.refreshedTokens()
        }
        #expect(await refresher.callCount == 0)
    }

    @Test
    func refresherFailurePropagatesToAllWaiters() async {
        let refresher = CountingTokenRefreshing(result: .failure(APIClientError.unauthorized(nil)))
        let tokenStore = InMemoryTokenStore(tokens: AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let coordinator = TokenRefreshCoordinator(refresher: refresher, tokenStore: tokenStore)

        async let first = Self.attempt(coordinator)
        async let second = Self.attempt(coordinator)
        let results = await [first, second]

        for result in results {
            guard case .failure = result else {
                Issue.record("Expected every concurrent waiter to fail")
                continue
            }
        }
        #expect(await refresher.callCount == 1)
    }

    private static func attempt(_ coordinator: TokenRefreshCoordinator) async -> Result<AuthTokens, Error> {
        do {
            return .success(try await coordinator.refreshedTokens())
        } catch {
            return .failure(error)
        }
    }
}
