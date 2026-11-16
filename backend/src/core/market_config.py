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

import json
import logging
import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Dict, List, Optional, Union

from core.instruments import Instrument, InstrumentResolution, Market, ResolutionStatus, resolve_instrument

logger = logging.getLogger(__name__)

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

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_MODEL_ARTIFACTS_DIR = os.path.join(_BACKEND_DIR, "model_artifacts")
SP500_SYMBOLS_PATH = os.path.join(_MODEL_ARTIFACTS_DIR, "sp500_symbols.json")

# Day-one fallback - the exact 28 symbols the old hardcoded US_SYMBOLS
# dict held, captured so a fresh deployment (no sp500_symbols.json yet)
# still serves a real, if small, US universe instead of an empty one.
_SP500_SYMBOLS_SNAPSHOT_2026_11_01: Dict[str, str] = {
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
    "JPM":   "JPMorgan",
    "BAC":   "Bank of America",
    "GS":    "Goldman Sachs",
    "MS":    "Morgan Stanley",
    "V":     "Visa",
    "MA":    "Mastercard",
    "JNJ":   "Johnson & Johnson",
    "LLY":   "Eli Lilly",
    "PFE":   "Pfizer",
    "UNH":   "UnitedHealth",
    "XOM":   "ExxonMobil",
    "CVX":   "Chevron",
    "WMT":   "Walmart",
    "HD":    "Home Depot",
    "MCD":   "McDonald's",
    "CAT":   "Caterpillar",
    "BA":    "Boeing",
    "GE":    "GE Aerospace",
}


_us_symbols_fallback_warned = False


def get_us_symbols() -> Dict[str, str]:
    """Canlı entegrasyonun kullandığı GERÇEK US sembol evreni (S&P 500).
    `sp500_refresh_loop` (main.py) günde bir SP500_SYMBOLS_PATH'teki
    JSON'u günceller - bu fonksiyon dosyayı HER ÇAĞRIDA yeniden okuyor
    (sunucu yeniden başlatılmadan güncellensin diye), dosya yoksa/
    okunamazsa sabit anlık görüntüye düşer. Bu fonksiyon haber başına
    (news/entity_extraction.py, news_analyzer.py) ve her market-for-
    symbol aramasında çağrıldığı için, geri dönüş uyarısı sadece bir
    kez loglanır - her başarılı okuma bayrağı sıfırlar, yeni bir
    başarısızlık dizisi tekrar loglanmasına izin verir."""
    global _us_symbols_fallback_warned
    try:
        with open(SP500_SYMBOLS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _us_symbols_fallback_warned = False
        return dict(data["sp500_symbols"])
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        if not _us_symbols_fallback_warned:
            logger.warning(f"{SP500_SYMBOLS_PATH} okunamadı ({exc}), sabit anlık görüntüye dönülüyor.")
            _us_symbols_fallback_warned = True
        return dict(_SP500_SYMBOLS_SNAPSHOT_2026_11_01)

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
    # Anything else falls through to US - this was already true before
    # get_us_symbols() existed (the old US_SYMBOLS membership check
    # below returned "US" on a hit, and the fallback right after it
    # returned "US" on a miss too), so checking membership here was
    # always dead weight; removed rather than paying a file read for
    # an answer that doesn't change either way.
    return "US"


def get_symbols_for_market(market: str) -> Dict[str, str]:
    """Piyasa kodu için sembol sözlüğünü döndür."""
    market = market.upper()
    if market == "TR":
        return BIST_SYMBOLS
    if market == "CRYPTO":
        return CRYPTO_SYMBOLS
    return get_us_symbols()


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


# Canonical market -> this module's legacy market code. "JP" (in MARKETS)
# has no canonical market: core.instruments treats it as UNSUPPORTED.
LEGACY_MARKET_CODES: Dict[Market, str] = {
    Market.BIST: "TR",
    Market.US: "US",
    Market.CRYPTO: "CRYPTO",
}


class MarketProvenance(StrEnum):
    """Where the market behind a resolve_legacy_symbol() result came from."""
    EXPLICIT_HINT = "EXPLICIT_HINT"      # the caller passed `market`
    SYMBOL_DERIVED = "SYMBOL_DERIVED"    # the symbol alone, no market hint
    LEGACY_INFERRED = "LEGACY_INFERRED"  # get_market_for_symbol(), incl. its US default


@dataclass(frozen=True)
class LegacyResolution:
    """A core.instruments resolution plus the provenance of its market.
    `resolution` is returned unchanged; the properties mirror it."""

    resolution: InstrumentResolution
    provenance: MarketProvenance

    @property
    def status(self) -> ResolutionStatus:
        return self.resolution.status

    @property
    def instrument(self) -> Optional[Instrument]:
        return self.resolution.instrument

    @property
    def reason(self) -> str:
        return self.resolution.reason

    @property
    def ok(self) -> bool:
        return self.resolution.ok


def resolve_legacy_symbol(symbol: object, market: Union[Market, str, None] = None) -> LegacyResolution:
    """Canonical Instrument for a symbol as the legacy code classifies it.

    - `market` given (a legacy code "TR" / "US" / "CRYPTO", any case, or a
      Market): passed to core.instruments as the hint -> EXPLICIT_HINT.
      It may deliberately differ from the legacy classification, and an
      empty or unknown market is an INVALID explicit hint, not "none".
    - No `market`: if the symbol alone resolves to the market legacy
      also assigns it (".IS", "BASE-USD", known indices), that result is
      kept -> SYMBOL_DERIVED. A malformed symbol is INVALID from the
      symbol alone -> SYMBOL_DERIVED. Otherwise the symbol is resolved
      under get_market_for_symbol() -> LEGACY_INFERRED; this is where the
      legacy bare-ticker -> US default lives, never in the resolver.
      Without `market`, a resolved instrument always agrees with the
      legacy classification.

    The resolver's status and instrument are never altered: UNRESOLVED
    and UNSUPPORTED stay failures ("BTC-USDT" is legacy US, not a valid
    US ticker, and is never re-read as crypto). Never raises."""
    if market is not None:
        return LegacyResolution(resolve_instrument(symbol, market=market), MarketProvenance.EXPLICIT_HINT)

    direct = resolve_instrument(symbol)
    if direct.status == ResolutionStatus.INVALID:
        return LegacyResolution(direct, MarketProvenance.SYMBOL_DERIVED)
    legacy_market = get_market_for_symbol(symbol)
    if direct.ok and LEGACY_MARKET_CODES[direct.instrument.market] == legacy_market:
        return LegacyResolution(direct, MarketProvenance.SYMBOL_DERIVED)
    return LegacyResolution(resolve_instrument(symbol, market=legacy_market), MarketProvenance.LEGACY_INFERRED)
