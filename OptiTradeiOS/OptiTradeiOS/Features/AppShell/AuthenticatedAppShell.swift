import SwiftUI

/// The authenticated application's primary navigation structure. Portfolio
/// and Watchlist/Search are the only real destinations so far — Quant
/// Analysis/AI Analyst/Dashboard/Paper Trading are separate, later tasks
/// and are not stubbed in here.
struct AuthenticatedAppShell: View {
    @State private var shellViewModel: AuthenticatedAppShellViewModel
    private let makePortfolioViewModel: () -> PortfolioViewModel
    private let makeWatchlistScreenViewModel: () -> WatchlistScreenViewModel
    private let makeAssetSearchViewModel: () -> AssetSearchViewModel

    init(
        shellViewModel: AuthenticatedAppShellViewModel,
        makePortfolioViewModel: @escaping () -> PortfolioViewModel,
        makeWatchlistScreenViewModel: @escaping () -> WatchlistScreenViewModel,
        makeAssetSearchViewModel: @escaping () -> AssetSearchViewModel
    ) {
        _shellViewModel = State(initialValue: shellViewModel)
        self.makePortfolioViewModel = makePortfolioViewModel
        self.makeWatchlistScreenViewModel = makeWatchlistScreenViewModel
        self.makeAssetSearchViewModel = makeAssetSearchViewModel
    }

    var body: some View {
        TabView {
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
                WatchlistView(viewModel: makeWatchlistScreenViewModel(), searchViewModel: makeAssetSearchViewModel())
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
/// relocated now that Portfolio is the primary content.
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
