import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject private var session: UserSession
    @EnvironmentObject private var preferences: UserPreferences
    @AppStorage("api_base_url") private var apiURL = "https://api.optitrade.app"
    @State private var page = 0
    @State private var disclaimerChecked = false
    @State private var apiTestState: APITestState = .idle
    @State private var animateGlow = false

    enum APITestState { case idle, testing, success, failure }

    private let totalPages = 4

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            ZStack {
                Circle()
                    .fill(Color.accentColor.opacity(0.12))
                    .frame(width: 400, height: 400)
                    .blur(radius: 80)
                    .offset(x: animateGlow ? -100 : 100, y: animateGlow ? -150 : 150)

                Circle()
                    .fill(Color.blue.opacity(0.1))
                    .frame(width: 300, height: 300)
                    .blur(radius: 60)
                    .offset(x: animateGlow ? 150 : -150, y: animateGlow ? 200 : -200)
            }
            .animation(.easeInOut(duration: 8).repeatForever(autoreverses: true), value: animateGlow)
            .onAppear { animateGlow = true }

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
                    .fill(i == page ? Color.accentColor : Color.gray.opacity(0.3))
                    .frame(width: i == page ? 24 : 8, height: 6)
                    .animation(.spring(response: 0.35, dampingFraction: 0.7), value: page)
            }
        }
    }

    private var welcomePage: some View {
        VStack(spacing: 0) {
            Spacer()
            VStack(spacing: 28) {
                ZStack {
                    Circle()
                        .stroke(Color.accentColor.opacity(0.3), lineWidth: 1)
                        .frame(width: 140, height: 140)
                        .scaleEffect(animateGlow ? 1.1 : 0.95)
                        .opacity(animateGlow ? 0.3 : 0.7)

                    Circle()
                        .fill(
                            RadialGradient(colors: [Color.accentColor.opacity(0.2), .clear], center: .center, startRadius: 0, endRadius: 70)
                        )
                        .frame(width: 140, height: 140)

                    Image(systemName: "chart.line.uptrend.xyaxis.circle.fill")
                        .font(.system(size: 72))
                        .foregroundStyle(
                            LinearGradient(colors: [Color.accentColor, .white], startPoint: .topLeading, endPoint: .bottomTrailing)
                        )
                        .shadow(color: Color.accentColor.opacity(0.5), radius: 10)
                }

                VStack(spacing: 12) {
                    Text("OptiTrade")
                        .font(.system(size: 42, weight: .black, design: .rounded))
                        .foregroundColor(.white)
                    Text(L("Hisse Senedi & Kripto\nAnaliz Asistanı"))
                        .font(.title3)
                        .foregroundColor(.gray)
                        .multilineTextAlignment(.center)
                    Text("Product by AlgorixStudio")
                        .font(.caption.weight(.semibold))
                        .foregroundColor(.accentColor.opacity(0.8))
                        .tracking(1.5)
                        .textCase(.uppercase)
                }

                VStack(spacing: 16) {
                    premiumFeatureRow(icon: "cpu.fill", title: "V2 ICT Analiz", subtitle: "Algoritmik sinyaller ve ICT modelleri")
                    premiumFeatureRow(icon: "brain.head.profile.fill", title: "Yapay Zeka", subtitle: "%64+ başarı oranlı XGBoost modeli")
                    premiumFeatureRow(icon: "chart.bar.xaxis", title: "Küresel Erişim", subtitle: "BIST, NASDAQ ve Kripto tek ekranda")
                }
                .padding(.horizontal, 32)

                Text(L("Bu uygulama yatırım tavsiyesi vermez."))
                    .font(.caption2)
                    .foregroundColor(.orange.opacity(0.8))
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }

            Spacer()

            nextButton(title: "Deneyimi Başlat") {
                withAnimation { page = 1 }
            }
            .padding(.horizontal, 40)
            .padding(.bottom, 60)
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

                Text(L("Yasal Uyarı & Risk Bildirimi"))
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
                            body: "Tüm yatırım kararları tamamen kullanıcıya aittir. AlgorixStudio ve OptiTrade, uygulamadan elde edilen bilgiler doğrultusunda gerçekleştirilen işlemlerden doğabilecek herhangi bir kayıp, zarar veya finansal sonuçtan sorumlu tutulamaz."
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
                        Text(L("Yukarıdaki uyarıları okudum, anladım ve kabul ediyorum."))
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
            nextButton(title: "Anladım ve Devam Et", disabled: !disclaimerChecked) {
                session.disclaimerAccepted = true
                withAnimation { page = 2 }
            }
            .padding(.horizontal, 32)
            .padding(.bottom, 80)
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

                Text(L("Sunucu Bağlantısı"))
                    .font(.title.bold())
                    .foregroundColor(.white)

                Text(L("OptiTrade'in çalışması için analiz sunucusuna ihtiyaç vardır. Lokal veya uzak sunucu adresini girin."))
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
                            Text(apiTestState == .success ? L("Bağlantı Başarılı") :
                                 apiTestState == .failure ? L("Bağlanamadı") :
                                 apiTestState == .testing ? L("Test ediliyor...") : L("Bağlantıyı Test Et"))
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
                withAnimation { page = 3 }
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

                Text(L("Hazırsınız!"))
                    .font(.title.bold())
                    .foregroundColor(.white)

                Text(L("OptiTrade kullanıma hazır!\n\nVerileriniz tüm cihazlarınızda Firebase ile senkronize edilir."))
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

            nextButton(title: "Başla") {
                session.onboardingDone = true
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
            Text(L(title))
                .font(.headline)
                .foregroundColor(.black)
                .frame(maxWidth: .infinity)
                .frame(height: 56)
                .background(disabled ? Color.gray.opacity(0.5) : Color.accentColor)
                .cornerRadius(28)
                .shadow(color: disabled ? .clear : Color.accentColor.opacity(0.3), radius: 10, y: 5)
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
                Text(L(title))
                    .font(.subheadline.weight(.semibold))
                    .foregroundColor(.white)
                Text(L(subtitle))
                    .font(.caption)
                    .foregroundColor(.gray)
            }
            Spacer()
        }
    }

    private func premiumFeatureRow(icon: String, title: String, subtitle: String) -> some View {
        HStack(spacing: 16) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundColor(.accentColor)
                .frame(width: 40)

            VStack(alignment: .leading, spacing: 2) {
                Text(L(title))
                    .font(.subheadline.weight(.semibold))
                    .foregroundColor(.white)
                Text(L(subtitle))
                    .font(.caption)
                    .foregroundColor(.gray)
            }
            Spacer()
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
                Text(L(title))
                    .font(.subheadline.weight(.semibold))
                    .foregroundColor(.white)
                Text(L(body))
                    .font(.caption)
                    .foregroundColor(.gray)
                    .fixedSize(horizontal: false, vertical: true)
            }
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
                        Text(L("OptiTrade'e\nHoş Geldiniz"))
                            .font(.system(size: 32, weight: .bold))
                            .foregroundColor(.white)
                            .multilineTextAlignment(.center)
                        Text(L("Hangi piyasada işlem yapıyorsunuz?"))
                            .font(.subheadline)
                            .foregroundColor(.gray)
                    } else {
                        Text(L("Piyasa Seçimi"))
                            .font(.title2.bold())
                            .foregroundColor(.white)
                        Text(L("Haber filtresi ve arama bu tercihle yapılandırılır"))
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
                        Text(L("Kripto piyasası 7/24 globaldir. Haber filtresi otomatik uygulanır."))
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
                        Text(isOnboarding ? L("Devam Et") : L("Kaydet"))
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
                    Text(L(market.displayName)).font(.headline).foregroundColor(.white)
                    Text(L(market.description)).font(.caption).foregroundColor(.gray).lineLimit(2)
                    HStack(spacing: 4) {
                        Image(systemName: "chart.line.uptrend.xyaxis").font(.caption2).foregroundColor(accentColor)
                        Text(L(market.indexName)).font(.caption2.weight(.medium)).foregroundColor(accentColor)
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
        .navigationTitle(L("Sektör Analizi"))
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
                    Text("\(vm.sectors.count) \(L("sektör"))").font(.caption).foregroundColor(.gray)
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
                    Text(L("En Yüksek Fırsat")).font(.caption.weight(.semibold)).foregroundColor(Color(hex: "#00FF88").opacity(0.8))
                    Text(L(top.nameTr ?? top.sector ?? "")).font(.headline.bold()).foregroundColor(.white)
                }
                Spacer()
                if let score = top.score { Text("\(Int(score))").font(.title2.bold()).foregroundColor(Color(hex: "#00FF88")) }
            }
        }.padding(16).background(Color(hex: "#00FF88").opacity(0.08)).cornerRadius(14).padding(.horizontal, 16)
    }
    private var loadingView: some View { ProgressView().tint(.blue) }
    private func errorView(_ msg: String) -> some View { Text(msg).foregroundColor(.red) }
    private var cryptoMessage: some View { Text(L("Kripto piyasasında sektör ayrımı yoktur")).foregroundColor(.gray) }
}

struct SectorCard: View {
    let sector: SectorOverview
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                Text(sector.icon).font(.title2).frame(width: 44, height: 44).background(Color.white.opacity(0.06)).cornerRadius(10)
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(L(sector.nameTr)).font(.headline).foregroundColor(.white)
                        Text(sector.trendEmoji)
                        Spacer()
                        Text(L(sector.riskLabel)).font(.caption2.weight(.semibold)).foregroundColor(sector.riskColor).padding(.horizontal, 6).padding(.vertical, 2).background(sector.riskColor.opacity(0.12)).cornerRadius(5)
                    }
                    Text(L(sector.description)).font(.caption).foregroundColor(.gray).lineLimit(1)
                }
            }
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(L(sector.opportunityLabel)).font(.caption.weight(.semibold)).foregroundColor(sector.scoreColor)
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

@MainActor
final class SectorNewsViewModel: ObservableObject {
    @Published var response: TopicNewsResponse?
    @Published var isLoading = false

    func load(query: String) async {
        isLoading = true
        response = try? await APIService.shared.fetchTopicNews(query: query)
        isLoading = false
    }
}

struct SectorDetailSheet: View {
    let sector: SectorOverview
    @Environment(\.dismiss) private var dismiss
    @StateObject private var newsVM = SectorNewsViewModel()

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text(L(sector.nameTr)).font(.title.bold()).foregroundColor(.primary).padding()
                    Text(sector.advice).foregroundColor(.secondary).padding(.horizontal)

                    sectorNewsSection
                }
            }
            .background(Color(.systemBackground).ignoresSafeArea())
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button(L("Kapat")) { dismiss() } } }
            .task { await newsVM.load(query: sector.nameTr) }
        }
    }

    @ViewBuilder
    private var sectorNewsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(L("İlgili Haberler"))
                .font(.headline)
                .padding(.horizontal)

            if newsVM.isLoading {
                HStack { Spacer(); ProgressView(); Spacer() }
                    .padding()
            } else if let headlines = newsVM.response?.headlines, !headlines.isEmpty {
                VStack(spacing: 0) {
                    ForEach(headlines) { headline in
                        HStack(alignment: .top, spacing: 10) {
                            Circle()
                                .fill(headline.sentimentColor)
                                .frame(width: 8, height: 8)
                                .padding(.top, 5)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(headline.title)
                                    .font(.caption)
                                    .foregroundColor(.primary)
                                Text(headline.source)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                        }
                        .padding(.vertical, 8)
                        .padding(.horizontal)
                        Divider().padding(.leading, 34)
                    }
                }
            } else {
                Text(L("İlgili haber bulunamadı."))
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.horizontal)
            }
        }
        .padding(.top, 8)
    }
}
