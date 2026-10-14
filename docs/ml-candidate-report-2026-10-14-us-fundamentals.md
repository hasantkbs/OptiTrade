# ML Candidate Report — 2026-10-14 (US equities, Technical + SEC Fundamentals)

Model: `xgb-dir-5d-7eaeff78` (algorithm=xgboost, label=direction, horizon_days=5)
Promotion state: `candidate` (CANDIDATE only - no SHADOW/ACTIVE in this run)
Basket: 28 US equities (AAPL, MSFT, NVDA, GOOGL, META, AMZN, TSLA, AMD, INTC, CRM, JPM, BAC, GS, MS, V, MA, JNJ, LLY, PFE, UNH, XOM, CVX, WMT, HD, MCD, CAT, BA, GE)

## Held-out out-of-sample evaluation

Train window: [2024-04-17, 2026-04-17]
Held-out window (strictly after train_end_date): [2026-04-18, 2026-10-14]
Held-out samples: 4844 (4844 with at least one SEC fundamental feature present)
Total features: 34 (17 SEC fundamentals, 17 Technical)

| Metric | Value |
|---|---|
| Accuracy | 0.454 |
| Majority baseline | 0.459 |
| Precision | 0.301 |
| Recall | 0.339 |
| ROC AUC | 0.5112871789017126 |

## In-training metrics (for reference, NOT the out-of-sample result above)

| Metric | Value |
|---|---|
| Accuracy | 0.446 |
| Hypothesis outcome | accepted |

## SEC fundamental features used

- `sec_debt_to_equity_pct`
- `sec_eps_diluted`
- `sec_net_income`
- `sec_net_margin_pct`
- `sec_operating_cash_flow`
- `sec_operating_income`
- `sec_operating_margin_pct`
- `sec_pb_ratio`
- `sec_pe_ratio`
- `sec_revenue`
- `sec_revenue_growth_yoy_pct`
- `sec_roa_pct`
- `sec_roe_pct`
- `sec_shares_outstanding`
- `sec_stockholders_equity`
- `sec_total_assets`
- `sec_total_liabilities`
