// OptiTrade — UserPreferences
// Kullanıcının piyasa tercihi ve uygulama ayarları.

import Foundation
import FirebaseFirestore
import FirebaseAuth
import SwiftUI

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

enum AppTheme: String, CaseIterable {
    case system = "Sistem"
    case light = "Açık"
    case dark = "Koyu"

    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────

@MainActor
class UserPreferences: ObservableObject {

    @Published var selectedMarket: TradingMarket = .tr
    @Published var hasCompletedOnboarding: Bool  = false
    @Published var isSaving: Bool = false
    @Published var appTheme: AppTheme = .system
    @Published var enableNotifications: Bool = true
    @Published var refreshInterval: Int = 5 // dakika

    private let marketKey = "selectedMarket"
    private let onboardingKey = "hasCompletedOnboarding"
    private let themeKey = "appTheme"
    private let notificationsKey = "enableNotifications"
    private let refreshKey = "refreshInterval"

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
        
        if let themeRaw = UserDefaults.standard.string(forKey: themeKey),
           let theme = AppTheme(rawValue: themeRaw) {
            appTheme = theme
        }
        
        enableNotifications = UserDefaults.standard.object(forKey: notificationsKey) as? Bool ?? true
        let savedRefresh = UserDefaults.standard.integer(forKey: refreshKey)
        refreshInterval = savedRefresh > 0 ? savedRefresh : 5
    }

    func save() {
        UserDefaults.standard.set(selectedMarket.rawValue, forKey: marketKey)
        UserDefaults.standard.set(hasCompletedOnboarding, forKey: onboardingKey)
        UserDefaults.standard.set(appTheme.rawValue, forKey: themeKey)
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

    func setTheme(_ theme: AppTheme) {
        appTheme = theme
        save()
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
                "theme": appTheme.rawValue,
                "notifications": enableNotifications,
                "refreshInterval": refreshInterval,
                "updatedAt": FieldValue.serverTimestamp(),
            ]
        ], merge: true)
    }

    func fetchFromFirebase() async {
        guard let uid = Auth.auth().currentUser?.uid else { return }
        let db = Firestore.firestore()
        guard let doc = try? await db.collection("users").document(uid).getDocument(),
              let prefs = doc.data()?["preferences"] as? [String: Any] else { return }
        
        if let marketRaw = prefs["market"] as? String,
           let market = TradingMarket(rawValue: marketRaw) {
            selectedMarket = market
        }
        
        if let themeRaw = prefs["theme"] as? String,
           let theme = AppTheme(rawValue: themeRaw) {
            appTheme = theme
        }
        
        if let notif = prefs["notifications"] as? Bool {
            enableNotifications = notif
        }
        
        if let interval = prefs["refreshInterval"] as? Int {
            refreshInterval = interval
        }
        
        save()
    }
}
