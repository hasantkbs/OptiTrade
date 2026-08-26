import Foundation
@testable import OptiTradeiOS

/// Shared fixtures/factories used across the test target so each test file
/// doesn't re-derive its own `APIClient` wiring.
enum TestSupport {
    static let configuration = NetworkConfiguration(baseURL: URL(string: "http://localhost:8000")!, timeoutInterval: 5)
}

func makeClient(
    transport: HTTPTransport,
    tokenStore: TokenStore,
    refresher: TokenRefreshing? = nil,
    onSessionExpired: @escaping @Sendable () async -> Void = {}
) -> APIClient {
    let refreshCoordinator = TokenRefreshCoordinator(
        refresher: refresher ?? BackendTokenRefresher(transport: transport, configuration: TestSupport.configuration),
        tokenStore: tokenStore
    )
    return APIClient(
        configuration: TestSupport.configuration,
        transport: transport,
        tokenStore: tokenStore,
        refreshCoordinator: refreshCoordinator,
        logger: TestLogger(),
        onSessionExpired: onSessionExpired
    )
}
