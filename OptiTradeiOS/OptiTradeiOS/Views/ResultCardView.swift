import SwiftUI

struct ResultCardView: View {
    let result: AnalysisResult
    @State private var chartData: [ChartPoint] = []

    private var accentColor: Color {
        switch result.decisionCode {
        case "STRONG_BUY": return .green
        case "BUY":        return Color(red: 0.2, green: 0.75, blue: 0.3)
        case "STRONG_SELL":return .red
        case "SELL":       return Color(red: 1.0, green: 0.35, blue: 0.3)
        default:           return .orange
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 14) {
                ScoreMeter(score: result.score)

                VStack(alignment: .leading, spacing: 5) {
                    Text(result.symbol)
                        .font(.headline)
                    DecisionBadge(decisionCode: result.decisionCode, decision: result.decision)
                    RiskBadge(level: result.riskLevel)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 6) {
                    Text(formatPrice(result.indicators.currentPrice))
                        .font(.subheadline.weight(.bold))

                    Text(String(format: "%+.2f%%", result.indicators.priceVelocity))
                        .font(.caption.weight(.semibold))
                        .foregroundColor(result.indicators.priceVelocity >= 0 ? .green : .red)

                    if let rsi = result.indicators.rsi {
                        Text("RSI \(String(format: "%.0f", rsi))")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)

            if !chartData.isEmpty {
                MiniSparkline(
                    points: chartData,
                    isPositive: result.indicators.priceVelocity >= 0
                )
                .padding(.horizontal, 14)
                .padding(.bottom, 10)
                .transition(.opacity.combined(with: .move(edge: .bottom)))
            }
        }
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .task { await loadChart() }
    }

    private func loadChart() async {
        guard chartData.isEmpty else { return }
        if let chart = try? await APIService.shared.getChart(symbol: result.symbol, period: "1mo") {
            withAnimation(.easeIn(duration: 0.4)) {
                chartData = chart.points
            }
        }
    }

    private func formatPrice(_ v: Double) -> String {
        v >= 1000
            ? String(format: "%.0f", v)
            : String(format: "%.2f", v)
    }
}
