import SwiftUI

private let bistQuickSymbols: [(symbol: String, name: String)] = [
    ("THYAO.IS", "THYAO"), ("GARAN.IS", "GARAN"), ("ASELS.IS", "ASELS"),
    ("KCHOL.IS", "KCHOL"), ("EREGL.IS", "EREGL"), ("AKBNK.IS", "AKBNK"),
    ("TUPRS.IS", "TUPRS"), ("FROTO.IS", "FROTO"), ("BIMAS.IS", "BIMAS"),
    ("PGSUS.IS", "PGSUS"), ("SISE.IS", "SISE"),  ("YKBNK.IS", "YKBNK"),
    ("ISCTR.IS", "ISCTR"), ("VESTL.IS", "VESTL"), ("TOASO.IS", "TOASO"),
    ("TTRAK.IS", "TTRAK"),
]

private let bistSectorSymbols: [(sector: String, symbols: [(symbol: String, name: String)])] = [
    ("Bankacılık", [
        ("GARAN.IS", "GARAN"), ("AKBNK.IS", "AKBNK"), ("YKBNK.IS", "YKBNK"),
        ("ISCTR.IS", "ISCTR"), ("VAKBN.IS", "VAKBN"), ("HALKB.IS", "HALKB"),
        ("TSKB.IS", "TSKB"),  ("QNBFB.IS", "QNBFB"),
    ]),
    ("Enerji", [
        ("TUPRS.IS", "TUPRS"), ("EREGL.IS", "EREGL"), ("AYGAZ.IS", "AYGAZ"),
        ("PETKIM.IS", "PETKIM"), ("AKSEN.IS", "AKSEN"), ("ENKAI.IS", "ENKAI"),
    ]),
    ("Ulaşım", [
        ("THYAO.IS", "THYAO"), ("PGSUS.IS", "PGSUS"), ("TAVHL.IS", "TAVHL"),
    ]),
    ("Teknoloji", [
        ("ASELS.IS", "ASELS"), ("NETAS.IS", "NETAS"), ("LOGO.IS", "LOGO"),
        ("ALCTL.IS", "ALCTL"), ("ARDYZ.IS", "ARDYZ"),
    ]),
    ("Sanayi", [
        ("KCHOL.IS", "KCHOL"), ("SISE.IS", "SISE"),  ("FROTO.IS", "FROTO"),
        ("TOASO.IS", "TOASO"), ("TTRAK.IS", "TTRAK"), ("VESTL.IS", "VESTL"),
    ]),
    ("Perakende", [
        ("BIMAS.IS", "BIMAS"), ("MGROS.IS", "MGROS"), ("MAVI.IS", "MAVI"),
        ("ARCLK.IS", "ARCLK"),
    ]),
]

private let cryptoQuickSymbols: [(symbol: String, name: String)] = [
    ("BTC-USD", "BTC"), ("ETH-USD", "ETH"), ("BNB-USD", "BNB"),
    ("SOL-USD", "SOL"), ("AVAX-USD", "AVAX"), ("XRP-USD", "XRP"),
    ("ADA-USD", "ADA"), ("DOT-USD", "DOT"), ("LINK-USD", "LINK"),
]

@MainActor
final class SearchViewModel: ObservableObject {
    @Published var symbol: String = ""
    @Published var potentialPrice: String = ""
    @Published var assetType: String = "stock"
    @Published var result: AnalysisResult?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var searchHistory: [SearchHistoryItem] = []
    @Published var navigateToDetail = false

    private let session = UserSession.shared

    init() {
        searchHistory = session.searchHistory()
        assetType = session.defaultAssetType
    }

    var suggestions: [(symbol: String, name: String)] {
        let pool = assetType == "stock" ? bistQuickSymbols : cryptoQuickSymbols
        guard !symbol.isEmpty else { return [] }
        let q = symbol.uppercased()
        return pool.filter { $0.symbol.contains(q) || $0.name.contains(q) }
    }

    var quickSymbols: [(symbol: String, name: String)] {
        assetType == "stock" ? bistQuickSymbols : cryptoQuickSymbols
    }

    func analyze() async {
        let trimmed = symbol.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        isLoading = true
        errorMessage = nil
        result = nil
        do {
            let r = try await APIService.shared.analyze(
                symbol: trimmed.uppercased(),
                potentialPrice: Double(potentialPrice),
                assetType: assetType
            )
            result = r
            session.addSearchHistory(SearchHistoryItem(from: r))
            searchHistory = session.searchHistory()
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func fillSymbol(_ s: String, type: String) {
        symbol = s
        assetType = type
    }

    func clearHistory() {
        session.clearSearchHistory()
        searchHistory = []
    }
}

struct SearchView: View {
    @StateObject private var vm = SearchViewModel()
    @FocusState private var fieldFocused: Bool
    @State private var selectedResult: AnalysisResult?
    @State private var selectedSector = "Tümü"

    private var bistSectors: [String] {
        ["Tümü"] + bistSectorSymbols.map(\.sector)
    }

    private var filteredBISTSymbols: [(symbol: String, name: String)] {
        if selectedSector == "Tümü" { return bistQuickSymbols }
        return bistSectorSymbols.first(where: { $0.sector == selectedSector })?.symbols ?? []
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    searchCard
                    if vm.isLoading {
                        loadingView
                    } else if let error = vm.errorMessage {
                        errorView(error)
                    } else if let result = vm.result {
                        resultSection(result)
                    } else if !vm.symbol.isEmpty && !vm.suggestions.isEmpty {
                        suggestionsSection
                    } else if vm.symbol.isEmpty {
                        if !vm.searchHistory.isEmpty {
                            historySection
                        }
                        quickAccessSection
                    }
                }
                .padding()
                .padding(.bottom, 32)
            }
            .navigationTitle("Hisse Analizi")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                if !vm.symbol.isEmpty {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("Temizle") {
                            vm.symbol = ""
                            vm.potentialPrice = ""
                            vm.result = nil
                            vm.errorMessage = nil
                        }
                        .font(.subheadline)
                    }
                }
            }
        }
    }

    private var searchCard: some View {
        VStack(spacing: 12) {
            Picker("Varlık Tipi", selection: $vm.assetType) {
                Text("Hisse Senedi").tag("stock")
                Text("Kripto Para").tag("crypto")
            }
            .pickerStyle(.segmented)
            .onChange(of: vm.assetType) {
                vm.symbol = ""
                vm.result = nil
                vm.errorMessage = nil
            }

            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.secondary)
                TextField(
                    vm.assetType == "stock" ? "THYAO.IS, GARAN.IS..." : "BTC-USD, ETH-USD...",
                    text: $vm.symbol
                )
                .textInputAutocapitalization(.characters)
                .disableAutocorrection(true)
                .focused($fieldFocused)
                .submitLabel(.search)
                .onSubmit { Task { await vm.analyze() } }

                if !vm.symbol.isEmpty {
                    Button {
                        vm.symbol = ""
                        vm.result = nil
                        vm.errorMessage = nil
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.secondary)
                    }
                }
            }
            .padding(12)
            .background(Color(.tertiarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 12))

            HStack(spacing: 10) {
                Image(systemName: "target")
                    .foregroundColor(.secondary)
                TextField("Potansiyel fiyat (opsiyonel)", text: $vm.potentialPrice)
                    .keyboardType(.decimalPad)
            }
            .padding(12)
            .background(Color(.tertiarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 12))

            Button {
                fieldFocused = false
                Task { await vm.analyze() }
            } label: {
                HStack(spacing: 8) {
                    if vm.isLoading {
                        ProgressView().tint(.white)
                    } else {
                        Image(systemName: "chart.xyaxis.line")
                    }
                    Text(vm.isLoading ? "Analiz ediliyor..." : "Analiz Et")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .padding(14)
                .background(vm.symbol.isEmpty ? Color.gray : Color.accentColor)
                .foregroundColor(.white)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .disabled(vm.symbol.isEmpty)
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
                .scaleEffect(1.3)
            Text("Analiz ediliyor...")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(40)
    }

    private func errorView(_ error: String) -> some View {
        VStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.largeTitle)
                .foregroundColor(.orange)
            Text(error)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Button("Tekrar Dene") { Task { await vm.analyze() } }
                .font(.subheadline.weight(.medium))
                .foregroundColor(.accentColor)
        }
        .padding(20)
        .frame(maxWidth: .infinity)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private func resultSection(_ result: AnalysisResult) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Analiz Sonucu")
                .font(.headline)
                .padding(.leading, 4)
            NavigationLink(destination: AnalysisDetailView(result: result)) {
                ResultCardView(result: result)
            }
            .buttonStyle(.plain)
        }
    }

    private var suggestionsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Öneriler")
                .font(.subheadline.weight(.semibold))
                .foregroundColor(.secondary)
                .padding(.leading, 4)
            VStack(spacing: 4) {
                ForEach(vm.suggestions, id: \.symbol) { s in
                    Button {
                        vm.symbol = s.symbol
                        fieldFocused = false
                        Task { await vm.analyze() }
                    } label: {
                        HStack {
                            Image(systemName: "magnifyingglass")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text(s.symbol)
                                .font(.subheadline.weight(.medium))
                                .foregroundColor(.primary)
                            Text(s.name)
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Spacer()
                            Image(systemName: "arrow.up.left")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                    }
                    if s.symbol != vm.suggestions.last?.symbol {
                        Divider().padding(.leading, 38)
                    }
                }
            }
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    private var historySection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Son Aramalar")
                    .font(.subheadline.weight(.semibold))
                    .foregroundColor(.secondary)
                Spacer()
                Button("Temizle") { vm.clearHistory() }
                    .font(.caption)
                    .foregroundColor(.accentColor)
            }
            .padding(.horizontal, 4)

            FlowLayout(spacing: 8) {
                ForEach(vm.searchHistory) { item in
                    SearchHistoryTag(
                        item: item,
                        onTap: {
                            vm.fillSymbol(item.symbol, type: item.assetType)
                            Task { await vm.analyze() }
                        },
                        onDelete: {
                            var h = UserSession.shared.searchHistory()
                            h.removeAll { $0.id == item.id }
                            if let data = try? JSONEncoder().encode(h) {
                                UserDefaults.standard.set(data, forKey: "search_history")
                            }
                            Task { try? await FirebaseService.shared.addSearchHistory(item) }
                            vm.searchHistory = UserSession.shared.searchHistory()
                        }
                    )
                }
            }
        }
    }

    private var quickAccessSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            if vm.assetType == "stock" {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(bistSectors, id: \.self) { sector in
                            SectorChip(title: sector, isSelected: selectedSector == sector) {
                                withAnimation(.easeInOut(duration: 0.2)) {
                                    selectedSector = sector
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 4)
                }
            }

            Text(vm.assetType == "stock" ? "Popüler BIST Hisseleri" : "Popüler Kriptolar")
                .font(.subheadline.weight(.semibold))
                .foregroundColor(.secondary)
                .padding(.horizontal, 4)

            let symbols = vm.assetType == "stock" ? filteredBISTSymbols : vm.quickSymbols
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 4), spacing: 8) {
                ForEach(symbols, id: \.symbol) { s in
                    QuickSymbolButton(symbol: s.symbol, displayName: s.name) {
                        vm.fillSymbol(s.symbol, type: vm.assetType)
                        fieldFocused = false
                        Task { await vm.analyze() }
                    }
                }
            }
        }
    }
}

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = computeRows(proposal: proposal, subviews: subviews)
        let height = rows.map { $0.map { $0.sizeThatFits(.unspecified).height }.max() ?? 0 }
            .reduce(0) { $0 + $1 + spacing } - spacing
        return CGSize(width: proposal.width ?? 0, height: max(height, 0))
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let rows = computeRows(proposal: ProposedViewSize(width: bounds.width, height: nil), subviews: subviews)
        var y = bounds.minY
        for row in rows {
            let rowHeight = row.map { $0.sizeThatFits(.unspecified).height }.max() ?? 0
            var x = bounds.minX
            for view in row {
                let size = view.sizeThatFits(.unspecified)
                view.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += rowHeight + spacing
        }
    }

    private func computeRows(proposal: ProposedViewSize, subviews: Subviews) -> [[LayoutSubviews.Element]] {
        var rows: [[LayoutSubviews.Element]] = [[]]
        var x: CGFloat = 0
        let maxWidth = proposal.width ?? .infinity
        for view in subviews {
            let w = view.sizeThatFits(.unspecified).width
            if x + w > maxWidth && !rows[rows.count - 1].isEmpty {
                rows.append([])
                x = 0
            }
            rows[rows.count - 1].append(view)
            x += w + spacing
        }
        return rows
    }
}
