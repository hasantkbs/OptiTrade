# ML Accuracy — Consolidated Summary of All 7 Attempts, Final (as of 2026-10-14)

Supersedes `ml-accuracy-consolidated-summary-2026-10-14e.md` (second-window
validation), `-2026-10-14d.md` (AUC diagnosis), `-2026-10-14c.md`
(significance test), `-2026-10-14b.md` (pre-significance-test summary), and
the earlier `-2026-10-14.md` (6 attempts) / `-2026-10-13.md` (5 attempts) —
all kept for history, not current. This version folds the AUC diagnosis
and the second-window replication check back into one coherent summary,
in the same format as the earlier consolidated versions, rather than
three separate addenda that each covered only one piece.

## Verdict

Seven attempts, one genuinely interesting result, and that result did
not survive its first replication check. Attempt 7 (Technical + SEC
Fundamentals + News, 28 US equities) was the first of seven to beat its
baseline and the first with a statistically significant metric — on its
original held-out window (2026-07-16 → 2026-10-14). A second,
independent, non-overlapping held-out window (2026-04-17 → 2026-07-15)
reran the identical same-split control and found the effect shrinks
~2.5x, loses significance, and the News-included model falls **below**
baseline — the same failure mode every other attempt showed.

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
| 7 | 2026-10-14 | Technical + SEC Fundamentals + News | 28 US equities | Window 1: 0.449 vs 0.445 (p=0.014). Window 2: 0.451 vs 0.470 (p=0.308) | **Promising on one window, did not replicate on a second** |

## Attempt 7 in detail

**Window 1** (`scripts/train_ml_candidate_us_news_control.py`, train
2025-10-29→2026-07-15, held-out 2026-07-16→2026-10-14, 7,280/2,352
samples): accuracy 0.449 vs. 0.424 without News (baseline 0.445),
ROC-AUC 0.530 vs. 0.522. McNemar's test on the paired held-out
predictions: p=0.014. Paired bootstrap (2,000 resamples): accuracy gap
95% CI [0.005, 0.044] (excludes zero); ROC-AUC gap 95% CI [-0.006, 0.025]
(includes zero — not significant).

**Why AUC didn't move on window 1, diagnosed**
(`scripts/train_ml_candidate_us_news_control.py`'s per-class/confidence
diagnostics): the "easy, already-confident calls" hypothesis was
checked and falsified — the discordant cases McNemar's test is built on
sit at *below*-average model confidence (0.544 vs. 0.626 overall), and
the accuracy gain is largest in the model's *least* confident tercile
(+0.034), not its most confident one (+0.012). The real mechanism:
News improved per-class AUC for BUY (+0.015) and SELL (+0.016) — 87% of
the held-out set — but slightly hurt HOLD's (-0.011), a class neither
model variant could predict at all (recall ≈1%). Macro-averaged AUC
weighs HOLD equally with BUY/SELL despite its much smaller support, so
a real BUY/SELL gain was partly cancelled in the average; a
support-weighted re-aggregation of the same three per-class AUCs gave a
gap of +0.0119, roughly double the plain macro gap.

**Window 2** (`scripts/train_ml_candidate_us_news_window2.py`, train
2025-10-29→2026-04-16, held-out 2026-04-17→2026-07-15 — zero overlap
with window 1's held-out period, 4,760/2,520 samples): accuracy 0.451
vs. 0.441 without News, but **baseline here is 0.470** — so even the
News-included model (0.451) sits below baseline. McNemar's p=0.308
(not significant). Bootstrap accuracy gap 95% CI [-0.008, 0.029]
(includes zero); ROC-AUC gap 95% CI [-0.005, 0.027] (includes zero).
The window-1 mechanism also didn't reproduce in the same shape: on
window 2, News *helped* HOLD's AUC (+0.016, versus window 1's -0.011),
and the confidence-tercile gain pattern inverted (largest in the middle
tercile, not the low one). One thing did hold on both windows: the
McNemar discordant cases sit at below-average model confidence on both
— News tips close calls, not easy ones, consistently.

## What this does and doesn't show

**Does show**: News features produced a real, same-direction effect on
accuracy and ROC-AUC on both of the two available windows — the point
estimate never flipped sign across either metric or either window, and
when it IS significant (window 1), it is not an artifact of reinforcing
already-easy predictions. That distinguishes attempt 7 from attempts
2–6, none of which ever had a result worth testing for significance in
the first place.

**Doesn't show**: a reliable, production-worthy edge. The one window
where the effect was statistically significant does not replicate on
an adjacent, non-overlapping window — the effect shrinks ~2.5x, loses
significance, and the model falls below baseline there. The specific
per-class/confidence mechanism identified on window 1 is not a stable
property of the model either, since it doesn't reproduce in the same
shape on window 2 — consistent with both windows' effects being
substantially driven by window-specific noise on a held-out set that
is small either way (≤2,520 samples), rather than one robust underlying
signal. Both available windows inside Finnhub's free-tier News history
(~2025-10-29 onward) are now used; there is no further reslicing left
that adds genuinely new information rather than just shrinking samples.

## Recommendation

1. **No promotion of any kind** — not even SHADOW — on the strength of
   attempt 7. The bar that would have justified considering SHADOW (a
   validated, statistically significant effect) is no longer met once a
   second window is checked.
2. If this basket/feature combination is worth continuing, the next
   real lever is **more News history** — a paid Finnhub/EODHD tier, or
   waiting for free-tier coverage to extend — not another reslicing of
   the same ~350 days already fully used by these two windows.
3. Treat attempt 7 as **inconclusive**, not a clean negative like
   attempts 2–6 and not the validated positive it looked like after one
   window — the point estimates still favor News on both windows, just
   not at a size or confidence that supports acting on it yet.
