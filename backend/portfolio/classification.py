"""
OptiTrade Portfolio Intelligence Platform — symbol classification.

Sector classification reuses `core.sector_intelligence.SECTOR_DEFINITIONS`
directly (a reverse lookup built once at import time) rather than
maintaining a second sector taxonomy. Country/currency classification
follows the exact symbol-suffix convention already used informally
throughout the codebase (`main.py`'s own `BIST_SYMBOLS`/`CRYPTO_SYMBOLS`
lists, `core.market_config.MARKETS`): a `.IS` suffix is BIST/Turkey/TRY,
a `-USD` suffix is a global/24-7 crypto pair priced in USD, and every
other symbol defaults to the US market priced in USD.
"""
from __future__ import annotations

from typing import Dict

from core.sector_intelligence import SECTOR_DEFINITIONS

UNKNOWN_SECTOR = "OTHER"


def _build_symbol_to_sector() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for sector_key, definition in SECTOR_DEFINITIONS.items():
        for symbol in definition.get("tr_symbols", []) + definition.get("us_symbols", []):
            mapping[symbol.upper()] = sector_key
    return mapping


_SYMBOL_TO_SECTOR = _build_symbol_to_sector()


def sector_for_symbol(symbol: str) -> str:
    return _SYMBOL_TO_SECTOR.get(symbol.upper(), UNKNOWN_SECTOR)


def country_for_symbol(symbol: str) -> str:
    upper = symbol.upper()
    if upper.endswith(".IS"):
        return "TR"
    if upper.endswith("-USD"):
        return "CRYPTO"
    return "US"


def currency_for_symbol(symbol: str) -> str:
    country = country_for_symbol(symbol)
    return {"TR": "TRY", "CRYPTO": "USD", "US": "USD"}[country]
