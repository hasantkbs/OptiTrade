"""
OptiTrade News Engine — asset resolver.

Every article already arrives pre-scoped to `symbol` (fetched via that
symbol's own provider feed - see `providers.py`), so resolution here is
a confidence signal rather than a hard filter: articles that actually
mention the bare ticker (or its cashtag form) in their text are strongly
confirmed; articles from the symbol's own feed that don't mention it by
name are still treated as relevant (the provider already scoped them)
but with a lower confidence, since they may be broader
sector/market-wide coverage merely attributed to this symbol's news
page.
"""
from __future__ import annotations

from engines.news.models import AssetResolution, NormalizedArticle

_MENTIONED_CONFIDENCE = 1.0
_UNMENTIONED_CONFIDENCE = 0.7


def _bare_symbol(symbol: str) -> str:
    return symbol.split(".")[0].upper()


def resolve(symbol: str, article: NormalizedArticle) -> AssetResolution:
    bare = _bare_symbol(symbol)
    text_upper = article.text.upper()
    mentioned = bare in text_upper or f"${bare}" in text_upper
    confidence = _MENTIONED_CONFIDENCE if mentioned else _UNMENTIONED_CONFIDENCE
    return AssetResolution(symbol=symbol, is_relevant=True, confidence=confidence)
