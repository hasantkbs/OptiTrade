# ML Candidate Report — 2026-10-01

Model: `xgb-dir-5d-eda870a7` (algorithm=xgboost, label=direction, horizon_days=5)
Promotion state: `candidate` (CANDIDATE only - no SHADOW/ACTIVE in this run)

## Held-out out-of-sample evaluation

Train window: [2024-04-04, 2026-04-04]
Held-out window (strictly after train_end_date): (2026-04-04, 2026-10-01]
Held-out samples: 3850

| Metric | Value |
|---|---|
| Accuracy | 0.430 |
| Majority baseline | 0.476 |
| Precision | 0.380 |
| Recall | 0.333 |

## In-training metrics (for reference, NOT the out-of-sample result above)

| Metric | Value |
|---|---|
| Accuracy | 0.456 |
| Hypothesis outcome | accepted |
