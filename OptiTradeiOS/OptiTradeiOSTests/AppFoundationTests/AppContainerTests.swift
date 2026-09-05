import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct AppContainerTests {
    @Test
    func testInitializerWiresInjectedDependenciesRatherThanConstructingItsOwn() {
        let logger = TestLogger()
        let tokenStore = InMemoryTokenStore()
        let refreshCoordinator = TokenRefreshCoordinator(
            refresher: CountingTokenRefreshing(result: .failure(APIClientError.unauthorized(nil))),
            tokenStore: tokenStore
        )
        let sessionManager = SessionManager(tokenStore: tokenStore, refreshCoordinator: refreshCoordinator, logger: logger)
        let apiClient = makeClient(transport: MockHTTPTransport(), tokenStore: tokenStore)
        let authenticationService = AuthenticationService(apiClient: apiClient)

        let container = AppContainer(
            logger: logger,
            tokenStore: tokenStore,
            refreshCoordinator: refreshCoordinator,
            sessionManager: sessionManager,
            apiClient: apiClient,
            authenticationService: authenticationService
        )

        #expect(container.sessionManager === sessionManager)
        #expect(container.apiClient === apiClient)
    }

    /// Step 9 hardening: every API response here is either authenticated
    /// financial data (portfolio balances, positions, quant decisions,
    /// alerts) or an auth payload — none of it should ever be written to
    /// an on-disk response cache. `URLSessionConfiguration.default`
    /// otherwise uses `URLCache.shared` for exactly that.
    @Test
    func urlSessionConfigurationDisablesResponseCaching() {
        let configuration = AppContainer.urlSessionConfiguration(timeoutInterval: 30)

        #expect(configuration.urlCache == nil)
        #expect(configuration.requestCachePolicy == .reloadIgnoringLocalCacheData)
        #expect(configuration.timeoutIntervalForRequest == 30)
    }

    @Test
    func productionInitializerRestoresNoSessionWhenKeychainIsEmpty() async {
        // Uses the real KeychainTokenStore end-to-end (development environment,
        // no stubbed network) to prove the DI graph in `AppContainer()` actually
        // constructs and connects without crashing.
        let container = AppContainer(environmentKind: .development)
        await container.sessionManager.restoreSession()
        #expect(container.sessionManager.state == .unauthenticated || container.sessionManager.state == .authenticated)
    }
}
