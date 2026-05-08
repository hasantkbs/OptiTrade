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
                        Image(systemName: "crown.fill")
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
                                .foregroundColor(.black)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                        }
                    }
                }
                .padding(.vertical, 4)
            }
        } header: {
            Text("Üyelik Durumu")
        }
    }

    // MARK: - Market Section

    private var marketSection: some View {
        Section {
            HStack {
                Text(preferences.selectedMarket.flag)
                    .font(.title2)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Aktif Piyasa")
                        .font(.subheadline.weight(.medium))
                    Text(preferences.selectedMarket.displayName)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                Spacer()
                Button("Değiştir") {
                    showMarketSelection = true
                }
                .font(.subheadline)
                .foregroundColor(.blue)
            }
            .padding(.vertical, 2)
        } header: {
            Text("Piyasa Tercihi")
        } footer: {
            Text("Haber filtresi, arama önerileri ve varsayılan izleme listesi bu tercihle yapılandırılır.")
                .font(.caption)
        }
        .sheet(isPresented: $showMarketSelection) {
            MarketSelectionView(isOnboarding: false)
        }
    }

    // MARK: - Profile Section

    private var profileSection: some View {
        Section {
            HStack(spacing: 14) {
                ZStack {
                    Circle()
                        .fill(Color.accentColor.opacity(0.2))
                        .frame(width: 52, height: 52)
                    Image(systemName: session.isGuestMode ? "person.slash.fill" : "person.fill")
                        .font(.title2)
                        .foregroundColor(.accentColor)
                }
                VStack(alignment: .leading, spacing: 4) {
                    if session.isGuestMode {
                        Text("Misafir Kullanıcı")
                            .font(.headline)
                        Text("Giriş yapılmamış")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Text(session.displayName.isEmpty ? "Kullanıcı" : session.displayName)
                            .font(.headline)
                        Text(session.userEmail.isEmpty ? "OptiTrade Kullanıcısı" : session.userEmail)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .padding(.vertical, 4)

            HStack {
                Text("İsim")
                Spacer()
                TextField("Adınız (opsiyonel)", text: $session.displayName)
                    .multilineTextAlignment(.trailing)
                    .foregroundColor(.secondary)
            }

            HStack {
                Text("E-posta")
                Spacer()
                TextField("E-posta (opsiyonel)", text: $session.userEmail)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .multilineTextAlignment(.trailing)
                    .foregroundColor(.secondary)
            }

            if let date = session.disclaimerAcceptedAt {
                HStack {
                    Label("Risk Uyarısı Onaylandı", systemImage: "checkmark.shield.fill")
                        .foregroundColor(.green)
                    Spacer()
                    Text(date, style: .date)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        } header: {
            Text("Hesap")
        }
    }

    private var connectionSection: some View {
        Section {
            VStack(alignment: .leading, spacing: 8) {
                Text("Backend URL")
                    .font(.caption)
                    .foregroundColor(.secondary)
                TextField("http://localhost:8000", text: $apiURL)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .disableAutocorrection(true)
                    .font(.system(.body, design: .monospaced))
                    .onChange(of: apiURL) { APIService.shared.baseURL = apiURL }
            }
            .padding(.vertical, 2)

            Button {
                testConnection()
            } label: {
                HStack {
                    if connectionState == .testing {
                        ProgressView().tint(.accentColor)
                    } else {
                        Image(systemName: connectionState == .success ? "checkmark.circle.fill" :
                              connectionState == .failure ? "xmark.circle.fill" : "antenna.radiowaves.left.and.right")
                            .foregroundColor(connectionState == .success ? .green :
                                            connectionState == .failure ? .red : .accentColor)
                    }
                    Text(connectionState == .success ? "Bağlantı Başarılı" :
                         connectionState == .failure ? "Bağlanamadı" :
                         connectionState == .testing ? "Test ediliyor..." : "Bağlantıyı Test Et")
                }
            }
            .disabled(connectionState == .testing)
        } header: {
            Text("Bağlantı")
        } footer: {
            Text("Sunucu adresi değiştirildiğinde analiz verileri bu adresten çekilir.")
        }
    }

    private var analysisSection: some View {
        Section {
            Picker("Varsayılan Varlık Tipi", selection: $session.defaultAssetType) {
                Text("Hisse Senedi").tag("stock")
                Text("Kripto Para").tag("crypto")
            }

            Toggle("Taramada Nötr Sinyalleri Göster", isOn: $session.showNeutralInScan)
        } header: {
            Text("Analiz Tercihleri")
        } footer: {
            Text("Nötr sinyaller kapatılırsa tarama sayfasında yalnızca AL/SAT sonuçları görünür.")
        }
    }

    private var appearanceSection: some View {
        Section {
            Picker("Tema", selection: $session.appTheme) {
                ForEach(AppTheme.allCases, id: \.self) { theme in
                    Label(theme.label, systemImage: themeIcon(theme))
                        .tag(theme)
                }
            }
            .pickerStyle(.navigationLink)
        } header: {
            Text("Görünüm")
        }
    }

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
                session.onboardingDone = false
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

    private func fetchMLStatus() async {
        guard let url = URL(string: APIService.shared.baseURL + "/ml/status") else { return }
        guard let (data, _) = try? await URLSession.shared.data(from: url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        let name     = json["model_name"]    as? String ?? "XGBoost"
        let accuracy = json["test_accuracy"] as? Double ?? 0
        let version  = json["version"]       as? String ?? "—"
        await MainActor.run {
            mlStatus = MLStatusInfo(
                modelName: name,
                accuracy: String(format: "%.1f%%", accuracy * 100),
                version: version
            )
        }
    }

    @ViewBuilder
    private var aboutSection: some View {
        Section {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color.accentColor.opacity(0.15))
                        .frame(width: 44, height: 44)
                    Image(systemName: "chart.line.uptrend.xyaxis.circle.fill")
                        .font(.title2)
                        .foregroundColor(.accentColor)
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text("OptiTrade")
                        .font(.headline)
                    Text("Product by Algorix")
                        .font(.caption.weight(.semibold))
                        .foregroundColor(.accentColor)
                        .tracking(0.8)
                }
            }
            .padding(.vertical, 4)

            HStack {
                Text("Versiyon")
                Spacer()
                Text("3.1.0 (Build \(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1"))")
                    .foregroundColor(.secondary)
            }
            HStack {
                Text("Analiz Motoru")
                Spacer()
                Text("OptiTrade v3.1")
                    .foregroundColor(.secondary)
            }
            HStack {
                Text("ML Model")
                Spacer()
                if let ml = mlStatus {
                    Text("\(ml.modelName) — \(ml.accuracy)")
                        .foregroundColor(.secondary)
                } else {
                    ProgressView().scaleEffect(0.7)
                }
            }
            HStack {
                Text("Backtest Doğruluğu")
                Spacer()
                if let ml = mlStatus {
                    Text(ml.accuracy)
                        .foregroundColor(.secondary)
                } else {
                    Text("—").foregroundColor(.secondary)
                }
            }
        } header: {
            Text("Hakkında")
        }

        Section {
            Link(destination: URL(string: "https://algorix.io/privacy")!) {
                HStack {
                    Label("Gizlilik Politikası", systemImage: "hand.raised.fill")
                    Spacer()
                    Image(systemName: "arrow.up.right")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            Link(destination: URL(string: "https://algorix.io/terms")!) {
                HStack {
                    Label("Kullanım Koşulları", systemImage: "doc.text.fill")
                    Spacer()
                    Image(systemName: "arrow.up.right")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            Link(destination: URL(string: "mailto:support@algorix.io")!) {
                HStack {
                    Label("Destek & İletişim", systemImage: "envelope.fill")
                    Spacer()
                    Image(systemName: "arrow.up.right")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        } header: {
            Text("Algorix")
        }

        Section {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundColor(.orange)
                    Text("Yatırım Tavsiyesi Değildir")
                        .font(.caption.weight(.bold))
                        .foregroundColor(.orange)
                }
                Text("OptiTrade, teknik analiz göstergeleri aracılığıyla bilgi sunar. Uygulama içeriği hiçbir koşulda yatırım tavsiyesi, alım-satım önerisi veya finansal danışmanlık hizmeti niteliği taşımaz.\n\nTüm yatırım kararları kullanıcının kendi sorumluluğundadır. Algorix, kullanıcıların uygulamadan elde ettiği bilgilere dayanarak aldıkları kararlar sonucunda oluşabilecek kayıp ve zararlardan sorumlu tutulamaz.\n\nGeçmiş performans verileri ve backtest sonuçları gelecekteki başarıyı garanti etmez.")
                    .font(.caption2)
                    .foregroundColor(.secondary)

                if let date = session.disclaimerAcceptedAt {
                    HStack(spacing: 6) {
                        Image(systemName: "checkmark.shield.fill")
                            .font(.caption2)
                            .foregroundColor(.green)
                        Text("Risk bildirimi \(date.formatted(date: .abbreviated, time: .omitted)) tarihinde onaylandı.")
                            .font(.caption2)
                            .foregroundColor(.green.opacity(0.8))
                    }
                    .padding(.top, 4)
                }
            }
            .padding(.vertical, 6)
        } header: {
            Text("Yasal Uyarı")
        }
    }

    private func testConnection() {
        connectionState = .testing
        APIService.shared.baseURL = apiURL
        Task {
            do {
                let url = URL(string: apiURL + "/health")!
                let (_, response) = try await URLSession.shared.data(from: url)
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                await MainActor.run {
                    connectionState = (200...299).contains(code) ? .success : .failure
                }
            } catch {
                await MainActor.run { connectionState = .failure }
            }
        }
    }

    private func themeIcon(_ theme: AppTheme) -> String {
        switch theme {
        case .system: return "circle.lefthalf.filled"
        case .dark:   return "moon.fill"
        case .light:  return "sun.max.fill"
        }
    }
}
