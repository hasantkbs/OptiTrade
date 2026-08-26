import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct RootViewModelTests {
    @Test
    func startTransitionsFromLaunchingToReadyReflectingSessionState() async {
        let store = InMemoryTokenStore(tokens: AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let sessionManager = SessionManager(tokenStore: store, logger: TestLogger())
        let viewModel = RootViewModel(sessionManager: sessionManager, environmentKind: .development, logger: TestLogger())

        #expect(viewModel.status == .launching)

        await viewModel.start()

        #expect(viewModel.status == .ready(environment: .development, sessionState: .authenticated))
    }
}
