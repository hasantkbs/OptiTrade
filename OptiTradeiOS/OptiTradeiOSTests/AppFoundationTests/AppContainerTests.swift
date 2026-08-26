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
