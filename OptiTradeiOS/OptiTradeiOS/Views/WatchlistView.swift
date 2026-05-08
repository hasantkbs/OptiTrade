import SwiftUI

@MainActor
final class WatchlistViewModel: ObservableObject {
    @Published var items: [WatchlistItemData] = []
    @Published var results: [UUID: AnalysisResult] = [:]
    @Published var isAnalyzing = false
    @Published var lastUpdated: Date?

    private let session = UserSession.shared

    init() {
        items = session.watchlist()
    }

    func addItem(_ symbol: String, potential: Double?, assetType: String) {
        guard !items.contains(where: { $0.symbol == symbol.uppercased() }) else { return }
        let item = WatchlistItemData(symbol: symbol.uppercased(), potentialPrice: potential, assetType: assetType)
        items.append(item)
        persist()
        Task { await analyzeItem(item) }
    }

    func removeItems(at offsets: IndexSet) {
        for i in offsets { results.removeValue(forKey: items[i].id) }
        items.remove(atOffsets: offsets)
        persist()
    }

    func removeItem(_ item: WatchlistItemData) {
        results.removeValue(forKey: item.id)
        items.removeAll { $0.id == item.id }
        persist()
    }

    func move(from source: IndexSet, to destination: Int) {
        items.move(fromOffsets: source, toOffset: destination)
        persist()
    }

    func analyzeAll() async {
        isAnalyzing = true
        await withTaskGroup(of: Void.self) { group in
            for item in items {
                group.addTask { await self.analyzeItem(item) }
            }
        }
        isAnalyzing = false
        lastUpdated = Date()
    }

    func analyzeItem(_ item: WatchlistItemData) async {
        do {
            let r = try await APIService.shared.analyze(
                symbol: item.symbol,
                potentialPrice: item.potentialPrice,
                assetType: item.assetType
            )
            await MainActor.run { results[item.id] = r }
        } catch {}
    }

    private func persist() { session.saveWatchlist(items) }

    var sortedItems: [WatchlistItemData] {
        items.sorted {
            let a = results[$0.id]?.score ?? 0
            let b = results[$1.id]?.score ?? 0
            return a > b
        }
    }
}

struct WatchlistView: View {
    @StateObject private var vm = WatchlistViewModel()
    @State private var showAddSheet = false
    @State private var newSymbol = ""
    @State private var newPotential = ""
    @State private var newAssetType = "stock"
    @State private var editMode: EditMode = .inactive

    private var displayItems: [WatchlistItemData] {
        editMode == .active ? vm.items : vm.sortedItems
    }

    var body: some View {
        NavigationStack {
            Group {
                if vm.items.isEmpty {
                    EmptyStateView(
                        icon: "star.circle",
                        title: "Takip listesi boş",
                        subtitle: "Sağ üstteki + butonuyla hisse veya kripto ekleyin"
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    listContent
                }
            }
            .navigationTitle("Takip Listesi")
            .toolbar { toolbarContent }
            .sheet(isPresented: $showAddSheet) { addSheet }
            .environment(\.editMode, $editMode)
        }
    }

    private var listContent: some View {
        List {
            if let updated = vm.lastUpdated {
                HStack {
                    Spacer()
                    Text("Güncellendi: \(updated, style: .time)")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    Spacer()
                }
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
            }

            ForEach(displayItems) { item in
                Group {
                    if let result = vm.results[item.id] {
                        NavigationLink(destination: AnalysisDetailView(result: result)) {
                            ResultCardView(result: result)
                        }
                        .buttonStyle(.plain)
                    } else {
                        pendingCard(item: item)
                    }
                }
                .listRowInsets(EdgeInsets(top: 5, leading: 16, bottom: 5, trailing: 16))
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                    Button(role: .destructive) {
                        withAnimation { vm.removeItem(item) }
                    } label: {
                        Label("Sil", systemImage: "trash")
                    }
                }
                .swipeActions(edge: .leading, allowsFullSwipe: false) {
                    Button {
                        Task { await vm.analyzeItem(item) }
                    } label: {
                        Label("Güncelle", systemImage: "arrow.clockwise")
                    }
                    .tint(.blue)
                }
            }
            .onMove(perform: vm.move)
        }
        .listStyle(.plain)
        .refreshable { await vm.analyzeAll() }
    }

    private func pendingCard(item: WatchlistItemData) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(item.symbol)
                    .font(.headline)
                Text(item.assetType == "stock" ? "Hisse Senedi" : "Kripto Para")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Spacer()
            if vm.isAnalyzing {
                ProgressView().tint(.accentColor)
            } else {
                Text("Analiz bekleniyor")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal)
    }

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .navigationBarLeading) {
            if !vm.items.isEmpty {
                Button(editMode == .active ? "Tamam" : "Düzenle") {
                    withAnimation {
                        editMode = editMode == .active ? .inactive : .active
                    }
                }
                .font(.subheadline)
            }
        }
        ToolbarItem(placement: .navigationBarTrailing) {
            HStack(spacing: 14) {
                if !vm.items.isEmpty && editMode != .active {
                    if vm.isAnalyzing {
                        ProgressView().tint(.accentColor)
                    } else {
                        Button {
                            Task { await vm.analyzeAll() }
                        } label: {
                            Image(systemName: "arrow.clockwise")
                        }
                    }
                }
                Button { showAddSheet = true } label: {
                    Image(systemName: "plus")
                }
            }
        }
    }

    private var addSheet: some View {
        NavigationStack {
            Form {
                Section("Varlık Tipi") {
                    Picker("Tip", selection: $newAssetType) {
                        Text("Hisse Senedi").tag("stock")
                        Text("Kripto Para").tag("crypto")
                    }
                    .pickerStyle(.segmented)
                    .listRowInsets(EdgeInsets())
                    .listRowBackground(Color.clear)
                }

                Section("Sembol") {
                    TextField(newAssetType == "stock" ? "THYAO.IS" : "BTC-USD", text: $newSymbol)
                        .textInputAutocapitalization(.characters)
                        .disableAutocorrection(true)
                }

                Section {
                    TextField("Örn: 350 (opsiyonel)", text: $newPotential)
                        .keyboardType(.decimalPad)
                } header: {
                    Text("Potansiyel Fiyat")
                } footer: {
                    Text("Potansiyel fiyat girilirse ucuz/pahalı analizi yapılır.")
                }
            }
            .navigationTitle("Sembol Ekle")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Vazgeç") {
                        showAddSheet = false
                        newSymbol = ""
                        newPotential = ""
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Ekle") {
                        vm.addItem(newSymbol, potential: Double(newPotential), assetType: newAssetType)
                        newSymbol = ""
                        newPotential = ""
                        showAddSheet = false
                    }
                    .disabled(newSymbol.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
        .presentationDetents([.medium])
    }
}
