import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct LoginViewModelTests {
    private func makeViewModel(
        service: StubAuthenticationService,
        tokenStore: TokenStore = InMemoryTokenStore()
    ) -> (LoginViewModel, SessionManager) {
        let sessionManager = makeSessionManager(tokenStore: tokenStore)
        let viewModel = LoginViewModel(authenticationService: service, sessionManager: sessionManager, logger: TestLogger())
        return (viewModel, sessionManager)
    }

    @Test
    func successfulLoginPersistsTokensAndAuthenticatesSession() async {
        let tokens = AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600)
        let service = StubAuthenticationService(loginResult: .success(tokens))
        let tokenStore = InMemoryTokenStore()
        let (viewModel, sessionManager) = makeViewModel(service: service, tokenStore: tokenStore)
        viewModel.email = "trader@optitrade.app"
        viewModel.password = "correct-horse"

        await viewModel.login()

        #expect(viewModel.authError == nil)
        #expect(sessionManager.state == .authenticated)
        #expect(await tokenStore.accessToken() == "a")
        #expect(await service.loginCallCount == 1)
    }

    @Test
    func invalidCredentialsSurfaceASafeMessageAndStaySignedOut() async {
        let service = StubAuthenticationService(loginResult: .failure(APIClientError.unauthorized(nil)))
        let (viewModel, sessionManager) = makeViewModel(service: service)
        await sessionManager.restoreSession() // reach .unauthenticated, as on the real login screen
        viewModel.email = "trader@optitrade.app"
        viewModel.password = "wrong"

        await viewModel.login()

        #expect(viewModel.authError == "Incorrect email or password.")
        #expect(sessionManager.state == .unauthenticated)
    }

    @Test
    func networkFailureSurfacesASafeMessage() async {
        let service = StubAuthenticationService(loginResult: .failure(APIClientError.transport("offline")))
        let (viewModel, _) = makeViewModel(service: service)
        viewModel.email = "trader@optitrade.app"
        viewModel.password = "whatever"

        await viewModel.login()

        #expect(viewModel.authError == "Couldn't reach the server. Check your connection and try again.")
    }

    @Test
    func emptyEmailFailsValidationWithoutCallingTheService() async {
        let service = StubAuthenticationService(loginResult: .success(
            AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600)
        ))
        let (viewModel, _) = makeViewModel(service: service)
        viewModel.email = "   "
        viewModel.password = "something"

        await viewModel.login()

        #expect(viewModel.validationError == .emptyEmail)
        #expect(await service.loginCallCount == 0)
    }

    @Test
    func emptyPasswordFailsValidationWithoutCallingTheService() async {
        let service = StubAuthenticationService()
        let (viewModel, _) = makeViewModel(service: service)
        viewModel.email = "trader@optitrade.app"
        viewModel.password = ""

        await viewModel.login()

        #expect(viewModel.validationError == .emptyPassword)
        #expect(await service.loginCallCount == 0)
    }

    @Test
    func repeatedTapsOnlyProduceOneLoginRequest() async {
        let tokens = AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600)
        let service = StubAuthenticationService(loginResult: .success(tokens), delayNanoseconds: 20_000_000)
        let (viewModel, _) = makeViewModel(service: service)
        viewModel.email = "trader@optitrade.app"
        viewModel.password = "correct-horse"

        async let first: Void = viewModel.login()
        async let second: Void = viewModel.login()
        async let third: Void = viewModel.login()
        _ = await [first, second, third]

        #expect(await service.loginCallCount == 1)
    }
}
