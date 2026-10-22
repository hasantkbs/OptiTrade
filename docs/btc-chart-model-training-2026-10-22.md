# Chart AI Model — Fix, Training, and Multi-Symbol Validation (2026-10-22)

## Context

`ml/chart_model.py` (CNN + Bidirectional LSTM, 60-day sliding window,
11 technical-indicator features, 3-class SELL/NEUTRAL/BUY output) was
already wired into the live analysis path (`main.py::_enrich_result`
→ `core/advanced_analysis.py::compute_recommendation`, 15% weight) —
but no trained model file (`model_artifacts/btc_chart_model.keras`)
had ever existed, so this path was always a no-op (`is_model_available()`
returned `False`).

## Three bugs found and fixed before training

1. **`train()` ignored its own `symbol` parameter.** The actual data-
   pull loop was hardcoded to a 20-symbol list spanning crypto, US
   tech, BIST, Nikkei, and global indices, concatenated together -
   whatever `--symbol` was passed only got written into the output
   metadata's `trained_on` field. Fixed: `train()` now pulls only
   `symbol`'s own history, matching its docstring and its own
   `MODEL_PATH` (`btc_chart_model.keras` - a single-symbol file name).

2. **Train/val/test split was not chronological.** Because sequences
   from 20 different symbols were concatenated in a fixed order before
   a positional split, the "test" set was dominated by whichever
   symbols came last in that list (global indices) - not BTC, and not
   reliably "the most recent period" for any one market. Fixed as a
   side effect of (1): pulling a single symbol's own history preserves
   chronological order, so the existing positional split is now a
   genuine time-ordered split.

3. **ADX calculation crashed on every real symbol.** In
   `_build_features()`, `pd.Series(plus_dm)` / `pd.Series(minus_dm)`
   were built with a default `RangeIndex` while `atr` kept the OHLCV
   frame's original `DatetimeIndex`. Dividing the two made pandas
   align by index (the union of both - roughly double length, mostly
   NaN) instead of elementwise by position, so every downstream
   `np.column_stack` call raised a dimension-mismatch error. This is
   almost certainly *why* no model file ever existed: under the old
   per-symbol `try/except: log and skip` loop, this exception fired
   for every single symbol, silently emptied `all_X`, and raised
   `"Hiç veri toplanamadı"` - the training pipeline had likely never
   completed successfully, for any symbol, since it was written. Fixed
   by passing `index=high.index` to both `pd.Series()` calls.

Added `tests/test_chart_model_build_features.py` (3 tests) as a
regression guard against bug #3, and confirmed `tests/test_research_train_chart_model.py`
and `tests/test_research_isolation.py` still pass.

## Training result (window 1 — chronologically last 15% of BTC-USD's full history)

4,324 sequences total (BTC-USD, `period="max"`), 70/15/15
chronological train/val/test split with a `FORWARD_DAYS`-sized gap at
each boundary (to avoid the forward-return label leaking across a
split edge):

| | Value |
|---|---|
| Test accuracy | **0.5583** |
| Test-set majority baseline | 0.4852 (NEUTRAL, 312/643) |
| Gap vs. baseline | **+0.0731** |
| Binomial test (accuracy > baseline rate) | p = 0.00012 |

Saved to `backend/model_artifacts/btc_chart_model.keras` /
`btc_chart_scaler.joblib` / `btc_chart_model_meta.json` (full
classification report + confusion matrix in the meta file).

## Second-window validation (`scripts/research/validate_chart_model_window2.py`)

Following the same discipline used for the ML-accuracy News-features
work (never trust a single split without checking it replicates on a
non-overlapping window): a *freshly trained* model, using only
window 1's former TRAIN block (first 70%) as its own train/inner-val
split, evaluated on window 1's former VAL block (middle 15% - zero
overlap with window 1's reported test block):

| | Window 1 | Window 2 |
|---|---|---|
| Test accuracy | 0.5583 | 0.5365 |
| Majority baseline | 0.4852 | 0.4370 |
| Gap vs. baseline | +0.0731 | **+0.0995** |
| Binomial p-value | 0.00012 | <0.00001 |

The effect replicates - same direction, comparable (if anything,
slightly larger) magnitude, on a held-out period that shares zero days
with window 1's. This is a materially different outcome than the
ML-accuracy News-features result (attempt 7), which looked similarly
promising on one window and did not replicate on a second
(`ml-accuracy-consolidated-summary-2026-10-14f.md`).

## Operational note — no staging gate

Unlike `ml_training`'s candidates (which go through an explicit
CANDIDATE → SHADOW → ACTIVE promotion state machine), this chart
model's live integration has no such gate: `main.py` checks only
`is_model_available()` (does the file exist on disk), so the moment
`btc_chart_model.keras` exists, it is live - weighing 15% into every
BTC recommendation via `compute_recommendation`. Given the second-
window validation held up, this is being kept live rather than rolled
back.

## Fourth bug found while expanding to a second symbol — no symbol gate at all

Right after the BTC model went live, `main.py::_enrich_result` was
found to apply it to **every** analyzed symbol, not just BTC -
`is_model_available()` had no symbol parameter, so once *any* model
file existed, `predict_chart_signal()` ran on every symbol's own
features through BTC's model and scaler, feeding a signal into
non-BTC recommendations at 15% weight. Fixed by adding
`ml.chart_model.MODEL_SYMBOL` and gating `_enrich_result` on
`result.symbol == MODEL_SYMBOL` (committed separately, `4e13267`).
Regression test: `tests/test_main_chart_ai_symbol_gating.py`.

## Per-symbol model storage (prerequisite for a second symbol)

`MODEL_PATH`/`SCALER_PATH` were flat, BTC-only path constants -
training a second symbol would have silently overwritten BTC's
already-validated model file. Added `model_path_for(symbol)` /
`scaler_path_for(symbol)` / `meta_path_for(symbol)` (e.g. `"BTC-USD"` →
`btc_chart_model.keras`, `"ETH-USD"` → `eth_chart_model.keras`).
`load_model()`, `predict_chart_signal()`, `is_model_available()`, and
`get_model_meta()` all gained an optional `symbol` parameter
defaulting to `MODEL_SYMBOL`, so every existing BTC-only call site
(including `main.py`, which still only gates on `MODEL_SYMBOL`) is
completely unaffected. `MODEL_PATH`/`SCALER_PATH` stay as flat
attributes for backward compatibility with the untouched
`_try_load_base_model()` legacy helper and its tests. Regression test:
`tests/test_chart_model_per_symbol_paths.py`.

`research/validate_chart_model_window2.py` also gained a `--symbol`
CLI argument it was missing (caught immediately when a first attempt
to validate ETH silently re-ran on BTC's own data instead - the script
had no `argparse` block at all, so `--symbol ETH-USD` was accepted by
the shell but ignored by the script, which always called `validate()`
with its BTC default).

## ETH-USD — second symbol, same methodology

Trained and validated exactly like BTC (same architecture, same
chronological split discipline, same second-window check), now that
per-symbol storage exists:

| | BTC window 1 | BTC window 2 | ETH window 1 | ETH window 2 |
|---|---|---|---|---|
| Test accuracy | 0.5583 | 0.5365 | 0.5287 | 0.4459 |
| Majority baseline | 0.4852 | 0.4370 | 0.3546 | 0.3546 |
| Gap vs. baseline | +0.0731 | +0.0995 | **+0.1741** | +0.0913 |
| Binomial p-value | 0.00012 | <0.00001 | <0.000001 | 0.000028 |

ETH's effect also replicates on its own non-overlapping second
window - smaller than window 1's gap (unlike BTC, where window 2 was
if anything larger), but still clearly significant (p=0.000028, well
under any conventional threshold). Saved to
`backend/model_artifacts/eth_chart_model.keras` /
`eth_chart_scaler.joblib` / `eth_chart_model_meta.json` - BTC's own
files were confirmed untouched (same mtimes) before and after.

## ETH wired live too

Given ETH's second-window validation held up, `main.py`'s gate was
extended from a single `MODEL_SYMBOL` constant to
`ml.chart_model.SUPPORTED_SYMBOLS = ("BTC-USD", "ETH-USD")` - an
explicit allowlist, not "any symbol with a model file on disk is
live," so adding a future symbol still requires a deliberate code
change rather than becoming active the moment a training run happens
to produce a file. `is_model_available(symbol)` and
`predict_chart_signal(hist, symbol=...)` are now called with each
analyzed symbol explicitly (previously both defaulted silently to
BTC), so BTC and ETH each score through their own model/scaler.
Verified end-to-end with a real ETH-USD history pull before
committing. Regression tests extended in
`tests/test_main_chart_ai_symbol_gating.py` (now also covers "every
supported symbol gets scored through its own model" and "an
unsupported symbol is still skipped").

## Completing the platform's crypto basket — BNB, SOL, XRP

`core/market_config.py::CRYPTO_SYMBOLS` has exactly five entries
(BTC-USD, ETH-USD, BNB-USD, SOL-USD, XRP-USD). With BTC and ETH both
validated and live, the remaining three were trained and validated
the same day, same methodology, in one batch:

| | BNB W1 | BNB W2 | SOL W1 | SOL W2 | XRP W1 | XRP W2 |
|---|---|---|---|---|---|---|
| Test accuracy | 0.5117 | 0.4671 | 0.3550 | 0.4527 | 0.4756 | 0.5074 |
| Majority baseline | 0.4246 | 0.3631 | **0.3876** | 0.4024 | 0.4289 | 0.3715 |
| Gap vs. baseline | +0.0871 | +0.1040 | **-0.0326** | +0.0503 | +0.0467 | +0.1359 |
| Binomial p-value | 0.000087 | 0.000002 | **0.901** | 0.034 | 0.023 | 0.000000 |

**BNB-USD**: clean replication, both windows strongly significant and
positive - same pattern as BTC/ETH. Added to `SUPPORTED_SYMBOLS`, live.

**XRP-USD**: both windows significant and positive, though window 1 is
markedly weaker (p=0.023 - well under 0.05, but nowhere near as
decisive as BTC/ETH/BNB's window 1 results). Window 2 is actually
*more* significant than window 1 (p<0.000001), the opposite of what
pure noise inflating window 1 would predict - this is the same kind of
corroboration-across-windows reasoning used throughout the ml-accuracy
research, and it reads as a genuine (if weaker) effect rather than a
fluke. Added to `SUPPORTED_SYMBOLS`, live.

**SOL-USD**: window 1 is not just non-significant, it's *negative*
(0.355 vs. 0.388 baseline, p=0.901 - essentially indistinguishable
from chance, and if anything worse). Window 2 alone looks fine
(p=0.034), but one failing window is disqualifying under the same bar
BTC/ETH/BNB/XRP all had to clear on *both* windows - this is exactly
the single-window-looked-promising-then-didn't-hold pattern the
ml-accuracy News-features work hit (`ml-accuracy-consolidated-summary-2026-10-14f.md`).
**Not** added to `SUPPORTED_SYMBOLS` - trained and saved
(`sol_chart_model.keras` etc. exist on disk) but inert, since the
allowlist design means existing on disk is not enough to go live.
Worth revisiting if SOL-USD's yfinance history grows - it already has
noticeably fewer sequences than the other four (2,292 vs. ~3,175),
plausibly because SOL's listing history is shorter, which may be
contributing to the weaker/inconsistent result rather than ruling out
the approach for this symbol permanently.

`SUPPORTED_SYMBOLS` is now `("BTC-USD", "ETH-USD", "BNB-USD", "XRP-USD")`
- 4 of the platform's 5 canonical crypto symbols live, SOL-USD excluded
with the reasoning recorded above (both in this doc and as a code
comment next to `SUPPORTED_SYMBOLS` in `ml/chart_model.py`).

## First equity — THYAO.IS (BIST), and a fifth bug in the live path

With the crypto basket done, the next test is a different asset class
entirely: BIST equities, trading 5 days/week (unlike crypto's 7).
THYAO.IS (Türk Hava Yolları, the BIST basket's flagship/most liquid
symbol) was trained and validated the same way:

| | THYAO W1 | THYAO W2 |
|---|---|---|
| Test accuracy | 0.5010 | 0.5900 |
| Majority baseline | 0.4210 | 0.3840 |
| Gap vs. baseline | +0.0800 | **+0.2060** |
| Binomial p-value | 0.0000002 | ~0 |

The strongest result of any symbol tried so far - both windows highly
significant, window 2 even larger than window 1 (same reinforcing
pattern as BTC and BNB). 6,704 total sequences, far more than any
crypto symbol, because THYAO.IS has a much longer yfinance history
than any crypto asset (BIST listing vs. a 2017-era crypto listing) -
more training data plausibly explains part of why equity numbers came
out stronger than crypto's.

**Fifth bug, found while smoke-testing before going live**:
`main.py`'s live history pull used a hardcoded `period="3mo"`. For
THYAO.IS this produced only 37 valid feature rows after `_build_features()`'s
30-row warmup trim - short of `WINDOW` (60) - so `predict_chart_signal()`
always returned `{"error": "Yetersiz veri"}` in production, silently
producing no signal. Worse: crypto's own margin was dangerously thin
too (63 rows for a 60-row window, since crypto trades 7 days/week vs.
equities' 5) - a slightly shorter month could have broken BTC/ETH/BNB/XRP
the same way at any time without anyone noticing, since the failure is
swallowed by `_enrich_result`'s own try/except. Fixed by changing to
`period="6mo"` (125 raw rows for THYAO.IS, 95 after warmup - comfortable
margin for both 5-day and 7-day markets). Regression tests added to
`tests/test_chart_model_build_features.py` encoding the exact margin
requirement with synthetic business-day data (3mo-equivalent fails the
window requirement, 6mo-equivalent clears it).

Added to `SUPPORTED_SYMBOLS` (now `("BTC-USD", "ETH-USD", "BNB-USD",
"XRP-USD", "THYAO.IS")`) after re-verifying the real end-to-end
prediction with the `period="6mo"` fix in place for both THYAO.IS and
BTC-USD.

## Completing the platform's default BIST watchlist

`core/market_config.py::get_default_watchlist("TR")` - the platform's
actual default-active basket for the Turkish market (10 symbols,
distinct from the much larger `BIST_SYMBOLS` reference/display-name
table of 36) - has THYAO.IS plus 9 more: GARAN.IS, EREGL.IS, ASELS.IS,
KCHOL.IS, AKBNK.IS, TUPRS.IS, SISE.IS, BIMAS.IS, FROTO.IS. All 9 were
trained and validated the same day, same methodology, in one batch:

| Symbol | W1 gap | W1 p | W2 gap | W2 p |
|---|---|---|---|---|
| GARAN.IS | +0.228 | ~0 | +0.102 | ~0 |
| EREGL.IS | +0.120 | ~0 | +0.150 | ~0 |
| ASELS.IS | +0.161 | ~0 | +0.156 | ~0 |
| KCHOL.IS | +0.220 | ~0 | +0.102 | ~0 |
| AKBNK.IS | +0.242 | ~0 | +0.163 | ~0 |
| TUPRS.IS | +0.185 | ~0 | +0.134 | ~0 |
| SISE.IS | +0.190 | ~0 | +0.146 | ~0 |
| BIMAS.IS | +0.105 | ~0 | +0.075 | 0.000012 |
| FROTO.IS | +0.207 | ~0 | +0.189 | ~0 |

**9 for 9** - every single symbol clears both windows decisively, the
cleanest result of any basket tried (crypto's 4-for-5 included one
outright failure, SOL-USD). BIMAS.IS's window 2 p-value (0.000012) is
the "weakest" result in this whole batch and still far below any
conventional significance threshold. All 9 added to `SUPPORTED_SYMBOLS`
alongside THYAO.IS, verified end-to-end with real yfinance pulls
(`period="6mo"`) for every symbol before committing - the platform's
entire default BIST watchlist (10/10) is now live.

This consistency across 10 different BIST equities - after crypto
showed one failure out of 5 - is suggestive (plausibly: longer price
history than any crypto symbol gives the model more to learn from,
and/or BIST's retail-driven trading has more exploitable short-term
momentum than crypto or the News-features basket this session's
ml-accuracy research used) but shouldn't be over-read from 10 single-
window-pair checks alone; the same two-window bar was applied
uniformly, not relaxed for this batch.

## US equities — the platform's default US watchlist, mixed result

`core/market_config.py::get_default_watchlist("US")` (10 symbols:
AAPL, MSFT, NVDA, GOOGL, META, TSLA, JPM, V, XOM, HD) were trained and
validated the same way. Unlike BIST's clean 9-for-9, this basket is
mixed - the first real failures beyond crypto's single SOL-USD case:

| Symbol | W1 gap | W1 p | W2 gap | W2 p | Status |
|---|---|---|---|---|---|
| AAPL | +0.218 | ~0 | +0.130 | ~0 | LIVE |
| NVDA | +0.144 | ~0 | +0.195 | ~0 | LIVE |
| META | +0.067 | 0.0012 | +0.084 | 0.0001 | LIVE |
| TSLA | +0.151 | ~0 | +0.111 | ~0 | LIVE |
| JPM | +0.169 | ~0 | +0.138 | ~0 | LIVE |
| XOM | +0.201 | ~0 | +0.120 | ~0 | LIVE |
| HD | +0.125 | ~0 | +0.039 | 0.0002 | LIVE |
| MSFT | +0.108 | ~0 | **-0.009** | **0.769** | NOT live |
| GOOGL | **-0.004** | **0.597** | +0.044 | 0.0065 | NOT live |
| V | **-0.138** | **1.00** | **-0.057** | **0.999** | NOT live |

7 of 10 clear both windows and go live. 3 fail the same both-windows
bar every other symbol in this effort had to clear: **MSFT** passes
window 1 but window 2 is flat-to-negative (p=0.769 - no better than
chance); **GOOGL** is the reverse, window 1 essentially flat/negative
(p=0.597) despite a real window 2; **V** fails both windows outright,
clearly negative each time (p≈1 and p≈0.999) - the most decisive
failure of any symbol attempted, stronger even than SOL-USD's.

All three excluded symbols' model files exist on disk
(`msft_chart_model.keras` etc.) but are deliberately left out of
`SUPPORTED_SYMBOLS`, same treatment as SOL-USD. `SUPPORTED_SYMBOLS`
now has 21 symbols: the 4 live crypto, all 10 default-BIST, and 7 of
10 default-US. All 7 going live were re-verified end-to-end with real
yfinance pulls (`period="6mo"`) before committing.

A stale test caught during this step: `tests/test_main_chart_ai_symbol_gating.py`'s
"unsupported symbol is skipped" test used `"AAPL"` as its unsupported
example - which broke the moment AAPL itself went live, since the
test's premise silently became false. Fixed to use an obviously-fake
symbol literal instead of a real ticker, so it can't go stale the same
way again as `SUPPORTED_SYMBOLS` keeps growing.

This basket's lower hit rate (7/10 vs. BIST's 10/10 and crypto's 4/5)
is worth noting as a real data point rather than averaged away: the
"BIST does even better than crypto, and this basket does worse" pattern
could reflect genuine differences in exploitable short-term momentum
across markets, or could just be basket-specific noise at this sample
size (3 failures out of 10 isn't a large enough sample to separate
those two explanations) - the same caution from the ml-accuracy
research applies here: a single-digit set of symbols, each checked on
only two windows, is suggestive, not conclusive, about the underlying
market.

## Full universe expansion — the rest of BIST, US, and crypto

After the default-watchlist work above, the decision was made to
broaden the LIVE universe to the platform's full configured symbol
tables (`core/market_config.py::BIST_SYMBOLS`, `US_SYMBOLS`,
`CRYPTO_SYMBOLS`) rather than build on-demand/scheduled training
infrastructure - same methodology, just every remaining symbol in
each table. Ran as 3 parallel batches (one per market, to use the
machine's 8 cores) covering 55 remaining symbols: 24 BIST, 18 US, 13
crypto.

**6 symbols never trained at all** - yfinance can't resolve the exact
ticker string in `market_config.py`: `KOZAL.IS`, `QNBFB.IS`, `SODA.IS`
("possibly delisted; no timezone found"), `GE` ("possibly delisted;
no price data found" - plausibly stale after GE's 2024 three-way
corporate split into GE Aerospace/Vernova/HealthCare), `APT-USD`,
`MATIC-USD` ("possibly delisted; no timezone found" - MATIC rebranded
to POL in 2024, so the old ticker may no longer resolve). This is a
`market_config.py` data-quality issue, not a bug in the training
pipeline - left unfixed since correcting ticker mappings wasn't part
of this task and guessing a replacement ticker (e.g. `POL-USD` for
`MATIC-USD`) without confirming it's actually the intended asset would
be worse than leaving the gap visible.

**49 symbols successfully trained and validated. 40 went live, 9 excluded**
(same both-windows-significant bar as every symbol before):

**BIST (21 of 24 attempted, all 21 went live)** - cleanest result yet,
zero failures for the third basket running: ALBRK.IS, ARCLK.IS,
DOHOL.IS, ENKAI.IS, HALKB.IS, INDES.IS, ISCTR.IS, KRDMD.IS, LOGO.IS,
MGROS.IS, PETKM.IS, PGSUS.IS, SAHOL.IS, TCELL.IS, TOASO.IS, TTKOM.IS,
ULKER.IS, VAKBN.IS, VESTL.IS, YKBNK.IS, ZOREN.IS.

**US (17 of 18 attempted, 15 went live, 2 excluded)**: AMD, AMZN, BA,
BAC, CAT, CRM, CVX, GS, INTC, JNJ, LLY, MCD, MS, PFE, UNH LIVE. **MA
NOT live** (window 1 clearly negative, p=0.99999965). **WMT NOT live**
(window 2 flat/negative, p=0.858, despite a strong window 1).

**Crypto (11 of 13 attempted, 4 went live, 7 excluded)** - crypto's hit
rate dropped further on this wider, lower-cap/newer-listing set:
DOGE-USD, INJ-USD, LINK-USD, LTC-USD LIVE. **NOT live**: ADA-USD (both
weak/non-significant), ARB-USD (window 1 catastrophically negative,
-0.502, p=1.00 - likely too little/volatile history), AVAX-USD (window
2 negative), DOT-USD (both windows non-significant/negative), NEAR-USD
(both non-significant), OP-USD (window 1 marginal, window 2 fails),
TIA-USD (both flat/non-significant - likely too little history, it's
one of the newer listings in this set).

`SUPPORTED_SYMBOLS` now has **61 symbols**: 8 crypto, 31 BIST, 22 US.
All 40 newly-live symbols spot-checked (not exhaustively re-verified
one by one, given the volume) with real end-to-end `predict_chart_signal()`
calls across all three markets before committing.

**Pattern holding across the whole effort**: BIST has now gone 31-for-31
(10 default-watchlist + 21 more) with zero failures across three
separate batches. Crypto's hit rate keeps falling as the set widens
past the top 5 by market cap (4/5 → now 12/18 overall, with most of
today's new failures concentrated in newer/smaller-cap listings with
less price history). US sits in between (22/28 overall). This is
still not enough evidence to firmly explain *why* - more history and
possibly BIST's retail-driven trading pattern remain the leading
hypotheses from earlier in this doc - but the shape of the result
(BIST clean, crypto noisy, US in between) has now replicated across
three independent expansion rounds rather than one.

## Weekly automatic retraining — SUPPORTED_SYMBOLS becomes live state

Every decision above (promote BTC, demote SOL, promote THYAO, etc.)
was made by a human reading the numbers after a one-off training run.
To make the system actually adapt to changing market conditions
without a human reviewing every symbol every week, a scheduled
retraining job needed two things that didn't exist before:

1. **A machine-checkable version of the "both windows significant"
   bar.** Added `ml.chart_model.check_window_significance(n, baseline,
   accuracy) -> (passes: bool, p_value: float)` - the exact one-sided
   binomial test used by hand throughout this whole effort, now a
   single reusable function instead of ad-hoc scratch Python each
   time. Also added `test_majority_baseline` to `train()`'s own meta
   dict (the TEST set's own baseline, not the full dataset's
   `class_distribution` that was already there) so the retraining job
   doesn't need to recompute it from the confusion matrix.

2. **A live allowlist a running server can see change without a
   restart.** `SUPPORTED_SYMBOLS` was a hardcoded Python tuple -
   editing it only ever took effect on the next deploy. Replaced the
   live-serving path with `ml.chart_model.get_supported_symbols()`,
   which reads `model_artifacts/supported_symbols.json` fresh on
   *every call* (cheap - it's a tiny file) and falls back to a frozen
   2026-10-22 snapshot (`_SUPPORTED_SYMBOLS_SNAPSHOT_2026_10_22`) if
   the file is missing or corrupt. `main.py` and tests updated to call
   the function instead of importing the old constant. The JSON file
   was bootstrapped with the current 61-symbol live set before this
   landed, so there's no gap in coverage.

**`research/retrain_chart_models.py`** (new): re-trains and
re-validates every symbol currently in `get_supported_symbols()` -
never the already-excluded ones (SOL, MSFT, GOOGL, ...), since
re-attempting those every week without being asked would be scope
creep on its own. A symbol is **demoted** (dropped from the live
allowlist) the moment either window no longer clears
`check_window_significance()` - same bar, no human in the loop. A
symbol whose retrain fails for an infrastructure reason (yfinance
fetch error) is **not** demoted - its previous live status is kept
and the failure is flagged in the run's report, matching the
"non-fatal, bounded gap" judgment already used for GS's partial news
backfill earlier in this project. Writes the updated model/scaler
files (so a change is live on the very next request, no restart),
the new `supported_symbols.json`, and a timestamped JSON report under
`model_artifacts/retrain_reports/` with the full per-symbol numbers
behind every keep/demote decision.

**Deliberately does not run `git add`/`commit`/`push`.** This script
runs unattended on a schedule with no human reviewing each run - an
automated process rewriting the shared `main` branch on its own is a
materially different risk than every other change in this project,
which a human (this session) reviewed and pushed individually. Git
operations stay a deliberate, separate step.

**Installed on `mayasoftlnx01`'s crontab the same day**, once the user
explicitly confirmed each step (this is the live production host, so
every step here was deliberate, not something done unprompted):

```
0 2 * * 0 cd /home/mayasoft/app/OptiTrade/backend/src && /home/mayasoft/app/OptiTrade/venv/bin/python -m research.retrain_chart_models >> /opt/algorix/logs/optitrade-retrain-cron.log 2>&1
```

(Sundays 02:00 server time - weekly, chosen over daily since one
day's new data barely moves a model trained on years of history, and
over monthly given the "adapt to current market conditions" framing
behind this whole feature. Points at the main checkout
`/home/mayasoft/app/OptiTrade`, not the ephemeral worktree this
session was running in - the worktree can be cleaned up without
breaking the schedule.)

Getting the cron job to have any real effect required two more fixes,
both now in place and verified:

1. **The main checkout was ~30+ commits stale** (this session's
   worktree-isolation sandbox can't run `git pull` in the shared
   checkout - a known limitation, see the git-worktrees deployment
   note in memory). The user ran `git pull --ff-only origin main`
   there directly from their own terminal, bringing it fully current
   - confirmed after by diffing `main.py` between the worktree and the
   checkout (identical) and counting `model_artifacts/` (226 files in
   both).

2. **`model_artifacts/` was never actually live for the running
   container.** Production runs the `api` service from a Docker image
   built via `COPY . .` at image-build time - with no volume mount,
   anything `retrain_chart_models.py` wrote to the host's
   `backend/model_artifacts/` would never reach the already-running
   container, contradicting this doc's own "no restart needed" claim.
   Added a bind mount to `docker-compose.yml`:
   `./backend/model_artifacts:/app/model_artifacts` (container path
   confirmed from the Dockerfile's `WORKDIR /app` + `COPY . .`, then
   `WORKDIR /app/src` for runtime - so `ml/chart_model.py`'s own
   `BACKEND_DIR` computation resolves to `/app`). Verified live: wrote
   a probe value to the host's `supported_symbols.json` and confirmed
   `docker exec optitrade-api cat /app/model_artifacts/supported_symbols.json`
   reflected it immediately, no restart - then restored the real
   61-symbol file and reconfirmed.

   Restarting to apply the compose change caused a real (brief)
   production incident, and surfaced a pre-existing inconsistency in
   this project's own documentation: the restart command used `docker
   compose -f docker-compose.yml up -d --build api --no-deps` - the
   explicit `-f` flag suppresses Compose's normal auto-merge of
   `docker-compose.override.yml`. That file is what actually publishes
   port 8000 to `127.0.0.1` (the base file alone only `expose`s it,
   internal-network-only) - which the host's system nginx depends on
   to reach the container at all (per the deployment-topology memory:
   nginx proxies to `127.0.0.1:8000`). Dropping that binding 502'd
   `https://algorixstudio.com/optitrade/api/health` for a few minutes,
   fixed by re-running `docker compose up -d --build api --no-deps`
   **without** `-f`, letting Compose auto-merge both files by default
   again.

   **This means `docker-compose.override.yml`'s own header comment -
   "Production deployment must NOT include this file ... so the API
   stay off any public interface" - does not match how production
   actually runs.** The live site only works *because* that file's
   port-publish is merged in; this session didn't create that
   dependency, just tripped over it by explicitly passing `-f` and
   accidentally removing it. Flagging here rather than "fixing" either
   side unprompted: someone should eventually either update that
   file's header to reflect reality, or move the production-needed
   part of its config (the loopback port publish nginx depends on)
   into `docker-compose.yml` itself and trim the override file down to
   genuinely dev-only additions. Until then: any future rebuild of
   `api` on this host should omit `-f` entirely (the default merge),
   not add it.

**Verified end-to-end** (not a full 61-symbol run - that takes ~1-1.5h
and wasn't necessary to prove the mechanism): called the script's
`_check_symbol("BTC-USD")` directly. It retrained BTC-USD fresh,
revalidated it, and correctly returned `{"status": "kept", "window1":
{"passes": true, "p_value": 0.0014}, "window2": {"passes": true,
"p_value": 0.0}}` - matching the live decision already on record for
BTC. Caught and fixed one real bug in the process: `scipy.stats.binomtest`
rejects a numpy `int64`/`float64` for its sample-size argument
outright ("n must be an integer") - `check_window_significance` now
explicitly coerces `n`/`k` to plain Python `int` before calling it,
since `retrain_chart_models.py` sums `classification_report`'s
numpy-typed `support` values into that argument.

## Live scan check: does chart AI's disagreement with decision_engine hold up?

With 61 live symbols, a natural question is how often chart AI's
signal actually disagrees with decision_engine's own output, and
whether any such disagreement reflects something real. A live
market-opportunities scan on 2026-10-22 (all three markets) found:

- Only **5 of 61** checked symbols genuinely agree in direction (both
  BUY or both SELL) between decision_engine and chart AI.
- **11 directly conflict** (one says BUY, the other SELL) - e.g.
  `SISE.IS`, `ALBRK.IS`, `CRM`, `AMZN`, `ASELS.IS`, `THYAO.IS`,
  `TTKOM.IS`, `AKBNK.IS`, `ISCTR.IS`, `SAHOL.IS` (chart AI SELL,
  decision_engine BUY), and `LOGO.IS` (the one reverse case).
- **21 more** have decision_engine at HOLD while chart AI holds a
  confident opinion (`>55%`), overwhelmingly SELL (17 of 21).

**Root cause, traced through the three direct-conflict examples with
the highest chart AI confidence** (`SISE.IS`, `ALBRK.IS`, `CRM`): in
every case, decision_engine's BUY call is driven almost entirely by
`FundamentalEngine`'s cheap-valuation thesis. `TechnicalEngine`'s own
evidence already shows real bearish momentum (`SISE.IS`: "8.4% below
EMA20 - bearish trend... MACD below signal... oversold") but either
(a) still votes BUY itself, reading "oversold" as an implicit "bounce
coming" signal, or (b) votes HOLD without that assumption changing
decision_engine's overall BUY. Chart AI, trained on actual outcomes
rather than a hand-coded "oversold → bounce" rule, disagrees with that
assumption specifically.

**Checking the "oversold → bounce" assumption at scale**: broadening
beyond the 3 examples to every BIST symbol where `TechnicalEngine`'s
own evidence says "oversold" (27 symbols, not filtered to any
particular overall decision) found chart AI calling SELL on 16/26
(62%) with a live model, BUY on only 4/26 (15%, often lower
confidence), NEUTRAL on 6/26.

**Then the real test - not what any model predicts live, but what
actually happened historically**: `research/backtest_oversold_regime.py`
pools each of those 26 symbols' own held-out test split (never trained
on, same chronological boundaries `train()` itself uses), flags
"oversold" days (raw RSI<30 or Bollinger %B≈0, using the model's own
pre-scaling features), and reports the TRUE 5-day-later outcome -
1,290 pooled real instances:

| | Rate |
|---|---|
| Actually SELL 5 days later | **30.8%** |
| Actually NEUTRAL | 39.6-39.8% |
| Actually BUY ("the bounce") | **29.5-29.6%** |

**The "oversold implies a bounce" assumption is not supported by this
data** - a decline is, if anything, very slightly *more* likely than a
bounce following an oversold reading in this BIST basket, not less.
`TechnicalEngine`'s implicit heuristic has no real edge here.

**Chart AI's own accuracy on this exact held-out oversold subset:
56.1-56.3%**, against a 39.6-39.8% ceiling from the best naive
strategy (always guess the majority class) - binomial test
`p≈3-4×10⁻³²` at n=1,290. This is a genuine, statistically solid
result specific to the hardest/most ambiguous regime (not an easy
subset where any model would look good by default): chart AI has real
discriminating skill exactly where decision_engine's rule-based
Technical heuristic has none, on a sample far larger than any single
day's live scan could provide.

**Same check, all three markets.** `backtest_oversold_regime.py` was
generalized (`--market {BIST,US,CRYPTO}`, reading the market's full
currently-live chart-AI symbol set from `get_supported_symbols()`
rather than a hand-picked list) and re-run on US (22 symbols) and
CRYPTO (8 symbols):

| Market | Pooled n | Actual SELL | Actual NEUTRAL | Actual BUY | Model accuracy | Baseline | p-value |
|---|---|---|---|---|---|---|---|
| BIST | 1,290 | 30.8% | 39.6% | 29.6% | 56.1% | 39.6% | 3×10⁻³² |
| US | 2,630 | 25.6% | 53.7% | 20.7% | **71.8%** | 53.7% | 9.6×10⁻⁸¹ |
| CRYPTO | 279 | **44.1%** | 36.2% | 19.7% | 50.9% | 44.1% | 1.3×10⁻² |

**The "oversold implies a bounce" assumption fails in every market** -
actual SELL rate exceeds actual BUY rate in all three, not just BIST.
The *degree* differs sharply: CRYPTO shows the starkest anti-bounce
skew (SELL 2.2x more likely than BUY - consistent with crypto's
reputation for trend continuation over mean reversion), BIST is
closest to a coin flip, US sits in between with the majority of
outcomes landing NEUTRAL (lower realized volatility than the other
two).

**Chart AI's edge over the naive baseline also varies by market**:
largest and most statistically overwhelming in US (+18.1 points,
p≈10⁻⁸⁰, also the largest pooled sample), solid in BIST (+16.5
points, p≈10⁻³²), and more marginal in CRYPTO (+6.5-6.8 points) -
significant, but on by far the smallest sample of the three.

**CRYPTO re-run with roughly double the sample.** Added
`--include-window2` to `backtest_oversold_regime.py`: for each symbol,
also trains a SECOND model on window 1's former train block and
evaluates it on window 1's former val block (mirrors
`validate_chart_model_window2.py`'s exact split - zero overlap with
window 1's own test block), pooling both windows' oversold subsets
together. Worth doing specifically for CRYPTO, whose symbols have far
less price history than BIST/US, so window 1's test split alone gives
a thin subset per symbol:

| | n=279 (window 1 only) | n=569 (window 1 + 2) |
|---|---|---|
| Actual SELL | 44.1% | 44.5% |
| Actual NEUTRAL | 36.2% | 30.2% |
| Actual BUY | 19.7% | 25.3% |
| Model accuracy | 50.9% | 51.0% |
| Majority baseline | 44.1% | 44.6% |
| p-value | 0.013 | **0.0011** |

The pattern holds under a near-doubled sample, and the p-value drops
by more than an order of magnitude - CRYPTO's result is no longer the
comparatively marginal one of the three; it's now on statistical
footing comparable to BIST and US.

## Known follow-up, not fixed here (out of today's scope)

`_try_load_base_model()` / `transfer_train()`'s "continual training"
and "transfer learning" claims are currently dead code in practice:
`train()` loads the existing model via `_try_load_base_model()` but
never actually uses the loaded weights - it always calls `build_model()`
fresh and, for `freeze_cnn_for_transfer`, freezes the first 5 layers of
that *freshly initialized* (not pretrained) model. True transfer
learning would need to copy the base model's trained CNN weights into
the new model before freezing them. Not fixed in this session since it
wasn't part of today's BTC-training task and doesn't affect the
already-trained BTC model's correctness.
