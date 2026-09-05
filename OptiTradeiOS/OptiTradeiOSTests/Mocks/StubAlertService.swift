import Foundation
@testable import OptiTradeiOS

/// Configurable `AlertServicing` fake — no network, no `APIClient`.
actor StubAlertService: AlertServicing {
    private(set) var fetchCallCount = 0
    private(set) var createCallCount = 0
    private(set) var setEnabledCallCount = 0
    private(set) var deleteCallCount = 0
    private(set) var scanCallCount = 0
    private(set) var recordedSetEnabledIDs: [Int] = []
    private(set) var recordedDeletedIDs: [Int] = []

    var fetchResult: Result<[AlertRule], Error>
    var createResult: Result<AlertRule, Error>
    var setEnabledResult: Result<AlertRule, Error>
    var deleteResult: Result<Void, Error>
    var scanResult: Result<AlertScanSummary, Error>
    var delayNanoseconds: UInt64

    init(
        fetchResult: Result<[AlertRule], Error> = .success([]),
        createResult: Result<AlertRule, Error> = .success(StubAlertService.defaultAlert),
        setEnabledResult: Result<AlertRule, Error> = .success(StubAlertService.defaultAlert),
        deleteResult: Result<Void, Error> = .success(()),
        scanResult: Result<AlertScanSummary, Error> = .success(AlertScanSummary(dto: ScanReportDTO(totalAlerts: 0, checkedCount: 0, triggeredCount: 0))),
        delayNanoseconds: UInt64 = 0
    ) {
        self.fetchResult = fetchResult
        self.createResult = createResult
        self.setEnabledResult = setEnabledResult
        self.deleteResult = deleteResult
        self.scanResult = scanResult
        self.delayNanoseconds = delayNanoseconds
    }

    static let defaultAlert = AlertRule(dto: AlertDTO(
        id: 1, owner: "trader@optitrade.app", watchlistId: nil, symbol: "AAPL", portfolioId: nil,
        category: .price, alertType: .priceAbove, parameters: ["threshold": 200], cooldownMinutes: 60, enabled: true
    ))!

    func fetchAlerts() async throws -> [AlertRule] {
        fetchCallCount += 1
        if delayNanoseconds > 0 { try await Task.sleep(nanoseconds: delayNanoseconds) }
        return try fetchResult.get()
    }

    func createAlert(category: AlertCategoryDTO, alertType: AlertTypeDTO, symbol: String?, parameters: [String: Double], cooldownMinutes: Int) async throws -> AlertRule {
        createCallCount += 1
        return try createResult.get()
    }

    func setEnabled(_ enabled: Bool, alertID: Int) async throws -> AlertRule {
        setEnabledCallCount += 1
        recordedSetEnabledIDs.append(alertID)
        return try setEnabledResult.get()
    }

    func deleteAlert(alertID: Int) async throws {
        deleteCallCount += 1
        recordedDeletedIDs.append(alertID)
        try deleteResult.get()
    }

    func scanNow() async throws -> AlertScanSummary {
        scanCallCount += 1
        return try scanResult.get()
    }

    func setFetchResult(_ newResult: Result<[AlertRule], Error>) {
        fetchResult = newResult
    }

    func setCreateResult(_ newResult: Result<AlertRule, Error>) {
        createResult = newResult
    }

    func setSetEnabledResult(_ newResult: Result<AlertRule, Error>) {
        setEnabledResult = newResult
    }

    func setDeleteResult(_ newResult: Result<Void, Error>) {
        deleteResult = newResult
    }
}
