import Foundation
import Testing
@testable import OptiTradeiOS

struct APIClientTests {
    @Test
    func attachesBearerTokenWhenRequestRequiresAuth() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("{}".utf8))])
        let tokenStore = InMemoryTokenStore(tokens: AuthTokens(accessToken: "abc123", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let client = makeClient(transport: transport, tokenStore: tokenStore)

        _ = try await client.send(APIRequest<EmptyResponse>(path: "portfolios"))

        let recorded = await transport.recordedRequests
        #expect(recorded.first?.value(forHTTPHeaderField: "Authorization") == "Bearer abc123")
    }

    @Test
    func omitsAuthorizationHeaderWhenRequestDoesNotRequireAuth() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("{}".utf8))])
        let tokenStore = InMemoryTokenStore(tokens: AuthTokens(accessToken: "abc123", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
        let client = makeClient(transport: transport, tokenStore: tokenStore)

        _ = try await client.send(APIRequest<EmptyResponse>(path: "health", requiresAuth: false))

        let recorded = await transport.recordedRequests
        #expect(recorded.first?.value(forHTTPHeaderField: "Authorization") == nil)
    }

    @Test
    func decodesSuccessfulJSONResponse() async throws {
        struct Health: Decodable, Equatable { let status: String }
        let transport = MockHTTPTransport(stubs: [.json(200, ["status": "ok"])])
        let client = makeClient(transport: transport, tokenStore: InMemoryTokenStore())

        let result = try await client.send(APIRequest<Health>(path: "health", requiresAuth: false))
        #expect(result == Health(status: "ok"))
    }

    @Test
    func emptyResponseTypeDecodesWithoutTouchingBody() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(204)])
        let client = makeClient(transport: transport, tokenStore: InMemoryTokenStore())

        _ = try await client.send(APIRequest<EmptyResponse>(path: "watchlists/1", method: .delete))
    }

    @Test
    func malformedJSONSurfacesAsDecodingError() async throws {
        struct Health: Decodable { let status: String }
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("not json".utf8))])
        let client = makeClient(transport: transport, tokenStore: InMemoryTokenStore())

        await #expect(throws: APIClientError.self) {
            _ = try await client.send(APIRequest<Health>(path: "health", requiresAuth: false))
        }
    }

    @Test
    func serverErrorStatusSurfacesAsTypedAPIError() async throws {
        let transport = MockHTTPTransport(stubs: [.json(500, ["error": "INTERNAL_ERROR", "message": "boom"])])
        let client = makeClient(transport: transport, tokenStore: InMemoryTokenStore())

        do {
            _ = try await client.send(APIRequest<EmptyResponse>(path: "analyze", method: .post, requiresAuth: false))
            Issue.record("Expected APIClientError.server to be thrown")
        } catch let error as APIClientError {
            guard case .server(let statusCode, let payload) = error else {
                Issue.record("Expected .server, got \(error)")
                return
            }
            #expect(statusCode == 500)
            #expect(payload?.code == "INTERNAL_ERROR")
        }
    }

    @Test
    func refreshesOnceAndRetriesOriginalRequestAfter401() async throws {
        let transport = ConcurrentRefreshTransport()
        let tokenStore = InMemoryTokenStore(tokens: AuthTokens(accessToken: "stale", refreshToken: "r-1", tokenType: "bearer", expiresIn: 3600))
        let client = makeClient(transport: transport, tokenStore: tokenStore)

        let result = try await client.send(APIRequest<ConcurrentRefreshTransport.EchoBody>(
            path: "portfolios",
            headers: ["X-Test-Request-Id": "single"]
        ))

        #expect(result.authHeader == "Bearer refreshed-access-1")
        #expect(await transport.refreshCallCount == 1)
        #expect(await tokenStore.accessToken() == "refreshed-access-1")
    }

    @Test
    func sessionExpiryCallbackFiresWhenRefreshTokenIsMissing() async throws {
        let transport = ConcurrentRefreshTransport()
        let tokenStore = InMemoryTokenStore() // no tokens at all
        let expired = Recorder()
        let client = makeClient(transport: transport, tokenStore: tokenStore, onSessionExpired: { await expired.record() })

        await #expect(throws: APIClientError.self) {
            _ = try await client.send(APIRequest<EmptyResponse>(path: "portfolios", headers: ["X-Test-Request-Id": "no-refresh"]))
        }
        #expect(await expired.count == 1)
    }
}

private actor Recorder {
    private(set) var count = 0
    func record() { count += 1 }
}
