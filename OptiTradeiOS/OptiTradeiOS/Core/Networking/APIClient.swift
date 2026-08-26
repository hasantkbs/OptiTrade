import Foundation

/// Generic REST client: builds a `URLRequest` from an `APIRequest`, sends it
/// via `HTTPTransport`, decodes the result, and — for authenticated requests
/// that come back 401 — coordinates exactly one token refresh before retrying
/// once. It does not know about any specific feature endpoint.
final class APIClient: Sendable {
    private let configuration: NetworkConfiguration
    private let transport: HTTPTransport
    private let tokenStore: TokenStore
    private let refreshCoordinator: TokenRefreshCoordinator
    private let logger: AppLogging
    private let onSessionExpired: @Sendable () async -> Void

    init(
        configuration: NetworkConfiguration,
        transport: HTTPTransport,
        tokenStore: TokenStore,
        refreshCoordinator: TokenRefreshCoordinator,
        logger: AppLogging,
        onSessionExpired: @escaping @Sendable () async -> Void
    ) {
        self.configuration = configuration
        self.transport = transport
        self.tokenStore = tokenStore
        self.refreshCoordinator = refreshCoordinator
        self.logger = logger
        self.onSessionExpired = onSessionExpired
    }

    func send<Response>(_ request: APIRequest<Response>) async throws -> Response {
        try await send(request, allowRefreshRetry: true)
    }

    private func send<Response>(_ request: APIRequest<Response>, allowRefreshRetry: Bool) async throws -> Response {
        let accessToken = request.requiresAuth ? await tokenStore.accessToken() : nil
        let urlRequest = try buildURLRequest(for: request, accessToken: accessToken)

        let data: Data
        let httpResponse: HTTPURLResponse
        do {
            (data, httpResponse) = try await transport.send(urlRequest)
        } catch {
            logger.warning("Request to \(request.path) failed in transport.", category: .networking)
            throw error
        }

        switch httpResponse.statusCode {
        case 200..<300:
            return try decodeResponse(Response.self, from: data)

        case 401 where request.requiresAuth && allowRefreshRetry:
            logger.info("Access token rejected for \(request.path); attempting refresh.", category: .authentication)
            do {
                _ = try await refreshCoordinator.refreshedTokens()
            } catch {
                logger.warning("Token refresh failed; ending session.", category: .authentication)
                await onSessionExpired()
                throw APIClientError.map(statusCode: 401, data: data, decoder: APICoding.decoder)
            }
            return try await send(request, allowRefreshRetry: false)

        default:
            let retryAfter = (httpResponse.value(forHTTPHeaderField: "Retry-After")).flatMap(TimeInterval.init)
            throw APIClientError.map(statusCode: httpResponse.statusCode, data: data, decoder: APICoding.decoder, retryAfter: retryAfter)
        }
    }

    private func decodeResponse<Response: Decodable>(_ type: Response.Type, from data: Data) throws -> Response {
        if Response.self == EmptyResponse.self, let empty = EmptyResponse() as? Response {
            return empty
        }
        do {
            return try APICoding.decoder.decode(Response.self, from: data)
        } catch {
            throw APIClientError.decoding(String(describing: error))
        }
    }

    private func buildURLRequest<Response>(for request: APIRequest<Response>, accessToken: String?) throws -> URLRequest {
        let fullURL = configuration.baseURL.appendingPathComponent(request.path)
        guard var components = URLComponents(url: fullURL, resolvingAgainstBaseURL: false) else {
            throw APIClientError.invalidURL
        }
        if !request.queryItems.isEmpty {
            components.queryItems = request.queryItems
        }
        guard let url = components.url else {
            throw APIClientError.invalidURL
        }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = request.method.rawValue
        urlRequest.timeoutInterval = configuration.timeoutInterval
        urlRequest.httpBody = request.bodyData

        urlRequest.setValue("application/json", forHTTPHeaderField: "Accept")
        if request.bodyData != nil {
            urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        for (field, value) in request.headers {
            urlRequest.setValue(value, forHTTPHeaderField: field)
        }
        if let accessToken {
            urlRequest.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        }
        return urlRequest
    }
}
