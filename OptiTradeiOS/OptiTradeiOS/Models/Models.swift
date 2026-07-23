import Foundation
import SwiftUI
import Network
import FirebaseFirestore
import FirebaseAuth

// ── Market Models ─────────────────────────────────────────────────────────────

enum TradingMarket: String, CaseIterable, Codable {
    case tr     = "TR"
    case us     = "US"
    case jp     = "JP"
    case crypto = "CRYPTO"

    var displayName: String {
        switch self {
        case .tr:     return "Türkiye (BIST)"
        case .us:     return "Amerika (NYSE/NASDAQ)"
        case .jp:     return "Japonya (Nikkei)"
        case .crypto: return "Kripto (Global)"
        }
    }

    var flag: String {
        switch self {
        case .tr:     return "🇹🇷"
        case .us:     return "🇺🇸"
        case .jp:     return "🇯🇵"
        case .crypto: return "🌐"
        }
    }

    var description: String {
        switch self {
        case .tr:     return "BIST 100 hisseleri, Türkiye ekonomi haberleri"
        case .us:     return "NYSE/NASDAQ hisseleri, Fed ve ABD ekonomi haberleri"
        case .jp:     return "Nikkei 225 hisseleri, Japonya ekonomi haberleri"
        case .crypto: return "Bitcoin, Ethereum ve diğer kripto varlıklar"
        }
    }

    var indexSymbol: String {
        switch self {
        case .tr:     return "XU100.IS"
        case .us:     return "^GSPC"
        case .jp:     return "^N225"
        case .crypto: return "BTC-USD"
        }
    }

    var indexName: String {
        switch self {
        case .tr:     return "BIST 100"
        case .us:     return "S&P 500"
        case .jp:     return "Nikkei 225"
        case .crypto: return "Bitcoin"
        }
    }

    var defaultWatchlist: [String] {
        switch self {
        case .tr:
            return ["GARAN.IS","THYAO.IS","EREGL.IS","ASELS.IS","KCHOL.IS",
                    "AKBNK.IS","TUPRS.IS","SISE.IS","BIMAS.IS","FROTO.IS"]
        case .us:
            return ["AAPL","MSFT","NVDA","GOOGL","META","TSLA","JPM","V","XOM","HD"]
        case .jp:
            return ["7203.T", "9984.T", "8035.T", "6758.T", "9432.T"]
        case .crypto:
            return ["BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD"]
        }
    }

    func normalizeSymbol(_ symbol: String) -> String {
        let s = symbol.uppercased().trimmingCharacters(in: .whitespaces)
        if self == .tr && !s.hasSuffix(".IS") {
            return s + ".IS"
        }
        if self == .jp && !s.hasSuffix(".T") && s.count == 4 && Int(s) != nil {
            return s + ".T"
        }
        return s
    }
}

struct MarketInfo: Decodable {
    let name:         String
    let flag:         String?
    let currency:     String?
    let timezone:     String?
    let sessionOpen:  String?
    let sessionClose: String?
    let indexSymbol:  String?
    let indexName:    String?
    let description:  String?

    enum CodingKeys: String, CodingKey {
        case name, flag, currency, timezone, description
        case sessionOpen  = "session_open"
        case sessionClose = "session_close"
        case indexSymbol  = "index_symbol"
        case indexName    = "index_name"
    }
}

struct MarketWatchlistResponse: Decodable {
    let market:    String
    let info:      MarketInfo?
    let watchlist: [String]
    let symbols:   [String: String]
}

// ── Sector Models ─────────────────────────────────────────────────────────────

struct SectorOverview: Decodable, Identifiable {
    var id: String { sector }
    let sector:           String
    let nameTr:           String
    let icon:             String
    let description:      String
    let market:           String
    let opportunityScore: Double
    let trend:            String
    let opportunityLabel: String
    let avgTechnical:     Double
    let avgNewsDelta:     Double
    let avgChangePct:     Double
    let bullishCount:     Int
    let totalCount:       Int
    let topSymbols:       [String]
    let advice:           String
    let risk:             String

    enum CodingKeys: String, CodingKey {
        case sector, icon, description, market, trend, advice, risk
        case nameTr           = "name_tr"
        case opportunityScore = "opportunity_score"
        case opportunityLabel = "opportunity_label"
        case avgTechnical     = "avg_technical"
        case avgNewsDelta     = "avg_news_delta"
        case avgChangePct     = "avg_change_pct"
        case bullishCount     = "bullish_count"
        case totalCount       = "total_count"
        case topSymbols       = "top_symbols"
    }

    var trendColor: Color {
        switch trend {
        case "STRONG_BULL": return Color(hex: "#00FF88")
        case "BULLISH":     return Color(hex: "#44CC66")
        case "STRONG_BEAR": return .red
        case "BEARISH":     return Color(hex: "#FF6644")
        default:            return .gray
        }
    }

    var trendEmoji: String {
        switch trend {
        case "STRONG_BULL": return "🚀"
        case "BULLISH":     return "📈"
        case "STRONG_BEAR": return "💥"
        case "BEARISH":     return "📉"
        default:            return "➡️"
        }
    }

    var scoreColor: Color {
        if opportunityScore >= 68 { return Color(hex: "#00FF88") }
        if opportunityScore >= 55 { return Color(hex: "#88CC44") }
        if opportunityScore >= 42 { return .gray }
        if opportunityScore >= 30 { return Color(hex: "#FF8844") }
        return .red
    }

    var riskColor: Color {
        switch risk {
        case "LOW":  return .green
        case "HIGH": return .red
        default:     return .orange
        }
    }

    var riskLabel: String {
        switch risk {
        case "LOW":  return "Düşük Risk"
        case "HIGH": return "Yüksek Risk"
        default:     return "Orta Risk"
        }
    }
}

struct SectorsResponse: Decodable {
    let market: String
    let sectors: [SectorOverview]
    struct TopOpportunity: Decodable {
        let sector:  String?
        let nameTr:  String?
        let score:   Double?
        let trend:   String?
        let advice:  String?
        enum CodingKeys: String, CodingKey {
            case sector, trend, advice
            case nameTr = "name_tr"
            case score
        }
    }
    let topOpportunity: TopOpportunity?

    enum CodingKeys: String, CodingKey {
        case market, sectors
        case topOpportunity = "top_opportunity"
    }
}

// ── News Models ───────────────────────────────────────────────────────────────

struct NewsHeadline: Decodable, Identifiable {
    var id: String { title + (publishedAt ?? "") }
    let title:       String
    let sentiment:   String
    let score:       Double
    let ageWeight:   Double?
    let keywords:    [String]?
    let publishedAt: String?

    enum CodingKeys: String, CodingKey {
        case title, sentiment, score
        case ageWeight   = "age_weight"
        case keywords
        case publishedAt = "published_at"
    }
}

struct NewsAnalysis: Decodable {
    let symbol:            String
    let sector:            String?
    let market:            String?
    let totalNews:         Int
    let analyzedNews:      Int
    let sentimentScore:    Double
    let sentimentLabel:    String
    let scoreDelta:        Int
    let positiveCount:     Int
    let negativeCount:     Int
    let neutralCount:      Int
    let signals:           [String]
    let topPositiveTitle:  String?
    let topNegativeTitle:  String?
    let fetchedAt:         String?
    let headlines:         [NewsHeadline]
    let error:             String?

    enum CodingKeys: String, CodingKey {
        case symbol, sector, market, signals, headlines, error
        case totalNews      = "total_news"
        case analyzedNews   = "analyzed_news"
        case sentimentScore = "sentiment_score"
        case sentimentLabel = "sentiment_label"
        case scoreDelta     = "score_delta"
        case positiveCount  = "positive_count"
        case negativeCount  = "negative_count"
        case neutralCount   = "neutral_count"
        case topPositiveTitle = "top_positive_title"
        case topNegativeTitle = "top_negative_title"
        case fetchedAt      = "fetched_at"
    }

    var sentimentColor: Color {
        switch sentimentLabel {
        case "POSITIVE":          return .green
        case "SLIGHTLY_POSITIVE": return Color(hex: "#88CC44")
        case "NEGATIVE":          return .red
        case "SLIGHTLY_NEGATIVE": return Color(hex: "#FF8844")
        default:                  return .gray
        }
    }
}

struct TopicNewsHeadline: Decodable, Identifiable {
    var id: String { title + (publishedAt ?? "") }
    let title:       String
    let source:      String
    let sentiment:   String
    let score:       Double
    let keywords:    [String]?
    let publishedAt: String?

    enum CodingKeys: String, CodingKey {
        case title, source, sentiment, score, keywords
        case publishedAt = "published_at"
    }

    var sentimentColor: Color {
        switch sentiment {
        case "POSITIVE":          return .green
        case "SLIGHTLY_POSITIVE": return Color(hex: "#88CC44")
        case "NEGATIVE":          return .red
        case "SLIGHTLY_NEGATIVE": return Color(hex: "#FF8844")
        default:                  return .gray
        }
    }

    var publishedDate: Date? {
        guard let publishedAt else { return nil }
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = withFraction.date(from: publishedAt) { return d }
        return ISO8601DateFormatter().date(from: publishedAt)
    }
}

struct TopicNewsResponse: Decodable {
    let query:      String?
    let total:      Int
    let headlines:  [TopicNewsHeadline]
    let fetchedAt:  String?

    enum CodingKeys: String, CodingKey {
        case query, total, headlines
        case fetchedAt = "fetched_at"
    }
}

struct SectorNewsResponse: Decodable {
    let symbols:          [String]
    let market:           String
    let sectorSentiment:  Double
    let sectorLabel:      String
    let totalPositive:    Int
    let totalNegative:    Int
    let symbolResults:    [NewsAnalysis]

    enum CodingKeys: String, CodingKey {
        case symbols, market
        case sectorSentiment = "sector_sentiment"
        case sectorLabel     = "sector_label"
        case totalPositive   = "total_positive"
        case totalNegative   = "total_negative"
        case symbolResults   = "symbol_results"
    }
}

// ── Technical Analysis Models ────────────────────────────────────────────────

struct ChartPoint: Decodable, Identifiable {
    var id: String { date }
    let date: String
    let close: Double
    let volume: Double
    let rsi: Double?
}

struct ChartResponse: Decodable {
    let symbol: String
    let period: String
    let points: [ChartPoint]
    let changePct: Double
    let high: Double
    let low: Double

    enum CodingKeys: String, CodingKey {
        case symbol, period, points, high, low
        case changePct = "change_pct"
    }
}

struct TechnicalIndicators: Decodable {
    let rsi: Double?
    let macd: Double?
    let macdSignal: Double?
    let macdHistogram: Double?
    let currentPrice: Double
    let openPrice: Double
    let priceVelocity: Double
    let dailyVolume: Double
    let avgMonthlyVolume: Double
    let volumeRatio: Double

    enum CodingKeys: String, CodingKey {
        case rsi, macd
        case macdSignal = "macd_signal"
        case macdHistogram = "macd_histogram"
        case currentPrice = "current_price"
        case openPrice = "open_price"
        case priceVelocity = "price_velocity"
        case dailyVolume = "daily_volume"
        case avgMonthlyVolume = "avg_monthly_volume"
        case volumeRatio = "volume_ratio"
    }
}

struct AnalysisResult: Decodable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let decision: String
    let decisionCode: String
    let score: Int
    let riskLevel: String
    let balanceStatus: String
    let indicators: TechnicalIndicators
    let shortSignals: [String]
    let longSignals: [String]
    let assetType: String
    let mlConfidence: Double?
    let monteCarlo: MonteCarloResult?
    let recommendation: RecommendationResult?

    enum CodingKeys: String, CodingKey {
        case symbol, decision, score, indicators
        case decisionCode = "decision_code"
        case riskLevel = "risk_level"
        case balanceStatus = "balance_status"
        case shortSignals = "short_signals"
        case longSignals = "long_signals"
        case assetType = "asset_type"
        case mlConfidence = "ml_confidence"
        case monteCarlo = "monte_carlo"
        case recommendation
    }
}

struct ScanResult: Decodable {
    let topBuys: [AnalysisResult]
    let topSells: [AnalysisResult]
    let neutral: [AnalysisResult]
    let totalScanned: Int

    enum CodingKeys: String, CodingKey {
        case topBuys = "top_buys"
        case topSells = "top_sells"
        case neutral
        case totalScanned = "total_scanned"
    }
}

struct MonteCarloResult: Decodable {
    let currentPrice: Double
    let expectedPrice30d: Double
    let expectedReturnPct: Double
    let probProfitPct: Double
    let var95Pct: Double
    let cvar95Pct: Double
    let upside95Price: Double
    let downside5Price: Double
    let dailyVolatilityPct: Double
    let annualSharpe: Double
    let nSimulations: Int
    let nDays: Int

    enum CodingKeys: String, CodingKey {
        case currentPrice = "current_price"
        case expectedPrice30d = "expected_price_30d"
        case expectedReturnPct = "expected_return_pct"
        case probProfitPct = "prob_profit_pct"
        case var95Pct = "var_95_pct"
        case cvar95Pct = "cvar_95_pct"
        case upside95Price = "upside_95_price"
        case downside5Price = "downside_5_price"
        case dailyVolatilityPct = "daily_volatility_pct"
        case annualSharpe = "annual_sharpe"
        case nSimulations = "n_simulations"
        case nDays = "n_days"
    }
}

struct RecommendationResult: Decodable {
    let action: String
    let actionCode: String
    let compositeScore: Double
    let confidencePct: Double
    let color: String
    let suggestedPositionPct: Double
    let reasons: [String]

    enum CodingKeys: String, CodingKey {
        case action
        case actionCode = "action_code"
        case compositeScore = "composite_score"
        case confidencePct = "confidence_pct"
        case color
        case suggestedPositionPct = "suggested_position_pct"
        case reasons
    }
}

// ── Optimization & Session Models ─────────────────────────────────────────────

struct PortfolioOptRequest: Encodable {
    let symbols: [String]
    let riskTolerance: Double

    enum CodingKeys: String, CodingKey {
        case symbols
        case riskTolerance = "risk_tolerance"
    }
}

struct PortfolioOptResult: Decodable {
    let symbols: [String]
    let weights: [String: Double]
    let expectedAnnualReturnPct: Double
    let annualVolatilityPct: Double
    let sharpeRatio: Double
    let riskTolerance: Double
    let efficientFrontierSamples: Int

    enum CodingKeys: String, CodingKey {
        case symbols, weights
        case expectedAnnualReturnPct = "expected_annual_return_pct"
        case annualVolatilityPct = "annual_volatility_pct"
        case sharpeRatio = "sharpe_ratio"
        case riskTolerance = "risk_tolerance"
        case efficientFrontierSamples = "efficient_frontier_samples"
    }
}

struct SessionInfo: Decodable {
    let sessionCode: String
    let sessionName: String
    let sessionDescription: String
    let sessionCurrencies: [String]
    let volatilityMultiplier: Double
    let rsiSignal: Double
    let macdSignal: Double
    let volumeSignal: Double
    let breakoutSignal: Double
    let compositeRaw: Double
    let compositeNorm: Double
    let baseScore: Int
    let sessionAdjustedScore: Double
    let confidence: Double
    let sessionSignals: [String]
    let nextSessionMinutes: Int
    let nextSessionLabel: String

    enum CodingKeys: String, CodingKey {
        case sessionCode         = "session_code"
        case sessionName         = "session_name"
        case sessionDescription  = "session_description"
        case sessionCurrencies   = "session_currencies"
        case volatilityMultiplier = "volatility_multiplier"
        case rsiSignal           = "rsi_signal"
        case macdSignal          = "macd_signal"
        case volumeSignal        = "volume_signal"
        case breakoutSignal      = "breakout_signal"
        case compositeRaw        = "composite_raw"
        case compositeNorm       = "composite_norm"
        case baseScore           = "base_score"
        case sessionAdjustedScore = "session_adjusted_score"
        case confidence
        case sessionSignals      = "session_signals"
        case nextSessionMinutes  = "next_session_minutes"
        case nextSessionLabel    = "next_session_label"
    }

    var sessionColor: String {
        switch sessionCode {
        case "OVERLAP": return "FF4444"
        case "NY":      return "FF8800"
        case "LONDON":  return "3399FF"
        case "ASIA":    return "00CCAA"
        default:        return "666666"
        }
    }

    var sessionIcon: String {
        switch sessionCode {
        case "OVERLAP": return "bolt.fill"
        case "NY":      return "flag.fill"
        case "LONDON":  return "building.columns.fill"
        case "ASIA":    return "sun.horizon.fill"
        default:        return "moon.fill"
        }
    }
}

struct SessionDefinition: Decodable, Identifiable {
    var id: String { code }
    let code: String
    let name: String
    let start: String
    let end: String
    let volatilityMult: Double
    let description: String
    let currencies: [String]

    enum CodingKeys: String, CodingKey {
        case code, name, start, end, description, currencies
        case volatilityMult = "volatility_mult"
    }
}

// ── V2 Engine Models ─────────────────────────────────────────────────────────

enum SignalSideV2: String, Codable {
    case buy = "BUY"
    case sell = "SELL"
    case neutral = "NEUTRAL"
    
    var color: Color {
        switch self {
        case .buy: return .green
        case .sell: return .red
        case .neutral: return .gray
        }
    }
}

struct IndicatorOutputV2: Decodable, Identifiable {
    var id: String { indicatorName }
    let indicatorName: String
    let score: Double
    let confidence: Double
    let side: SignalSideV2
    let metadata: [String: JSONValue]

    enum CodingKeys: String, CodingKey {
        case score, confidence, side, metadata
        case indicatorName = "indicator_name"
    }
}

struct EngineResultV2: Decodable, Identifiable {
    var id: String { symbol + timestamp }
    let symbol: String
    let aggregatedScore: Double
    let confidence: Double
    let signals: [IndicatorOutputV2]
    let mlPrediction: MLPredictionV2?
    let riskScore: Double
    let timestamp: String

    enum CodingKeys: String, CodingKey {
        case symbol, confidence, signals, timestamp
        case aggregatedScore = "aggregated_score"
        case mlPrediction = "ml_prediction"
        case riskScore = "risk_score"
    }
}

struct MLPredictionV2: Decodable {
    let probability: Double
    let isBullish: Bool
    let confidence: Double

    enum CodingKeys: String, CodingKey {
        case probability, confidence
        case isBullish = "is_bullish"
    }
}

enum JSONValue: Decodable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case dictionary([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let x = try? container.decode(String.self) {
            self = .string(x)
            return
        }
        if let x = try? container.decode(Double.self) {
            self = .number(x)
            return
        }
        if let x = try? container.decode(Bool.self) {
            self = .bool(x)
            return
        }
        if let x = try? container.decode([String: JSONValue].self) {
            self = .dictionary(x)
            return
        }
        if let x = try? container.decode([JSONValue].self) {
            self = .array(x)
            return
        }
        self = .null
    }
}

struct BacktestPointV2: Decodable, Identifiable {
    var id: String { timestamp }
    let timestamp: String
    let price: Double
    let score: Double
    let signal: String
    let equity: Double
}

// ── Persistence Models ────────────────────────────────────────────────────────

struct SearchHistoryItem: Codable, Identifiable {
    let id: UUID
    let symbol: String
    let assetType: String
    let date: Date
    let score: Int
    let decisionCode: String

    init(from result: AnalysisResult) {
        self.id = UUID()
        self.symbol = result.symbol
        self.assetType = result.assetType
        self.date = Date()
        self.score = result.score
        self.decisionCode = result.decisionCode
    }

    init(id: UUID, symbol: String, assetType: String, date: Date, score: Int, decisionCode: String) {
        self.id = id; self.symbol = symbol; self.assetType = assetType
        self.date = date; self.score = score; self.decisionCode = decisionCode
    }
}

struct WatchlistItemData: Codable, Identifiable {
    let id: UUID
    var symbol: String
    var potentialPrice: Double?
    var assetType: String

    init(symbol: String, potentialPrice: Double? = nil, assetType: String) {
        self.id = UUID()
        self.symbol = symbol
        self.potentialPrice = potentialPrice
        self.assetType = assetType
    }

    init(id: UUID, symbol: String, potentialPrice: Double?, assetType: String) {
        self.id = id; self.symbol = symbol
        self.potentialPrice = potentialPrice; self.assetType = assetType
    }
}

struct PriceResponse: Decodable {
    let symbol: String
    let price: Double
    let changePct: Double
    let timestamp: String

    enum CodingKeys: String, CodingKey {
        case symbol, price, timestamp
        case changePct = "change_pct"
    }
}

struct PaperTrade: Codable, Identifiable {
    let id: UUID
    let symbol: String
    let assetType: String
    let direction: TradeDirection
    let entryPrice: Double
    let quantity: Double
    let entryDate: Date
    var exitPrice: Double?
    var exitDate: Date?
    var isOpen: Bool
    var analysisScore: Int
    var decisionCode: String

    enum TradeDirection: String, Codable, CaseIterable {
        case long  = "LONG"
        case short = "SHORT"

        var label: String { self == .long ? "AL (Long)" : "SAT (Short)" }
        var icon: String  { self == .long ? "arrow.up.right" : "arrow.down.right" }
    }

    var finalPLPercent: Double {
        guard let exit = exitPrice else { return 0 }
        return direction == .long
            ? (exit - entryPrice) / entryPrice * 100
            : (entryPrice - exit) / entryPrice * 100
    }
}

struct PortfolioHolding: Codable, Identifiable {
    let id: UUID
    var symbol: String
    var assetType: String
    var quantity: Double
    var purchasePrice: Double
    var purchaseDate: Date

    init(symbol: String, assetType: String, quantity: Double, purchasePrice: Double, purchaseDate: Date = Date()) {
        self.id = UUID()
        self.symbol = symbol
        self.assetType = assetType
        self.quantity = quantity
        self.purchasePrice = purchasePrice
        self.purchaseDate = purchaseDate
    }

    init(id: UUID, symbol: String, assetType: String, quantity: Double, purchasePrice: Double, purchaseDate: Date) {
        self.id = id
        self.symbol = symbol
        self.assetType = assetType
        self.quantity = quantity
        self.purchasePrice = purchasePrice
        self.purchaseDate = purchaseDate
    }

    var costBasis: Double { quantity * purchasePrice }

    func unrealizedPLPercent(currentPrice: Double) -> Double {
        guard purchasePrice > 0 else { return 0 }
        return (currentPrice - purchasePrice) / purchasePrice * 100
    }

    func unrealizedPLAmount(currentPrice: Double) -> Double {
        (currentPrice - purchasePrice) * quantity
    }

    func marketValue(currentPrice: Double) -> Double {
        currentPrice * quantity
    }
}

// ── App Settings ──────────────────────────────────────────────────────────────

enum AppTheme: String, CaseIterable, Codable {
    case system = "system"
    case dark   = "dark"
    case light  = "light"

    var label: String {
        switch self {
        case .system: return "Sistem"
        case .dark:   return "Karanlik"
        case .light:  return "Aydinlik"
        }
    }

    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .dark:   return .dark
        case .light:  return .light
        }
    }
}

enum SubscriptionLevel: String, Codable, CaseIterable {
    case free     = "FREE"
    case premium  = "PREMIUM"
    case trade    = "TRADE"
}

// ── UserPreferences Logic ─────────────────────────────────────────────────────

@MainActor
class UserPreferences: ObservableObject {

    @Published var selectedMarket: TradingMarket = .tr
    @Published var hasCompletedOnboarding: Bool  = false
    @Published var isSaving: Bool = false
    @Published var enableNotifications: Bool = true
    @Published var refreshInterval: Int = 5 // dakika

    private let marketKey        = "selectedMarket"
    private let onboardingKey    = "hasCompletedOnboarding"
    private let notificationsKey = "enableNotifications"
    private let refreshKey       = "refreshInterval"

    init() {
        load()
    }

    func load() {
        if let raw = UserDefaults.standard.string(forKey: marketKey),
           let market = TradingMarket(rawValue: raw) {
            selectedMarket = market
        }
        hasCompletedOnboarding = UserDefaults.standard.bool(forKey: onboardingKey)
        enableNotifications = UserDefaults.standard.object(forKey: notificationsKey) as? Bool ?? true
        let savedRefresh = UserDefaults.standard.integer(forKey: refreshKey)
        refreshInterval = savedRefresh > 0 ? savedRefresh : 5
    }

    func save() {
        UserDefaults.standard.set(selectedMarket.rawValue, forKey: marketKey)
        UserDefaults.standard.set(hasCompletedOnboarding, forKey: onboardingKey)
        UserDefaults.standard.set(enableNotifications, forKey: notificationsKey)
        UserDefaults.standard.set(refreshInterval, forKey: refreshKey)
    }

    func setMarket(_ market: TradingMarket, saveToFirebase: Bool = true) {
        selectedMarket = market
        save()
        if saveToFirebase {
            Task { await syncToFirebase() }
        }
    }

    func completeOnboarding(market: TradingMarket) {
        setMarket(market)
        hasCompletedOnboarding = true
        save()
    }

    func syncToFirebase() async {
        guard let uid = Auth.auth().currentUser?.uid else { return }
        isSaving = true
        defer { isSaving = false }
        let db = Firestore.firestore()
        try? await db.collection("users").document(uid).setData([
            "preferences": [
                "market":          selectedMarket.rawValue,
                "notifications":   enableNotifications,
                "refreshInterval": refreshInterval,
                "updatedAt":       FieldValue.serverTimestamp(),
            ]
        ], merge: true)
    }

    func fetchFromFirebase() async {
        guard let uid = Auth.auth().currentUser?.uid else { return }
        let db = Firestore.firestore()
        guard let doc = try? await db.collection("users").document(uid).getDocument(),
              let prefs = doc.data()?["preferences"] as? [String: Any],
              let marketRaw = prefs["market"] as? String,
              let market = TradingMarket(rawValue: marketRaw) else { return }
        selectedMarket = market
        if let notif = prefs["notifications"] as? Bool {
            enableNotifications = notif
        }
        if let interval = prefs["refreshInterval"] as? Int {
            refreshInterval = interval
        }
        save()
    }
}

// ── Session Logic ─────────────────────────────────────────────────────────────

final class UserSession: ObservableObject {
    static let shared = UserSession()

    @Published var onboardingDone: Bool {
        didSet { UserDefaults.standard.set(onboardingDone, forKey: "onboarding_done") }
    }
    @Published var disclaimerAccepted: Bool {
        didSet {
            UserDefaults.standard.set(disclaimerAccepted, forKey: "disclaimer_accepted")
            if disclaimerAccepted && disclaimerAcceptedAt == nil {
                disclaimerAcceptedAt = Date()
            }
        }
    }
    @Published var displayName: String {
        didSet { UserDefaults.standard.set(displayName, forKey: "display_name") }
    }
    @Published var userEmail: String {
        didSet { UserDefaults.standard.set(userEmail, forKey: "user_email") }
    }
    @Published var isGuestMode: Bool {
        didSet { UserDefaults.standard.set(isGuestMode, forKey: "is_guest_mode") }
    }
    @Published var appTheme: AppTheme {
        didSet { UserDefaults.standard.set(appTheme.rawValue, forKey: "app_theme") }
    }
    @Published var defaultAssetType: String {
        didSet { UserDefaults.standard.set(defaultAssetType, forKey: "default_asset_type") }
    }
    @Published var showNeutralInScan: Bool {
        didSet { UserDefaults.standard.set(showNeutralInScan, forKey: "show_neutral_scan") }
    }
    @Published var isPremium: Bool {
        didSet { UserDefaults.standard.set(isPremium, forKey: "is_premium") }
    }
    @Published var isAdmin: Bool {
        didSet { UserDefaults.standard.set(isAdmin, forKey: "is_admin") }
    }
    @Published var subscriptionLevel: SubscriptionLevel {
        didSet { UserDefaults.standard.set(subscriptionLevel.rawValue, forKey: "subscription_level") }
    }
    @Published var focusAssets: [String] {
        didSet { UserDefaults.standard.set(focusAssets, forKey: "focus_assets") }
    }
    @Published var isOnline: Bool = true

    private let networkMonitor = NWPathMonitor()
    private let networkMonitorQueue = DispatchQueue(label: "com.optitrade.networkMonitor")

    var disclaimerAcceptedAt: Date? {
        get {
            let t = UserDefaults.standard.double(forKey: "disclaimer_accepted_at")
            return t > 0 ? Date(timeIntervalSince1970: t) : nil
        }
        set {
            UserDefaults.standard.set(newValue?.timeIntervalSince1970 ?? 0, forKey: "disclaimer_accepted_at")
        }
    }

    private init() {
        onboardingDone     = UserDefaults.standard.bool(forKey: "onboarding_done")
        disclaimerAccepted = UserDefaults.standard.bool(forKey: "disclaimer_accepted")
        displayName        = UserDefaults.standard.string(forKey: "display_name") ?? ""
        userEmail          = UserDefaults.standard.string(forKey: "user_email") ?? ""
        isGuestMode        = UserDefaults.standard.bool(forKey: "is_guest_mode")
        appTheme           = AppTheme(rawValue: UserDefaults.standard.string(forKey: "app_theme") ?? "") ?? .dark
        defaultAssetType   = UserDefaults.standard.string(forKey: "default_asset_type") ?? "stock"
        let rawNeutral     = UserDefaults.standard.object(forKey: "show_neutral_scan")
        showNeutralInScan  = rawNeutral != nil ? UserDefaults.standard.bool(forKey: "show_neutral_scan") : true
        isPremium          = UserDefaults.standard.bool(forKey: "is_premium")
        isAdmin            = UserDefaults.standard.bool(forKey: "is_admin")
        subscriptionLevel  = SubscriptionLevel(rawValue: UserDefaults.standard.string(forKey: "subscription_level") ?? "") ?? .free
        focusAssets        = UserDefaults.standard.stringArray(forKey: "focus_assets") ?? []

        networkMonitor.pathUpdateHandler = { [weak self] path in
            DispatchQueue.main.async {
                self?.isOnline = path.status == .satisfied
            }
        }
        networkMonitor.start(queue: networkMonitorQueue)
    }

    func setTheme(_ theme: AppTheme) {
        appTheme = theme
    }

    @MainActor
    func syncFromFirebase() async {
        guard let profile = try? await FirebaseService.shared.fetchUserProfile() else { return }
        displayName       = profile.displayName
        userEmail         = profile.email
        defaultAssetType  = profile.defaultAssetType
        showNeutralInScan = profile.showNeutralInScan
        isPremium         = profile.isPremium
        isAdmin           = profile.isAdmin
        subscriptionLevel = SubscriptionLevel(rawValue: profile.subscriptionLevel) ?? .free
        focusAssets       = profile.focusAssets
        appTheme          = AppTheme(rawValue: profile.appTheme) ?? .dark
    }

    func resetAccount() {
        displayName        = ""
        userEmail          = ""
        isGuestMode        = false
        onboardingDone     = false
        disclaimerAccepted = false
        disclaimerAcceptedAt = nil
        isPremium          = false
        isAdmin            = false
        subscriptionLevel  = .free
        focusAssets        = []
    }

    func watchlist() -> [WatchlistItemData] {
        guard let data = UserDefaults.standard.data(forKey: "watchlist"),
              let items = try? JSONDecoder().decode([WatchlistItemData].self, from: data) else { return [] }
        return items
    }

    func saveWatchlist(_ items: [WatchlistItemData]) {
        if let data = try? JSONEncoder().encode(items) {
            UserDefaults.standard.set(data, forKey: "watchlist")
        }
        Task { try? await FirebaseService.shared.saveWatchlist(items) }
    }

    func paperTrades() -> [PaperTrade] {
        guard let data = UserDefaults.standard.data(forKey: "paper_trades"),
              let items = try? JSONDecoder().decode([PaperTrade].self, from: data) else { return [] }
        return items
    }

    func savePaperTrades(_ items: [PaperTrade]) {
        if let data = try? JSONEncoder().encode(items) {
            UserDefaults.standard.set(data, forKey: "paper_trades")
        }
        Task { try? await FirebaseService.shared.savePaperTrades(items) }
    }

    func portfolioHoldings() -> [PortfolioHolding] {
        guard let data = UserDefaults.standard.data(forKey: "portfolio_holdings"),
              let items = try? JSONDecoder().decode([PortfolioHolding].self, from: data) else { return [] }
        return items
    }

    func savePortfolioHoldings(_ items: [PortfolioHolding]) {
        if let data = try? JSONEncoder().encode(items) {
            UserDefaults.standard.set(data, forKey: "portfolio_holdings")
        }
        Task { try? await FirebaseService.shared.savePortfolioHoldings(items) }
    }

    func searchHistory() -> [SearchHistoryItem] {
        guard let data = UserDefaults.standard.data(forKey: "search_history"),
              let items = try? JSONDecoder().decode([SearchHistoryItem].self, from: data) else { return [] }
        return items
    }

    func addSearchHistory(_ item: SearchHistoryItem) {
        var all = searchHistory()
        all.insert(item, at: 0)
        if all.count > 20 { all = Array(all.prefix(20)) }
        if let data = try? JSONEncoder().encode(all) {
            UserDefaults.standard.set(data, forKey: "search_history")
        }
        Task { try? await FirebaseService.shared.addSearchHistory(item) }
    }

    func clearSearchHistory() {
        UserDefaults.standard.removeObject(forKey: "search_history")
    }
}

struct AnalysisRequest: Encodable {
    let symbol: String
    let potentialPrice: Double?
    let assetType: String

    enum CodingKeys: String, CodingKey {
        case symbol
        case potentialPrice = "potential_price"
        case assetType = "asset_type"
    }
}

struct EnhancedAnalysisRequest: Encodable {
    let symbol: String
    let potentialPrice: Double?
    let assetType: String
    let runMonteCarlo: Bool
    let nSimulations: Int
    let nDays: Int

    enum CodingKeys: String, CodingKey {
        case symbol
        case potentialPrice = "potential_price"
        case assetType = "asset_type"
        case runMonteCarlo = "run_monte_carlo"
        case nSimulations = "n_simulations"
        case nDays = "n_days"
    }
}
