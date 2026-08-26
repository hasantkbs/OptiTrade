import Foundation
import Observation

/// Drives the minimal root/foundation screen. Proves the app can launch,
/// resolve its environment, initialize networking, and restore (or not
/// restore) a session — nothing more.
@MainActor
@Observable
final class RootViewModel {
    enum FoundationStatus: Sendable, Equatable {
        case launching
        case ready(environment: AppEnvironmentKind, sessionState: SessionManager.State)
    }

    private(set) var status: FoundationStatus = .launching

    private let sessionManager: SessionManager
    private let environmentKind: AppEnvironmentKind
    private let logger: AppLogging

    init(sessionManager: SessionManager, environmentKind: AppEnvironmentKind, logger: AppLogging) {
        self.sessionManager = sessionManager
        self.environmentKind = environmentKind
        self.logger = logger
    }

    func start() async {
        logger.info("OptiTrade foundation starting.", category: .app)
        await sessionManager.restoreSession()
        status = .ready(environment: environmentKind, sessionState: sessionManager.state)
        logger.info("OptiTrade foundation ready.", category: .app)
    }
}
