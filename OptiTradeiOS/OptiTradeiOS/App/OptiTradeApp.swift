import SwiftUI

@main
struct OptiTradeApp: App {
    private let container: AppContainer

    init() {
        container = AppContainer()
    }

    var body: some Scene {
        WindowGroup {
            RootView(
                sessionManager: container.sessionManager,
                makeLoginViewModel: {
                    LoginViewModel(
                        authenticationService: container.authenticationService,
                        sessionManager: container.sessionManager,
                        logger: container.logger
                    )
                },
                makeShellViewModel: {
                    AuthenticatedAppShellViewModel(
                        authenticationService: container.authenticationService,
                        sessionManager: container.sessionManager,
                        tokenStore: container.tokenStore,
                        logger: container.logger
                    )
                }
            )
        }
    }
}
