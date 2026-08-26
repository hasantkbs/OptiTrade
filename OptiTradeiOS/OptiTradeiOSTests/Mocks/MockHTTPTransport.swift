import Foundation
@testable import OptiTradeiOS

/// FIFO-stub transport for tests where request order is deterministic
/// (i.e. no concurrent requests racing each other).
actor MockHTTPTransport: HTTPTransport {
    struct Stub: Sendable {
        let statusCode: Int
        let data: Data
        let headers: [String: String]
        let error: Error?

        static func json(_ statusCode: Int, _ object: some Encodable, headers: [String: String] = [:]) -> Stub {
            let data = (try? APICoding.encoder.encode(object)) ?? Data()
            return Stub(statusCode: statusCode, data: data, headers: headers, error: nil)
        }

        static func raw(_ statusCode: Int, _ data: Data = Data(), headers: [String: String] = [:]) -> Stub {
            Stub(statusCode: statusCode, data: data, headers: headers, error: nil)
        }

        static func failure(_ error: Error) -> Stub {
            Stub(statusCode: 0, data: Data(), headers: [:], error: error)
        }
    }

    private var stubs: [Stub]
    private(set) var recordedRequests: [URLRequest] = []

    init(stubs: [Stub] = []) {
        self.stubs = stubs
    }

    func enqueue(_ stub: Stub) {
        stubs.append(stub)
    }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        recordedRequests.append(request)
        guard !stubs.isEmpty else {
            preconditionFailure("MockHTTPTransport: no stub enqueued for request #\(recordedRequests.count)")
        }
        let stub = stubs.removeFirst()
        if let error = stub.error {
            throw error
        }
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: stub.statusCode,
            httpVersion: "HTTP/1.1",
            headerFields: stub.headers
        )!
        return (stub.data, response)
    }
}
