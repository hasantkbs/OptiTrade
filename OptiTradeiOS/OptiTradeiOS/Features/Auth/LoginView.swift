import SwiftUI

struct LoginView: View {
    private enum Field: Hashable {
        case email
        case password
    }

    @State private var viewModel: LoginViewModel
    @FocusState private var focusedField: Field?

    init(viewModel: LoginViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                header

                VStack(alignment: .leading, spacing: 16) {
                    emailField
                    passwordField
                }

                if let authError = viewModel.authError {
                    Text(authError)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .multilineTextAlignment(.center)
                        .accessibilityLabel("Login error: \(authError)")
                }

                loginButton
            }
            .padding(24)
            .frame(maxWidth: 420)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private var header: some View {
        VStack(spacing: 8) {
            Image(systemName: "chart.line.uptrend.xyaxis")
                .font(.system(size: 44))
                .foregroundStyle(.tint)
                .accessibilityHidden(true)
            Text("OptiTrade")
                .font(.largeTitle.bold())
        }
        .padding(.top, 40)
    }

    private var emailField: some View {
        VStack(alignment: .leading, spacing: 4) {
            TextField("Email", text: $viewModel.email)
                .textContentType(.username)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .focused($focusedField, equals: .email)
                .submitLabel(.next)
                .onSubmit { focusedField = .password }
                .textFieldStyle(.roundedBorder)
                .disabled(viewModel.isLoading)
                .accessibilityLabel("Email")

            if viewModel.validationError == .emptyEmail {
                Text("Please enter your email.")
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
    }

    private var passwordField: some View {
        VStack(alignment: .leading, spacing: 4) {
            SecureField("Password", text: $viewModel.password)
                .textContentType(.password)
                .focused($focusedField, equals: .password)
                .submitLabel(.go)
                .onSubmit(submit)
                .textFieldStyle(.roundedBorder)
                .disabled(viewModel.isLoading)
                .accessibilityLabel("Password")

            if viewModel.validationError == .emptyPassword {
                Text("Please enter your password.")
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
    }

    private var loginButton: some View {
        Button(action: submit) {
            Group {
                if viewModel.isLoading {
                    ProgressView()
                        .tint(.white)
                } else {
                    Text("Log In")
                }
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .disabled(viewModel.isLoginButtonDisabled)
        .accessibilityLabel("Log In")
        .accessibilityHint(viewModel.isLoading ? "Logging in" : "")
    }

    private func submit() {
        Task { await viewModel.login() }
    }
}
