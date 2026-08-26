import Foundation
import Testing
@testable import OptiTradeiOS

/// Exercises the real Keychain (via a uniquely-scoped service name so these
/// tests never touch the app's actual session credentials) — not a fake.
struct KeychainTokenStoreTests {
    private func makeStore() -> KeychainTokenStore {
        let service = "com.algorix.optitrade.tests.\(UUID().uuidString)"
        return KeychainTokenStore(keychain: KeychainStore(service: service))
    }

    @Test
    func returnsNilWhenNothingStored() async {
        let store = makeStore()
        #expect(await store.accessToken() == nil)
        #expect(await store.refreshToken() == nil)
    }

    @Test
    func savesAndReadsBackBothTokens() async throws {
        let store = makeStore()
        let tokens = AuthTokens(accessToken: "a-1", refreshToken: "r-1", tokenType: "bearer", expiresIn: 3600)

        try await store.save(tokens)

        #expect(await store.accessToken() == "a-1")
        #expect(await store.refreshToken() == "r-1")
    }

    @Test
    func savingTwiceOverwritesRatherThanFailing() async throws {
        let store = makeStore()
        try await store.save(AuthTokens(accessToken: "first", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        try await store.save(AuthTokens(accessToken: "second", refreshToken: "r2", tokenType: "bearer", expiresIn: 3600))

        #expect(await store.accessToken() == "second")
        #expect(await store.refreshToken() == "r2")
    }

    @Test
    func clearRemovesBothTokens() async throws {
        let store = makeStore()
        try await store.save(AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))

        try await store.clear()

        #expect(await store.accessToken() == nil)
        #expect(await store.refreshToken() == nil)
    }

    @Test
    func clearingAnEmptyStoreDoesNotThrow() async throws {
        let store = makeStore()
        try await store.clear()
    }
}
