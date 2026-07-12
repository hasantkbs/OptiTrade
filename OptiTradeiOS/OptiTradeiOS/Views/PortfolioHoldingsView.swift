import SwiftUI

@MainActor
final class PortfolioHoldingsViewModel: ObservableObject {
    @Published var holdings: [PortfolioHolding] = []
    @Published var currentPrices: [UUID: Double] = [:]
    @Published var isRefreshing = false
    @Published var lastUpdated: Date?

    private let session = UserSession.shared

    init() {
        holdings = session.portfolioHoldings()
    }

    var totalCostBasis: Double {
        holdings.reduce(0) { $0 + $1.costBasis }
    }

    var totalMarketValue: Double {
        holdings.reduce(0) { total, h in
            total + h.marketValue(currentPrice: currentPrices[h.id] ?? h.purchasePrice)
        }
    }

    var totalPLAmount: Double { totalMarketValue - totalCostBasis }

    var totalPLPercent: Double {
        guard totalCostBasis > 0 else { return 0 }
        return totalPLAmount / totalCostBasis * 100
    }

    func addHolding(symbol: String, assetType: String, quantity: Double, purchasePrice: Double) {
        let s = symbol.trimmingCharacters(in: .whitespaces).uppercased()
        guard !s.isEmpty, quantity > 0, purchasePrice > 0 else { return }
        let holding = PortfolioHolding(symbol: s, assetType: assetType, quantity: quantity, purchasePrice: purchasePrice)
        holdings.append(holding)
        persist()
        Task { await refreshPrice(holding) }
    }

    func updateHolding(_ id: UUID, quantity: Double, purchasePrice: Double) {
        guard let idx = holdings.firstIndex(where: { $0.id == id }) else { return }
        holdings[idx].quantity = quantity
        holdings[idx].purchasePrice = purchasePrice
        persist()
    }

    func removeHolding(_ holding: PortfolioHolding) {
        currentPrices.removeValue(forKey: holding.id)
        holdings.removeAll { $0.id == holding.id }
        persist()
    }

    func refreshAll() async {
        isRefreshing = true
        await withTaskGroup(of: Void.self) { group in
            for holding in holdings {
                group.addTask { await self.refreshPrice(holding) }
            }
        }
        isRefreshing = false
        lastUpdated = Date()
    }

    func refreshPrice(_ holding: PortfolioHolding) async {
        guard let price = try? await APIService.shared.getPrice(symbol: holding.symbol) else { return }
        await MainActor.run { currentPrices[holding.id] = price.price }
    }

    private func persist() { session.savePortfolioHoldings(holdings) }
}

struct PortfolioHoldingsSection: View {
    @StateObject private var vm = PortfolioHoldingsViewModel()
    @State private var showAddSheet = false
    @State private var editingHolding: PortfolioHolding?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label(L("Portföyüm"), systemImage: "wallet.pass.fill")
                    .font(.headline.bold())
                    .foregroundColor(.cyan)
                Spacer()
                if vm.isRefreshing {
                    ProgressView().tint(.cyan)
                } else {
                    Button {
                        Task { await vm.refreshAll() }
                    } label: {
                        Image(systemName: "arrow.clockwise").foregroundColor(.cyan)
                    }
                }
                Button { showAddSheet = true } label: {
                    Image(systemName: "plus.circle.fill").foregroundColor(.cyan)
                }
            }

            if vm.holdings.isEmpty {
                Text(L("Portföyünüz boş. Sağ üstteki + ile sahip olduğunuz hisse veya kripto ekleyin."))
                    .font(.caption)
                    .foregroundColor(.primary.opacity(0.5))
            } else {
                summaryCard
                VStack(spacing: 10) {
                    ForEach(vm.holdings) { holding in
                        holdingRow(holding)
                            .onTapGesture { editingHolding = holding }
                    }
                }
            }
        }
        .task { await vm.refreshAll() }
        .sheet(isPresented: $showAddSheet) {
            HoldingEditSheet(mode: .add) { symbol, assetType, quantity, price in
                vm.addHolding(symbol: symbol, assetType: assetType, quantity: quantity, purchasePrice: price)
            }
        }
        .sheet(item: $editingHolding) { holding in
            HoldingEditSheet(mode: .edit(holding)) { _, _, quantity, price in
                vm.updateHolding(holding.id, quantity: quantity, purchasePrice: price)
            } onDelete: {
                vm.removeHolding(holding)
            }
        }
    }

    private var summaryCard: some View {
        HStack(spacing: 0) {
            summaryCell(label: L("Toplam Değer"), value: formatCurrency(vm.totalMarketValue))
            Divider().frame(height: 34).background(Color.primary.opacity(0.1))
            summaryCell(
                label: L("Kar/Zarar"),
                value: "\(formatCurrency(vm.totalPLAmount)) (\(String(format: "%+.1f%%", vm.totalPLPercent)))",
                color: vm.totalPLAmount >= 0 ? .green : .red
            )
        }
        .padding(.vertical, 10)
        .background(Color.primary.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func summaryCell(label: String, value: String, color: Color = .primary) -> some View {
        VStack(spacing: 4) {
            Text(value).font(.subheadline.bold().monospacedDigit()).foregroundColor(color)
            Text(label).font(.caption2).foregroundColor(.primary.opacity(0.5))
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private func holdingRow(_ holding: PortfolioHolding) -> some View {
        let currentPrice = vm.currentPrices[holding.id]
        HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                Text(holding.symbol).font(.headline).foregroundColor(.primary)
                Text("\(formatQuantity(holding.quantity)) \(L("adet")) @ \(formatCurrency(holding.purchasePrice))")
                    .font(.caption2)
                    .foregroundColor(.primary.opacity(0.5))
            }
            Spacer()
            if let price = currentPrice {
                VStack(alignment: .trailing, spacing: 4) {
                    Text(formatCurrency(price))
                        .font(.subheadline.weight(.semibold))
                        .foregroundColor(.primary)
                    let pl = holding.unrealizedPLPercent(currentPrice: price)
                    Text(String(format: "%+.1f%%", pl))
                        .font(.caption.weight(.semibold))
                        .foregroundColor(pl >= 0 ? .green : .red)
                }
            } else {
                ProgressView().tint(.cyan)
            }
            Image(systemName: "chevron.right")
                .font(.caption2)
                .foregroundColor(.primary.opacity(0.3))
        }
        .padding()
        .background(Color.primary.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private func formatCurrency(_ v: Double) -> String {
        v >= 1000 ? String(format: "%.0f", v) : String(format: "%.2f", v)
    }

    private func formatQuantity(_ v: Double) -> String {
        v == v.rounded() ? String(format: "%.0f", v) : String(format: "%.4f", v)
    }
}

private struct HoldingEditSheet: View {
    enum Mode {
        case add
        case edit(PortfolioHolding)
    }

    let mode: Mode
    let onSave: (_ symbol: String, _ assetType: String, _ quantity: Double, _ price: Double) -> Void
    var onDelete: (() -> Void)? = nil

    @Environment(\.dismiss) private var dismiss
    @State private var symbol: String
    @State private var assetType: String
    @State private var quantity: String
    @State private var price: String
    @State private var showDeleteAlert = false
    @State private var isFetchingPrice = false
    @State private var priceFetchTask: Task<Void, Never>?

    init(mode: Mode, onSave: @escaping (String, String, Double, Double) -> Void, onDelete: (() -> Void)? = nil) {
        self.mode = mode
        self.onSave = onSave
        self.onDelete = onDelete
        switch mode {
        case .add:
            _symbol = State(initialValue: "")
            _assetType = State(initialValue: "stock")
            _quantity = State(initialValue: "")
            _price = State(initialValue: "")
        case .edit(let holding):
            _symbol = State(initialValue: holding.symbol)
            _assetType = State(initialValue: holding.assetType)
            _quantity = State(initialValue: String(holding.quantity))
            _price = State(initialValue: String(holding.purchasePrice))
        }
    }

    private var isEditing: Bool {
        if case .edit = mode { return true }
        return false
    }

    private var canSave: Bool {
        !symbol.trimmingCharacters(in: .whitespaces).isEmpty
            && (Double(quantity) ?? 0) > 0
            && (Double(price) ?? 0) > 0
    }

    var body: some View {
        NavigationStack {
            Form {
                if !isEditing {
                    Section(L("Varlık Tipi")) {
                        Picker(L("Tip"), selection: $assetType) {
                            Text(L("Hisse Senedi")).tag("stock")
                            Text(L("Kripto Para")).tag("crypto")
                        }
                        .pickerStyle(.segmented)
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                    }

                    Section(L("Sembol")) {
                        TextField(assetType == "stock" ? "THYAO.IS" : "BTC-USD", text: $symbol)
                            .textInputAutocapitalization(.characters)
                            .disableAutocorrection(true)
                            .onChange(of: symbol) { scheduleFetchPrice() }
                            .onChange(of: assetType) { scheduleFetchPrice() }
                    }
                } else {
                    Section {
                        HStack {
                            Text(L("Sembol"))
                            Spacer()
                            Text(symbol).foregroundColor(.secondary)
                        }
                    }
                }

                Section(L("Miktar")) {
                    TextField(L("Örn: 10"), text: $quantity)
                        .keyboardType(.decimalPad)
                }

                Section {
                    HStack {
                        TextField(L("Örn: 285.50"), text: $price)
                            .keyboardType(.decimalPad)
                        if isFetchingPrice {
                            ProgressView()
                        }
                    }
                } header: {
                    Text(L("Alım Birim Fiyatı"))
                } footer: {
                    if !isEditing {
                        Text(L("Sembolü girince güncel fiyat otomatik doldurulur; gerekirse değiştirebilirsiniz."))
                    }
                }

                if isEditing, let onDelete {
                    Section {
                        Button(role: .destructive) {
                            showDeleteAlert = true
                        } label: {
                            Label(L("Portföyden Kaldır"), systemImage: "trash")
                        }
                    }
                    .alert(L("Bu pozisyon kaldırılsın mı?"), isPresented: $showDeleteAlert) {
                        Button(L("Kaldır"), role: .destructive) {
                            onDelete()
                            dismiss()
                        }
                        Button(L("Vazgeç"), role: .cancel) {}
                    }
                }
            }
            .navigationTitle(isEditing ? L("Pozisyonu Düzenle") : L("Pozisyon Ekle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(L("Vazgeç")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("Kaydet")) {
                        onSave(symbol, assetType, Double(quantity) ?? 0, Double(price) ?? 0)
                        dismiss()
                    }
                    .disabled(!canSave)
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func scheduleFetchPrice() {
        priceFetchTask?.cancel()
        let sym = symbol.trimmingCharacters(in: .whitespaces).uppercased()
        guard !sym.isEmpty else { return }
        priceFetchTask = Task {
            try? await Task.sleep(nanoseconds: 500_000_000)
            guard !Task.isCancelled else { return }
            await MainActor.run { isFetchingPrice = true }
            let normalized = assetType == "stock" ? TradingMarket.tr.normalizeSymbol(sym) : sym
            let result = try? await APIService.shared.getPrice(symbol: normalized)
            guard !Task.isCancelled else { return }
            await MainActor.run {
                isFetchingPrice = false
                if let result {
                    price = String(format: "%.4f", result.price)
                }
            }
        }
    }
}
