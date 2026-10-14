# ML Candidate Report — 2026-10-14 (US equities, Technical + SEC Fundamentals + News)

Model: `xgb-dir-5d-2bb97fd1` (algorithm=xgboost, label=direction, horizon_days=5)
Promotion state: `candidate` (CANDIDATE only - no SHADOW/ACTIVE in this run)
Basket: 28 US equities (AAPL, MSFT, NVDA, GOOGL, META, AMZN, TSLA, AMD, INTC, CRM, JPM, BAC, GS, MS, V, MA, JNJ, LLY, PFE, UNH, XOM, CVX, WMT, HD, MCD, CAT, BA, GE)

## Held-out out-of-sample evaluation

Train window: [2025-10-29, 2026-07-15] (sized to News' own real backfilled coverage - see module docstring)
Held-out window: [2026-07-16, 2026-10-14]
Held-out samples: 2352 (2352 with real News features, 2352 with real SEC Fundamental features)
Total features: 39 (17 Technical, 17 SEC Fundamental, 5 News)

| Metric | Value |
|---|---|
| Accuracy | 0.460 |
| Majority baseline | 0.445 |
| Precision | 0.339 |
| Recall | 0.354 |
| ROC AUC | 0.5370624361075291 |

## In-training metrics (for reference, NOT the out-of-sample result above)

| Metric | Value |
|---|---|
| Accuracy | 0.453 |
| Hypothesis outcome | accepted |

## News features used

- `news_article_count`
- `news_confidence_score`
- `news_impact_score`
- `news_relevance_score`
- `news_sentiment_score`
