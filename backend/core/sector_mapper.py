"""
OptiTrade — Sector Mapper
==========================
Sembol → Sektör eşlemesi ve sektör anahtar kelime sözlüğü.

Desteklenen sektörler:
  ENERGY, TECH, FINANCE, HEALTH, CONSUMER, INDUSTRIAL,
  MATERIALS, REAL_ESTATE, UTILITIES, CRYPTO, FOREX, INDICES

Her sektörün iki kelime kümesi var:
  positive_keywords : bu sektör için yükseliş haberleri
  negative_keywords : bu sektör için düşüş haberleri
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Sektör Tanımları
# ─────────────────────────────────────────────────────────────────────────────

SECTOR_KEYWORDS: Dict[str, Dict[str, List[str]]] = {

    "ENERGY": {
        "positive": [
            "oil price rise", "crude surge", "energy demand", "opec cut",
            "opec production cut", "supply shortage", "pipeline", "lng export",
            "natural gas demand", "refinery output", "oil reserve", "energy rally",
            "brent rise", "wti rally", "petroleum demand", "fuel prices rise",
            "energy recovery", "oil output cut", "supply disruption bullish",
            "strait of hormuz open", "tanker flow", "energy transition investment",
        ],
        "negative": [
            "oil price fall", "crude drop", "energy oversupply", "opec increase",
            "oil glut", "pipeline closed", "strait of hormuz closed",
            "hormuz blockade", "hormuz closure", "energy route blocked",
            "oil embargo", "energy sanctions", "refinery shutdown", "fuel demand drop",
            "renewable replace oil", "oil demand decline", "crude inventory build",
            "energy supply blocked", "oil tanker attack", "pipeline explosion",
            "lng terminal shutdown", "energy crisis supply", "oil spill shutdown",
            "opec output increase", "shale production surge",
        ],
        "sector_symbols": [
            "XOM", "CVX", "BP", "SHEL", "TTE", "COP", "EOG", "SLB",
            "MPC", "PSX", "VLO", "OXY", "DVN", "FANG", "HES",
        ],
    },

    "TECH": {
        "positive": [
            "ai breakthrough", "chip demand", "semiconductor shortage",
            "tech earnings beat", "cloud growth", "software revenue",
            "data center expansion", "ai investment", "tech rally",
            "smartphone sales rise", "app revenue", "tech acquisition",
            "ipo success", "tech upgrade cycle", "digital transformation",
            "nvidia demand", "gpu shortage", "quantum computing",
        ],
        "negative": [
            "tech layoffs", "chip oversupply", "tech regulation", "antitrust",
            "data breach", "cyberattack", "tech selloff", "chip ban",
            "semiconductor export ban", "tech bubble", "app store fine",
            "big tech fine", "privacy regulation", "gdpr penalty",
            "tech revenue miss", "silicon valley layoffs", "it spending cut",
        ],
        "sector_symbols": [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMD", "INTC",
            "TSM", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC",
        ],
    },

    "FINANCE": {
        "positive": [
            "fed rate cut", "interest rate cut", "bank earnings beat",
            "loan demand rise", "credit growth", "ipo surge", "m&a activity",
            "financial deregulation", "bank rally", "profit growth bank",
            "mortgage demand rise", "finance sector rally", "hedge fund gains",
            "crypto regulation clarity", "banking sector strength",
        ],
        "negative": [
            "fed rate hike", "interest rate rise", "bank failure",
            "credit crisis", "loan default", "npl rise", "bank run",
            "financial stress", "banking crisis", "recession fears",
            "credit rating downgrade", "debt ceiling", "bank collapse",
            "svb collapse", "lehman", "systemic risk", "liquidity crisis",
            "mortgage default", "subprime", "financial contagion",
        ],
        "sector_symbols": [
            "JPM", "BAC", "GS", "MS", "WFC", "C", "BLK", "AXP",
            "V", "MA", "PYPL", "SQ", "SCHW",
        ],
    },

    "HEALTH": {
        "positive": [
            "fda approval", "drug approval", "clinical trial success",
            "vaccine success", "cancer treatment", "pharma earnings beat",
            "healthcare expansion", "biotech breakthrough", "gene therapy",
            "medical device approval", "hospital capacity", "insurance growth",
        ],
        "negative": [
            "fda rejection", "drug recall", "clinical trial failure",
            "pharma scandal", "opioid lawsuit", "patent expiry",
            "generic competition", "healthcare cut", "drug pricing regulation",
            "hospital shortage", "medical supply chain", "epidemic outbreak",
            "pandemic risk", "healthcare reform negative",
        ],
        "sector_symbols": [
            "JNJ", "UNH", "PFE", "MRK", "ABBV", "LLY", "BMY",
            "AMGN", "GILD", "CVS", "ABT", "MDT",
        ],
    },

    "CONSUMER": {
        "positive": [
            "retail sales rise", "consumer spending", "holiday sales beat",
            "consumer confidence high", "e-commerce growth", "brand expansion",
            "luxury demand", "consumer credit growth", "spending boom",
        ],
        "negative": [
            "retail sales fall", "consumer spending cut", "inflation impact consumer",
            "consumer debt high", "retail bankruptcy", "store closure",
            "consumer confidence low", "discretionary spending drop",
        ],
        "sector_symbols": [
            "AMZN", "WMT", "HD", "NKE", "MCD", "SBUX", "TGT",
            "COST", "LOW", "TJX", "YUM", "CMG",
        ],
    },

    "INDUSTRIAL": {
        "positive": [
            "manufacturing growth", "pmi expansion", "infrastructure spending",
            "factory output rise", "industrial demand", "supply chain recovery",
            "aerospace order", "defense contract", "construction boom",
        ],
        "negative": [
            "manufacturing decline", "pmi contraction", "factory shutdown",
            "supply chain disruption", "trade war", "tariff increase",
            "industrial recession", "capex cut", "logistics crisis",
        ],
        "sector_symbols": [
            "CAT", "DE", "HON", "MMM", "GE", "BA", "LMT", "RTX",
            "UPS", "FDX", "CSX", "NSC",
        ],
    },

    "MATERIALS": {
        "positive": [
            "gold price rise", "silver rally", "copper demand",
            "iron ore price rise", "steel demand", "commodity rally",
            "lithium demand", "rare earth shortage", "mining output cut",
        ],
        "negative": [
            "gold price fall", "metal prices drop", "copper surplus",
            "steel oversupply", "commodity selloff", "mining strike",
            "lithium oversupply", "iron ore fall",
        ],
        "sector_symbols": [
            "GLD", "SLV", "FCX", "NEM", "GOLD", "AA", "CF",
            "MOS", "ALB", "SQM",
        ],
    },

    "CRYPTO": {
        "positive": [
            "bitcoin rally", "btc surge", "crypto adoption", "etf approval",
            "institutional bitcoin", "crypto regulation clarity",
            "blockchain growth", "defi expansion", "nft market",
            "ethereum upgrade", "crypto bull", "bitcoin halving",
            "spot bitcoin etf", "crypto exchange launch",
        ],
        "negative": [
            "bitcoin crash", "crypto selloff", "exchange hack", "crypto ban",
            "bitcoin bear", "defi exploit", "crypto regulation crackdown",
            "exchange bankruptcy", "ftx collapse", "crypto fraud",
            "51% attack", "stablecoin depeg", "crypto market crash",
            "cbdc threat", "mining ban",
        ],
        "sector_symbols": [
            "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
            "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "MATIC-USD",
            "COIN", "MSTR", "MARA", "RIOT",
        ],
    },

    "GEOPOLITICAL": {
        "positive": [
            "ceasefire", "peace deal", "trade agreement", "sanctions lifted",
            "diplomatic resolution", "trade deal signed", "tariff reduction",
            "economic cooperation", "g7 agreement", "imf support",
        ],
        "negative": [
            "war", "conflict escalation", "sanctions imposed", "trade war",
            "military strike", "nato tension", "russia ukraine",
            "taiwan strait", "north korea missile", "iran nuclear",
            "oil embargo", "energy weaponization", "supply chain war",
            "straits blockade", "shipping lane blocked",
        ],
        "sector_symbols": [],  # Tüm piyasaları etkiler
    },

    "MACRO": {
        "positive": [
            "gdp growth", "jobs report beat", "unemployment falls",
            "inflation cooling", "soft landing", "economic expansion",
            "consumer confidence high", "pce below expectation",
            "federal reserve dovish", "rate cut expected",
        ],
        "negative": [
            "gdp contraction", "recession", "unemployment rise",
            "inflation surge", "stagflation", "cpi above expectation",
            "federal reserve hawkish", "rate hike", "debt crisis",
            "banking sector stress", "yield curve inversion",
            "hard landing", "economic slowdown",
        ],
        "sector_symbols": [],  # Tüm piyasaları etkiler
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Sembol → Sektör Eşleme
# ─────────────────────────────────────────────────────────────────────────────

def get_sector(symbol: str) -> str:
    """Sembole göre sektör kodu döndürür."""
    symbol_upper = symbol.upper().replace("=X", "")
    for sector, data in SECTOR_KEYWORDS.items():
        if symbol_upper in [s.upper() for s in data.get("sector_symbols", [])]:
            return sector
    # Kripto suffix kontrolü
    if symbol_upper.endswith("-USD") or symbol_upper in (
        "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE"
    ):
        return "CRYPTO"
    # Forex
    if len(symbol_upper) == 6 and symbol_upper.isalpha():
        return "FOREX"
    return "MACRO"  # bilinmeyen = makro haberler


def get_sector_keywords(sector: str) -> Tuple[List[str], List[str]]:
    """Sektöre ait (pozitif, negatif) anahtar kelime listelerini döndürür."""
    data = SECTOR_KEYWORDS.get(sector, SECTOR_KEYWORDS["MACRO"])
    return data.get("positive", []), data.get("negative", [])


def get_related_sectors(symbol: str) -> List[str]:
    """Sembolün etkilenebileceği tüm sektörleri döndürür."""
    primary = get_sector(symbol)
    # MACRO ve GEOPOLITICAL her zaman dahil
    sectors = list({primary, "MACRO", "GEOPOLITICAL"})
    return sectors
