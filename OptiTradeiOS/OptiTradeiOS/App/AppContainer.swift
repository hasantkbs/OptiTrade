import Foundation

/// Composition root. Production code builds one via `init(environmentKind:)`;
/// tests build one via the designated initializer with fakes injected.
@MainActor
final class AppContainer {
    let logger: AppLogging
    let tokenStore: TokenStore
    let sessionManager: SessionManager
    let apiClient: APIClient

    convenience init(environmentKind: AppEnvironmentKind = AppEnvironment.current) {
        let logger = AppLogger()
        let configuration: NetworkConfiguration
        do {
            configuration = try AppEnvironment.networkConfiguration(for: environmentKind)
        } catch {
            // Intentionally fatal: shipping a build with no confirmed backend
            // URL for its environment is a configuration bug, not something
            // to silently paper over with a guessed domain.
            fatalError("OptiTrade: no network configuration for \(environmentKind): \(error)")
        }

        let tokenStore = KeychainTokenStore(keychain: KeychainStore(service: "com.algorix.optitrade.auth"))
        let sessionManager = SessionManager(tokenStore: tokenStore, logger: logger)

        let sessionConfig = URLSessionConfiguration.default
        sessionConfig.timeoutIntervalForRequest = configuration.timeoutInterval
        let transport = URLSessionHTTPTransport(session: URLSession(configuration: sessionConfig))

        let refresher = BackendTokenRefresher(transport: transport, configuration: configuration)
        let refreshCoordinator = TokenRefreshCoordinator(refresher: refresher, tokenStore: tokenStore)

        let apiClient = APIClient(
            configuration: configuration,
            transport: transport,
            tokenStore: tokenStore,
            refreshCoordinator: refreshCoordinator,
            logger: logger,
            onSessionExpired: { [sessionManager] in await sessionManager.handleSessionExpired() }
        )

        self.init(
            logger: logger,
            tokenStore: tokenStore,
            sessionManager: sessionManager,
            apiClient: apiClient
        )
    }

    /// Test/preview-facing initializer — every dependency is injectable.
    init(logger: AppLogging, tokenStore: TokenStore, sessionManager: SessionManager, apiClient: APIClient) {
        self.logger = logger
        self.tokenStore = tokenStore
        self.sessionManager = sessionManager
        self.apiClient = apiClient
    }
}
