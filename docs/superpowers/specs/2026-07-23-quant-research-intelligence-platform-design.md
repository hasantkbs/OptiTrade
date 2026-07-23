# Quant Research & Intelligence Platform — Phase 1 Architecture

Date: 2026-07-23

Status: **Design only — not approved for implementation.** No code is written as part of
this spec. A future implementation plan may only be created after explicit approval of
this document.

## Context

OptiTrade's backend has grown a set of independent, never-formally-unified analysis
modules: rule-based Technical/Fundamental/News signal engines (`signals/technical.py`,
`fundamental.py`, `news.py`, all conforming to a shared but underused `EngineResult`
contract in `signals/models.py`), an unimplemented `DecisionEngine` stub
(`signals/decision.py`, `NullDecisionEngine`), and a separate, newer LLM-driven pipeline
(`core/hybrid_engine.py`) where `AITraderPersona`/`InvestorPersona` each decide a
BUY/SELL/HOLD-equivalent signal directly via LLM reasoning, with no connection to the
signal-engine/Decision-Engine machinery at all.

This spec designs **Phase 1: Quant Research & Intelligence Platform** — the architecture
that unifies all of these into one coherent research system with institutional-grade
properties: independent engines, explainable AI, self-validation, continuous learning,
continuous backtesting, continuous benchmarking, and modular expansion.

## Non-negotiable requirements (as given)

- Independent Engines
- Explainable AI
- Self Validation
- Continuous Learning
- Continuous Backtesting
- Continuous Benchmarking
- Modular Expansion
- Every engine produces: Score, Confidence, Evidence, Explanation, Historical Accuracy
- **Only the Decision Engine may produce BUY / SELL / HOLD**

## Key decision, resolved during design: engine scope

Trader Profile and Investor Profile (currently `AITraderPersona`/`InvestorPersona`, which
decide independently today) become genuine **Independent Engines** under this
architecture — not a separate, disconnected surface. They produce the same
Score/Confidence/Evidence/Explanation/Historical-Accuracy contract as every other engine
and feed the Decision Engine as additional evidence. Their existing product-facing output
(the Turkish commentary, the 1w/1m/1y horizon views) is preserved and still shown to the
user **alongside** the Decision Engine's final verdict — the Decision Engine does not
replace or hide per-engine opinions, it synthesizes them into one additional, final
signal that only it is allowed to label BUY/SELL/HOLD.

## 1. The Engine Contract

Every engine (existing and future) implements one shared output shape:

```
EngineOutput
├── engine_name        : str            e.g. "TECHNICAL", "TRADER_PROFILE", "INVESTOR_PROFILE_1Y"
├── engine_version      : str            identifies the exact logic/prompt/model that produced this
├── symbol              : str
├── as_of               : datetime
├── score               : float [-100, 100]   bearish..bullish opinion, NOT a decision
├── confidence          : float [0.0, 1.0]
├── evidence            : List[EvidenceItem]  raw, structured, machine-recomputable data points
├── explanation         : str                 human-readable narrative, built FROM evidence
└── historical_accuracy : HistoricalAccuracy  this engine's own rolling track record
```

```
EvidenceItem
├── key      : str      e.g. "rsi_14", "horizon_1_year_regime_persistence", "news_headline_match"
├── value    : Any       raw value (number, enum, matched text span)
└── weight   : float      this item's contribution to `score`, signed
```

```
HistoricalAccuracy
├── window_days         : int     e.g. 30
├── sample_size         : int     number of reconciled predictions in the window
├── accuracy_pct        : float   [0.0, 1.0]; None if sample_size == 0 (cold start)
└── confidence_calibration : float  how well stated `confidence` matched actual correctness
```

`DecisionOutput` is the **only** structure permitted to contain a `BUY | SELL | HOLD`
field. This is enforced structurally, not just by convention: no other Pydantic/dataclass
model in the system may declare a field with that enum.

**Evidence vs. Explanation, and why the split matters:** `evidence` must be emittable
*before* the narrative is generated, exactly mirroring the pattern `AITraderPersona`'s
system prompt already uses today (reason as a Technical Trader, then a Macro Investor,
*then* synthesize into commentary — evidence-then-narrative, not narrative-then-evidence).
For rule-based engines this is free (`Signal.value`/`contribution` already are evidence).
For LLM-based engines, the forced-tool-calling schema must require the evidence fields
before the explanation field, matching the existing `_RECOMMENDATION_SCHEMA` ordering
convention in `core/ai_trader_persona.py`/`core/investor_persona.py`.

## 2. Independent Engines — current inventory and adaptation

| Engine | Current implementation | Phase 1 adaptation |
|---|---|---|
| Technical | `TechnicalSignalEngine` (`signals/technical.py`), already returns `EngineResult` | Thin adapter maps `EngineResult` → `EngineOutput`; `evidence` = existing `Signal` list unchanged |
| Fundamental | `FundamentalSignalEngine` (`signals/fundamental.py`) | Same adapter pattern |
| News | `NewsSignalEngine` (`signals/news.py`) | Same adapter pattern |
| Trader Profile | `AITraderPersona` (`core/ai_trader_persona.py`) — LLM decides `signal` directly today | Re-scoped: LLM reasoning unchanged, but `signal`/`confidence_score` become this engine's `score`/`confidence` (one opinion among several), `trader_analysis`/`investor_analysis` become `evidence`, `trader_commentary` becomes `explanation`. The engine no longer has authority to be presented as "the" recommendation on its own — see product-surface note in §9. |
| Investor Profile | `InvestorPersona` (`core/investor_persona.py`) — 3 independent horizons today | Split into **three separate engine identities**: `INVESTOR_PROFILE_1W`, `INVESTOR_PROFILE_1M`, `INVESTOR_PROFILE_1Y`. Each horizon's `signal`/`confidence_score`/`rationale` maps to its own `EngineOutput`. Rationale: a 1-year call and a 1-week call from the same LLM persona have structurally different track records (a 1-year prediction can't even be reconciled for a year) and must not share one blended accuracy number or one blended vote. |
| Volume, Market Structure, Macro | Not implemented — already reserved as `None` fields in `signals/models.py`'s `SignalCollection` | Genuinely new engines, built in a later phase. Their existence is the reason the Engine Registry (§3) must not hardcode an engine list anywhere. |

## 3. Engine Registry — the modular-expansion mechanism

```python
# Illustrative only — no code is written in this phase.
EngineRegistry.register("TECHNICAL", TechnicalEngineAdapter())
EngineRegistry.register("FUNDAMENTAL", FundamentalEngineAdapter())
EngineRegistry.register("NEWS", NewsEngineAdapter())
EngineRegistry.register("TRADER_PROFILE", TraderProfileEngineAdapter())
EngineRegistry.register("INVESTOR_PROFILE_1W", InvestorProfileEngineAdapter(horizon="1W"))
EngineRegistry.register("INVESTOR_PROFILE_1M", InvestorProfileEngineAdapter(horizon="1M"))
EngineRegistry.register("INVESTOR_PROFILE_1Y", InvestorProfileEngineAdapter(horizon="1Y"))

EngineRegistry.run_all(symbol) -> List[EngineOutput]   # parallel; a failing engine is dropped, not fatal
```

This mirrors the existing `providers/registry.py` pattern already established in this
codebase (single access point, swappable/registrable implementations) — applied to
engines instead of market-data providers. Adding Volume/Market Structure/Macro (or any
future engine) later means writing one adapter and one `register()` call; it never
requires touching the Decision Engine.

A failing engine (LLM timeout, missing fundamentals data for a thinly-traded symbol)
simply does not appear in the `List[EngineOutput]` passed to the Decision Engine — the
same non-blocking philosophy `HybridTradingEngine._process_symbol` already uses for its
own per-symbol try/except today.

## 4. Decision Engine — accuracy-weighted adaptive voting

```
DecisionEngine.decide(engine_outputs: List[EngineOutput]) -> DecisionOutput

DecisionOutput
├── decision              : BUY | SELL | HOLD    -- ONLY this structure may hold this field
├── confidence             : float [0.0, 1.0]
├── contributing_engines   : List[{name, weight, score, historical_accuracy}]
└── explanation            : str   -- generated deterministically from the weight table, not by an LLM
```

**Aggregation strategy: accuracy-weighted adaptive voting**, chosen over two alternatives
considered:
- *Static fixed weights* — simplest, fully explainable, but doesn't satisfy "Continuous
  Learning" (weights never move without a human retuning them).
- *ML meta-model (stacked classifier over historical engine outputs)* — potentially
  highest raw accuracy, but works against "Explainable AI" (a trained model's internal
  logic is not a plain-language weight table) and requires its own
  train/validate/deploy/retrain pipeline that doesn't exist and isn't justified yet given
  how little historical engine-level data exists at Phase 1's start.

Accuracy-weighted voting satisfies both requirements at once: each engine's vote weight
*is* its own `historical_accuracy.accuracy_pct` (renormalized across the engines that
responded for this symbol), so the explanation is literally the weight table — no
separate "explain the model" step is needed. A brand-new engine with `sample_size == 0`
gets a neutral fallback weight (0.5-equivalent) until it accumulates enough reconciled
predictions to earn its own weight — a natural cold-start rule, not a special case.

**The aggregation strategy itself is pluggable** (an `AggregationStrategy` protocol) —
ships with `AccuracyWeightedVoting` in Phase 1; a future `StackedMetaModel` strategy (the
option not chosen above) can be swapped in later behind the same interface without
touching any engine or any caller. This applies the "Modular Expansion" principle one
level above the engines themselves.

This Decision Engine **is** the concrete implementation of the long-deferred "Phase C"
already referenced in this codebase's own prior design docs and `signals/decision.py`'s
docstrings — it replaces `NullDecisionEngine`, not `signals/decision.py`'s
`DecisionInput`/`DecisionOutput`/`DecisionEngineProtocol` shapes, which this design is
compatible with (though `DecisionOutput`'s existing `buy_probability`/`sell_probability`/
`hold_probability` triple may be superseded by the single `decision` enum field above —
flagged as a compatibility decision for the implementation-planning phase, not resolved
here).

## 5. Self-Validation — per-engine historical accuracy

New table, deliberately separate from the existing `analysis_predictions` table (which
only ever tracked the *final* decision's outcome, never per-engine attribution):

```
engine_predictions
├── id                (uuid, pk)
├── engine_name       (str)               e.g. "TECHNICAL", "INVESTOR_PROFILE_1Y"
├── engine_version    (str)
├── symbol            (str)
├── predicted_at      (timestamp)
├── score             (float)
├── confidence        (float)
├── evidence_json     (jsonb)             frozen snapshot — required for reproducible backtests
├── actual_price_1d / 7d / 30d / 1y  (float, nullable — filled by reconciliation job)
├── actual_direction  (str, nullable)
├── was_correct       (bool, nullable)
└── accuracy_contribution (float, nullable)
```

Every live `EngineOutput.historical_accuracy` is a **read** of a rolling window over this
table (e.g., trailing 30 days), never a fresh computation performed inline during a
request — matching the "predict now, reconcile later" pattern the existing
`analysis_predictions.actual_outcome`/`prediction_accuracy` columns already use for the
final decision. Phase 1 applies the same pattern one layer deeper: per-engine instead of
per-final-decision only.

`INVESTOR_PROFILE_1Y` predictions cannot be reconciled for a year — this engine
necessarily has a long cold-start period and should be expected (and shown in the UI, per
`sample_size`) to carry a neutral/low-confidence weight in the Decision Engine for a long
time after launch. This is a real, accepted consequence of splitting the horizons into
separate engines (§2), not an oversight.

## 6. Continuous Backtesting

`BacktestRunner` replays historical OHLCV — already cached in the TimescaleDB
`ohlcv_data` hypertable — bar-by-bar through the **exact same** `EngineRegistry.run_all()`
+ `DecisionEngine.decide()` code path used live. No separate "backtest-only"
reimplementation of any engine's logic exists, which is the standard source of
live/backtest drift in quant systems and is explicitly avoided here.

Results land in a new `backtest_runs` table, deliberately isolated from
`engine_predictions`/`analysis_predictions` — a backtest must never contaminate live
accuracy statistics or the Decision Engine's live weight computation.

```
backtest_runs
├── id, run_at, symbol_universe, date_range_start, date_range_end
├── engine_name (nullable — NULL means "the Decision Engine's own aggregate result")
├── simulated_accuracy_pct, simulated_return_pct, max_drawdown_pct
└── config_snapshot_json    (which engine_version(s)/weights were active during the run)
```

## 7. Continuous Benchmarking

`BenchmarkRunner` compares the Decision Engine's backtested performance each cycle
against named baselines:
- **Buy-and-hold** on the same symbol universe.
- **Random-walk null model** (statistical floor — any real edge must beat this).
- **The existing rule-based `core/scoring.py` score** (`compute_score`) — the system this
  platform is meant to supersede, kept as an honest baseline rather than assumed inferior.

```
benchmark_results
├── id, run_at, symbol_universe, date_range
├── baseline_name           ("BUY_AND_HOLD" | "RANDOM_WALK" | "LEGACY_SCORING")
├── baseline_return_pct, decision_engine_return_pct
└── outperformance_pct
```

This is what lets the platform answer, concretely and on a schedule, "is the new
institutional system actually better than what existed before it?" — rather than
asserting it by design.

## 8. Continuous Learning

A single daily reconciliation job closes the loop:
1. For every `engine_predictions` row old enough to score (1d/7d/30d/1y horizons as
   applicable), fetch the actual price and fill `actual_direction`/`was_correct`.
2. Recompute each engine's rolling `historical_accuracy` from the updated table.
3. Nothing else. No separate "training" step exists, because the Decision Engine's
   weights are a **read** of accuracy (§4), not a trained parameter — this is the direct
   payoff of choosing accuracy-weighted voting over an ML meta-model: the learning loop
   is one SQL aggregation, fully auditable, with no model artifact to version or
   validate.

## 9. Runtime & Scheduling

No scheduler or worker infrastructure exists in this codebase today (verified: no
Celery, no cron, no APScheduler anywhere in `backend/`). Proposed, reusing infrastructure
already present in `docker-compose.yml` (Redis + PostgreSQL — no new services introduced):

- **Celery + Redis** as the job queue (Redis is already a required service in this
  stack for `RedisCacheManager`).
- Three scheduled jobs:
  - `reconcile_predictions` — daily (§8)
  - `run_backtests` — weekly (§6)
  - `run_benchmarks` — weekly, after backtests complete (§7)
- The live request path (`/analyze`, `/api/v1/signals/analyze`, a future unified research
  endpoint) is completely decoupled from all of the above — it only ever *reads* the
  latest `historical_accuracy` snapshot from `engine_predictions`; it never blocks on, or
  triggers, a scheduled job.

## 10. Explainability & Auditability

- Every `EngineOutput` and `DecisionOutput` carries `engine_version` — when an engine's
  logic or an LLM prompt/model changes, its version increments, so
  `historical_accuracy`/`backtest_runs`/`benchmark_results` can all be sliced
  "before/after this specific change." Without this, an engine's accuracy history
  becomes meaningless the first time its logic changes.
- LLM-based engines must log the exact prompt template version, model identifier, and
  full evidence payload that produced each stored `EngineOutput` — not just the parsed
  result — so a backtest replay or an audit can reconstruct *why* the engine said what it
  said, not merely *that* it said it.

## 11. Product-surface note (not an architecture change, stated for clarity)

Per the resolved key decision above: Trader Profile and Investor Profile's existing,
already-shipped user-facing commentary (Turkish narrative, entry/SL/TP for trader,
per-horizon views for investor) is unaffected by this platform — it continues to be
generated and shown exactly as today. What changes is invisible to that surface: those
two modules' outputs are *additionally* captured as `EngineOutput`s and fed into the new
Decision Engine, whose separate, final BUY/SELL/HOLD verdict is shown **alongside** (not
instead of) the existing per-profile commentary.

## Open item deferred to the implementation-planning phase

`signals/decision.py`'s existing `DecisionOutput` dataclass
(`buy_probability`/`sell_probability`/`hold_probability` as three separate floats) predates
this design's single `decision: BUY|SELL|HOLD` enum field. Reconciling these two shapes
(replace vs. extend vs. derive one from the other) is a concrete decision left for
whoever writes the implementation plan for this spec — flagged here so it isn't
rediscovered as a surprise later.

## Out of scope for Phase 1 (explicitly deferred)

- Any code implementation whatsoever — this document is architecture only.
- Volume / Market Structure / Macro engines' actual logic (only their registry slot is
  designed here).
- The `StackedMetaModel` aggregation strategy (designed as a future pluggable option,
  not built).
- Any change to `HybridTradingEngine`'s live request/response shapes, caching behavior,
  or the `/signals/analyze`, `/signals/alerts` endpoints added in the prior
  investor/trader-alerts work — this platform sits alongside that work, consuming the
  same personas as additional engines, without modifying their existing contracts.
- iOS/UI changes of any kind.
- Deployment/infrastructure changes beyond adding Celery workers to the existing Docker
  Compose stack (no Kubernetes, no separate microservice, no new cloud infrastructure).
