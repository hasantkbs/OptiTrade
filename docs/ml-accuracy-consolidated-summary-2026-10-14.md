# ML Accuracy — Consolidated Summary of All 6 Attempts (as of 2026-10-14)

Supersedes `ml-accuracy-consolidated-summary-2026-10-13.md` (that
document's own verdict changes with attempt #6 below — kept for
history, not current).

## Verdict

Six independent attempts — one rule-based backtest and five trained
models, across two target types (direction, volatility), two
algorithms (XGBoost, RandomForest), two feature-set sizes (17, 49
features), and now two different symbol baskets with two different
feature families (pure Technical on BIST+crypto; Technical **plus
genuinely point-in-time Fundamental** on US equities) — have been run.
**None produced a result that beats a reasonable baseline cleanly
enough to promote.**

The sixth attempt is the important new evidence: it was specifically
designed to test whether the missing ingredient was Fundamental data.
It wasn't blocked by data availability this time (SEC EDGAR gave
genuinely free, point-in-time-correct fundamentals for US equities,
with 100% feature coverage across all 4,844 held-out samples) — and it
still landed at chance-level ROC-AUC (0.511) and below the majority
baseline. That changes the previous document's own framing: Fundamental
data was the one remaining unexhausted direction, and testing it (on
the one basket where it was actually available for free) did not
change the outcome. The most defensible reading is no longer just "a
ceiling in the Technical feature family" — it now looks like a ceiling
in the *task* (5-day-ahead price direction, at individual-stock daily
granularity, from these feature families generally), independent of
which basket or which fundamental data source is used.

No model from any of these attempts has been promoted beyond
`CANDIDATE`. The live decision_engine's production behavior is
unaffected by any of this work.

## The six attempts, side by side

| # | Date | What | Basket | Target | Algorithm(s) | Result vs. baseline | Verdict |
|---|------|------|--------|--------|--------------|----------------------|---------|
| 1 | 2026-10-03 | Decision-engine backtest (not an ML model) | 15 BIST + 7 crypto | direction | rule-based voting | 0.492 vs 0.588 | Inconclusive — HOLD-rate ambiguity never resolved |
| 2 | 2026-10-01 | First ML candidate | 15 BIST + 7 crypto | direction, 5d | XGBoost | 0.429 vs 0.479 | Invalid — real data bugs (crypto source mismatch, missing weekend data) |
| 3 | 2026-10-03 | Corrected-backfill, 3 bounded attempts | 15 BIST + 7 crypto | direction, 5d | XGBoost, RandomForest (×2 bands) | best: 0.458 vs 0.514 | Clean negative — ROC-AUC ≈ 0.50 on every variant |
| 4 | 2026-10-03 | Derived-features candidate | 15 BIST + 7 crypto | direction, 5d | XGBoost, 49 features | 0.424 vs 0.486 | Clean negative — feature engineering changed nothing |
| 5 | 2026-10-13 | Volatility-regression candidate | 15 BIST + 7 crypto | expected_volatility, 5d | XGBoost regressor, 17 features | beats naive persistence; **loses to constant-mean baseline** | Mixed/negative — weak rank correlation (0.098) the only positive |
| 6 | 2026-10-14 | **Technical + genuinely point-in-time SEC Fundamentals** | **28 US equities** | direction, 5d | XGBoost, 34 features (17 Technical + 17 SEC Fundamental) | **0.454 vs 0.459, ROC-AUC 0.511** | **Clean negative** — fundamentals added, zero improvement |

## Attempt 6 in detail — `docs/ml-candidate-report-2026-10-14-us-fundamentals.md`

Built entirely on free data: SEC EDGAR's XBRL Company Facts API for
genuinely point-in-time fundamentals (`docs/data-vendor-research-2026-
10-13.md` found no paid vendor offering a *confirmed* point-in-time
guarantee at any price — SEC EDGAR, the actual legal source every
vendor resells, turned out to both solve the correctness problem and
cost nothing). 17 raw and derived fundamental features (total
assets/liabilities/equity, revenue, net income, operating income, EPS,
shares outstanding, operating cash flow, debt/equity, ROE, ROA,
margins, revenue growth, P/E, P/B) were backfilled for 28 US equities,
each value keyed by its actual SEC filing date — not the fiscal period
end date — so a later restatement (verified live: AAPL's FY2008 Assets
figure was refiled three times under three different dates, the last a
10-K/A amendment) is correctly invisible to any training sample dated
before that refiling. Combined with the same 17 Technical features
used throughout attempts 2-5, on a 2-year train window with a genuinely
held-out 6-month-later evaluation window (4,844 samples, same
discipline as every prior attempt):

| Metric | Value |
|---|---|
| Accuracy | 0.454 |
| Majority baseline | 0.459 |
| Precision | 0.301 |
| Recall | 0.339 |
| ROC AUC | 0.511 |

All 17 SEC fundamental features were present in 100% of held-out
samples — this is not a sparse-data result. The model performs
indistinguishably from chance and very slightly below the naive
majority-class baseline, the same pattern as attempts 2-4 on a
completely different basket and feature family.

## What this changes

Prior documents (`ml-accuracy-consolidated-summary-2026-10-13.md`,
`data-vendor-research-2026-10-13.md`) framed Fundamental/News data as
the one genuinely unexhausted direction, worth testing cheaply on US
equities before deciding whether a harder/costlier BIST-specific data
investment made sense. That test has now run, cleanly, on real
point-in-time data, and found nothing. This doesn't prove Fundamental
data can *never* help (News remains genuinely untested — see below),
but it substantially weakens the case that *missing data* was the
reason the first five attempts failed, and correspondingly weakens the
case for investing further in a harder data problem (BIST point-in-time
fundamentals, which the vendor research found to be expensive and
still not confirmed-correct at any price) expecting a different
outcome.

## What's still genuinely untested

- **News features** — still completely untested across all 6 attempts.
  EODHD's free tier does provide genuine historical news with real
  timestamps (confirmed working), unlike its fundamentals endpoint —
  this is the one remaining direction with a free path already
  partially validated.
- **Per-asset-class modeling, different horizons, sequence models** —
  as noted in the prior summary, still untested, though six
  convergent negative results now make a strong positive surprise
  from any of these less likely than it would otherwise seem.

## Recommendation

Six independent, methodologically sound attempts — including the one
that was specifically designed to fill the previously-identified gap —
converge on the same result. Before investing in anything costlier
(a BIST data vendor, a sequence-model rewrite), the one remaining cheap,
already-partially-validated option is a News-only test on the same US
basket (EODHD's free news endpoint already confirmed working). If that
also comes back negative, the honest conclusion is that 5-day-ahead
directional prediction from this project's available data sources —
price, volume, fundamentals, and likely news — does not support a
promotable model, and effort is better spent elsewhere (e.g., the
rule-based "Top opportunities" ranking already shipped, or portfolio-
level risk management rather than single-symbol direction prediction).
