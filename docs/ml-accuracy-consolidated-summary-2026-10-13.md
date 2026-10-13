# ML Accuracy — Consolidated Summary of All 5 Attempts (as of 2026-10-13)

## Verdict

Five independent attempts — one rule-based backtest and four trained
models, across two target types (direction, volatility), two
algorithms (XGBoost, RandomForest), and two feature-set sizes (17, 49
features) — have been run against the same 22-symbol basket (15 BIST
+ 7 crypto). **None produced a result that beats a reasonable baseline
cleanly enough to promote.** The pattern is consistent enough across
independent attempts that the most defensible reading is a ceiling in
the feature family itself (pure price/volume technicals, at a 5-day
horizon, on this basket), not an algorithm-choice or engineering-effort
problem. No Fundamental or News features have been tried yet — they
cannot currently be backfilled historically without a paid data vendor
— so that remains the one genuinely unexhausted direction.

No model from any of these attempts has been promoted beyond
`CANDIDATE`. The live decision_engine's production behavior is
unaffected by any of this work.

## The five attempts, side by side

| # | Date | What | Target | Algorithm(s) | Result vs. baseline | Verdict |
|---|------|------|--------|--------------|----------------------|---------|
| 1 | 2026-10-03 | Decision-engine backtest (not an ML model — the live Technical voting engine vs. ground truth) | direction (BUY/HOLD/SELL) | rule-based voting | 0.492 vs 0.588 | Inconclusive — 67% HOLD rate conflates genuine abstention with data-coverage gaps, never separated |
| 2 | 2026-10-01 | First ML candidate | direction, 5d horizon | XGBoost | 0.429 vs 0.479 | Invalid — real data bugs (crypto train/serve source mismatch, missing weekend crypto data) |
| 3 | 2026-10-03 | Corrected-backfill candidate, 3 bounded attempts | direction, 5d horizon | XGBoost, RandomForest (×2 bands) | best: 0.458 vs 0.514 | Clean negative — ROC-AUC ≈ 0.50 (chance) on every variant |
| 4 | 2026-10-03 | Derived-features candidate | direction, 5d horizon | XGBoost, 49 features | 0.424 vs 0.486 | Clean negative — feature engineering changed nothing; ROC-AUC 0.495 |
| 5 | 2026-10-13 | Volatility-regression candidate | expected_volatility (magnitude, not direction), 5d horizon | XGBoost regressor, 17 features | beats naive persistence (MAE 19.2 vs 25.1); **loses to constant-mean baseline** (MAE 19.2 vs 18.8, R²=-0.026) | Mixed/negative — weak positive rank correlation (0.098) is the only encouraging number |

## Detail per attempt

### 1. Decision-engine backtest — `docs/decision-engine-backtest-report-2026-10-03.md`

Point-in-time backtest of the live Technical voting engine (not an ML
model) across 12,859 samples. 8,602 (67%) came back HOLD and were
excluded from accuracy; on the remaining 4,257 directional calls:
**accuracy 0.492, majority baseline 0.588, precision 0.395, recall
0.438.** The report itself flags this as unresolved: the 67% HOLD rate
mixes "the engine genuinely saw no signal" with "no feature data was
available, defaulted to HOLD" — these look identical today, so the
below-baseline result cannot yet be cleanly attributed to weak signal
vs. a data-coverage artifact.

### 2. First ML candidate — `docs/ml-candidate-report-2026-10-01.md`

XGBoost, direction label, 5-day horizon, 22 symbols. **0.429 vs 0.479
baseline**, precision 0.380, recall 0.333 — but invalidated by two real
bugs discovered in review: the backfill fetched crypto prices via
yfinance while live serving routes crypto through Binance (a
train/serve source mismatch for 7 of 22 symbols), and the backfill
script excluded weekends for all symbols, wrong for 24/7 crypto markets
(~28% of crypto calendar days missing). Not a clean read on signal —
superseded by attempt 3's corrected backfill.

### 3. Corrected-backfill candidate, 3 bounded attempts — `docs/ml-candidate-report-2026-10-03.md`

Same setup, backfill bugs from attempt 2 fixed (221,188 rows, crypto
now correctly routed through Binance). Three attempts under a
"stop if baseline isn't beaten" rule:

| Attempt | Algorithm | Band | Accuracy | Baseline |
|---|---|---|---|---|
| 1 | XGBoost | 1.0% | 0.431 | 0.484 |
| 2 | RandomForest | 1.0% | 0.434 | 0.484 |
| 3 | RandomForest | 0.5% (narrower) | 0.458 | 0.514 |

**All three scored ROC-AUC ≈ 0.50 (chance level).** The report's own
conclusion: this is a data/label-difficulty result, not an
algorithm-choice problem — a hyperparameter search would not be
expected to close the gap, so none was attempted.

### 4. Derived-features candidate — `docs/ml-candidate-report-2026-10-03-derived-features.md`

Identical setup to attempt 3's first run (XGBoost, 1.0% band), with 32
engineered features added to the original 17 (lags, rolling stats,
cross-sectional rank, volatility regime — 49 total), isolating the
effect of feature engineering alone. **0.424 vs 0.486 baseline**,
precision 0.297, recall 0.333, held-out n=3,798. In-training accuracy
(0.447) stayed close to out-of-sample (0.424) — ruling out overfitting;
the extra features simply added no signal (ROC-AUC 0.495, essentially
unchanged from attempt 3's 17-feature result).

### 5. Volatility-regression candidate — `docs/ml-candidate-report-2026-10-13-volatility.md`

A different hypothesis, not a retry of the same one: pure technical
features might not predict *direction* but could still predict
*magnitude* of the forward move, since volatility clustering is a far
more robust market pattern than short-horizon direction. Reused the
`ml_training` package's already-existing `expected_volatility`
regression label (zero package changes needed — this label was wired
end-to-end but had simply never been used as a training target).

| Metric | Model | Naive persistence baseline | Constant-mean baseline |
|---|---|---|---|
| MAE | 19.213 | 25.105 | 18.758 |
| RMSE | 26.032 | 35.512 | 25.699 |
| R² | -0.026 | -0.909 | 0.000 (by definition) |
| Spearman correlation | 0.098 | 0.078 | 0.000 (by definition) |

The model clearly beats "yesterday's volatility predicts tomorrow's"
— but that baseline turned out to be unusually bad for this basket.
Against the strictest baseline (just predicting the held-out period's
own average volatility), **the model loses.** The one number worth
tracking: Spearman rank correlation is weakly positive and higher than
the naive baseline's — a faint hint of relative-ranking ability even
with no real point-prediction skill. Not a promotion candidate.

## Common thread across attempts 2-5

Two algorithms (XGBoost, RandomForest), two target types (direction
classification, volatility regression), two feature-set sizes (17, 49
features), and multiple move-thresholds all converge on the same
place: **no reliable out-of-sample edge beyond trivial baselines**, on
this 22-symbol basket, at a 5-day horizon, from pure price/volume
technical indicators. Attempt 1 (the rule-based backtest) is a
different kind of result — its below-baseline score is still
confounded by the unresolved HOLD-rate ambiguity — but is at minimum
consistent with the same conclusion, not contradicting it.

## What hasn't been tried

- **Fundamental and News features** — blocked, not attempted: neither
  can currently be backfilled with genuine historical point-in-time
  data on the data sources this project has access to without a paid
  vendor. This is the one direction every attempt so far has been
  structurally unable to test.
- **A different horizon** (1-day, 10-20-day) on the same
  direction-classification task — cheap to try, but doesn't address
  the likely root cause (direction may not be learnable from this
  feature family at any horizon, consistent with weak-form market
  efficiency).
- **Per-asset-class models** (BIST and crypto modeled separately
  rather than pooled) — plausible the pooling dilutes signal, untested.
- **Sequence models** (LSTM/transformer on raw price history rather
  than hand-engineered indicators) — a materially different modeling
  approach, untested, though the consistent convergence across
  attempts 2-5 makes a strong positive result from this alone less
  likely than it would otherwise seem.

## Recommendation

Given five independent, methodologically sound attempts converge on
the same negative result, further attempts within this same feature
family (pure technical/price-volume indicators on this basket) are
unlikely to find something these five missed. The real fork is
strategic, not technical: invest in a paid data vendor for genuine
historical Fundamental/News data, or redirect effort away from
standalone directional/volatility prediction — e.g., using attempt 5's
weak rank-correlation signal only as a soft secondary input to the
existing rule-based "Top opportunities" ranking, rather than pursuing
a promotable standalone model on this data.
