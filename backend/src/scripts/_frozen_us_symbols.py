"""Frozen copy of core/market_config.py's original, pre-2026-11-01
US_SYMBOLS dict (28 symbols), for the research/backfill scripts in
this package only. core.market_config.get_us_symbols() is now dynamic
(the real, changing S&P 500 list) - these scripts already ran once
against this exact 28-symbol universe, and must keep doing so on any
future re-run, or their published results stop being reproducible."""
from typing import Dict

ORIGINAL_US_SYMBOLS_28: Dict[str, str] = {
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
