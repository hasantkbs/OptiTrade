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

