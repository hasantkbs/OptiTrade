import Foundation

/// Client-side view of a backend token pair. Never `CustomStringConvertible`
/// beyond the default — do not add a `description` that prints the tokens.
struct AuthTokens: Sendable, Equatable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let expiresIn: Int
}

/// Wire shape of `users.schemas.TokenPairResponse`.
///
/// No custom `CodingKeys` — property names are plain camelCase and rely on
/// `APICoding`'s `convertToSnakeCase`/`convertFromSnakeCase` strategies to
/// meet the backend's snake_case field names. (A custom `CodingKeys` with
/// snake_case raw values here would double-convert and fail to match.)
///
/// `Encodable` only exists so tests can fabricate a fake backend response;
/// the app itself never sends this shape anywhere.
struct TokenPairDTO: Codable, Sendable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let expiresIn: Int

    var tokens: AuthTokens {
        AuthTokens(accessToken: accessToken, refreshToken: refreshToken, tokenType: tokenType, expiresIn: expiresIn)
    }
}

/// Wire shape of `users.schemas.RefreshRequest`.
struct RefreshRequestDTO: Encodable, Sendable {
    let refreshToken: String
}
