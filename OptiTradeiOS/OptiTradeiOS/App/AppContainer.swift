import Foundation

/// Composition root. Production code builds one via `init(environmentKind:)`;
/// tests build one via the designated initializer with fakes injected.
@MainActor
final class AppContainer {
    let logger: AppLogging
    let tokenStore: TokenStore
    let refreshCoordinator: TokenRefreshCoordinator
    let sessionManager: SessionManager
    let apiClient: APIClient
    let authenticationService: Authenticating

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

        let sessionConfig = Self.urlSessionConfiguration(timeoutInterval: configuration.timeoutInterval)
        let transport = URLSessionHTTPTransport(session: URLSession(configuration: sessionConfig))

        let refresher = BackendTokenRefresher(transport: transport, configuration: configuration)
        let refreshCoordinator = TokenRefreshCoordinator(refresher: refresher, tokenStore: tokenStore)
        let sessionManager = SessionManager(tokenStore: tokenStore, refreshCoordinator: refreshCoordinator, logger: logger)

        let apiClient = APIClient(
            configuration: configuration,
            transport: transport,
            tokenStore: tokenStore,
            refreshCoordinator: refreshCoordinator,
            logger: logger,
            onSessionExpired: { [sessionManager] in await sessionManager.handleSessionExpired() }
        )

        let authenticationService = AuthenticationService(apiClient: apiClient)

        self.init(
            logger: logger,
            tokenStore: tokenStore,
            refreshCoordinator: refreshCoordinator,
            sessionManager: sessionManager,
            apiClient: apiClient,
            authenticationService: authenticationService
        )
    }

    /// `URLSessionConfiguration.default` otherwise uses `URLCache.shared`,
    /// which would persist API responses (portfolio balances, positions,
    /// quant decisions, alerts) to on-disk cache files under the app's
    /// Library/Caches — readable by anything with filesystem access to
    /// the device, and outside Keychain's protection entirely. Every
    /// response this app receives is either authenticated financial data
    /// or an auth payload; neither should ever be written to a response
    /// cache. A `static` function (not inlined into `init`) so this
    /// hardening is independently testable.
    static func urlSessionConfiguration(timeoutInterval: TimeInterval) -> URLSessionConfiguration {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = timeoutInterval
        configuration.urlCache = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        return configuration
    }

    /// Test/preview-facing initializer — every dependency is injectable.
    init(
        logger: AppLogging,
        tokenStore: TokenStore,
        refreshCoordinator: TokenRefreshCoordinator,
        sessionManager: SessionManager,
        apiClient: APIClient,
        authenticationService: Authenticating
    ) {
        self.logger = logger
        self.tokenStore = tokenStore
        self.refreshCoordinator = refreshCoordinator
        self.sessionManager = sessionManager
        self.apiClient = apiClient
        self.authenticationService = authenticationService
    }
}
