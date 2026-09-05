import Foundation
import Testing
@testable import OptiTradeiOS

@MainActor
struct AlertViewModelTests {
    private static func alert(id: Int = 1, symbol: String = "AAPL", enabled: Bool = true) -> AlertRule {
        AlertRule(dto: AlertDTO(
            id: id, owner: "trader@optitrade.app", watchlistId: nil, symbol: symbol, portfolioId: nil,
            category: .price, alertType: .priceAbove, parameters: ["threshold": 200], cooldownMinutes: 60, enabled: enabled
        ))!
    }

    @Test
    func initialStateIsIdleBeforeLoading() {
        let viewModel = AlertViewModel(service: StubAlertService(), logger: TestLogger())
        #expect(viewModel.state == .idle)
    }

    @Test
    func loadIfNeededTransitionsToLoadedOnSuccess() async {
        let service = StubAlertService(fetchResult: .success([Self.alert()]))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())

        await viewModel.loadIfNeeded()

        #expect(viewModel.state == .loaded([Self.alert()]))
    }

    @Test
    func loadIfNeededTransitionsToEmptyWhenNoAlertsExist() async {
        let service = StubAlertService(fetchResult: .success([]))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())

        await viewModel.loadIfNeeded()

        #expect(viewModel.state == .empty)
    }

    @Test
    func loadIfNeededTransitionsToFailedOnServerError() async {
        let service = StubAlertService(fetchResult: .failure(APIClientError.server(statusCode: 500, payload: nil)))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())

        await viewModel.loadIfNeeded()

        #expect(viewModel.state == .failed("The server is having trouble. Please try again shortly."))
    }

    @Test
    func loadIfNeededIsANoOpOnceLoadingHasStarted() async {
        let service = StubAlertService(fetchResult: .success([Self.alert()]), delayNanoseconds: 20_000_000)
        let viewModel = AlertViewModel(service: service, logger: TestLogger())

        async let first: Void = viewModel.loadIfNeeded()
        async let second: Void = viewModel.loadIfNeeded()
        _ = await [first, second]

        #expect(await service.fetchCallCount == 1)
    }

    @Test
    func refreshReplacesLoadedDataOnSuccess() async {
        let service = StubAlertService(fetchResult: .success([Self.alert(enabled: true)]))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setFetchResult(.success([Self.alert(enabled: false)]))
        await viewModel.refresh()

        #expect(viewModel.state == .loaded([Self.alert(enabled: false)]))
        #expect(viewModel.refreshError == nil)
    }

    @Test
    func refreshFailurePreservesExistingLoadedDataAndSurfacesABanner() async {
        let alerts = [Self.alert()]
        let service = StubAlertService(fetchResult: .success(alerts))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setFetchResult(.failure(APIClientError.transport("offline")))
        await viewModel.refresh()

        #expect(viewModel.state == .loaded(alerts)) // unchanged
        #expect(viewModel.refreshError == "Couldn't reach the server. Check your connection and try again.")
    }

    @Test
    func repeatedRefreshTapsOnlyProduceOneRequest() async {
        let service = StubAlertService(fetchResult: .success([Self.alert()]), delayNanoseconds: 20_000_000)
        let viewModel = AlertViewModel(service: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        async let first: Void = viewModel.refresh()
        async let second: Void = viewModel.refresh()
        _ = await [first, second]

        #expect(await service.fetchCallCount == 2) // one from loadIfNeeded, one from the two racing refreshes
    }

    // MARK: - Create

    @Test
    func createAlertSucceedsAndReloadsFromTheBackend() async {
        let service = StubAlertService(fetchResult: .success([]))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setFetchResult(.success([Self.alert()]))
        let success = await viewModel.createAlert(category: .price, alertType: .priceAbove, symbol: "AAPL", parameters: ["threshold": 200], cooldownMinutes: 60)

        #expect(success == true)
        #expect(await service.createCallCount == 1)
        #expect(viewModel.state == .loaded([Self.alert()]))
        #expect(viewModel.createError == nil)
    }

    @Test
    func createAlertFailureSurfacesACreateError() async {
        let service = StubAlertService(createResult: .failure(APIClientError.validation(nil)))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())

        let success = await viewModel.createAlert(category: .price, alertType: .priceAbove, symbol: "AAPL", parameters: [:], cooldownMinutes: 60)

        #expect(success == false)
        #expect(viewModel.createError == "Please check your details and try again.")
    }

    @Test
    func concurrentCreateCallsOnlyProduceOneRequest() async {
        let service = StubAlertService(createResult: .success(Self.alert()), delayNanoseconds: 20_000_000)
        let viewModel = AlertViewModel(service: service, logger: TestLogger())

        async let first: Bool = viewModel.createAlert(category: .price, alertType: .priceAbove, symbol: "AAPL", parameters: [:], cooldownMinutes: 60)
        async let second: Bool = viewModel.createAlert(category: .price, alertType: .priceAbove, symbol: "AAPL", parameters: [:], cooldownMinutes: 60)
        _ = await [first, second]

        #expect(await service.createCallCount == 1)
    }

    // MARK: - Enable / disable

    @Test
    func setEnabledSucceedsAndReloadsFromTheBackend() async {
        let service = StubAlertService(fetchResult: .success([Self.alert(enabled: true)]))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setFetchResult(.success([Self.alert(enabled: false)]))
        await viewModel.setEnabled(false, alertID: 1)

        #expect(await service.recordedSetEnabledIDs == [1])
        #expect(viewModel.state == .loaded([Self.alert(enabled: false)]))
    }

    @Test
    func concurrentSetEnabledForTheSameAlertOnlyProducesOneRequest() async {
        let service = StubAlertService(setEnabledResult: .success(Self.alert()), delayNanoseconds: 20_000_000)
        let viewModel = AlertViewModel(service: service, logger: TestLogger())

        async let first: Void = viewModel.setEnabled(false, alertID: 1)
        async let second: Void = viewModel.setEnabled(false, alertID: 1)
        _ = await [first, second]

        #expect(await service.setEnabledCallCount == 1)
    }

    @Test
    func setEnabledFailureSurfacesAMutationError() async {
        let service = StubAlertService(setEnabledResult: .failure(APIClientError.server(statusCode: 500, payload: nil)))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())

        await viewModel.setEnabled(false, alertID: 1)

        #expect(viewModel.mutationError == "The server is having trouble. Please try again shortly.")
    }

    // MARK: - Delete

    @Test
    func deleteAlertSucceedsAndReloadsFromTheBackend() async {
        let service = StubAlertService(fetchResult: .success([Self.alert()]))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await service.setFetchResult(.success([]))
        await viewModel.deleteAlert(alertID: 1)

        #expect(await service.recordedDeletedIDs == [1])
        #expect(viewModel.state == .empty)
    }

    @Test
    func deleteFailurePreservesExistingDataAndSurfacesAnError() async {
        let alerts = [Self.alert()]
        let service = StubAlertService(fetchResult: .success(alerts), deleteResult: .failure(APIClientError.server(statusCode: 500, payload: nil)))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())
        await viewModel.loadIfNeeded()

        await viewModel.deleteAlert(alertID: 1)

        #expect(viewModel.state == .loaded(alerts)) // preserved
        #expect(viewModel.mutationError == "The server is having trouble. Please try again shortly.")
    }

    @Test
    func concurrentDeleteForTheSameAlertOnlyProducesOneRequest() async {
        let service = StubAlertService(deleteResult: .success(()), delayNanoseconds: 20_000_000)
        let viewModel = AlertViewModel(service: service, logger: TestLogger())

        async let first: Void = viewModel.deleteAlert(alertID: 1)
        async let second: Void = viewModel.deleteAlert(alertID: 1)
        _ = await [first, second]

        #expect(await service.deleteCallCount == 1)
    }

    // MARK: - Scan

    @Test
    func scanNowStoresTheSummaryOnSuccess() async {
        let summary = AlertScanSummary(dto: ScanReportDTO(totalAlerts: 3, checkedCount: 3, triggeredCount: 1))
        let service = StubAlertService(scanResult: .success(summary))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())

        await viewModel.scanNow()

        #expect(viewModel.lastScanSummary == summary)
        #expect(viewModel.scanError == nil)
    }

    @Test
    func scanNowFailureSurfacesAScanError() async {
        let service = StubAlertService(scanResult: .failure(APIClientError.server(statusCode: 503, payload: nil)))
        let viewModel = AlertViewModel(service: service, logger: TestLogger())

        await viewModel.scanNow()

        #expect(viewModel.scanError == "The server is having trouble. Please try again shortly.")
        #expect(viewModel.lastScanSummary == nil)
    }
}
