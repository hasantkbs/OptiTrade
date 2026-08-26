import Foundation

/// Where the app is running against. Kept intentionally small — the base URL
/// per case is resolved in exactly one place (`networkConfiguration(for:)`
/// below), never scattered across call sites.
enum AppEnvironmentKind: String, Sendable, CaseIterable {
    case development
    case staging
    case production
}

enum AppEnvironmentError: Error, Sendable, Equatable {
    /// Thrown instead of silently falling back to a fake/unverified URL.
    case missingBaseURLConfiguration(AppEnvironmentKind)
}

enum AppEnvironment {
    /// Single source of truth for which environment the running build targets.
    /// Debug builds default to `.development`; everything else is `.production`.
    static var current: AppEnvironmentKind {
        #if DEBUG
        return .development
        #else
        return .production
        #endif
    }

    /// The only place a base URL is written down in this app.
    ///
    /// `.staging` and `.production` intentionally have no confirmed backend
    /// URL yet, so they fail loudly here rather than silently defaulting to
    /// an unverified domain.
    static func networkConfiguration(for kind: AppEnvironmentKind = current) throws -> NetworkConfiguration {
        switch kind {
        case .development:
            guard let url = URL(string: "http://localhost:8000") else {
                throw AppEnvironmentError.missingBaseURLConfiguration(kind)
            }
            return NetworkConfiguration(baseURL: url, timeoutInterval: 30)
        case .staging, .production:
            throw AppEnvironmentError.missingBaseURLConfiguration(kind)
        }
    }
}
