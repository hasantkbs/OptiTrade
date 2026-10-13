# ML Candidate Report — 2026-10-13 (expected_volatility)

Model: `xgb-evol-5d-c8e35694` (algorithm=xgboost, label=expected_volatility, horizon_days=5)
Promotion state: `candidate` (CANDIDATE only - no SHADOW/ACTIVE in this run)

## Held-out out-of-sample evaluation

Train window: [2024-04-16, 2026-04-16]
Held-out window (strictly after train_end_date): [2026-04-17, 2026-10-13]
Held-out samples: 3813 (naive baseline computable for 3813 - the rest lack enough trailing price history)

Naive baseline = trailing realized volatility over the same horizon, predicting the forward realized volatility (the standard persistence benchmark in volatility forecasting).

| Metric | Model | Naive baseline (persistence) | Constant-mean baseline |
|---|---|---|---|
| MAE | 19.213 | 25.105 | 18.758 |
| RMSE | 26.032 | 35.512 | 25.699 |
| R² | -0.026 | -0.909 | 0.000 (by definition) |
| Spearman rank correlation | 0.098 | 0.078 | 0.000 (by definition) |

Constant-mean baseline predicts the held-out period's own mean expected_volatility for every sample - not a deployable strategy (that mean isn't known in advance), but it is exactly what R²=0 represents, so a negative R² above means worse than this reference point, not "no baseline beaten at all".

**Beats naive (persistence) baseline (lower MAE AND lower RMSE): True**
**Beats constant-mean baseline (lower MAE AND lower RMSE): False**

## In-training metrics (for reference, NOT the out-of-sample result above)

| Metric | Value |
|---|---|
| MAE | 19.756 |
| RMSE | 28.236 |
| Hypothesis outcome | accepted |
