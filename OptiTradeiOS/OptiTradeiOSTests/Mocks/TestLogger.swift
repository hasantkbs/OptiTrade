import Foundation
@testable import OptiTradeiOS

/// Silent `AppLogging` fake for tests that need a logger dependency but
/// don't assert on log output.
struct TestLogger: AppLogging {
    func debug(_ message: String, category: LogCategory) {}
    func info(_ message: String, category: LogCategory) {}
    func warning(_ message: String, category: LogCategory) {}
    func error(_ message: String, category: LogCategory) {}
}
