import Foundation

enum APIError: LocalizedError {
    case invalidURL
    case noData
    case decodingError(String)
    case serverError(Int)
    case networkError(String)
    case timeout
    case rateLimited
    case noRecommendations

    var errorDescription: String? {
        switch self {
        case .invalidURL:            return "Gecersiz URL"
        case .noData:                return "Veri alinamadi"
        case .decodingError(let m):  return "Ayristirma hatasi: \(m)"
        case .serverError(let c):    return "Sunucu hatasi: \(c)"
        case .networkError(let m):   return "Ag hatasi: \(m)"
        case .timeout:               return "Istek zaman asimina ugradi. AI analizi ilk seferde biraz surebilir, lutfen tekrar deneyin."
        case .rateLimited:           return "Cok fazla istek gonderildi. Lutfen bir dakika sonra tekrar deneyin."
        case .noRecommendations:     return "Secili semboller icin su anda bir AI onerisi uretilemedi."
        }
    }
}

final class APIService {
    static let shared = APIService()

    var baseURL: String = "http://localhost:8000"

    private let decoder = JSONDecoder()
    private init() {}

    func getSessionInfo() async throws -> SessionInfo {
        try await get(url: makeURL(path: "/session/info"))
    }

    func getAllSessions() async throws -> [SessionDefinition] {
        try await get(url: makeURL(path: "/session/all"))
    }

    func analyzeWithSession(symbol: String, assetType: String = "stock") async throws -> SessionInfo {
        let url = try makeURL(path: "/session/analyze")
        let body = AnalysisRequest(symbol: symbol, potentialPrice: nil, assetType: assetType)
        return try await post(url: url, body: body)
    }

    // ── Analyze ───────────────────────────────────────────────────────────────

    func analyze(
        symbol: String,
        potentialPrice: Double? = nil,
        assetType: String = "stock"
    ) async throws -> AnalysisResult {
        let url = try makeURL(path: "/analyze")
        let body = AnalysisRequest(symbol: symbol, potentialPrice: potentialPrice, assetType: assetType)
        return try await post(url: url, body: body)
    }

    /// Enhanced analysis: includes Monte Carlo + composite recommendation.
    func analyzeEnhanced(
        symbol: String,
        potentialPrice: Double? = nil,
        assetType: String = "stock",
        nSimulations: Int = 500,
        nDays: Int = 30
    ) async throws -> AnalysisResult {
        let url = try makeURL(path: "/analyze/enhanced")
        let body = EnhancedAnalysisRequest(
            symbol: symbol,
            potentialPrice: potentialPrice,
            assetType: assetType,
            runMonteCarlo: true,
            nSimulations: nSimulations,
            nDays: nDays
        )
        return try await post(url: url, body: body)
    }

    // ── Portfolio Optimization ────────────────────────────────────────────────

    func optimizePortfolio(symbols: [String], riskTolerance: Double) async throws -> PortfolioOptResult {
        let url = try makeURL(path: "/portfolio/optimize")
        let body = PortfolioOptRequest(symbols: symbols, riskTolerance: riskTolerance)
        return try await post(url: url, body: body)
    }

    // ── Scan ──────────────────────────────────────────────────────────────────

    func scanBIST() async throws -> ScanResult {
        try await get(url: makeURL(path: "/scan/bist"))
    }

    func scanCrypto() async throws -> ScanResult {
        try await get(url: makeURL(path: "/scan/crypto"))
    }

    func scanMarket(_ market: TradingMarket) async throws -> ScanResult {
        try await get(url: makeURL(path: "/scan/\(market.rawValue.lowercased())"))
    }

    func getBISTSymbols() async throws -> [String] {
        try await get(url: makeURL(path: "/symbols/bist"))
    }

    func getCryptoSymbols() async throws -> [String] {
        try await get(url: makeURL(path: "/symbols/crypto"))
    }

    // ── Sectors ───────────────────────────────────────────────────────────────

    func getSectorsOverview(market: TradingMarket) async throws -> SectorsResponse {
        guard var components = URLComponents(string: baseURL + "/sectors/overview") else {
            throw APIError.invalidURL
        }
        components.queryItems = [URLQueryItem(name: "market", value: market.rawValue)]
        guard let url = components.url else { throw APIError.invalidURL }
        return try await get(url: url)
    }

    func getMarketSymbols(_ market: TradingMarket) async throws -> MarketWatchlistResponse {
        try await get(url: makeURL(path: "/market/watchlist/\(market.rawValue)"))
    }

    func getMarketList() async throws -> [String: MarketInfo] {
        struct Wrapper: Decodable { let markets: [String: MarketInfo] }
        let w: Wrapper = try await get(url: makeURL(path: "/market/list"))
        return w.markets
    }

    // ── News ──────────────────────────────────────────────────────────────────

    /// Aktif uygulama diline göre backend'e gönderilecek "lang" değeri ("tr"|"en").
    /// Haber başlıkları bu dile çevrilir (orijinal kaynak dilinden bağımsız).
    private var newsLang: String { LocalizationManager.shared.language.rawValue }

    /// Piyasayı belirtmeden çağırır; backend sembolden piyasayı otomatik tespit eder (AUTO).
    func fetchNews(symbol: String) async throws -> NewsAnalysis {
        guard var components = URLComponents(string: baseURL + "/news/\(symbol)") else {
            throw APIError.invalidURL
        }
        components.queryItems = [URLQueryItem(name: "lang", value: newsLang)]
        guard let url = components.url else { throw APIError.invalidURL }
        return try await get(url: url)
    }

    func fetchNews(symbol: String, market: TradingMarket = .us) async throws -> NewsAnalysis {
        guard var components = URLComponents(string: baseURL + "/news/\(symbol)") else {
            throw APIError.invalidURL
        }
        components.queryItems = [
            URLQueryItem(name: "market", value: market.rawValue),
            URLQueryItem(name: "lang", value: newsLang),
        ]
        guard let url = components.url else { throw APIError.invalidURL }
        return try await get(url: url)
    }

    /// Sembole bağlı olmayan genel piyasa gündemi (BIST + ABD + kripto, TR+EN).
    func fetchMarketNews() async throws -> TopicNewsResponse {
        guard var components = URLComponents(string: baseURL + "/news/market") else {
            throw APIError.invalidURL
        }
        components.queryItems = [URLQueryItem(name: "lang", value: newsLang)]
        guard let url = components.url else { throw APIError.invalidURL }
        return try await get(url: url)
    }

    /// Serbest metin sorgusu için haber (örn. bir sektör adı) — sembol gerektirmez.
    func fetchTopicNews(query: String) async throws -> TopicNewsResponse {
        guard var components = URLComponents(string: baseURL + "/news/topic") else {
            throw APIError.invalidURL
        }
        components.queryItems = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "lang", value: newsLang),
        ]
        guard let url = components.url else { throw APIError.invalidURL }
        return try await get(url: url)
    }

    func fetchSectorNews(symbols: [String], market: TradingMarket) async throws -> SectorNewsResponse {
        let url = try makeURL(path: "/news/sector")
        let body: [String: Any] = ["symbols": symbols, "market": market.rawValue]
        let data = try JSONSerialization.data(withJSONObject: body)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let headers = await authHeaders()
        headers.forEach { request.setValue($1, forHTTPHeaderField: $0) }
        request.httpBody = data
        let (responseData, response) = try await URLSession.shared.data(for: request)
        try validateResponse(response)
        return try decode(responseData)
    }

    // ── User Preferences ──────────────────────────────────────────────────────

    func saveMarketPreference(market: TradingMarket, uid: String) async throws {
        let url = try makeURL(path: "/user/preferences")
        struct Body: Encodable { let market: String; let uid: String }
        let _: [String: String] = try await post(url: url, body: Body(market: market.rawValue, uid: uid))
    }

    // ── Chart & Price ─────────────────────────────────────────────────────────

    func getChart(symbol: String, period: String = "3mo") async throws -> ChartResponse {
        guard var components = URLComponents(string: baseURL + "/chart/\(symbol)") else {
            throw APIError.invalidURL
        }
        components.queryItems = [URLQueryItem(name: "period", value: period)]
        guard let url = components.url else { throw APIError.invalidURL }
        return try await get(url: url)
    }

    func getPrice(symbol: String) async throws -> PriceResponse {
        try await get(url: makeURL(path: "/price/\(symbol)"))
    }

    // ── AI Hub (Hybrid Trading Engine) ───────────────────────────────────────────

    /// Sembol listesi için ``HybridTradingEngine`` tabanlı hibrit AI ticaret
    /// önerilerini getirir. Backend'de sembol başına 15 dakikalık bir cache
    /// var; cache miss durumunda (yfinance + Groq LLM çağrısı yapıldığından)
    /// ilk istek ~5 saniye sürebilir — bu yüzden varsayılan session
    /// timeout'undan bağımsız, bilinçli olarak 30 saniyelik bir timeout
    /// kullanılıyor. Piyasa rejimi filtresini geçemeyen veya veri
    /// sağlanamayan semboller yanıtta yer almaz.
    func analyzeSignals(symbols: [String]) async throws -> [TradeRecommendation] {
        guard !symbols.isEmpty else { return [] }
        let url = try makeURL(path: "/api/v1/signals/analyze")
        let body = SignalsAnalyzeRequest(symbols: symbols)
        do {
            return try await post(url: url, body: body, timeout: 30)
        } catch APIError.serverError(404) {
            throw APIError.noRecommendations
        } catch let urlError as URLError {
            throw urlError.code == .timedOut
                ? APIError.timeout
                : APIError.networkError(urlError.localizedDescription)
        }
    }

    // ── V2 Engine ─────────────────────────────────────────────────────────────

    func analyzeV2(symbol: String) async throws -> EngineResultV2 {
        try await get(url: makeURL(path: "/v2/analyze/\(symbol)"))
    }

    func scanV2(symbols: [String]) async throws -> [EngineResultV2] {
        let url = try makeURL(path: "/v2/scan")
        return try await post(url: url, body: symbols)
    }

    func getBacktestV2(symbol: String, days: Int = 30) async throws -> [BacktestPointV2] {
        try await get(url: makeURL(path: "/v2/backtest/\(symbol)?days=\(days)"))
    }

    // ── Internals ─────────────────────────────────────────────────────────────

    private func makeURL(path: String) throws -> URL {
        guard let url = URL(string: baseURL + path) else { throw APIError.invalidURL }
        return url
    }

    private func authHeaders() async -> [String: String] {
        guard let token = await FirebaseService.shared.getIDToken() else { return [:] }
        return ["Authorization": "Bearer \(token)"]
    }

    private func get<T: Decodable>(url: URL) async throws -> T {
        var request = URLRequest(url: url)
        let headers = await authHeaders()
        headers.forEach { request.setValue($1, forHTTPHeaderField: $0) }
        let (data, response) = try await URLSession.shared.data(for: request)
        try validateResponse(response)
        return try decode(data)
    }

    private func post<Body: Encodable, T: Decodable>(url: URL, body: Body, timeout: TimeInterval? = nil) async throws -> T {
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        if let timeout { request.timeoutInterval = timeout }
        let headers = await authHeaders()
        headers.forEach { request.setValue($1, forHTTPHeaderField: $0) }
        let (data, response) = try await URLSession.shared.data(for: request)
        try validateResponse(response)
        return try decode(data)
    }

    private func validateResponse(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { return }
        if http.statusCode == 429 {
            throw APIError.rateLimited
        }
        guard (200...299).contains(http.statusCode) else {
            throw APIError.serverError(http.statusCode)
        }
    }

    private func decode<T: Decodable>(_ data: Data) throws -> T {
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error.localizedDescription)
        }
    }
}
