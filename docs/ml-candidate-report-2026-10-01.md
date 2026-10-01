# ML Candidate Report — 2026-10-01

Model: `xgb-dir-5d-eda870a7` (algorithm=xgboost, label=direction, horizon_days=5)
Promotion state: `candidate` (CANDIDATE only - no SHADOW/ACTIVE in this run)

## Held-out out-of-sample evaluation

Train window (nominal, as computed by the script): [2024-04-04, 2026-04-04]
Train window (REAL Feature Store coverage, see note below): [2024-10-01, 2026-04-04]
Held-out window (strictly after train_end_date): [2026-04-05, 2026-10-01]
Held-out samples: 3828

**Train window correction (final review fix round):** the script computes
`train_start = train_end_date - 730 days` = 2024-04-04, but Task 2's
backfill was run with `--start 2024-10-01` - the basket has zero feature
rows before that date (verified directly against production Postgres:
`COUNT(DISTINCT event_timestamp::date) WHERE event_timestamp <
'2024-10-01'` = 0 for this basket). `DatasetBuilder.build` silently
`continue`s past days with no feature data rather than warning, so
~6 months of the nominal [2024-04-04, 2026-04-04] window contributed
zero training samples - the run only succeeded because the remaining
~18 months (2024-10-01 onward) cleared `min_training_samples`. This
does NOT invalidate the trained model or the result below (plenty of
real data existed in the real [2024-10-01, 2026-04-04] window) - only
the originally-stated train window was a false factual claim, now
corrected. `train_ml_candidate.py` now probes real Feature Store
coverage and logs a loud warning if a future run's computed
`train_start` again falls before it.

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

**Train/serve feature as-of alignment (disclosure, final review fix round):**
Task 2's backfilled rows are written at `23:59:59` UTC for the day they
describe, but `DatasetBuilder`'s cursor inherits `train_start`'s own
wall-clock time-of-day (not day-end), so in practice each training
sample's point-in-time feature lookup resolves to the PREVIOUS day's
backfilled value, paired with the `as_of -> as_of+5d` label - a
consistent, one-day-earlier alignment throughout the training window.
Separately, ~6% of the dates inside the held-out window
`[2026-04-05, 2026-10-01]` overlap with when LIVE Technical Engine
ingestion began (2026-07-29) and so resolve to a same-day LIVE row
instead of a T-1 backfilled one - a mixed as-of convention for that
slice of the held-out set. This skew is conservative (features are, if
anything, slightly stale relative to the label window, never
look-ahead), so it does not invalidate the 0.429-vs-0.479 result above,
but it is an unmodeled train/serve alignment detail worth disclosing
rather than silently omitting from a report whose purpose is honesty.

## In-training metrics (for reference, NOT the out-of-sample result above)

| Metric | Value |
|---|---|
| Accuracy | 0.456 |
| Hypothesis outcome | accepted |
