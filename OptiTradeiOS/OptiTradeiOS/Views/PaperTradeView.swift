import SwiftUI

struct PaperTradeView: View {
    @EnvironmentObject private var session: UserSession
    @State private var trades: [PaperTrade] = []
    @State private var showNewTrade = false
    @State private var selectedTab = 0

    var openTrades: [PaperTrade]   { trades.filter { $0.isOpen } }
    var closedTrades: [PaperTrade] { trades.filter { !$0.isOpen } }

    // Ağırlıklı P&L: her pozisyonun entry×qty toplamı üzerinden gerçek getiri
    var totalPL: Double {
        let closed = closedTrades
        guard !closed.isEmpty else { return 0 }
        let totalInvested = closed.reduce(0.0) { $0 + $1.entryPrice * $1.quantity }
        guard totalInvested > 0 else { return 0 }
        let totalGain = closed.reduce(0.0) { acc, t in
            guard let exit = t.exitPrice else { return acc }
            let gain = t.direction == .long
                ? (exit - t.entryPrice) * t.quantity
                : (t.entryPrice - exit) * t.quantity
            return acc + gain
        }
        return (totalGain / totalInvested) * 100
    }

    var winRate: Double {
        let closed = closedTrades.filter { $0.exitPrice != nil }
        guard !closed.isEmpty else { return 0 }
        let wins = closed.filter { $0.finalPLPercent > 0 }.count
        return Double(wins) / Double(closed.count) * 100
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                summaryBar
                tabPicker
                    .padding(.horizontal)
                    .padding(.top, 8)

                if selectedTab == 0 {
                    openTradesList
                } else {
                    closedTradesList
                }
            }
            .navigationTitle("Beta Trade")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button { showNewTrade = true } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showNewTrade, onDismiss: { trades = session.paperTrades() }) {
                NewTradeSheet()
                    .environmentObject(session)
            }
            .onAppear { trades = session.paperTrades() }
        }
    }

    private var summaryBar: some View {
        HStack(spacing: 0) {
            summaryCard(title: "Açık İşlem", value: "\(openTrades.count)", color: .accentColor)
            Divider().frame(height: 40)
            summaryCard(title: "Kapalı", value: "\(closedTrades.count)", color: .secondary)
            Divider().frame(height: 40)
            summaryCard(
                title: "Win Rate",
                value: String(format: "%.0f%%", winRate),
                color: winRate >= 50 ? .green : .red
            )
            Divider().frame(height: 40)
            summaryCard(
                title: "Ağırlıklı K/Z",
                value: String(format: "%+.1f%%", totalPL),
                color: totalPL >= 0 ? .green : .red
            )
        }
        .padding(.vertical, 12)
        .background(Color(.secondarySystemBackground))
    }

    private func summaryCard(title: String, value: String, color: Color) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.headline.monospacedDigit())
                .foregroundColor(color)
            Text(title)
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private var tabPicker: some View {
        Picker("", selection: $selectedTab) {
            Text("Açık (\(openTrades.count))").tag(0)
            Text("Kapalı (\(closedTrades.count))").tag(1)
        }
        .pickerStyle(.segmented)
    }

    private var openTradesList: some View {
        Group {
            if openTrades.isEmpty {
                emptyState(
                    icon: "chart.line.uptrend.xyaxis",
                    title: "Açık İşlem Yok",
                    subtitle: "Yeni bir işlem açmak için + butonuna dokun."
                )
            } else {
                List {
                    ForEach(openTrades) { trade in
                        OpenTradeRow(trade: trade) {
                            closeTrade(trade)
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
    }

    private var closedTradesList: some View {
        Group {
            if closedTrades.isEmpty {
                emptyState(
                    icon: "clock.arrow.circlepath",
                    title: "Kapalı İşlem Yok",
                    subtitle: "Kapattığınız işlemler burada görünür."
                )
            } else {
                List {
                    ForEach(closedTrades) { trade in
                        ClosedTradeRow(trade: trade)
                    }
                }
                .listStyle(.plain)
            }
        }
    }

    private func closeTrade(_ trade: PaperTrade) {
        Task {
            var updatedTrade = trade
            if let price = try? await APIService.shared.getPrice(symbol: trade.symbol) {
                updatedTrade.exitPrice = price.price
            }
            updatedTrade.exitDate = Date()
            updatedTrade.isOpen = false
            var all = session.paperTrades()
            if let idx = all.firstIndex(where: { $0.id == trade.id }) {
                all[idx] = updatedTrade
            }
            session.savePaperTrades(all)
            await MainActor.run { trades = session.paperTrades() }
        }
    }

    private func emptyState(icon: String, title: String, subtitle: String) -> some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: icon)
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            VStack(spacing: 6) {
                Text(title).font(.headline)
                Text(subtitle).font(.subheadline).foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
            }
            Spacer()
        }
        .padding(.horizontal, 32)
    }
}

struct OpenTradeRow: View {
    let trade: PaperTrade
    let onClose: () -> Void
    @State private var currentPrice: Double? = nil
    @State private var loadingPrice = false

    var unrealizedPL: Double {
        guard let price = currentPrice else { return 0 }
        return trade.direction == .long
            ? (price - trade.entryPrice) / trade.entryPrice * 100
            : (trade.entryPrice - price) / trade.entryPrice * 100
    }

    var body: some View {
        HStack(spacing: 12) {
            directionBadge
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(trade.symbol).font(.headline)
                    Spacer()
                    if loadingPrice {
                        ProgressView().scaleEffect(0.7)
                    } else if currentPrice != nil {
                        Text(String(format: "%+.1f%%", unrealizedPL))
                            .font(.subheadline.monospacedDigit())
                            .foregroundColor(unrealizedPL >= 0 ? .green : .red)
                    }
                }
                HStack {
                    Text("Giriş: \(String(format: "%.2f", trade.entryPrice))")
                        .font(.caption).foregroundColor(.secondary)
                    Text("×\(String(format: "%.2f", trade.quantity))")
                        .font(.caption).foregroundColor(.secondary)
                    Spacer()
                    Button("Kapat", action: onClose)
                        .font(.caption.weight(.medium))
                        .foregroundColor(.white)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(Color.red.opacity(0.8))
                        .clipShape(Capsule())
                }
            }
        }
        .padding(.vertical, 6)
        .task { await fetchPrice() }
    }

    private var directionBadge: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 8)
                .fill(trade.direction == .long ? Color.green.opacity(0.15) : Color.red.opacity(0.15))
                .frame(width: 40, height: 40)
            Image(systemName: trade.direction.icon)
                .foregroundColor(trade.direction == .long ? .green : .red)
        }
    }

    private func fetchPrice() async {
        loadingPrice = true
        currentPrice = try? await APIService.shared.getPrice(symbol: trade.symbol).price
        loadingPrice = false
    }
}

struct ClosedTradeRow: View {
    let trade: PaperTrade

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(trade.finalPLPercent >= 0 ? Color.green.opacity(0.12) : Color.red.opacity(0.12))
                    .frame(width: 40, height: 40)
                Image(systemName: trade.direction.icon)
                    .foregroundColor(trade.finalPLPercent >= 0 ? .green : .red)
            }
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(trade.symbol).font(.headline)
                    Spacer()
                    Text(String(format: "%+.1f%%", trade.finalPLPercent))
                        .font(.subheadline.monospacedDigit())
                        .foregroundColor(trade.finalPLPercent >= 0 ? .green : .red)
                }
                HStack {
                    Text("Giriş: \(String(format: "%.2f", trade.entryPrice))")
                        .font(.caption).foregroundColor(.secondary)
                    if let exit = trade.exitPrice {
                        Text("→ \(String(format: "%.2f", exit))")
                            .font(.caption).foregroundColor(.secondary)
                    }
                }
            }
        }
        .padding(.vertical, 6)
    }
}

struct NewTradeSheet: View {
    @EnvironmentObject private var session: UserSession
    @Environment(\.dismiss) private var dismiss
    @State private var symbol = ""
    @State private var direction: PaperTrade.TradeDirection = .long
    @State private var quantity = "1"
    @State private var assetType = "stock"
    @State private var fetchedPrice: Double? = nil
    @State private var fetchState: FetchState = .idle
    @State private var errorMessage: String? = nil

    enum FetchState { case idle, loading, done, error }

    var canSubmit: Bool {
        !symbol.isEmpty && fetchedPrice != nil && (Double(quantity) ?? 0) > 0
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Sembol") {
                    HStack {
                        TextField("Örn: THYAO.IS veya BTC-USD", text: $symbol)
                            .textInputAutocapitalization(.characters)
                            .disableAutocorrection(true)
                            .onChange(of: symbol) {
                                fetchedPrice = nil
                                fetchState = .idle
                            }
                        Button {
                            fetchCurrentPrice()
                        } label: {
                            if fetchState == .loading {
                                ProgressView().scaleEffect(0.8)
                            } else {
                                Image(systemName: fetchState == .done ? "checkmark.circle.fill" : "arrow.down.circle")
                                    .foregroundColor(fetchState == .done ? .green : .accentColor)
                            }
                        }
                        .disabled(symbol.isEmpty || fetchState == .loading)
                    }

                    if let price = fetchedPrice {
                        HStack {
                            Text("Güncel Fiyat")
                            Spacer()
                            Text(String(format: "%.4f", price))
                                .foregroundColor(.secondary)
                                .monospacedDigit()
                        }
                    }
                    if let err = errorMessage {
                        Text(err).font(.caption).foregroundColor(.red)
                    }
                }

                Section("Yön") {
                    Picker("Yön", selection: $direction) {
                        ForEach(PaperTrade.TradeDirection.allCases, id: \.self) { d in
                            Label(d.label, systemImage: d.icon).tag(d)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                Section("Ayrıntılar") {
                    Picker("Varlık Türü", selection: $assetType) {
                        Text("Hisse Senedi").tag("stock")
                        Text("Kripto Para").tag("crypto")
                    }
                    HStack {
                        Text("Miktar")
                        Spacer()
                        TextField("1", text: $quantity)
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                            .frame(width: 100)
                    }
                }
            }
            .navigationTitle("Yeni Beta Trade")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("İptal") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Aç") {
                        openTrade()
                    }
                    .disabled(!canSubmit)
                    .fontWeight(.semibold)
                }
            }
        }
    }

    private func fetchCurrentPrice() {
        fetchState = .loading
        errorMessage = nil
        let sym = symbol.trimmingCharacters(in: .whitespaces)
        Task {
            do {
                let resp = try await APIService.shared.getPrice(symbol: sym)
                // Analiz skorunu da paralel çek
                let analysis = try? await APIService.shared.analyze(
                    symbol: sym, assetType: assetType
                )
                await MainActor.run {
                    fetchedPrice = resp.price
                    fetchState = .done
                    if let a = analysis {
                        liveAnalysisScore = a.score
                        liveDecisionCode  = a.decisionCode
                    }
                }
            } catch {
                await MainActor.run {
                    fetchState = .error
                    errorMessage = "Fiyat alınamadı: \(error.localizedDescription)"
                }
            }
        }
    }

    @State private var liveAnalysisScore: Int = 0
    @State private var liveDecisionCode: String = "NEUTRAL"

    private func openTrade() {
        guard let price = fetchedPrice, let qty = Double(quantity), qty > 0 else { return }
        let trade = PaperTrade(
            id: UUID(),
            symbol: symbol.uppercased(),
            assetType: assetType,
            direction: direction,
            entryPrice: price,
            quantity: qty,
            entryDate: Date(),
            exitPrice: nil,
            exitDate: nil,
            isOpen: true,
            analysisScore: liveAnalysisScore,
            decisionCode: liveDecisionCode
        )
        var all = session.paperTrades()
        all.insert(trade, at: 0)
        session.savePaperTrades(all)
        dismiss()
    }
}
