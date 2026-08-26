import SwiftUI

/// Minimal launch screen proving the foundation works end-to-end. Deliberately
/// unstyled — real feature screens (Dashboard, Portfolio, Watchlist, …) are
/// separate, later tasks and are not implemented here.
struct RootView: View {
    @State private var viewModel: RootViewModel

    init(viewModel: RootViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        VStack(spacing: 12) {
            switch viewModel.status {
            case .launching:
                ProgressView("Starting OptiTrade…")

            case .ready(let environment, let sessionState):
                Image(systemName: "checkmark.seal")
                    .font(.largeTitle)
                Text("OptiTrade foundation ready")
                    .font(.headline)
                Text("Environment: \(environment.rawValue)")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                Text("Session: \(String(describing: sessionState))")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .task { await viewModel.start() }
    }
}
