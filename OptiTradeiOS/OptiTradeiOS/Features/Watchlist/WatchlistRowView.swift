import SwiftUI

struct WatchlistRowView: View {
    let item: WatchlistAssetItem
    let isPending: Bool
    let onRemove: () -> Void

    var body: some View {
        HStack {
            HStack(spacing: 6) {
                Text(item.symbol)
                    .font(.headline)
                if item.isFavorite {
                    Image(systemName: "star.fill")
                        .font(.caption)
                        .foregroundStyle(.yellow)
                        .accessibilityHidden(true)
                }
            }

            Spacer()

            if isPending {
                ProgressView()
            } else {
                Button(role: .destructive, action: onRemove) {
                    Image(systemName: "minus.circle")
                }
                .buttonStyle(.borderless)
                .accessibilityLabel("Remove \(item.symbol) from watchlist")
            }
        }
        .accessibilityElement(children: .combine)
    }
}
