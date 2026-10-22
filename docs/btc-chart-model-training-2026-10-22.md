# BTC Chart AI Model — Fix, Training, and Second-Window Validation (2026-10-22)

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
