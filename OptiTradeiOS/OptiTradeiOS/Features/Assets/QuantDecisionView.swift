import SwiftUI

/// The Decision Engine's single, aggregated result. Deliberately visually
/// separate from `EngineVoteRow` below it — Section 9's "make the
/// distinction between ENGINE VOTES and FINAL DECISION very clear."
struct QuantDecisionCardView: View {
    let quant: QuantAnalysis

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                decisionBadge
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("Confidence")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(quant.confidence, format: .percent.precision(.fractionLength(0)))
                        .font(.headline)
                }
            }

            HStack(spacing: 24) {
                metric(label: "Expected Return", value: quant.expectedReturn, colored: true)
                metric(label: "Expected Volatility", value: quant.expectedVolatility, colored: false)
            }

            if quant.degraded {
                Label(
                    "Degraded analysis — \(quant.enginesSucceeded) of \(quant.enginesAvailable) engines succeeded",
                    systemImage: "exclamationmark.triangle"
                )
                .font(.caption)
                .foregroundStyle(.orange)
            }
        }
        .padding()
        .background(RoundedRectangle(cornerRadius: 12).fill(Color(.secondarySystemBackground)))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Decision Engine result: \(decisionLabel), confidence \(quant.confidence.formatted(.percent.precision(.fractionLength(0))))")
    }

    private var decisionBadge: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("Decision Engine")
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack(spacing: 6) {
                Image(systemName: decisionIcon)
                Text(decisionLabel)
                    .font(.title.bold())
            }
            .foregroundStyle(decisionColor)
        }
    }

    private var decisionLabel: String {
        switch quant.decision {
        case .buy: "BUY"
        case .hold: "HOLD"
        case .sell: "SELL"
        }
    }

    private var decisionIcon: String {
        switch quant.decision {
        case .buy: "arrow.up.circle.fill"
        case .hold: "minus.circle.fill"
        case .sell: "arrow.down.circle.fill"
        }
    }

    private var decisionColor: Color {
        switch quant.decision {
        case .buy: .green
        case .hold: .orange
        case .sell: .red
        }
    }

    private func metric(label: String, value: Double, colored: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value, format: .percent.precision(.fractionLength(1)))
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(colored ? (value >= 0 ? Color.green : Color.red) : Color.primary)
        }
        .accessibilityElement(children: .combine)
    }
}

/// One engine's vote — clearly a *vote*, not the final decision. Handles
/// every `EngineExecutionStatus`, including a non-`success` engine whose
/// prediction/confidence/etc. are genuinely absent (Section 19: never
/// backfilled with a zero or a fake neutral value).
struct EngineVoteRow: View {
    let vote: EngineVoteSummary

    var body: some View {
        HStack {
            Text(vote.displayName)
                .font(.subheadline.weight(.medium))

            Spacer()

            switch vote.status {
            case .success:
                if let prediction = vote.prediction {
                    voteBadge(prediction)
                    if let confidence = vote.confidence {
                        Text(confidence, format: .percent.precision(.fractionLength(0)))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            case .timeout:
                statusLabel("Timed Out", systemImage: "clock.badge.exclamationmark")
            case .failed:
                statusLabel("Unavailable", systemImage: "exclamationmark.circle")
            case .invalid:
                statusLabel("Invalid", systemImage: "questionmark.circle")
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func voteBadge(_ prediction: QuantDecision) -> some View {
        Text(prediction.rawValue)
            .font(.caption.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Capsule().fill(color(for: prediction).opacity(0.15)))
            .foregroundStyle(color(for: prediction))
    }

    private func color(for prediction: QuantDecision) -> Color {
        switch prediction {
        case .buy: .green
        case .hold: .orange
        case .sell: .red
        }
    }

    private func statusLabel(_ text: String, systemImage: String) -> some View {
        Label(text, systemImage: systemImage)
            .font(.caption)
            .foregroundStyle(.secondary)
    }
}

/// Full detail for one engine (Technical, Fundamental, or News — the row
/// is generic since all three share the same `EngineVoteSummary` shape).
/// Shown only when the engine actually has evidence or a vote to show;
/// callers skip rendering this entirely for a `nil` vote rather than
/// showing an empty section.
struct EngineDetailSectionView: View {
    let title: String
    let vote: EngineVoteSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            EngineVoteRow(vote: vote)

            if vote.status == .success, let expectedReturn = vote.expectedReturn, let volatility = vote.volatility {
                HStack(spacing: 16) {
                    Text("Return \(expectedReturn.formatted(.percent.precision(.fractionLength(1))))")
                    Text("Volatility \(volatility.formatted(.percent.precision(.fractionLength(1))))")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            if !vote.evidence.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(vote.evidence, id: \.self) { line in
                        Text("• \(line)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}
