import Foundation
import Testing
@testable import OptiTradeiOS

struct AuthModelsTests {
    @Test
    func tokenPairDTODecodesBackendSnakeCaseShape() throws {
        let json = Data("""
        {"access_token": "a", "refresh_token": "r", "token_type": "bearer", "expires_in": 3600}
        """.utf8)
        let dto = try APICoding.decoder.decode(TokenPairDTO.self, from: json)
        #expect(dto.tokens == AuthTokens(accessToken: "a", refreshToken: "r", tokenType: "bearer", expiresIn: 3600))
    }

    @Test
    func refreshRequestDTOEncodesSnakeCaseField() throws {
        let data = try APICoding.encoder.encode(RefreshRequestDTO(refreshToken: "r-1"))
        let object = try JSONSerialization.jsonObject(with: data) as? [String: String]
        #expect(object == ["refresh_token": "r-1"])
    }
}
