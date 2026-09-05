import SwiftUI

/// "Good morning, Trader" — falls back to a neutral greeting when the
/// current user hasn't loaded yet (Section A: never block Dashboard
/// rendering on the user's name).
struct DashboardHeaderView: View {
    let displayName: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(DashboardGreeting.salutation(hour: Calendar.current.component(.hour, from: Date())))
                .font(.title2.bold())
            if let displayName {
                Text(displayName)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

/// Compact Portfolio summary card — same fields and currency handling as
/// `PortfolioView`'s own header (Step 3), just condensed for the
/// Dashboard. P/L is never communicated by color alone (Section 13):
/// "Gain"/"Loss" text always accompanies the color.
struct DashboardPortfolioSummaryCard: View {
    let summary: PortfolioSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(summary.totalValue, format: .currency(code: summary.baseCurrency))
                .font(.title2.weight(.semibold))
                .accessibilityLabel("Total value \(summary.totalValue.formatted(.currency(code: summary.baseCurrency)))")

            HStack(spacing: 20) {
                metric(label: "Cash", value: summary.cashBalance, currency: summary.baseCurrency)
                pnlMetric(label: "Unrealized", value: summary.unrealizedPnL, currency: summary.baseCurrency)
                pnlMetric(label: "Realized", value: summary.realizedPnL, currency: summary.baseCurrency)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func metric(label: String, value: Double, currency: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value, format: .currency(code: currency)).font(.subheadline.weight(.medium))
        }
    }

    private func pnlMetric(label: String, value: Double, currency: String) -> some View {
        let isGain = value >= 0
        return VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value, format: .currency(code: currency))
                .font(.subheadline.weight(.medium))
                .foregroundStyle(isGain ? Color.green : Color.red)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(label) \(isGain ? "gain" : "loss") \(value.formatted(.currency(code: currency)))")
    }
}

/// Shared section-level error presentation — safe, user-facing text only
/// (never raw backend JSON/HTTP internals), with a retry action.
struct DashboardSectionErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(message, systemImage: "exclamationmark.triangle")
                .font(.footnote)
                .foregroundStyle(.secondary)
            Button("Try Again", action: retry)
                .font(.footnote)
        }
    }
}
