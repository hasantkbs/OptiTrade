// OptiTrade — UserPreferences
// Kullanıcının piyasa tercihi ve uygulama ayarları.

import Foundation
import FirebaseFirestore
import FirebaseAuth

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

    // yfinance sembol normalize
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

// ─────────────────────────────────────────────────────────────────────────────

@MainActor
class UserPreferences: ObservableObject {

    @Published var selectedMarket: TradingMarket = .tr
    @Published var hasCompletedOnboarding: Bool  = false
    @Published var isSaving: Bool = false

    private let marketKey    = "selectedMarket"
    private let onboardingKey = "hasCompletedOnboarding"

    init() {
        load()
    }

    // MARK: - Local Persist

    func load() {
        if let raw = UserDefaults.standard.string(forKey: marketKey),
           let market = TradingMarket(rawValue: raw) {
            selectedMarket = market
        }
        hasCompletedOnboarding = UserDefaults.standard.bool(forKey: onboardingKey)
    }

    func save() {
        UserDefaults.standard.set(selectedMarket.rawValue, forKey: marketKey)
        UserDefaults.standard.set(hasCompletedOnboarding, forKey: onboardingKey)
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

    // MARK: - Firebase Sync

    func syncToFirebase() async {
        guard let uid = Auth.auth().currentUser?.uid else { return }
        isSaving = true
        defer { isSaving = false }
        let db = Firestore.firestore()
        try? await db.collection("users").document(uid).setData([
            "preferences": [
                "market":    selectedMarket.rawValue,
                "updatedAt": FieldValue.serverTimestamp(),
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
        save()
    }
}
