import Foundation
import os

enum LogCategory: String, Sendable, CaseIterable {
    case app
    case networking
    case authentication
    case session
    case portfolio
    case assets
    case watchlist
    case aiAnalyst
}

/// Abstraction over Apple's unified logging so call sites (and tests) don't
/// depend on `os.Logger` directly.
///
/// Callers must never pass a token, password, or account-financial detail as
/// `message` — these methods log it verbatim.
protocol AppLogging: Sendable {
    func debug(_ message: String, category: LogCategory)
    func info(_ message: String, category: LogCategory)
    func warning(_ message: String, category: LogCategory)
    func error(_ message: String, category: LogCategory)
}

struct AppLogger: AppLogging {
    private let loggers: [LogCategory: Logger]

    init(subsystem: String = Bundle.main.bundleIdentifier ?? "com.algorix.optitrade") {
        var loggers: [LogCategory: Logger] = [:]
        for category in LogCategory.allCases {
            loggers[category] = Logger(subsystem: subsystem, category: category.rawValue)
        }
        self.loggers = loggers
    }

    func debug(_ message: String, category: LogCategory) {
        loggers[category]?.debug("\(message, privacy: .public)")
    }

    func info(_ message: String, category: LogCategory) {
        loggers[category]?.info("\(message, privacy: .public)")
    }

    func warning(_ message: String, category: LogCategory) {
        loggers[category]?.warning("\(message, privacy: .public)")
    }

    func error(_ message: String, category: LogCategory) {
        loggers[category]?.error("\(message, privacy: .public)")
    }
}
