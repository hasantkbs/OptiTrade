import Foundation

/// Wire shape of `users.schemas.LoginRequest`. Field names ("email",
/// "password") have no underscores, so plain camelCase already matches the
/// backend — no custom `CodingKeys` needed.
struct LoginRequestBody: Encodable, Sendable {
    let email: String
    let password: String
}

/// Wire shape of `users.schemas.UserResponse` — only the fields this app
/// currently displays. Codable silently ignores JSON keys that aren't
/// declared here (`is_email_verified`, `is_active`, `created_at`,
/// `last_login_at`), so there's no need to model fields nothing reads yet.
struct CurrentUserDTO: Decodable, Sendable {
    let id: Int
    let email: String
    let displayName: String

    var user: CurrentUser {
        CurrentUser(id: id, email: email, displayName: displayName)
    }
}

/// Domain-facing current-user model. Deliberately excludes anything
/// sensitive — this is what the authenticated shell is allowed to show.
struct CurrentUser: Sendable, Equatable {
    let id: Int
    let email: String
    let displayName: String
}

/// Maps a thrown error to copy that's safe to show a user — never the raw
/// backend JSON, error code, or a stack trace.
enum AuthPresentableError {
    static func message(for error: Error) -> String {
        guard let apiError = error as? APIClientError else {
            return "Something went wrong. Please try again."
        }
        switch apiError {
        case .invalidURL:
            return "Something went wrong. Please try again."
        case .unauthorized:
            return "Incorrect email or password."
        case .forbidden:
            return "You don't have access to this account."
        case .notFound:
            return "We couldn't find that account."
        case .validation:
            return "Please check your details and try again."
        case .rateLimited:
            return "Too many attempts. Please wait a moment and try again."
        case .transport, .timeout:
            return "Couldn't reach the server. Check your connection and try again."
        case .cancelled:
            return "Request cancelled."
        case .server, .unknown:
            return "The server is having trouble. Please try again shortly."
        case .decoding:
            return "Unexpected response from the server."
        }
    }
}
