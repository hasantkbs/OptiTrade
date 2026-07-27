# OptiTrade Quant Research Platform — Phase 1 Gap Analysis

Date: 2026-07-27
Status: Analysis only — no code changed, no architecture altered.

## Purpose

This document compares the **current backend implementation** (as it exists
in this repository today) against the **approved Phase 1 architectural
decisions** stated so far, in order to produce an implementation roadmap.

It does not propose new architecture. Where no approved decision exists for
a named subsystem, this document says so explicitly rather than inventing
one.

## Method

Findings below are based on direct inspection of the code in this
repository (paths cited per finding), not on assumption. Files read in
full or in relevant part: `backend/main.py`, `backend/core/hybrid_engine.py`,
`backend/core/ai_trader_persona.py`, `backend/core/scoring.py`,
`backend/core/analyzer.py`, `backend/core/ml_predictor.py`,
`backend/core/cache_manager.py`, `backend/core/monitoring.py`,
`backend/data/fetcher.py`, `backend/v2/core/engine.py`,
`backend/v2/api/router.py`, `backend/api/v1/router.py`,
`backend/backtest.py`, `backend/backtest_advanced.py`, `backend/ml_trainer.py`,
`backend/v2/ml/train_v2.py`, `backend/test_engine.py`, `docker-compose.yml`,
`backend/requirements.txt`, plus the existing design note at
`docs/superpowers/specs/2026-07-22-hybrid-quant-trading-design.md`.

## Approved Phase 1 decisions (source of truth for this analysis)

Only the following four decisions have been explicitly approved in this
conversation. Every gap below is measured against one of these:

1. **LLMs are explanation engines only.** They do not make investment
   decisions.
2. **The Decision Engine is the only component responsible for investment
   decisions.**
3. **Feature Store (minimal version):** versioning, point-in-time
   correctness, validation, Redis as the online store, PostgreSQL as the
   offline store.
4. **Research Lab is strictly internal** and never participates in live
   predictions.

No approved decision exists yet for an "Engine Platform," "Learning
Engine," or "Validation Framework" as named components. Those three are
included below as **current-state-only** sections (no gap can be computed
without an approved target), so the absence of a target is itself flagged
as an open item rather than silently skipped.

---

## 1. Decision Engine

### Current implementation

There is no single Decision Engine. Three independent, fully wired
decision paths run concurrently inside the same `backend/main.py` FastAPI
process:

| Path | Entry point | Decision logic | Output |
|---|---|---|---|
| Legacy v1 | `core/analyzer.py::analyze()` → `main.py` | `core/scoring.py::compute_score()` (deterministic weighted rule scoring, 0–100) → `get_decision(score)` | `AnalysisResult` (decision, decision_code) |
| v2 | `v2/core/engine.py::TradingEngineV2.analyze()` → `v2/api/router.py` | `SignalFusion.aggregate()` (confidence-weighted average of per-indicator scores) | `EngineResult` (aggregated_score, signals, risk_score) |
| Hybrid/v1-new | `core/hybrid_engine.py::HybridTradingEngine.run()` → `api/v1/router.py` → `api/v1/endpoints/signals.py` | `core/ai_trader_persona.py::AITraderPersona.generate_recommendation()` — an LLM (Groq) call whose structured output *is* the trade signal | `TradeRecommendation` (signal, confidence_score, entry/SL/TP) |

All three are mounted simultaneously (`main.py:35-37`: `v2.api.router`,
`api.v1.router`, plus the inline v1 endpoints using `core.analyzer`).
`core/ml_predictor.py`'s XGBoost output is a fourth, partial signal —
it only annotates the legacy path's result (`ml_confidence` field) and
does not gate or override `get_decision()`.

### Approved Phase 1 architecture

A single component holds sole authority over investment decisions.

### Missing components

- A single `DecisionEngine` component/module does not exist.
- No arbitration or deprecation path between the three existing decision
  paths — all three are live in production simultaneously today.
- No contract/interface separating "signal generation" from "decision
  authority" — currently each path conflates data → analysis → decision in
  one call.

### Components requiring refactoring

- `core/hybrid_engine.py` / `core/ai_trader_persona.py`: currently the LLM
  call *is* the decision (see §2). To comply with decision #2, decision
  authority (signal, entry/SL/TP) must move out of the LLM call and into a
  deterministic Decision Engine component; the LLM's role would need to be
  reduced to consuming an already-made decision and generating
  natural-language commentary about it.
- `core/analyzer.py` / `core/scoring.py`: deterministic and rule-based
  (a reasonable starting point for a Decision Engine's logic), but currently
  invoked directly by `main.py` as its own standalone path rather than
  behind a single authoritative interface.
- `v2/core/engine.py::TradingEngineV2`: a second, differently-shaped
  deterministic scorer (0–1 confidence-weighted fusion vs. 0–100 rule
  score) that would need to be reconciled with or retired in favor of
  the single Decision Engine.

### Components already compliant

- None of the three existing paths is itself a compliant "single Decision
  Engine" — by definition, three concurrent authorities is the opposite of
  decision #2.
- The deterministic scoring logic in `core/scoring.py` (weighted, auditable,
  no LLM involvement) is architecturally the closest existing building
  block to what a compliant Decision Engine's core logic should look like
  in kind (deterministic, explainable), even though it is not wired as the
  sole authority today.

### Estimated implementation complexity

High. Requires consolidating three live code paths behind one interface
without breaking `main.py`, `v2/api/router.py`, and `api/v1/endpoints/signals.py`
consumers (including the iOS client, which calls these endpoints).

### Dependencies

- Requires the Feature Store (or at least a stable, versioned feature
  interface) to exist first, so the Decision Engine has one consistent
  input contract instead of three separate ad-hoc feature-assembly code
  paths (`analyzer.py`, `TradingEngineV2.analyze`, `MultiTimeframeAnalyzer.analyze`).

---

## 2. LLM Role

### Current implementation

`core/ai_trader_persona.py::AITraderPersona.generate_recommendation()`
sends technical/risk/news data to Groq's Chat Completions API with forced
tool-calling, and the LLM's structured tool-call output directly populates
`TradeRecommendation.signal` (`STRONG_BUY` … `STRONG_SELL`),
`confidence_score`, and (copied through from risk_manager) the price
levels. The system prompt explicitly instructs the model to decide the
final signal ("Teknik Trader ile Makro Yatırımcı birbiriyle çelişiyorsa …
sinyali ACIMASIZCA NEUTRAL'a çek ve confidence_score'u düşür").

### Approved Phase 1 architecture

LLMs are explanation engines only; they do not make investment decisions.

### Missing components

- No separation exists between "decision" fields (`signal`,
  `confidence_score`) and "explanation" fields (`trader_analysis`,
  `investor_analysis`, `trader_commentary`) in `TradeRecommendation` — all
  are produced by the same LLM call today.

### Components requiring refactoring

- `AITraderPersona`: needs to stop producing `signal`/`confidence_score`
  itself. Its role should narrow to taking an already-decided output from
  the Decision Engine and generating the Turkish commentary fields only.
- `TradeRecommendation` (pydantic model in `core/ai_trader_persona.py`):
  the decision fields (`signal`, `confidence_score`, `entry_price`,
  `stop_loss`, `take_profit_1`, `take_profit_2`) would need to originate
  from the Decision Engine, not from the tool-call schema the LLM fills in.

### Components already compliant

- `core/news_analyzer.py`'s sentiment analysis (used as an input, not a
  decision) and `core/sector_intelligence.py` are not LLM-driven decision
  points — not directly relevant to this decision, but confirm no other
  LLM call in the codebase currently violates it besides `AITraderPersona`.

### Estimated implementation complexity

Medium. The prompt/schema surface is well-isolated to one file
(`core/ai_trader_persona.py`), but downstream consumers
(`hybrid_engine.py`, iOS `TradeRecommendation` model, `dashboard.py`)
all currently read `signal`/`confidence_score` off the LLM's own output and
would need to read them from the Decision Engine instead.

### Dependencies

- Directly depends on the Decision Engine existing first (§1) — the LLM
  cannot be demoted to "explanation only" until something else is
  producing the decision for it to explain.

---

## 3. Feature Store

### Current implementation

No Feature Store exists in any form. Concretely, as of this analysis:

- **Data fetching**: `backend/data/fetcher.py` calls `yfinance` directly,
  synchronously, per request, with no persistence layer at all.
- **Caching**: `core/cache_manager.py::TTLCache` is in-memory only,
  per-process, cleared on restart — used for `news_analyzer.py` /
  `sector_intelligence.py` sentiment/sector lookups and
  `hybrid_engine.py`'s 15-minute recommendation cache. Its own docstring
  states explicitly: *"Kalıcı bir depolama katmanı yoktur (Redis/SQLite
  değil)"* ("no persistent storage layer — not Redis/SQLite").
- **Versioning**: none. Features are recomputed from whatever `yfinance`
  returns at call time; there is no record of what feature values were
  used for a past decision.
- **Point-in-time correctness**: not enforced. `fetch_history(symbol,
  period=...)` returns whatever the live API currently reports for that
  window; there is no snapshotting or as-of query capability, so a
  decision made "now" cannot be reproduced later against the exact data
  it saw.
- **Validation**: no schema/data-quality validation layer on fetched data
  (only `if hist.empty` / try-except guards).
- **Storage engines**: neither Redis nor PostgreSQL appear anywhere in
  `backend/requirements.txt`, any `.py` file, or `docker-compose.yml`
  (which defines only the `api` service — no datastore containers at all).
  The only persistent store in the entire backend is a single SQLite file
  (`backend/data/monitoring.db`, via `core/monitoring.py` — prediction
  logging, not features).

### Approved Phase 1 architecture

Minimal Feature Store: versioning, point-in-time correctness, validation,
Redis (online store), PostgreSQL (offline store).

### Missing components

- Redis online store — does not exist.
- PostgreSQL offline store — does not exist.
- Feature versioning — does not exist.
- Point-in-time correctness / as-of retrieval — does not exist.
- Feature validation layer — does not exist.
- A `FeatureStore` interface/module of any kind — does not exist.

### Components requiring refactoring

- `data/fetcher.py`: currently the sole data-access point; would need to
  sit *behind* the Feature Store (or be absorbed into its offline
  ingestion path) rather than being called directly by `analyzer.py`,
  `mtf_analyzer.py`, `regime_scanner.py`, and the backtest/training scripts
  independently, as it is today.
- `core/cache_manager.py::TTLCache`: its in-memory, single-process,
  non-versioned design is exactly what the Redis online store needs to
  replace for any state that must survive process restarts or be shared
  across workers.

### Components already compliant

- None. This subsystem does not exist yet in any partial form beyond
  ad-hoc TTL caching.

### Estimated implementation complexity

High. This is new infrastructure (two new stateful services: Redis,
PostgreSQL) plus a new module boundary that essentially every existing
data-consuming module (`analyzer.py`, `mtf_analyzer.py`, `regime_scanner.py`,
`ml_predictor.py`, `ml_trainer.py`, `backtest*.py`) would eventually need
to read through instead of calling `yfinance` directly.

### Dependencies

- None upstream — this is foundational infrastructure. Every other
  subsystem in this document (Decision Engine, Learning Engine,
  Validation Framework, Research Lab) depends on it existing first if
  point-in-time correctness is to hold end-to-end.

---

## 4. Research Lab

### Current implementation

There is no isolated "Research Lab." Research/training scripts
(`backend/backtest.py`, `backend/backtest_advanced.py`,
`backend/ml_trainer.py`, `backend/v2/ml/train_v2.py`,
`backend/ml/train_chart_model.py`) are loose top-level/`ml/` scripts that
directly `import` the same production modules used by the live paths:

- `backtest.py` / `backtest_advanced.py` / `ml_trainer.py` import
  `core.indicators` and `core.scoring.compute_score` / `get_decision` —
  the exact same functions `core/analyzer.py` calls in the live v1 request
  path.
- Trained model artifacts (`backend/models/xgb_signal_model.joblib`) are
  loaded directly into the live path by `core/ml_predictor.py` with no
  staging, review, or promotion step between "trained" and "serving."

There is currently no mechanism that would *prevent* a research script
from affecting live predictions — quite the opposite, importing
`core.scoring` directly means a research-only change to that module would
immediately change live decisions too, since it is one shared module, not
two.

### Approved Phase 1 architecture

Research Lab is strictly internal and never participates in live
predictions.

### Missing components

- No module/package boundary separating "research" from "production" —
  no `research/` (or equivalent) namespace exists; research scripts live
  alongside production code in `backend/` and `backend/core/`.
- No model-promotion step between training output
  (`xgb_signal_model.joblib`) and production consumption
  (`ml_predictor.py` loads the file directly with no versioning or gating).
- No enforcement (lint rule, import boundary, CI check, or otherwise)
  preventing production modules from importing research modules or
  vice versa.

### Components requiring refactoring

- `backtest.py`, `backtest_advanced.py`, `ml_trainer.py`,
  `v2/ml/train_v2.py`, `ml/train_chart_model.py`: need to move into an
  isolated research namespace and stop importing `core.scoring` /
  `core.indicators` as live production modules — either by depending on
  frozen/versioned interfaces instead, or by the Feature Store providing
  the historical data they need without touching production code paths.
- `core/ml_predictor.py`: the direct `joblib.load()` of a file dropped in
  `backend/models/` by a training script is an implicit, unguarded
  promotion path from research to production and needs a real boundary
  (even a manual one) between the two.

### Components already compliant

- None — the current structure has no isolation at all between research
  and production for either code or models.

### Estimated implementation complexity

Medium. Mostly a matter of relocating files and changing import paths /
introducing a data-access seam, rather than new algorithmic work — but it
touches every research script that currently reaches into `core/`.

### Dependencies

- Benefits from the Feature Store existing first (§3), so research scripts
  can pull historical, point-in-time data from PostgreSQL instead of
  hitting `yfinance` ad hoc the way `backtest.py`/`ml_trainer.py` do today
  — but isolating the *code/import* boundary does not strictly require it
  and could be done independently/earlier.

---

## 5. Engine Platform, Learning Engine, Validation Framework — no approved target yet

No Phase 1 decision has been stated for these three named subsystems.
Per this document's ground rules, no gap can be computed without an
approved architecture to compare against. Current-state facts only:

### Engine Platform (current state)

Three separate orchestration/execution entry points exist today, matching
the three decision paths in §1: `core/analyzer.py::analyze()`,
`v2/core/engine.py::TradingEngineV2`, and
`core/hybrid_engine.py::HybridTradingEngine`. There is no unifying
"platform" layer — each is invoked directly from its own router/endpoint
in `main.py`.

### Learning Engine (current state)

Model training is manual and offline only: `backend/ml_trainer.py`
(XGBoost, hand-run via `python ml_trainer.py`) and
`backend/v2/ml/train_v2.py` (separate XGBoost training pipeline with
`StratifiedKFold` cross-validation) both produce `.joblib` artifacts
consumed directly by `core/ml_predictor.py` / `v2/ml/predictor.py`. There
is no scheduled retraining, no online/continuous learning, and no
versioning of model artifacts beyond the single file each script
overwrites.

### Validation Framework (current state)

`core/monitoring.py` provides a real, existing mechanism: predictions are
logged to a local SQLite database (`backend/data/monitoring.db`) via
`log_prediction()`, and `validate_predictions()` later checks realized
price movement against the logged `decision_code` to compute accuracy
(`get_performance_stats()`). This is wired only into the legacy v1 path
(`main.py` imports it alongside `core.analyzer`); it is not connected to
the v2 or hybrid/LLM decision paths. Separately, `backtest.py` /
`backtest_advanced.py` provide offline historical validation (Sharpe,
max drawdown, win rate) against `core/scoring.py`, unconnected to the
live monitoring mechanism above — i.e. today there are two disconnected,
non-unified validation mechanisms (live outcome tracking vs. offline
backtesting), not one framework.

**Open item**: these three subsystems need an approved Phase 1 decision
before an actual gap analysis (missing/refactor/compliant/complexity/
dependencies) can be produced for them.

---

## Cross-cutting findings

- **Triplication, not gaps alone**: the single largest finding in this
  analysis is that §1–§2 aren't really about *missing* a Decision Engine —
  they're about **three fully-built, currently-serving decision systems**
  that would need to be reconciled or retired, which is a materially
  different (and higher-risk) kind of work than building something from
  zero.
- **No automated test suite**: the only test-like script found,
  `backend/test_engine.py`, is a manual/interactive smoke-test harness
  (requires a live `GROQ_API_KEY` and live network calls) — there is no
  `pytest`/`unittest` suite anywhere in `backend/`. This affects every
  future sprint's ability to add unit tests incrementally, since there is
  no existing test scaffolding (fixtures, mocked data, CI wiring) to build on.
- **No infrastructure-as-code for stateful services**: `docker-compose.yml`
  defines only the API container; adding Redis/PostgreSQL for the Feature
  Store will be the first stateful infrastructure this project has had.

## Suggested build order (dependency-driven, not a redesign)

This sequencing follows strictly from the "Dependencies" fields stated
above — it does not introduce new components or change any approved
decision:

1. **Feature Store** (§3) — foundational; nothing else can be made
   point-in-time-correct without it.
2. **Research Lab isolation** (§4) — can start in parallel with (1); code/
   import-boundary work does not strictly require the Feature Store, though
   full completion (research reading from PostgreSQL) does.
3. **Decision Engine consolidation** (§1) — depends on (1) for a stable
   input contract.
4. **LLM demotion to explanation-only** (§2) — depends on (3) existing,
   since the LLM needs a decision to explain instead of make.
5. **Engine Platform / Learning Engine / Validation Framework** — blocked
   on an approved Phase 1 decision for each; cannot be sequenced further
   until that exists.
