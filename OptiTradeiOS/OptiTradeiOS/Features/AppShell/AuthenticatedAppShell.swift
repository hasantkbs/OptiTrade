import SwiftUI

/// The authenticated application's primary navigation structure: Dashboard
/// (the primary landing tab, Step 7), Portfolio, and Watchlist/Search.
///
/// `watchlistViewModel` is owned here — not inside `WatchlistView`'s own
/// init as it was through Step 6 — specifically so Dashboard and the
/// Watchlist tab share the exact same instance and therefore the exact
/// same live state (Step 7 needs a second consumer of watchlist data;
/// two independent instances would let "is AAPL in my watchlist"
/// disagree between the two screens until each happened to reload).
struct AuthenticatedAppShell: View {
    @State private var shellViewModel: AuthenticatedAppShellViewModel
    @State private var watchlistViewModel: WatchlistScreenViewModel
    private let makePortfolioViewModel: () -> PortfolioViewModel
    private let makeAssetSearchViewModel: () -> AssetSearchViewModel
    private let makeAssetDetailViewModel: () -> AssetDetailViewModel
    private let makeAIAnalystViewModel: () -> AIAnalystViewModel
    private let makeDashboardViewModel: () -> DashboardScreenViewModel

    init(
        shellViewModel: AuthenticatedAppShellViewModel,
        makeWatchlistScreenViewModel: () -> WatchlistScreenViewModel,
        makePortfolioViewModel: @escaping () -> PortfolioViewModel,
        makeAssetSearchViewModel: @escaping () -> AssetSearchViewModel,
        makeAssetDetailViewModel: @escaping () -> AssetDetailViewModel,
        makeAIAnalystViewModel: @escaping () -> AIAnalystViewModel,
        makeDashboardViewModel: @escaping () -> DashboardScreenViewModel
    ) {
        _shellViewModel = State(initialValue: shellViewModel)
        _watchlistViewModel = State(initialValue: makeWatchlistScreenViewModel())
        self.makePortfolioViewModel = makePortfolioViewModel
        self.makeAssetSearchViewModel = makeAssetSearchViewModel
        self.makeAssetDetailViewModel = makeAssetDetailViewModel
        self.makeAIAnalystViewModel = makeAIAnalystViewModel
        self.makeDashboardViewModel = makeDashboardViewModel
    }

    var body: some View {
        TabView {
            NavigationStack {
                DashboardScreenView(
                    shellViewModel: shellViewModel,
                    watchlistViewModel: watchlistViewModel,
                    makeDashboardViewModel: makeDashboardViewModel,
                    makePortfolioViewModel: makePortfolioViewModel,
                    makeAssetSearchViewModel: makeAssetSearchViewModel,
                    makeAssetDetailViewModel: makeAssetDetailViewModel,
                    makeAIAnalystViewModel: makeAIAnalystViewModel
                )
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        AccountMenu(viewModel: shellViewModel)
                    }
                }
            }
            .tabItem { Label("Dashboard", systemImage: "square.grid.2x2") }

            NavigationStack {
                PortfolioView(viewModel: makePortfolioViewModel())
                    .navigationTitle("Portfolio")
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            AccountMenu(viewModel: shellViewModel)
                        }
                    }
            }
            .tabItem { Label("Portfolio", systemImage: "chart.pie") }

            NavigationStack {
                WatchlistView(
                    viewModel: watchlistViewModel,
                    searchViewModel: makeAssetSearchViewModel(),
                    makeAssetDetailViewModel: makeAssetDetailViewModel,
                    makeAIAnalystViewModel: makeAIAnalystViewModel
                )
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        AccountMenu(viewModel: shellViewModel)
                    }
                }
            }
            .tabItem { Label("Watchlist", systemImage: "star") }
        }
        .task { await shellViewModel.loadCurrentUserIfNeeded() }
    }
}

/// Holds what Step 2's shell used to show front-and-center (current user +
/// logout) — still the same `AuthenticatedAppShellViewModel`, just
/// relocated now that Dashboard/Portfolio are the primary content.
private struct AccountMenu: View {
    let viewModel: AuthenticatedAppShellViewModel

    var body: some View {
        Menu {
            if let user = viewModel.currentUser {
                Text(user.displayName)
                Text(user.email)
            } else if viewModel.isLoadingUser {
                Text("Loading…")
            } else if let error = viewModel.userLoadError {
                Text(error)
            }

            Divider()

            Button(role: .destructive) {
                Task { await viewModel.logout() }
            } label: {
                if viewModel.isLoggingOut {
                    Text("Logging out…")
                } else {
                    Label("Log Out", systemImage: "rectangle.portrait.and.arrow.right")
                }
            }
            .disabled(viewModel.isLoggingOut)
        } label: {
            Image(systemName: "person.circle")
                .accessibilityLabel("Account")
        }
    }
}
