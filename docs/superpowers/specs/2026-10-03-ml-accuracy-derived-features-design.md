# ML Candidate Accuracy — Derived Feature Engineering — Design

## Mission

Try to make an ML candidate model beat its naive majority-class out-of-sample
baseline, as the first attempt of the "model-based development, focus on
accuracy" initiative's second sub-project (the first, `decision_engine`'s own
Technical-only point-in-time backtest, is complete: 0.492 accuracy vs 0.588
baseline — does not beat it either, see
`docs/decision-engine-backtest-report-2026-10-03.md`).

## Current State

Three prior bounded CANDIDATE training attempts (`docs/ml-candidate-report-
2026-10-03.md`) all trained **one global model across all 22 symbols** (15
BIST equities + 7 crypto), using only the **17 raw Technical-engine feature
values** (`engines/technical/config.py::ALL_FEATURE_NAMES`) as features, for
a **direction label at a 5-day horizon with a 1.0% band**
(`ml_training.labels.generator`, `MLTrainingConfig.direction_band_pct`).
Both XGBoost and RandomForest scored OOS `roc_auc` ≈ 0.50 (chance level) —
the report's own conclusion was that this is a genuine data/feature/task-
difficulty result, not an algorithm-choice problem, so a hyperparameter
search would not be expected to close the gap.

The success bar (stated earlier this session): beat the naive majority-class
baseline. Not state-of-the-art performance.

## Scope

Add richer **engineered features**, computed from data that already exists
(the 2-year backfilled Feature Store + cached OHLCV), then retrain and
re-evaluate with everything else held fixed — same global model across all
22 symbols, same direction/5-day/1.0%-band label — to isolate whether a
richer feature set alone can beat baseline. Changing the model scope
(per-symbol/per-asset-class) or the label/task definition are explicitly
deferred to a later attempt if this one doesn't clear the bar.

## Architecture

**Everything is computed entirely inside `ml_training`, at dataset-build
time only. Zero changes to the live `TechnicalEngine`, Feature Store schema,
or `decision_engine`.** This keeps the blast radius contained to the
training/evaluation pipeline and matches this initiative's established
sequencing: measure/attempt first, act on findings (e.g. promoting a feature
into the live engine) is a separate, later, human-approved decision.

1. **New `ml_training/features/derived.py`** — pure, stateless functions,
   one per category, each taking already-fetched data (never fetching
   itself):
   - `lag_rolling_features(history: Dict[str, List[FeatureRecord]], as_of: datetime) -> Dict[str, float]`
   - `multi_timeframe_features(ohlcv: pd.DataFrame, as_of: datetime) -> Dict[str, float]`
   - `cross_sectional_features(symbol_value: Optional[float], basket_values: List[float], feature_name: str) -> Dict[str, float]`
   - `volatility_regime_features(history: Dict[str, List[FeatureRecord]], as_of: datetime) -> Dict[str, float]`
2. **New `ml_training/features/derived_builder.py::DerivedFeatureBuilder`** —
   owns a `FeatureStoreService` and a `PriceFetcher` (same protocol
   `ml_training.labels.generator.PriceFetcher` already defines), and one
   method `compute(symbol: str, as_of: datetime, day_snapshot: Dict[str, Dict[str, float]]) -> Dict[str, float]`
   (`day_snapshot` maps `symbol -> {feature_name: value}` for every symbol
   in the basket on that calendar day — supplied by the caller, not fetched
   by the builder, so cross-sectional ranking needs no extra Feature Store
   round-trips). Orchestrates the 4 pure functions and merges their output
   into one dict. Every returned key is prefixed `derived_` so it can never
   collide with the 17 base feature names in the same flat dict.
3. **`ml_training/features/extractor.py::FeatureExtractor` is NOT modified.**
   Its own docstring's invariant ("never computes a single feature value
   itself") stays true — `DerivedFeatureBuilder` is a deliberately separate
   component that *does* compute, so this boundary stays honest.
4. **`ml_training/datasets/builder.py::DatasetBuilder.build()` is the only
   integration point touched.** Its per-day loop already visits every
   symbol in `symbols` for each `cursor` date. It is restructured to, per
   `cursor`: first call `self.feature_extractor.extract(symbol, cursor, respect_ingestion_time=True)`
   for every symbol in the basket (as it already does, just reordered to
   finish the whole day before moving to labels) to build that day's
   `day_snapshot`; then, per symbol, call
   `self.derived_feature_builder.compute(symbol, cursor, day_snapshot)` and
   merge the result into that symbol's `vector.values` before
   `generate_labels` is called and the `TrainingSample` is built. Nothing
   else in `DatasetBuilder` changes — the labels call, the horizon loop, and
   the `DatasetVersion` bookkeeping are untouched except that
   `feature_names_seen` now also picks up the new `derived_*` keys
   (already handled by the existing `feature_names_seen.update(vector.values.keys())`
   line, since derived keys are merged into the same `vector.values` dict
   before that line runs).

## Data Flow — exact features per category

Base features used for lag/rolling and volatility-regime are the 5 most
momentum/volatility-relevant of the 17 (not all 17, to keep dimensionality
sane relative to ~17K training rows): `rsi_14`, `macd_histogram`,
`volume_ratio`, `atr_pct`, `trend_strength_pct` (exact Feature Store names
from `engines/technical/config.py`).

### Lag / rolling-window (25 features: 5 base × 5)

Via `feature_store.get_feature_history(symbol, name, as_of - timedelta(days=10), as_of)`
(ascending list of `FeatureRecord`; a 10-calendar-day lookback comfortably
covers a 5-trading-day lag plus a 5-sample rolling window even across
weekends/holidays):

- `derived_lag1_<name>`, `derived_lag3_<name>`, `derived_lag5_<name>` — the
  value from the record whose `event_timestamp` is the Nth most recent
  entry strictly before `as_of` in the returned history (not calendar-day
  arithmetic — trading-day lag, consistent with how the Feature Store only
  ever has records on trading days).
- `derived_roll5_mean_<name>`, `derived_roll5_std_<name>` — mean/population
  std of the trailing 5 records up to and including `as_of`'s own value (if
  fewer than 5 records exist in the window, use however many are available,
  down to a floor of 3; below that, omit both).

### Multi-timeframe (2 features)

Resample the already-cached daily OHLCV (same `CachingPriceFetcher` pattern
`scripts/train_ml_candidate.py` already uses) to weekly closes
(`pandas.Series.resample("W").last()`) over the trailing 8 weeks ending at
`as_of`, then call the real production indicator functions
`core.indicators.calculate_rsi(weekly_closes, period=14)` and
`core.indicators.calculate_trend_strength(weekly_closes, period=20)` —
reusing the exact math `TechnicalFeatureAdapter._compute_all` already uses
for the daily versions, not a reimplementation:

- `derived_weekly_rsi_14`, `derived_weekly_trend_strength_pct`

If fewer than 4 weekly closes are available (insufficient OHLCV history this
early in the backfill window), omit both.

### Cross-sectional (3 features)

Using `day_snapshot` (every symbol's base-feature values already resolved
for this exact calendar day by `DatasetBuilder`'s restructured loop), for
`rsi_14`, `volume_ratio`, `trend_strength_pct`: this symbol's percentile
rank (0.0–1.0) among every symbol in `day_snapshot` that has a value for
that feature name on this day (`scipy.stats.rankdata` or equivalent,
normalized to `[0, 1]`):

- `derived_rank_rsi_14`, `derived_rank_volume_ratio`, `derived_rank_trend_strength_pct`

If fewer than 3 symbols (including this one) have a value for that feature
on this day, omit that feature's rank (a rank against 1–2 peers is not a
meaningful cross-sectional signal).

### Volatility regime (2 features)

From `atr_pct` and `bollinger_bandwidth_pct`'s own trailing 20-record
history (`get_feature_history(symbol, name, as_of - timedelta(days=30), as_of)`,
a 30-calendar-day window to comfortably cover 20 trading-day records): a
z-score of today's value vs. the trailing window's own mean/std (today's
value included in the window, consistent with the rolling-window
convention above):

- `derived_volregime_atr_pct`, `derived_volregime_bb_bandwidth_pct`

If fewer than 10 records are available, or the trailing std is 0 (a
division-by-zero guard, not expected in practice), omit both.

**Total: 32 new `derived_*` features alongside the 17 base ones (49 features
per sample).**

## Error Handling

Every category above already specifies its own floor below which it omits
its output rather than fabricating a value — the same "missing stays
missing, never fabricated" convention `FeatureExtractor`/`generate_labels`
already use throughout this project. Concretely:

- **Insufficient lookback history** (a symbol early in the 2-year backfill
  window, before enough trailing records exist): affected `derived_*` keys
  are omitted from that sample's feature dict. Training/evaluation code
  already tolerates partial feature dicts end-to-end
  (`ml_training.service._samples_to_arrays`'s `.get(name, 0.0)`), so no new
  downstream handling is needed.
- **Thin basket for cross-sectional ranking**: rank features omitted for
  that sample rather than computed against a degenerate 1–2-symbol basket.
- **OHLCV cache miss for multi-timeframe** (same failure mode
  `CachingPriceFetcher` already logs-and-skips for label generation):
  weekly features omitted for that sample; nothing else in the sample is
  affected.
- **Zero-std guard** for the volatility-regime z-score: omit rather than
  divide by zero.
- All failures are per-(symbol, day, feature-category) — one omission never
  aborts the whole dataset build, matching `backfill_feature_store.py`/
  `evaluate_model_accuracy.py`'s established per-item try/skip/log
  convention.

## Testing

- **Unit tests per pure function in `derived.py`**: small, hand-built
  `FeatureRecord` lists / OHLCV `DataFrame`s with known expected outputs —
  lag/rolling arithmetic, weekly-resample-then-indicator-call, percentile
  rank, z-score — plus one test per category's own omission floor (e.g.
  fewer than 3 history records → lag/rolling keys absent; fewer than 4
  weekly closes → multi-timeframe keys absent; fewer than 3 symbols in the
  basket → rank keys absent; zero std → volregime keys absent).
- **`DerivedFeatureBuilder` tests** with a fake `FeatureStoreService` and
  fake `price_fetcher`: confirms `compute()` merges exactly the expected
  `derived_*` keys for a healthy case, and cleanly omits them for each
  error-handling case above, never raising.
- **`DatasetBuilder.build()` regression test**: with `DerivedFeatureBuilder`
  wired in, existing base-feature behavior (the 17 base keys, the labels,
  the sample count, the `DatasetVersion` metadata) stays byte-for-byte
  identical to today — only new `derived_*` keys are added to
  `vector.values`, nothing already there is removed or altered. This is
  the single most important test in this plan, the same role the
  `decision_engine` backtest plan's own "zero behavior change for
  `as_of=None`" regression test played there.
- **One retrain-and-evaluate run**: XGBoost, same direction/5-day/1.0%-band
  label, same global 22-symbol basket, against the expanded 49-feature
  dataset — reported honestly against the majority baseline exactly like
  the prior 3 attempts in `docs/ml-candidate-report-2026-10-03.md`,
  whichever way the result goes. This is the actual test of this sub-
  project's hypothesis (richer features alone can beat baseline).

## Global Constraints

- Every commit ends with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Zero change to any existing caller's behavior for the 17 base features —
  the `DatasetBuilder.build()` regression test above is the concrete proof,
  not just an assertion.
- Zero changes to `TechnicalEngine`, `TechnicalFeatureAdapter`, the live
  Feature Store schema, or `decision_engine` — this sub-project is
  training-side only.
- No new backfill work — every input (base Feature Store history, cached
  OHLCV) already exists from prior work this session.
- Missing data stays missing (never fabricated/defaulted) at the
  per-(symbol, day, feature-category) granularity specified above.
- Reuse real production indicator math for multi-timeframe
  (`core.indicators.calculate_rsi`/`calculate_trend_strength`) — no
  reimplementation of RSI/trend-strength formulas.
- Model scope (one global model across all 22 symbols) and label
  definition (direction, 5-day horizon, 1.0% band) stay fixed, matching the
  prior 3 attempts, so the retrain result isolates the effect of the
  feature set alone.
- Report the real result honestly, whatever it is — beating or not beating
  baseline are both legitimate, reportable outcomes, consistent with every
  prior ML evaluation in this project.

## Out of Scope

- Changing model scope (per-symbol or per-asset-class models instead of one
  global model) — deferred to a later attempt if this one doesn't clear
  the baseline bar.
- Changing the label/task definition (horizon, band width, regression
  instead of classification) — same deferral.
- Hyperparameter search / trying additional algorithms — already shown in
  the prior attempts not to be the bottleneck (`roc_auc` ≈ 0.50 for both
  XGBoost and RandomForest).
- Promoting any derived feature into the live `TechnicalEngine`/Feature
  Store/`decision_engine` — a separate, later, human-approved decision if
  this attempt succeeds and the team wants the winning features live.
- Fundamental/News feature engineering — still infeasible to backfill
  historically with current data sources (established and out of scope in
  the prior `decision_engine` backtest spec).

## Risks

- **32 new features against ~17K rows raises the feature-to-sample ratio
  meaningfully (17 → 49 features)** — mitigated by this being exactly the
  kind of question the retrain-and-evaluate step answers empirically; if
  overfitting dominates, the OOS metrics will show it (OOS accuracy
  collapsing relative to in-training accuracy), and that's itself a
  reportable, honest finding.
- **Lag/rolling and volatility-regime features computed from history that
  does not filter `ingestion_timestamp`** (`get_feature_history` has no
  `respect_ingestion_time` parameter, unlike `get_feature_as_of`) — on the
  specific backfilled dataset used here this is a non-issue, matching the
  same already-documented finding in the `decision_engine` backtest report
  (the backfill script set `ingestion_timestamp == event_timestamp` for
  every row, so no additional filtering is actually needed on this
  dataset); this risk is disclosed here for completeness, not treated as
  blocking.
- **Cross-sectional ranking mixes two very different asset classes (BIST
  equities vs. crypto) into one basket-wide rank** — a symbol's RSI rank
  among 15 equities + 7 crypto may be less meaningful than a rank within
  its own asset class. Accepted for this attempt (model scope is held
  fixed at "one global model, one basket" per the Scope section); worth
  revisiting if a later attempt splits models by asset class.
