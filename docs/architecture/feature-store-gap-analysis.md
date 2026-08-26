# Feature Store Gap Analysis

Date: 2026-07-27
Status: Analysis only — no code changed, no architecture altered.

## Purpose

Sprint 1 (Repository Refactoring) is complete: the backend is now protected
by characterization tests, `core/interfaces.py` Protocols, a
production/research boundary, structured logging, and improved typing —
all behavior-preserving.

This document inspects the **current** backend against the approved Phase 2
direction — a minimal Feature Store (versioning, point-in-time correctness,
validation, Redis online store, PostgreSQL offline store; see
`docs/architecture/gap-analysis.md` section 3) — across eight specific
areas. It is a factual snapshot, not a design. No solutions are proposed;
each section only records what exists today, what's missing, the risks of
that gap, what it depends on, and — narrowly, per section — a suggested
order for closing that section's gap relative to the others.

## Method

Every claim below is grounded in direct inspection of this exact
repository state (post-Sprint-1), not carried over unverified from the
Phase 1 gap analysis. Re-checked in this pass: `backend/requirements.txt`,
`docker-compose.yml`, a repo-wide grep for `redis`/`postgres`/`psycopg`/
`sqlalchemy`/`sqlite3`, `backend/data/fetcher.py`,
`backend/core/regime_scanner.py`, `backend/core/mtf_analyzer.py`,
`backend/core/news_analyzer.py`, `backend/core/sector_intelligence.py`,
`backend/core/cache_manager.py`, `backend/core/indicators.py`,
`backend/core/pattern_scanner.py`, `backend/models/schemas.py`,
`backend/v2/models/schemas.py`, `backend/core/risk_manager.py`,
`backend/core/regime_scanner.py`'s `ScannedSymbol`,
`backend/core/ai_trader_persona.py`'s `TradeRecommendation`,
`backend/core/ml_predictor.py`, `backend/research/ml_trainer.py`,
`backend/research/train_v2.py`, `backend/research/train_chart_model.py`,
`backend/ml/chart_model.py`, `backend/v2/ml/predictor.py`, and
`backend/main.py`.

---

## 1. Current data flow

### Current implementation
There is no single data flow — three parallel paths each pull, transform,
and score data independently (this mirrors the three-decision-path finding
in `gap-analysis.md` section 1, but the duplication starts one layer
earlier, at data acquisition):
- **Legacy v1** (`core/analyzer.py`): `data/fetcher.fetch_history()` →
  `core/indicators.py` functions → `core/scoring.compute_score()` →
  `core/ml_predictor.get_ml_confidence()` (annotation only) → `AnalysisResult`.
- **Hybrid** (`core/hybrid_engine.py`): `core/regime_scanner.py` (its own
  `yf.download()` batch call) → `core/mtf_analyzer.py` (its own
  `yf.Ticker().history()` calls + `pandas_ta` + `core/pattern_scanner.py`)
  → `core/risk_manager.py` → `core/ai_trader_persona.py` (Groq LLM) →
  `TradeRecommendation`.
- **v2** (`v2/api/router.py`): its own `yf.Ticker().history()` call →
  `v2/core/engine.py`'s `TradingEngineV2` → `v2/indicators/*` → `EngineResult`.

Each path fetches its own data independently from Yahoo Finance, computes
its own features independently, and produces its own result shape
independently. Nothing is shared between them at any stage.

### Missing capabilities
- No single, canonical data-flow path from "raw market data" to "features"
  to "decision" — there are three, and a Feature Store would need to sit
  in front of all three or become the reason they converge.
- No point-in-time guarantee anywhere: every path fetches "whatever
  Yahoo Finance returns right now" and computes features from it
  immediately; nothing records what data was actually seen for a given
  decision, so no decision is reproducible after the fact.

### Technical risks
- Three independent fetch-and-compute paths reading the same underlying
  market data (BTC-USD's daily closes, for example) can and do observe
  slightly different data at slightly different moments, so the "same"
  symbol can carry a different regime/score/signal in the v1, hybrid, and
  v2 responses simultaneously depending on which endpoint was called and
  when — already a real, verifiable inconsistency risk within the current
  system, before a Feature Store is even introduced.
- Introducing a Feature Store in front of only one of the three paths
  (the most likely realistic Sprint 2 scope) leaves the other two reading
  live, ungoverned data — a partial migration that must be tracked
  explicitly or it will look like the Feature Store "isn't working" for
  two-thirds of the API surface.

### Dependencies
- Depends on the Decision Engine consolidation work being sequenced
  (`gap-analysis.md`'s suggested order already lists Feature Store before
  Decision Engine) — but the reverse dependency also holds: knowing which
  of the three paths the Feature Store must serve first requires knowing
  which one survives the eventual Decision Engine consolidation.

### Recommended implementation order (this section only)
Establish the Feature Store against **one** path first — the hybrid engine
is the newest, best-tested (Task 6 already added `core/interfaces.py`
Protocols for it), and least duplicative internally — before attempting to
unify all three fetch patterns into it.

---

## 2. Existing market data pipeline

### Current implementation
- `backend/data/fetcher.py`: `fetch_history(symbol, period)` →
  `yfinance.Ticker(symbol).history(period=period)`, synchronous, one
  symbol at a time, no persistence. Also `fetch_info`, `fetch_bist100_volume`,
  `get_balance_status` (uses `yf.Ticker(...).info`).
- `core/regime_scanner.py::_fetch_batch_history`: a *different* call
  shape — `yf.download(tickers=" ".join(symbols), period=..., interval="1d",
  group_by="ticker", threads=True)` — a genuine multi-symbol batch fetch,
  not used anywhere else in the codebase.
- `core/mtf_analyzer.py::_fetch`: yet another call shape —
  `yf.Ticker(symbol).history(period=..., interval=...)`, called twice per
  symbol per `analyze()` (once for the macro 1D/1W timeframe, once for the
  micro 1H timeframe) — 2 live network calls per symbol, every time,
  regardless of how recently the same symbol was analyzed elsewhere.
- `v2/api/router.py` and `v2/core/backtest_engine.py` each call
  `yf.Ticker(...).history(...)` independently again.

### Missing capabilities
- No shared data-access layer of any kind — four distinct call sites, at
  least three distinct calling conventions (`fetch_history`'s single-ticker
  `.history()`, `regime_scanner`'s batch `yf.download()`, `mtf_analyzer`'s
  per-timeframe `.history()`), all hitting the same external API
  independently.
- No persistence: every fetch is transient, in-memory, discarded after use.
- No request deduplication: two different engines analyzing the same
  symbol in the same second each make their own independent network calls.
- No retry/backoff policy anywhere visible in any of the four call sites
  (each either lets the exception propagate or catches it broadly and
  returns `None`/empty).

### Technical risks
- Yahoo Finance rate-limiting or transient failures currently degrade each
  engine independently and silently (mostly via broad `except Exception`
  blocks returning `None`) — a Feature Store's offline store would need to
  become the buffer against this, but today there is no buffer at all.
- The regime scanner's batch download (`group_by="ticker"`) returns a
  differently-shaped DataFrame (multi-index columns) than the single-ticker
  `.history()` calls used everywhere else — any future unification of the
  fetch layer has to reconcile two genuinely different response shapes,
  not just two call signatures.

### Dependencies
- A unified fetch layer (if pursued) would need to precede or accompany
  the PostgreSQL offline store, since the offline store's ingestion path
  is exactly "fetch once, persist, serve reads from storage instead of
  re-fetching" — building the store without first knowing which of the
  three fetch shapes it standardizes on would just relocate the
  duplication rather than remove it.

### Recommended implementation order (this section only)
Before writing any offline-store ingestion code, first decide (as a
Sprint 2 design step, not part of this analysis) which single fetch
pattern becomes canonical — this is a prerequisite decision, not
something to infer from this document.

---

## 3. Current caching

### Current implementation
Three independent, in-memory, TTL-based caching implementations exist
side by side, all solving the same problem differently:
- `core/cache_manager.TTLCache` — the generic, reusable, thread-safe class
  characterized in Sprint 1 Task 3 (`docs/architecture/migration-notes.md`).
  Used today only by `core/hybrid_engine.py` (15-minute
  `TradeRecommendation` cache).
- `core/news_analyzer.py`: its own module-level `_NEWS_CACHE:
  Dict[str, Tuple[float, NewsAnalysisResult]]`, manual TTL check
  (`_CACHE_TTL = 1800`), predates `TTLCache` and was never migrated to it.
- `core/sector_intelligence.py`: its own module-level `_SECTOR_CACHE:
  Dict[str, Tuple[float, SectorResult]]`, manual TTL check
  (`_SECTOR_CACHE_TTL = 900`), same pattern, also never migrated.

`core/cache_manager.py`'s own docstring acknowledges this: it was written
to replace the news/sector ad-hoc pattern but only the *new* call site
(`hybrid_engine.py`) actually uses it — the two original ad-hoc caches it
was modeled on still exist unchanged.

### Missing capabilities
- No shared cache instance across engines: `regime_scanner.py` and
  `mtf_analyzer.py` (both hit by the hybrid engine) have **no caching at
  all** — every `HybridTradingEngine.run()` call re-fetches and
  re-computes regime/analysis data from scratch even though the
  15-minute `TradeRecommendation` cache sits one layer above them (the
  cache only short-circuits the LLM call and risk/analysis steps on a
  hit; the regime scan itself always runs live per the Task 2/6
  characterization work).
- No persistent (cross-process-restart) cache layer anywhere — every
  cache (all three implementations) is wiped on every process restart.
- No cache invalidation signal from a data source — all three are
  purely time-based, never "the underlying data actually changed."

### Technical risks
- The Redis online store (approved Phase 2 direction) is the natural
  replacement for all three of today's in-memory caches simultaneously —
  but because they have three different key shapes, three different TTLs,
  and (per the Task 3 characterization) `TTLCache` specifically cannot
  distinguish a cached `None` from a cache miss, a naive lift-and-shift of
  all three into Redis would carry that same ambiguity into the new store
  unless addressed during the migration.
- `news_analyzer.py`/`sector_intelligence.py`'s caches were never
  reconciled with `TTLCache` even after it was introduced specifically to
  replace this pattern — a sign that "introduce the better version" does
  not by itself retire the old ones; an explicit migration step is needed
  for each of the two remaining ad-hoc caches, not just for new code.

### Dependencies
- Directly downstream of "existing market data pipeline" (§2) — a Redis
  online store's value is highest once there's a single fetch path to
  populate it from; caching three uncoordinated fetch paths into one Redis
  store doesn't remove the underlying fetch duplication, only adds a
  fourth cache layer on top of it.

### Recommended implementation order (this section only)
Migrate the two still-ad-hoc caches (`news_analyzer.py`,
`sector_intelligence.py`) onto `TTLCache` first (a same-sprint-1-style,
low-risk, behavior-preserving refactor) — this consolidates three cache
implementations down to one *before* that one gets replaced by Redis,
so the Redis migration only has to reason about a single existing
in-memory contract instead of three.

---

## 4. Existing PostgreSQL usage

### Current implementation
**None.** Verified via `backend/requirements.txt` (no `psycopg2`,
`asyncpg`, `sqlalchemy`, or any Postgres driver), `docker-compose.yml`
(only the `api` service — no `postgres` service, no volume, no
connection string anywhere in the codebase), and a repo-wide grep for
`postgres`/`psycopg`/`sqlalchemy` returning zero hits in `backend/`. The
only persistent database in the entire backend is a single SQLite file,
`backend/data/monitoring.db`, managed by `core/monitoring.py`'s bare
`sqlite3` calls (predictions log + performance history — already
characterized in `gap-analysis.md` section 5; unrelated to features).

### Missing capabilities
Everything: no PostgreSQL instance, no driver dependency, no schema, no
migration tooling (no Alembic or equivalent), no connection pooling, no
offline-store table design, no historical feature snapshots of any kind.

### Technical risks
- This is genuinely new infrastructure for the project — the first
  relational, network-attached database it will have ever run. Every
  operational concern that comes with that (connection management,
  migrations, backup, local dev setup, `docker-compose.yml` additions) is
  starting from zero, not from an existing-but-imperfect implementation
  like most of the other sections in this document.
- `core/monitoring.py`'s existing SQLite usage means there are *two*
  different persistence technologies in play once PostgreSQL is added
  (SQLite for prediction tracking, PostgreSQL for offline features) unless
  a decision is made about whether monitoring data should move too — a
  decision explicitly out of scope for this analysis, but worth flagging
  as a question Sprint 2 will eventually face.

### Dependencies
- None upstream within the codebase (this is foundational, greenfield
  work) — but it does depend on the market-data-pipeline decision (§2),
  since the offline store's schema is shaped by whatever the canonical
  fetch/feature format ends up being.

### Recommended implementation order (this section only)
This is infrastructure-first work: the PostgreSQL instance, driver, and
connection scaffolding would need to exist before any offline-store
schema or ingestion code could be written or tested against it.

---

## 5. Existing Redis usage

### Current implementation
**None.** Same verification method as §4 — no `redis`/`redis-py` in
`requirements.txt`, no Redis service in `docker-compose.yml`, zero source
hits for `redis` anywhere in `backend/` except the explanatory comment in
`core/cache_manager.py`'s own docstring explicitly stating it does *not*
use Redis ("Kalıcı bir depolama katmanı yoktur (Redis/SQLite değil)").

### Missing capabilities
Everything: no Redis instance, no client dependency (`redis-py` or
similar), no key-naming scheme, no serialization contract, no TTL
migration from the in-memory `TTLCache` pattern, no connection pooling or
failure-mode handling (what happens to `HybridTradingEngine.run()` if
Redis is briefly unreachable — today there is no such failure mode to
handle at all, since the cache is in-process memory).

### Technical risks
- Introducing Redis introduces a new *runtime dependency* the application
  didn't have before: today, if the in-memory cache layer has a problem,
  at worst a cache miss occurs and the expensive path re-runs; a
  Redis-backed online store failing (network partition, Redis down) is a
  qualitatively different failure mode that the current code has no
  precedent for handling gracefully anywhere.
- Per §3, three different existing cache call sites would need to migrate
  to whatever the new Redis-backed interface looks like — the serialization
  format decision (JSON? pickle? something else) directly affects all
  three, plus the `TradeRecommendation`/`NewsAnalysisResult`/`SectorResult`
  pydantic models that currently pass through those caches by reference,
  uncopied, unserialized (per the Task 3 characterization of `TTLCache`).

### Dependencies
- Same infrastructure-first nature as §4 — needs the Redis instance and
  client scaffolding before any online-store code can be written or
  tested.
- Logically paired with §3 (current caching): Redis is this project's
  Phase 2 answer to "current caching," so the two sections' gaps are, in
  effect, the same gap looked at from "what exists" vs. "what's approved."

### Recommended implementation order (this section only)
Stand up the Redis instance and a minimal client wrapper before migrating
any of the three existing cache call sites onto it, and migrate the
already-consolidated `TTLCache` call sites (per §3's recommended order)
rather than the two ad-hoc caches directly — this means §3's cleanup
should land first.

---

## 6. Existing data models

### Current implementation
Data models are scattered across at least five independent locations with
no shared base or registry:
- `backend/models/schemas.py` — the legacy v1/hybrid-adjacent Pydantic
  models: `AnalysisRequest`, `TechnicalIndicators`, `MonteCarloResult`,
  `RecommendationResult`, `AnalysisResult`, `ScanResult`, `ScanRequest`,
  `ChartPoint`/`ChartResponse`, `PortfolioOptRequest`/`PortfolioOptResult`,
  `EnhancedAnalysisRequest`, `SessionInfo`.
- `backend/v2/models/schemas.py` — a completely separate, smaller set:
  `SignalSide` (enum), `IndicatorOutput`, `EngineResult`.
- `backend/core/regime_scanner.py` — `MarketRegime` (enum),
  `ScannedSymbol` (dataclass, not Pydantic).
- `backend/core/risk_manager.py` — `RiskLevels` (Pydantic).
- `backend/core/ai_trader_persona.py` — `TradeSignal` (enum),
  `TradeRecommendation` (Pydantic).

### Missing capabilities
- No single canonical representation of "a technical analysis result" —
  `AnalysisResult` (v1), `EngineResult` (v2), and `TradeRecommendation`
  (hybrid) all represent conceptually the same idea (symbol + score/signal
  + supporting data) with three incompatible shapes and three different
  field-naming conventions (`decision_code` vs. `side`/`aggregated_score`
  vs. `signal`/`confidence_score`).
- No feature-specific schema exists at all yet — none of the five model
  sources above represent "a versioned, point-in-time feature vector for
  symbol X at time T," since that concept doesn't exist anywhere in the
  current codebase.
- Mixed dataclass/Pydantic usage (`ScannedSymbol` is a plain
  `@dataclass`, everything else is Pydantic) — no consistent
  serialization contract across even the existing models, which matters
  directly for a Redis/PostgreSQL migration where every model that
  crosses that boundary needs a defined (de)serialization path.

### Technical risks
- Any Feature Store schema introduced in Sprint 2 becomes a *sixth*
  parallel model definition unless it's deliberately designed to unify or
  wrap the existing three result shapes — otherwise this project goes
  from three duplicate engines with three duplicate result models to
  three duplicate engines, three duplicate result models, *and* a fourth,
  Feature-Store-specific model that doesn't talk to any of them.
- The `ScannedSymbol` dataclass would need explicit serialization handling
  (dataclasses don't get free JSON/Pydantic-style `.model_dump()`) if it
  or anything shaped like it is ever persisted to PostgreSQL or cached in
  Redis.

### Dependencies
- Directly follows from whichever engine is chosen as the Feature Store's
  first consumer (per §1's recommended order) — that choice determines
  which of the three existing result-shape families the first feature
  schema needs to be compatible with.

### Recommended implementation order (this section only)
Inventory the exact fields each of the three result models actually
carries (a documentation step, not a code step) before defining any new
feature schema, so the new schema is designed with visibility into what
already exists rather than in isolation.

---

## 7. Existing feature generation

### Current implementation
Feature computation is duplicated across three independent
implementations of substantially the same technical indicators:
- `core/indicators.py` — 13 pure functions (RSI, MACD, Bollinger, EMA
  crossover, trend strength, price velocity, volume ratio, Williams %R,
  CCI, VWAP, ROC, Ichimoku, divergence), each operating on raw
  `pd.Series`/floats passed in directly. Used by `core/analyzer.py` (v1)
  and by the research scripts (`research/backtest.py`,
  `research/backtest_advanced.py`, `research/ml_trainer.py`).
- `core/mtf_analyzer.py` — a *different* implementation using
  `pandas_ta` (EMA 50/200 crossover, Supertrend, RSI, MACD histogram,
  Bollinger squeeze) plus `core/pattern_scanner.py` (candlestick patterns,
  support/resistance proximity) — used only by the hybrid engine.
- `v2/indicators/*` — a *third* implementation (`VWAPIndicator`,
  `EMAIndicator`, `KillzoneIndicator`, `FVGIndicator`,
  `MarketStructureIndicator`, `PivotPointsIndicator`), each a separate
  class implementing `BaseIndicator.calculate()`, producing normalized
  `[-1, +1]` scores — used only by the v2 engine.

None of the three persists a single computed feature value anywhere;
every feature is computed fresh, in-process, on every call, and discarded
immediately after use.

### Missing capabilities
- No feature versioning of any kind — there is no way today to know
  "which version of the RSI calculation produced this score" because
  nothing records that a calculation happened at all, only its immediate
  consumption.
- No point-in-time feature retrieval — every feature is "whatever the
  live indicator functions compute right now against whatever
  `data/fetcher.py`/`_fetch_batch_history`/`_fetch` just returned."
- No shared feature-computation layer between the three implementations —
  RSI, for example, is computed three separate ways (`core/indicators.py`'s
  `calculate_rsi`, `pandas_ta`'s RSI inside `mtf_analyzer.py`, and
  whatever `v2/indicators/`'s relevant indicator does), with no guarantee
  the three produce identical values for the same input data (different
  smoothing conventions between hand-rolled and `pandas_ta`
  implementations are a known common source of RSI value drift).

### Technical risks
- A Feature Store needs one authoritative feature-computation path to
  populate it; today there are three, and picking any one to formalize
  as "the" feature-generation layer leaves the other two computing
  potentially-different values for the same nominal indicator, for the
  two engines not migrated.
- Because nothing is persisted, there is currently no historical feature
  data at all to backfill a new offline store with — any PostgreSQL
  offline store starts genuinely empty and only accumulates history from
  the point features start being written, not retroactively.

### Dependencies
- Directly coupled to §1/§6: the choice of which engine's feature
  generation becomes canonical determines both which fetch pipeline (§2)
  feeds it and which existing data model (§6) it needs to be compatible
  with.

### Recommended implementation order (this section only)
Do not attempt to reconcile all three feature-generation implementations
into one at the start of Sprint 2 — per §1's recommendation, formalize
the hybrid engine's feature set (`core/mtf_analyzer.py` +
`core/pattern_scanner.py`) as the first Feature-Store-backed path, and
treat unifying it with `core/indicators.py`/`v2/indicators/*` as later,
separate work once the Feature Store pattern itself is proven.

---

## 8. Existing ML pipeline

### Current implementation
- **Serving**: `core/ml_predictor.py` (characterized in Sprint 1 Task 5 —
  process-wide `_MODEL_CACHE` global, load-once-forever on success,
  hardcoded 7-feature vector, no schema validation against the model
  artifact's own `feature_names` metadata), `ml/chart_model.py` (CNN/LSTM
  chart-pattern serving, used by `main.py::_enrich_result`), and
  `v2/ml/predictor.py` (`MLPredictorV2`, used by `v2/api/router.py`) —
  three separate serving modules, one per engine, none sharing code.
- **Training** (now isolated under `backend/research/` per Sprint 1
  Task 7): `research/ml_trainer.py` (XGBoost, feeds
  `core/ml_predictor.py`'s artifact), `research/train_v2.py` (a second,
  differently-featured XGBoost pipeline for `v2/ml/predictor.py`'s
  artifact — currently non-importable in this environment due to a
  pre-existing missing `xgboost` dependency, per the Task 7 report), and
  `research/train_chart_model.py` (CNN/LSTM, feeds `ml/chart_model.py`).
- **Scheduling**: `main.py`'s `self_evolution_loop()` background task
  calls `research.ml_trainer.train()` once every 24 hours, in-process,
  with no separation between the serving process and the training job.

### Missing capabilities
- No feature store integration of any kind between training and serving —
  each of the three train/serve pairs independently re-derives its own
  feature vector from raw OHLCV data, with no shared, versioned feature
  computation between the two halves of even a single pair (the training
  script's feature extraction and the serving module's feature extraction
  are two separately-written, separately-maintained code paths that
  happen to agree today only because no one has changed one without the
  other yet).
- No model versioning or registry (already noted in
  `docs/architecture/migration-notes.md`'s `ml_predictor.py` section) —
  extending this to a Feature Store context, there is also no link
  between "which feature-store schema version" a given trained model
  artifact expects.
- No offline feature history to train against beyond what
  `research/ml_trainer.py` fetches live from `yfinance` at training time —
  a PostgreSQL offline store would be the first time this project has
  had a durable, queryable history to train from, rather than a fresh
  live pull every time a training script runs.

### Technical risks
- `main.py`'s daily in-process retraining call (`self_evolution_loop`)
  means production and research are still coupled at runtime even after
  Sprint 1's code-level separation (documented as known, accepted
  coupling in `migration-notes.md`'s "Production vs Research Separation"
  section) — any Feature Store integration into the training path
  inherits that same coupling unless it's addressed as part of the same
  effort.
- Three independent train/serve pairs each needing to be pointed at a new
  Feature Store (if that's the eventual goal) is three times the
  migration surface of a single unified pipeline — consistent with every
  other "three engines" risk already identified in `gap-analysis.md`.

### Dependencies
- Downstream of §6/§7 (data models, feature generation) — a Feature Store
  cannot serve a consistent feature vector to a training script unless
  the training script's current hand-rolled feature extraction is first
  reconciled with whichever feature-generation path (per §7) becomes
  canonical.

### Recommended implementation order (this section only)
Leave all three train/serve pairs on their current, independent
feature-extraction code for the first iteration of the Feature Store —
wiring even one of them (most naturally, `research/ml_trainer.py` /
`core/ml_predictor.py`, since it's the pair without the pre-existing
`xgboost` import failure `research/train_v2.py` has) through the new
store is a meaningfully-sized task on its own and shouldn't be bundled
with the other two in the same pass.

---

## Cross-cutting synthesis: suggested order across all eight sections

This follows directly from the "Dependencies" and per-section
"Recommended implementation order" notes above — it sequences work, it
does not add or redesign anything beyond what's already described section
by section:

1. **§3 caching cleanup** — migrate `news_analyzer.py` and
   `sector_intelligence.py` off their ad-hoc caches onto `TTLCache`
   first. Cheapest, lowest-risk, and reduces three cache implementations
   to one before Redis has to replace anything.
2. **§4 + §5 infrastructure** — stand up PostgreSQL and Redis
   (`docker-compose.yml` additions, driver dependencies, connection
   scaffolding) in parallel; both are greenfield, foundational, and
   don't depend on each other.
3. **§2 pipeline decision** — decide which single market-data fetch
   pattern (of the ≥3 existing shapes) becomes canonical for whichever
   engine is chosen first.
4. **§1 + §7 first integration** — per §1 and §7's own recommended
   orders, wire the **hybrid engine** path
   (`core/regime_scanner.py`/`core/mtf_analyzer.py`/
   `core/pattern_scanner.py`) through the new Feature Store first, since
   it's the newest, most recently characterized (Sprint 1 Task 6), and
   least internally duplicative of the three engines.
5. **§6 schema reconciliation** — only after step 4 proves the pattern
   once, revisit whether `AnalysisResult`/`EngineResult`/
   `TradeRecommendation` should converge, informed by real experience
   rather than upfront guessing.
6. **§8 ML pipeline integration** — last, and only for the
   `research/ml_trainer.py` / `core/ml_predictor.py` pair first (not
   `train_v2.py`, which has its own unrelated pre-existing environment
   issue, and not the chart model, which is a different modality
   entirely).

No step above assumes anything not already stated in the corresponding
section; this is a sequencing summary, not a new plan.
