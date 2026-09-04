import Foundation
@testable import OptiTradeiOS

/// Configurable `AssetDetailServicing` fake — no network, no `APIClient`.
/// `delayNanoseconds` uses real `Task.sleep` (not `try?`) so task
/// cancellation genuinely propagates, letting tests exercise "a slower
/// request for a previous symbol must not overwrite the current one"
/// deterministically (same technique as `StubAssetSearchService`).
actor StubAssetDetailService: AssetDetailServicing {
    private(set) var callCount = 0
    private(set) var recordedSymbols: [String] = []
    /// Per-symbol result/delay overrides, consulted before the defaults
    /// below — lets a test give "AAPL" a long delay and "TSLA" a short
    /// one within the same stub.
    private var resultsBySymbol: [String: Result<AssetDetailSummary, Error>] = [:]
    private var delaysBySymbol: [String: UInt64] = [:]

    var result: Result<AssetDetailSummary, Error>
    var delayNanoseconds: UInt64

    init(result: Result<AssetDetailSummary, Error>, delayNanoseconds: UInt64 = 0) {
        self.result = result
        self.delayNanoseconds = delayNanoseconds
    }

    func fetchAssetDetail(symbol: String, assetType: String) async throws -> AssetDetailSummary {
        callCount += 1
        recordedSymbols.append(symbol)
        let delay = delaysBySymbol[symbol] ?? delayNanoseconds
        if delay > 0 {
            try await Task.sleep(nanoseconds: delay)
        }
        let outcome = resultsBySymbol[symbol] ?? result
        return try outcome.get()
    }

    func setResult(_ newResult: Result<AssetDetailSummary, Error>) {
        result = newResult
    }

    func setResult(_ newResult: Result<AssetDetailSummary, Error>, forSymbol symbol: String) {
        resultsBySymbol[symbol] = newResult
    }

    func setDelay(_ nanoseconds: UInt64, forSymbol symbol: String) {
        delaysBySymbol[symbol] = nanoseconds
    }
}
