import Foundation
import Testing
@testable import OptiTradeiOS

/// `AssetSelection` is the strongly-typed navigation payload Step 4's spec
/// requires in place of a dictionary. These verify it carries the real
/// backend symbol from both sources that can produce one: a fully-detailed
/// Asset Search result, and a bare Watchlist row (which the backend never
/// returns a name/market/currency for).
struct AssetSelectionTests {
    @Test
    func selectionFromASearchResultCarriesEveryKnownField() {
        let result = AssetSearchResult(symbol: "AAPL", name: "Apple", market: "US", currency: "USD")

        let selection = AssetSelection(searchResult: result)

        #expect(selection.symbol == "AAPL")
        #expect(selection.name == "Apple")
        #expect(selection.market == "US")
        #expect(selection.currency == "USD")
    }

    @Test
    func selectionFromAWatchlistRowCarriesOnlyTheSymbolItActuallyHas() {
        let selection = AssetSelection(symbol: "AAPL")

        #expect(selection.symbol == "AAPL")
        #expect(selection.name == nil)
        #expect(selection.market == nil)
        #expect(selection.currency == nil)
    }

    @Test
    func selectionsWithTheSameSymbolAreEqualRegardlessOfSource() {
        let fromSearch = AssetSelection(searchResult: AssetSearchResult(symbol: "AAPL", name: "Apple", market: "US", currency: "USD"))
        let fromWatchlist = AssetSelection(symbol: "AAPL")

        #expect(fromSearch != fromWatchlist) // different metadata -> not Equatable-equal
        #expect(fromSearch.id == fromWatchlist.id) // same identity for navigation purposes
    }
}
