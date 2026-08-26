"""
OptiTrade News Engine — relevance scoring.

Reuses `core.news_analyzer._sector_relevance` unchanged (keyword-hit
based sector/market relevance weighting, the same helper
`core.news_analyzer.analyze_news` already relies on internally) together
with the existing `core.sector_mapper` / `core.market_config` keyword
registries - never re-derives sector or market keyword lists.

`_sector_relevance` returns a `[0.5, 1.5]` weight; this module
normalizes that onto `[0, 1]` and blends it with the asset-resolution
confidence (from `asset_resolver.py`) so an article's final relevance
reflects both "is this about the right sector/market" and "does it
actually mention this symbol."
"""
from __future__ import annotations

from core.market_config import MARKET_NEWS_KEYWORDS, get_market_for_symbol
from core.news_analyzer import _sector_relevance as _core_sector_relevance
from core.sector_mapper import SECTOR_KEYWORDS, get_sector, get_sector_keywords
from engines.news.models import AssetResolution, NormalizedArticle


def _keyword_universe(symbol: str) -> tuple:
    sector = get_sector(symbol)
    sector_pos, sector_neg = get_sector_keywords(sector)

    market = get_market_for_symbol(symbol)
    market_kw = MARKET_NEWS_KEYWORDS.get(market, {})
    market_pos = (
        market_kw.get("positive", []) + market_kw.get("positive_en", []) + market_kw.get("positive_tr", [])
    )
    market_neg = (
        market_kw.get("negative", []) + market_kw.get("negative_en", []) + market_kw.get("negative_tr", [])
    )

    macro_pos = SECTOR_KEYWORDS.get("MACRO", {}).get("positive", [])
    macro_neg = SECTOR_KEYWORDS.get("MACRO", {}).get("negative", [])
    geo_pos = SECTOR_KEYWORDS.get("GEOPOLITICAL", {}).get("positive", [])
    geo_neg = SECTOR_KEYWORDS.get("GEOPOLITICAL", {}).get("negative", [])

    all_pos = list(set(sector_pos + market_pos + macro_pos + geo_pos))
    all_neg = list(set(sector_neg + market_neg + macro_neg + geo_neg))
    return all_pos, all_neg


def score_relevance(symbol: str, article: NormalizedArticle, asset_resolution: AssetResolution) -> float:
    """Returns a `[0, 1]` relevance score blending sector/market keyword
    relevance with symbol-mention confidence."""
    all_pos, all_neg = _keyword_universe(symbol)
    sector_weight, _bias = _core_sector_relevance(article.text, all_pos, all_neg)

    normalized_sector_weight = max(0.0, min(1.0, (sector_weight - 0.5) / 1.0))
    return max(0.0, min(1.0, 0.5 * normalized_sector_weight + 0.5 * asset_resolution.confidence))
