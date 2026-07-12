import SwiftUI
import Charts

// ─────────────────────────────────────────────────────────────────────────────
// MARK: - Portfolio Analysis View
// ─────────────────────────────────────────────────────────────────────────────

struct PortfolioAnalysisView: View {
    @EnvironmentObject private var session: UserSession
    @StateObject private var watchlistVM = WatchlistViewModel()
    @State private var showWatchlistAddSheet = false
    @State private var newWatchSymbol = ""
    @State private var newWatchPotential = ""
    @State private var newWatchAssetType = "stock"

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
                Color(.systemBackground).ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        PortfolioHoldingsSection()
                        Divider().background(Color.primary.opacity(0.1))
                        watchlistSection
                        Divider().background(Color.primary.opacity(0.1))
                        portfolioSection
                        Divider().background(Color.primary.opacity(0.1))
                        monteCarloSection
                    }
                    .padding()
                }
            }
            .navigationTitle(L("Portfoy & Risk Analizi"))
            .navigationBarTitleDisplayMode(.large)
            .task { await watchlistVM.analyzeAll() }
        }
    }

    // ── Watchlist ("Takip") Section ───────────────────────────────────────────

    private var watchlistSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                sectionHeader("Takip Listesi", icon: "star.fill", color: .yellow)
                Spacer()
                if watchlistVM.isAnalyzing {
                    ProgressView().tint(.cyan)
                } else {
                    Button {
                        Task { await watchlistVM.analyzeAll() }
                    } label: {
                        Image(systemName: "arrow.clockwise").foregroundColor(.cyan)
                    }
                }
                Button { showWatchlistAddSheet = true } label: {
                    Image(systemName: "plus.circle.fill").foregroundColor(.cyan)
                }
            }

            if watchlistVM.items.isEmpty {
                Text(L("Takip listeniz boş. Sağ üstteki + ile hisse veya kripto ekleyin."))
                    .font(.caption)
                    .foregroundColor(.primary.opacity(0.5))
            } else {
                VStack(spacing: 10) {
                    ForEach(watchlistVM.sortedItems) { item in
                        watchlistRow(item)
                    }
                }
            }
        }
        .sheet(isPresented: $showWatchlistAddSheet) { watchlistAddSheet }
    }

    @ViewBuilder
    private func watchlistRow(_ item: WatchlistItemData) -> some View {
        HStack(spacing: 8) {
            Group {
                if let result = watchlistVM.results[item.id] {
                    NavigationLink(destination: AnalysisDetailView(result: result)) {
                        ResultCardView(result: result)
                    }
                    .buttonStyle(.plain)
                } else {
                    watchlistPendingCard(item)
                }
            }
            Button {
                withAnimation { watchlistVM.removeItem(item) }
            } label: {
                Image(systemName: "trash.circle.fill")
                    .foregroundColor(.red.opacity(0.7))
            }
        }
    }

    private func watchlistPendingCard(_ item: WatchlistItemData) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(item.symbol)
                    .font(.headline)
                    .foregroundColor(.primary)
                Text(item.assetType == "stock" ? L("Hisse Senedi") : L("Kripto Para"))
                    .font(.caption)
                    .foregroundColor(.primary.opacity(0.5))
            }
            Spacer()
            ProgressView().tint(.cyan)
        }
        .padding()
        .background(Color.primary.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private var watchlistAddSheet: some View {
        NavigationStack {
            Form {
                Section(L("Varlık Tipi")) {
                    Picker(L("Tip"), selection: $newWatchAssetType) {
                        Text(L("Hisse Senedi")).tag("stock")
                        Text(L("Kripto Para")).tag("crypto")
                    }
                    .pickerStyle(.segmented)
                    .listRowInsets(EdgeInsets())
                    .listRowBackground(Color.clear)
                }

                Section(L("Sembol")) {
                    TextField(newWatchAssetType == "stock" ? "THYAO.IS" : "BTC-USD", text: $newWatchSymbol)
                        .textInputAutocapitalization(.characters)
                        .disableAutocorrection(true)
                }

                Section {
                    TextField(L("Örn: 350 (opsiyonel)"), text: $newWatchPotential)
                        .keyboardType(.decimalPad)
                } header: {
                    Text(L("Potansiyel Fiyat"))
                } footer: {
                    Text(L("Potansiyel fiyat girilirse ucuz/pahalı analizi yapılır."))
                }
            }
            .navigationTitle(L("Sembol Ekle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(L("Vazgeç")) {
                        showWatchlistAddSheet = false
                        newWatchSymbol = ""
                        newWatchPotential = ""
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("Ekle")) {
                        watchlistVM.addItem(newWatchSymbol, potential: Double(newWatchPotential), assetType: newWatchAssetType)
                        newWatchSymbol = ""
                        newWatchPotential = ""
                        showWatchlistAddSheet = false
                    }
                    .disabled(newWatchSymbol.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
        .presentationDetents([.medium])
    }

    // ── Portfolio Optimization Section ────────────────────────────────────────

    private var portfolioSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            sectionHeader("Portfoy Optimizasyonu", icon: "chart.pie.fill", color: .blue)

            Text(L("Markowitz Ortalama-Varyans modeli ile optimal agirliklar hesaplanir."))
                .font(.caption)
                .foregroundColor(.primary.opacity(0.5))

            // Symbol input
            HStack {
                TextField(L("Sembol ekle (orn. THYAO.IS)"), text: $symbolInput)
                    .foregroundColor(.primary)
                    .tint(.cyan)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.characters)
                    .padding(10)
                    .background(Color.primary.opacity(0.07))
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
                    Text(L("Risk Toleransi:"))
                        .font(.caption)
                        .foregroundColor(.primary.opacity(0.6))
                    Spacer()
                    Text(riskLabel)
                        .font(.caption.bold())
                        .foregroundColor(riskColor)
                }
                Slider(value: $riskTolerance, in: 0...1, step: 0.1)
                    .tint(.cyan)
                HStack {
                    Text(L("Min Varyans")).font(.caption2).foregroundColor(.primary.opacity(0.4))
                    Spacer()
                    Text(L("Max Sharpe")).font(.caption2).foregroundColor(.primary.opacity(0.4))
                }
            }

            // Optimize button
            Button(action: optimizePortfolio) {
                HStack {
                    if isLoading { ProgressView().tint(.black) }
                    else { Image(systemName: "wand.and.stars"); Text(L("Portfoyu Optimize Et")) }
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
            .background(Color.primary.opacity(0.05))
            .clipShape(RoundedRectangle(cornerRadius: 12))

            // Weight chart using Swift Charts
            Text(L("Optimal Agirliklar"))
                .font(.caption.bold())
                .foregroundColor(.primary.opacity(0.7))

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
                        .foregroundColor(.primary)
                    Spacer()
                    Text("\(item.weight * 100, specifier: "%.1f")%")
                        .font(.caption.monospacedDigit())
                        .foregroundColor(.cyan)
                }
                .padding(.vertical, 2)
            }
        }
        .padding(16)
        .background(Color.primary.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    // ── Monte Carlo Section ────────────────────────────────────────────────────

    private var monteCarloSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            sectionHeader("Monte Carlo Simülasyonu", icon: "waveform.path.ecg", color: .purple)

            Text(L("Geometrik Brownian Motion ile 30 gunluk 500 fiyat yolu simüle edilir."))
                .font(.caption)
                .foregroundColor(.primary.opacity(0.5))

            HStack {
                TextField(L("Sembol (orn. GARAN.IS)"), text: $mcSymbol)
                    .foregroundColor(.primary)
                    .tint(.cyan)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.characters)
                    .padding(10)
                    .background(Color.primary.opacity(0.07))
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
                    Text(L("Mevcut Fiyat"))
                        .font(.caption2).foregroundColor(.primary.opacity(0.5))
                    Text("\(mc.currentPrice, specifier: "%.4f")")
                        .font(.headline.monospacedDigit()).foregroundColor(.primary)
                }
                Spacer()
                Image(systemName: "arrow.right")
                    .foregroundColor(.primary.opacity(0.3))
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(L("30G Beklenti"))
                        .font(.caption2).foregroundColor(.primary.opacity(0.5))
                    Text("\(mc.expectedPrice30d, specifier: "%.4f")")
                        .font(.headline.monospacedDigit())
                        .foregroundColor(mc.expectedReturnPct >= 0 ? .green : .red)
                }
            }

            Divider().background(Color.primary.opacity(0.1))

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
                Text(L("5.–95. Persentil Fiyat Araligi"))
                    .font(.caption2).foregroundColor(.primary.opacity(0.5))
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
                    Text(L("Yapay Zeka Onerisi"))
                        .font(.caption).foregroundColor(.primary.opacity(0.5))
                    Text(L(rec.action))
                        .font(.title2.bold())
                        .foregroundColor(actionColor(rec.actionCode))
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    Text(L("Birlesik Skor"))
                        .font(.caption2).foregroundColor(.primary.opacity(0.4))
                    Text("\(rec.compositeScore, specifier: "%.0f")/100")
                        .font(.headline.monospacedDigit())
                        .foregroundColor(.cyan)
                }
            }

            // Progress bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4).fill(Color.primary.opacity(0.1))
                    RoundedRectangle(cornerRadius: 4)
                        .fill(actionColor(rec.actionCode))
                        .frame(width: geo.size.width * CGFloat(rec.compositeScore / 100))
                }
            }
            .frame(height: 8)

            HStack {
                Label("\(L("Onerilen Pozisyon Buyuklugu")): %\(rec.suggestedPositionPct, specifier: "%.0f")", systemImage: "scale.3d")
                    .font(.caption)
                    .foregroundColor(.primary.opacity(0.6))
            }

            if !rec.reasons.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(L("Gerekce:"))
                        .font(.caption.bold()).foregroundColor(.primary.opacity(0.5))
                    ForEach(rec.reasons, id: \.self) { reason in
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: "circle.fill")
                                .font(.system(size: 5))
                                .foregroundColor(.cyan)
                                .padding(.top, 5)
                            Text(LD(reason)).font(.caption).foregroundColor(.primary.opacity(0.7))
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(Color.primary.opacity(0.05))
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
        Label(L(title), systemImage: icon)
            .font(.headline.bold())
            .foregroundColor(color)
    }

    @ViewBuilder
    private func metricCell(label: String, value: String, color: Color) -> some View {
        VStack(spacing: 4) {
            Text(value).font(.headline.monospacedDigit()).foregroundColor(color)
            Text(L(label)).font(.caption2).foregroundColor(.primary.opacity(0.5))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
    }

    @ViewBuilder
    private func mcMetric(_ label: String, _ value: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(value).font(.subheadline.bold().monospacedDigit()).foregroundColor(color)
            Text(L(label)).font(.caption2).foregroundColor(.primary.opacity(0.4))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.primary.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private var riskLabel: String {
        switch riskTolerance {
        case 0..<0.2: return L("Cok Dusuk")
        case 0.2..<0.4: return L("Dusuk")
        case 0.4..<0.6: return L("Orta")
        case 0.6..<0.8: return L("Yuksek")
        default: return L("Cok Yuksek")
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
