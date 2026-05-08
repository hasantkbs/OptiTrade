import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject private var session: UserSession
    @EnvironmentObject private var preferences: UserPreferences
    @AppStorage("api_base_url") private var apiURL = "http://localhost:8000"
    @State private var page = 0
    @State private var disclaimerChecked = false
    @State private var apiTestState: APITestState = .idle

    enum APITestState { case idle, testing, success, failure }

    private let totalPages = 4

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            TabView(selection: $page) {
                welcomePage.tag(0)
                disclaimerPage.tag(1)
                apiSetupPage.tag(2)
                loginPage.tag(3)
            }
            .tabViewStyle(.page(indexDisplayMode: .never))
            .animation(.easeInOut, value: page)

            VStack {
                Spacer()
                pageIndicator
                    .padding(.bottom, 32)
            }
        }
        .preferredColorScheme(.dark)
    }

    private var pageIndicator: some View {
        HStack(spacing: 8) {
            ForEach(0..<totalPages, id: \.self) { i in
                Capsule()
                    .fill(i == page ? Color.accentColor : Color.gray.opacity(0.4))
                    .frame(width: i == page ? 20 : 8, height: 8)
                    .animation(.spring(response: 0.3), value: page)
            }
        }
    }

    private var welcomePage: some View {
        VStack(spacing: 0) {
            Spacer()
            VStack(spacing: 24) {
                ZStack {
                    Circle()
                        .fill(Color.accentColor.opacity(0.15))
                        .frame(width: 120, height: 120)
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .font(.system(size: 52))
                        .foregroundColor(.accentColor)
                }

                VStack(spacing: 8) {
                    Text("OptiTrade")
                        .font(.system(size: 38, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                    Text("Hisse Senedi & Kripto\nAnaliz Asistanı")
                        .font(.title3)
                        .foregroundColor(.gray)
                        .multilineTextAlignment(.center)
                    Text("Product by Algorix")
                        .font(.caption.weight(.semibold))
                        .foregroundColor(.accentColor.opacity(0.8))
                        .tracking(1.5)
                        .textCase(.uppercase)
                }

                VStack(spacing: 14) {
                    featureRow(icon: "waveform.path.ecg", title: "Teknik Analiz", subtitle: "RSI, MACD, Bollinger Bands")
                    featureRow(icon: "chart.bar.xaxis", title: "Piyasa Taraması", subtitle: "BIST ve kripto tüm piyasaları tara")
                    featureRow(icon: "star.fill", title: "Takip Listesi", subtitle: "Favori sembollerini kaydet ve takip et")
                }
                .padding(.horizontal, 32)

                Text("Bu uygulama yatırım tavsiyesi vermez.")
                    .font(.caption2)
                    .foregroundColor(.orange.opacity(0.8))
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }
            Spacer()
            nextButton(title: "Başla") { page = 1 }
                .padding(.horizontal, 32)
                .padding(.bottom, 80)
        }
    }

    private var disclaimerPage: some View {
        VStack(spacing: 0) {
            VStack(spacing: 16) {
                ZStack {
                    Circle()
                        .fill(Color.orange.opacity(0.15))
                        .frame(width: 90, height: 90)
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 40))
                        .foregroundColor(.orange)
                }
                .padding(.top, 52)

                Text("Yasal Uyarı & Risk Bildirimi")
                    .font(.title2.bold())
                    .foregroundColor(.white)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)

                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        disclaimerBlock(
                            icon: "xmark.shield.fill", color: .red,
                            title: "Yatırım Tavsiyesi Değildir",
                            body: "OptiTrade uygulaması (\"Uygulama\") yalnızca teknik gösterge ve algoritma çıktıları sunar. Uygulama içindeki hiçbir içerik, sinyal, analiz veya öneri; yatırım tavsiyesi, portföy yönetimi önerisi veya aracılık hizmeti niteliği taşımaz."
                        )
                        disclaimerBlock(
                            icon: "person.fill.questionmark", color: .orange,
                            title: "Kullanıcı Sorumluluğu",
                            body: "Tüm yatırım kararları tamamen kullanıcıya aittir. Algorix ve OptiTrade, uygulamadan elde edilen bilgiler doğrultusunda gerçekleştirilen işlemlerden doğabilecek herhangi bir kayıp, zarar veya finansal sonuçtan sorumlu tutulamaz."
                        )
                        disclaimerBlock(
                            icon: "clock.arrow.2.circlepath", color: .yellow,
                            title: "Geçmiş Performans Garantisi Yoktur",
                            body: "Geçmiş analiz doğruluğu veya backtest sonuçları, gelecekteki performansı garanti etmez. Piyasa koşulları öngörülemeyen şekillerde değişebilir."
                        )
                        disclaimerBlock(
                            icon: "chart.line.downtrend.xyaxis", color: .red,
                            title: "Yüksek Risk",
                            body: "Hisse senedi ve kripto para piyasalarında işlem yapmak ciddi finansal risk içerir. Yatırım yapmadan önce bir finansal danışmana başvurmanız tavsiye edilir."
                        )
                        disclaimerBlock(
                            icon: "building.columns.fill", color: .blue,
                            title: "Düzenleyici Uyarı",
                            body: "Uygulama hiçbir ülkede düzenleyici kurumlar (SPK, BDDK, SEC vb.) tarafından lisanslı finansal hizmet sağlayıcısı değildir."
                        )
                    }
                    .padding(.horizontal, 24)
                    .padding(.vertical, 8)
                }
                .frame(maxHeight: 340)
                .background(Color.white.opacity(0.04))
                .clipShape(RoundedRectangle(cornerRadius: 16))
                .padding(.horizontal, 16)

                Button {
                    withAnimation { disclaimerChecked.toggle() }
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: disclaimerChecked ? "checkmark.square.fill" : "square")
                            .font(.title3)
                            .foregroundColor(disclaimerChecked ? .green : .gray)
                        Text("Yukarıdaki uyarıları okudum, anladım ve kabul ediyorum.")
                            .font(.subheadline.weight(.medium))
                            .foregroundColor(.white)
                            .multilineTextAlignment(.leading)
                    }
                    .padding(.horizontal, 24)
                    .padding(.vertical, 14)
                    .background(disclaimerChecked ? Color.green.opacity(0.12) : Color.white.opacity(0.07))
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(disclaimerChecked ? Color.green.opacity(0.4) : Color.clear, lineWidth: 1)
                    )
                }
                .padding(.horizontal, 16)
            }

            Spacer()
            nextButton(title: "Devam Et", disabled: !disclaimerChecked) {
                session.disclaimerAccepted = true
                page = 2
            }
            .padding(.horizontal, 32)
            .padding(.bottom, 80)
        }
    }

    private func disclaimerBlock(icon: String, color: Color, title: String, body: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .font(.subheadline)
                .foregroundColor(color)
                .frame(width: 22)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundColor(.white)
                Text(body)
                    .font(.caption)
                    .foregroundColor(.gray)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var apiSetupPage: some View {
        VStack(spacing: 0) {
            Spacer()
            VStack(spacing: 24) {
                ZStack {
                    Circle()
                        .fill(Color.blue.opacity(0.15))
                        .frame(width: 100, height: 100)
                    Image(systemName: "server.rack")
                        .font(.system(size: 40))
                        .foregroundColor(.blue)
                }

                Text("Sunucu Bağlantısı")
                    .font(.title.bold())
                    .foregroundColor(.white)

                Text("OptiTrade'in çalışması için analiz sunucusuna ihtiyaç vardır. Lokal veya uzak sunucu adresini girin.")
                    .font(.subheadline)
                    .foregroundColor(.gray)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)

                VStack(spacing: 12) {
                    TextField("http://localhost:8000", text: $apiURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .disableAutocorrection(true)
                        .padding(14)
                        .background(Color.white.opacity(0.07))
                        .foregroundColor(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(Color.white.opacity(0.1), lineWidth: 1)
                        )

                    Button {
                        testConnection()
                    } label: {
                        HStack(spacing: 8) {
                            if apiTestState == .testing {
                                ProgressView().tint(.white)
                            } else {
                                Image(systemName: apiTestState == .success ? "checkmark.circle.fill" :
                                      apiTestState == .failure ? "xmark.circle.fill" : "antenna.radiowaves.left.and.right")
                                    .foregroundColor(apiTestState == .success ? .green :
                                                    apiTestState == .failure ? .red : .white)
                            }
                            Text(apiTestState == .success ? "Bağlantı Başarılı" :
                                 apiTestState == .failure ? "Bağlanamadı" :
                                 apiTestState == .testing ? "Test ediliyor..." : "Bağlantıyı Test Et")
                                .font(.subheadline.weight(.medium))
                                .foregroundColor(.white)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(14)
                        .background(Color.white.opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .disabled(apiTestState == .testing)
                }
                .padding(.horizontal, 32)
            }
            Spacer()
            nextButton(title: "Devam Et") {
                APIService.shared.baseURL = apiURL
                page = 3
            }
            .padding(.horizontal, 32)
            .padding(.bottom, 80)
        }
    }

    private var loginPage: some View {
        VStack(spacing: 0) {
            Spacer()
            VStack(spacing: 24) {
                ZStack {
                    Circle()
                        .fill(Color.accentColor.opacity(0.15))
                        .frame(width: 100, height: 100)
                    Image(systemName: "person.crop.circle.fill")
                        .font(.system(size: 44))
                        .foregroundColor(.accentColor)
                }

                Text("Hazırsınız!")
                    .font(.title.bold())
                    .foregroundColor(.white)

                Text("OptiTrade'i kullanmaya başlamak için giriş yapın veya yeni hesap oluşturun.\n\nVerileriniz tüm cihazlarınızda Firebase ile senkronize edilir.")
                    .font(.subheadline)
                    .foregroundColor(.gray)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)

                VStack(spacing: 10) {
                    featureRow(icon: "icloud.fill",      title: "Bulut Senkronizasyonu", subtitle: "Watchlist ve işlemler her cihazda")
                    featureRow(icon: "lock.shield.fill", title: "Güvenli Giriş",         subtitle: "Firebase Authentication koruması")
                    featureRow(icon: "star.fill",        title: "Kişisel Takip Listesi", subtitle: "Hesabınıza özel favori semboller")
                }
                .padding(.horizontal, 32)
            }
            Spacer()

            VStack(spacing: 12) {
                nextButton(title: "Giriş Yap / Kayıt Ol") {
                    session.isGuestMode = false
                    session.onboardingDone = true
                }

                Button {
                    session.isGuestMode = true
                    session.onboardingDone = true
                } label: {
                    Text("Misafir Olarak Devam Et")
                        .font(.subheadline)
                        .foregroundColor(.gray)
                        .padding(.vertical, 8)
                }
            }
            .padding(.horizontal, 32)
            .padding(.bottom, 80)
        }
    }

    private func testConnection() {
        apiTestState = .testing
        APIService.shared.baseURL = apiURL
        Task {
            do {
                let url = URL(string: apiURL + "/health")!
                let (_, response) = try await URLSession.shared.data(from: url)
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                await MainActor.run {
                    apiTestState = (200...299).contains(code) ? .success : .failure
                }
            } catch {
                await MainActor.run { apiTestState = .failure }
            }
        }
    }

    private func nextButton(title: String, disabled: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.headline)
                .foregroundColor(.black)
                .frame(maxWidth: .infinity)
                .padding(16)
                .background(disabled ? Color.gray : Color.accentColor)
                .clipShape(RoundedRectangle(cornerRadius: 14))
        }
        .disabled(disabled)
    }

    private func featureRow(icon: String, title: String, subtitle: String) -> some View {
        HStack(spacing: 16) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundColor(.accentColor)
                .frame(width: 36)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundColor(.white)
                Text(subtitle)
                    .font(.caption)
                    .foregroundColor(.gray)
            }
            Spacer()
        }
    }
}

struct MarketSelectionView: View {
    @EnvironmentObject var preferences: UserPreferences
    var isOnboarding: Bool = false
    var onComplete: (() -> Void)? = nil
    @State private var selectedMarket: TradingMarket = .tr
    @State private var isSaving = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            Color(hex: "#0A0E1A").ignoresSafeArea()
            VStack(spacing: 0) {
                VStack(spacing: 8) {
                    if isOnboarding {
                        Text("OptiTrade'e\nHoş Geldiniz")
                            .font(.system(size: 32, weight: .bold))
                            .foregroundColor(.white)
                            .multilineTextAlignment(.center)
                        Text("Hangi piyasada işlem yapıyorsunuz?")
                            .font(.subheadline)
                            .foregroundColor(.gray)
                    } else {
                        Text("Piyasa Seçimi")
                            .font(.title2.bold())
                            .foregroundColor(.white)
                        Text("Haber filtresi ve arama bu tercihle yapılandırılır")
                            .font(.caption)
                            .foregroundColor(.gray)
                    }
                }
                .padding(.top, isOnboarding ? 60 : 24)
                .padding(.bottom, 40)
                VStack(spacing: 16) {
                    ForEach(TradingMarket.allCases, id: \.self) { market in
                        MarketCard(market: market, isSelected: selectedMarket == market) {
                            withAnimation(.spring(response: 0.3)) { selectedMarket = market }
                        }
                    }
                }
                .padding(.horizontal, 24)
                if selectedMarket == .crypto {
                    HStack(spacing: 8) {
                        Image(systemName: "info.circle").foregroundColor(.blue)
                        Text("Kripto piyasası 7/24 globaldir. Haber filtresi otomatik uygulanır.")
                            .font(.caption).foregroundColor(.gray)
                    }
                    .padding(12).background(Color.blue.opacity(0.08)).cornerRadius(10)
                    .padding(.horizontal, 24).padding(.top, 12)
                }
                Spacer()
                Button { save() } label: {
                    if isSaving {
                        ProgressView().tint(.black).frame(maxWidth: .infinity).frame(height: 54)
                    } else {
                        Text(isOnboarding ? "Devam Et" : "Kaydet")
                            .font(.headline).foregroundColor(.black).frame(maxWidth: .infinity).frame(height: 54)
                    }
                }
                .background(LinearGradient(colors: [Color(hex: "#00D4FF"), Color(hex: "#0094FF")], startPoint: .leading, endPoint: .trailing))
                .cornerRadius(14).padding(.horizontal, 24).padding(.bottom, isOnboarding ? 50 : 24).disabled(isSaving)
            }
        }
        .onAppear { selectedMarket = preferences.selectedMarket }
    }

    private func save() {
        isSaving = true
        if isOnboarding { preferences.completeOnboarding(market: selectedMarket) }
        else { preferences.setMarket(selectedMarket) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
            isSaving = false
            onComplete?()
            if !isOnboarding { dismiss() }
        }
    }
}

private struct MarketCard: View {
    let market: TradingMarket
    let isSelected: Bool
    let onTap: () -> Void
    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 16) {
                Text(market.flag).font(.system(size: 32)).frame(width: 52, height: 52).background(Color.white.opacity(0.06)).cornerRadius(12)
                VStack(alignment: .leading, spacing: 4) {
                    Text(market.displayName).font(.headline).foregroundColor(.white)
                    Text(market.description).font(.caption).foregroundColor(.gray).lineLimit(2)
                    HStack(spacing: 4) {
                        Image(systemName: "chart.line.uptrend.xyaxis").font(.caption2).foregroundColor(accentColor)
                        Text(market.indexName).font(.caption2.weight(.medium)).foregroundColor(accentColor)
                    }
                }
                Spacer()
                ZStack {
                    Circle().stroke(isSelected ? accentColor : Color.gray.opacity(0.3), lineWidth: 2).frame(width: 24, height: 24)
                    if isSelected { Circle().fill(accentColor).frame(width: 14, height: 14) }
                }
            }
            .padding(16).background(RoundedRectangle(cornerRadius: 16).fill(isSelected ? accentColor.opacity(0.12) : Color.white.opacity(0.05))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(isSelected ? accentColor.opacity(0.6) : Color.clear, lineWidth: 1.5)))
        }
        .buttonStyle(.plain)
    }
    private var accentColor: Color {
        switch market {
        case .tr: return Color(hex: "#FF4444")
        case .us: return Color(hex: "#4488FF")
        case .jp: return Color(hex: "#FFCC00")
        case .crypto: return Color(hex: "#F7931A")
        }
    }
}

struct MarketBadge: View {
    let market: TradingMarket
    var body: some View {
        HStack(spacing: 4) {
            Text(market.flag).font(.caption2)
            Text(market.rawValue).font(.caption2.weight(.semibold)).foregroundColor(badgeColor)
        }
        .padding(.horizontal, 8).padding(.vertical, 3).background(badgeColor.opacity(0.12)).cornerRadius(6)
    }
    private var badgeColor: Color {
        switch market {
        case .tr: return Color(hex: "#FF4444")
        case .us: return Color(hex: "#4488FF")
        case .jp: return Color(hex: "#FFCC00")
        case .crypto: return Color(hex: "#F7931A")
        }
    }
}

@MainActor
final class SectorViewModel: ObservableObject {
    @Published var sectors: [SectorOverview] = []
    @Published var isLoading = false
    @Published var error: String?
    @Published var topOpportunity: SectorsResponse.TopOpportunity?

    func load(market: TradingMarket) async {
        guard market != .crypto else { sectors = []; return }
        isLoading = true; error = nil
        defer { isLoading = false }
        do {
            let response = try await APIService.shared.getSectorsOverview(market: market)
            sectors = response.sectors
            topOpportunity = response.topOpportunity
        } catch { self.error = error.localizedDescription }
    }
}

struct SectorOpportunityView: View {
    @EnvironmentObject var preferences: UserPreferences
    @StateObject private var vm = SectorViewModel()
    @State private var selectedSector: SectorOverview?
    var body: some View {
        ZStack {
            Color(hex: "#0A0E1A").ignoresSafeArea()
            if preferences.selectedMarket == .crypto { cryptoMessage }
            else if vm.isLoading { loadingView }
            else if let err = vm.error { errorView(err) }
            else { mainContent }
        }
        .navigationTitle("Sektör Analizi")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load(market: preferences.selectedMarket) }
        .sheet(item: $selectedSector) { sector in SectorDetailSheet(sector: sector) }
    }
    private var mainContent: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                if let top = vm.topOpportunity, let score = top.score, score >= 60 { opportunityBanner(top) }
                HStack {
                    MarketBadge(market: preferences.selectedMarket)
                    Text("\(vm.sectors.count) sektör").font(.caption).foregroundColor(.gray)
                    Spacer()
                }.padding(.horizontal, 20)
                ForEach(vm.sectors) { sector in
                    SectorCard(sector: sector).onTapGesture { selectedSector = sector }.padding(.horizontal, 16)
                }
            }.padding(.bottom, 30)
        }.refreshable { await vm.load(market: preferences.selectedMarket) }
    }
    private func opportunityBanner(_ top: SectorsResponse.TopOpportunity) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Text("🎯").font(.title2)
                VStack(alignment: .leading, spacing: 2) {
                    Text("En Yüksek Fırsat").font(.caption.weight(.semibold)).foregroundColor(Color(hex: "#00FF88").opacity(0.8))
                    Text(top.nameTr ?? top.sector ?? "").font(.headline.bold()).foregroundColor(.white)
                }
                Spacer()
                if let score = top.score { Text("\(Int(score))").font(.title2.bold()).foregroundColor(Color(hex: "#00FF88")) }
            }
        }.padding(16).background(Color(hex: "#00FF88").opacity(0.08)).cornerRadius(14).padding(.horizontal, 16)
    }
    private var loadingView: some View { ProgressView().tint(.blue) }
    private func errorView(_ msg: String) -> some View { Text(msg).foregroundColor(.red) }
    private var cryptoMessage: some View { Text("Kripto piyasasında sektör ayrımı yoktur").foregroundColor(.gray) }
}

struct SectorCard: View {
    let sector: SectorOverview
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                Text(sector.icon).font(.title2).frame(width: 44, height: 44).background(Color.white.opacity(0.06)).cornerRadius(10)
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(sector.nameTr).font(.headline).foregroundColor(.white)
                        Text(sector.trendEmoji)
                        Spacer()
                        Text(sector.risk).font(.caption2.weight(.semibold)).foregroundColor(sector.riskColor).padding(.horizontal, 6).padding(.vertical, 2).background(sector.riskColor.opacity(0.12)).cornerRadius(5)
                    }
                    Text(sector.description).font(.caption).foregroundColor(.gray).lineLimit(1)
                }
            }
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(sector.opportunityLabel).font(.caption.weight(.semibold)).foregroundColor(sector.scoreColor)
                    Spacer()
                    Text("\(Int(sector.opportunityScore))/100").font(.caption.weight(.bold)).foregroundColor(sector.scoreColor)
                }
                ScoreProgressBar(score: sector.opportunityScore, color: sector.scoreColor)
            }
        }.padding(14).background(Color.white.opacity(0.04)).cornerRadius(14)
    }
}

struct ScoreProgressBar: View {
    let score: Double
    let color: Color
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 4).fill(Color.white.opacity(0.08))
                RoundedRectangle(cornerRadius: 4).fill(color).frame(width: geo.size.width * min(1, score / 100))
            }
        }.frame(height: 6)
    }
}

struct SectorDetailSheet: View {
    let sector: SectorOverview
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationView {
            ZStack {
                Color(hex: "#0A0E1A").ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        Text(sector.nameTr).font(.title.bold()).foregroundColor(.white).padding()
                        Text(sector.advice).foregroundColor(.white.opacity(0.8)).padding()
                        Spacer()
                    }
                }
            }.toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Kapat") { dismiss() } } }
        }
    }
}
