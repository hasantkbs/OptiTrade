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

**Not yet wired into `main.py`.** The BTC gate (`result.symbol ==
MODEL_SYMBOL`) is a single-symbol check - extending it to cover ETH
too (and whatever future symbols get trained) needs its own small
change (a supported-symbols set/dict instead of one constant) and is
a separate decision from training/validating ETH itself.

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
