import Foundation

/// Immutable, injectable network settings. Never constructed with a guessed
/// or placeholder URL — see `AppEnvironment.networkConfiguration(for:)`.
struct NetworkConfiguration: Sendable, Equatable {
    let baseURL: URL
    let timeoutInterval: TimeInterval

    init(baseURL: URL, timeoutInterval: TimeInterval = 30) {
        self.baseURL = baseURL
        self.timeoutInterval = timeoutInterval
    }
}
