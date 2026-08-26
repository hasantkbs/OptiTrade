import Foundation
import Testing
@testable import OptiTradeiOS

struct APIErrorMappingTests {
    @Test
    func decodesOptiTradeErrorShape() throws {
        let json = Data("""
        {"error": "SYMBOL_NOT_FOUND", "message": "AAPL için veri yok", "details": {}}
        """.utf8)
        let payload = try APICoding.decoder.decode(BackendErrorPayload.self, from: json)
        #expect(payload.code == "SYMBOL_NOT_FOUND")
        #expect(payload.message == "AAPL için veri yok")
    }

    @Test
    func decodesPlainFastAPIDetailShape() throws {
        let json = Data("""
        {"detail": "Authorization token missing."}
        """.utf8)
        let payload = try APICoding.decoder.decode(BackendErrorPayload.self, from: json)
        #expect(payload.code == nil)
        #expect(payload.message == "Authorization token missing.")
    }

    @Test(arguments: [
        (401, "unauthorized"),
        (403, "forbidden"),
        (404, "notFound"),
        (400, "validation"),
        (422, "validation"),
        (429, "rateLimited"),
        (500, "server"),
        (503, "server"),
    ])
    func mapsStatusCodeToExpectedCase(statusCode: Int, expectedCase: String) {
        let data = Data("{}".utf8)
        let error = APIClientError.map(statusCode: statusCode, data: data, decoder: APICoding.decoder)
        switch (error, expectedCase) {
        case (.unauthorized, "unauthorized"),
             (.forbidden, "forbidden"),
             (.notFound, "notFound"),
             (.validation, "validation"),
             (.rateLimited, "rateLimited"),
             (.server, "server"):
            return
        default:
            Issue.record("Status \(statusCode) mapped to \(error), expected \(expectedCase)")
        }
    }

    @Test
    func unmappedStatusCodeBecomesUnknown() {
        let error = APIClientError.map(statusCode: 999, data: Data(), decoder: APICoding.decoder)
        #expect(error == .unknown(statusCode: 999))
    }
}
