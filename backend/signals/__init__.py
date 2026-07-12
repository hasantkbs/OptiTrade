"""
OptiTrade — Financial Intelligence Signal Layer
================================================
Transforms raw indicator values and scoring contributions into structured,
explainable Signal objects.

Implemented:
  TechnicalSignalEngine    — reads contributions from compute_score() and
                             enriches them into Signal objects. Zero
                             recomputation — core.scoring remains the
                             single source of truth for numeric values.
  FundamentalSignalEngine  — EPS, P/E, book value, earnings trend
  NewsSignalEngine (news.py) — consumes news.pipeline.NewsPipeline output
                             (see backend/news/ for the staged pipeline:
                             Provider -> Normalizer -> Deduplicator ->
                             Entity Extraction -> Asset Resolver ->
                             Relevance -> Impact -> Event Classification ->
                             Sentiment)

Future phases:
  VolumeSignalEngine       — volume profile, OBV divergence, VWAP bands
  MarketStructureEngine    — support/resistance, patterns, Fibonacci
  MacroSignalEngine        — session context, sector rotation, macro indicators
  DecisionEngine           — buy/sell/hold probabilities, risk, horizon
"""
