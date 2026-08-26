import Foundation

/// A decoded response plus the transport metadata callers occasionally need
/// (status code, backend correlation id) without forcing every call site to
/// parse headers itself.
struct APIResponse<Body: Sendable>: Sendable {
    let value: Body
    let statusCode: Int
    let requestID: String?
}
