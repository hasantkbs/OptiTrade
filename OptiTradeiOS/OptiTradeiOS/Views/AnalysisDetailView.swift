import SwiftUI

struct AnalysisDetailView: View {
    @EnvironmentObject private var session: UserSession
    let result: AnalysisResult
    @State private var chart: ChartResponse?
    @State private var chartPeriod = "3mo"
    @State private var isLoadingChart = false
    @State private var enhancedResult: AnalysisResult?
    @State private var isLoadingEnhanced = false
    @State private var v2Result: EngineResultV2?
    @State private var isLoadingV2 = false
    @State private var showFullChart = false

    private var displayResult: AnalysisResult { enhancedResult ?? result }

    private var accentColor: Color {
        switch result.decisionCode {
        case "STRONG_BUY", "BUY":     return .green
        case "STRONG_SELL", "SELL":   return .red
        default:                       return .orange
        }
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                headerCard
                
                if session.isPremium {
                    v2AnalysisSection
                    BacktestPerformanceView(symbol: result.symbol)
                }
                
                if isLoadingEnhanced {
                    HStack {
                        ProgressView()
                        Text("Derin analiz yükleniyor…")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .padding()
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                }
                if let rec = displayResult.recommendation { recommendationCard(rec) }
                if let mc  = displayResult.monteCarlo     { monteCarloCard(mc)     }
                chartSection
                
                Button {
                    showFullChart = true
                } label: {
                    HStack {
                        Image(systemName: "chart.bar.xaxis")
                        Text("Gelişmiş Etkileşimli Grafiği Aç")
                    }
                    .font(.headline)
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .frame(height: 50)
                    .background(Color.blue)
                    .cornerRadius(12)
                }
                .sheet(isPresented: $showFullChart) {
                    NavigationStack {
                        TradingViewChart(symbol: result.symbol, theme: session.appTheme == .light ? "light" : "dark")
                            .navigationTitle("\(result.symbol) Canlı Grafik")
                            .navigationBarTitleDisplayMode(.inline)
                            .toolbar {
                                ToolbarItem(placement: .navigationBarTrailing) {
                                    Button("Kapat") { showFullChart = false }
                                }
                            }
                            .ignoresSafeArea(edges: .bottom)
                    }
                }

                indicatorsCard
                if result.assetType == "stock" { fundamentalsCard }
                signalsCard
                if !session.isPremium {
                    AdBannerPlaceholder()
                }
                disclaimerFooter
            }
            .padding()
            .padding(.bottom, 24)
        }
        .navigationTitle(result.symbol)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadChart()
            await loadEnhanced()
            if session.isPremium { await loadV2() }
        }
        .onChange(of: chartPeriod) { Task { await loadChart() } }
        .onAppear { HapticService.shared.signalFeedback(decisionCode: result.decisionCode) }
    }

    // ── Header ────────────────────────────────────────────────────────────────

    private var headerCard: some View {
        VStack(spacing: 12) {
            HStack(spacing: 16) {
                ScoreMeter(score: result.score)
                VStack(alignment: .leading, spacing: 8) {
                    Text(result.symbol)
                        .font(.title2.bold())
                    DecisionBadge(decisionCode: result.decisionCode, decision: result.decision)
                    HStack(spacing: 8) {
                        RiskBadge(level: result.riskLevel)
                        Text(result.assetType == "stock" ? "Hisse" : "Kripto")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 7).padding(.vertical, 3)
                            .background(Color(.tertiarySystemBackground))
                            .clipShape(Capsule())
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    Text(formatPrice(result.indicators.currentPrice))
                        .font(.title3.bold())
                    Text(String(format: "%+.2f%%", result.indicators.priceVelocity))
                        .font(.subheadline.weight(.semibold))
                        .foregroundColor(result.indicators.priceVelocity >= 0 ? .green : .red)
                }
            }
            // ML Güven Çubuğu
            if let conf = result.mlConfidence {
                Divider()
                HStack(spacing: 10) {
                    Image(systemName: "brain.head.profile")
                        .font(.caption)
                        .foregroundColor(.purple)
                    Text("ML Model Güveni")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Spacer()
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 4).fill(Color.white.opacity(0.1))
                            RoundedRectangle(cornerRadius: 4)
                                .fill(conf >= 0.6 ? Color.green : conf >= 0.4 ? Color.orange : Color.red)
                                .frame(width: geo.size.width * conf)
                        }
                    }
                    .frame(width: 100, height: 7)
                    Text(String(format: "%%%.0f", conf * 100))
                        .font(.caption.monospacedDigit().bold())
                        .foregroundColor(conf >= 0.6 ? .green : conf >= 0.4 ? .orange : .red)
                        .frame(width: 36, alignment: .trailing)
                }
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    // ── AI Öneri Kartı ────────────────────────────────────────────────────────

    @ViewBuilder
    private func recommendationCard(_ rec: RecommendationResult) -> some View {
        sectionCard("Yapay Zeka Önerisi") {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(rec.action)
                        .font(.title3.bold())
                        .foregroundColor(actionColor(rec.actionCode))
                    HStack(spacing: 6) {
                        Image(systemName: "percent")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("Birleşik Skor: \(rec.compositeScore, specifier: "%.0f")/100")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    // Skor çubuğu
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 4).fill(Color.white.opacity(0.08))
                            RoundedRectangle(cornerRadius: 4)
                                .fill(actionColor(rec.actionCode))
                                .frame(width: geo.size.width * CGFloat(rec.compositeScore / 100))
                        }
                    }
                    .frame(height: 6)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    Text("Önerilen Pozisyon")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    Text(String(format: "%%%.0f", rec.suggestedPositionPct))
                        .font(.headline.monospacedDigit().bold())
                        .foregroundColor(.cyan)
                    Text("portföyden")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
            if !rec.reasons.isEmpty {
                Divider()
                VStack(alignment: .leading, spacing: 6) {
                    Text("Gerekçe").font(.caption.weight(.semibold)).foregroundColor(.secondary)
                    ForEach(rec.reasons, id: \.self) { reason in
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: "circle.fill")
                                .font(.system(size: 4))
                                .foregroundColor(actionColor(rec.actionCode))
                                .padding(.top, 5)
                            Text(reason).font(.caption).foregroundColor(.primary)
                        }
                    }
                }
            }
        }
    }

    // ── Monte Carlo Kartı ────────────────────────────────────────────────────

    @ViewBuilder
    private func monteCarloCard(_ mc: MonteCarloResult) -> some View {
        sectionCard("Monte Carlo Simülasyonu (30 Gün, \(mc.nSimulations) Yol)") {
            // Fiyat beklentisi
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Mevcut").font(.caption).foregroundColor(.secondary)
                    Text(formatPrice(mc.currentPrice))
                        .font(.headline.monospacedDigit())
                }
                Spacer()
                Image(systemName: "arrow.right").foregroundColor(.secondary).font(.caption)
                Spacer()
                VStack(alignment: .trailing, spacing: 3) {
                    Text("30G Beklenti").font(.caption).foregroundColor(.secondary)
                    Text(formatPrice(mc.expectedPrice30d))
                        .font(.headline.monospacedDigit())
                        .foregroundColor(mc.expectedReturnPct >= 0 ? .green : .red)
                }
            }
            Divider()
            // 6 metrik grid
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 3), spacing: 10) {
                mcMetric("Bkln. Getiri", String(format: "%+.1f%%", mc.expectedReturnPct),
                         mc.expectedReturnPct >= 0 ? .green : .red)
                mcMetric("Kar Olasılığı", String(format: "%%.0f", mc.probProfitPct), .cyan)
                mcMetric("Sharpe", String(format: "%.2f", mc.annualSharpe), .purple)
                mcMetric("VaR %95", String(format: "%.1f%%", mc.var95Pct), .orange)
                mcMetric("CVaR %95", String(format: "%.1f%%", mc.cvar95Pct), .red)
                mcMetric("Gün. Vol.", String(format: "%.2f%%", mc.dailyVolatilityPct), .yellow)
            }
            Divider()
            // Persentil aralığı
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("5. Persentil").font(.caption2).foregroundColor(.red)
                    Text(formatPrice(mc.downside5Price)).font(.caption.monospacedDigit()).foregroundColor(.red)
                }
                Spacer()
                VStack(alignment: .center, spacing: 2) {
                    Text("Beklenti").font(.caption2).foregroundColor(.secondary)
                    Text(formatPrice(mc.expectedPrice30d)).font(.caption.monospacedDigit())
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("95. Persentil").font(.caption2).foregroundColor(.green)
                    Text(formatPrice(mc.upside95Price)).font(.caption.monospacedDigit()).foregroundColor(.green)
                }
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4).fill(Color.red.opacity(0.25))
                    RoundedRectangle(cornerRadius: 4).fill(Color.green.opacity(0.4))
                        .frame(width: geo.size.width * 0.6)
                        .offset(x: geo.size.width * 0.4)
                }
            }
            .frame(height: 6)
        }
    }

    // ── Chart Section ─────────────────────────────────────────────────────────

    @ViewBuilder
    private var chartSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Fiyat Grafiği").font(.headline)
                Spacer()
                Picker("Periyot", selection: $chartPeriod) {
                    Text("1A").tag("1mo")
                    Text("3A").tag("3mo")
                    Text("6A").tag("6mo")
                    Text("1Y").tag("1y")
                }
                .pickerStyle(.segmented)
                .frame(width: 160)
            }
            if isLoadingChart {
                HStack { Spacer(); ProgressView(); Spacer() }
                    .frame(height: 230)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 16))
            } else if let c = chart {
                PriceChart(chart: c)
                if c.points.filter({ $0.rsi != nil }).count > 5 {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("RSI (14)").font(.caption.weight(.semibold)).foregroundColor(.secondary)
                            .padding(.horizontal).padding(.top, 10)
                        RSIChart(points: c.points).padding(.horizontal).padding(.bottom, 10)
                    }
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("Hacim").font(.caption.weight(.semibold)).foregroundColor(.secondary)
                        .padding(.horizontal).padding(.top, 10)
                    VolumeChart(points: c.points, isPositive: c.changePct >= 0)
                        .padding(.horizontal).padding(.bottom, 10)
                }
                .background(Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 16))
            }
        }
    }

    // ── Teknik Göstergeler ────────────────────────────────────────────────────

    private var indicatorsCard: some View {
        sectionCard("Teknik Göstergeler") {
            if let rsi = result.indicators.rsi {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("RSI (14)").font(.subheadline).foregroundColor(.secondary)
                        Text(rsi > 70 ? "Aşırı Alım" : rsi < 30 ? "Aşırı Satım" : "Normal Bölge")
                            .font(.caption)
                            .foregroundColor(rsi > 70 ? .red : rsi < 30 ? .green : .secondary)
                    }
                    Spacer()
                    RSIGauge(value: rsi)
                }
                Divider()
            }
            if let macd = result.indicators.macd, let sig = result.indicators.macdSignal {
                IndicatorRow(title: "MACD",      value: String(format: "%.4f", macd), color: .primary)
                IndicatorRow(title: "Sinyal",    value: String(format: "%.4f", sig),  color: .primary)
                if let hist = result.indicators.macdHistogram {
                    IndicatorRow(
                        title: "Histogram",
                        value: String(format: "%+.4f", hist),
                        color: hist >= 0 ? .green : .red
                    )
                }
                IndicatorRow(
                    title: "MACD Durumu",
                    value: macd > sig ? "Yükseliş ▲" : "Düşüş ▼",
                    color: macd > sig ? .green : .red
                )
                Divider()
            }
            IndicatorRow(
                title: "Fiyat Hızı",
                value: String(format: "%+.2f%%", result.indicators.priceVelocity),
                color: result.indicators.priceVelocity >= 0 ? .green : .red
            )
            IndicatorRow(
                title: "Hacim Oranı",
                value: String(format: "%.2fx", result.indicators.volumeRatio),
                color: result.indicators.volumeRatio > 1.2 ? .green : .secondary
            )
            IndicatorRow(
                title: "Günlük Hacim",
                value: formatVolume(result.indicators.dailyVolume),
                color: .primary
            )
        }
    }

    // ── Temel Analiz ──────────────────────────────────────────────────────────

    private var fundamentalsCard: some View {
        sectionCard("Temel Analiz") {
            IndicatorRow(
                title: "Bilanço Durumu",
                value: result.balanceStatus,
                color: result.balanceStatus == "Pozitif" ? .green :
                       result.balanceStatus == "Negatif" ? .red : .secondary
            )
        }
    }

    // ── Sinyal Analizi ────────────────────────────────────────────────────────

    @ViewBuilder
    private var signalsCard: some View {
        if !result.longSignals.isEmpty || !result.shortSignals.isEmpty {
            sectionCard("Sinyal Analizi") {
                if !result.longSignals.isEmpty {
                    Text("AL Sinyalleri").font(.caption.weight(.semibold)).foregroundColor(.green)
                    ForEach(result.longSignals, id: \.self) { s in SignalRow(text: s, isLong: true) }
                }
                if !result.shortSignals.isEmpty {
                    if !result.longSignals.isEmpty { Divider() }
                    Text("SAT Sinyalleri").font(.caption.weight(.semibold)).foregroundColor(.red)
                    ForEach(result.shortSignals, id: \.self) { s in SignalRow(text: s, isLong: false) }
                }
            }
        }
    }

    // ── Disclaimer ────────────────────────────────────────────────────────────

    private var disclaimerFooter: some View {
        VStack(spacing: 6) {
            Divider()
            HStack(spacing: 6) {
                Image(systemName: "exclamationmark.triangle.fill").font(.caption2).foregroundColor(.orange)
                Text("Bu analiz yatırım tavsiyesi değildir. Tüm kararlar kullanıcıya aittir.")
                    .font(.caption2).foregroundColor(.secondary).multilineTextAlignment(.center)
            }
            Text("Product by Algorix  •  algorix.io")
                .font(.caption2).foregroundColor(.secondary.opacity(0.6)).tracking(0.5)
        }
        .padding(.vertical, 8).frame(maxWidth: .infinity)
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    @ViewBuilder
    private func sectionCard<C: View>(_ title: String, @ViewBuilder content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.headline)
            content()
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    @ViewBuilder
    private func mcMetric(_ label: String, _ value: String, _ color: Color) -> some View {
        VStack(spacing: 4) {
            Text(value).font(.subheadline.bold().monospacedDigit()).foregroundColor(color)
            Text(label).font(.caption2).foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(color.opacity(0.07))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func actionColor(_ code: String) -> Color {
        switch code {
        case "STRONG_BUY":  return .green
        case "BUY":         return Color(red: 0.3, green: 0.85, blue: 0.3)
        case "STRONG_SELL": return .red
        case "SELL":        return .orange
        default:            return .gray
        }
    }

    private func loadChart() async {
        isLoadingChart = true
        chart = try? await APIService.shared.getChart(symbol: result.symbol, period: chartPeriod)
        isLoadingChart = false
    }

    private func loadEnhanced() async {
        isLoadingEnhanced = true
        enhancedResult = try? await APIService.shared.analyzeEnhanced(
            symbol: result.symbol,
            assetType: result.assetType
        )
        isLoadingEnhanced = false
    }

    private func loadV2() async {
        isLoadingV2 = true
        v2Result = try? await APIService.shared.analyzeV2(symbol: result.symbol)
        isLoadingV2 = false
    }

    @ViewBuilder
    private var v2AnalysisSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("V2 ICT Engine", systemImage: "cpu.fill")
                    .font(.headline)
                    .foregroundColor(.accentColor)
                Spacer()
                if isLoadingV2 {
                    ProgressView().scaleEffect(0.8)
                } else if v2Result != nil {
                    Text("Canlı")
                        .font(.caption2.bold())
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.green.opacity(0.2))
                        .foregroundColor(.green)
                        .cornerRadius(4)
                }
            }

            if let v2 = v2Result {
                VStack(spacing: 12) {
                    // Aggregated Score V2
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Gelişmiş Skor")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text(String(format: "%.1f", v2.aggregatedScore * 100))
                                .font(.title3.bold())
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 4) {
                            Text("Güven")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text(String(format: "%%%.1f", v2.confidence * 100))
                                .font(.body.bold())
                        }
                    }

                    Divider()

                    // Signals List
                    ForEach(v2.signals) { signal in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(signal.indicatorName.replacingOccurrences(of: "Indicator", with: ""))
                                    .font(.subheadline.weight(.medium))
                                if case .string(let desc) = signal.metadata["description"] {
                                    Text(desc)
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                }
                            }
                            Spacer()
                            Text(signal.side.rawValue)
                                .font(.caption.bold())
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(signal.side.color.opacity(0.15))
                                .foregroundColor(signal.side.color)
                                .cornerRadius(6)
                        }
                    }
                    
                    if let ml = v2.mlPrediction {
                        Divider()
                        HStack {
                            Label("V2 ML Tahmini", systemImage: "brain.head.profile.fill")
                                .font(.caption)
                                .foregroundColor(.purple)
                            Spacer()
                            Text(ml.isBullish ? "YÜKSELİŞ" : "DÜŞÜŞ")
                                .font(.caption.bold())
                                .foregroundColor(ml.isBullish ? .green : .red)
                            Text(String(format: "%%%.1f", ml.confidence * 100))
                                .font(.caption.monospacedDigit())
                                .foregroundColor(.secondary)
                        }
                    }
                }
            } else if !isLoadingV2 {
                Text("V2 analiz verisi alınamadı.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .background(Color.accentColor.opacity(0.05))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.accentColor.opacity(0.2), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private func formatPrice(_ v: Double) -> String {
        v >= 1000 ? String(format: "%.0f", v) : String(format: "%.4f", v)
    }

    private func formatVolume(_ v: Double) -> String {
        if v >= 1_000_000_000 { return String(format: "%.1fB", v / 1_000_000_000) }
        if v >= 1_000_000     { return String(format: "%.1fM", v / 1_000_000) }
        if v >= 1_000         { return String(format: "%.1fK", v / 1_000) }
        return String(format: "%.0f", v)
    }
}
