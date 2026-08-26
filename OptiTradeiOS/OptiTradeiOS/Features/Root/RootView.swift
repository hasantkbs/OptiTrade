import SwiftUI

/// The app's canonical authentication boundary. Branches purely on the one
/// shared `SessionManager.state` — there is no separate navigation state to
/// keep in sync with it.
struct RootView: View {
    let sessionManager: SessionManager
    let makeLoginViewModel: () -> LoginViewModel
    let makeShellViewModel: () -> AuthenticatedAppShellViewModel
    let makePortfolioViewModel: () -> PortfolioViewModel

    var body: some View {
        Group {
            switch sessionManager.state {
            case .restoring:
                LaunchLoadingView()
            case .unauthenticated:
                LoginView(viewModel: makeLoginViewModel())
            case .authenticated:
                AuthenticatedAppShell(shellViewModel: makeShellViewModel(), makePortfolioViewModel: makePortfolioViewModel)
            }
        }
        .task { await sessionManager.restoreSession() }
    }
}

/// Shown only while `SessionManager` is checking for a stored session, so
/// there's never a visible flash of `LoginView` on a warm launch.
private struct LaunchLoadingView: View {
    var body: some View {
        ProgressView("Starting OptiTrade…")
    }
}
