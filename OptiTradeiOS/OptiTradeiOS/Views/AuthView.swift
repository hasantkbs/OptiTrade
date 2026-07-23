import SwiftUI
import AuthenticationServices
import FirebaseAuth

// ─────────────────────────────────────────────────────────────────────────────
// MARK: - Auth View (Login / Register)
// ─────────────────────────────────────────────────────────────────────────────

struct AuthView: View {
    @EnvironmentObject private var firebase: FirebaseService
    @EnvironmentObject private var session: UserSession
    @State private var isLogin = true
    @State private var email = ""
    @State private var password = ""
    @State private var displayName = ""
    @State private var confirmPassword = ""
    @State private var errorMessage: String?
    @State private var showResetAlert = false
    @State private var resetSent = false
    @State private var currentNonce: String?

    var body: some View {
        ZStack {
            // Background gradient
            LinearGradient(
                colors: [Color(hex: "0A0E1A"), Color(hex: "0D1B2A"), Color(hex: "1A1A2E")],
                startPoint: .topLeading, endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            ScrollView {
                VStack(spacing: 28) {
                    // Logo
                    VStack(spacing: 8) {
                        Image(systemName: "chart.line.uptrend.xyaxis.circle.fill")
                            .font(.system(size: 64))
                            .foregroundStyle(
                                LinearGradient(colors: [.cyan, .blue], startPoint: .top, endPoint: .bottom)
                            )
                        Text("OptiTrade")
                            .font(.system(size: 32, weight: .bold, design: .rounded))
                            .foregroundColor(.white)
                        Text(L("Akilli Borsa Analiz Platformu"))
                            .font(.subheadline)
                            .foregroundColor(.white.opacity(0.5))
                    }
                    .padding(.top, 60)

                    // Tab selector
                    HStack(spacing: 0) {
                        tabButton(title: L("Giris Yap"), selected: isLogin) { isLogin = true }
                        tabButton(title: L("Kayit Ol"), selected: !isLogin) { isLogin = false }
                    }
                    .background(Color.white.opacity(0.07))
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .padding(.horizontal)

                    // Form card
                    VStack(spacing: 16) {
                        if !isLogin {
                            authField(icon: "person.fill", placeholder: L("Ad Soyad"), text: $displayName)
                        }
                        authField(icon: "envelope.fill", placeholder: L("E-posta"), text: $email)
                            .keyboardType(.emailAddress)
                            .autocorrectionDisabled()
                            .textInputAutocapitalization(.never)

                        authSecureField(icon: "lock.fill", placeholder: L("Sifre"), text: $password)

                        if !isLogin {
                            authSecureField(icon: "lock.shield.fill", placeholder: L("Sifre Tekrar"), text: $confirmPassword)
                        }

                        if let err = errorMessage {
                            HStack {
                                Image(systemName: "exclamationmark.triangle.fill")
                                Text(err)
                                    .font(.caption)
                            }
                            .foregroundColor(.red.opacity(0.9))
                            .padding(10)
                            .background(Color.red.opacity(0.1))
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                        }

                        // Submit button
                        Button(action: handleAuth) {
                            HStack {
                                if firebase.isLoading {
                                    ProgressView()
                                        .tint(.black)
                                } else {
                                    Text(isLogin ? L("Giris Yap") : L("Hesap Olustur"))
                                        .fontWeight(.semibold)
                                }
                            }
                            .frame(maxWidth: .infinity)
                            .frame(height: 52)
                            .background(
                                LinearGradient(colors: [.cyan, .blue], startPoint: .leading, endPoint: .trailing)
                            )
                            .foregroundColor(.black)
                            .clipShape(RoundedRectangle(cornerRadius: 14))
                        }
                        .disabled(firebase.isLoading)

                        // OR Divider
                        HStack {
                            Rectangle().fill(Color.white.opacity(0.1)).frame(height: 1)
                            Text(L("VEYA")).font(.caption2).foregroundColor(.white.opacity(0.3))
                            Rectangle().fill(Color.white.opacity(0.1)).frame(height: 1)
                        }
                        .padding(.vertical, 8)

                        // Apple Sign In
                        SignInWithAppleButton(
                            onRequest: { request in
                                let nonce = String.randomNonceString()
                                currentNonce = nonce
                                request.requestedScopes = [.email, .fullName]
                                request.nonce = nonce.sha256()
                            },
                            onCompletion: { result in
                                handleAppleSignIn(result)
                            }
                        )
                        .signInWithAppleButtonStyle(.white)
                        .frame(height: 50)
                        .clipShape(RoundedRectangle(cornerRadius: 14))

                        if isLogin {
                            Button(L("Sifremi Unuttum")) { showResetAlert = true }
                                .font(.footnote)
                                .foregroundColor(.cyan.opacity(0.8))
                        }
                    }
                    .padding(20)
                    .background(Color.white.opacity(0.05))
                    .clipShape(RoundedRectangle(cornerRadius: 20))
                    .padding(.horizontal)

                    // Guest mode button
                    Button {
                        withAnimation {
                            session.isGuestMode = true
                        }
                    } label: {
                        Text(L("Misafir Olarak Devam Et"))
                            .font(.subheadline)
                            .foregroundColor(.white.opacity(0.6))
                    }
                    .padding(.top, 4)

                    // Disclaimer
                    Text(L("OptiTrade yatirim tavsiyesi vermez. Butun kararlar kullaniciya aittir."))
                        .font(.caption2)
                        .foregroundColor(.white.opacity(0.3))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 32)
                        .padding(.bottom, 32)
                }
            }
        }
        .alert(L("Sifre Sifirlama"), isPresented: $showResetAlert) {
            Button(L("Gonder")) { sendReset() }
            Button(L("Iptal"), role: .cancel) {}
        } message: {
            Text(resetSent ? L("Sifre sifirlama maili gonderildi.") : "\(email) \(L("adresine sifre sifirlama maili gonderilecek."))")
        }
    }

    // ── Helpers ────────────────────────────────────────────────────────────────

    private func handleAppleSignIn(_ result: Result<ASAuthorization, Error>) {
        switch result {
        case .success(let auth):
            if let appleID = auth.credential as? ASAuthorizationAppleIDCredential {
                guard let token = appleID.identityToken,
                      let tokenStr = String(data: token, encoding: .utf8),
                      let nonce = currentNonce else { return }
                
                let credential = OAuthProvider.appleCredential(
                    withIDToken: tokenStr,
                    rawNonce: nonce,
                    fullName: appleID.fullName
                )
                
                Task {
                    do {
                        try await firebase.signInWithApple(credential: credential)
                    } catch {
                        errorMessage = error.localizedDescription
                    }
                }
            }
        case .failure(let error):
            errorMessage = error.localizedDescription
        }
    }

    private func handleAuth() {
        errorMessage = nil
        if email.isEmpty || password.isEmpty {
            errorMessage = L("E-posta ve sifre bos birakilamaz.")
            return
        }
        if !isLogin {
            guard password == confirmPassword else {
                errorMessage = L("Sifreler eslesmiyor.")
                return
            }
            guard password.count >= 6 else {
                errorMessage = L("Sifre en az 6 karakter olmalidir.")
                return
            }
        }
        Task {
            do {
                if isLogin {
                    try await firebase.signIn(email: email, password: password)
                } else {
                    try await firebase.signUp(email: email, password: password, displayName: displayName)
                }
            } catch {
                errorMessage = localizedAuthError(error)
            }
        }
    }

    private func sendReset() {
        Task {
            do {
                try await firebase.sendPasswordReset(email: email)
                resetSent = true
            } catch {
                errorMessage = L("Sifre sifirlama maili gonderilemedi.")
            }
        }
    }

    private func localizedAuthError(_ error: Error) -> String {
        let code = (error as NSError).code
        switch code {
        case 17011: return L("Bu e-posta ile kayitli hesap bulunamadi.")
        case 17009: return L("Sifre yanlis. Lutfen tekrar deneyin.")
        case 17007: return L("Bu e-posta zaten kullanilmaktadir.")
        case 17026: return L("Sifre cok zayif. En az 6 karakter girin.")
        default: return error.localizedDescription
        }
    }

    @ViewBuilder
    private func tabButton(title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .frame(maxWidth: .infinity)
                .frame(height: 40)
                .background(selected ? Color.cyan.opacity(0.25) : Color.clear)
                .foregroundColor(selected ? .cyan : .white.opacity(0.5))
                .clipShape(RoundedRectangle(cornerRadius: 10))
        }
    }

    @ViewBuilder
    private func authField(icon: String, placeholder: String, text: Binding<String>) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .foregroundColor(.cyan.opacity(0.7))
                .frame(width: 20)
            TextField(placeholder, text: text)
                .foregroundColor(.white)
                .tint(.cyan)
        }
        .padding(14)
        .background(Color.white.opacity(0.07))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    @ViewBuilder
    private func authSecureField(icon: String, placeholder: String, text: Binding<String>) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .foregroundColor(.cyan.opacity(0.7))
                .frame(width: 20)
            SecureField(placeholder, text: text)
                .foregroundColor(.white)
                .tint(.cyan)
        }
        .padding(14)
        .background(Color.white.opacity(0.07))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
