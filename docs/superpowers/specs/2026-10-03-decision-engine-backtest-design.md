# decision_engine Point-in-Time Backtest — Design

## Mission

Measure, for the first time ever, how accurate `decision_engine`'s real live decision logic actually is — not a separate ML model's accuracy, the actual BUY/SELL/HOLD/confidence output the live app would have produced. This is the first sub-project of a larger "model-based development, focus on accuracy" initiative; a later sub-project will act on what this measurement reveals, and a further one will redesign the web frontend around whatever the recommendation surface becomes.

## Current State

`decision_engine.service.DecisionEngine.decide(symbol: str, strict: bool = False) -> DecisionOutput` has no point-in-time parameter — it always reads "now" at every layer:

- `decide()` → `engine.vote(symbol)` for every registered engine (`VotingEngineProtocol.vote(self, symbol: str) -> EngineVote`, `decision_engine/interfaces.py`).
- Technical engine: `vote()` → `analyze(symbol)` → `TechnicalFeatureAdapter.get_features(symbol)` → `resolve_features(...)`, which calls `feature_store.get_latest_feature(symbol, name)` (live-only) and, on a cache miss, `_compute_all(symbol)` → `fetch_history(symbol, period=...)` (always "now") + a fresh `write_feature()`.
- The point-in-time-capable method already exists and is unused by this chain: `FeatureStoreService.get_feature_as_of(symbol, feature_name, as_of, respect_ingestion_time=False)` → `PostgresOfflineStore.get_as_of(...)`.

No ML model (legacy, v2, or the new `ml_training` candidate) currently beats its naive majority-class baseline out-of-sample — but none of them drive `decision_engine`'s actual decisions either (confirmed earlier this session: `xgb_signal_model` only feeds a secondary `ml_confidence` display field; `v2_xgb_model` only feeds `v2/api/router.py`'s separate `ml_prediction` field). `decision_engine` itself, the real live decision authority (Technical + Fundamental + News voting engines), has never had its own accuracy measured at all.

**Fundamental and News engines cannot be included in a genuine historical backtest with current data sources** (investigated this session, see Risks for detail): Fundamental's majority feature set comes from yfinance `.info`, a current-only snapshot with no historical query capability; its statement-derived minority is only a short trailing window of current-vintage annual data, not true point-in-time/restatement-free history. News's entire feature set comes from yfinance's live news feed only, with no historical archive query capability (the one `NEWS_API_KEY`/newsapi.org reference in `.env.example` is dead code, read by nothing). Both engines ARE already Feature-Store-aware going forward (they persist current values on every live call), so real historical data for them will accumulate naturally over time — but genuine *retroactive* backfill, the way Technical's 2-year history was backfilled, is not feasible without integrating a new (likely paid) data vendor, which is out of scope for this sub-project.

## Scope: Technical-only backtest

This backtest measures `decision_engine`'s decision quality using **only the Technical voting engine** — an honest, clearly-labeled approximation of the real 3-engine live decision, not a claim of measuring the full live decision. The real 2-year, 22-symbol (15 BIST equities + 7 crypto) Feature Store backfill already done this session is what makes this possible today.

## Architecture

**`as_of` threaded through the real `decide()` call chain, not reimplemented separately.** This reuses the actual live code for the historical replay, so there's no second implementation to drift from what production actually does over time (the exact "duplicated logic" pattern that caused a real bug earlier in this project, when a hand-copied feature extractor silently diverged from the original).

1. `decision_engine/interfaces.py::VotingEngineProtocol.vote(self, symbol: str, as_of: Optional[datetime] = None) -> EngineVote` — Protocol gains an optional parameter, defaulting to `None` (current behavior, unchanged for every existing caller).
2. `decision_engine/service.py::DecisionEngine.decide(self, symbol: str, strict: bool = False, as_of: Optional[datetime] = None) -> DecisionOutput` — threads `as_of` through `_collect_valid_votes` to every `engine.vote(symbol, as_of=as_of)` call.
3. All three concrete engines (Technical/Fundamental/News) gain the `as_of` parameter on `vote()`/`analyze()`, for Protocol consistency — **only Technical's implementation actually uses it**; Fundamental and News accept and ignore it (their data is unavoidably live-only today; this keeps one uniform Protocol signature rather than special-casing Technical).
4. `engines/technical/feature_adapter.py::TechnicalFeatureAdapter.get_features(self, symbol: str, as_of: Optional[datetime] = None) -> FeatureResolution` — when `as_of` is given, bypasses the live `resolve_features`/`_compute_all` path entirely (compute-fresh-on-miss is meaningless for a historical date) and instead calls a new `_resolve_as_of(symbol, as_of)` that queries `feature_store.get_feature_as_of(symbol, name, as_of, respect_ingestion_time=True)` for each of `ALL_FEATURE_NAMES` — `respect_ingestion_time=True` is the leakage guard already established this session, ensuring a feature isn't visible to a replay `as_of` a date before it was actually known/ingested. Missing data stays missing (no live-compute fallback), the same way Fundamental's existing analyzers already skip absent tiers.
5. A Technical-only `DecisionEngine` instance for the backtest, constructed via the existing test pattern (`VotingEngineRegistry()` + `.register(technical_engine_instance)` + `DecisionEngine(registry=...)`) — **not** `get_default_decision_engine()`'s singleton, which registers all three engines by design.
6. New `backend/src/scripts/backtest_decision_engine.py`: for each trading day in the already-backfilled 2-year window, for each of the 22 symbols, calls `decide(symbol, as_of=day)` against the Technical-only engine, compares the decision's directional implication against the realized forward return using the SAME convention already established in this project's ML evaluation scripts (`FORWARD_DAYS=5`, `THRESHOLD_UP_PCT=1.0`, for direct comparability with the existing ML accuracy reports), and writes a report with accuracy/precision/recall vs. a naive majority-class baseline — explicitly, repeatedly labeled "Technical-engine-only decision_engine backtest — not the full 3-engine live decision" everywhere it's presented.

## Side-effect isolation: no persistence during replay

`decide()` currently calls `self._persist(output)` unconditionally, writing every decision to `decision_engine_executions`. A full backtest run is roughly 2 years × 22 symbols ≈ 16,000 `decide()` calls — persisting all of them would pollute the live monitoring table with thousands of synthetic historical-replay rows alongside real live decisions. **When `as_of` is provided, `decide()` skips `self._persist(output)` entirely.** This matches the "historical replay must have zero live-system side effects" principle already established for the Feature Store backfill (which only ever reads via `get_as_of`, never touches the online cache). Live calls (`as_of=None`, the default) are completely unaffected — persistence behavior there doesn't change at all.

## Data Flow

```
backtest_decision_engine.py
  for day in trading_days(2024-10-02 .. 2026-10-02):
    for symbol in SYMBOLS (22):
      decide(symbol, as_of=day)                      # Technical-only registry
        -> TechnicalEngine.vote(symbol, as_of=day)
          -> TechnicalEngine.analyze(symbol, as_of=day)
            -> feature_adapter.get_features(symbol, as_of=day)
              -> feature_store.get_feature_as_of(symbol, name, day, respect_ingestion_time=True)
                 (per feature, x17)
        -> DecisionOutput (decision, confidence, data_sufficiency, NOT persisted)
      compare DecisionOutput's directional implication vs. realized return[day -> day+5]
  -> accuracy / precision / recall / majority_baseline, honestly reported either way
```

## Error Handling

Matches this project's established conventions (`evaluate_model_accuracy.py`, `backfill_feature_store.py`): per-symbol and per-day try/except, log and skip rather than aborting the whole run. A day/symbol with `data_sufficiency` below a reasonable floor (e.g., the Technical engine's own vote wasn't collected at all — `votes` empty) is recorded as a skip, not a forced HOLD; the report states how many day/symbol pairs were skipped and why, honestly, the same way the ML evaluation reports already disclose their own sample-size caveats.

## Testing

- Regression test: `decide(symbol)` (no `as_of`, or `as_of=None` explicitly) behaves byte-for-byte identically to today's current behavior — same votes collected, same persistence call made. This is the single most important test in this whole change: it must be impossible for this feature to alter any live decision path.
- Unit test: `TechnicalFeatureAdapter.get_features(symbol, as_of=<date>)` calls `get_feature_as_of` with `respect_ingestion_time=True` for every one of `ALL_FEATURE_NAMES`, and never calls `get_latest_feature` or `_compute_all` when `as_of` is given.
- Unit test: `decide(symbol, as_of=<date>)` does NOT call `self._persist`, using a fake execution repository to assert zero writes — while `decide(symbol)` (no `as_of`) still does, unchanged.
- Unit test: Fundamental/News fake engines confirm their `vote()` accepts `as_of` without error and ignores it (same output with or without it).
- Backtest script's own core loop (day iteration, direction-labeling, accuracy/baseline math) tested with fakes, matching the pattern already used in `test_backfill_feature_store.py`/the ML eval scripts' own test coverage.

## Global Constraints

- Every commit ends with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Zero change to any existing caller's behavior: every current call site of `decide()`/`vote()`/`analyze()`/`get_features()` omits `as_of`, and must continue behaving exactly as today.
- `as_of` replay must never call `self._persist()` — zero rows written to `decision_engine_executions` for historical replay.
- Fundamental and News engines are NOT backfilled or made historically aware in this sub-project — they gain the `as_of` parameter for Protocol consistency only, and are excluded from the backtest's own engine registry entirely (not registered, not voted).
- `respect_ingestion_time=True` on every historical feature read — this is the leakage guard; a value must not be visible to a replay dated before it was actually known/ingested.
- Report the real result honestly, whatever it is — this is exactly the kind of measurement where an unfavorable finding (decision_engine's Technical-only historical accuracy is also no better than chance) is a legitimate, valuable, and acceptable outcome, consistent with how every ML evaluation in this project has been reported so far.
- `FORWARD_DAYS=5`, `THRESHOLD_UP_PCT=1.0` for the backtest's own direction-labeling — matching the existing ML evaluation scripts' convention, for direct comparability.
- Reuse the real `decide()`/engine code for the replay — no parallel reimplementation of Technical's voting or aggregation logic.

## Out of Scope

- Fundamental/News historical backfill or inclusion in the backtest (infeasible with current data sources, a separate future decision pending on a paid data vendor).
- Any ML model fine-tuning or retraining — this sub-project is purely a measurement capability for `decision_engine` itself.
- SHADOW/ACTIVE promotion of anything — not applicable here, there's no model being registered.
- Acting on the backtest's findings (e.g., retuning engine weights, redesigning the Technical engine's logic) — that's a follow-up decision made AFTER this measurement exists, not part of building the measurement tool itself.
- The web frontend redesign the user mentioned as a later phase — a separate, later sub-project with its own brainstorming cycle.

## Risks

- **`respect_ingestion_time=True` could return `None` for many (symbol, day, feature) combinations if the backfill's `ingestion_timestamp` values don't cleanly support this query pattern at scale** — mitigated by the fact this exact flag and this exact backfilled data were already used successfully for the `ml_training` candidate's own out-of-sample evaluation earlier this session (same data, same query pattern, already proven to work).
- **Protocol signature change touches 3 concrete engines plus every test fake implementing `VotingEngineProtocol`** (`FakeVotingEngine` in `test_decision_engine_service.py`, and likely similar fakes elsewhere) — every one needs updating to accept (even if ignoring) the new parameter, or the Protocol's structural check could start failing them. The implementation plan must find and update every fake, not just the 3 real engines.
- **The Technical-only approximation may systematically differ from what the real 3-engine decision would have been** — this is a known, named, accepted limitation (see Scope section), not a flaw in the backtest's execution; the report must state this prominently every time results are presented, not just once in a footnote.
- **A ~16,000-call backtest run is a real, possibly multi-minutes-to-tens-of-minutes operation against the real production Feature Store** (read-only, no writes given the persistence skip) — should be run in the background with patient polling, matching this project's established pattern for long-running real operations.
