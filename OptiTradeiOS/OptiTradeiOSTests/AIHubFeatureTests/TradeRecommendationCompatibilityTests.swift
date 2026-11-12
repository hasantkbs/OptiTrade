import Foundation
import Testing
@testable import OptiTradeiOS

/// Task 0.1.1 — regression coverage for the iOS/backend compatibility bug
/// introduced by backend Task 0.1 (CTO Remediation Plan Revision 4,
/// Finding 8's risk-geometry fix): a SELL/STRONG_SELL/NEUTRAL
/// `TradeRecommendation` now legitimately carries `null` for
/// `stop_loss`/`take_profit_1`/`take_profit_2`, since `DynamicRiskManager`
/// only computes long-side risk geometry. Before this fix,
/// `TradeRecommendation` declared these three fields non-optional, so
/// `JSONDecoder` threw on the *entire* `[TradeRecommendation]` array the
/// moment any one element carried a `null` - not just that one element.
struct TradeRecommendationDecodingTests {
    /// Field set and order match `TradeRecommendation.model_dump_json()`'s
    /// real, verified output exactly (`backend/src/core/ai_trader_persona.py`),
    /// including `signal_source` - a real field Task 0.1 added to the wire
    /// response that the Swift model does not yet declare. Swift's
    /// `Decodable` ignores unrecognized keys by default, so including it
    /// here (rather than a convenient smaller shape) proves decoding
    /// against the actual current contract, not a fake/simplified one.
    private static func recommendationJSON(
        symbol: String, signal: String, stopLoss: String, takeProfit1: String, takeProfit2: String
    ) -> String {
        """
        {
          "symbol": "\(symbol)",
          "market_regime": "TRENDING_BULL",
          "trader_analysis": "Test trader analysis.",
          "investor_analysis": "Test investor analysis.",
          "signal": "\(signal)",
          "confidence_score": 72,
          "entry_price": 180.25,
          "stop_loss": \(stopLoss),
          "take_profit_1": \(takeProfit1),
          "take_profit_2": \(takeProfit2),
          "signal_source": "decision_engine",
          "trader_commentary": "Test commentary."
        }
        """
    }

    @Test
    func buyRecommendationWithAllRiskLevelsDecodes() throws {
        let json = Self.recommendationJSON(
            symbol: "AAPL", signal: "BUY", stopLoss: "175.0", takeProfit1: "185.0", takeProfit2: "190.0"
        )
        let data = Data(json.utf8)

        let rec = try JSONDecoder().decode(TradeRecommendation.self, from: data)

        #expect(rec.signal == .buy)
        #expect(rec.stopLoss == 175.0)
        #expect(rec.takeProfit1 == 185.0)
        #expect(rec.takeProfit2 == 190.0)
    }

    @Test
    func sellRecommendationWithNullRiskLevelsDecodes() throws {
        let json = Self.recommendationJSON(
            symbol: "TSLA", signal: "SELL", stopLoss: "null", takeProfit1: "null", takeProfit2: "null"
        )
        let data = Data(json.utf8)

        let rec = try JSONDecoder().decode(TradeRecommendation.self, from: data)

        #expect(rec.signal == .sell)
        #expect(rec.stopLoss == nil)
        #expect(rec.takeProfit1 == nil)
        #expect(rec.takeProfit2 == nil)
        // entry_price/signal/confidence_score are never null for an
        // actually-returned recommendation - unaffected by this fix.
        #expect(rec.entryPrice == 180.25)
    }

    @Test
    func neutralRecommendationWithNullRiskLevelsDecodes() throws {
        let json = Self.recommendationJSON(
            symbol: "BTC-USD", signal: "NEUTRAL", stopLoss: "null", takeProfit1: "null", takeProfit2: "null"
        )
        let data = Data(json.utf8)

        let rec = try JSONDecoder().decode(TradeRecommendation.self, from: data)

        #expect(rec.signal == .neutral)
        #expect(rec.stopLoss == nil)
        #expect(rec.takeProfit1 == nil)
        #expect(rec.takeProfit2 == nil)
    }

    @Test
    func arrayContainingBothBuyAndSellRecommendationsDecodesSuccessfully() throws {
        // This is the exact regression this task fixes: before Task
        // 0.1.1, decoding this array threw entirely the moment the SELL
        // element's null fields were hit, losing the valid BUY element too.
        let buy = Self.recommendationJSON(
            symbol: "AAPL", signal: "BUY", stopLoss: "175.0", takeProfit1: "185.0", takeProfit2: "190.0"
        )
        let sell = Self.recommendationJSON(
            symbol: "TSLA", signal: "SELL", stopLoss: "null", takeProfit1: "null", takeProfit2: "null"
        )
        let arrayJSON = "[\(buy), \(sell)]"
        let data = Data(arrayJSON.utf8)

        let recs = try JSONDecoder().decode([TradeRecommendation].self, from: data)

        #expect(recs.count == 2)
        #expect(recs[0].symbol == "AAPL")
        #expect(recs[0].stopLoss == 175.0)
        #expect(recs[1].symbol == "TSLA")
        #expect(recs[1].stopLoss == nil)
    }

    @Test
    func missingRiskLevelKeysDecodeTheSameAsExplicitNull() throws {
        // A field that is absent from the JSON entirely (not just
        // `null`) must decode identically for an Optional field -
        // Swift's synthesized Decodable uses decodeIfPresent for
        // Optional members, which handles both cases the same way.
        let json = """
        {
          "symbol": "ETH-USD",
          "market_regime": "CHOPPY_NO_OPPORTUNITY",
          "signal": "NEUTRAL",
          "confidence_score": 40,
          "entry_price": 3200.5,
          "trader_commentary": "No risk levels supplied at all."
        }
        """
        let data = Data(json.utf8)

        let rec = try JSONDecoder().decode(TradeRecommendation.self, from: data)

        #expect(rec.stopLoss == nil)
        #expect(rec.takeProfit1 == nil)
        #expect(rec.takeProfit2 == nil)
    }
}

/// Proves the presentation-layer formatter `TradeRecommendationCard.
/// formattedPriceText(_:)` is nil-safe: a missing risk level must never
/// force-unwrap, never format as a misleading "0.0000", and never crash -
/// it must signal "hide this row" (`nil`) instead.
struct TradeRecommendationCardPresentationTests {
    @Test
    func nilValueProducesNoDisplayText() {
        #expect(TradeRecommendationCard.formattedPriceText(nil) == nil)
    }

    @Test
    func smallRealValueFormatsToFourDecimalPlaces() {
        #expect(TradeRecommendationCard.formattedPriceText(175.5) == "175.5000")
    }

    @Test
    func largeRealValueFormatsToTwoDecimalPlaces() {
        #expect(TradeRecommendationCard.formattedPriceText(3200.5) == "3200.50")
    }

    @Test
    func zeroIsARealValueNotTreatedAsUnavailable() {
        // 0.0 is a legitimate (if unusual) price and must still format,
        // not be confused with "unavailable" (nil) - only `nil` hides a row.
        #expect(TradeRecommendationCard.formattedPriceText(0.0) == "0.0000")
    }
}
