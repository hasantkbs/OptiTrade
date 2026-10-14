# ML Accuracy — Why Attempt 7's Accuracy Moved But ROC-AUC Didn't (as of 2026-10-14)

Supersedes `ml-accuracy-consolidated-summary-2026-10-14c.md` for one
specific point: that doc's recommendation guessed the AUC gap was
"a classic pattern when a model gets more of the 'easy,'
already-high-confidence calls right." A follow-up diagnostic run
(`scripts/train_ml_candidate_us_news_control.py`, extended with
per-class confusion matrices, per-class one-vs-rest AUC,
confidence-tercile accuracy, and a breakdown of the McNemar
discordant cases) shows **that guess was wrong**. Everything else in
`-2026-10-14c.md` (the headline numbers, the significance tests, the
recommendation to validate on a second window before any promotion)
still stands.

## What the diagnostic found

**1. The "easy calls" hypothesis is falsified by the data.**

The McNemar discordant cases — the 300 samples where adding News
flips a wrong prediction to right, and the 242 where it flips a right
one to wrong — are both **below the model's own average confidence**
(0.544 mean max-probability on both sets, vs. 0.626 overall). News is
tipping *close, uncertain* calls, not reinforcing calls the model was
already sure about.

The confidence-stratified breakdown confirms this directly: the
accuracy gain from adding News is **larger in the model's least
confident tercile, not its most confident one**.

| Confidence tercile | WITH News accuracy | WITHOUT News accuracy | Gap |
|---|---|---|---|
| Low (mean conf. 0.48) | 0.423 | 0.389 | +0.034 |
| Mid (mean conf. 0.60) | 0.432 | 0.404 | +0.028 |
| High (mean conf. 0.79) | 0.490 | 0.478 | +0.012 |

If this were an "easy wins" effect, the gap would be largest in the
high-confidence tercile. It's the opposite.

**2. The real explanation: News helps BUY and SELL discrimination, but
slightly hurts HOLD's — and macro-AUC weighs all three equally.**

Per-class one-vs-rest AUC, same held-out set:

| Class | Support | WITH News AUC | WITHOUT News AUC | Gap |
|---|---|---|---|---|
| BUY | 1,046 (44.5%) | 0.526 | 0.511 | **+0.015** |
| SELL | 998 (42.4%) | 0.537 | 0.521 | **+0.016** |
| HOLD | 308 (13.1%) | 0.522 | 0.533 | **-0.011** |

News genuinely improves ranking quality on the two large, tradable
classes — consistently, by a similar margin on both. It makes the
already-weak HOLD class's ranking slightly worse. Macro-averaged
ROC-AUC (what the significance test computes) gives HOLD the same
1/3 weight as BUY and SELL despite it being under a third of their
sample size, so HOLD's small regression cancels out a real portion of
BUY/SELL's gains in the average. Re-weighting the same three numbers
by actual class support (1046/308/998 instead of equal thirds) gives
a gap of **+0.0119** — roughly double the plain macro gap this run
measured (+0.0068) — confirming the dilution is coming from exactly
where the per-class table says it is.

Accuracy doesn't have this problem: it's naturally weighted by how
often each class actually occurs, so the BUY/SELL improvement (87% of
the held-out set) dominates it directly. That's the core answer to
"why did accuracy move but not AUC": **not every class benefited, and
the one that didn't gets over-weighted by macro-AUC's averaging
convention relative to its real frequency and its real usefulness** —
both models already struggle badly with HOLD (recall ≈1% for both
arms, confusion matrices below), so a further small wobble there has
outsized leverage on the equal-weighted macro-AUC average without
reflecting anything that matters for 87% of real predictions.

**3. A separate, more basic finding, independent of News: neither
model can call HOLD at all.**

| True \ Predicted (WITH News) | BUY | HOLD | SELL |
|---|---|---|---|
| BUY (1046) | 547 | 21 | 478 |
| HOLD (308) | 158 | **3** | 147 |
| SELL (998) | 480 | 13 | 505 |

HOLD recall is 0.010 (WITH) / 0.013 (WITHOUT) — both models predict
HOLD on essentially none of the 308 samples that are actually HOLD,
and effectively act as BUY-vs-SELL classifiers. This is a pre-existing
property of this label/feature combination, not something News
caused or fixed — flagged here because it's the direct mechanical
reason HOLD's AUC is so fragile (so few predicted-HOLD samples that
its ranking can swing on small amounts of noise) and therefore why it
has outsized leverage on the macro-AUC average. Worth a separate look
(wider HOLD band, class weighting, or a 2-class BUY/SELL reformulation)
if HOLD prediction quality itself ever becomes a goal — out of scope
for this News investigation.

## Revised reading of attempt 7

Accuracy's significance (McNemar's p≈0.014, bootstrap CI excluding
zero) reflects a real, non-trivial effect specifically on the BUY/SELL
decision — the one that would actually drive trades — and it is not
an artifact of the model getting more of its easy calls right. ROC-AUC's
non-significance is largely a byproduct of macro-averaging across a
third class (HOLD) that both models already handle poorly and rarely
predict, not evidence that News' effect on the classes that matter is
illusory.

This strengthens the case for attempt 7's result somewhat (the original
worry — "maybe this is just inflating confidence on already-easy
rows" — is directly contradicted by the data) but doesn't change the
recommendation already on record in `-2026-10-14c.md`: still unreplicated
on a second window, still CANDIDATE-only, still SHADOW-not-ACTIVE if it
ever gets there.
