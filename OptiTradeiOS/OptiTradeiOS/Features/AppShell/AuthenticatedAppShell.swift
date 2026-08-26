import SwiftUI

/// Proves authentication actually works end-to-end. Not the dashboard —
/// Portfolio/Watchlist/Quant/Paper Trading/etc. are separate, later tasks.
struct AuthenticatedAppShell: View {
    @State private var viewModel: AuthenticatedAppShellViewModel

    init(viewModel: AuthenticatedAppShellViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "checkmark.seal.fill")
                .font(.system(size: 44))
                .foregroundStyle(.green)
                .accessibilityHidden(true)

            Text("Signed in")
                .font(.title2.bold())

            userSection

            Spacer()

            logoutButton
        }
        .padding(24)
        .task { await viewModel.loadCurrentUserIfNeeded() }
    }

    @ViewBuilder
    private var userSection: some View {
        if viewModel.isLoadingUser {
            ProgressView()
        } else if let user = viewModel.currentUser {
            VStack(spacing: 4) {
                Text(user.displayName)
                    .font(.headline)
                Text(user.email)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Text("User ID: \(user.id)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .accessibilityElement(children: .combine)
        } else if let error = viewModel.userLoadError {
            Text(error)
                .font(.footnote)
                .foregroundStyle(.red)
        }
    }

    private var logoutButton: some View {
        Button(role: .destructive) {
            Task { await viewModel.logout() }
        } label: {
            Group {
                if viewModel.isLoggingOut {
                    ProgressView().tint(.white)
                } else {
                    Text("Log Out")
                }
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .disabled(viewModel.isLoggingOut)
        .accessibilityLabel("Log Out")
    }
}
