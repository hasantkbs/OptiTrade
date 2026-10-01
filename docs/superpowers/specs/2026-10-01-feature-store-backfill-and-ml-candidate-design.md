# Feature Store Backfill & ML Candidate Training — Design Spec

**Status:** Approved by user, ready for implementation planning.

**Relationship to other work:** This follows directly from PR #3
(`worktree-ml-oos-retrain`, stacked on PR #2's decision-path
consolidation), which found via genuine out-of-sample evaluation that
the legacy `xgb_signal_model.joblib` does not beat its majority-class
baseline (0.568 accuracy vs 0.580 baseline) — and, separately, that this
model has zero influence on `decision_engine`'s actual BUY/SELL/HOLD
decisions anyway (it only feeds `AnalysisResult.ml_confidence`, a
secondary display field). This spec targets the thing that actually
matters for decision quality: training a real candidate model through
the more capable `ml_training` package (multi-algorithm, calibration,
registry, promotion lifecycle — all already built, never yet exercised
end-to-end with real data) and getting it to the `CANDIDATE` stage with
genuine out-of-sample validation.

**Explicitly deferred (separate, later, human-approved decisions):**
deploying the candidate to `SHADOW` (live-but-observe-only voting,
already-built mechanism in `ml_training/shadow/service.py`), and any
later promotion to `ACTIVE` (which the existing code already hard-requires
a human `approved_by` for — see `ml_training/registry/service.py`). This
spec stops at producing a validated `CANDIDATE`.

## Mission

Train a real, validated candidate model via `ml_training.service`'s
already-built (but never yet exercised with real data) training/
evaluation pipeline, so there is an honest answer to "is a model-based
vote worth adding to `decision_engine` at all" — building on the
same out-of-sample discipline PR #3 established, now using the more
capable training infrastructure instead of the legacy script.

## Current State (what was found during brainstorming)

- `ml_training/` has a fully-built model lifecycle already: train →
  register as `CANDIDATE` → promote to `SHADOW` (observe-only, never
  affects live decisions) → accumulate real shadow-vs-production
  accuracy via `learning`'s Continuous Learning cycle → promote to
  `ACTIVE` (requires human `approved_by`, archives whatever was
  previously `ACTIVE` for that label/horizon). This is extensively
  unit-tested but has **no CLI/script entry point anywhere** — nothing
  under `scripts/` or `research/` has ever called
  `ml_training.service`'s `run_training_job`. It has never been run
  end-to-end against real data.
- `ml_training.datasets.builder.DatasetBuilder.build()` sources every
  training sample via `ml_training.features.extractor.FeatureExtractor
  .extract(symbol, cursor, respect_ingestion_time=True)` — a genuine
  point-in-time Feature Store read, not a raw-OHLCV computation like
  `research/ml_trainer.py` does. `respect_ingestion_time=True` additionally
  excludes any record whose `ingestion_timestamp` is after the query's
  `as_of` — the system's own guard against a naively-backfilled row
  leaking future information into a historical training sample.
- **The Feature Store does not have enough history for this to work
  today.** Queried directly: `feature_store_records` has data from
  **2026-07-29 to present only** (~2 months, 62 symbols, 20,453 rows) —
  far short of the 1-2 years `ml_training`'s point-in-time dataset
  builder needs for a meaningful training set. This was not apparent
  until queried directly; it is the reason this spec includes a backfill
  phase rather than going straight to training.
- The Feature Store's schema already, correctly supports backfilling:
  `FeatureRecord`/`offline_store.insert()` take a caller-supplied
  `ingestion_timestamp`, not a server-forced "now" — so a backfill can
  honestly write historical rows with both `event_timestamp` and
  `ingestion_timestamp` set to the historical date, which
  `respect_ingestion_time=True` queries will then correctly treat as
  genuinely-known-as-of that day. This is not a workaround; it's exactly
  what the schema was designed to support.
- `engines/technical/feature_adapter.py::_compute_all(symbol)` — the
  function the LIVE Technical engine already uses to compute all 17 of
  `ALL_FEATURE_NAMES` (RSI, MACD line/signal/histogram, ROC, Bollinger
  %B/bandwidth, ATR/ATR%, volume ratio, VWAP diff, support/resistance
  proximity, bullish/bearish pattern counts, trend strength, EMA
  crossover encoding) — is a pure function of one `fetch_history(...)`
  call's OHLCV DataFrame plus a `PatternScanner` pass. Its ONLY
  live-coupling is that single fetch call; the computation itself has no
  other dependency on "now". This means the backfill can reuse the
  EXACT SAME feature computation the live engine uses (refactored to
  accept a given historical OHLCV window instead of always fetching the
  live-period one), guaranteeing the backfilled historical features and
  whatever the live engine computes going forward are bit-for-bit
  consistent in method — critical, since a model trained on one
  definition of "RSI" must see the identical definition at live-vote
  time later.
- `ml_training/features/extractor.py` auto-discovers feature names per
  symbol via `FeatureStoreService.list_feature_names` — it has no
  hardcoded feature list. Whatever feature names the backfill writes are
  automatically what `ml_training` trains and infers on; no separate
  "register this feature name" step exists or is needed.

## Architecture

**Three sequential pieces, each independently runnable and verifiable:**

```
1. Feature Store backfill (new script)
      ↓ (writes historical point-in-time FeatureRecords)
2. ml_training training run (new script, calls existing
   ml_training.service.run_training_job)
      ↓ (produces a registered CANDIDATE model + its own CV metrics)
3. Out-of-sample evaluation (new script, calls existing
   ml_training.evaluation.ModelEvaluator against held-out dates)
      ↓
   Honest report: does this candidate actually beat baseline
   out-of-sample? (Answer may be "no" — that's a legitimate result,
   not a failure, per PR #3's own precedent.)
```

### 1. Feature Store backfill

**New file:** `backend/src/scripts/backfill_feature_store.py`

For each symbol in `SYMBOL_BASKET` (same 22-symbol BIST+crypto basket
`research/ml_trainer.py` already uses — reused verbatim, not
reinvented), fetches the full historical OHLCV range once (one network
call per symbol, not one per day), then for each trading day in
`[BACKFILL_START, BACKFILL_END]` computes the same 17
`ALL_FEATURE_NAMES` features from the OHLCV window ending at that day
(reusing `engines/technical/feature_adapter.py`'s computation — see
"Refactor" below) and writes one `FeatureRecord` per (symbol, feature,
day) via `PostgresOfflineStore.insert()`, with `event_timestamp =
ingestion_timestamp = that day's close` (both backdated — an honest
backfill, not data invented at "now").

**Idempotent/resumable:** before computing a (symbol, day) pair, checks
whether `feature_store_records` already has a row for
`(symbol, any_of_ALL_FEATURE_NAMES, that_day)` and skips it if so — a
killed/restarted run never duplicates work or data.

**Refactor (small, DRY):** `engines/technical/feature_adapter.py
::_compute_all` currently does `fetch_history(...)` AND the 17-feature
computation AND the live Feature Store writes in one method. This spec
extracts the middle part into a new pure function,
`compute_technical_features(hist: pd.DataFrame, config: TechnicalEngineConfig)
-> Dict[str, float]`, callable with ANY historical OHLCV DataFrame, not
just a freshly-fetched live one. `_compute_all` becomes a thin wrapper:
fetch, call the pure function, write results — zero behavior change for
the live engine (same inputs produce the same outputs), confirmed by
the existing Technical engine test suite passing unchanged. The backfill
script imports and calls `compute_technical_features` directly.

### 2. Training run

**New file:** `backend/src/scripts/train_ml_candidate.py`

Calls `ml_training.service.MLTrainingService.run_training_job(
author=..., symbols=SYMBOL_BASKET, dataset_type=DatasetType.TRADER,
label_name=LabelName.DIRECTION, horizon_days=5,
algorithm=ModelAlgorithm.XGBOOST, start=BACKFILL_START, end=TRAIN_END_DATE)`
— `horizon_days=5` and the label's `direction_band_pct=1.0%` default
match `research/ml_trainer.py`'s own `FORWARD_DAYS=5`/`THRESHOLD_UP=1.0%`
exactly, so this candidate is a fair, apples-to-apples comparison against
PR #3's `xgb_signal_model_oos_test` result. `TRAIN_END_DATE` is the same
"6 months before now" convention PR #3 used (dynamically computed, printed
explicitly, not silently assumed). Produces a registered `CANDIDATE`
model (via `ml_training`'s own registry — no new registry code needed,
it already exists and is tested) plus `run_training_job`'s own in-training
CV metrics.

### 3. Out-of-sample evaluation

Same script or a short follow-up step: loads the registered candidate,
builds a held-out dataset via `ml_training.datasets.builder.DatasetBuilder
.build(SYMBOL_BASKET, DatasetType.TRADER, start=TRAIN_END_DATE,
end=BACKFILL_END, horizons_days=[5])` (strictly AFTER the training
cutoff — the same no-overlap discipline as PR #3, just expressed via
`ml_training`'s own dataset builder instead of hand-rolled date
filtering), then scores it with `ml_training.evaluation.ModelEvaluator
.evaluate(...)` (already-built: classification metrics, calibration
error, trading-performance metrics when `actual_returns` is available).
Reports accuracy/precision/recall/calibration-error against a majority-
class baseline, honestly — including if the result is unfavorable,
exactly as PR #3's report did for the legacy model.

## Data Flow

```
SYMBOL_BASKET (22 symbols) ─┐
                            ▼
              backfill_feature_store.py
     (fetch once per symbol, compute 17 features/day,
      write historical FeatureRecords, idempotent)
                            │
                            ▼
                 feature_store_records
          (now has ~2y of point-in-time history)
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
   run_training_job(...,              DatasetBuilder.build(...,
   start=BACKFILL_START,              start=TRAIN_END_DATE,
   end=TRAIN_END_DATE)                end=BACKFILL_END)
              │                           │
              ▼                           │
      CANDIDATE model                     │
      (registered, has                    │
       its own CV metrics)                │
              │                           │
              └──────────┬────────────────┘
                         ▼
              ModelEvaluator.evaluate(...)
                         │
                         ▼
          Honest out-of-sample report
     (accuracy/precision/recall/calibration
      vs majority baseline - may be unfavorable)
```

## Global Constraints

- **No SHADOW deployment, no ACTIVE promotion in this work.** The
  candidate stays at `CANDIDATE` state. `ml_training/shadow/service.py
  ::deploy_shadow()` and `ml_training/registry/service.py`'s promotion
  methods are never called by anything built here.
- **Backfilled rows must have both `event_timestamp` and
  `ingestion_timestamp` set to the historical date**, never to "now" —
  this is the specific property that makes `respect_ingestion_time=True`
  training queries correct rather than silently leaking future
  information.
- **The backfill must reuse `engines/technical/feature_adapter.py`'s
  exact feature computation** (via the `compute_technical_features`
  extraction), not a reimplementation — so backfilled history and
  future live-computed features are guaranteed consistent.
- **Idempotent/resumable backfill** — a killed/restarted run must not
  duplicate data or redo already-completed work.
- `horizon_days=5` / `direction_band_pct=1.0%` (the label's default) to
  match PR #3's `xgb_signal_model_oos_test` exactly, for a fair
  comparison.
- Report results honestly, including an unfavorable outcome — this is
  the same commitment PR #3 made and kept.
- Every commit ends with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## Explicitly Out of Scope

- `SHADOW` deployment and `ACTIVE` promotion (separate, later,
  human-approved steps — the lifecycle code for both already exists and
  is untouched by this work).
- Fundamental/News engine feature backfill — only the Technical engine's
  17 features are backfilled; `ml_training`'s feature-name
  auto-discovery means Fundamental/News features could be added later
  by a separate backfill without touching this work.
- Hyperparameter optimization (`run_training_job`'s own
  `optimize_hyperparameters`/`n_trials` Optuna path exists but isn't
  used here — a single, fixed-hyperparameter XGBoost run first,
  consistent with keeping this comparable to PR #3's legacy baseline).
- Retraining/improving the legacy `xgb_signal_model.joblib` itself
  (explicitly declined by the user in favor of this path).
- The pre-existing `v2_xgb_model` unscoreable-schema issue — unrelated,
  untouched.

## Risks

- **Backfill volume/time.** ~22 symbols × ~500-700 trading days × 17
  features ≈ 100,000-190,000 row inserts. At a plain per-row `insert()`
  call (no batch-insert API currently exists on
  `PostgresOfflineStore`), this is a one-time job estimated at roughly
  10-30 minutes on local Postgres — acceptable for a one-time backfill,
  but should be run with visible progress output and the implementer
  should flag early if it's taking meaningfully longer than this
  estimate, rather than silently waiting.
- **The candidate may not beat baseline either.** PR #3 already
  demonstrated the legacy model doesn't; the newer training
  infrastructure uses the same underlying technical-indicator feature
  family (just a cleaner pipeline + more engine-consistent features via
  `ALL_FEATURE_NAMES`, which has a few more indicators than the legacy
  script's 7), so a similarly unfavorable result is a real possibility,
  not a sign of a bug if it happens. This must be reported honestly per
  the Global Constraints, not tuned-until-favorable.
- **`respect_ingestion_time=True`'s correctness depends entirely on the
  backfill setting `ingestion_timestamp` honestly.** A bug that leaves
  `ingestion_timestamp` at its Pydantic/dataclass default (likely "now")
  would silently defeat the entire point-in-time safety guarantee this
  spec exists to uphold the data builder's part of, while looking
  identical in row counts. The implementation plan should include an
  explicit verification step (e.g., query a backfilled row and assert
  its `ingestion_timestamp` equals the intended historical date, not
  today) before trusting any training run built on top of it.
