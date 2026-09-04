import SwiftUI

/// AI Analyst — Step 6. Reached from Asset Detail ("Ask AI Analyst").
/// Presents the real Explanation Engine output for the symbol's already-
/// computed Decision Engine result (`POST /quant/analyze`'s
/// `explanation` field). There is no follow-up-question input here: the
/// backend has no endpoint that accepts free-text user input for the LLM
/// to answer (see `AIAnalystModels.swift`'s doc comment) — this screen
/// honestly stops at that integration boundary rather than fabricating
/// one.
struct AIAnalystView: View {
    let selection: AssetSelection
    let assetType: String
    @State private var viewModel: AIAnalystViewModel

    init(selection: AssetSelection, assetType: String, makeViewModel: () -> AIAnalystViewModel) {
        self.selection = selection
        self.assetType = assetType
        _viewModel = State(initialValue: makeViewModel())
    }

    var body: some View {
        content
            .navigationTitle("AI Analyst")
            .navigationBarTitleDisplayMode(.inline)
            .task { viewModel.load(symbol: selection.symbol, assetType: assetType) }
            .onDisappear { viewModel.cancel() }
    }

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .idle, .loading:
            ProgressView("Asking AI Analyst about \(selection.symbol)…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .accessibilityLabel("Loading AI Analyst explanation for \(selection.symbol)")

        case .empty:
            ContentUnavailableView(
                "No Explanation Available",
                systemImage: "text.bubble",
                description: Text("The AI Analyst has no explanation for \(selection.symbol) right now.")
            )

        case .failed(let message):
            AIAnalystErrorView(message: message) {
                viewModel.load(symbol: selection.symbol, assetType: assetType)
            }

        case .loaded(let explanation):
            AIAnalystLoadedView(explanation: explanation)
        }
    }
}

private struct AIAnalystErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Couldn't Reach AI Analyst", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button("Try Again", action: retry)
        }
    }
}

// MARK: - Loaded state

private struct AIAnalystLoadedView: View {
    let explanation: AIAnalystExplanation

    var body: some View {
        List {
            Section {
                AIAnalystContextCard(context: explanation.context)
            }
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)

            Section {
                AIAnalystMessageBubble(message: explanation.message)
            }

            if !explanation.context.evidence.isEmpty {
                Section("Evidence") {
                    EvidenceSectionView(evidence: explanation.context.evidence)
                }
            }
        }
        .listStyle(.insetGrouped)
    }
}

/// The deterministic result being explained — deliberately minimal
/// (Decision/Confidence/Return/Volatility/Risk only) since the full
/// engine-by-engine breakdown remains the Quant Analysis screen's job
/// (Section 26: don't move that content here).
private struct AIAnalystContextCard: View {
    let context: AIAnalystContext

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(context.symbol)
                    .font(.headline)
                Spacer()
                decisionBadge
            }

            HStack(spacing: 20) {
                metric(label: "Confidence", value: context.confidence)
                metric(label: "Expected Return", value: context.expectedReturn)
                metric(label: "Risk", text: context.risk.riskLevel.capitalized)
            }
        }
        .padding()
        .background(RoundedRectangle(cornerRadius: 12).fill(Color(.secondarySystemBackground)))
        .accessibilityElement(children: .combine)
    }

    private var decisionBadge: some View {
        Text(context.decision.rawValue)
            .font(.caption.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Capsule().fill(decisionColor.opacity(0.15)))
            .foregroundStyle(decisionColor)
    }

    private var decisionColor: Color {
        switch context.decision {
        case .buy: .green
        case .hold: .orange
        case .sell: .red
        }
    }

    private func metric(label: String, value: Double) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption2).foregroundStyle(.secondary)
            Text(value, format: .percent.precision(.fractionLength(0)))
                .font(.caption.weight(.semibold))
        }
    }

    private func metric(label: String, text: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption2).foregroundStyle(.secondary)
            Text(text).font(.caption.weight(.semibold))
        }
    }
}

/// One conversation turn. Role is communicated via an icon + label, not
/// color alone (Section 27).
private struct AIAnalystMessageBubble: View {
    let message: AIAnalystMessage

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(roleLabel, systemImage: roleIcon)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)

            Text(message.text)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)

            Text("Generated by OptiTrade's Explanation Engine from the Decision Engine's result — not personalized financial advice.")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(roleLabel): \(message.text)")
    }

    private var roleLabel: String {
        switch message.role {
        case .assistant: "AI Analyst"
        case .user: "You"
        }
    }

    private var roleIcon: String {
        switch message.role {
        case .assistant: "sparkles"
        case .user: "person.fill"
        }
    }
}
