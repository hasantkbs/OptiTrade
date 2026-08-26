import Foundation
@testable import OptiTradeiOS

/// In-memory `TokenStore` fake — no Keychain access, no disk I/O.
actor InMemoryTokenStore: TokenStore {
    private var tokens: AuthTokens?

    init(tokens: AuthTokens? = nil) {
        self.tokens = tokens
    }

    func accessToken() async -> String? { tokens?.accessToken }
    func refreshToken() async -> String? { tokens?.refreshToken }

    func save(_ tokens: AuthTokens) async throws {
        self.tokens = tokens
    }

    func clear() async throws {
        tokens = nil
    }
}
