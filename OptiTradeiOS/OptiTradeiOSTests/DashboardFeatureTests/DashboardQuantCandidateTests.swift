import Foundation
import Testing
@testable import OptiTradeiOS

/// `DashboardQuantCandidate` is the navigation-model mapping between real
/// Watchlist data and the strongly-typed `AssetSelection` Asset Detail/AI
/// Analyst require — verifies it carries only what `WatchlistAssetItem`
/// actually has (no invented name/market/currency).
struct DashboardQuantCandidateTests {
    @Test
    func candidateCarriesTheRealSymbolFromTheWatchlistItem() {
        let item = WatchlistItemDTO(id: 1, watchlistId: 1, symbol: "AAPL", isFavorite: true, folder: nil, tags: [], notes: "")
        let candidate = DashboardQuantCandidate(item: WatchlistAssetItem(dto: item))

        #expect(candidate.symbol == "AAPL")
        #expect(candidate.id == "AAPL")
    }

    @Test
    func assetSelectionFromACandidateHasNoInventedMetadata() {
        let item = WatchlistItemDTO(id: 1, watchlistId: 1, symbol: "TSLA", isFavorite: false, folder: nil, tags: [], notes: "")
        let candidate = DashboardQuantCandidate(item: WatchlistAssetItem(dto: item))

        let selection = candidate.assetSelection

        #expect(selection.symbol == "TSLA")
        #expect(selection.name == nil)
        #expect(selection.market == nil)
        #expect(selection.currency == nil)
        #expect(selection.assetType == "stock") // backend's own default, not a guess
    }
}
