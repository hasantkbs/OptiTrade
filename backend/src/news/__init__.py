"""
OptiTrade — News Intelligence Pipeline
=========================================
Staged pipeline that turns raw provider news into enriched, structured
items ready for signals.news.NewsSignalEngine.

    Provider -> Normalizer -> Deduplicator -> Entity Extraction
        -> Asset Resolver -> Relevance -> Impact -> Event Classification
        -> Sentiment -> NewsSignalEngine (signals/news.py)

Each stage is a small, independently testable class operating on
news.models.NewsItemContext.  Entity Extraction is defined behind a
Protocol (news.entity_extraction.EntityExtractor) so the deterministic
keyword implementation can be replaced by an NLP/LLM-backed one later
without changing any caller.

This package is entirely separate from core.news_analyzer, which remains
the source of the existing iOS-facing `news_analysis` response and is
never modified by this pipeline.
"""
