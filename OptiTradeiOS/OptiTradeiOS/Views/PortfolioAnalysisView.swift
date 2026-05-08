import SwiftUI
import Charts

// ─────────────────────────────────────────────────────────────────────────────
// MARK: - Portfolio Analysis View
// ─────────────────────────────────────────────────────────────────────────────

struct PortfolioAnalysisView: View {
    @EnvironmentObject private var session: UserSession
    @State private var symbolInput = ""
    @State private var symbols: [String] = []
    @State private var riskTolerance: Double = 0.5
    @State private var optResult: PortfolioOptResult?
    @State private var isLoading = false
    @State private var errorMessage: String?

    // Monte Carlo for single symbol
    @State private var mcSymbol = ""
    @State private var mcResult: MonteCarloResult?
    @State private var mcLoading = false
    @State private var recommendation: RecommendationResult?

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "0A0E1A").ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        portfolioSection
                        Divider().background(Color.white.opacity(0.1))
                        monteCarloSection
                    }
                    .padding()
                }
            }
            .navigationTitle("Portfoy & Risk Analizi")
            .navigationBarTitleDisplayMode(.large)
        }
    }

    // ── Portfolio Optimization Section ────────────────────────────────────────

    private var portfolioSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            sectionHeader("Portfoy Optimizasyonu", icon: "chart.pie.fill", color: .blue)

            Text("Markowitz Ortalama-Varyans modeli ile optimal agirliklar hesaplanir.")
                .font(.caption)
                .foregroundColor(.white.opacity(0.5))

            // Symbol input
            HStack {
                TextField("Sembol ekle (orn. THYAO.IS)", text: $symbolInput)
                    .foregroundColor(.white)
                    .tint(.cyan)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.characters)
                    .padding(10)
                    .background(Color.white.opacity(0.07))
                    .clipShape(RoundedRectangle(cornerRadius: 10))

                Button(action: addSymbol) {
                    Image(systemName: "plus.circle.fill")
                        .font(.title2)
                        .foregroundColor(.cyan)
                }
            }

            // Symbol chips
            if !symbols.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack {
                        ForEach(symbols, id: \.self) { sym in
                            HStack(spacing: 4) {
                                Text(sym)
                                    .font(.caption.bold())
                                Button { symbols.removeAll { $0 == sym } } label: {
                                    Image(systemName: "xmark.circle.fill")
                                        .font(.caption)
                                }
                            }
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(Color.blue.opacity(0.2))
                            .foregroundColor(.cyan)
                            .clipShape(Capsule())
                        }
                    }
                }
            }

            // Risk slider
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("Risk Toleransi:")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.6))
                    Spacer()
                    Text(riskLabel)
                        .font(.caption.bold())
                        .foregroundColor(riskColor)
                }
                Slider(value: $riskTolerance, in: 0...1, step: 0.1)
                    .tint(.cyan)
                HStack {
                    Text("Min Varyans").font(.caption2).foregroundColor(.white.opacity(0.4))
                    Spacer()
                    Text("Max Sharpe").font(.caption2).foregroundColor(.white.opacity(0.4))
                }
            }

            // Optimize button
            Button(action: optimizePortfolio) {
                HStack {
                    if isLoading { ProgressView().tint(.black) }
                    else { Image(systemName: "wand.and.stars"); Text("Portfoyu Optimize Et") }
                }
                .frame(maxWidth: .infinity)
                .frame(height: 46)
                .background(symbols.count >= 2 ? Color.blue : Color.gray.opacity(0.3))
                .foregroundColor(symbols.count >= 2 ? .white : .white.opacity(0.3))
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .disabled(symbols.count < 2 || isLoading)

            if let err = errorMessage {
                Label(err, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundColor(.red.opacity(0.8))
            }

            if let result = optResult {
                portfolioResultCard(result)
            }
        }
    }

    @ViewBuilder
    private func portfolioResultCard(_ result: PortfolioOptResult) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            // Key metrics row
            HStack(spacing: 0) {
                metricCell(label: "Yillik Getiri", value: String(format: "%.1f%%", result.expectedAnnualReturnPct),
                           color: result.expectedAnnualReturnPct >= 0 ? .green : .red)
                metricCell(label: "Volatilite", value: String(format: "%.1f%%", result.annualVolatilityPct), color: .orange)
                metricCell(label: "Sharpe", value: String(format: "%.2f", result.sharpeRatio), color: .cyan)
            }
            .background(Color.white.opacity(0.05))
            .clipShape(RoundedRectangle(cornerRadius: 12))

            // Weight chart using Swift Charts
            Text("Optimal Agirliklar")
                .font(.caption.bold())
                .foregroundColor(.white.opacity(0.7))

            Chart(result.weightsList, id: \.symbol) { item in
                SectorMark(
                    angle: .value("Agirlik", item.weight * 100),
                    innerRadius: .ratio(0.5),
                    outerRadius: .ratio(0.95)
                )
                .foregroundStyle(by: .value("Sembol", item.symbol))
                .cornerRadius(4)
            }
            .frame(height: 180)
            .chartLegend(position: .trailing, alignment: .center)

            // Weight list
            ForEach(result.weightsList, id: \.symbol) { item in
                HStack {
                    Text(item.symbol)
                        .font(.caption.bold())
                        .foregroundColor(.white)
                    Spacer()
                    Text("\(item.weight * 100, specifier: "%.1f")%")
                        .font(.caption.monospacedDigit())
                        .foregroundColor(.cyan)
                }
                .padding(.vertical, 2)
            }
        }
        .padding(16)
        .background(Color.white.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    // ── Monte Carlo Section ────────────────────────────────────────────────────

    private var monteCarloSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            sectionHeader("Monte Carlo Simülasyonu", icon: "waveform.path.ecg", color: .purple)

            Text("Geometrik Brownian Motion ile 30 gunluk 500 fiyat yolu simüle edilir.")
                .font(.caption)
                .foregroundColor(.white.opacity(0.5))

            HStack {
                TextField("Sembol (orn. GARAN.IS)", text: $mcSymbol)
                    .foregroundColor(.white)
                    .tint(.cyan)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.characters)
                    .padding(10)
                    .background(Color.white.opacity(0.07))
                    .clipShape(RoundedRectangle(cornerRadius: 10))

                Button(action: runMonteCarlo) {
                    if mcLoading {
                        ProgressView().tint(.cyan)
                    } else {
                        Image(systemName: "play.circle.fill")
                            .font(.title2)
                            .foregroundColor(.purple)
                    }
                }
                .disabled(mcSymbol.isEmpty || mcLoading)
            }

            if let mc = mcResult {
                monteCarloCard(mc)
            }

            if let rec = recommendation {
                recommendationCard(rec)
            }
        }
    }

    @ViewBuilder
    private func monteCarloCard(_ mc: MonteCarloResult) -> some View {
        VStack(spacing: 12) {
            // Price expectation
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Mevcut Fiyat")
                        .font(.caption2).foregroundColor(.white.opacity(0.5))
                    Text("\(mc.currentPrice, specifier: "%.4f")")
                        .font(.headline.monospacedDigit()).foregroundColor(.white)
                }
                Spacer()
                Image(systemName: "arrow.right")
                    .foregroundColor(.white.opacity(0.3))
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("30G Beklenti")
                        .font(.caption2).foregroundColor(.white.opacity(0.5))
                    Text("\(mc.expectedPrice30d, specifier: "%.4f")")
                        .font(.headline.monospacedDigit())
                        .foregroundColor(mc.expectedReturnPct >= 0 ? .green : .red)
                }
            }

            Divider().background(Color.white.opacity(0.1))

            // Metrics grid
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 2), spacing: 10) {
                mcMetric("Beklenen Getiri", String(format: "%+.1f%%", mc.expectedReturnPct),
                         color: mc.expectedReturnPct >= 0 ? .green : .red)
                mcMetric("Kar Olasiligi", String(format: "%%.0f", mc.probProfitPct), color: .cyan)
                mcMetric("VaR (%95)", String(format: "%.1f%%", mc.var95Pct), color: .orange)
                mcMetric("CVaR (%95)", String(format: "%.1f%%", mc.cvar95Pct), color: .red.opacity(0.8))
                mcMetric("Gunluk Volatilite", String(format: "%.2f%%", mc.dailyVolatilityPct), color: .yellow)
                mcMetric("Yillik Sharpe", String(format: "%.2f", mc.annualSharpe), color: .purple)
            }

            // Price range bar
            VStack(alignment: .leading, spacing: 6) {
                Text("5.–95. Persentil Fiyat Araligi")
                    .font(.caption2).foregroundColor(.white.opacity(0.5))
                HStack {
                    Text("\(mc.downside5Price, specifier: "%.2f")")
                        .font(.caption.monospacedDigit()).foregroundColor(.red)
                    Spacer()
                    Text("\(mc.upside95Price, specifier: "%.2f")")
                        .font(.caption.monospacedDigit()).foregroundColor(.green)
                }
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 4).fill(Color.red.opacity(0.3))
                        RoundedRectangle(cornerRadius: 4).fill(Color.green.opacity(0.5))
                            .frame(width: geo.size.width * 0.6)
                    }
                }
                .frame(height: 8)
            }
        }
        .padding(16)
        .background(Color.purple.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.purple.opacity(0.2), lineWidth: 1))
    }

    @ViewBuilder
    private func recommendationCard(_ rec: RecommendationResult) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Yapay Zeka Onerisi")
                        .font(.caption).foregroundColor(.white.opacity(0.5))
                    Text(rec.action)
                        .font(.title2.bold())
                        .foregroundColor(actionColor(rec.actionCode))
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    Text("Birlesik Skor")
                        .font(.caption2).foregroundColor(.white.opacity(0.4))
                    Text("\(rec.compositeScore, specifier: "%.0f")/100")
                        .font(.headline.monospacedDigit())
                        .foregroundColor(.cyan)
                }
            }

            // Progress bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4).fill(Color.white.opacity(0.1))
                    RoundedRectangle(cornerRadius: 4)
                        .fill(actionColor(rec.actionCode))
                        .frame(width: geo.size.width * CGFloat(rec.compositeScore / 100))
                }
            }
            .frame(height: 8)

            HStack {
                Label("Onerilen Pozisyon Buyuklugu: %\(rec.suggestedPositionPct, specifier: "%.0f")", systemImage: "scale.3d")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.6))
            }

            if !rec.reasons.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Gerekce:")
                        .font(.caption.bold()).foregroundColor(.white.opacity(0.5))
                    ForEach(rec.reasons, id: \.self) { reason in
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: "circle.fill")
                                .font(.system(size: 5))
                                .foregroundColor(.cyan)
                                .padding(.top, 5)
                            Text(reason).font(.caption).foregroundColor(.white.opacity(0.7))
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(Color.white.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(actionColor(rec.actionCode).opacity(0.3), lineWidth: 1))
    }

    // ── Helpers ────────────────────────────────────────────────────────────────

    private func addSymbol() {
        let s = symbolInput.trimmingCharacters(in: .whitespaces).uppercased()
        guard !s.isEmpty, !symbols.contains(s), symbols.count < 20 else { return }
        symbols.append(s)
        symbolInput = ""
    }

    private func optimizePortfolio() {
        isLoading = true
        errorMessage = nil
        optResult = nil
        Task {
            do {
                optResult = try await APIService.shared.optimizePortfolio(symbols: symbols, riskTolerance: riskTolerance)
            } catch {
                errorMessage = error.localizedDescription
            }
            isLoading = false
        }
    }

    private func runMonteCarlo() {
        let sym = mcSymbol.trimmingCharacters(in: .whitespaces).uppercased()
        guard !sym.isEmpty else { return }
        mcLoading = true
        mcResult = nil
        recommendation = nil
        Task {
            do {
                let result = try await APIService.shared.analyzeEnhanced(symbol: sym)
                mcResult = result.monteCarlo
                recommendation = result.recommendation
            } catch {
                mcResult = nil
            }
            mcLoading = false
        }
    }

    private func actionColor(_ code: String) -> Color {
        switch code {
        case "STRONG_BUY": return .green
        case "BUY": return Color(red: 0.4, green: 0.9, blue: 0.4)
        case "STRONG_SELL": return .red
        case "SELL": return .orange
        default: return .gray
        }
    }

    @ViewBuilder
    private func sectionHeader(_ title: String, icon: String, color: Color) -> some View {
        Label(title, systemImage: icon)
            .font(.headline.bold())
            .foregroundColor(color)
    }

    @ViewBuilder
    private func metricCell(label: String, value: String, color: Color) -> some View {
        VStack(spacing: 4) {
            Text(value).font(.headline.monospacedDigit()).foregroundColor(color)
            Text(label).font(.caption2).foregroundColor(.white.opacity(0.5))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
    }

    @ViewBuilder
    private func mcMetric(_ label: String, _ value: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(value).font(.subheadline.bold().monospacedDigit()).foregroundColor(color)
            Text(label).font(.caption2).foregroundColor(.white.opacity(0.4))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.white.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private var riskLabel: String {
        switch riskTolerance {
        case 0..<0.2: return "Cok Dusuk"
        case 0.2..<0.4: return "Dusuk"
        case 0.4..<0.6: return "Orta"
        case 0.6..<0.8: return "Yuksek"
        default: return "Cok Yuksek"
        }
    }

    private var riskColor: Color {
        switch riskTolerance {
        case 0..<0.3: return .green
        case 0.3..<0.6: return .yellow
        default: return .red
        }
    }
}

struct WeightItem: Identifiable {
    let symbol: String
    let weight: Double
    var id: String { symbol }
}

extension PortfolioOptResult {
    var weightsList: [WeightItem] {
        weights.map { WeightItem(symbol: $0.key, weight: $0.value) }
            .sorted { $0.weight > $1.weight }
    }
}
