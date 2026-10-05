# ML Candidate Report — 2026-10-03 (derived features attempt)

Retraining against the same 2-year backfilled Feature Store, train window,
held-out window, label (direction, horizon_days=5, 1.0% band), and 22-symbol
basket as `docs/ml-candidate-report-2026-10-03.md`'s 1st attempt (xgboost,
default 1.0% band, baseline 0.484) — NOT the 3rd/final attempt kept in that
report's detail section, which used random_forest with a narrowed 0.5% band
and is therefore not a like-for-like comparison. The ONLY change from the
1st attempt is 32 new engineered features (lag/rolling, weekly
multi-timeframe, cross-sectional rank, volatility regime; see
`docs/superpowers/specs/2026-10-03-ml-accuracy-derived-features-design.md`)
added alongside the original 17, per this sub-project's own Global
Constraint of holding model scope and label definition fixed to isolate
the effect of the feature set alone. `docs/ml-candidate-report-2026-10-03
.md` is NOT overwritten and remains the historical record of all three
pre-derived-features attempts.

This run's roc_auc was 0.495 — in-training, near chance level. That is
consistent with "no signal found" rather than an overfitting artifact:
in-training accuracy (0.447) and out-of-sample accuracy (0.424) are
close together, not a large in-training/OOS gap that would suggest the
model memorized noise in the larger 49-feature space.

Numeric comparison to the 1st attempt: 0.431 accuracy vs 0.484 majority
baseline (1st attempt, 17 features) versus 0.424 accuracy vs 0.486
majority baseline (this run, 49 features) — i.e. still below baseline,
and not meaningfully different from the 1st attempt's own shortfall.

One honest caveat: the held-out sample count here (3798) is not
byte-identical to the 1st attempt's own held-out sample count (not
restated in that report's summary table, but implied by its slightly
different majority baseline, 0.484 vs this run's 0.486). This is most
likely because `train_ml_candidate.py` computes its train/held-out
window from `datetime.now()` at run time, and this run executed on a
different real date than the original attempt — so the two runs' underlying
samples are not byte-identical, only configuration-identical (same
algorithm, same label, same horizon, same band, same symbol basket).

# ML Candidate Report — 2026-10-03

Model: `xgb-dir-5d-69bd84a0` (algorithm=xgboost, label=direction, horizon_days=5)
Promotion state: `candidate` (CANDIDATE only - no SHADOW/ACTIVE in this run)

## Held-out out-of-sample evaluation

Train window: [2024-04-06, 2026-04-06]
Held-out window (strictly after train_end_date): [2026-04-07, 2026-10-03]
Held-out samples: 3798

| Metric | Value |
|---|---|
| Accuracy | 0.424 |
| Majority baseline | 0.486 |
| Precision | 0.297 |
| Recall | 0.333 |

## In-training metrics (for reference, NOT the out-of-sample result above)

| Metric | Value |
|---|---|
| Accuracy | 0.447 |
| Hypothesis outcome | accepted |
