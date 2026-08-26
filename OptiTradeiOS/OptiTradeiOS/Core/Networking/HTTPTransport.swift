import Foundation

/// The one seam between `APIClient` and `URLSession`. Tests inject a fake
/// conforming type instead of hitting the network.
///
///     APIClient -> HTTPTransport -> URLSession
protocol HTTPTransport: Sendable {
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

struct URLSessionHTTPTransport: HTTPTransport {
    private let session: URLSession

    init(session: URLSession) {
        self.session = session
    }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIClientError.unknown(statusCode: nil)
            }
            return (data, httpResponse)
        } catch let error as APIClientError {
            throw error
        } catch let urlError as URLError {
            switch urlError.code {
            case .cancelled:
                throw APIClientError.cancelled
            case .timedOut:
                throw APIClientError.timeout
            default:
                // Deliberately generic: never include the request (which may
                // carry an Authorization header) in the surfaced description.
                throw APIClientError.transport("URLError(\(urlError.code.rawValue))")
            }
        } catch {
            throw APIClientError.transport(String(describing: type(of: error)))
        }
    }
}
