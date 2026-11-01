# S&P 500 US Market Universe — Design Spec

**Goal:** the "US" market tab (search, watchlist, sector overview, news
entity matching, and the Market page's "Top opportunities" scanner)
should cover the real S&P 500 constituents, not the current curated
28-symbol list — dynamically sourced, so it stays current as the index
changes, without a new paid dependency.

## Context

`core/market_config.py::US_SYMBOLS` is a hardcoded, 28-symbol dict used
by: `main.py` (search/watchlist/`/market/list`/opportunities scanning),
`core/news_analyzer.py` and `news/entity_extraction.py` (symbol-name
lookup for news text), and several one-off research backfill scripts
under `scripts/`. Labeling this list "US" when it's a fraction of the
real S&P 500 is misleading (surfaced during this session's work on the
Market page's opportunity picker).

`ml/chart_model.py`'s chart-AI model has its OWN, fully independent
live-symbol allowlist (`get_supported_symbols()`, reading
`model_artifacts/supported_symbols.json`) — it does not import
`US_SYMBOLS` at all (only mentions it in a historical comment
explaining where its frozen 2026-10-22 snapshot's symbols came from).
This design does not touch that mechanism.

`core/market_config.py::get_default_watchlist("US")` is a separate,
already-small hardcoded 10-symbol "suggested starter watchlist" —
unrelated to the full-universe list this design replaces, and stays
unchanged.

## Design

### 1. Data source and refresh

New function `core/market_config.py::get_us_symbols() -> Dict[str, str]`
(symbol → company name), mirroring `ml.chart_model.get_supported_
symbols()`'s own proven pattern exactly:

- Reads `model_artifacts/sp500_symbols.json` fresh on every call (no
  network call on the request path).
- Falls back to a frozen snapshot (`_SP500_SYMBOLS_SNAPSHOT_2026_11_01`,
  a tuple of (symbol, name) pairs captured at implementation time) if
  the file is missing, corrupt, or empty.

New background loop `sp500_refresh_loop()` (`main.py`, same shape as
`market_opportunities_refresh_loop`): once every 24h, fetches the
Wikipedia "List of S&P 500 companies" constituent table via
`pandas.read_html` (network call, `lxml` already a dependency),
normalizes tickers from Wikipedia's dot-notation for dual-class
shares (e.g. `BRK.B`) to yfinance's own hyphen convention (`BRK-B`),
and writes the result to
`model_artifacts/sp500_symbols.json`. On fetch/parse failure: log and
keep the existing cached file untouched (same "infrastructure failure
never demotes/destroys good data" principle as
`research/retrain_chart_models.py`). Not git-committed automatically —
the file is `model_artifacts/`-local, same as `supported_symbols.json`.

### 2. Propagation

`US_SYMBOLS` the module-level dict is removed. Every live call site
switches to calling `get_us_symbols()`:

- `main.py`: `get_symbols_for_market("US")`, `market_list`, search/
  watchlist endpoints — already call `get_symbols_for_market`/
  `get_default_watchlist` as functions (no call-site signature change,
  `get_symbols_for_market` internally calls `get_us_symbols()` instead
  of referencing the dict).
- `core/news_analyzer.py:396-397` and `news/entity_extraction.py:20,35`:
  currently `from core.market_config import US_SYMBOLS` at module
  import time (a stale snapshot for the process's whole lifetime) —
  both change to calling `get_us_symbols()` at use time instead.

**Research scripts stay pinned.** `scripts/backfill_sec_fundamentals.py`,
`scripts/backfill_feature_store.py`, `scripts/backfill_news_features.py`,
`scripts/train_ml_candidate_us_news*.py`, `scripts/train_ml_candidate_
us_fundamentals.py` each get a local, frozen copy of the *original*
28-symbol dict (inlined as `_ORIGINAL_US_SYMBOLS_28` in each script, or
one shared constant in a scripts-only module) instead of importing the
now-dynamic `get_us_symbols()`. These scripts already ran once against
that exact 28-symbol universe; silently widening their universe on a
future re-run would make already-published research results
non-reproducible.

**Chart-AI stays explicitly out of scope.** Chart-AI's own
`get_supported_symbols()` allowlist does not change. A newly-visible US
symbol with no trained chart-AI model simply gets `chart_ai: None` on
`/quant/analyze` — the existing, already-tested fallback behavior.
Training chart-AI for more US symbols remains a separate, manually
reviewed process (train → validate on two windows → edit
`supported_symbols.json`), unchanged by this work.

### 3. Opportunities-scanner performance

`intelligence.market_scanner.MarketScannerConfig.max_parallel_symbols`
defaults to 3 (deliberately conservative — each scanned symbol is
already a full, internally-parallel `PipelineService.run()` call). At
that concurrency, scanning ~500 US symbols takes roughly 28 minutes in
the best case (500 ÷ 3 × ~10s/symbol observed in this session for a
healthy run) — before any FundamentalEngine/NewsEngine timeouts, which
this session's own production logs show do happen. The existing 300s
(5-minute) `market_opportunities_refresh_loop` interval cannot
physically complete a 500-symbol scan before the next tick fires.

- `market_opportunities_refresh_loop` (`main.py:594`) keeps its
  existing 300s sleep and keeps refreshing TR/CRYPTO every tick, but
  gates US behind a tick counter so US refreshes only every 6th tick
  (30 minutes).
- A new, separate `MarketScannerConfig` instance (`max_parallel_symbols
  =10`) is used only for the US opportunities scan — TR/CRYPTO's
  scanner keeps the existing default-3 instance untouched (their
  universes are small enough that 3 is fine, and there's no reason to
  add load to engines serving other markets).
- The US scan continues to run inside the existing
  `_HEAVY_BACKGROUND_SCAN_LOCK`, same as today — chosen deliberately:
  this lock exists because of a real production incident
  (2026-10-12) where concurrent heavy scans starved each other. A
  longer US scan (~15-20 minutes at the new concurrency) means other
  heavy refreshes (dashboard, sector overview) skip their tick during
  that window, once every 30 minutes — an accepted tradeoff, not a
  silent regression.

## Testing

- `get_us_symbols()`: reads a real cache file, falls back to the
  frozen snapshot on missing/corrupt file (mirrors `ml/chart_model.py`'s
  own existing tests for `get_supported_symbols()` exactly).
- `sp500_refresh_loop`: a fake Wikipedia-table fetch function,
  confirming the cache file is written on success and left untouched
  on failure (mirrors `research/retrain_chart_models.py`'s "infra
  failure never destroys good data" test pattern).
- `news_analyzer`/`entity_extraction`: confirm they resolve a symbol
  added only to the new dynamic list (not in the original 28), proving
  they no longer read a frozen import-time snapshot.
- `market_opportunities_refresh_loop`: confirm US is skipped on
  non-multiple-of-6 ticks and refreshed on the 6th, while TR/CRYPTO
  refresh every tick (extends this session's own
  `test_main_background_scan_loops.py`).
- Research scripts: a lightweight test per script confirming its own
  local constant still has exactly the original 28 symbols (a
  regression guard against someone "helpfully" switching a script back
  to the dynamic function later).

## Review Focus

- A symbol present in the new S&P 500 list but with no live chart-AI
  model must render `chart_ai: None` on the asset detail page exactly
  like today's MSFT case — not an error.
- `get_us_symbols()`'s frozen fallback snapshot must still let the app
  start and serve a reasonable (if stale) US universe on a completely
  fresh deployment with no `sp500_symbols.json` yet written.
- A ticker Wikipedia lists with a different punctuation convention than
  yfinance expects (e.g. `BRK.B` vs `BRK-B`) must not silently produce
  an unfetchable symbol with no indication anywhere that it's broken —
  at minimum logged the same way chart-AI's own 6 known-stale tickers
  are already surfaced.
- The 6-tick US gate must not also delay TR/CRYPTO — both still refresh
  every 300s tick exactly as today.
- Re-running one of the pinned research scripts today must produce the
  identical 28-symbol universe it used originally, not the new ~500.

## Out of scope

- Chart-AI training/validation for any of the ~472 newly-visible US
  symbols (separate, manual process, unaffected by this work).
- `get_default_watchlist("US")` (the small hardcoded starter list) —
  unrelated, unchanged.
- Any change to BIST or Crypto's own symbol universes or scan cadence.
- A UI affordance for browsing/filtering the full ~500-symbol list
  beyond what `SymbolSearch`'s existing type-ahead already does.
