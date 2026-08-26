import Foundation

/// A marker `Decodable` for endpoints that return no body (e.g. 204).
struct EmptyResponse: Decodable, Sendable, Equatable {}

/// Describes one API call. The body (if any) is encoded eagerly at
/// construction time so the request itself stays a plain, trivially
/// `Sendable` value — no existential `Encodable` stored property.
struct APIRequest<Response: Decodable & Sendable>: Sendable {
    let path: String
    let method: HTTPMethod
    let queryItems: [URLQueryItem]
    let headers: [String: String]
    let bodyData: Data?
    /// Whether the `Authorization` header should be attached and a 401
    /// should trigger the token-refresh path.
    let requiresAuth: Bool

    init(
        path: String,
        method: HTTPMethod = .get,
        queryItems: [URLQueryItem] = [],
        headers: [String: String] = [:],
        requiresAuth: Bool = true
    ) {
        self.path = path
        self.method = method
        self.queryItems = queryItems
        self.headers = headers
        self.bodyData = nil
        self.requiresAuth = requiresAuth
    }

    init<Body: Encodable>(
        path: String,
        method: HTTPMethod = .post,
        body: Body,
        queryItems: [URLQueryItem] = [],
        headers: [String: String] = [:],
        requiresAuth: Bool = true,
        encoder: JSONEncoder = APICoding.encoder
    ) throws {
        self.path = path
        self.method = method
        self.queryItems = queryItems
        self.headers = headers
        self.bodyData = try encoder.encode(body)
        self.requiresAuth = requiresAuth
    }
}

/// Shared `JSONEncoder`/`JSONDecoder` configuration so every request/response
/// in the app agrees on date/key conventions. The backend uses snake_case
/// field names (see `users/schemas.py`, `models/schemas.py`).
enum APICoding {
    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()
}
