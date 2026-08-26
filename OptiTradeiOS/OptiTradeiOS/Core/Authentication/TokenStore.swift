import Foundation

/// Secure storage for the current session's tokens. Implementations must
/// never persist to `UserDefaults` and must never log token values.
protocol TokenStore: Sendable {
    func accessToken() async -> String?
    func refreshToken() async -> String?
    func save(_ tokens: AuthTokens) async throws
    func clear() async throws
}

/// `KeychainTokenStore` — Keychain-backed implementation.
///
/// An `actor` so concurrent reads/writes from multiple in-flight requests
/// (and the refresh coordinator) are serialized without extra locking.
actor KeychainTokenStore: TokenStore {
    private let keychain: KeychainStore
    private let accessTokenKey = "accessToken"
    private let refreshTokenKey = "refreshToken"

    init(keychain: KeychainStore) {
        self.keychain = keychain
    }

    func accessToken() async -> String? {
        (try? readString(accessTokenKey)) ?? nil
    }

    func refreshToken() async -> String? {
        (try? readString(refreshTokenKey)) ?? nil
    }

    func save(_ tokens: AuthTokens) async throws {
        try keychain.set(Data(tokens.accessToken.utf8), forKey: accessTokenKey)
        try keychain.set(Data(tokens.refreshToken.utf8), forKey: refreshTokenKey)
    }

    func clear() async throws {
        try keychain.delete(forKey: accessTokenKey)
        try keychain.delete(forKey: refreshTokenKey)
    }

    private func readString(_ key: String) throws -> String? {
        guard let data = try keychain.get(forKey: key) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}
