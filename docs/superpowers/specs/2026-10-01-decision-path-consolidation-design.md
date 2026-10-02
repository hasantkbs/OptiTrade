# Decision Path Consolidation & SOLID Hardening — Design Spec

**Status:** Approved by user, ready for implementation planning.

**Relationship to other specs:** This is the first of three sequenced
sub-projects that together resume the roadmap `claude_build_spec.md` and
`investment_ai_system_schema.md` describe (whose later phases were
explicitly deferred during the `2026-09-30-src-layout-restructure-design.md`
Phase 0 work). This sub-project corresponds to hardening what already
exists under `claude_build_spec.md`'s Phase 8 ("Decision Engine") before
building the product-facing Phase 7/9 work on top of it.

- **Sub-project 1 (this spec):** backend decision-path consolidation,
  dead-code removal, SOLID hardening, test suite stabilization, ML model
  accuracy evaluation.
- **Sub-project 2 (future, separate spec):** the dual-asset-class
  (stocks vs. crypto) recommendation + news + "investment advisor"
  product feature, built on top of the now-consolidated decision path.
- **Sub-project 3 (future, separate spec):** web frontend update with
  charts, surfacing sub-project 2's output.
- **Explicitly not in this spec:** simplifying iOS's own UI to the
  leaner `DecisionOutput` shape (noted as a possible future, separate
  iOS-only project — raised during brainstorming, not scheduled).

## Mission

OptiTrade's backend currently computes a BUY/SELL/HOLD-style decision
for a symbol through **four independent, duplicated code paths**, each
reachable from a different HTTP route and each consumed by the iOS app.
Three of those paths have already started delegating their headline
score to the canonical `decision_engine` (added in an earlier session),
but none of the four has had its own now-redundant decision logic
actually removed, and the fourth (`core.analyzer.analyze()`, behind
`/analyze` and `/analyze/enhanced`) has not been touched at all — it
remains fully self-contained, by deliberate prior design (see
"Current State" below).

This sub-project finishes that consolidation: every route ends up
calling the single `decision_engine` for its decision, with a thin,
per-route **presentation layer** translating `decision_engine`'s
canonical `DecisionOutput` into whatever historical response shape that
route's existing clients (iOS) expect. No HTTP route, request schema, or
response schema changes. iOS requires zero code changes.
Alongside this, the full backend test suite is stabilized (including
the 4 currently-known pre-existing flaky failures), and the ML models
backing these decisions get an accuracy/performance evaluation separate
from code-level testing.

## Current State

Four analysis-producing code paths exist today, all reachable by iOS
(`OptiTradeiOS/OptiTradeiOS/Services/APIService.swift`):

| Route(s) | Backing code | Response shape | decision_engine status |
|---|---|---|---|
| `POST /analyze`, `POST /analyze/enhanced`, `POST /session/analyze` | `core/analyzer.py::analyze()` | `AnalysisResult` (rich: patterns, fibonacci, support/resistance, monte carlo, `decision_code` 5-level) | **Not wired** — fully self-contained scoring, deliberately kept separate (see below) |
| `GET /v2/analyze/{symbol}` | `v2/core/engine.py::TradingEngineV2` | `EngineResult` | Wired, with `SignalFusion` fallback-on-error (resilience, not duplication — see "What stays") |
| `POST /api/v1/signals/analyze` (`profile="trader"`) | `core/hybrid_engine.py::HybridTradingEngine` | `TradeRecommendation` | Wired (`_apply_canonical_decision`) |
| `POST /api/v1/signals/analyze` (`profile="investor"`) | `core/hybrid_engine.py::HybridTradingEngine` | `InvestorRecommendation` | **Not wired** — deliberately left untouched in the prior session pending this work |
| `POST /quant/analyze` | `pipeline/service.py::PipelineService` → `decision_engine` | `PipelineResponse` | Canonical path itself; no change needed |

**Why `/analyze` was deliberately left alone:** `main.py`'s own
docstring on the `/analyze` route states existing clients depend on
"this exact `AnalysisResult` shape and scoring behavior," and a
regression test
(`tests/test_main_backward_compatibility.py::test_legacy_analyze_endpoint_still_returns_the_original_analysisresult_shape`)
pins the response's field set. Reading that test shows it checks field
*presence*, not field *values* — so the "value pinning" was intent, not
an enforced guarantee. **During brainstorming, the user explicitly
approved overriding that intent**: `/analyze`/`/analyze/enhanced`'s
decision values (score, `decision_code`) may change once backed by
`decision_engine`, accepted as a deliberate, informed trade-off in
exchange for removing this last and largest duplicate decision path.
The field-presence test itself is unaffected (fields stay the same) and
needs no change.

**Addendum (post-implementation, final-review fix wave):** the route
table above lists `/analyze`/`/analyze/enhanced`/`/session/analyze` as
`core/analyzer.py::analyze()`'s only callers, but that function also
backs `/scan`, `/scan/bist`, and `/scan/crypto` (via `main.py`'s
`_analyze_safe`/`_parallel_scan`) and `core/sector_intelligence.py`'s
fast-analysis path. Now that `analyze()` is wired to `decision_engine`,
every scan request triggers one full `decide()` call (3 voting engines +
Feature Store lookups + a `decision_engine_executions` DB insert) **per
symbol scanned** — 15 symbols for `/scan/bist`, 10 for `/scan/crypto`.
This is functionally correct (both scan routes were verified working),
but it is a real, previously-undocumented increase in per-scan latency
and DB write volume that anyone changing scan-route performance or
`decision_engine` load characteristics should be aware of.

## Architecture

**The established pattern, generalized.** Two of the three already-wired
paths (`v2/core/engine.py`, `core/hybrid_engine.py`'s trader profile)
independently invented the same shape: call
`decision_engine.service.get_default_decision_engine().decide(symbol)`,
get back a `DecisionOutput`, and convert it with a small private
function (`_to_directional_score`, `_to_trade_signal`) into the route's
own legacy type. This sub-project:

1. **Extracts and completes that pattern** into one shared module,
   `core/analysis_presentation.py`, holding one converter function per
   legacy response shape:
   - `to_engine_result(decision_output, indicator_results, risk_score) -> EngineResult` (moved from `v2/core/engine.py::_to_directional_score`, adapted)
   - `to_trade_recommendation(decision_output, ...) -> TradeRecommendation` (moved from `core/hybrid_engine.py::_to_trade_signal`, adapted)
   - `to_investor_recommendation(decision_output, ...) -> InvestorRecommendation` (new — the currently-missing investor-profile converter)
   - `to_analysis_result(decision_output, presentation_extras) -> AnalysisResult` (new — the biggest piece, see below)
2. **Finishes wiring the two remaining paths** (`core/analyzer.py`,
   `core/hybrid_engine.py`'s investor profile) through
   `decision_engine` + their new converter, following the same
   try/except-with-fallback resilience shape already established in
   `v2/core/engine.py` (a `decision_engine` failure degrades to a
   simpler local computation rather than a hard 500 — this is
   intentional redundancy for *failure resilience*, not architectural
   duplication, and is preserved everywhere it already exists).
3. **Deletes the now-redundant decision logic** each converted path
   leaves behind once `decision_engine` is the actual source of the
   decision (the `get_decision(score)` / local score-accumulation logic
   in `core/analyzer.py`; any now-dead branches in `core/hybrid_engine.py`'s
   investor path).

**`core/analyzer.py::analyze()`'s split (the one non-trivial case):**
today this single function computes the decision score *and* several
presentation-only extras (fibonacci, support/resistance, pattern
recognition) from the same OHLC data in one pass, with pattern/news
deltas folded into the score before a decision is made. After this
change: the presentation-only extras keep being computed locally
exactly as today (they are not decision_engine's concern and have no
equivalent there), while the score/decision themselves come from
`decision_engine.decide(symbol)`. `to_analysis_result()` is the
converter that assembles the final `AnalysisResult` from both halves.

**SOLID mapping:**
- **SRP:** `decision_engine` decides; `analysis_presentation` formats for
  a specific consumer. Neither does the other's job.
- **DIP:** every route depends on `decision_engine`'s abstract
  `DecisionOutput` interface, never on another route's concrete engine
  class (today, e.g., nothing stops `core/analyzer.py` and
  `core/hybrid_engine.py` from silently diverging — after this change
  they share one decision source by construction).
- **OCP:** a future consumer (the web frontend in sub-project 3) adds
  one new converter function to `analysis_presentation.py` without
  touching `decision_engine` or any existing route.

**What stays exactly as-is (not duplication, don't touch):**
- `decision_engine`'s own internals (aggregation, weighting, registry) —
  already canonical, out of scope.
- The `SignalFusion`-on-error fallback in `v2/core/engine.py` (and the
  equivalent to be added to `core/analyzer.py`/`core/hybrid_engine.py`'s
  investor path) — resilience, not an architecture smell.
- Fibonacci/support-resistance/pattern-recognition computation in
  `core/analyzer.py` — presentation-only, no decision_engine equivalent,
  not a duplicate of anything.
- `/quant/analyze` and `pipeline/service.py` — already the canonical
  path this work is consolidating everything else toward.

## Data Flow (after this change)

```
Any route (/analyze, /analyze/enhanced, /session/analyze,
/v2/analyze/{symbol}, /api/v1/signals/analyze)
        │
        ▼
decision_engine.service.get_default_decision_engine().decide(symbol)
        │  (on failure: route-local fallback, as today)
        ▼
   DecisionOutput  ──────────────┐
        │                        │
        ▼                        ▼
 core/analysis_presentation.py   route-local presentation extras
   to_<shape>(...)               (fibonacci/S-R/patterns, indicator
        │                         breakdowns, risk_level, etc. — all
        ▼                         unchanged, still computed locally)
  <Route's existing response shape>
   (AnalysisResult / EngineResult / TradeRecommendation /
    InvestorRecommendation — byte-for-byte same Pydantic model as today)
        │
        ▼
      iOS (zero changes required)
```

## Testing Scope

Per the user's explicit confirmation, "test the model" covers three
distinct things, all in scope for this sub-project:

1. **Full pytest suite, green.** Includes fixing the 4 currently-known,
   pre-existing, environment-dependent flaky failures identified during
   PR #1's work: `test_no_news_result_is_also_cached` (live news-source
   dependency not fully mocked), `test_generated_secret_is_stable_within_a_process_but_differs_across_processes`
   (test design assumes stable secret across processes; by design the
   secret is process-random when `USERS_JWT_SECRET` is unset), `test_run_training_job_end_to_end`
   (sklearn `cross_val_predict` class-imbalance crash on this test's
   synthetic data), `test_monthly_report` (DB test-isolation ordering).
   Each needs its own root-cause fix, not a blanket skip.
   New tests are needed for `core/analysis_presentation.py`'s converters
   and for the two newly-wired paths (`core/analyzer.py`,
   `core/hybrid_engine.py`'s investor profile), following the existing
   backward-compatibility test file's pattern (field presence, not
   brittle exact-value pinning — consistent with the user's decision to
   let decision values change).
2. **ML model accuracy/performance evaluation.** A backtest-style
   accuracy report for the trained models backing these decisions
   (`xgb_signal_model.joblib`, `v2_xgb_model.joblib`, and
   `decision_engine`'s voting engines) against recent real market data —
   not just "does the code run," but "is the model's signal any good
   right now." Exact methodology (walk-forward window, metrics reported)
   to be detailed in the implementation plan.
3. **Live endpoint manual verification.** Once consolidated, exercise
   `/quant/analyze`, `/scan/bist`, `/scan/crypto`, and the newly-rewired
   legacy routes against the running production container with real
   symbols, confirming expected output shape and plausible values (not
   just unit-test mocks).

## Global Constraints (carried forward from the broader product vision)

These don't change anything in this sub-project's own code, but are
recorded here because they were raised and settled during brainstorming
and must bind sub-project 2 (which this spec's work enables):

- OptiTrade has, or is planning for, real users beyond the operator.
  Per `claude_build_spec.md`'s Phase 10, any user-facing output that
  reads as *personalized investment advice* must be framed as
  educational/informational, must avoid the literal phrase "investment
  advisory" (or local-market equivalents implying regulated advisory
  status), and must carry a visible risk disclaimer. A dedicated
  compliance/legal design review is required before sub-project 2 ships
  anything recommendation-shaped to real users, per that phase's own
  explicit instruction.

## Explicitly Out of Scope

- Any change to `decision_engine`'s own decision logic/weighting.
- Any iOS code change (by construction, route contracts are preserved).
- Simplifying iOS's UI to drop fibonacci/monte-carlo/pattern displays in
  favor of `DecisionOutput`'s leaner shape — raised during brainstorming
  as a possible future, separate project; not scheduled here.
- The dual-asset-class advisor feature itself (news surfacing,
  recommendations, "advisor" framing) — sub-project 2.
- The web frontend update — sub-project 3.
- `v2/ml/predictor.py:8` and `research/train_v2.py:88`'s pre-existing
  CWD-relative path bugs — already identified and explicitly ruled
  out-of-scope during PR #1's review; still out of scope here unless
  they start blocking this work directly.

## Known Limitations

- **`core.advanced_analysis.compute_recommendation`'s `action_code` is a
  separate, pre-existing composite signal that this consolidation does
  NOT route through `decision_engine`.** It blends `score` (now
  canonical, via `to_analysis_decision`) with ML confidence, Monte
  Carlo, and Chart AI into its own weighted composite
  (`0.40*score_norm + 0.25*ml_norm + 0.20*mc_norm + 0.15*ai_norm`) and
  applies its own independent 5-way thresholds to produce
  `action_code`/`suggested_position_pct`. Because 60% of that composite
  comes from non-canonical inputs, `/analyze/enhanced` can legitimately
  return a `decision_code` (e.g. `STRONG_BUY`) that disagrees with
  `recommendation.action_code` (e.g. `NEUTRAL`) for the same symbol.
  This is an accepted, pre-existing characteristic of that endpoint's
  response shape, not a defect this PR introduces or is responsible for
  closing — changing `compute_recommendation`'s own logic is out of
  scope here (see "Explicitly Out of Scope" above).

## Risks

- **Decision-value drift is the main risk, and it's accepted, not
  mitigated away.** `/analyze`/`/analyze/enhanced`'s BUY/SELL scores
  will likely shift once backed by `decision_engine` instead of
  `core.analyzer.analyze()`'s own formula. This is a known, approved
  trade-off (see "Why `/analyze` was deliberately left alone" above),
  not a bug to prevent — but it should be called out clearly in the
  implementation plan's commit messages and in any changelog, since
  it's a real behavior change for existing users even though no
  contract/schema changed.
- **`core/analyzer.py`'s split is the most delicate single edit.**
  Getting the "decision half" vs. "presentation half" boundary wrong
  (e.g., leaving a stale score variable that no longer feeds the
  response, or double-applying a pattern delta) is easy to miss without
  care. The implementation plan should include an explicit before/after
  trace of every variable `analyze()` currently computes.
- **ML accuracy evaluation may surface that a model is currently
  underperforming**, which is a legitimate, in-scope finding (not a
  plan failure) — the implementation plan should define what happens if
  it does (e.g., flag for retraining, not block this sub-project's
  completion on a full retrain).
