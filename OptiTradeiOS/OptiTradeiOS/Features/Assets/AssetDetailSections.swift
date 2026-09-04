import SwiftUI
import Charts

/// Market data header. `MarketQuote` is `nil` when `GET /price/{symbol}`
/// failed — shown as an inline "unavailable" note rather than blocking
/// the rest of the screen. Currency is never assumed: it comes from
/// `AssetSelection` when Asset Search supplied one (the backend's
/// `/price/{symbol}` itself returns no currency field), and falls back to
/// a bare, unit-less number when genuinely unknown (a Watchlist-only
/// selection, per Step 4's own honest `nil` modeling).
struct AssetHeaderView: View {
    let selection: AssetSelection
    let quote: MarketQuote?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(selection.symbol)
                .font(.largeTitle.bold())
            if let name = selection.name {
                Text(name)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            if let quote {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text(priceText(quote.price))
                        .font(.title2.weight(.semibold))
                    changeLabel(quote.changePct)
                }
            } else {
                Label("Market data unavailable", systemImage: "wifi.slash")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func priceText(_ price: Double) -> String {
        if let currency = selection.currency {
            return price.formatted(.currency(code: currency))
        }
        return price.formatted(.number.precision(.fractionLength(2)))
    }

    private func changeLabel(_ changePct: Double) -> some View {
        let isUp = changePct >= 0
        return Label(
            "\(isUp ? "+" : "")\(changePct.formatted(.number.precision(.fractionLength(2))))%",
            systemImage: isUp ? "arrow.up.right" : "arrow.down.right"
        )
        .font(.subheadline.weight(.medium))
        .foregroundStyle(isUp ? Color.green : Color.red)
    }
}

/// Basic historical price chart from `GET /chart/{symbol}`'s real data.
/// Omitted entirely by the caller when `chart` is `nil` — no fabricated
/// points are ever drawn.
struct AssetPriceChartSectionView: View {
    let chart: AssetPriceChart

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Price (\(chart.period))")
                .font(.headline)

            Chart(chart.points) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("Close", point.close)
                )
                .interpolationMethod(.monotone)
            }
            .chartXAxis(.hidden)
            .frame(height: 160)
            .accessibilityLabel("Price chart, \(chart.period), change \(chart.changePct.formatted(.number.precision(.fractionLength(2))))%")

            HStack {
                Text("Low \(chart.low.formatted(.number.precision(.fractionLength(2))))")
                Spacer()
                Text("High \(chart.high.formatted(.number.precision(.fractionLength(2))))")
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
    }
}

/// `pipeline.models.RiskAssessment` as actually returned — only
/// `riskLevel`/`expectedVolatility`/`dataSufficiency` exist at this
/// asset-level endpoint (see `RiskAssessmentDTO`'s doc comment for what's
/// genuinely not available: entry/stop-loss/take-profit/ATR).
struct RiskSectionView: View {
    let risk: RiskSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label(risk.riskLevel.capitalized, systemImage: riskIcon)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(riskColor)
                Spacer()
            }

            HStack(spacing: 20) {
                metric(label: "Expected Volatility", value: risk.expectedVolatility)
                metric(label: "Data Sufficiency", value: risk.dataSufficiency)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Risk level \(risk.riskLevel)")
    }

    private var riskIcon: String {
        switch risk.riskLevel.uppercased() {
        case "LOW": "checkmark.shield"
        case "HIGH": "exclamationmark.shield"
        default: "shield"
        }
    }

    private var riskColor: Color {
        switch risk.riskLevel.uppercased() {
        case "LOW": .green
        case "HIGH": .red
        default: .orange
        }
    }

    private func metric(label: String, value: Double) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value, format: .percent.precision(.fractionLength(0)))
                .font(.subheadline.weight(.semibold))
        }
    }
}

/// Direct presentation of the Decision Engine's own deterministic
/// evidence list — not an AI-generated explanation (Section 12).
struct EvidenceSectionView: View {
    let evidence: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(evidence, id: \.self) { line in
                Text("• \(line)")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
