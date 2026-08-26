import Foundation
import Testing
@testable import OptiTradeiOS

struct AppEnvironmentTests {
    @Test
    func developmentResolvesToLocalhost() throws {
        let configuration = try AppEnvironment.networkConfiguration(for: .development)
        #expect(configuration.baseURL.absoluteString == "http://localhost:8000")
    }

    @Test(arguments: [AppEnvironmentKind.staging, .production])
    func unconfirmedEnvironmentsFailExplicitlyInsteadOfGuessingAURL(kind: AppEnvironmentKind) {
        #expect(throws: AppEnvironmentError.missingBaseURLConfiguration(kind)) {
            _ = try AppEnvironment.networkConfiguration(for: kind)
        }
    }
}
