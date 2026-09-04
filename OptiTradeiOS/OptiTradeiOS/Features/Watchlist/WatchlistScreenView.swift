import SwiftUI

/// The combined Search / Watchlist screen:
///   - no search text -> shows the user's real Watchlist
///   - search text present -> shows `AssetSearchView`'s live results
///
/// Both list a row that pushes the same `AssetSelection`-typed
/// `AssetDetailView` destination, closing the flow described in Step 4's
/// spec (`Search/Watchlist -> Asset Search -> Asset Result -> Asset ->
/// Watchlist`) as one `NavigationStack`, not four separate screens.
struct WatchlistView: View {
    @State private var viewModel: WatchlistScreenViewModel
    @State private var searchViewModel: AssetSearchViewModel

    init(viewModel: WatchlistScreenViewModel, searchViewModel: AssetSearchViewModel) {
        _viewModel = State(initialValue: viewModel)
        _searchViewModel = State(initialValue: searchViewModel)
    }

    var body: some View {
        content
            .navigationTitle("Watchlist")
            .searchable(text: searchTextBinding, prompt: "Search symbol or name")
            .task { await viewModel.loadIfNeeded() }
            .navigationDestination(for: AssetSelection.self) { selection in
                AssetDetailView(selection: selection, watchlistViewModel: viewModel)
            }
    }

    private var searchTextBinding: Binding<String> {
        Binding(
            get: { searchViewModel.query },
            set: { searchViewModel.query = $0 }
        )
    }

    @ViewBuilder
    private var content: some View {
        if searchViewModel.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            watchlistContent
        } else {
            AssetSearchView(viewModel: searchViewModel, isInWatchlist: viewModel.isInWatchlist)
        }
    }

    @ViewBuilder
    private var watchlistContent: some View {
        switch viewModel.state {
        case .idle, .loading:
            ProgressView("Loading watchlist…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)

        case .empty:
            WatchlistEmptyStateView()

        case .failed(let message):
            WatchlistErrorView(message: message) {
                Task { await viewModel.loadIfNeeded() }
            }

        case .loaded(let summary):
            WatchlistLoadedView(
                summary: summary,
                refreshError: viewModel.refreshError,
                mutationError: viewModel.mutationError,
                pendingSymbols: viewModel.pendingSymbols,
                onRemove: { symbol in Task { await viewModel.remove(symbol: symbol) } }
            )
            .refreshable { await viewModel.refresh() }
        }
    }
}

// MARK: - Empty / error states

private struct WatchlistEmptyStateView: View {
    var body: some View {
        ContentUnavailableView(
            "No Watchlist Yet",
            systemImage: "star",
            description: Text("Search for an asset above to start your watchlist.")
        )
    }
}

private struct WatchlistErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Couldn't Load Watchlist", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button("Try Again", action: retry)
        }
    }
}

// MARK: - Loaded state

private struct WatchlistLoadedView: View {
    let summary: WatchlistSummary
    let refreshError: String?
    let mutationError: String?
    let pendingSymbols: Set<String>
    let onRemove: (String) -> Void

    var body: some View {
        List {
            if let refreshError {
                Section {
                    Text(refreshError)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .accessibilityLabel("Refresh error: \(refreshError)")
                }
            }

            if let mutationError {
                Section {
                    Text(mutationError)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .accessibilityLabel("Watchlist error: \(mutationError)")
                }
            }

            Section(summary.name) {
                if summary.items.isEmpty {
                    Text("No assets yet. Search above to add one.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(summary.items) { item in
                        NavigationLink(value: AssetSelection(symbol: item.symbol)) {
                            WatchlistRowView(
                                item: item,
                                isPending: pendingSymbols.contains(item.symbol),
                                onRemove: { onRemove(item.symbol) }
                            )
                        }
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
    }
}
