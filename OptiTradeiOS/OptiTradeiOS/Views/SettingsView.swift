import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var session:     UserSession
    @EnvironmentObject private var firebase:    FirebaseService
    @EnvironmentObject private var preferences: UserPreferences
    @AppStorage("api_base_url") private var apiURL = "http://localhost:8000"
    @State private var connectionState: ConnectionState = .idle
    @State private var showResetAlert = false
    @State private var showClearHistoryAlert = false
    @State private var showResetAccountAlert = false
    @State private var showSignOutAlert = false
    @State private var showMarketSelection = false
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
                marketSection
                profileSection
                connectionSection
                analysisSection
                appearanceSection
                dataSection
                accountActionsSection
                aboutSection
            }
            .navigationTitle("Ayarlar")
            .preferredColorScheme(preferences.appTheme.colorScheme)
            .task { await fetchMLStatus() }
            .alert("Takip listesi sıfırlansın mı?", isPresented: $showResetAlert) {
                Button("Sıfırla", role: .destructive) { session.saveWatchlist([]) }
                Button("Vazgeç", role: .cancel) {}
            }
            .alert("Arama geçmişi temizlensin mi?", isPresented: $showClearHistoryAlert) {
                Button("Temizle", role: .destructive) { session.clearSearchHistory() }
                Button("Vazgeç", role: .cancel) {}
            }
            .alert("Hesap sıfırlansın mı?", isPresented: $showResetAccountAlert) {
                Button("Sıfırla", role: .destructive) { session.resetAccount() }
                Button("Vazgeç", role: .cancel) {}
            } message: {
                Text("Tüm veriler, tercihler ve işlem geçmişi silinecek. Başlangıç ekranı yeniden gösterilecek.")
            }
            .alert("Çıkış Yap", isPresented: $showSignOutAlert) {
                Button("Çıkış Yap", role: .destructive) {
                    try? firebase.signOut()
                    session.resetAccount()
                }
                Button("Vazgeç", role: .cancel) {}
            } message: {
                Text("Hesabınızdan çıkış yapılacak. Verileriniz Firebase'de saklanmaya devam eder.")
            }
        }
    }

    // MARK: - Premium Section

    private var premiumSection: some View {
        Section {
            if session.subscriptionLevel == .trade {
                HStack {
                    Label("Trader Paketi Aktif", systemImage: "bolt.crown.fill")
                        .foregroundColor(.orange)
                    Spacer()
                    Image(systemName: "checkmark.seal.fill")
                        .foregroundColor(.orange)
                }
            } else if session.isPremium {
                HStack {
                    Label("Premium Üyelik Aktif", systemImage: "crown.fill")
                        .foregroundColor(.yellow)
                    Spacer()
                    Image(systemName: "checkmark.seal.fill")
                        .foregroundColor(.blue)
                }
            } else {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("OptiTrade Pro'ya Geç")
                                .font(.headline)
                            Text("Reklamsız deneyim, sınırsız analiz ve derinlemesine piyasa raporları.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        Image(systemImage: "crown.fill")
                            .font(.title)
                            .foregroundColor(.yellow)
                    }
                    
                    HStack {
                        Button {
                            // Satın alma işlemi
                        } label: {
                            Text("Premium Al")
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
                            Text("Trader Ol")
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
            Text("Üyelik")
        }
    }

    // MARK: - Market Section

    private var marketSection: some View {
        Section {
            Picker("Piyasa", selection: $preferences.selectedMarket) {
                ForEach(TradingMarket.allCases, id: \.self) { market in
                    HStack {
                        Text(market.flag).font(.title3)
                        Text(market.displayName)
                    }.tag(market)
                }
            }
            .onChange(of: preferences.selectedMarket) {
                preferences.setMarket($0)
            }
            .pickerStyle(.navigationLink)
            
            VStack(alignment: .leading, spacing: 4) {
                Text(preferences.selectedMarket.description)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .transition(.opacity)
            }
        } header: {
            Text("Piyasa Seçimi")
        }
    }

    // MARK: - Profile Section

    private var profileSection: some View {
        Section {
            if firebase.isAuthenticated {
                HStack {
                    Label("Hesap", systemImage: "person.crop.circle")
                    Spacer()
                    VStack(alignment: .trailing, spacing: 4) {
                        Text(firebase.currentUser?.displayName ?? "Kullanıcı")
                            .font(.subheadline.weight(.semibold))
                        Text(firebase.currentUser?.email ?? "")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            } else {
                HStack {
                    Label("Hesap", systemImage: "person.crop.circle.badge.xmark")
                    Spacer()
                    Text("Oturum açılmadı")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        } header: {
            Text("Profil")
        }
    }

    // MARK: - Connection Section

    private var connectionSection: some View {
        Section {
            HStack {
                Label("API Sunucusu", systemImage: "server.rack")
                Spacer()
                Text(apiURL == "http://localhost:8000" ? "Yerel" : "Uzak")
                    .font(.caption)
                    .foregroundColor(connectionState == .success ? .green : .orange)
            }

            Button {
                testConnection()
            } label: {
                Label("Bağlantıyı Test Et", systemImage: "network")
                    .foregroundColor(.blue)
            }
            .disabled(connectionState == .testing)
            
            HStack {
                Label("İnternet", systemImage: "wifi")
                Spacer()
                Text(session.isOnline ? "Çevrimiçi" : "Çevrimdışı")
                    .font(.caption)
                    .foregroundColor(session.isOnline ? .green : .red)
            }
        } header: {
            Text("Bağlantı")
        } footer: {
            if connectionState == .success {
                Text("Başarıyla bağlandı")
                    .foregroundColor(.green)
            } else if connectionState == .failure {
                Text("Bağlantı başarısız")
                    .foregroundColor(.red)
            }
        }
    }

    // MARK: - Analysis Section

    private var analysisSection: some View {
        Section {
            if let ml = mlStatus {
                HStack {
                    Label("Model", systemImage: "brain")
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
                    Label("Doğruluk", systemImage: "chart.bar.fill")
                    Spacer()
                    Text(ml.accuracy)
                        .font(.caption.weight(.semibold))
                        .foregroundColor(.green)
                }
            }
        } header: {
            Text("Analiz")
        }
    }

    // MARK: - Appearance Section

    private var appearanceSection: some View {
        Section {
            Picker("Tema", selection: $preferences.appTheme) {
                ForEach(AppTheme.allCases, id: \.self) { theme in
                    HStack {
                        Image(systemName: themeIcon(theme))
                        Text(theme.rawValue)
                    }
                    .tag(theme)
                }
            }
            .onChange(of: preferences.appTheme) {
                preferences.setTheme($0)
            }
            .pickerStyle(.navigationLink)
            
            Toggle("Bildirimler", isOn: $preferences.enableNotifications)
                .onChange(of: preferences.enableNotifications) {
                    preferences.save()
                    Task { await preferences.syncToFirebase() }
                }
            
            HStack {
                Label("Yenile Süresi", systemImage: "timer")
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
            Text("Görünüm & Tercihler")
        }
    }

    // MARK: - Data Section

    private var dataSection: some View {
        Section {
            Button(role: .destructive) {
                showClearHistoryAlert = true
            } label: {
                Label("Arama Geçmişini Temizle", systemImage: "clock.arrow.circlepath")
            }

            Button(role: .destructive) {
                showResetAlert = true
            } label: {
                Label("Takip Listesini Sıfırla", systemImage: "star.slash")
            }

            Button(role: .destructive) {
                preferences.hasCompletedOnboarding = false
                preferences.save()
            } label: {
                Label("Başlangıç Ekranını Tekrar Göster", systemImage: "arrow.counterclockwise")
            }

            Button(role: .destructive) {
                showResetAccountAlert = true
            } label: {
                Label("Hesabı Tamamen Sıfırla", systemImage: "trash.fill")
            }
        } header: {
            Text("Veri")
        }
    }

    @ViewBuilder
    private var accountActionsSection: some View {
        if firebase.isAuthenticated {
            Section {
                Button(role: .destructive) {
                    showSignOutAlert = true
                } label: {
                    Label("Çıkış Yap", systemImage: "rectangle.portrait.and.arrow.right")
                }
            } header: {
                Text("Hesap İşlemleri")
            } footer: {
                if let email = firebase.currentUser?.email {
                    Text("\(email) olarak giriş yapıldı")
                }
            }
        }
    }

    // MARK: - About Section

    private var aboutSection: some View {
        Section {
            HStack {
                Label("Versiyon", systemImage: "info.circle")
                Spacer()
                Text("1.0.0")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Link(destination: URL(string: "https://algorix.io")!) {
                Label("Web Sitesi", systemImage: "globe")
                    .foregroundColor(.blue)
            }
            
            Link(destination: URL(string: "https://twitter.com/algorix")!) {
                Label("Twitter", systemImage: "link")
                    .foregroundColor(.blue)
            }
        } header: {
            Text("Hakkında")
        } footer: {
            VStack(alignment: .center, spacing: 8) {
                Text("OptiTrade v1.0.0")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                Text("© 2025 Algorix — Tüm hakları saklıdır")
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
                let response = try await APIService.shared.getSessionInfo()
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
