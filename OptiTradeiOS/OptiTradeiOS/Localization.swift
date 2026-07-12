import Foundation
import Combine

enum AppLanguage: String, CaseIterable, Codable {
    case tr, en

    var displayName: String {
        switch self {
        case .tr: return "Türkçe"
        case .en: return "English"
        }
    }

    var flag: String {
        switch self {
        case .tr: return "🇹🇷"
        case .en: return "🇬🇧"
        }
    }
}

/// Lightweight runtime language switcher. No .strings/.xcstrings catalog —
/// English translations live in `_translations` below, keyed by the Turkish
/// source string already hardcoded across the views. Any string not yet
/// added to the dictionary simply falls back to Turkish under English mode,
/// so partially-localized screens never show blank text.
final class LocalizationManager: ObservableObject {
    static let shared = LocalizationManager()

    @Published var language: AppLanguage {
        didSet { UserDefaults.standard.set(language.rawValue, forKey: Self.storageKey) }
    }

    private static let storageKey = "app_language"

    private init() {
        if let raw = UserDefaults.standard.string(forKey: Self.storageKey),
           let saved = AppLanguage(rawValue: raw) {
            language = saved
        } else {
            // No saved preference yet (first launch) — default to the device's
            // system language so English-phone users see English immediately.
            let deviceLanguage = Locale.preferredLanguages.first ?? "tr"
            language = deviceLanguage.hasPrefix("en") ? .en : .tr
        }
    }

    func string(_ turkish: String) -> String {
        guard language == .en else { return turkish }
        return Self._translations[turkish] ?? turkish
    }

    private static let _translations: [String: String] = [
        // Tab bar
        "Tarama":      "Scan",
        "Analiz":      "Analysis",
        "Beta Trade":  "Beta Trade",
        "Portfoy":     "Portfolio",
        "Daha Fazla":  "More",

        // Dashboard / Tarama
        "Piyasa Taraması": "Market Scan",
        "Hisse":           "Stocks",
        "Kripto":          "Crypto",
        "Piyasa":          "Market",
        "Gösterilen sinyaller yatırım tavsiyesi değildir.": "Signals shown are not investment advice.",

        // Search / sector chips
        "Tümü":            "All",
        "Gündem":          "Trending",
        "Bankacılık":      "Banking",
        "Ulaşım":          "Transportation",
        "Sanayi":          "Industrial",
        "Perakende":       "Retail",

        // Sector intelligence (backend fixed catalog, 10 sectors)
        "Teknoloji":                                   "Technology",
        "Yazılım, yarı iletken, yapay zeka, donanım":  "Software, semiconductors, AI, hardware",
        "Enerji":                                      "Energy",
        "Petrol, doğalgaz, yenilenebilir enerji, rafineriler": "Oil, natural gas, renewable energy, refineries",
        "Finans / Bankacılık":                         "Finance / Banking",
        "Bankalar, sigorta, yatırım şirketleri":       "Banks, insurance, investment companies",
        "Sağlık / İlaç":                                "Healthcare / Pharma",
        "İlaç şirketleri, tıbbi cihaz, biyoteknoloji": "Pharmaceutical companies, medical devices, biotech",
        "Sanayi / Üretim":                             "Industrial / Manufacturing",
        "Metal, çelik, savunma, havacılık, lojistik":  "Metal, steel, defense, aerospace, logistics",
        "Tüketici / Perakende":                        "Consumer / Retail",
        "Perakende, gıda, otomotiv, elektronik tüketici": "Retail, food, automotive, consumer electronics",
        "Havacılık / Ulaşım":                          "Aviation / Transportation",
        "Havayolları, turizm, lojistik":               "Airlines, tourism, logistics",
        "Hammadde / Emtia":                            "Materials / Commodities",
        "Madencilik, altın, çelik, kimya":             "Mining, gold, steel, chemicals",
        "Tarım / Gıda Üretimi":                        "Agriculture / Food Production",
        "Tarım kimyasalları, gıda üretimi, gübre":     "Agricultural chemicals, food production, fertilizer",
        "Holdingler":                                  "Holdings",
        "Diversifiye yatırım şirketleri":              "Diversified investment companies",
        "GÜÇLÜ FIRSAT":     "STRONG OPPORTUNITY",
        "FIRSAT":           "OPPORTUNITY",
        "NÖTR / İZLE":      "NEUTRAL / WATCH",
        "KAÇIN":            "AVOID",
        "GÜÇLÜ KAÇ":        "STRONG AVOID",

        // Trading sessions (backend fixed catalog, 5 sessions)
        "Asya Seansı":      "Asia Session",
        "Tokyo, Hong Kong, Sydney — dar bant, sakin hareketler": "Tokyo, Hong Kong, Sydney — narrow range, calm movements",
        "Londra Seansı":    "London Session",
        "Londra — trendler burada oluşur, yüksek hacim başlar": "London — trends form here, high volume begins",
        "New York Seansı":  "New York Session",
        "New York — haberler gelir, sert hareketler olur": "New York — news breaks, sharp movements occur",
        "Londra + New York Çakışması": "London + New York Overlap",
        "⚡ En volatil saat dilimi — büyük kırılımlar burada oluşur": "⚡ Most volatile time window — major breakouts happen here",
        "Piyasa Kapalı":    "Market Closed",
        "Tüm majör piyasalar kapalı — düşük güvenilirlik": "All major markets closed — low reliability",
        "Asya Seansı başlıyor":              "Asia Session starting",
        "Londra Seansı başlıyor":            "London Session starting",
        "Çakışma başlıyor (EN KRİTİK)":      "Overlap starting (MOST CRITICAL)",
        "New York tek başına devam ediyor":  "New York continuing alone",
        "Piyasa kapanıyor":                  "Market closing",
        "Asya Seansı başlıyor (yarın)":      "Asia Session starting (tomorrow)",

        // Settings / Daha Fazla
        "Ayarlar":                    "Settings",
        "Üyelik":                     "Membership",
        "OptiTrade Pro'ya Geç":       "Upgrade to OptiTrade Pro",
        "Premium Al":                 "Get Premium",
        "Trader Ol":                  "Become a Trader",
        "Trader Paketi Aktif":        "Trader Plan Active",
        "Premium Üyelik Aktif":       "Premium Membership Active",
        "Profil":                     "Profile",
        "Hesap":                      "Account",
        "Bağlantı":                   "Connection",
        "Görünüm & Tercihler":        "Appearance & Preferences",
        "Tema":                       "Theme",
        "Dil":                        "Language",
        "Veri":                       "Data",
        "Hesap İşlemleri":            "Account Actions",
        "Çıkış Yap":                  "Sign Out",
        "Hakkında":                   "About",
        "Versiyon":                   "Version",
        "Web Sitesi":                 "Website",
        "Gizlilik Politikası":        "Privacy Policy",
        "Twitter":                    "Twitter",
        "Bildirimler":                "Notifications",
        "Yenile Süresi":              "Refresh Interval",
        "API Sunucusu":               "API Server",
        "Bağlantıyı Test Et":         "Test Connection",
        "İnternet":                   "Internet",
        "Model":                      "Model",
        "Doğruluk":                   "Accuracy",
        "Arama Geçmişini Temizle":    "Clear Search History",
        "Takip Listesini Sıfırla":    "Reset Watchlist",
        "Başlangıç Ekranını Tekrar Göster": "Show Onboarding Again",
        "Hesabı Tamamen Sıfırla":     "Reset Account Completely",
        "Oturum açılmadı":           "Not signed in",
        "Kullanıcı":                  "User",
        "Yerel":                      "Local",
        "Uzak":                       "Remote",
        "Çevrimiçi":                  "Online",
        "Çevrimdışı":                 "Offline",

        // Portföyüm (real holdings)
        "Portföyüm":               "My Portfolio",
        "Portföyünüz boş. Sağ üstteki + ile sahip olduğunuz hisse veya kripto ekleyin.": "Your portfolio is empty. Use the + button above to add a stock or crypto you own.",
        "Toplam Değer":            "Total Value",
        "Kar/Zarar":               "Profit/Loss",
        "adet":                    "units",
        "Alım Birim Fiyatı":       "Purchase Unit Price",
        "Sembolü girince güncel fiyat otomatik doldurulur; gerekirse değiştirebilirsiniz.": "The current price is filled in automatically once you enter the symbol; you can change it if needed.",
        "Örn: 10":                 "e.g. 10",
        "Örn: 285.50":             "e.g. 285.50",
        "Portföyden Kaldır":       "Remove from Portfolio",
        "Bu pozisyon kaldırılsın mı?": "Remove this position?",
        "Kaldır":                  "Remove",
        "Pozisyonu Düzenle":       "Edit Position",
        "Pozisyon Ekle":           "Add Position",

        // Common actions
        "Vazgeç":   "Cancel",
        "Sıfırla":  "Reset",
        "Temizle":  "Clear",
        "Ekle":     "Add",
        "Kaydet":   "Save",
        "Tamam":    "OK",
        "Düzenle":  "Edit",
        "Sil":      "Delete",
        "Kapat":    "Close",
        "İptal":    "Cancel",
        "Aç":       "Open",

        // Search / Analiz
        "Hisse Analizi":            "Stock Analysis",
        "Varlık Tipi":              "Asset Type",
        "Hisse Senedi":             "Stock",
        "Kripto Para":              "Crypto",
        "Potansiyel fiyat (opsiyonel)": "Potential price (optional)",
        "Analiz ediliyor...":       "Analyzing...",
        "Analiz Et":                "Analyze",
        "Tekrar Dene":              "Try Again",
        "Analiz Sonucu":            "Analysis Result",
        "Öneriler":                 "Suggestions",
        "Son Aramalar":             "Recent Searches",
        "Popüler BIST Hisseleri":   "Popular BIST Stocks",
        "Popüler Kriptolar":        "Popular Crypto",

        // Beta Trade
        "Açık İşlem":               "Open Positions",
        "Açık":                     "Open",
        "Kapalı":                   "Closed",
        "Ağırlıklı K/Z":            "Weighted P/L",
        "Açık İşlem Yok":           "No Open Positions",
        "Yeni bir işlem açmak için + butonuna dokun.": "Tap + to open a new position.",
        "Kapalı İşlem Yok":         "No Closed Positions",
        "Kapattığınız işlemler burada görünür.": "Positions you close will appear here.",
        "Giriş":                    "Entry",
        "Sembol":                   "Symbol",
        "Örn: THYAO.IS veya BTC-USD": "e.g. THYAO.IS or BTC-USD",
        "Güncel Fiyat":             "Current Price",
        "Yön":                      "Direction",
        "Ayrıntılar":               "Details",
        "Varlık Türü":              "Asset Type",
        "Miktar":                   "Quantity",
        "Yeni Beta Trade":          "New Beta Trade",

        // Portföy / Takip
        "Portfoy & Risk Analizi":   "Portfolio & Risk Analysis",
        "Takip Listesi":            "Watchlist",
        "Takip listeniz boş. Sağ üstteki + ile hisse veya kripto ekleyin.": "Your watchlist is empty. Use the + button above to add a stock or crypto.",
        "Tip":                      "Type",
        "Örn: 350 (opsiyonel)":     "e.g. 350 (optional)",
        "Potansiyel Fiyat":         "Potential Price",
        "Potansiyel fiyat girilirse ucuz/pahalı analizi yapılır.": "If a potential price is entered, an under/overvalued analysis is performed.",
        "Sembol Ekle":              "Add Symbol",
        "Portfoy Optimizasyonu":    "Portfolio Optimization",
        "Markowitz Ortalama-Varyans modeli ile optimal agirliklar hesaplanir.": "Optimal weights are calculated using the Markowitz Mean-Variance model.",
        "Sembol ekle (orn. THYAO.IS)": "Add symbol (e.g. THYAO.IS)",
        "Risk Toleransi:":          "Risk Tolerance:",
        "Min Varyans":              "Min Variance",
        "Max Sharpe":               "Max Sharpe",
        "Portfoyu Optimize Et":     "Optimize Portfolio",
        "Optimal Agirliklar":       "Optimal Weights",
        "Yillik Getiri":            "Annual Return",
        "Volatilite":               "Volatility",
        "Sharpe":                   "Sharpe",
        "Monte Carlo Simülasyonu":  "Monte Carlo Simulation",
        "Geometrik Brownian Motion ile 30 gunluk 500 fiyat yolu simüle edilir.": "500 price paths over 30 days are simulated using Geometric Brownian Motion.",
        "Sembol (orn. GARAN.IS)":   "Symbol (e.g. GARAN.IS)",
        "Mevcut Fiyat":             "Current Price",
        "30G Beklenti":             "30D Forecast",
        "Beklenen Getiri":          "Expected Return",
        "Kar Olasiligi":            "Profit Probability",
        "Gunluk Volatilite":        "Daily Volatility",
        "Yillik Sharpe":            "Annual Sharpe",
        "5.–95. Persentil Fiyat Araligi": "5th–95th Percentile Price Range",
        "Yapay Zeka Onerisi":       "AI Recommendation",
        "Yapay Zeka Önerisi":       "AI Recommendation",
        "Birlesik Skor":            "Composite Score",
        "Önerilen Pozisyon":        "Suggested Position",
        "portföyden":               "of portfolio",
        "Gerekce:":                 "Rationale:",
        "Onerilen Pozisyon Buyuklugu": "Suggested Position Size",
        "Cok Dusuk":                "Very Low",
        "Dusuk":                    "Low",
        "Orta":                     "Medium",
        "Yuksek":                   "High",
        "Cok Yuksek":               "Very High",

        // Analysis detail
        "ML Model Güveni":          "ML Model Confidence",
        "Birleşik Skor":            "Composite Score",
        "Gerekçe":                  "Rationale",
        "Monte Carlo Simülasyonu (30 Gün, %d Yol)": "Monte Carlo Simulation (30 Days, %d Paths)",
        "30 Gün":                   "30 Days",
        "Yol":                      "Paths",
        "Mevcut":                   "Current",
        "5. Persentil":             "5th Percentile",
        "Beklenti":                 "Forecast",
        "95. Persentil":            "95th Percentile",
        "Fiyat Grafiği":            "Price Chart",
        "Periyot":                  "Period",
        "Hacim":                    "Volume",
        "Teknik Göstergeler":       "Technical Indicators",
        "Aşırı Alım":               "Overbought",
        "Aşırı Satım":              "Oversold",
        "Normal Bölge":             "Normal Zone",
        "Normal":                   "Normal",
        "MACD":                     "MACD",
        "Sinyal":                   "Signal",
        "Histogram":                "Histogram",
        "MACD Durumu":              "MACD Status",
        "Yükseliş ▲":               "Uptrend ▲",
        "Düşüş ▼":                  "Downtrend ▼",
        "Fiyat Hızı":               "Price Velocity",
        "Hacim Oranı":              "Volume Ratio",
        "Günlük Hacim":             "Daily Volume",
        "Temel Analiz":             "Fundamental Analysis",
        "Bilanço Durumu":           "Balance Sheet Status",
        "Pozitif":                  "Positive",
        "Negatif":                  "Negative",
        "Notr":                     "Neutral",
        "Sinyal Analizi":           "Signal Analysis",
        "AL Sinyalleri":            "BUY Signals",
        "SAT Sinyalleri":           "SELL Signals",
        "İlgili Haberler":          "Related News",
        "İlgili haber bulunamadı.": "No related news found.",
        "Piyasa Haberleri":         "Market News",
        "Haberler yükleniyor...":   "Loading news...",
        "Haber bulunamadı":         "No news found",
        "Daha sonra tekrar deneyin.": "Please try again later.",
        "haber analiz edildi":      "news items analyzed",
        "Olumlu Haber Akışı":       "Positive News Flow",
        "Hafif Olumlu":             "Slightly Positive",
        "Olumsuz Haber Akışı":      "Negative News Flow",
        "Hafif Olumsuz":            "Slightly Negative",
        "Nötr":                     "Neutral",
        "nötr":                     "neutral",
        "öğe":                      "item",
        "sembolü":                  "symbol",
        "Tarama özeti":             "Scan summary",
        "alım":                     "buy",
        "satım":                    "sell",
        "ortalama puan":            "average score",
        "sektörü":                  "sector",
        "seçili":                   "selected",
        "seçili değil":             "not selected",
        "Başarıyla bağlandı":       "Connected successfully",
        "Bağlantı başarısız":       "Connection failed",
        "olarak giriş yapıldı":     "signed in",
        "Takip listesi sıfırlansın mı?": "Reset your watchlist?",
        "Arama geçmişi temizlensin mi?": "Clear your search history?",
        "Hesap sıfırlansın mı?":    "Reset your account?",
        "Tüm veriler, tercihler ve işlem geçmişi silinecek. Başlangıç ekranı yeniden gösterilecek.": "All data, preferences, and trade history will be deleted. The onboarding screen will be shown again.",
        "Hesabınızdan çıkış yapılacak. Verileriniz Firebase'de saklanmaya devam eder.": "You'll be signed out of your account. Your data remains stored in Firebase.",
        "Derin analiz yükleniyor…": "Loading deep analysis…",
        "Fiyat alınamadı":          "Price unavailable",

        // TradingMarket enum (Models.swift) — used in onboarding market cards
        "Türkiye (BIST)":           "Turkey (BIST)",
        "Amerika (NYSE/NASDAQ)":    "United States (NYSE/NASDAQ)",
        "Japonya (Nikkei)":         "Japan (Nikkei)",
        "Kripto (Global)":         "Crypto (Global)",
        "BIST 100 hisseleri, Türkiye ekonomi haberleri": "BIST 100 stocks, Turkish economic news",
        "NYSE/NASDAQ hisseleri, Fed ve ABD ekonomi haberleri": "NYSE/NASDAQ stocks, Fed and US economic news",
        "Nikkei 225 hisseleri, Japonya ekonomi haberleri": "Nikkei 225 stocks, Japanese economic news",
        "Bitcoin, Ethereum ve diğer kripto varlıklar": "Bitcoin, Ethereum, and other crypto assets",
        "Bu analiz yatırım tavsiyesi değildir. Tüm kararlar kullanıcıya aittir.": "This analysis is not investment advice. All decisions are the user's own.",

        // Decision / risk labels (backend-generated)
        "GUCLU AL (LONG)":          "STRONG BUY (LONG)",
        "AL":                       "BUY",
        "GUCLU SAT (SHORT)":        "STRONG SELL (SHORT)",
        "SAT":                      "SELL",
        "NOTR / IZLE":              "NEUTRAL / WATCH",
        "Çok Yüksek Risk":          "Very High Risk",
        "Yüksek Risk":              "High Risk",
        "Orta Risk":                "Medium Risk",
        "Düşük Risk":               "Low Risk",
        "NÖTR":                     "NEUTRAL",
        "Ort. Puan":                "Avg. Score",
        "puan":                     "score",

        // Dashboard scan results
        "En Yüksek Puanlı Hisseler": "Top Scored Stocks",
        "sembol tarandı":           "symbols scanned",
        "Son tarama":               "Last scan",
        "Puana Göre":               "By Score",
        "Değişime Göre":            "By Change",
        "RSI'ya Göre":              "By RSI",
        "Tarama Başlatılıyor":      "Starting Scan",
        "Veriler yükleniyor...":    "Loading data...",

        // Charts
        "Güncel":                   "Current",

        // Session info
        "Seans Analizi":            "Session Analysis",
        "Seans Skoru":              "Session Score",
        "Güven":                    "Confidence",
        "Matematiksel Sinyal Analizi": "Mathematical Signal Analysis",
        "RSI Sinyali":              "RSI Signal",
        "MACD Sinyali":             "MACD Signal",
        "Hacim Sinyali":            "Volume Signal",
        "Kırılım Sinyali":          "Breakout Signal",
        "Kırılım":                  "Breakout",
        "Birleşik Ham Sinyal":      "Composite Raw Signal",
        "Normalize [0–1]":          "Normalized [0–1]",
        "Seans Sinyal Ağırlıkları": "Session Signal Weights",
        "Bu seansta göstergeler aşağıdaki ağırlıklarla değerlendirilir:": "Indicators are weighted as follows in this session:",
        "Anlık Seans Sinyalleri":   "Live Session Signals",
        "Sonraki Geçiş":            "Next Transition",
        "dakika":                   "minutes",
        "Bu Seansta En Aktif":      "Most Active This Session",
        "Seans Takvimi (Türkiye Saati)": "Session Calendar (Turkey Time)",
        "Seans yükleniyor...":      "Loading session...",
        "Asya":                     "Asia",
        "Londra":                   "London",
        "Çakışma ⚡":                "Overlap ⚡",

        // Onboarding
        "Hisse Senedi & Kripto\nAnaliz Asistanı": "Stock & Crypto\nAnalysis Assistant",
        "Teknik Analiz":            "Technical Analysis",
        "RSI, MACD, Bollinger Bands": "RSI, MACD, Bollinger Bands",
        "BIST ve kripto tüm piyasaları tara": "Scan BIST and crypto markets",
        "Favori sembollerini kaydet ve takip et": "Save and track your favorite symbols",
        "Bu uygulama yatırım tavsiyesi vermez.": "This app does not provide investment advice.",
        "Başla":                    "Get Started",
        "Yasal Uyarı & Risk Bildirimi": "Legal Notice & Risk Disclosure",
        "Yatırım Tavsiyesi Değildir": "Not Investment Advice",
        "OptiTrade uygulaması (\"Uygulama\") yalnızca teknik gösterge ve algoritma çıktıları sunar. Uygulama içindeki hiçbir içerik, sinyal, analiz veya öneri; yatırım tavsiyesi, portföy yönetimi önerisi veya aracılık hizmeti niteliği taşımaz.":
            "The OptiTrade app (\"App\") only provides technical indicator and algorithm outputs. No content, signal, analysis, or suggestion in the App constitutes investment advice, portfolio management advice, or brokerage service.",
        "Kullanıcı Sorumluluğu":    "User Responsibility",
        "Tüm yatırım kararları tamamen kullanıcıya aittir. AlgorixStudio ve OptiTrade, uygulamadan elde edilen bilgiler doğrultusunda gerçekleştirilen işlemlerden doğabilecek herhangi bir kayıp, zarar veya finansal sonuçtan sorumlu tutulamaz.":
            "All investment decisions are entirely the user's own. AlgorixStudio and OptiTrade are not liable for any loss, damage, or financial outcome resulting from actions taken based on information obtained from the app.",
        "Geçmiş Performans Garantisi Yoktur": "No Guarantee of Past Performance",
        "Geçmiş analiz doğruluğu veya backtest sonuçları, gelecekteki performansı garanti etmez. Piyasa koşulları öngörülemeyen şekillerde değişebilir.":
            "Past analysis accuracy or backtest results do not guarantee future performance. Market conditions may change unpredictably.",
        "Hisse senedi ve kripto para piyasalarında işlem yapmak ciddi finansal risk içerir. Yatırım yapmadan önce bir finansal danışmana başvurmanız tavsiye edilir.":
            "Trading in stock and cryptocurrency markets carries significant financial risk. It is advisable to consult a financial advisor before investing.",
        "Düzenleyici Uyarı":        "Regulatory Notice",
        "Uygulama hiçbir ülkede düzenleyici kurumlar (SPK, BDDK, SEC vb.) tarafından lisanslı finansal hizmet sağlayıcısı değildir.":
            "The app is not a financial service provider licensed by regulatory bodies (SPK, BDDK, SEC, etc.) in any country.",
        "Yukarıdaki uyarıları okudum, anladım ve kabul ediyorum.": "I have read, understood, and accept the notices above.",
        "Devam Et":                 "Continue",
        "Sunucu Bağlantısı":        "Server Connection",
        "OptiTrade'in çalışması için analiz sunucusuna ihtiyaç vardır. Lokal veya uzak sunucu adresini girin.":
            "OptiTrade needs an analysis server to work. Enter a local or remote server address.",
        "Bağlantı Başarılı":        "Connection Successful",
        "Bağlanamadı":              "Connection Failed",
        "Test ediliyor...":         "Testing...",
        "Hazırsınız!":              "You're Ready!",
        "OptiTrade kullanıma hazır!\n\nVerileriniz tüm cihazlarınızda Firebase ile senkronize edilir.":
            "OptiTrade is ready to use!\n\nYour data is synced across all your devices with Firebase.",
        "Bulut Senkronizasyonu":    "Cloud Sync",
        "Watchlist ve işlemler her cihazda": "Watchlist and trades on every device",
        "Güvenli Giriş":            "Secure Sign-In",
        "Firebase Authentication koruması": "Protected by Firebase Authentication",
        "Kişisel Takip Listesi":    "Personal Watchlist",
        "Hesabınıza özel favori semboller": "Favorite symbols unique to your account",
        "Giriş Yap / Kayıt Ol":     "Sign In / Sign Up",
        "Misafir Olarak Devam Et":  "Continue as Guest",

        // Market selection (live version, embedded in OnboardingView.swift)
        "OptiTrade'e\nHoş Geldiniz": "Welcome to\nOptiTrade",
        "Hangi piyasada işlem yapıyorsunuz?": "Which market do you trade in?",
        "Piyasa Seçimi":            "Market Selection",
        "Haber filtresi ve arama bu tercihle yapılandırılır": "News filtering and search are configured by this preference",
        "Kripto piyasası 7/24 globaldir. Haber filtresi otomatik uygulanır.": "The crypto market is global 24/7. News filtering is applied automatically.",

        // Sector opportunity (live version, embedded in OnboardingView.swift)
        "Sektör Analizi":           "Sector Analysis",
        "Hangi sektörde fırsat var?": "Which sector has an opportunity?",
        "sektör":                   "sectors",
        "En Yüksek Fırsat":         "Top Opportunity",
        "Kripto piyasasında sektör ayrımı yoktur": "There is no sector breakdown in the crypto market",

        // Auth
        "Akilli Borsa Analiz Platformu": "Smart Stock Analysis Platform",
        "Giris Yap":                "Sign In",
        "Kayit Ol":                 "Sign Up",
        "Ad Soyad":                 "Full Name",
        "E-posta":                  "Email",
        "Sifre":                    "Password",
        "Sifre Tekrar":             "Confirm Password",
        "Hesap Olustur":            "Create Account",
        "VEYA":                     "OR",
        "Sifremi Unuttum":          "Forgot Password",
        "OptiTrade yatirim tavsiyesi vermez. Butun kararlar kullaniciya aittir.": "OptiTrade does not provide investment advice. All decisions belong to the user.",
        "Sifre Sifirlama":          "Password Reset",
        "Gonder":                   "Send",
        "Sifre sifirlama maili gonderildi.": "Password reset email sent.",
        "adresine sifre sifirlama maili gonderilecek.": "will receive a password reset email.",
        "E-posta ve sifre bos birakilamaz.": "Email and password cannot be empty.",
        "Sifreler eslesmiyor.":     "Passwords do not match.",
        "Sifre en az 6 karakter olmalidir.": "Password must be at least 6 characters.",
        "Sifre sifirlama maili gonderilemedi.": "Could not send password reset email.",
        "Bu e-posta ile kayitli hesap bulunamadi.": "No account found with this email.",
        "Sifre yanlis. Lutfen tekrar deneyin.": "Incorrect password. Please try again.",
        "Bu e-posta zaten kullanilmaktadir.": "This email is already in use.",
        "Sifre cok zayif. En az 6 karakter girin.": "Password is too weak. Enter at least 6 characters.",

        // Ad banner
        "REKLAM":                   "AD",
        "Google AdMob Alanı":       "Google AdMob Space",

        // Backend recommendation-reason exact strings (risk_level has only 2 possible values here)
        "Risk seviyesi Yuksek — pozisyon buyuklugunu sinirli tutun": "Risk level High — keep position size limited",
        "Risk seviyesi Cok Yuksek — pozisyon buyuklugunu sinirli tutun": "Risk level Very High — keep position size limited",
    ]

    // MARK: - Dynamic backend message translation (scoring signals, session signals, AI reasons)

    /// Backend-generated signal/reason strings (e.g. "RSI cok asiri alim (72.3)") are built
    /// server-side with embedded numbers, so they can't be exact-matched like static UI text.
    /// Instead: replace every numeric run with a placeholder to get a stable "shell", look the
    /// shell up in `_dynamicShells`, then re-insert the original numbers (in order) into the
    /// English shell's placeholders. Falls back to the original Turkish string if the shell
    /// isn't recognized (e.g. wording changed server-side) — never crashes, never blanks.
    func dynamicString(_ turkish: String) -> String {
        guard language == .en else { return turkish }

        if turkish.hasPrefix("DIVERJANS ALIM: ") {
            return "BULLISH DIVERGENCE: " + turkish.dropFirst("DIVERJANS ALIM: ".count)
        }
        if turkish.hasPrefix("DIVERJANS SATIS: ") {
            return "BEARISH DIVERGENCE: " + turkish.dropFirst("DIVERJANS SATIS: ".count)
        }

        let (shell, numbers) = Self.numericShell(of: turkish)
        if let enShell = Self._dynamicShells[shell] {
            return Self.fill(enShell, with: numbers)
        }
        // Some backend messages have no embedded number at all (e.g. a fixed
        // risk-level sentence) and were only added to the static L() dict —
        // fall back to it before giving up.
        return Self._translations[turkish] ?? turkish
    }

    private static func numericShell(of s: String) -> (shell: String, numbers: [String]) {
        let regex = try! NSRegularExpression(pattern: "-?\\d+(?:[.,]\\d+)?")
        let nsrange = NSRange(s.startIndex..<s.endIndex, in: s)
        var numbers: [String] = []
        var shell = ""
        var lastEnd = s.startIndex
        for match in regex.matches(in: s, range: nsrange) {
            guard let range = Range(match.range, in: s) else { continue }
            shell += s[lastEnd..<range.lowerBound]
            shell += "{}"
            numbers.append(String(s[range]))
            lastEnd = range.upperBound
        }
        shell += s[lastEnd...]
        return (shell, numbers)
    }

    private static func fill(_ shell: String, with numbers: [String]) -> String {
        var result = ""
        var numIdx = 0
        var i = shell.startIndex
        while i < shell.endIndex {
            if shell[i...].hasPrefix("{}") {
                result += numIdx < numbers.count ? numbers[numIdx] : "{}"
                numIdx += 1
                i = shell.index(i, offsetBy: 2)
            } else {
                result.append(shell[i])
                i = shell.index(after: i)
            }
        }
        return result
    }

    private static let _dynamicShells: [String: String] = [
        // MARK: scoring.py — compute_score() long/short signal messages
        "Fiyat potansiyelin %{}+ altinda (ucuz)": "Price is {}%+ below potential (cheap)",
        "Fiyat potansiyelin altinda": "Price is below potential",
        "Fiyat potansiyelin %{}+ ustunde (pahali)": "Price is {}%+ above potential (expensive)",
        "Fiyat potansiyelin ustunde": "Price is above potential",
        "RSI cok asiri alim ({})": "RSI extremely overbought ({})",
        "RSI asiri alim bolgesinde ({})": "RSI in overbought zone ({})",
        "RSI cok asiri satim ({})": "RSI extremely oversold ({})",
        "RSI asiri satim bolgesinde ({})": "RSI in oversold zone ({})",
        "RSI hafif alim bolgesi ({})": "RSI mildly bullish zone ({})",
        "RSI hafif satis bolgesi ({})": "RSI mildly bearish zone ({})",
        "Fiyat Bollinger alt bandinin altinda (%B={})": "Price below lower Bollinger band (%B={})",
        "Fiyat Bollinger alt bandina yakin (%B={})": "Price near lower Bollinger band (%B={})",
        "Fiyat Bollinger ust bandinin ustunde (%B={})": "Price above upper Bollinger band (%B={})",
        "Fiyat Bollinger ust bandina yakin (%B={})": "Price near upper Bollinger band (%B={})",
        "Bollinger sikismasi (%{}) — kirilim olasiligi yuksek": "Bollinger squeeze (%{}) — high breakout probability",
        "MACD sinyal cizgisinin ustunde (yukselis)": "MACD above signal line (bullish)",
        "MACD sinyal cizgisinin altinda (dusus)": "MACD below signal line (bearish)",
        "MACD histogram ivmeleniyor": "MACD histogram gaining momentum",
        "MACD histogram yavasliyor (negatif)": "MACD histogram slowing (negative)",
        "EMA {}/{} Altin Kesisim — guclu yukselis sinyali": "EMA {}/{} Golden Cross — strong bullish signal",
        "EMA {}/{} Olum Kesisimi — guclu dusus sinyali": "EMA {}/{} Death Cross — strong bearish signal",
        "EMA {}/{} yukselis pozisyonu": "EMA {}/{} bullish position",
        "EMA {}/{} dusus pozisyonu": "EMA {}/{} bearish position",
        "Guclu yukselis trendi (EMA'dan %{} yukarida)": "Strong uptrend ({}% above EMA)",
        "Hafif yukselis trendi (%{})": "Mild uptrend ({}%)",
        "Guclu dusus trendi (EMA'dan %{} asagida)": "Strong downtrend ({}% below EMA)",
        "Hafif dusus trendi (%{})": "Mild downtrend ({}%)",
        "Hacim cok guclu + sinyal destegi ({}x)": "Very strong volume + signal support ({}x)",
        "Hacim guclu + dusus sinyalleri ({}x)": "Strong volume + bearish signals ({}x)",
        "Hacim ortalamanin {}x ustunde": "Volume {}x above average",
        "Hacim cok zayif — trend onaylanmiyor": "Volume very weak — trend not confirmed",
        "Williams %R asiri satim ({}) — alim firsat bolgesi": "Williams %R oversold ({}) — buying opportunity zone",
        "Williams %R dusuk ({}) — satici baskisi azaliyor": "Williams %R low ({}) — selling pressure easing",
        "Williams %R asiri alim ({}) — satis baskisi artabilir": "Williams %R overbought ({}) — selling pressure may increase",
        "Williams %R yuksek ({}) — dikkatli olun": "Williams %R high ({}) — proceed with caution",
        "CCI cok asiri satim ({}) — guclu geri donus sinyali": "CCI extremely oversold ({}) — strong reversal signal",
        "CCI asiri satim ({})": "CCI oversold ({})",
        "CCI cok asiri alim ({}) — kar alma bolgesi": "CCI extremely overbought ({}) — profit-taking zone",
        "CCI asiri alim ({})": "CCI overbought ({})",
        "CCI sifir bolgesi — momentum sifirlanmis, yon belirsiz": "CCI zero zone — momentum neutralized, direction unclear",
        "Fiyat VWAP'in %{} ustunde — ortalamaya donus riski": "Price {}% above VWAP — mean-reversion risk",
        "Fiyat VWAP'in %{} altinda — destek bolgesi": "Price {}% below VWAP — support zone",
        "ROC guclu yukselis momentumu (%{})": "ROC strong bullish momentum ({}%)",
        "ROC yukselis momentumu (%{})": "ROC bullish momentum ({}%)",
        "ROC guclu dusus momentumu (%{})": "ROC strong bearish momentum ({}%)",
        "ROC dusus momentumu (%{})": "ROC bearish momentum ({}%)",
        "Ichimoku: Fiyat bulutun ustunde — guclu yukselis trendi": "Ichimoku: Price above the cloud — strong uptrend",
        "Ichimoku: Fiyat bulutun altinda — guclu dusus trendi": "Ichimoku: Price below the cloud — strong downtrend",
        "Ichimoku: Fiyat bulut icinde — kararsizlik bolgesi": "Ichimoku: Price inside the cloud — indecision zone",
        "Ichimoku TK kesisimi (boga): Tenkan, Kijun'u kesti — alim sinyali": "Ichimoku TK cross (bullish): Tenkan crossed Kijun — buy signal",
        "Ichimoku TK kesisimi (ayi): Tenkan, Kijun'u asagi kesti — satis sinyali": "Ichimoku TK cross (bearish): Tenkan crossed below Kijun — sell signal",
        "Bilanco pozitif (forwardEPS > trailingEPS)": "Balance sheet positive (forwardEPS > trailingEPS)",
        "Bilanco negatif (forwardEPS < trailingEPS)": "Balance sheet negative (forwardEPS < trailingEPS)",
        "Stochastic aşırı satım (%K={}) — alım fırsatı": "Stochastic oversold (%K={}) — buying opportunity",
        "Stochastic satım bölgesi (%K={})": "Stochastic oversold zone (%K={})",
        "Stochastic aşırı alım (%K={}) — satış baskısı": "Stochastic overbought (%K={}) — selling pressure",
        "Stochastic alım bölgesi (%K={})": "Stochastic overbought zone (%K={})",
        "Stochastic %K > %D ({} > {}) — yükselen momentum": "Stochastic %K > %D ({} > {}) — rising momentum",
        "Stochastic %K < %D ({} < {}) — düşen momentum": "Stochastic %K < %D ({} < {}) — falling momentum",
        "ADX trend zayif ({}) — sinyal güvenilirliği düsük": "ADX trend weak ({}) — signal reliability low",
        "ADX cok guclu trend ({}) — yukselis sinyallerini dogrular": "ADX very strong trend ({}) — confirms bullish signals",
        "ADX cok guclu trend ({}) — dusus sinyallerini dogrular": "ADX very strong trend ({}) — confirms bearish signals",
        "ADX cok guclu trend ({}) ancak yon belirsiz": "ADX very strong trend ({}) but direction unclear",
        "ADX trend guclu ({}) — yukselis momentum onaylandi": "ADX trend strong ({}) — bullish momentum confirmed",
        "ADX trend guclu ({}) — dusus momentum onaylandi": "ADX trend strong ({}) — bearish momentum confirmed",
        "ADX orta gucte trend ({}) — yon dengeli": "ADX medium-strength trend ({}) — direction balanced",
        "ADX belirsiz bölge ({}) — trend henuz olusmuyor": "ADX uncertain zone ({}) — trend not yet forming",
        "Guclu yakinlasma: {} yukselis sinyali ayni anda": "Strong convergence: {} bullish signals at once",
        "Yakinlasma: {} yukselis sinyali": "Convergence: {} bullish signals",
        "Hafif yakinlasma: {} yukselis sinyali": "Mild convergence: {} bullish signals",
        "Guclu yakinlasma: {} dusus sinyali ayni anda": "Strong convergence: {} bearish signals at once",
        "Yakinlasma: {} dusus sinyali": "Convergence: {} bearish signals",
        "Hafif yakinlasma: {} dusus sinyali": "Mild convergence: {} bearish signals",

        // MARK: advanced_analysis.py — _build_reasons()
        "Teknik puan guclu ({}/{})": "Technical score strong ({}/{})",
        "Teknik puan dusuk ({}/{}) — zayif gorulum": "Technical score low ({}/{}) — weak outlook",
        "Teknik puan nötr ({}/{})": "Technical score neutral ({}/{})",
        "XGBoost modeli yukselis ihtimali %{}": "XGBoost model bullish probability {}%",
        "XGBoost modeli dusus ihtimali %{}": "XGBoost model bearish probability {}%",
        "XGBoost modeli notr (%{} yukselis olasiligi)": "XGBoost model neutral ({}% bullish probability)",
        "MC: {}g beklenen getiri %{}, kar olasılığı %{}": "MC: {}d expected return {}%, profit probability {}%",
        "MC: {}g beklenen kayip %{}, VaR(%{})=%{}": "MC: {}d expected loss {}%, VaR({}%)={}%",
        "Sortino orani guclu ({}) — asagı yonlu risk düşük": "Sortino ratio strong ({}) — downside risk low",
        "Sortino orani negatif ({}) — riske gore getiri yetersiz": "Sortino ratio negative ({}) — insufficient risk-adjusted return",
        "Tarihsel max dusus %{} — yuksek volatilite gecmisi": "Historical max drawdown {}% — history of high volatility",

        // MARK: session_analysis.py — _build_session_signals() (session.name × 5 fixed sessions)
        "Asya Seansı: Volatilite çarpanı ×{}": "Asia Session: Volatility multiplier ×{}",
        "Londra Seansı: Volatilite çarpanı ×{}": "London Session: Volatility multiplier ×{}",
        "New York Seansı: Volatilite çarpanı ×{}": "New York Session: Volatility multiplier ×{}",
        "Londra + New York Çakışması: Volatilite çarpanı ×{}": "London + New York Overlap: Volatility multiplier ×{}",
        "Piyasa Kapalı: Volatilite çarpanı ×{}": "Market Closed: Volatility multiplier ×{}",
        "RSI {} — aşırı satım bölgesi, alış sinyali güçlü": "RSI {} — oversold zone, strong buy signal",
        "RSI {} — aşırı alım bölgesi, satış sinyali güçlü": "RSI {} — overbought zone, strong sell signal",
        "RSI {} — nötr bölge, net sinyal yok": "RSI {} — neutral zone, no clear signal",
        "MACD yükseliş momentumu — trend doğrulanıyor": "MACD bullish momentum — trend confirming",
        "MACD düşüş momentumu — trend aşağı yönlü": "MACD bearish momentum — trend pointing down",
        "Yükseliş kırılımı sinyali — anlık fırsat penceresi açık": "Bullish breakout signal — momentary opportunity window open",
        "Düşüş kırılımı sinyali — stop-loss seviyelerini gözden geçirin": "Bearish breakout signal — review your stop-loss levels",
        "⚡ Çakışma seansı: En yüksek volatilite — pozisyon boyutunu dikkatli belirleyin": "⚡ Overlap session: Highest volatility — size positions carefully",
        "Hacim güçlü (×{}) — Asya Seansı onayı": "Strong volume (×{}) — Asia Session confirmation",
        "Hacim güçlü (×{}) — Londra Seansı onayı": "Strong volume (×{}) — London Session confirmation",
        "Hacim güçlü (×{}) — New York Seansı onayı": "Strong volume (×{}) — New York Session confirmation",
        "Hacim güçlü (×{}) — Londra + New York Çakışması onayı": "Strong volume (×{}) — London + New York Overlap confirmation",
        "Hacim güçlü (×{}) — Piyasa Kapalı onayı": "Strong volume (×{}) — Market Closed confirmation",
        "Hacim zayıf (×{}) — Asya Seansı sırasında düşük hacim uyarısı": "Weak volume (×{}) — low-volume warning during Asia Session",
        "Hacim zayıf (×{}) — Londra Seansı sırasında düşük hacim uyarısı": "Weak volume (×{}) — low-volume warning during London Session",
        "Hacim zayıf (×{}) — New York Seansı sırasında düşük hacim uyarısı": "Weak volume (×{}) — low-volume warning during New York Session",
        "Hacim zayıf (×{}) — Londra + New York Çakışması sırasında düşük hacim uyarısı": "Weak volume (×{}) — low-volume warning during London + New York Overlap",
        "Hacim zayıf (×{}) — Piyasa Kapalı sırasında düşük hacim uyarısı": "Weak volume (×{}) — low-volume warning during Market Closed",
    ]
}

/// `L("Ayarlar")` → localized string for the current language.
func L(_ turkish: String) -> String {
    LocalizationManager.shared.string(turkish)
}

/// `LD(signal)` → localized string for backend-generated messages with embedded numbers
/// (scoring signals, AI recommendation reasons, session signals). See `dynamicString(_:)`.
func LD(_ turkish: String) -> String {
    LocalizationManager.shared.dynamicString(turkish)
}
