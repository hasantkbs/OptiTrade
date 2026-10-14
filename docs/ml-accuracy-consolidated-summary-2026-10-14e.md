# ML Accuracy — Attempt 7's Second-Window Validation (as of 2026-10-14)

Supersedes nothing in `-2026-10-14d.md`'s AUC diagnosis (that mechanism
analysis stands on its own data), but materially changes the verdict on
attempt 7 itself: **the News effect does not clearly replicate on an
independent held-out window, and on that window the News-included model
falls below baseline.**

## What was run

`scripts/train_ml_candidate_us_news_window2.py` (new, reuses every
helper from `train_ml_candidate_us_news_control.py` - significance
tests and diagnostics unchanged, only the date window differs) repeats
the exact same WITH-News vs WITHOUT-News comparison on the window
immediately preceding the original one, chosen so the two held-out
periods share **zero days**:

| | Window 1 (original) | Window 2 (this validation) |
|---|---|---|
| Train | 2025-10-29 → 2026-07-15 (7,280 samples) | 2025-10-29 → 2026-04-16 (4,760 samples) |
| Held-out | 2026-07-16 → 2026-10-14 (2,352 samples) | 2026-04-17 → 2026-07-15 (2,520 samples) |

Both windows are the largest available inside Finnhub's free-tier News
coverage (~2025-10-29 onward) that still leave a held-out period long
enough to be meaningful - window 2's training period is necessarily
shorter since it has to end before window 1's held-out period begins.

## Results side by side

| Metric | Window 1 | Window 2 |
|---|---|---|
| Majority baseline | 0.445 | **0.470** |
| WITH News accuracy | 0.449 | 0.451 |
| WITHOUT News accuracy | 0.424 | 0.441 |
| WITH News vs. baseline | **+0.004** (above) | **-0.019** (below) |
| Accuracy gap (With − Without) | +0.025 | +0.010 |
| McNemar's p-value | **0.014** | **0.308** |
| Bootstrap accuracy 95% CI | [0.005, 0.044] (excludes 0) | [-0.008, 0.029] (includes 0) |
| WITH News ROC-AUC | 0.530 | 0.516 |
| WITHOUT News ROC-AUC | 0.522 | 0.505 |
| Bootstrap AUC 95% CI | [-0.006, 0.025] (includes 0) | [-0.005, 0.027] (includes 0) |

## What this does and doesn't show

**Still true on both windows**: the point estimate for News' effect on
both accuracy and ROC-AUC is positive in the same direction. Zero out of
four point estimates flipped sign.

**No longer true**: window 1's headline claim - "accuracy improvement is
statistically significant" - does not hold on window 2. McNemar's
p-value goes from 0.014 to 0.308, and the bootstrap CI widens to include
zero. The effect is roughly 2.5x smaller on window 2 (+0.010 vs +0.025).

**New and more concerning**: on window 2, the WITH-News model is **below**
the majority-class baseline (0.451 vs 0.470), the same failure mode every
one of attempts 1-6 showed. Window 1's "first model to beat baseline"
result does not generalize to this adjacent period - the baseline itself
moved (0.445 → 0.470, since the true BUY/HOLD/SELL mix differs by
window), and neither model variant tracked that shift.

**The window-1 "mechanism" doesn't reproduce either**, which matters for
how much to trust it as an explanation rather than a post-hoc story fit
to one run:
- Window 1: News improved BUY and SELL per-class AUC but *hurt* HOLD's
  (+0.015, +0.016, -0.011). Window 2: News improved all three, including
  HOLD (+0.009, +0.009, **+0.016**).
- Window 1: the accuracy gain was *largest in the model's least
  confident tercile* (+0.034 low vs. +0.012 high). Window 2: that
  pattern inverts (-0.001 low vs. -0.024 high, with the gain
  concentrated in the *middle* tercile instead, +0.055).

Both windows still show the McNemar/bootstrap discordant cases sitting
at below-average model confidence (News tips close calls, not easy
ones, in both windows) - that part replicates. But the specific
per-class and confidence-tercile shape of the effect does not, which
means `-2026-14d.md`'s detailed mechanism (BUY/SELL gain diluted by a
HOLD-class macro-AUC penalty) was a real, correct read of window 1's
data, but isn't a stable property of this model - it's consistent with
both windows' effects being driven substantially by window-specific
noise on a ~2,400-sample held-out set, not one robust underlying signal.

## Revised recommendation

Attempt 7 should be read as: **a promising single-window result that
did not survive its first replication check.** That is a materially
different status than `-2026-10-14c.md`'s "first statistically
significant positive, pending validation" framing - this is the
validation, and it came back weak.

This does not prove News features are useless - the point estimates
stayed positive on both metrics on both windows, and the real
constraint here is data, not necessarily the hypothesis: both windows
are small (≤2,520 held-out samples) and short (≤9 months), bounded by
Finnhub's one-year free-tier history. But it does mean:

1. **No promotion of any kind** - not even SHADOW - on the strength of
   attempt 7 alone. The bar that motivated considering SHADOW in
   `-2026-10-14c.md` (a statistically significant, validated effect) is
   no longer met once a second window is checked.
2. If this basket/feature combination is worth continuing, the next
   real lever is **more News history** (a paid Finnhub/EODHD tier, or
   waiting for free-tier coverage to extend), not another same-data
   reslicing - both available windows are already used, and reslicing
   the same ~350 days of News coverage any further only shrinks samples
   further without adding genuine new information.
3. Barring new data, this is a reasonable point to close out the
   News-features line of investigation as "inconclusive, not negative" -
   distinct from attempts 2-6's clean negatives, but not the positive
   result it looked like after a single window.
