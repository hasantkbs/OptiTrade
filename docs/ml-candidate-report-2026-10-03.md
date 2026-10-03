# ML Candidate Report — 2026-10-03

Retraining against Task 6's corrected, real production Feature Store backfill
(221,188 rows, UTC-explicit, crypto routed through Binance). This supersedes
`docs/ml-candidate-report-2026-10-01.md`, which was produced against the
wrong database and the pre-fix crypto logic and remains a historical
record of that incident — it is not overwritten by this file.

## Summary of all attempts (bounded fine-tuning, per plan's Global Constraints)

Success bar: beat the naive majority-class out-of-sample baseline. None of
the three bounded attempts below cleared it; per the plan this is the
honest, final result and no further retraining was performed.

| # | Algorithm | direction_band_pct | model_id | OOS accuracy | Majority baseline | Beat baseline? |
|---|---|---|---|---|---|---|
| 1 (unmodified script) | xgboost | 1.0 (default) | `xgb-dir-5d-33276640` | 0.431 | 0.484 | No |
| 2 | random_forest | 1.0 (default) | `rf-dir-5d-2dd83fb3` | 0.434 | 0.484 | No |
| 3 | random_forest | 0.5 (narrowed) | `rf-dir-5d-983f2be9` | 0.458 | 0.514 | No |

All three models were registered as real `CANDIDATE` rows in
`ml_training_model_registry` (verified directly against the database, not
just the script's own print output) — none were promoted to SHADOW or
ACTIVE. Attempts 2 and 3's algorithm/config edits to
`train_ml_candidate.py` were reverted after each run; the committed script
differs from its pre-task state only by the one-line output-path date fix.
Both XGBoost and RandomForest scored an OOS `roc_auc` near 0.50 (see the
registry's `metrics` column), indicating neither model is extracting
real directional signal from this feature set over this window — the
gap below baseline looks like a genuine data/label-difficulty result,
not an algorithm-choice problem, so a hyperparameter search would not be
expected to close it (and was out of scope per the Global Constraints).

The out-of-sample detail below is the unmodified script's own report
output for the final (3rd) attempt.

---

Model: `rf-dir-5d-983f2be9` (algorithm=random_forest, label=direction, horizon_days=5)
Promotion state: `candidate` (CANDIDATE only - no SHADOW/ACTIVE in this run)

## Held-out out-of-sample evaluation

Train window: [2024-04-06, 2026-04-06]
Held-out window (strictly after train_end_date): [2026-04-07, 2026-10-03]
Held-out samples: 3813

| Metric | Value |
|---|---|
| Accuracy | 0.458 |
| Majority baseline | 0.514 |
| Precision | 0.316 |
| Recall | 0.336 |

## In-training metrics (for reference, NOT the out-of-sample result above)

| Metric | Value |
|---|---|
| Accuracy | 0.493 |
| Hypothesis outcome | accepted |
