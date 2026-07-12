import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var session:     UserSession
    @EnvironmentObject private var firebase:    FirebaseService
    @EnvironmentObject private var preferences: UserPreferences
    @EnvironmentObject private var localization: LocalizationManager
    @AppStorage("api_base_url") private var apiURL = "http://localhost:8000"
    @State private var connectionState: ConnectionState = .idle
    @State private var showResetAlert = false
    @State private var showClearHistoryAlert = false
    @State private var showResetAccountAlert = false
    @State private var showSignOutAlert = false
    @State private var mlStatus: MLStatusInfo?

    struct MLStatusInfo {
        let modelName: String
        let accuracy: String
        let version: String
    }

    enum ConnectionState { case idle, testing, success, failure }

    var body: some View {
        NavigationStack {
            Form {
                premiumSection
                newsSection
                profileSection
                connectionSection
                analysisSection
                appearanceSection
                dataSection
                accountActionsSection
                aboutSection
            }
            .navigationTitle(L("Ayarlar"))
            .preferredColorScheme(session.appTheme.colorScheme)
            .task { await fetchMLStatus() }
            .alert(L("Takip listesi sıfırlansın mı?"), isPresented: $showResetAlert) {
                Button(L("Sıfırla"), role: .destructive) { session.saveWatchlist([]) }
                Button(L("Vazgeç"), role: .cancel) {}
            }
            .alert(L("Arama geçmişi temizlensin mi?"), isPresented: $showClearHistoryAlert) {
                Button(L("Temizle"), role: .destructive) { session.clearSearchHistory() }
                Button(L("Vazgeç"), role: .cancel) {}
            }
            .alert(L("Hesap sıfırlansın mı?"), isPresented: $showResetAccountAlert) {
                Button(L("Sıfırla"), role: .destructive) { session.resetAccount() }
                Button(L("Vazgeç"), role: .cancel) {}
            } message: {
                Text(L("Tüm veriler, tercihler ve işlem geçmişi silinecek. Başlangıç ekranı yeniden gösterilecek."))
            }
            .alert(L("Çıkış Yap"), isPresented: $showSignOutAlert) {
                Button(L("Çıkış Yap"), role: .destructive) {
                    try? firebase.signOut()
                    session.resetAccount()
                }
                Button(L("Vazgeç"), role: .cancel) {}
            } message: {
                Text(L("Hesabınızdan çıkış yapılacak. Verileriniz Firebase'de saklanmaya devam eder."))
            }
        }
    }

    // MARK: - Premium Section

    private var premiumSection: some View {
        Section {
            if session.subscriptionLevel == .trade {
                HStack {
                    Label(L("Trader Paketi Aktif"), systemImage: "bolt.crown.fill")
                        .foregroundColor(.orange)
                    Spacer()
                    Image(systemName: "checkmark.seal.fill")
                        .foregroundColor(.orange)
                }
            } else if session.isPremium {
                HStack {
                    Label(L("Premium Üyelik Aktif"), systemImage: "crown.fill")
                        .foregroundColor(.yellow)
                    Spacer()
                    Image(systemName: "checkmark.seal.fill")
                        .foregroundColor(.blue)
                }
            } else {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(L("OptiTrade Pro'ya Geç"))
                                .font(.headline)
                            Text(L("Reklamsız deneyim, sınırsız analiz ve derinlemesine piyasa raporları."))
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        Image(systemName: "crown.fill")
                            .font(.title)
                            .foregroundColor(.yellow)
                    }
                    
                    HStack {
                        Button {
                            // Satın alma işlemi
                        } label: {
                            Text(L("Premium Al"))
                                .font(.subheadline.weight(.bold))
                                .frame(maxWidth: .infinity)
                                .frame(height: 38)
                                .background(Color.yellow)
                                .foregroundColor(.black)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                        }
                        
                        Button {
                            // Trader paketi
                        } label: {
                            Text(L("Trader Ol"))
                                .font(.subheadline.weight(.bold))
                                .frame(maxWidth: .infinity)
                                .frame(height: 38)
                                .background(Color.orange)
                                .foregroundColor(.white)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                        }
                    }
                }
            }
        } header: {
            Text(L("Üyelik"))
        }
    }

    // MARK: - News Section

    private var newsSection: some View {
        Section {
            NavigationLink {
                MarketNewsView()
            } label: {
                Label(L("Piyasa Haberleri"), systemImage: "newspaper.fill")
            }
        }
    }

    // MARK: - Profile Section

    private var profileSection: some View {
        Section {
            if firebase.isAuthenticated {
                HStack {
                    Label(L("Hesap"), systemImage: "person.crop.circle")
                    Spacer()
                    VStack(alignment: .trailing, spacing: 4) {
                        Text(firebase.currentUser?.displayName ?? L("Kullanıcı"))
                            .font(.subheadline.weight(.semibold))
                        Text(firebase.currentUser?.email ?? "")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            } else {
                HStack {
                    Label(L("Hesap"), systemImage: "person.crop.circle.badge.xmark")
                    Spacer()
                    Text(L("Oturum açılmadı"))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        } header: {
            Text(L("Profil"))
        }
    }

    // MARK: - Connection Section

    private var connectionSection: some View {
        Section {
            HStack {
                Label(L("API Sunucusu"), systemImage: "server.rack")
                Spacer()
                Text(apiURL == "http://localhost:8000" ? L("Yerel") : L("Uzak"))
                    .font(.caption)
                    .foregroundColor(connectionState == .success ? .green : .orange)
            }

            Button {
                testConnection()
            } label: {
                Label(L("Bağlantıyı Test Et"), systemImage: "network")
                    .foregroundColor(.blue)
            }
            .disabled(connectionState == .testing)

            HStack {
                Label(L("İnternet"), systemImage: "wifi")
                Spacer()
                Text(session.isOnline ? L("Çevrimiçi") : L("Çevrimdışı"))
                    .font(.caption)
                    .foregroundColor(session.isOnline ? .green : .red)
            }
        } header: {
            Text(L("Bağlantı"))
        } footer: {
            if connectionState == .success {
                Text(L("Başarıyla bağlandı"))
                    .foregroundColor(.green)
            } else if connectionState == .failure {
                Text(L("Bağlantı başarısız"))
                    .foregroundColor(.red)
            }
        }
    }

    // MARK: - Analysis Section

    private var analysisSection: some View {
        Section {
            if let ml = mlStatus {
                HStack {
                    Label(L("Model"), systemImage: "brain")
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(ml.modelName)
                            .font(.caption.weight(.semibold))
                        Text("v\(ml.version)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }

                HStack {
                    Label(L("Doğruluk"), systemImage: "chart.bar.fill")
                    Spacer()
                    Text(ml.accuracy)
                        .font(.caption.weight(.semibold))
                        .foregroundColor(.green)
                }
            }
        } header: {
            Text(L("Analiz"))
        }
    }

    // MARK: - Appearance Section

    private var appearanceSection: some View {
        Section {
            Picker(L("Tema"), selection: $session.appTheme) {
                ForEach(AppTheme.allCases, id: \.self) { theme in
                    HStack {
                        Image(systemName: themeIcon(theme))
                        Text(theme.label)
                    }
                    .tag(theme)
                }
            }
            .onChange(of: session.appTheme) { _, newValue in
                session.setTheme(newValue)
            }
            .pickerStyle(.navigationLink)

            Picker(L("Dil"), selection: $localization.language) {
                ForEach(AppLanguage.allCases, id: \.self) { lang in
                    HStack {
                        Text(lang.flag)
                        Text(lang.displayName)
                    }
                    .tag(lang)
                }
            }
            .pickerStyle(.navigationLink)

            Toggle(L("Bildirimler"), isOn: $preferences.enableNotifications)
                .onChange(of: preferences.enableNotifications) {
                    preferences.save()
                    Task { await preferences.syncToFirebase() }
                }

            HStack {
                Label(L("Yenile Süresi"), systemImage: "timer")
                Spacer()
                Picker("", selection: $preferences.refreshInterval) {
                    ForEach([1, 2, 5, 10, 30], id: \.self) { interval in
                        Text("\(interval) dk").tag(interval)
                    }
                }
                .onChange(of: preferences.refreshInterval) {
                    preferences.save()
                    Task { await preferences.syncToFirebase() }
                }
                .pickerStyle(.navigationLink)
            }
        } header: {
            Text(L("Görünüm & Tercihler"))
        }
    }

    // MARK: - Data Section

    private var dataSection: some View {
        Section {
            Button(role: .destructive) {
                showClearHistoryAlert = true
            } label: {
                Label(L("Arama Geçmişini Temizle"), systemImage: "clock.arrow.circlepath")
            }

            Button(role: .destructive) {
                showResetAlert = true
            } label: {
                Label(L("Takip Listesini Sıfırla"), systemImage: "star.slash")
            }

            Button(role: .destructive) {
                preferences.hasCompletedOnboarding = false
                preferences.save()
            } label: {
                Label(L("Başlangıç Ekranını Tekrar Göster"), systemImage: "arrow.counterclockwise")
            }

            Button(role: .destructive) {
                showResetAccountAlert = true
            } label: {
                Label(L("Hesabı Tamamen Sıfırla"), systemImage: "trash.fill")
            }
        } header: {
            Text(L("Veri"))
        }
    }

    @ViewBuilder
    private var accountActionsSection: some View {
        if firebase.isAuthenticated {
            Section {
                Button(role: .destructive) {
                    showSignOutAlert = true
                } label: {
                    Label(L("Çıkış Yap"), systemImage: "rectangle.portrait.and.arrow.right")
                }
            } header: {
                Text(L("Hesap İşlemleri"))
            } footer: {
                if let email = firebase.currentUser?.email {
                    Text("\(email) \(L("olarak giriş yapıldı"))")
                }
            }
        }
    }

    // MARK: - About Section

    private var aboutSection: some View {
        Section {
            HStack {
                Label(L("Versiyon"), systemImage: "info.circle")
                Spacer()
                Text("1.0.0")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Link(destination: URL(string: "https://algorixstudio.com")!) {
                Label(L("Web Sitesi"), systemImage: "globe")
                    .foregroundColor(.blue)
            }

            Link(destination: URL(string: "https://privacy.algorixstudio.com")!) {
                Label(L("Gizlilik Politikası"), systemImage: "hand.raised")
                    .foregroundColor(.blue)
            }

            Link(destination: URL(string: "https://x.com/algorixstudio")!) {
                Label("X", systemImage: "link")
                    .foregroundColor(.blue)
            }
        } header: {
            Text(L("Hakkında"))
        } footer: {
            VStack(alignment: .center, spacing: 8) {
                Text("OptiTrade v1.0.0")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                Text(L("© 2025 AlgorixStudio — Tüm hakları saklıdır"))
                    .font(.caption2)
                    .foregroundColor(.secondary.opacity(0.6))
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
        }
    }

    // MARK: - Helpers

    private func testConnection() {
        connectionState = .testing
        Task {
            do {
                _ = try await APIService.shared.getSessionInfo()
                withAnimation {
                    connectionState = .success
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                    connectionState = .idle
                }
            } catch {
                withAnimation {
                    connectionState = .failure
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                    connectionState = .idle
                }
            }
        }
    }

    private func themeIcon(_ theme: AppTheme) -> String {
        switch theme {
        case .system: return "gearshape.fill"
        case .light: return "sun.max.fill"
        case .dark: return "moon.stars.fill"
        }
    }

    private func fetchMLStatus() async {
        guard let url = URL(string: APIService.shared.baseURL + "/ml/status") else { return }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let decoded = try JSONDecoder().decode([String: String].self, from: data)
            mlStatus = MLStatusInfo(
                modelName: decoded["model"] ?? "XGBoost",
                accuracy: decoded["accuracy"] ?? "—",
                version: decoded["version"] ?? "1.0"
            )
        } catch {
            mlStatus = nil
        }
    }
}
