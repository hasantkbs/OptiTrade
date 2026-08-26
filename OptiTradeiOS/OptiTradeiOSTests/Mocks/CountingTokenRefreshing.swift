import Foundation
@testable import OptiTradeiOS

/// Counts how many times `refresh(refreshToken:)` actually ran, with an
/// artificial delay so concurrent callers genuinely overlap in tests —
/// without the delay, a single-threaded test runner could serialize calls
/// by accident and hide a missing single-flight guarantee.
actor CountingTokenRefreshing: TokenRefreshing {
    private(set) var callCount = 0
    private let delayNanoseconds: UInt64
    private let result: Result<AuthTokens, Error>

    init(delayNanoseconds: UInt64 = 20_000_000, result: Result<AuthTokens, Error>) {
        self.delayNanoseconds = delayNanoseconds
        self.result = result
    }

    func refresh(refreshToken: String) async throws -> AuthTokens {
        callCount += 1
        try? await Task.sleep(nanoseconds: delayNanoseconds)
        return try result.get()
    }
}
