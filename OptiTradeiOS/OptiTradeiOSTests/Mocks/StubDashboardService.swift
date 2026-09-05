import Foundation
@testable import OptiTradeiOS

/// Configurable `DashboardServicing` fake — no network, no `APIClient`.
/// `delayNanoseconds` uses real `Task.sleep` (not `try?`) so task
/// cancellation genuinely propagates, matching `StubAssetDetailService`/
/// `StubAIAnalystService`.
actor StubDashboardService: DashboardServicing {
    private(set) var callCount = 0
    var result: Result<PortfolioSummary?, Error>
    var delayNanoseconds: UInt64

    init(result: Result<PortfolioSummary?, Error> = .success(nil), delayNanoseconds: UInt64 = 0) {
        self.result = result
        self.delayNanoseconds = delayNanoseconds
    }

    func fetchPortfolioSummary() async throws -> PortfolioSummary? {
        callCount += 1
        if delayNanoseconds > 0 {
            try await Task.sleep(nanoseconds: delayNanoseconds)
        }
        return try result.get()
    }

    func setResult(_ newResult: Result<PortfolioSummary?, Error>) {
        result = newResult
    }
}
