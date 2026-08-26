import SwiftUI

struct PortfolioView: View {
    @State private var viewModel: PortfolioViewModel

    init(viewModel: PortfolioViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        content
            .task { await viewModel.loadIfNeeded() }
    }

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .idle, .loading:
            ProgressView("Loading portfolio…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)

        case .empty:
            PortfolioEmptyStateView()

        case .failed(let message):
            PortfolioErrorView(message: message) {
                Task { await viewModel.loadIfNeeded() }
            }

        case .loaded(let summary):
            PortfolioLoadedView(summary: summary, refreshError: viewModel.refreshError)
                .refreshable { await viewModel.refresh() }
        }
    }
}

// MARK: - Empty / error states

private struct PortfolioEmptyStateView: View {
    var body: some View {
        ContentUnavailableView(
            "No Portfolio Yet",
            systemImage: "chart.pie",
            description: Text("You don't have a portfolio yet.")
        )
    }
}

private struct PortfolioErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Couldn't Load Portfolio", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button("Try Again", action: retry)
        }
    }
}

// MARK: - Loaded state

private struct PortfolioLoadedView: View {
    let summary: PortfolioSummary
    let refreshError: String?

    var body: some View {
        List {
            Section {
                PortfolioSummaryHeader(summary: summary)
            }
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)

            if let refreshError {
                Section {
                    Text(refreshError)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .accessibilityLabel("Refresh error: \(refreshError)")
                }
            }

            Section("Holdings") {
                if summary.positions.isEmpty {
                    Text("No positions yet.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(summary.positions) { position in
                        PortfolioPositionRow(position: position)
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
    }
}

private struct PortfolioSummaryHeader: View {
    let summary: PortfolioSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(summary.name)
                .font(.subheadline)
                .foregroundStyle(.secondary)

            Text(summary.totalValue, format: .currency(code: summary.baseCurrency))
                .font(.system(size: 34, weight: .bold, design: .rounded))
                .minimumScaleFactor(0.6)
                .lineLimit(1)
                .accessibilityLabel("Total value \(summary.totalValue.formatted(.currency(code: summary.baseCurrency)))")

            HStack(spacing: 20) {
                metric(label: "Cash", value: summary.cashBalance, currency: summary.baseCurrency)
                metric(label: "Unrealized P/L", value: summary.unrealizedPnL, currency: summary.baseCurrency, colored: true)
                metric(label: "Realized P/L", value: summary.realizedPnL, currency: summary.baseCurrency, colored: true)
            }
        }
        .padding(.vertical, 8)
    }

    private func metric(label: String, value: Double, currency: String, colored: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value, format: .currency(code: currency))
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(colored ? (value >= 0 ? Color.green : Color.red) : Color.primary)
        }
        .accessibilityElement(children: .combine)
    }
}

private struct PortfolioPositionRow: View {
    let position: PortfolioPosition

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(position.symbol)
                    .font(.headline)
                Text("\(position.quantity.formatted()) shares")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text(position.currentValue, format: .currency(code: position.currency))
                    .font(.subheadline.weight(.medium))
                Text(pnlText)
                    .font(.caption)
                    .foregroundStyle(position.unrealizedPnL >= 0 ? Color.green : Color.red)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var pnlText: String {
        let sign = position.unrealizedPnL >= 0 ? "+" : ""
        let amount = position.unrealizedPnL.formatted(.currency(code: position.currency))
        let pct = position.unrealizedPnLPct.formatted(.number.precision(.fractionLength(2)))
        return "\(sign)\(amount) (\(sign)\(pct)%)"
    }
}
