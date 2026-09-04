import Foundation
@testable import OptiTradeiOS

/// Configurable `AssetSearchServicing` fake — no network, no `APIClient`.
/// `delayNanoseconds` uses real `Task.sleep` (not `try?`) so a caller's
/// task cancellation genuinely propagates as `CancellationError`, letting
/// tests exercise "stale search cancelled" behavior deterministically.
actor StubAssetSearchService: AssetSearchServicing {
    private(set) var callCount = 0
    private(set) var recordedQueries: [String] = []
    var result: Result<[AssetSearchResult], Error>
    var delayNanoseconds: UInt64

    init(result: Result<[AssetSearchResult], Error> = .success([]), delayNanoseconds: UInt64 = 0) {
        self.result = result
        self.delayNanoseconds = delayNanoseconds
    }

    func search(query: String, market: String) async throws -> [AssetSearchResult] {
        callCount += 1
        recordedQueries.append(query)
        if delayNanoseconds > 0 {
            try await Task.sleep(nanoseconds: delayNanoseconds)
        }
        return try result.get()
    }

    func setResult(_ newResult: Result<[AssetSearchResult], Error>) {
        result = newResult
    }

    func setDelay(_ nanoseconds: UInt64) {
        delayNanoseconds = nanoseconds
    }
}
