import SwiftUI
import AuthenticationServices

struct OnboardingView: View {
    @EnvironmentObject private var session: UserSession
    @EnvironmentObject private var preferences: UserPreferences
    @EnvironmentObject private var firebase: FirebaseService
    @AppStorage("api_base_url") private var apiURL = "https://api.optitrade.app"
    @State private var page = 0
    @State private var disclaimerChecked = false
    @State private var apiTestState: APITestState = .idle
    @State private var animateGlow = false

    enum APITestState { case idle, testing, success, failure }

    private let totalPages = 4

    var body: some View {
        ZStack {
            // Animated Premium Background
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
                    // Glowing outer ring
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
                    
                    Text("Finansal Analizde Yeni Nesil")
                        .font(.title3.weight(.medium))
                        .foregroundColor(.accentColor)
                    
                    Text("Product by Algorix")
                        .font(.caption2.weight(.bold))
                        .foregroundColor(.gray.opacity(0.6))
                        .tracking(3)
                        .textCase(.uppercase)
                }

                VStack(spacing: 16) {
                    premiumFeatureRow(icon: "cpu.fill", title: "V2 ICT Analiz", subtitle: "Algoritmik sinyaller ve ICT modelleri")
                    premiumFeatureRow(icon: "brain.head.profile.fill", title: "Yapay Zeka", subtitle: "%64+ başarı oranlı XGBoost modeli")
                    premiumFeatureRow(icon: "chart.bar.xaxis", title: "Küresel Erişim", subtitle: "BIST, NASDAQ ve Kripto tek ekranda")
                }
                .padding(.horizontal, 40)
                .padding(.top, 10)
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
            VStack(spacing: 20) {
                Text("Risk Bildirimi")
                    .font(.title.bold())
                    .foregroundColor(.white)
                    .padding(.top, 40)

                ScrollView(showsIndicators: false) {
                    VStack(alignment: .leading, spacing: 16) {
                        disclaimerBlock(icon: "exclamationmark.shield.fill", color: .orange, title: "Yatırım Tavsiyesi Değildir", body: "Tüm analizler teknik veriye dayalı algoritma çıktılarıdır. Kararlar kullanıcı sorumluluğundadır.")
                        disclaimerBlock(icon: "clock.arrow.2.circlepath", color: .blue, title: "Geçmiş Performans", body: "Backtest sonuçları gelecekteki kazancı garanti etmez.")
                        disclaimerBlock(icon: "building.columns.fill", color: .purple, title: "Yasal Statü", body: "OptiTrade bir yatırım danışmanlığı kurumu değildir.")
                    }
                    .padding()
                }
                .background(Color.white.opacity(0.05))
                .cornerRadius(20)
                .padding(.horizontal, 24)

                Button {
                    withAnimation { disclaimerChecked.toggle() }
                } label: {
                    HStack {
                        Image(systemName: disclaimerChecked ? "checkmark.circle.fill" : "circle")
                            .foregroundColor(disclaimerChecked ? .accentColor : .gray)
                        Text("Yasal uyarıları kabul ediyorum.")
                            .font(.subheadline)
                            .foregroundColor(.white)
                    }
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(Color.white.opacity(0.05))
                    .cornerRadius(12)
                }
                .padding(.horizontal, 24)
            }

            Spacer()
            
            nextButton(title: "Anladım ve Devam Et", disabled: !disclaimerChecked) {
                session.disclaimerAccepted = true
                withAnimation { page = 2 }
            }
            .padding(.horizontal, 40)
            .padding(.bottom, 60)
        }
    }

    private var apiSetupPage: some View {
        VStack(spacing: 24) {
            Spacer()
            
            Image(systemName: "network")
                .font(.system(size: 60))
                .foregroundColor(.accentColor)
            
            Text("Bağlantı Ayarı")
                .font(.title.bold())
                .foregroundColor(.white)
            
            Text("Uygulamanın analiz motoruna erişebilmesi için backend adresini doğrulayın.")
                .font(.subheadline)
                .foregroundColor(.gray)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)

            TextField("API URL", text: $apiURL)
                .padding()
                .background(Color.white.opacity(0.1))
                .cornerRadius(12)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .padding(.horizontal, 40)

            Button {
                testConnection()
            } label: {
                HStack {
                    if apiTestState == .testing {
                        ProgressView().tint(.white)
                    } else {
                        Text(apiTestState == .success ? "Bağlantı Başarılı ✓" : "Bağlantıyı Doğrula")
                    }
                }
                .fontWeight(.bold)
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .frame(height: 50)
                .background(apiTestState == .success ? Color.green.opacity(0.3) : Color.white.opacity(0.1))
                .cornerRadius(12)
            }
            .padding(.horizontal, 40)
            
            Spacer()
            
            nextButton(title: "Devam Et") {
                APIService.shared.baseURL = apiURL
                withAnimation { page = 3 }
            }
            .padding(.horizontal, 40)
            .padding(.bottom, 60)
        }
    }

    private var loginPage: some View {
        VStack(spacing: 32) {
            Spacer()
            
            VStack(spacing: 16) {
                Text("Premium Deneyim")
                    .font(.system(size: 32, weight: .bold))
                    .foregroundColor(.white)
                
                Text("Hesabınızı oluşturun ve analizlerinizi tüm cihazlarınızda senkronize edin.")
                    .font(.subheadline)
                    .foregroundColor(.gray)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }

            VStack(spacing: 16) {
                // Sign in with Apple (Premium Look)
                SignInWithAppleButton(
                    onRequest: { _ in },
                    onCompletion: { _ in
                        // Handled in AuthView usually, but here for premium feel
                        session.onboardingDone = true
                    }
                )
                .signInWithAppleButtonStyle(.white)
                .frame(height: 54)
                .cornerRadius(27)
                .padding(.horizontal, 40)

                Button {
                    session.isGuestMode = true
                    session.onboardingDone = true
                } label: {
                    Text("Şimdilik Misafir Olarak Devam Et")
                        .font(.subheadline)
                        .foregroundColor(.accentColor)
                }
            }
            
            Spacer()
            
            Text("Hesap oluşturarak Kullanım Koşulları'nı kabul etmiş olursunuz.")
                .font(.caption2)
                .foregroundColor(.gray.opacity(0.5))
                .padding(.bottom, 40)
        }
    }

    private func testConnection() {
        apiTestState = .testing
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
                .frame(height: 56)
                .background(disabled ? Color.gray.opacity(0.5) : Color.accentColor)
                .cornerRadius(28)
                .shadow(color: disabled ? .clear : Color.accentColor.opacity(0.3), radius: 10, y: 5)
        }
        .disabled(disabled)
    }

    private func premiumFeatureRow(icon: String, title: String, subtitle: String) -> some View {
        HStack(spacing: 16) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundColor(.accentColor)
                .frame(width: 40)
            
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.headline)
                    .foregroundColor(.white)
                Text(subtitle)
                    .font(.caption)
                    .foregroundColor(.gray)
            }
            Spacer()
        }
    }

    private func disclaimerBlock(icon: String, color: Color, title: String, body: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: icon)
                .foregroundColor(color)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.subheadline.bold())
                    .foregroundColor(.white)
                Text(body)
                    .font(.caption)
                    .foregroundColor(.gray)
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
