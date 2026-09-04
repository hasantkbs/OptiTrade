import SwiftUI

struct AssetSearchResultRow: View {
    let result: AssetSearchResult
    let isInWatchlist: Bool

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(result.symbol)
                    .font(.headline)
                Text(result.name)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 4) {
                Text(result.market)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if isInWatchlist {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                        .accessibilityHidden(true)
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel)
    }

    private var accessibilityLabel: String {
        var label = "\(result.symbol), \(result.name), \(result.market)"
        if isInWatchlist {
            label += ", already in watchlist"
        }
        return label
    }
}
