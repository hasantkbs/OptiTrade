import SwiftUI

/// Minimal navigation destination reached after selecting an asset from
/// Asset Search results or a Watchlist row. Deliberately NOT the full Asset
/// Detail screen — Quant Analysis and the AI Analyst are separate, later
/// tasks. This exists only to close Step 4's user flow ("open an asset,
/// add/remove it from the Watchlist") with a strongly-typed `AssetSelection`
/// rather than a dictionary.
struct AssetDetailView: View {
    let selection: AssetSelection
    var watchlistViewModel: WatchlistScreenViewModel

    var body: some View {
        VStack(spacing: 20) {
            VStack(spacing: 4) {
                Text(selection.symbol)
                    .font(.largeTitle.bold())
                if let name = selection.name {
                    Text(name)
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }
                if let market = selection.market {
                    Text(market)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            watchlistButton

            Spacer()
        }
        .padding()
        .navigationTitle(selection.symbol)
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder
    private var watchlistButton: some View {
        let isPending = watchlistViewModel.pendingSymbols.contains(selection.symbol)
        let isMember = watchlistViewModel.isInWatchlist(selection.symbol)

        Button {
            Task {
                if isMember {
                    await watchlistViewModel.remove(symbol: selection.symbol)
                } else {
                    await watchlistViewModel.add(symbol: selection.symbol)
                }
            }
        } label: {
            if isPending {
                ProgressView()
                    .frame(maxWidth: .infinity)
            } else {
                Label(
                    isMember ? "Remove from Watchlist" : "Add to Watchlist",
                    systemImage: isMember ? "minus.circle" : "plus.circle"
                )
                .frame(maxWidth: .infinity)
            }
        }
        .buttonStyle(.borderedProminent)
        .tint(isMember ? .red : .accentColor)
        .disabled(isPending)
        .accessibilityLabel(isMember ? "Remove \(selection.symbol) from watchlist" : "Add \(selection.symbol) to watchlist")

        if let mutationError = watchlistViewModel.mutationError {
            Text(mutationError)
                .font(.footnote)
                .foregroundStyle(.red)
        }
    }
}
