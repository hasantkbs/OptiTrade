// OptiTrade — TradeSignalModels
// HybridTradingEngine tabanlı /api/v1/signals/analyze yanıtına karşılık gelen modeller.

import SwiftUI

/// Backend'deki ``core.ai_trader_persona.TradeSignal`` enum'ının Swift karşılığı.
enum TradeSignal: String, Codable, CaseIterable {
    case strongBuy  = "STRONG_BUY"
    case buy        = "BUY"
    case neutral    = "NEUTRAL"
    case sell       = "SELL"
    case strongSell = "STRONG_SELL"

    var displayName: String {
        switch self {
        case .strongBuy:  return "Güçlü Al"
        case .buy:        return "Al"
        case .neutral:    return "Nötr"
        case .sell:       return "Sat"
        case .strongSell: return "Güçlü Sat"
        }
    }

    var color: Color {
        switch self {
        case .strongBuy:  return .green
        case .buy:        return Color(red: 0.2, green: 0.8, blue: 0.4)
        case .neutral:    return .orange
        case .sell:       return Color(red: 1.0, green: 0.4, blue: 0.3)
        case .strongSell: return .red
        }
    }
}

/// Backend'deki ``core.ai_trader_persona.TradeRecommendation`` Pydantic modelinin
/// birebir karşılığı. Alan adları snake_case JSON'dan ``CodingKeys`` ile eşleniyor.
struct TradeRecommendation: Decodable, Identifiable, Equatable {
    var id: String { symbol }

    let symbol: String
    let marketRegime: String
    let signal: TradeSignal
    let confidenceScore: Int
    let entryPrice: Double
    let stopLoss: Double
    let takeProfit1: Double
    let takeProfit2: Double
    let traderCommentary: String

    enum CodingKeys: String, CodingKey {
        case symbol
        case marketRegime    = "market_regime"
        case signal
        case confidenceScore = "confidence_score"
        case entryPrice      = "entry_price"
        case stopLoss        = "stop_loss"
        case takeProfit1     = "take_profit_1"
        case takeProfit2     = "take_profit_2"
        case traderCommentary = "trader_commentary"
    }

    /// Backend'deki ``MarketRegime`` enum değerlerinin (core/regime_scanner.py)
    /// okunabilir Türkçe karşılığı.
    var marketRegimeDisplayName: String {
        switch marketRegime {
        case "TRENDING_BULL":          return "Yükseliş Trendi"
        case "TRENDING_BEAR":          return "Düşüş Trendi"
        case "RANGE_BOUND":            return "Yatay Seyir"
        case "CHOPPY_NO_OPPORTUNITY":  return "Kararsız Piyasa"
        default:                       return marketRegime
        }
    }
}

/// ``POST /api/v1/signals/analyze`` istek gövdesi.
struct SignalsAnalyzeRequest: Encodable {
    let symbols: [String]
}
