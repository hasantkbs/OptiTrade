# ML Candidate Report — 2026-10-01

Model: `xgb-dir-5d-eda870a7` (algorithm=xgboost, label=direction, horizon_days=5)
Promotion state: `candidate` (CANDIDATE only - no SHADOW/ACTIVE in this run)

## Held-out out-of-sample evaluation

Train window: [2024-04-04, 2026-04-04]
Held-out window (strictly after train_end_date): [2026-04-05, 2026-10-01]
Held-out samples: 3828

| Metric | Value |
|---|---|
| Accuracy | 0.429 |
| Majority baseline | 0.479 |
| Precision | 0.380 |
| Recall | 0.333 |

**Fix note (2026-10-01, fix round 1):** the original run's held-out
build started at `train_end_date` itself; because `DatasetBuilder
.build`'s cursor loop is inclusive on both ends, that re-included
`train_end_date`'s own calendar day (all 22 symbols) in BOTH the
training set and the "held-out" set - a real, not cosmetic, overlap.
The held-out build was corrected to start at `train_end_date + 1 day`
and re-run against the already-trained model artifact (no retraining).
Numbers above are the corrected, genuinely out-of-sample result (3,828
samples, 22 fewer than the original 3,850 - exactly the one overlapping
day removed). The original (overlapping) numbers were accuracy=0.430,
majority_baseline=0.476, precision=0.380, recall=0.333 on 3,850 samples
- the correction changes the result negligibly, as expected, but the
numbers above are the ones that are actually correct.

## In-training metrics (for reference, NOT the out-of-sample result above)

| Metric | Value |
|---|---|
| Accuracy | 0.456 |
| Hypothesis outcome | accepted |
