# ML Model Accuracy Report — 2026-10-01

## Walk-forward evaluation (XGBoost models)

| Model | Samples | Accuracy | Majority baseline | Precision | Recall |
|---|---|---|---|---|---|
| xgb_signal_model | 1850 | 0.608 | 0.568 | 0.546 | 0.559 |
| v2_xgb_model | 0 | ERROR | - | - | Feature shape mismatch, expected: 5, got 7 |

`v2_xgb_model`'s feature-shape mismatch above is a known, pre-existing issue, tracked separately — it needs its own feature-schema realignment and retraining, which is out of scope for the decision-path-consolidation work.

## decision_engine current-state snapshot (NOT a backtest)

`decision_engine.decide()` has no point-in-time parameter, so this is today's live decision only, not a historical accuracy figure. A proper decision_engine backtest needs historical replay support - out of scope for this evaluation.

| Symbol | Decision | Confidence | Data sufficiency |
|---|---|---|---|
| THYAO.IS | HOLD | 0.87 | 1.00 |
| GARAN.IS | BUY | 0.73 | 1.00 |
| ASELS.IS | BUY | 0.73 | 1.00 |
| EREGL.IS | BUY | 0.81 | 1.00 |
| AKBNK.IS | HOLD | 0.62 | 1.00 |
| BTC-USD | HOLD | 1.00 | 1.00 |
| ETH-USD | BUY | 0.71 | 1.00 |
| SOL-USD | BUY | 0.67 | 1.00 |
