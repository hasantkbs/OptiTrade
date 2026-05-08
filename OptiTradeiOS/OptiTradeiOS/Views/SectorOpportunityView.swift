// OptiTrade — SectorOpportunityView
// Sektörleri fırsat skoruna göre sıralar, kullanıcıya tavsiye verir.

import SwiftUI

// MARK: - Models

struct SectorOverview: Decodable, Identifiable {
    var id: String { sector }
    let sector:           String
    let nameTr:           String
    let icon:             String
    let description:      String
    let market:           String
    let opportunityScore: Double
    let trend:            String
    let opportunityLabel: String
    let avgTechnical:     Double
    let avgNewsDelta:     Double
    let avgChangePct:     Double
    let bullishCount:     Int
    let totalCount:       Int
    let topSymbols:       [String]
    let advice:           String
    let risk:             String

    enum CodingKeys: String, CodingKey {
        case sector, icon, description, market, trend, advice, risk
        case nameTr           = "name_tr"
        case opportunityScore = "opportunity_score"
        case opportunityLabel = "opportunity_label"
        case avgTechnical     = "avg_technical"
        case avgNewsDelta     = "avg_news_delta"
        case avgChangePct     = "avg_change_pct"
        case bullishCount     = "bullish_count"
        case totalCount       = "total_count"
        case topSymbols       = "top_symbols"
    }

    var trendColor: Color {
        switch trend {
        case "STRONG_BULL": return Color(hex: "#00FF88")
        case "BULLISH":     return Color(hex: "#44CC66")
        case "STRONG_BEAR": return .red
        case "BEARISH":     return Color(hex: "#FF6644")
        default:            return .gray
        }
    }

    var trendEmoji: String {
        switch trend {
        case "STRONG_BULL": return "🚀"
        case "BULLISH":     return "📈"
        case "STRONG_BEAR": return "💥"
        case "BEARISH":     return "📉"
        default:            return "➡️"
        }
    }

    var scoreColor: Color {
        if opportunityScore >= 68 { return Color(hex: "#00FF88") }
        if opportunityScore >= 55 { return Color(hex: "#88CC44") }
        if opportunityScore >= 42 { return .gray }
        if opportunityScore >= 30 { return Color(hex: "#FF8844") }
        return .red
    }

    var riskColor: Color {
        switch risk {
        case "LOW":  return .green
        case "HIGH": return .red
        default:     return .orange
        }
    }
}

struct SectorsResponse: Decodable {
    let market:   String
    let sectors:  [SectorOverview]
    struct TopOpportunity: Decodable {
        let sector:  String?
        let nameTr:  String?
        let score:   Double?
        let trend:   String?
        let advice:  String?
        enum CodingKeys: String, CodingKey {
            case sector, trend, advice
            case nameTr = "name_tr"
            case score
        }
    }
    let topOpportunity: TopOpportunity?
    enum CodingKeys: String, CodingKey {
        case market, sectors
        case topOpportunity = "top_opportunity"
    }
}

// MARK: - ViewModel

@MainActor
final class SectorViewModel: ObservableObject {
    @Published var sectors:  [SectorOverview] = []
    @Published var isLoading = false
    @Published var error:    String?
    @Published var topOpportunity: SectorsResponse.TopOpportunity?

    func load(market: TradingMarket) async {
        guard market != .crypto else {
            sectors = []; return
        }
        isLoading = true; error = nil
        defer { isLoading = false }
        do {
            let response = try await APIService.shared.getSectorsOverview(market: market)
            sectors        = response.sectors
            topOpportunity = response.topOpportunity
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - Main View

struct SectorOpportunityView: View {
    @EnvironmentObject var preferences: UserPreferences
    @StateObject private var vm = SectorViewModel()
    @State private var selectedSector: SectorOverview?

    var body: some View {
        ZStack {
            Color(hex: "#0A0E1A").ignoresSafeArea()

            if preferences.selectedMarket == .crypto {
                cryptoMessage
            } else if vm.isLoading {
                loadingView
            } else if let err = vm.error {
                errorView(err)
            } else {
                mainContent
            }
        }
        .navigationTitle("Sektör Analizi")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load(market: preferences.selectedMarket) }
        .onChange(of: preferences.selectedMarket) { _ in
            Task { await vm.load(market: preferences.selectedMarket) }
        }
        .sheet(item: $selectedSector) { sector in
            SectorDetailSheet(sector: sector)
        }
    }

    // ── Top Opportunity Banner ────────────────────────────────────────────────

    private var mainContent: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                if let top = vm.topOpportunity, let score = top.score, score >= 60 {
                    opportunityBanner(top)
                }

                // Piyasa Etiketi
                HStack {
                    MarketBadge(market: preferences.selectedMarket)
                    Text("\(vm.sectors.count) sektör")
                        .font(.caption)
                        .foregroundColor(.gray)
                    Spacer()
                    Text("Fırsata göre sıralı")
                        .font(.caption2)
                        .foregroundColor(.gray)
                }
                .padding(.horizontal, 20)
                .padding(.top, 4)

                // Sektör Kartları
                ForEach(vm.sectors) { sector in
                    SectorCard(sector: sector)
                        .onTapGesture { selectedSector = sector }
                        .padding(.horizontal, 16)
                }
            }
            .padding(.bottom, 30)
            .padding(.top, 8)
        }
        .refreshable { await vm.load(market: preferences.selectedMarket) }
    }

    private func opportunityBanner(_ top: SectorsResponse.TopOpportunity) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Text("🎯")
                    .font(.title2)
                VStack(alignment: .leading, spacing: 2) {
                    Text("En Yüksek Fırsat")
                        .font(.caption.weight(.semibold))
                        .foregroundColor(Color(hex: "#00FF88").opacity(0.8))
                    Text(top.nameTr ?? top.sector ?? "")
                        .font(.headline.bold())
                        .foregroundColor(.white)
                }
                Spacer()
                if let score = top.score {
                    VStack(spacing: 0) {
                        Text("\(Int(score))")
                            .font(.title2.bold())
                            .foregroundColor(Color(hex: "#00FF88"))
                        Text("puan")
                            .font(.caption2)
                            .foregroundColor(.gray)
                    }
                }
            }
            if let advice = top.advice {
                Text(advice)
                    .font(.caption)
                    .foregroundColor(.gray)
                    .lineLimit(3)
            }
        }
        .padding(16)
        .background(Color(hex: "#00FF88").opacity(0.08))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color(hex: "#00FF88").opacity(0.3), lineWidth: 1)
        )
        .cornerRadius(14)
        .padding(.horizontal, 16)
        .padding(.top, 8)
    }

    // ── Loading / Error / Crypto ──────────────────────────────────────────────

    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .tint(Color(hex: "#00D4FF"))
                .scaleEffect(1.3)
            Text("Sektörler analiz ediliyor...")
                .font(.subheadline)
                .foregroundColor(.gray)
        }
    }

    private func errorView(_ msg: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .foregroundColor(.orange)
            Text("Hata: \(msg)")
                .font(.caption)
                .foregroundColor(.gray)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            Button("Tekrar Dene") {
                Task { await vm.load(market: preferences.selectedMarket) }
            }
            .foregroundColor(Color(hex: "#00D4FF"))
        }
    }

    private var cryptoMessage: some View {
        VStack(spacing: 16) {
            Text("🌐")
                .font(.system(size: 50))
            Text("Kripto piyasasında sektör ayrımı yoktur")
                .font(.headline)
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
            Text("Bitcoin, Ethereum ve diğer kripto varlıklar\nglobal bir piyasada işlem görür.")
                .font(.subheadline)
                .foregroundColor(.gray)
                .multilineTextAlignment(.center)
        }
        .padding(40)
    }
}

// MARK: - SectorCard

struct SectorCard: View {
    let sector: SectorOverview

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                // İkon + İsim
                Text(sector.icon)
                    .font(.title2)
                    .frame(width: 44, height: 44)
                    .background(Color.white.opacity(0.06))
                    .cornerRadius(10)

                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(sector.nameTr)
                            .font(.headline)
                            .foregroundColor(.white)
                        Text(sector.trendEmoji)
                        Spacer()
                        // Risk badge
                        Text(sector.risk)
                            .font(.caption2.weight(.semibold))
                            .foregroundColor(sector.riskColor)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(sector.riskColor.opacity(0.12))
                            .cornerRadius(5)
                    }
                    Text(sector.description)
                        .font(.caption)
                        .foregroundColor(.gray)
                        .lineLimit(1)
                }
            }

            // Fırsat skoru çubuk
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(sector.opportunityLabel)
                        .font(.caption.weight(.semibold))
                        .foregroundColor(sector.scoreColor)
                    Spacer()
                    Text("\(Int(sector.opportunityScore))/100")
                        .font(.caption.weight(.bold))
                        .foregroundColor(sector.scoreColor)
                }
                ScoreProgressBar(score: sector.opportunityScore, color: sector.scoreColor)
            }

            // İstatistikler
            HStack(spacing: 0) {
                statCell(
                    label: "Teknik",
                    value: "\(Int(sector.avgTechnical))",
                    color: sector.avgTechnical > 55 ? .green : (sector.avgTechnical < 45 ? .red : .gray)
                )
                Divider().frame(height: 28).background(Color.white.opacity(0.1))
                statCell(
                    label: "Haber",
                    value: sector.avgNewsDelta >= 0 ? "+\(Int(sector.avgNewsDelta))" : "\(Int(sector.avgNewsDelta))",
                    color: sector.avgNewsDelta > 0 ? .green : (sector.avgNewsDelta < 0 ? .red : .gray)
                )
                Divider().frame(height: 28).background(Color.white.opacity(0.1))
                statCell(
                    label: "Boğa",
                    value: "\(sector.bullishCount)/\(sector.totalCount)",
                    color: sector.bullishCount > sector.totalCount / 2 ? .green : .gray
                )
                Divider().frame(height: 28).background(Color.white.opacity(0.1))
                statCell(
                    label: "Değişim",
                    value: sector.avgChangePct >= 0 ? "+\(String(format: "%.1f", sector.avgChangePct))%" : "\(String(format: "%.1f", sector.avgChangePct))%",
                    color: sector.avgChangePct > 0 ? .green : (sector.avgChangePct < 0 ? .red : .gray)
                )
            }

            // En iyi hisseler
            if !sector.topSymbols.isEmpty {
                HStack(spacing: 6) {
                    Text("Öne Çıkanlar:")
                        .font(.caption2)
                        .foregroundColor(.gray)
                    ForEach(sector.topSymbols, id: \.self) { sym in
                        Text(sym.replacingOccurrences(of: ".IS", with: ""))
                            .font(.caption2.weight(.semibold))
                            .foregroundColor(Color(hex: "#00D4FF"))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color(hex: "#00D4FF").opacity(0.1))
                            .cornerRadius(5)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.caption2)
                        .foregroundColor(.gray)
                }
            }
        }
        .padding(14)
        .background(Color.white.opacity(0.04))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(sector.trendColor.opacity(0.2), lineWidth: 1)
        )
        .cornerRadius(14)
    }

    private func statCell(label: String, value: String, color: Color) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.caption.weight(.semibold))
                .foregroundColor(color)
            Text(label)
                .font(.caption2)
                .foregroundColor(.gray)
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - ScoreProgressBar

struct ScoreProgressBar: View {
    let score: Double
    let color: Color

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.white.opacity(0.08))
                RoundedRectangle(cornerRadius: 4)
                    .fill(color)
                    .frame(width: geo.size.width * min(1, score / 100))
            }
        }
        .frame(height: 6)
        .animation(.spring(response: 0.6), value: score)
    }
}

// MARK: - SectorDetailSheet

struct SectorDetailSheet: View {
    let sector: SectorOverview
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationView {
            ZStack {
                Color(hex: "#0A0E1A").ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {

                        // Başlık
                        HStack(spacing: 12) {
                            Text(sector.icon)
                                .font(.largeTitle)
                            VStack(alignment: .leading) {
                                Text(sector.nameTr)
                                    .font(.title2.bold())
                                    .foregroundColor(.white)
                                Text(sector.description)
                                    .font(.caption)
                                    .foregroundColor(.gray)
                            }
                        }
                        .padding(.horizontal)

                        // Skor kartı
                        HStack(spacing: 0) {
                            scoreCard(title: "Fırsat",
                                      value: "\(Int(sector.opportunityScore))",
                                      sub: sector.opportunityLabel,
                                      color: sector.scoreColor)
                            scoreCard(title: "Trend",
                                      value: sector.trendEmoji,
                                      sub: sector.trend.replacingOccurrences(of: "_", with: " "),
                                      color: sector.trendColor)
                            scoreCard(title: "Risk",
                                      value: sector.risk,
                                      sub: "Seviye",
                                      color: sector.riskColor)
                        }
                        .background(Color.white.opacity(0.04))
                        .cornerRadius(14)
                        .padding(.horizontal)

                        // Tavsiye
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Sektör Tavsiyesi", systemImage: "lightbulb.fill")
                                .font(.subheadline.weight(.semibold))
                                .foregroundColor(Color(hex: "#F7C948"))
                            Text(sector.advice)
                                .font(.subheadline)
                                .foregroundColor(.white.opacity(0.85))
                                .lineSpacing(4)
                        }
                        .padding(14)
                        .background(Color(hex: "#F7C948").opacity(0.06))
                        .cornerRadius(12)
                        .padding(.horizontal)

                        // Öne çıkan hisseler
                        if !sector.topSymbols.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Öne Çıkan Hisseler")
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundColor(.gray)
                                    .padding(.horizontal)
                                ScrollView(.horizontal, showsIndicators: false) {
                                    HStack(spacing: 8) {
                                        ForEach(sector.topSymbols, id: \.self) { sym in
                                            Text(sym.replacingOccurrences(of: ".IS", with: ""))
                                                .font(.subheadline.weight(.bold))
                                                .foregroundColor(Color(hex: "#00D4FF"))
                                                .padding(.horizontal, 14)
                                                .padding(.vertical, 8)
                                                .background(Color(hex: "#00D4FF").opacity(0.12))
                                                .cornerRadius(10)
                                        }
                                    }
                                    .padding(.horizontal)
                                }
                            }
                        }

                        Spacer(minLength: 40)
                    }
                    .padding(.top)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Kapat") { dismiss() }
                        .foregroundColor(Color(hex: "#00D4FF"))
                }
            }
        }
    }

    private func scoreCard(title: String, value: String, sub: String, color: Color) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title3.bold())
                .foregroundColor(color)
            Text(title)
                .font(.caption2)
                .foregroundColor(.gray)
            Text(sub)
                .font(.caption2.weight(.medium))
                .foregroundColor(color.opacity(0.7))
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
    }
}
