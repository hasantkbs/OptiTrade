import Foundation
@testable import OptiTradeiOS

/// Routes responses by request path rather than FIFO arrival order.
/// `MockHTTPTransport`'s FIFO queue is only safe for callers that await
/// requests one at a time; `AssetDetailService` fires three requests
/// *concurrently* via `async let`, so which physical request reaches the
/// transport first is not deterministic — a FIFO stub queue could hand
/// the `/quant/analyze` response to the `/price/{symbol}` call. Keying by
/// path removes that race entirely.
actor RoutingHTTPTransport: HTTPTransport {
    struct Stub: Sendable {
        let statusCode: Int
        let data: Data
        let error: Error?

        static func json(_ statusCode: Int, _ object: some Encodable) -> Stub {
            let data = (try? APICoding.encoder.encode(object)) ?? Data()
            return Stub(statusCode: statusCode, data: data, error: nil)
        }

        static func raw(_ statusCode: Int, _ data: Data = Data()) -> Stub {
            Stub(statusCode: statusCode, data: data, error: nil)
        }

        static func failure(_ error: Error) -> Stub {
            Stub(statusCode: 0, data: Data(), error: error)
        }
    }

    private var stubsByPath: [String: Stub]
    private(set) var recordedRequests: [URLRequest] = []

    init(stubsByPath: [String: Stub] = [:]) {
        self.stubsByPath = stubsByPath
    }

    func setStub(_ stub: Stub, forPath path: String) {
        stubsByPath[path] = stub
    }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        recordedRequests.append(request)
        guard let path = request.url?.path, let stub = stubsByPath[path] else {
            preconditionFailure("RoutingHTTPTransport: no stub registered for path \(request.url?.path ?? "<nil>")")
        }
        if let error = stub.error {
            throw error
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: stub.statusCode, httpVersion: "HTTP/1.1", headerFields: [:])!
        return (stub.data, response)
    }
}
