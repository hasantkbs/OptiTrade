import Foundation
@testable import OptiTradeiOS

/// Purpose-built fake for exercising `APIClient`'s coordinated-refresh path
/// under real concurrency. Routes by request identity rather than call
/// order, since concurrent requests can arrive in any sequence:
///
///   - `POST /auth/refresh` always succeeds and counts how many times it
///     was actually called.
///   - Any other request is identified by its `X-Test-Request-Id` header;
///     its *first* attempt returns 401, its *second* attempt (the retry
///     after refresh) echoes back the `Authorization` header it received
///     so the test can confirm it used the refreshed token.
actor ConcurrentRefreshTransport: HTTPTransport {
    struct EchoBody: Codable, Sendable, Equatable {
        let authHeader: String
    }

    private(set) var refreshCallCount = 0
    private var attemptCounts: [String: Int] = [:]

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        if request.url?.path == "/auth/refresh" {
            refreshCallCount += 1
            let dto = TokenPairDTO(
                accessToken: "refreshed-access-\(refreshCallCount)",
                refreshToken: "refreshed-refresh-\(refreshCallCount)",
                tokenType: "bearer",
                expiresIn: 3600
            )
            let data = try APICoding.encoder.encode(dto)
            return (data, HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!)
        }

        let requestID = request.value(forHTTPHeaderField: "X-Test-Request-Id") ?? "default"
        let attempt = (attemptCounts[requestID] ?? 0) + 1
        attemptCounts[requestID] = attempt

        if attempt == 1 {
            let errorBody = try APICoding.encoder.encode(["error": "AUTHENTICATION_ERROR", "message": "expired"])
            return (errorBody, HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: nil)!)
        }

        let authHeader = request.value(forHTTPHeaderField: "Authorization") ?? ""
        let body = try APICoding.encoder.encode(EchoBody(authHeader: authHeader))
        return (body, HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!)
    }
}
