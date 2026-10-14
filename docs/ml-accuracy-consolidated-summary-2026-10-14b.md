# ML Accuracy — Consolidated Summary of All 7 Attempts (as of 2026-10-14)

Supersedes `ml-accuracy-consolidated-summary-2026-10-14.md` (6
attempts) and `-2026-10-13.md` (5 attempts) — kept for history, not
current.

## Verdict

Seven attempts now, and attempt 7 is the first genuinely interesting
result: adding News features to Technical + SEC Fundamentals, on the
**identical** chronological train/held-out split, consistently
improved both accuracy (0.424 → 0.449) and ROC-AUC (0.522 → 0.530).
This is the first time in seven attempts that adding a feature family
moved performance in a consistent positive direction — attempt 4
(adding 32 derived Technical features) moved it in no direction at
all (0.431 → 0.424, noise-sized and in the wrong direction), and
attempt 6 (adding SEC Fundamentals, different basket) showed none
either.

**This is not a conclusive win, and shouldn't be reported as one.**
The effect is small, on a smaller held-out sample (2,352) than most
other attempts, with no formal significance test run yet - at this
sample size and effect size, a 0.008-0.025 shift is plausibly within
ordinary model-to-model variance rather than a reliably exploitable
signal. What makes it worth flagging rather than dismissing outright
is the *consistency*: both accuracy and ROC-AUC moved the same
direction together, on the same exact data split - a coincidence is
possible but less likely than with a single-metric fluctuation.

No model from any of these seven attempts has been promoted beyond
`CANDIDATE`. The live decision_engine's production behavior is
unaffected by any of this work.

## The seven attempts, side by side

| # | Date | What | Basket | Target | Result vs. baseline | Verdict |
|---|------|------|--------|--------|----------------------|---------|
| 1 | 2026-10-03 | Decision-engine backtest | 15 BIST + 7 crypto | direction | 0.492 vs 0.588 | Inconclusive |
| 2 | 2026-10-01 | First ML candidate | 15 BIST + 7 crypto | direction, 5d | 0.429 vs 0.479 | Invalid (data bugs) |
| 3 | 2026-10-03 | Corrected-backfill, 3 attempts | 15 BIST + 7 crypto | direction, 5d | best 0.458 vs 0.514 | Clean negative |
| 4 | 2026-10-03 | Derived-features (49 features) | 15 BIST + 7 crypto | direction, 5d | 0.424 vs 0.486 | Clean negative |
| 5 | 2026-10-13 | Volatility-regression | 15 BIST + 7 crypto | expected_volatility, 5d | beats bad baseline, loses to good one | Mixed/negative |
| 6 | 2026-10-14 | Technical + SEC Fundamentals | 28 US equities | direction, 5d | 0.454 vs 0.459, AUC 0.511 | Clean negative |
| 7 | 2026-10-14 | **Technical + SEC Fundamentals + News** | 28 US equities | direction, 5d | **0.460 vs 0.445, AUC 0.537** | **First consistent positive — unconfirmed, needs more validation** |

## Attempt 7 in detail

Two runs, same train/held-out windows (sized to Finnhub's free-tier
~1-year News history: train 2025-10-29→2026-07-15, held-out
2026-07-16→2026-10-14), same 28-symbol US-equity basket:

**Main run** (`docs/ml-candidate-report-2026-10-14-us-news.md`,
proper train/val split with early stopping, registered as CANDIDATE
`xgb-dir-5d-2bb97fd1`): accuracy 0.460 vs 0.445 baseline, ROC-AUC
0.537, precision 0.339, recall 0.354. 39 features (17 Technical + 17
SEC Fundamental + 5 News), 100% News/Fundamental coverage across all
2,352 held-out samples.

**Same-split control** (`scripts/train_ml_candidate_us_news_control.py`,
no val split/early stopping, run purely for this A/B comparison - not
registered as a candidate): on the *identical* 7,280 train / 2,352
held-out samples -

| | WITH News (39 features) | WITHOUT News (34 features) |
|---|---|---|
| Accuracy | 0.449 | 0.424 |
| Majority baseline | 0.445 | 0.445 |
| ROC AUC | 0.530 | 0.522 |

Removing News drops the model below baseline and below the With-News
run on both metrics. The control's own numbers differ slightly from
the main run's (0.449 vs 0.460, 0.530 vs 0.537) because it skips the
validation split/early stopping the main run used - expected, not a
discrepancy to resolve, since the control's only purpose is the A/B
comparison between its own two arms, not reproducing the main run
exactly.

## What this does and doesn't show

**Does show**: on this specific basket, window, and label, News
features (sentiment/relevance/impact/confidence/article-count,
computed by the existing live News engine's own scoring pipeline,
backfilled point-in-time via Finnhub's free historical company-news
endpoint) contributed a small, same-direction improvement on both
accuracy and ROC-AUC when added to Technical + SEC Fundamentals -
unlike every previous feature addition tried across the first six
attempts.

**Doesn't show**: that this is a reliable, production-worthy edge.
No significance test (bootstrap CI, permutation test) has been run;
the held-out sample is smaller than other attempts' (News' free-tier
history only goes back ~1 year, vs. 2 years for Technical/SEC); and
the effect hasn't been replicated on a second, independent held-out
window. A result this size, on a sample this size, from a single
run, is evidence worth taking seriously - not evidence worth acting
on yet.

## Recommendation

Before any promotion decision: (1) run a bootstrap or permutation
significance test on the News-features gap to quantify how likely
0.008-0.025 is to arise by chance at n=2,352; (2) if time/resources
allow, validate on a second held-out window (even a smaller one) to
check the effect replicates rather than being specific to Jul-Oct
2026; (3) only after both of those, consider a SHADOW deployment
(per this platform's existing promotion-state machinery) rather than
ACTIVE promotion, so real-world performance can be tracked against
live outcomes before it ever influences a real decision.

This is also, notably, the one result across seven attempts that
makes investing further in News data (deeper history, more symbols,
a paid tier with faster backfill) a more defensible next step than
investing further in Fundamental data (attempt 6's clean negative) or
retrying Technical-only variations (attempts 2-5's clean negatives).
