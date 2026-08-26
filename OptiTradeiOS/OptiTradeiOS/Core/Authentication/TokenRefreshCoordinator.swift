import Foundation

/// Performs the actual `/auth/refresh` call. Kept separate from
/// `TokenRefreshCoordinator` so the coordination logic is testable with a
/// fake that never touches the network.
protocol TokenRefreshing: Sendable {
    func refresh(refreshToken: String) async throws -> AuthTokens
}

/// Calls the backend's refresh endpoint directly over `HTTPTransport`
/// (not `APIClient`) so refreshing a token can never itself trigger the
/// refresh-on-401 path and recurse.
struct BackendTokenRefresher: TokenRefreshing {
    private let transport: HTTPTransport
    private let configuration: NetworkConfiguration

    init(transport: HTTPTransport, configuration: NetworkConfiguration) {
        self.transport = transport
        self.configuration = configuration
    }

    func refresh(refreshToken: String) async throws -> AuthTokens {
        var request = URLRequest(url: configuration.baseURL.appendingPathComponent("auth/refresh"))
        request.httpMethod = HTTPMethod.post.rawValue
        request.timeoutInterval = configuration.timeoutInterval
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try APICoding.encoder.encode(RefreshRequestDTO(refreshToken: refreshToken))

        let (data, response) = try await transport.send(request)
        guard (200..<300).contains(response.statusCode) else {
            throw APIClientError.map(statusCode: response.statusCode, data: data, decoder: APICoding.decoder)
        }
        do {
            return try APICoding.decoder.decode(TokenPairDTO.self, from: data).tokens
        } catch {
            throw APIClientError.decoding(String(describing: error))
        }
    }
}

/// Ensures at most one `/auth/refresh` call is in flight at a time.
///
/// If requests A, B, and C each receive a 401 concurrently, all three call
/// `refreshedTokens()`; only the first creates the underlying `Task`, and B
/// and C await that same task's result instead of starting their own.
actor TokenRefreshCoordinator {
    private let refresher: TokenRefreshing
    private let tokenStore: TokenStore
    private var inFlight: Task<AuthTokens, Error>?

    /// Bumped by `invalidate()` (called on logout / session teardown). A
    /// refresh started before invalidation must not persist its result
    /// after the fact — otherwise a slow refresh completing just after the
    /// user logs out would silently resurrect the session.
    private var generation = 0

    init(refresher: TokenRefreshing, tokenStore: TokenStore) {
        self.refresher = refresher
        self.tokenStore = tokenStore
    }

    @discardableResult
    func refreshedTokens() async throws -> AuthTokens {
        if let inFlight {
            return try await inFlight.value
        }

        let generationAtStart = generation
        let task = Task { () throws -> AuthTokens in
            guard let refreshToken = await tokenStore.refreshToken() else {
                throw APIClientError.unauthorized(nil)
            }
            return try await refresher.refresh(refreshToken: refreshToken)
        }
        inFlight = task
        defer { inFlight = nil }

        let tokens = try await task.value

        guard generation == generationAtStart else {
            // Session was invalidated (logout) while this refresh was in
            // flight. Discard the result instead of writing it to the
            // Keychain.
            throw APIClientError.cancelled
        }
        try await tokenStore.save(tokens)
        return tokens
    }

    /// Called when the session is deliberately torn down (logout, or a
    /// prior refresh failure already ending the session). Cancels any
    /// in-flight refresh and ensures its result — if it completes anyway —
    /// is discarded rather than persisted.
    func invalidate() {
        generation += 1
        inFlight?.cancel()
        inFlight = nil
    }
}
