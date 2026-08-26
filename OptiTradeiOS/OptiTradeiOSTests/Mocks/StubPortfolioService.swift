import Foundation
@testable import OptiTradeiOS

/// Configurable `PortfolioServicing` fake — no network, no `APIClient`.
actor StubPortfolioService: PortfolioServicing {
    private(set) var callCount = 0
    var result: Result<PortfolioSummary?, Error>
    var delayNanoseconds: UInt64

    init(result: Result<PortfolioSummary?, Error> = .success(nil), delayNanoseconds: UInt64 = 0) {
        self.result = result
        self.delayNanoseconds = delayNanoseconds
    }

    func fetchPrimaryPortfolio() async throws -> PortfolioSummary? {
        callCount += 1
        if delayNanoseconds > 0 { try? await Task.sleep(nanoseconds: delayNanoseconds) }
        return try result.get()
    }
}
