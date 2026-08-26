import Foundation
import Testing
@testable import OptiTradeiOS

struct APIRequestConstructionTests {
    @Test
    func getRequestDefaultsToNoBodyAndRequiresAuth() {
        let request = APIRequest<EmptyResponse>(path: "portfolios")
        #expect(request.method == .get)
        #expect(request.bodyData == nil)
        #expect(request.requiresAuth == true)
        #expect(request.queryItems.isEmpty)
        #expect(request.headers.isEmpty)
    }

    @Test
    func postRequestEncodesBodyAsSnakeCaseJSON() throws {
        struct Body: Encodable { let refreshToken: String }
        let request = try APIRequest<EmptyResponse>(path: "auth/refresh", method: .post, body: Body(refreshToken: "r-1"), requiresAuth: false)

        #expect(request.method == .post)
        #expect(request.requiresAuth == false)
        let json = try #require(request.bodyData)
        let object = try JSONSerialization.jsonObject(with: json) as? [String: String]
        #expect(object?["refresh_token"] == "r-1")
    }

    @Test
    func queryItemsAndHeadersAreCarriedVerbatim() {
        let request = APIRequest<EmptyResponse>(
            path: "scan",
            queryItems: [URLQueryItem(name: "market", value: "bist")],
            headers: ["X-Custom": "1"]
        )
        #expect(request.queryItems == [URLQueryItem(name: "market", value: "bist")])
        #expect(request.headers["X-Custom"] == "1")
    }
}

struct APIClientURLBuildingTests {
    @Test
    func buildsURLRelativeToConfiguredBaseURL() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("{}".utf8))])
        let client = makeClient(transport: transport, tokenStore: InMemoryTokenStore())

        _ = try await client.send(APIRequest<EmptyResponse>(path: "health", requiresAuth: false))

        let recorded = await transport.recordedRequests
        #expect(recorded.first?.url?.absoluteString == "http://localhost:8000/health")
    }

    @Test
    func appendsQueryItemsToRequestURL() async throws {
        let transport = MockHTTPTransport(stubs: [.raw(200, Data("{}".utf8))])
        let client = makeClient(transport: transport, tokenStore: InMemoryTokenStore())

        _ = try await client.send(APIRequest<EmptyResponse>(
            path: "scan",
            queryItems: [URLQueryItem(name: "market", value: "bist")],
            requiresAuth: false
        ))

        let recorded = await transport.recordedRequests
        #expect(recorded.first?.url?.query == "market=bist")
    }
}
