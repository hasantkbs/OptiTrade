import SwiftUI

/// Renders `AssetSearchViewModel`'s state. Embedded inside `WatchlistView`
/// (shown while the attached `.searchable` field has text) rather than
/// pushed as its own screen — see that file for the combined Search/
/// Watchlist flow.
struct AssetSearchView: View {
    var viewModel: AssetSearchViewModel
    let isInWatchlist: (String) -> Bool

    var body: some View {
        content
    }

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .idle:
            ContentUnavailableView(
                "Search Assets",
                systemImage: "magnifyingglass",
                description: Text("Search by symbol or company name.")
            )

        case .loading:
            ProgressView("Searching…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)

        case .empty:
            ContentUnavailableView.search

        case .failed(let message):
            ContentUnavailableView {
                Label("Search Failed", systemImage: "exclamationmark.triangle")
            } description: {
                Text(message)
            }

        case .loaded(let results):
            List(results) { result in
                NavigationLink(value: AssetSelection(searchResult: result)) {
                    AssetSearchResultRow(result: result, isInWatchlist: isInWatchlist(result.symbol))
                }
            }
            .listStyle(.plain)
        }
    }
}
