import Foundation
@testable import OptiTradeiOS

/// Configurable `AIAnalystServicing` fake — no network, no `APIClient`.
/// Same per-symbol result/delay override shape as `StubAssetDetailService`
/// (used identically to test asset-switching/stale-response protection).
actor StubAIAnalystService: AIAnalystServicing {
    private(set) var callCount = 0
    private(set) var recordedSymbols: [String] = []
    private var resultsBySymbol: [String: Result<AIAnalystExplanation?, Error>] = [:]
    private var delaysBySymbol: [String: UInt64] = [:]

    var result: Result<AIAnalystExplanation?, Error>
    var delayNanoseconds: UInt64

    init(result: Result<AIAnalystExplanation?, Error>, delayNanoseconds: UInt64 = 0) {
        self.result = result
        self.delayNanoseconds = delayNanoseconds
    }

    func fetchExplanation(symbol: String, assetType: String) async throws -> AIAnalystExplanation? {
        callCount += 1
        recordedSymbols.append(symbol)
        let delay = delaysBySymbol[symbol] ?? delayNanoseconds
        if delay > 0 {
            try await Task.sleep(nanoseconds: delay)
        }
        let outcome = resultsBySymbol[symbol] ?? result
        return try outcome.get()
    }

    func setResult(_ newResult: Result<AIAnalystExplanation?, Error>) {
        result = newResult
    }

    func setResult(_ newResult: Result<AIAnalystExplanation?, Error>, forSymbol symbol: String) {
        resultsBySymbol[symbol] = newResult
    }

    func setDelay(_ nanoseconds: UInt64, forSymbol symbol: String) {
        delaysBySymbol[symbol] = nanoseconds
    }
}
