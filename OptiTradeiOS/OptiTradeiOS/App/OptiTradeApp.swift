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
                viewModel: RootViewModel(
                    sessionManager: container.sessionManager,
                    environmentKind: AppEnvironment.current,
                    logger: container.logger
                )
            )
        }
    }
}
