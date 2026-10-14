# ML Accuracy — Consolidated Summary of All 7 Attempts, With Significance Test (as of 2026-10-14)

Supersedes `ml-accuracy-consolidated-summary-2026-10-14b.md` (same 7
attempts, significance test not yet run) and the earlier `-2026-10-14.md`
(6 attempts) / `-2026-10-13.md` (5 attempts) — kept for history, not
current.

## Verdict

Attempt 7 (Technical + SEC Fundamentals + News, 28 US equities) is
the first result across all seven attempts with a statistically
significant finding - on one of its two key metrics, not both. A
same-split control (News features in vs. out, identical 7,280 train /
2,352 held-out samples) plus two significance tests give a precise,
honest picture:

- **Accuracy improvement (0.424 → 0.449) is statistically
  significant.** McNemar's paired test: p=0.0142. A 2,000-iteration
  bootstrap: 95% CI [0.0047, 0.0442] (excludes zero), P(News doesn't
  help)=0.0085.
- **ROC-AUC improvement (0.522 → 0.530) is NOT statistically
  significant at conventional thresholds.** Bootstrap: 95% CI
  [-0.0057, 0.0249] (includes zero), P(News doesn't help)=0.1185.

Both tests agree with each other on accuracy (McNemar's and the
bootstrap are independent methodologies, converging on the same
conclusion), which is itself reassuring - but the AUC result means
this is not an unambiguous, slam-dunk positive across every metric
that matters. It is the strongest, most carefully-checked positive
evidence across seven attempts, on accuracy specifically; ROC-AUC
trends the same direction (88% of bootstrap resamples favor News) but
doesn't clear the conventional 95% bar.

No model from any of these seven attempts has been promoted beyond
`CANDIDATE`. The live decision_engine's production behavior is
unaffected by any of this work.

## The seven attempts, side by side

| # | Date | What | Basket | Result vs. baseline | Verdict |
|---|------|------|--------|----------------------|---------|
| 1 | 2026-10-03 | Decision-engine backtest | 15 BIST + 7 crypto | 0.492 vs 0.588 | Inconclusive |
| 2 | 2026-10-01 | First ML candidate | 15 BIST + 7 crypto | 0.429 vs 0.479 | Invalid (data bugs) |
| 3 | 2026-10-03 | Corrected-backfill, 3 attempts | 15 BIST + 7 crypto | best 0.458 vs 0.514 | Clean negative |
| 4 | 2026-10-03 | Derived-features (49 features) | 15 BIST + 7 crypto | 0.424 vs 0.486 | Clean negative |
| 5 | 2026-10-13 | Volatility-regression | 15 BIST + 7 crypto | beats bad baseline, loses to good one | Mixed/negative |
| 6 | 2026-10-14 | Technical + SEC Fundamentals | 28 US equities | 0.454 vs 0.459, AUC 0.511 | Clean negative |
| 7 | 2026-10-14 | Technical + SEC Fundamentals + News | 28 US equities | 0.460 vs 0.445, AUC 0.537 | **Accuracy: significant (p=0.014). AUC: not significant (p≈0.12)** |

## Attempt 7's significance test in detail — `scripts/train_ml_candidate_us_news_control.py`

Same identical 7,280 train / 2,352 held-out samples as the earlier
control comparison, with two paired significance tests added (paired,
not independent-sample, since both models score the same held-out
set):

**McNemar's test (accuracy)**: of the discordant predictions, the
With-News model was uniquely right 299 times where Without-News was
wrong, versus 241 times the reverse. Statistic 6.02, p=0.0142 -
below the conventional 0.05 threshold.

**Paired bootstrap (2,000 resamples, accuracy and ROC-AUC gaps)**:

| Metric | Mean gap (With − Without) | 95% CI | P(gap ≤ 0) |
|---|---|---|---|
| Accuracy | +0.0250 | [0.0047, 0.0442] | 0.0085 |
| ROC-AUC | +0.0091 | [-0.0057, 0.0249] | 0.1185 |

The accuracy CI excludes zero; the ROC-AUC CI does not. Both point
estimates favor News, and the bootstrap's accuracy conclusion
independently agrees with McNemar's test - two different
methodologies landing on the same answer is a genuine corroboration,
not just one test's artifact.

## What this does and doesn't show

**Does show**: a statistically significant accuracy improvement from
adding News features to Technical + SEC Fundamentals, on this basket
and window, confirmed by two independent paired significance tests.
This is categorically different from attempts 2-6, none of which had
a result worth significance-testing in the first place (they were
at-or-below baseline, not meaningfully above it).

**Doesn't show**: that this is ready for production. ROC-AUC - a
metric that matters at least as much as accuracy for a 3-class
decision, since it reflects ranking/calibration quality, not just the
single threshold accuracy happens to measure - did not reach
significance. The result also hasn't been replicated on a second,
independent time window (News' free-tier history only covers this
one ~1-year span), and the held-out sample (2,352) is smaller than
other attempts'.

## Recommendation

This is the first result across seven attempts worth a real next
step, but that next step should be validation, not promotion: (1) a
second independent held-out window, once more News history is
available or a paid tier is worth considering; (2) treat the AUC gap
as the open question - understand WHY accuracy improved significantly
while AUC didn't (a classic pattern when a model gets more of the
"easy," already-high-confidence calls right without improving
discrimination on the harder ones) before deciding the improvement is
real and exploitable rather than concentrated in a few already-easy
cases; (3) if both of those hold up, a SHADOW deployment (this
platform's own existing promotion-state machinery) is the appropriate
next step - never a direct ACTIVE promotion - so real-world
performance can be tracked against live outcomes before influencing
any real decision.
