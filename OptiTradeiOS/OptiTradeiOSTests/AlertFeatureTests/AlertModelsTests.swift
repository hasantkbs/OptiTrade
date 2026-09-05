import Foundation
import Testing
@testable import OptiTradeiOS

struct AlertModelsTests {
    @Test
    func alertRuleRequiresARealServerAssignedID() {
        let dtoWithoutID = AlertDTO(
            id: nil, owner: "trader@optitrade.app", watchlistId: nil, symbol: "AAPL", portfolioId: nil,
            category: .price, alertType: .priceAbove, parameters: [:], cooldownMinutes: 60, enabled: true
        )
        #expect(AlertRule(dto: dtoWithoutID) == nil)
    }

    @Test
    func alertRuleCarriesTheRealSymbolAssociation() throws {
        let dto = AlertDTO(
            id: 9, owner: "trader@optitrade.app", watchlistId: nil, symbol: "TSLA", portfolioId: nil,
            category: .decision, alertType: .decisionSell, parameters: [:], cooldownMinutes: 15, enabled: true
        )
        let rule = try #require(AlertRule(dto: dto))

        #expect(rule.id == 9)
        #expect(rule.symbol == "TSLA")
        #expect(rule.category == .decision)
        #expect(rule.alertType == .decisionSell)
        #expect(rule.displayName == "Decision: Sell")
    }

    @Test
    func parameterSummaryIsNilWhenThereAreNoParameters() {
        let dto = AlertDTO(
            id: 1, owner: "trader@optitrade.app", watchlistId: nil, symbol: "AAPL", portfolioId: nil,
            category: .decision, alertType: .decisionBuy, parameters: [:], cooldownMinutes: 60, enabled: true
        )
        let rule = try! #require(AlertRule(dto: dto))
        #expect(rule.parameterSummary == nil)
    }

    @Test
    func parameterSummaryFormatsRealParameterValues() {
        let dto = AlertDTO(
            id: 1, owner: "trader@optitrade.app", watchlistId: nil, symbol: "AAPL", portfolioId: nil,
            category: .price, alertType: .priceAbove, parameters: ["threshold": 200], cooldownMinutes: 60, enabled: true
        )
        let rule = try! #require(AlertRule(dto: dto))
        #expect(rule.parameterSummary == "Threshold: 200")
    }

    @Test
    func creatableTypesAreOnlyThePriceAndDecisionTypesWithAVerifiedParameterContract() {
        #expect(Set(AlertTypeDTO.creatable) == Set([.priceAbove, .priceBelow, .pricePercentMove, .priceGap, .decisionBuy, .decisionSell]))
    }

    @Test
    func priceAboveAndBelowRequireAThresholdParameter() {
        #expect(AlertTypeDTO.priceAbove.requiresThresholdParameter)
        #expect(AlertTypeDTO.priceBelow.requiresThresholdParameter)
        #expect(!AlertTypeDTO.pricePercentMove.requiresThresholdParameter)
        #expect(!AlertTypeDTO.decisionBuy.requiresThresholdParameter)
    }

    @Test
    func percentMoveAndGapHaveAnOptionalThresholdPctParameter() {
        #expect(AlertTypeDTO.pricePercentMove.hasOptionalThresholdPctParameter)
        #expect(AlertTypeDTO.priceGap.hasOptionalThresholdPctParameter)
        #expect(!AlertTypeDTO.priceAbove.hasOptionalThresholdPctParameter)
    }

    @Test
    func eachCreatableTypeMapsToItsRealBackendCategory() {
        #expect(AlertTypeDTO.priceAbove.category == .price)
        #expect(AlertTypeDTO.priceBelow.category == .price)
        #expect(AlertTypeDTO.pricePercentMove.category == .price)
        #expect(AlertTypeDTO.priceGap.category == .price)
        #expect(AlertTypeDTO.decisionBuy.category == .decision)
        #expect(AlertTypeDTO.decisionSell.category == .decision)
    }
}
