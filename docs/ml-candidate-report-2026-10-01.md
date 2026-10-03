# ML Candidate Report — 2026-10-01

Model: `xgb-dir-5d-c5857b8f` (algorithm=xgboost, label=direction, horizon_days=5)
Promotion state: `candidate` (CANDIDATE only - no SHADOW/ACTIVE in this run)

**Model identity note:** this report's model_id changed from an earlier
run (`xgb-dir-5d-eda870a7`) to this one (`xgb-dir-5d-c5857b8f`) partway
through the final review's fix round. The original model's registry
metadata (its `ml_training_model_registry` row and linked
runs/calibration/benchmark/hypothesis/feature-importance rows) was
accidentally deleted by an unrelated, unscoped test-cleanup bug in
`test_ml_training_service.py`/`test_ml_training_datasets.py` while
running the full backend test suite during post-fix verification - not
a data-quality or methodology problem with the original training run.
The Feature Store backfill data and the original model's `.joblib`
artifact were unaffected, but since the registry row itself was gone,
a fresh, fully real retrain was performed to produce a new, properly
registered CANDIDATE - this report reflects that fresh run. The new
run's real numbers (below) are numerically identical to the
pre-incident corrected numbers (accuracy=0.429, majority_baseline=
0.479, precision=0.380, recall=0.333, 3,828 held-out samples), as
expected: same calendar day, same backfilled Feature Store data, same
historical OHLCV, same deterministic config.

## Held-out out-of-sample evaluation

Train window (nominal, as computed by the script): [2024-04-04, 2026-04-04]
Train window (REAL Feature Store coverage, see note below): [2024-10-01, 2026-04-04]
Held-out window (strictly after train_end_date): [2026-04-05, 2026-10-01]
Held-out samples: 3828

**Train window correction:** the script computes `train_start =
train_end_date - 730 days` = 2024-04-04, but Task 2's backfill was run
with `--start 2024-10-01` - the basket has zero feature rows before
that date (verified directly against production Postgres:
`COUNT(DISTINCT event_timestamp::date) WHERE event_timestamp <
'2024-10-01'` = 0 for this basket). `DatasetBuilder.build` silently
`continue`s past days with no feature data rather than warning, so
~6 months of the nominal [2024-04-04, 2026-04-04] window contributed
zero training samples - the run only succeeded because the remaining
~18 months (2024-10-01 onward) cleared `min_training_samples`. This
does NOT invalidate the trained model or the result below (plenty of
real data existed in the real [2024-10-01, 2026-04-04] window) - only
the nominally-computed train window overstates real coverage.
`train_ml_candidate.py` now probes real Feature Store coverage via
`_earliest_feature_date()` and logs a loud warning when this happens -
confirmed firing correctly on this very run: "Feature Store coverage
for this basket starts at 2024-10-01, AFTER this script's own computed
train_start 2024-04-04 [...]".

| Metric | Value |
|---|---|
| Accuracy | 0.429 |
| Majority baseline | 0.479 |
| Precision | 0.380 |
| Recall | 0.333 |

**Train/held-out overlap (historical note):** an earlier version of
this script built its held-out set starting at `train_end_date` itself;
because `DatasetBuilder.build`'s cursor loop is inclusive on both ends,
that re-included `train_end_date`'s own calendar day in BOTH the
training set and the "held-out" set. This was fixed (held-out now starts
at `train_end_date + 1 day`) before this run - the 3,828-sample held-out
window above is already the corrected, non-overlapping one.

**Train/serve feature as-of alignment (disclosure):** Task 2's
backfilled rows are written at `23:59:59` UTC for the day they describe,
but `DatasetBuilder`'s cursor inherits `train_start`'s own wall-clock
time-of-day (not day-end), so in practice each training sample's
point-in-time feature lookup resolves to the PREVIOUS day's backfilled
value, paired with the `as_of -> as_of+5d` label - a consistent,
one-day-earlier alignment throughout the training window. Separately,
~6% of the dates inside the held-out window `[2026-04-05, 2026-10-01]`
overlap with when LIVE Technical Engine ingestion began (2026-07-29) and
so resolve to a same-day LIVE row instead of a T-1 backfilled one - a
mixed as-of convention for that slice of the held-out set. This skew is
conservative (features are, if anything, slightly stale relative to the
label window, never look-ahead), so it does not invalidate the result
above, but it is an unmodeled train/serve alignment detail worth
disclosing rather than silently omitting from a report whose purpose is
honesty.

**Crypto data-source and coverage gaps (disclosure):** two further gaps in
the training data feeding this candidate, neither previously disclosed:

1. *Data-source skew.* `scripts/backfill_feature_store.py` fetches every
   symbol's OHLCV via a direct `yf.Ticker(symbol).history(...)` call. Live
   serving instead goes through `fetch_history()`
   (`engines/technical/feature_adapter.py`), which resolves to
   `HybridProvider` and routes any symbol ending `-USD` to Binance rather
   than yfinance. 7 of the basket's 22 symbols are crypto
   (BTC-USD, ETH-USD, BNB-USD, SOL-USD, AVAX-USD, XRP-USD, DOGE-USD), so
   ~32% of the basket's backfilled Feature Store rows were computed from a
   different OHLCV source (yfinance) than what the live Technical engine
   - and any future SHADOW/ACTIVE model - would see at vote time
   (Binance). The rows are indistinguishable by inspection once written.
   There is no live-serving risk today (this model is CANDIDATE only;
   nothing reads these rows for serving), but this skew MUST be resolved
   before any SHADOW/ACTIVE promotion decision for this candidate or a
   retrained successor.
2. *Missing crypto weekend history.* `trading_days_in_range` in the same
   script excludes Saturday/Sunday for every symbol - correct for BIST
   (`.IS`) equities, which don't trade on weekends, but wrong for 24/7
   crypto assets. Verified directly against production: BTC-USD's
   backfilled rows show 0 rows on both Saturday and Sunday, versus
   ~1,768-1,785 on each weekday - crypto is missing close to 2 of every 7
   days of available history (~28% of calendar days for those 7 symbols).
   This is a deliberate, tested design choice, not an accident, but it
   means (a) crypto contributes fewer training/eval samples than it
   could, and (b) a Monday crypto sample's point-in-time feature lookup
   resolves back to the PRECEDING FRIDAY's backfilled value - a
   3-calendar-day-stale feature - which compounds the as-of skew already
   disclosed above specifically for crypto symbols.

Neither issue affects today's result's validity as a CANDIDATE-stage
finding: the reported 0.429 vs 0.479 comparison used the same - if
imperfect - feature computation consistently for both the training set
and the held-out set. Both issues must be tracked and resolved, however,
before considering this candidate (or a retrained successor) for SHADOW
or ACTIVE.

## In-training metrics (for reference, NOT the out-of-sample result above)

| Metric | Value |
|---|---|
| Accuracy | 0.456 |
| Hypothesis outcome | accepted |
