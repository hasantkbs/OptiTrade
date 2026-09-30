"""
OptiTrade — Market Configuration
==================================
TR (BIST), US (NYSE/NASDAQ), CRYPTO piyasaları için:
  • Sembol listeleri
  • Haber anahtar kelimeleri (olumlu/olumsuz)
  • Ekonomik göstergeler
  • Seans bilgileri

Kripto: piyasa ayrımı yok (global 7/24).
Borsa:  TR kullanıcısı BIST haberlerini, US kullanıcısı Wall Street haberlerini görür.
"""
from __future__ import annotations
from typing import Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Piyasa Tanımları
# ─────────────────────────────────────────────────────────────────────────────

MARKETS = {
    "TR": {
        "name":        "Türkiye (BIST)",
        "flag":        "🇹🇷",
        "currency":    "TRY",
        "timezone":    "Europe/Istanbul",
        "session_open":  "10:00",
        "session_close": "18:00",
        "index_symbol":  "XU100.IS",
        "index_name":    "BIST 100",
        "description":   "Borsa İstanbul — Türkiye hisseleri",
    },
    "US": {
        "name":        "Amerika (NYSE/NASDAQ)",
        "flag":        "🇺🇸",
        "currency":    "USD",
        "timezone":    "America/New_York",
        "session_open":  "09:30",
        "session_close": "16:00",
        "index_symbol":  "^GSPC",
        "index_name":    "S&P 500",
        "description":   "New York borsaları",
    },
    "JP": {
        "name":        "Japonya (Nikkei)",
        "flag":        "🇯🇵",
        "currency":    "JPY",
        "timezone":    "Asia/Tokyo",
        "session_open":  "09:00",
        "session_close": "15:00",
        "index_symbol":  "^N225",
        "index_name":    "Nikkei 225",
        "description":   "Tokyo Menkul Kıymetler Borsası",
    },
    "CRYPTO": {
        "name":        "Kripto (Global)",
        "flag":        "🌐",
        "currency":    "USD",
        "timezone":    "UTC",
        "session_open":  "00:00",
        "session_close": "23:59",
        "index_symbol":  "BTC-USD",
        "index_name":    "Bitcoin",
        "description":   "Global kripto piyasası 7/24",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Sembol Listeleri
# ─────────────────────────────────────────────────────────────────────────────

BIST_SYMBOLS = {
    # Bankacılık
    "GARAN.IS": "Garanti BBVA",
    "AKBNK.IS": "Akbank",
    "YKBNK.IS": "Yapı Kredi",
    "ISCTR.IS": "İş Bankası C",
    "HALKB.IS": "Halkbank",
    "VAKBN.IS": "Vakıfbank",
    "QNBFB.IS": "QNB Finansbank",
    "ALBRK.IS": "Albaraka Türk",
    # Sanayi & Holding
    "KCHOL.IS": "Koç Holding",
    "SAHOL.IS": "Sabancı Holding",
    "DOHOL.IS": "Doğan Holding",
    "SISE.IS":  "Şişecam",
    "EREGL.IS": "Ereğli Demir Çelik",
    "KRDMD.IS": "Kardemir",
    "PETKM.IS": "Petkim",
    "TUPRS.IS": "Tüpraş",
    # Teknoloji & Savunma
    "ASELS.IS": "Aselsan",
    "TTKOM.IS": "Türk Telekom",
    "TCELL.IS": "Turkcell",
    "LOGO.IS":  "Logo Yazılım",
    "INDES.IS": "İndeks Bilgisayar",
    # Uçak & Lojistik
    "THYAO.IS": "Türk Hava Yolları",
    "PGSUS.IS": "Pegasus",
    "ULKER.IS": "Ülker Bisküvi",
    # Perakende & Gıda
    "BIMAS.IS": "BİM Mağazalar",
    "MGROS.IS": "Migros",
    "FROTO.IS": "Ford Otosan",
    "TOASO.IS": "Tofaş",
    "ARCLK.IS": "Arçelik",
    "VESTL.IS": "Vestel",
    # Madencilik & Diğer
    "KOZAL.IS": "Koza Altın",
    "SODA.IS":  "Soda Sanayii",
    "ZOREN.IS": "Zorlu Enerji",
    "ENKAI.IS": "Enka İnşaat",
}

US_SYMBOLS = {
    # Teknoloji
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "NVDA":  "NVIDIA",
    "GOOGL": "Alphabet",
    "META":  "Meta",
    "AMZN":  "Amazon",
    "TSLA":  "Tesla",
    "AMD":   "AMD",
    "INTC":  "Intel",
    "CRM":   "Salesforce",
    # Finans
    "JPM":   "JPMorgan",
    "BAC":   "Bank of America",
    "GS":    "Goldman Sachs",
    "MS":    "Morgan Stanley",
    "V":     "Visa",
    "MA":    "Mastercard",
    # Sağlık
    "JNJ":   "Johnson & Johnson",
    "LLY":   "Eli Lilly",
    "PFE":   "Pfizer",
    "UNH":   "UnitedHealth",
    # Enerji
    "XOM":   "ExxonMobil",
    "CVX":   "Chevron",
    # Tüketici
    "WMT":   "Walmart",
    "HD":    "Home Depot",
    "MCD":   "McDonald's",
    # Endüstriyel
    "CAT":   "Caterpillar",
    "BA":    "Boeing",
    "GE":    "GE Aerospace",
}

CRYPTO_SYMBOLS = {
    "BTC-USD":   "Bitcoin",
    "ETH-USD":   "Ethereum",
    "BNB-USD":   "BNB",
    "SOL-USD":   "Solana",
    "XRP-USD":   "XRP",
    "ADA-USD":   "Cardano",
    "DOGE-USD":  "Dogecoin",
    "AVAX-USD":  "Avalanche",
    "LINK-USD":  "Chainlink",
    "MATIC-USD": "Polygon",
    "DOT-USD":   "Polkadot",
    "LTC-USD":   "Litecoin",
    "NEAR-USD":  "NEAR",
    "APT-USD":   "Aptos",
    "ARB-USD":   "Arbitrum",
    "OP-USD":    "Optimism",
    "INJ-USD":   "Injective",
    "TIA-USD":   "Celestia",
}


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Haber Anahtar Kelime Sözlükleri
# ─────────────────────────────────────────────────────────────────────────────

MARKET_NEWS_KEYWORDS: Dict[str, Dict[str, List[str]]] = {

    "TR": {
        "positive": [
            # TCMB & Faiz
            "faiz indirimi", "merkez bankasi faiz", "tcmb faiz indirim",
            "para politikasi gevşeme", "likidite artisi",
            # Ekonomi
            "buyume", "gdp artis", "ihracat artisi", "cari fazla",
            "tuik buyume", "enflasyon dusus", "enflasyon geriledi",
            "bütçe fazlasi", "vergi geliri artis", "turizm geliri",
            # Borsa & Piyasa
            "bist rekor", "bist yukselis", "bist100 artis",
            "yabanci yatirimci alim", "borsa istanbul rekor",
            "halka arz basarisi", "ipo basarili",
            # Şirket Haberleri (TR)
            "net kar artis", "ciro artis", "temettü artis",
            "ihracat rekoru", "uretim artis", "siparis artis",
            "anlaşma imzalandi", "ihale kazanildi", "savunma ihracati",
            "thy yolcu rekoru", "koza altin uretim",
            # Altyapı & Yatırım
            "yatirim artis", "fabrika acilis", "proje tamamlandi",
            "doğalgaz keşfi", "enerji yatirimi",
            # Jeopolitik (TR için pozitif)
            "türkiye nato", "türkiye ab", "diplomatik görüşme",
            "tahil koridoru uzatildi",
        ],
        "negative": [
            # TCMB & Faiz
            "faiz artisi", "merkez bankasi faiz artirdi", "tcmb faiz yükseltti",
            "para politikasi sikileşme", "döviz rezerv azalmasi",
            # Ekonomi (negatif)
            "enflasyon artis", "enflasyon yukseldi", "tufe yukseldi",
            "cari acik artis", "butce acigi", "dis borc artis",
            "issizlik artis", "pmi dusus", "sanayi uretim dusus",
            "ihracat azalma", "turizm azalmasi",
            # TL & Döviz
            "turk lirasi deger kaybi", "tl deger kaybi", "dolar yükseldi",
            "dolar tl rekor", "kur krizi", "döviz krizi",
            "rezerv erimesi", "swap anlaşmasi",
            # Borsa (negatif)
            "bist dusus", "bist satış", "yabanci satisi",
            "borsa istanbul dusus", "endeks geriledi",
            # Şirket (negatif TR)
            "zarar açikladi", "iflas", "konkordato", "icra takibi",
            "kap özel durum negatif", "üretim durduruldu",
            # Jeopolitik (TR için negatif)
            "türkiye yaptırım", "türkiye abd gerilim",
            "türkiye ab gerilim", "karadeniz gerilim",
            "suriye sınır", "deprem hasarı",
        ],
        # İngilizce karşılıklar (yfinance haberleri İngilizce geliyor)
        "positive_en": [
            "turkey gdp growth", "turkey export", "turkey tourism record",
            "bist record", "turkish lira stabilize", "turkey rate cut",
            "central bank turkey cut", "turkey inflation fell",
            "turkey current account surplus", "turkish airline record",
            "turkey defense export", "thy passenger record",
        ],
        "negative_en": [
            "turkey inflation", "turkey rate hike", "turkish lira fell",
            "turkey current account deficit", "turkey recession",
            "turkey sanctions", "turkey us tension", "turkey eu tension",
            "turkish lira record low", "turkey earthquake damage",
            "turkey budget deficit", "bist fell", "istanbul stock",
        ],
    },

    "US": {
        "positive": [
            # Fed & Para Politikası
            "fed rate cut", "federal reserve cut", "dovish fed",
            "rate cut expected", "powell dovish", "quantitative easing",
            "interest rate pause", "fed pause",
            # Ekonomi
            "gdp beat", "gdp growth", "nonfarm payrolls beat",
            "unemployment falls", "jobless claims fall", "pce below",
            "cpi cooled", "inflation cooling", "soft landing",
            "consumer spending rise", "retail sales beat",
            "ism manufacturing expansion", "pmi expansion",
            # Borsa & Şirket
            "earnings beat", "revenue beat", "guidance raised",
            "buyback program", "dividend increase", "s&p 500 record",
            "nasdaq record", "dow record", "ipo success",
            "merger acquisition", "deal announced",
            # Sektörel
            "ai demand surge", "chip demand", "tech earnings beat",
            "bank earnings beat", "oil demand rise",
        ],
        "negative": [
            # Fed & Para Politikası
            "fed rate hike", "federal reserve hike", "hawkish fed",
            "powell hawkish", "quantitative tightening", "qt",
            "higher for longer", "rate hike expected",
            # Ekonomi
            "gdp miss", "gdp contraction", "recession", "stagflation",
            "nonfarm payrolls miss", "unemployment rise",
            "cpi above", "inflation surge", "hard landing",
            "consumer confidence low", "retail sales miss",
            "ism contraction", "pmi contraction",
            "yield curve inversion", "debt ceiling crisis",
            # Borsa
            "earnings miss", "revenue miss", "guidance cut",
            "layoffs", "job cuts", "restructuring",
            "bank failure", "regional bank", "credit crisis",
            # Jeopolitik
            "us china tension", "taiwan strait", "trade war tariff",
            "russia ukraine escalation",
        ],
    },

    "CRYPTO": {
        "positive": [
            "bitcoin etf approval", "spot btc etf", "institutional bitcoin",
            "bitcoin rally", "crypto adoption", "btc surge",
            "ethereum upgrade", "defi growth", "nft market recovery",
            "bitcoin halving", "mining difficulty", "blockchain adoption",
            "crypto regulatory clarity", "el salvador bitcoin",
            "microstrategy bitcoin", "blackrock bitcoin etf",
            "coinbase institutional", "grayscale approval",
            "crypto bull run", "altcoin season",
        ],
        "negative": [
            "bitcoin crash", "crypto selloff", "exchange hack",
            "crypto ban", "bitcoin bear", "defi exploit",
            "exchange bankruptcy", "ftx collapse", "crypto fraud",
            "stablecoin depeg", "usdt concern", "sec crypto",
            "crypto regulation crackdown", "mining ban",
            "bitcoin fork", "51% attack", "rug pull",
            "crypto market manipulation", "wash trading",
        ],
        # Türkçe kripto haberleri
        "positive_tr": [
            "bitcoin rekor", "kripto yükseliş", "ethereum güncelleme",
            "kripto benimseme", "halving yaklaşıyor",
        ],
        "negative_tr": [
            "kripto çöküş", "bitcoin düşüş", "borsa hack",
            "kripto yasak", "stablecoin sorunu",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Yardımcı Fonksiyonlar
# ─────────────────────────────────────────────────────────────────────────────

def get_market_for_symbol(symbol: str) -> str:
    """Sembole bakarak piyasayı tespit et."""
    sym = symbol.upper()
    if sym.endswith(".IS"):
        return "TR"
    if sym.endswith("-USD") or sym in CRYPTO_SYMBOLS:
        return "CRYPTO"
    if sym in US_SYMBOLS:
        return "US"
    # Fallback: yfinance suffix
    return "US"


def get_symbols_for_market(market: str) -> Dict[str, str]:
    """Piyasa kodu için sembol sözlüğünü döndür."""
    market = market.upper()
    if market == "TR":
        return BIST_SYMBOLS
    if market == "CRYPTO":
        return CRYPTO_SYMBOLS
    return US_SYMBOLS


def get_default_watchlist(market: str) -> List[str]:
    """Piyasa için varsayılan izleme listesi."""
    market = market.upper()
    if market == "TR":
        return ["GARAN.IS","THYAO.IS","EREGL.IS","ASELS.IS","KCHOL.IS",
                "AKBNK.IS","TUPRS.IS","SISE.IS","BIMAS.IS","FROTO.IS"]
    if market == "CRYPTO":
        return ["BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD"]
    # US
    return ["AAPL","MSFT","NVDA","GOOGL","META","TSLA","JPM","V","XOM","HD"]


def normalize_symbol(symbol: str, market: str) -> str:
    """
    Kullanıcının girdiği sembole piyasaya göre suffix ekle.
    Örnek: market=TR, symbol=GARAN → GARAN.IS
    """
    sym = symbol.upper().strip()
    if market == "TR" and not sym.endswith(".IS"):
        return sym + ".IS"
    return sym
