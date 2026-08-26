import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct AuthenticatedAppShellViewModelTests {
    private func makeViewModel(
        service: StubAuthenticationService,
        tokenStore: TokenStore,
        sessionManager: SessionManager? = nil
    ) -> (AuthenticatedAppShellViewModel, SessionManager) {
        let manager = sessionManager ?? makeSessionManager(tokenStore: tokenStore)
        let viewModel = AuthenticatedAppShellViewModel(
            authenticationService: service,
            sessionManager: manager,
            tokenStore: tokenStore,
            logger: TestLogger()
        )
        return (viewModel, manager)
    }

    @Test
    func loadsCurrentUserOnce() async {
        let user = CurrentUser(id: 1, email: "trader@optitrade.app", displayName: "Trader")
        let service = StubAuthenticationService(currentUserResult: .success(user))
        let (viewModel, _) = makeViewModel(service: service, tokenStore: InMemoryTokenStore())

        await viewModel.loadCurrentUserIfNeeded()
        await viewModel.loadCurrentUserIfNeeded() // second call should be a no-op

        #expect(viewModel.currentUser == user)
        #expect(await service.currentUserCallCount == 1)
    }

    @Test
    func currentUserLoadFailureSurfacesASafeMessage() async {
        let service = StubAuthenticationService(currentUserResult: .failure(APIClientError.server(statusCode: 500, payload: nil)))
        let (viewModel, _) = makeViewModel(service: service, tokenStore: InMemoryTokenStore())

        await viewModel.loadCurrentUserIfNeeded()

        #expect(viewModel.currentUser == nil)
        #expect(viewModel.userLoadError == "The server is having trouble. Please try again shortly.")
    }

    @Test
    func logoutClearsCredentialsAndEndsSessionOnSuccess() async {
        let tokenStore = InMemoryTokenStore(tokens: AuthTokens(accessToken: "a", refreshToken: "r-1", tokenType: "bearer", expiresIn: 3600))
        let service = StubAuthenticationService(logoutResult: .success(()))
        let (viewModel, sessionManager) = makeViewModel(service: service, tokenStore: tokenStore)
        await sessionManager.restoreSession()

        await viewModel.logout()

        #expect(sessionManager.state == .unauthenticated)
        #expect(await tokenStore.accessToken() == nil)
        #expect(await service.logoutCallCount == 1)
    }

    @Test
    func logoutClearsCredentialsLocallyEvenWhenTheNetworkCallFails() async {
        let tokenStore = InMemoryTokenStore(tokens: AuthTokens(accessToken: "a", refreshToken: "r-1", tokenType: "bearer", expiresIn: 3600))
        let service = StubAuthenticationService(logoutResult: .failure(APIClientError.transport("offline")))
        let (viewModel, sessionManager) = makeViewModel(service: service, tokenStore: tokenStore)
        await sessionManager.restoreSession()

        await viewModel.logout()

        #expect(sessionManager.state == .unauthenticated)
        #expect(await tokenStore.accessToken() == nil)
        #expect(await tokenStore.refreshToken() == nil)
    }

    @Test
    func repeatedLogoutTapsOnlyProduceOneRevocationRequest() async {
        let tokenStore = InMemoryTokenStore(tokens: AuthTokens(accessToken: "a", refreshToken: "r-1", tokenType: "bearer", expiresIn: 3600))
        let service = StubAuthenticationService(logoutResult: .success(()), delayNanoseconds: 20_000_000)
        let (viewModel, sessionManager) = makeViewModel(service: service, tokenStore: tokenStore)
        await sessionManager.restoreSession()

        async let first: Void = viewModel.logout()
        async let second: Void = viewModel.logout()
        _ = await [first, second]

        #expect(await service.logoutCallCount == 1)
        #expect(sessionManager.state == .unauthenticated)
    }
}
