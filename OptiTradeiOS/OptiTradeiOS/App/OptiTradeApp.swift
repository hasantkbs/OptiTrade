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
                },
                makePortfolioViewModel: {
                    PortfolioViewModel(
                        portfolioService: PortfolioService(apiClient: container.apiClient),
                        logger: container.logger
                    )
                },
                makeWatchlistScreenViewModel: {
                    WatchlistScreenViewModel(
                        watchlistService: WatchlistService(apiClient: container.apiClient),
                        logger: container.logger
                    )
                },
                makeAssetSearchViewModel: {
                    // No market-selection UI yet (out of Step 4's scope) —
                    // "US" is a real key in `core.market_config.MARKETS`,
                    // not a placeholder.
                    AssetSearchViewModel(
                        market: "US",
                        service: AssetService(apiClient: container.apiClient),
                        logger: container.logger
                    )
                },
                makeAssetDetailViewModel: {
                    AssetDetailViewModel(
                        service: AssetDetailService(apiClient: container.apiClient),
                        logger: container.logger
                    )
                },
                makeAIAnalystViewModel: {
                    AIAnalystViewModel(
                        service: AIAnalystService(apiClient: container.apiClient),
                        logger: container.logger
                    )
                },
                makeDashboardViewModel: {
                    DashboardScreenViewModel(
                        service: DashboardService(portfolioService: PortfolioService(apiClient: container.apiClient)),
                        logger: container.logger
                    )
                },
                makeAlertViewModel: {
                    AlertViewModel(
                        service: AlertService(apiClient: container.apiClient),
                        logger: container.logger
                    )
                }
            )
        }
    }
}
