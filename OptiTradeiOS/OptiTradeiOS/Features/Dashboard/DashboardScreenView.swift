import SwiftUI

/// The authenticated app's primary landing screen (Step 7).
///
/// `watchlistViewModel` is the *same shared instance* the Watchlist tab
/// uses (owned by `AuthenticatedAppShell`, not created fresh here) — so
/// Dashboard's Watchlist/Quant-Opportunities/AI-Analyst sections read
/// live, already-loaded data with zero duplicate network calls, and
/// adding/removing a symbol from either screen is instantly reflected in
/// both. Portfolio is the one section Dashboard fetches independently
/// (via `DashboardScreenViewModel`/`DashboardService`), since it has no
/// cross-screen mutable state to share.
///
/// Quant analysis and AI Analyst are never triggered automatically for
/// the whole watchlist here — each row is a `NavigationLink` that lets
/// the user request analysis for exactly the asset they tap, reusing
/// the existing `AssetDetailView`/`AIAnalystView` untouched.
struct DashboardScreenView: View {
    let shellViewModel: AuthenticatedAppShellViewModel
    let watchlistViewModel: WatchlistScreenViewModel
    @State private var dashboardViewModel: DashboardScreenViewModel

    private let makePortfolioViewModel: () -> PortfolioViewModel
    private let makeAssetSearchViewModel: () -> AssetSearchViewModel
    private let makeAssetDetailViewModel: () -> AssetDetailViewModel
    private let makeAIAnalystViewModel: () -> AIAnalystViewModel

    init(
        shellViewModel: AuthenticatedAppShellViewModel,
        watchlistViewModel: WatchlistScreenViewModel,
        makeDashboardViewModel: () -> DashboardScreenViewModel,
        makePortfolioViewModel: @escaping () -> PortfolioViewModel,
        makeAssetSearchViewModel: @escaping () -> AssetSearchViewModel,
        makeAssetDetailViewModel: @escaping () -> AssetDetailViewModel,
        makeAIAnalystViewModel: @escaping () -> AIAnalystViewModel
    ) {
        self.shellViewModel = shellViewModel
        self.watchlistViewModel = watchlistViewModel
        _dashboardViewModel = State(initialValue: makeDashboardViewModel())
        self.makePortfolioViewModel = makePortfolioViewModel
        self.makeAssetSearchViewModel = makeAssetSearchViewModel
        self.makeAssetDetailViewModel = makeAssetDetailViewModel
        self.makeAIAnalystViewModel = makeAIAnalystViewModel
    }

    var body: some View {
        List {
            Section {
                DashboardHeaderView(displayName: shellViewModel.currentUser?.displayName)
            }
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)

            portfolioSection
            watchlistSection
            quantOpportunitiesSection
            aiAnalystSection
        }
        .listStyle(.insetGrouped)
        .navigationTitle("Dashboard")
        .task { await dashboardViewModel.loadIfNeeded() }
        .task { await watchlistViewModel.loadIfNeeded() }
        .refreshable {
            async let portfolioRefresh: Void = dashboardViewModel.refresh()
            async let watchlistRefresh: Void = watchlistViewModel.refresh()
            _ = await (portfolioRefresh, watchlistRefresh)
        }
        .navigationDestination(for: AssetSelection.self) { selection in
            AssetDetailView(
                selection: selection,
                watchlistViewModel: watchlistViewModel,
                makeDetailViewModel: makeAssetDetailViewModel,
                makeAIAnalystViewModel: makeAIAnalystViewModel
            )
        }
    }

    // MARK: - Portfolio

    @ViewBuilder
    private var portfolioSection: some View {
        Section("Portfolio") {
            switch dashboardViewModel.portfolioState {
            case .idle, .loading:
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .center)

            case .empty:
                NavigationLink {
                    PortfolioView(viewModel: makePortfolioViewModel())
                } label: {
                    Text("No portfolio yet. View Portfolio.")
                        .foregroundStyle(.secondary)
                }

            case .failed(let message):
                DashboardSectionErrorView(message: message) {
                    Task { await dashboardViewModel.loadIfNeeded() }
                }

            case .loaded(let summary):
                NavigationLink {
                    PortfolioView(viewModel: makePortfolioViewModel())
                } label: {
                    DashboardPortfolioSummaryCard(summary: summary)
                }
            }

            if let portfolioRefreshError = dashboardViewModel.portfolioRefreshError {
                Text(portfolioRefreshError)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .accessibilityLabel("Portfolio refresh error: \(portfolioRefreshError)")
            }
        }
    }

    // MARK: - Watchlist

    @ViewBuilder
    private var watchlistSection: some View {
        Section {
            switch watchlistViewModel.state {
            case .idle, .loading:
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .center)

            case .empty:
                Text("No watchlist yet. Search for an asset to add one.")
                    .foregroundStyle(.secondary)

            case .failed(let message):
                DashboardSectionErrorView(message: message) {
                    Task { await watchlistViewModel.loadIfNeeded() }
                }

            case .loaded(let summary):
                if summary.items.isEmpty {
                    Text("No assets yet.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(summary.items.prefix(5)) { item in
                        NavigationLink(value: AssetSelection(symbol: item.symbol)) {
                            WatchlistRowView(
                                item: item,
                                isPending: watchlistViewModel.pendingSymbols.contains(item.symbol),
                                onRemove: { Task { await watchlistViewModel.remove(symbol: item.symbol) } }
                            )
                        }
                    }
                }
            }

            NavigationLink {
                WatchlistView(
                    viewModel: watchlistViewModel,
                    searchViewModel: makeAssetSearchViewModel(),
                    makeAssetDetailViewModel: makeAssetDetailViewModel,
                    makeAIAnalystViewModel: makeAIAnalystViewModel
                )
            } label: {
                Text("See All")
            }
        } header: {
            Text("Watchlist")
        }
    }

    // MARK: - Quant Opportunities / AI Analyst
    //
    // Both sections reuse the same short candidate list derived from the
    // already-loaded watchlist — no separate fetch, and never more than
    // one `/quant/analyze` call fires, and only when the user actually
    // taps a row (Section D: no automatic fan-out).

    private var quantCandidates: [DashboardQuantCandidate] {
        guard case .loaded(let summary) = watchlistViewModel.state else { return [] }
        return summary.items.prefix(3).map(DashboardQuantCandidate.init(item:))
    }

    @ViewBuilder
    private var quantOpportunitiesSection: some View {
        if !quantCandidates.isEmpty {
            Section("Quant Opportunities") {
                ForEach(quantCandidates) { candidate in
                    NavigationLink(value: candidate.assetSelection) {
                        Label(candidate.symbol, systemImage: "chart.line.uptrend.xyaxis")
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var aiAnalystSection: some View {
        if !quantCandidates.isEmpty {
            Section {
                ForEach(quantCandidates) { candidate in
                    NavigationLink {
                        AIAnalystView(
                            selection: candidate.assetSelection,
                            assetType: candidate.assetSelection.assetType,
                            makeViewModel: makeAIAnalystViewModel
                        )
                    } label: {
                        Label("Ask about \(candidate.symbol)", systemImage: "sparkles")
                    }
                }
            } header: {
                Text("AI Analyst")
            } footer: {
                Text("Explains the Decision Engine's existing result — it never generates its own trading signal.")
            }
        }
    }
}
