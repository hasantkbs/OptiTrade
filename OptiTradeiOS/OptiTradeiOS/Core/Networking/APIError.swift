import Foundation

/// Machine/human-readable error body the backend returns.
///
/// Handles both response shapes actually produced by the backend:
///   - `OptiTradeError` subclasses: `{"error": "CODE", "message": "...", "details": {...}}`
///   - plain FastAPI `HTTPException`/slowapi: `{"detail": "..."}`
struct BackendErrorPayload: Decodable, Sendable, Equatable {
    let code: String?
    let message: String?

    private enum CodingKeys: String, CodingKey {
        case error, message, detail
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        code = try container.decodeIfPresent(String.self, forKey: .error)
        let message = try container.decodeIfPresent(String.self, forKey: .message)
        let detail = try container.decodeIfPresent(String.self, forKey: .detail)
        self.message = message ?? detail
    }

    init(code: String?, message: String?) {
        self.code = code
        self.message = message
    }
}

/// Typed client/API error. Never carries a token or other secret — only
/// what's safe to show a user or write to a log.
enum APIClientError: Error, Sendable, Equatable {
    case invalidURL
    case transport(String)
    case timeout
    case cancelled
    case unauthorized(BackendErrorPayload?)
    case forbidden(BackendErrorPayload?)
    case notFound(BackendErrorPayload?)
    case validation(BackendErrorPayload?)
    case rateLimited(retryAfter: TimeInterval?, payload: BackendErrorPayload?)
    case server(statusCode: Int, payload: BackendErrorPayload?)
    case decoding(String)
    case unknown(statusCode: Int?)

    /// Maps an HTTP status + raw body to a typed error. Shared by `APIClient`
    /// and the token-refresh path so both classify backend errors identically.
    static func map(statusCode: Int, data: Data, decoder: JSONDecoder, retryAfter: TimeInterval? = nil) -> APIClientError {
        let payload = try? decoder.decode(BackendErrorPayload.self, from: data)
        switch statusCode {
        case 401: return .unauthorized(payload)
        case 403: return .forbidden(payload)
        case 404: return .notFound(payload)
        case 400, 422: return .validation(payload)
        case 429: return .rateLimited(retryAfter: retryAfter, payload: payload)
        case 500...599: return .server(statusCode: statusCode, payload: payload)
        default: return .unknown(statusCode: statusCode)
        }
    }
}
