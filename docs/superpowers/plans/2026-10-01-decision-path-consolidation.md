# Decision Path Consolidation & SOLID Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse OptiTrade's 4 duplicated BUY/SELL/HOLD decision code paths onto the single canonical `decision_engine`, via a shared presentation layer that preserves every route's existing response shape (zero iOS changes); stabilize the full backend test suite (including 4 named pre-existing flaky failures); evaluate the accuracy of the models backing these decisions.

**Architecture:** A new `core/analysis_presentation.py` module holds pure converter functions (`DecisionOutput` → each route's legacy response type), moved from two call sites that already independently invented this pattern and extended to the two remaining ones. Each route keeps computing its own response fully as it does today (unchanged, serving as an automatic fallback), then overrides the headline decision fields with `decision_engine`'s output in a try/except block — the exact pattern `core/hybrid_engine.py::_apply_canonical_decision` already established for the trader profile.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, scikit-learn, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-01-decision-path-consolidation-design.md`

## Global Constraints

- **Zero iOS code changes.** Every HTTP route's path, request schema, and response schema stay byte-identical. `OptiTradeiOS/OptiTradeiOS/Services/APIService.swift` is never touched by this plan.
- **Decision-value drift on `/analyze`/`/analyze/enhanced` is accepted, not a bug.** Once backed by `decision_engine`, their `decision`/`decision_code`/`score` values will likely differ from `core.analyzer.analyze()`'s own formula. This is a deliberate, user-approved trade-off (see spec's "Why `/analyze` was deliberately left alone"), not something to prevent or work around.
- **Fallback-on-error resilience must be preserved everywhere it exists, and added everywhere newly wired.** A `decision_engine` failure (infra down, zero valid votes) must degrade to each route's own pre-existing local computation, never a hard 500. Follow `v2/core/engine.py:150-164`'s exact try/except shape.
- **`decision_engine`'s single decision has no per-horizon concept.** Where a route exposes multiple time horizons (`core/hybrid_engine.py`'s investor profile: 1-week/1-month/1-year), only the single horizon closest in meaning to a current-conditions vote (1-week) is overridden. The others stay fully LLM-driven, untouched.
- **This repo IS the production host** (`mayasoftlnx01`, `optitrade-api` container running live). All verification in this plan uses an isolated Docker Compose project name (`-p dpc-verify` or similar, never the bare default project name) and is torn down afterward. Never run `docker compose down` / `docker compose up` without `-p` in this plan — that targets the live production stack.
- Every commit message ends with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Working directory: a fresh isolated worktree, created via `superpowers:using-git-worktrees` at execution time (same pattern as the prior `2026-09-30-src-layout-restructure` plan / PR #1).

---

### Task 1: `core/analysis_presentation.py` — extract and complete the converter pattern

**Files:**
- Create: `backend/src/core/analysis_presentation.py`
- Modify: `backend/src/v2/core/engine.py:103-112` (delete `_to_directional_score`, import from new module)
- Modify: `backend/src/core/hybrid_engine.py:60-74` (delete `_to_trade_signal`, import from new module)
- Test: `backend/src/tests/test_analysis_presentation.py` (new)

**Interfaces:**
- Produces:
  - `to_directional_score(decision_output: DecisionOutput) -> Tuple[float, float]`
  - `to_trade_signal(decision_output: DecisionOutput) -> Tuple[TradeSignal, int]`
  - `to_analysis_decision(decision_output: DecisionOutput) -> Tuple[str, str, int]` — `(decision_text, decision_code, score)`
- Consumes: `decision_engine.models.DecisionOutput`, `decision_engine.models.Prediction`, `core.ai_trader_persona.TradeSignal` (all pre-existing).

- [ ] **Step 1: Write the failing tests**

```python
# backend/src/tests/test_analysis_presentation.py
from datetime import datetime, timezone

import pytest

from core.analysis_presentation import to_analysis_decision, to_directional_score, to_trade_signal
from core.ai_trader_persona import TradeSignal
from decision_engine.models import DecisionOutput, Prediction


def _decision_output(decision: Prediction, confidence: float) -> DecisionOutput:
    return DecisionOutput(
        symbol="TEST", decision=decision, confidence=confidence,
        expected_return=0.0, expected_volatility=0.1,
        aggregation_strategy_version="test", data_sufficiency=1.0,
    )


def test_to_directional_score_buy_is_positive():
    score, confidence = to_directional_score(_decision_output(Prediction.BUY, 0.8))
    assert score == pytest.approx(0.8)
    assert confidence == pytest.approx(0.8)


def test_to_directional_score_sell_is_negative():
    score, confidence = to_directional_score(_decision_output(Prediction.SELL, 0.6))
    assert score == pytest.approx(-0.6)
    assert confidence == pytest.approx(0.6)


def test_to_directional_score_hold_is_zero():
    score, confidence = to_directional_score(_decision_output(Prediction.HOLD, 0.9))
    assert score == 0.0
    assert confidence == pytest.approx(0.9)


def test_to_trade_signal_strong_buy_above_threshold():
    signal, confidence_score = to_trade_signal(_decision_output(Prediction.BUY, 0.9))
    assert signal == TradeSignal.STRONG_BUY
    assert confidence_score == 90


def test_to_trade_signal_plain_buy_below_threshold():
    signal, confidence_score = to_trade_signal(_decision_output(Prediction.BUY, 0.5))
    assert signal == TradeSignal.BUY
    assert confidence_score == 50


def test_to_trade_signal_strong_sell_above_threshold():
    signal, confidence_score = to_trade_signal(_decision_output(Prediction.SELL, 0.85))
    assert signal == TradeSignal.STRONG_SELL
    assert confidence_score == 85


def test_to_trade_signal_hold_is_neutral():
    signal, confidence_score = to_trade_signal(_decision_output(Prediction.HOLD, 0.3))
    assert signal == TradeSignal.NEUTRAL
    assert confidence_score == 30


def test_to_analysis_decision_maps_strong_buy():
    decision_text, decision_code, score = to_analysis_decision(_decision_output(Prediction.BUY, 0.9))
    assert decision_code == "STRONG_BUY"
    assert decision_text == "GUCLU AL (LONG)"
    assert score == 90


def test_to_analysis_decision_maps_plain_sell():
    decision_text, decision_code, score = to_analysis_decision(_decision_output(Prediction.SELL, 0.5))
    assert decision_code == "SELL"
    assert decision_text == "SAT"
    assert score == 50


def test_to_analysis_decision_maps_hold_to_neutral():
    decision_text, decision_code, score = to_analysis_decision(_decision_output(Prediction.HOLD, 0.2))
    assert decision_code == "NEUTRAL"
    assert decision_text == "NOTR / IZLE"
    assert score == 20
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_analysis_presentation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.analysis_presentation'`

- [ ] **Step 3: Create `core/analysis_presentation.py`**

```python
"""OptiTrade — Decision Engine presentation layer.

Pure functions that convert `decision_engine.models.DecisionOutput` (the
single canonical decision authority — see docs/architecture/gap-
analysis.md section 2) into each legacy route's own historical response
shape. Every HTTP route keeps its own request/response contract exactly
as-is; only which computation is authoritative for the headline decision
fields changes. No route, request schema, or response schema changes
because of this module — see docs/superpowers/specs/2026-10-01-
decision-path-consolidation-design.md.

This module has no state and no I/O - every function here is a pure
mapping from one Pydantic model to a tuple of plain values, so it is
trivially unit-testable without a database, Feature Store, or live
decision_engine connection.
"""
from __future__ import annotations

import os
from typing import Tuple

from core.ai_trader_persona import TradeSignal
from decision_engine.models import DecisionOutput, Prediction

# Same "strong" confidence bar intelligence/config.py's
# INTELLIGENCE_STRONG_BUY_CONFIDENCE_THRESHOLD uses (default 0.75),
# applied symmetrically to SELL too - duplicated as its own env-driven
# constant rather than importing intelligence.config here, matching the
# precedent this constant is moved from (core/hybrid_engine.py).
_STRONG_SIGNAL_CONFIDENCE_THRESHOLD = float(
    os.getenv("INTELLIGENCE_STRONG_BUY_CONFIDENCE_THRESHOLD", "0.75")
)

_DECISION_CODE_TEXT = {
    "STRONG_BUY": "GUCLU AL (LONG)",
    "BUY": "AL",
    "NEUTRAL": "NOTR / IZLE",
    "SELL": "SAT",
    "STRONG_SELL": "GUCLU SAT (SHORT)",
}


def to_directional_score(decision_output: DecisionOutput) -> Tuple[float, float]:
    """Encodes the Decision Engine's discrete decision+confidence into
    a signed-magnitude scale: BUY/SELL set the sign, confidence
    (already 0..1) sets the magnitude, HOLD is exactly 0.0. Matches
    `v2.models.schemas.IndicatorOutput.score`'s own [-1, 1] bound and
    the shape `v2.core.engine.SignalFusion.aggregate()` already
    produces (a confidence-weighted signed score) - so `EngineResult`'s
    contract is unchanged, only which computation is authoritative for
    it. Moved here from `v2.core.engine._to_directional_score` (Task 1
    of docs/superpowers/plans/2026-10-01-decision-path-consolidation.md)."""
    sign = {Prediction.BUY: 1.0, Prediction.HOLD: 0.0, Prediction.SELL: -1.0}[decision_output.decision]
    return sign * decision_output.confidence, decision_output.confidence


def to_trade_signal(decision_output: DecisionOutput) -> Tuple[TradeSignal, int]:
    """Maps the Decision Engine's discrete (decision, confidence) onto
    the five-way `TradeSignal` vocabulary. `Prediction` is only
    BUY/HOLD/SELL - STRONG_BUY/STRONG_SELL are derived here from
    confidence crossing the same bar `intelligence.opportunity.
    classify_opportunity` uses for STRONG_BUY_BIAS, applied to both
    directions since a trade signal (unlike that product-facing
    "opportunity" label) needs to be symmetric. Moved here from
    `core.hybrid_engine._to_trade_signal` (Task 1 of
    docs/superpowers/plans/2026-10-01-decision-path-consolidation.md) -
    used directly by three callers: the trader profile's
    `TradeRecommendation`, the investor profile's 1-week `HorizonView`
    override (both in `core.hybrid_engine`), and `to_analysis_decision`
    below."""
    confidence_score = round(decision_output.confidence * 100)
    if decision_output.decision == Prediction.HOLD:
        return TradeSignal.NEUTRAL, confidence_score
    is_strong = decision_output.confidence >= _STRONG_SIGNAL_CONFIDENCE_THRESHOLD
    if decision_output.decision == Prediction.BUY:
        return (TradeSignal.STRONG_BUY if is_strong else TradeSignal.BUY), confidence_score
    return (TradeSignal.STRONG_SELL if is_strong else TradeSignal.SELL), confidence_score


def to_analysis_decision(decision_output: DecisionOutput) -> Tuple[str, str, int]:
    """Maps the Decision Engine's output onto `models.schemas.
    AnalysisResult`'s three headline fields: `(decision, decision_code,
    score)`. Reuses `to_trade_signal`'s exact BUY/SELL/HOLD→five-way
    mapping (the `TradeSignal` enum's values are byte-identical to
    `AnalysisResult.decision_code`'s documented vocabulary: STRONG_BUY|
    BUY|NEUTRAL|SELL|STRONG_SELL - see core.scoring.get_decision, which
    this supersedes as the authoritative source for `core.analyzer.
    analyze()`'s decision fields, keeping that function's own
    `get_decision(score)` call only as its error-fallback)."""
    signal, confidence_score = to_trade_signal(decision_output)
    decision_code = signal.value
    return _DECISION_CODE_TEXT[decision_code], decision_code, confidence_score
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_analysis_presentation.py -v`
Expected: 9 passed

- [ ] **Step 5: Update `v2/core/engine.py` to use the shared module**

In `backend/src/v2/core/engine.py`, delete the `_to_directional_score` function (lines 103-112). `Tuple` (from the `from typing import Any, Dict, List, Optional, Tuple` line at the top) is used by nothing else in this file — remove `Tuple` from that import line too. Add to the imports:

```python
from core.analysis_presentation import to_directional_score
```

Change the one call site (was `_to_directional_score(decision_output)`) to `to_directional_score(decision_output)`:

```python
            decision_output = await asyncio.to_thread(decision_engine.decide, symbol)
            aggregated_score, confidence = to_directional_score(decision_output)
```

- [ ] **Step 6: Update `core/hybrid_engine.py` to use the shared module**

In `backend/src/core/hybrid_engine.py`, delete the `_to_trade_signal` function and the `_STRONG_SIGNAL_CONFIDENCE_THRESHOLD` constant (lines 49-74 — both move to `analysis_presentation.py`, already done in Step 3). `TradeSignal` (from `core.ai_trader_persona`), `DecisionOutput`/`Prediction` (from `decision_engine.models`), and `Tuple` (from `typing`) were used only inside `_to_trade_signal` in this file: remove `TradeSignal` from the `from core.ai_trader_persona import AITraderPersona, TradeRecommendation, TradeSignal` line (becomes `from core.ai_trader_persona import AITraderPersona, TradeRecommendation`); remove the `from decision_engine.models import DecisionOutput, Prediction` line entirely (line 45 — `DecisionOutput`'s only other appearance is inside a comment, not code); remove `Tuple` from the `from typing import Any, Dict, List, Literal, Optional, Tuple, Union` line (becomes `from typing import Any, Dict, List, Literal, Optional, Union`). Add to the imports:

```python
from core.analysis_presentation import to_trade_signal
```

Change the one call site in `_apply_canonical_decision` (was `_to_trade_signal(decision_output)`):

```python
        signal, confidence_score = to_trade_signal(decision_output)
```

- [ ] **Step 7: Run the existing test suites for both touched files to confirm zero behavior change**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_v2_engine.py src/tests/test_hybrid_engine.py src/tests/unit/test_hybrid_engine.py src/tests/test_analysis_presentation.py -v`
Expected: all PASS, identical pass/fail set to before this task (this is a pure relocation — no caller's observable behavior changes)

- [ ] **Step 8: Commit**

```bash
cd backend && git add src/core/analysis_presentation.py src/core/hybrid_engine.py src/v2/core/engine.py src/tests/test_analysis_presentation.py
git commit -m "refactor: extract shared decision_engine presentation layer

Moves v2/core/engine.py's _to_directional_score and core/hybrid_engine.py's
_to_trade_signal into a new core/analysis_presentation.py module (both were
independently-invented copies of the same DecisionOutput->legacy-shape
pattern). Adds to_analysis_decision(), the converter Task 2 needs for
core/analyzer.py. Pure relocation - zero behavior change, confirmed by the
existing test suites for both touched call sites passing unchanged.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Wire `core/analyzer.py::analyze()` to `decision_engine`

**Files:**
- Modify: `backend/src/core/analyzer.py:1-16` (module docstring), `:245-260` (return statement — add override block before it)
- Modify: `backend/src/main.py` (the `/analyze` route's docstring, ~line 1293-1309 — update to reflect the new behavior)
- Test: `backend/src/tests/test_analyzer_canonical_decision.py` (new)

**Interfaces:**
- Consumes: `core.analysis_presentation.to_analysis_decision` (Task 1), `decision_engine.service.get_default_decision_engine` (pre-existing).

- [ ] **Step 1: Write the failing test**

```python
# backend/src/tests/test_analyzer_canonical_decision.py
"""core.analyzer.analyze() now defers its headline decision/decision_code/
score to decision_engine (see docs/superpowers/specs/2026-10-01-decision-
path-consolidation-design.md) - these tests characterize that override and
its fallback, using a fake decision_engine so no real Feature Store/
network calls are needed. analyze()'s OWN pattern/support-resistance/
fibonacci/news computation is untouched by this change and is already
covered by tests/test_main_backward_compatibility.py's shape-presence
test - not re-asserted here."""
from unittest.mock import patch

import pandas as pd
import pytest

from decision_engine.models import DecisionOutput, Prediction


def _fake_history():
    idx = pd.date_range("2026-01-01", periods=120, freq="D")
    return pd.DataFrame({
        "Open": [100.0 + i * 0.1 for i in range(120)],
        "High": [101.0 + i * 0.1 for i in range(120)],
        "Low": [99.0 + i * 0.1 for i in range(120)],
        "Close": [100.5 + i * 0.1 for i in range(120)],
        "Volume": [1_000_000 for _ in range(120)],
    }, index=idx)


class _FakeDecisionEngine:
    def __init__(self, decision_output):
        self._decision_output = decision_output

    def decide(self, symbol):
        return self._decision_output


def _decision_output(decision: Prediction, confidence: float) -> DecisionOutput:
    return DecisionOutput(
        symbol="AAPL", decision=decision, confidence=confidence,
        expected_return=0.0, expected_volatility=0.1,
        aggregation_strategy_version="test", data_sufficiency=1.0,
    )


@patch("core.analyzer.fetch_history", return_value=_fake_history())
@patch("decision_engine.service.get_default_decision_engine")
def test_analyze_uses_decision_engine_decision_code(mock_get_engine, _mock_history):
    mock_get_engine.return_value = _FakeDecisionEngine(_decision_output(Prediction.BUY, 0.9))
    from core.analyzer import analyze

    result = analyze(symbol="AAPL", asset_type="stock", include_news=False)
    assert result is not None
    assert result.decision_code == "STRONG_BUY"
    assert result.score == 90


@patch("core.analyzer.fetch_history", return_value=_fake_history())
@patch("decision_engine.service.get_default_decision_engine")
def test_analyze_falls_back_to_local_score_on_decision_engine_failure(mock_get_engine, _mock_history):
    mock_get_engine.side_effect = RuntimeError("feature store unreachable")
    from core.analyzer import analyze

    result = analyze(symbol="AAPL", asset_type="stock", include_news=False)
    assert result is not None
    # Fallback still produces a valid 5-way decision_code from the
    # local get_decision(score) path - exact value depends on the
    # synthetic fixture's indicators, so only the vocabulary is asserted.
    assert result.decision_code in {"STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_analyzer_canonical_decision.py -v`
Expected: FAIL — `test_analyze_uses_decision_engine_decision_code` fails because `analyze()` doesn't call `decision_engine` yet (decision_code comes from the local fallback regardless of the mock)

- [ ] **Step 3: Add the canonical-decision override to `core/analyzer.py`**

Update the module docstring (lines 1-16) to:

```python
"""
OptiTrade — legacy scoring engine (pre-pipeline presentation source).

Backs `main.py`'s `POST /analyze`, `POST /analyze/enhanced`, and
`POST /session/analyze`. Still computes its own indicators, pattern
recognition, support/resistance, fibonacci, ML confidence, and news
analysis locally (none of these have a decision_engine equivalent -
they are presentation/evidence, not the decision itself). As of
docs/superpowers/specs/2026-10-01-decision-path-consolidation-design.md,
the headline `decision`/`decision_code`/`score` fields are no longer
computed from this file's own `compute_score()`/`get_decision()` -
they come from `decision_engine`, the single canonical decision
authority (see docs/architecture/gap-analysis.md section 2), with the
local `get_decision(score)` computation kept only as the fallback value
if decision_engine is unreachable. This is a deliberate, user-approved
behavior change from this function's own prior scores (see the spec's
"Why /analyze was deliberately left alone" section) - existing clients'
exact score/decision VALUES may shift; the `AnalysisResult` field set
itself does not (see tests/test_main_backward_compatibility.py).
"""
from typing import Optional
import logging

from core.analysis_presentation import to_analysis_decision
from data.fetcher import fetch_history, get_balance_status
```

(keep the rest of the existing imports exactly as they are below the new `core.analysis_presentation` import)

Replace the `return AnalysisResult(` statement's preceding section — insert this block immediately before `return AnalysisResult(` (i.e., right after the `news_analysis` dict construction's inputs are ready, which today is right after the news analysis try/except block ends and before the final `return`):

```python
    # ── Kanonik karar ─────────────────────────────────────────────────────────
    # decision_engine is the single decision authority (see
    # docs/architecture/gap-analysis.md section 2) - everything computed
    # above (score/decision/decision_code via compute_score()+get_decision(),
    # pattern_delta, news_delta) stays exactly as it was and becomes this
    # override's fallback value if decision_engine is unreachable, rather
    # than being deleted - same resilience pattern as v2/core/engine.py's
    # SignalFusion fallback and core/hybrid_engine.py's
    # _apply_canonical_decision. long_signals/short_signals/
    # scoring_breakdown/patterns/support_resistance/fibonacci are
    # unaffected either way - they are explanatory evidence, not the
    # decision, and decision_engine has no equivalent for them.
    try:
        from decision_engine.service import get_default_decision_engine

        canonical_output = get_default_decision_engine().decide(symbol)
        decision, decision_code, score = to_analysis_decision(canonical_output)
    except Exception as exc:
        logger.error(f"{symbol}: decision engine yetkisi uygulanamadi, yerel skor korunuyor: {exc}")

    return AnalysisResult(
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_analyzer_canonical_decision.py -v`
Expected: 2 passed

- [ ] **Step 5: Update `/analyze`'s route docstring in `main.py`**

Find the `/analyze` route (`@app.post("/analyze", response_model=AnalysisResult)`, around line 1293). Replace its docstring (the triple-quoted string explaining "Deliberately NOT unified with the new pipeline...") with:

```python
    """`core.analyzer.analyze()` backs this route - its own indicators/
    pattern-recognition/support-resistance/fibonacci/ML-confidence/news
    computation stays local (no decision_engine equivalent exists for
    these), but as of docs/superpowers/specs/2026-10-01-decision-path-
    consolidation-design.md the headline `decision`/`decision_code`/
    `score` fields come from `decision_engine`, the single canonical
    decision authority, not this function's own formula. This is a
    deliberate, approved behavior change: existing clients' exact
    decision VALUES may shift; the `AnalysisResult` field set itself
    is unchanged (see tests/test_main_backward_compatibility.py's
    `test_legacy_analyze_endpoint_still_returns_the_original_
    analysisresult_shape`, which checks field presence, not values).
    `pipeline.service.PipelineService` (behind `/quant/analyze`) remains
    the sole canonical path for anything outside this pinned response
    contract."""
```

- [ ] **Step 6: Run the backward-compatibility suite to confirm the contract still holds**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_main_backward_compatibility.py -v`
Expected: all PASS (field presence only — values are allowed to differ per Global Constraints)

- [ ] **Step 7: Commit**

```bash
cd backend && git add src/core/analyzer.py src/main.py src/tests/test_analyzer_canonical_decision.py
git commit -m "refactor: wire core/analyzer.py's analyze() to decision_engine

/analyze, /analyze/enhanced, and /session/analyze's headline decision/
decision_code/score now come from decision_engine (the single canonical
decision authority) instead of this function's own compute_score()/
get_decision() formula, with that local computation kept as the
fallback value if decision_engine is unreachable - same override-after-
construction pattern core/hybrid_engine.py::_apply_canonical_decision
already established. Pattern recognition, support/resistance,
fibonacci, ML confidence, and news analysis are untouched (no
decision_engine equivalent exists for them).

This is a deliberate, user-approved behavior change: decision/score
VALUES for /analyze and /analyze/enhanced may now differ from before.
The AnalysisResult response SHAPE is unchanged (confirmed by
tests/test_main_backward_compatibility.py, which asserts field
presence, not values) - no iOS code change is required.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Wire the investor profile's 1-week horizon to `decision_engine`

**Files:**
- Modify: `backend/src/core/hybrid_engine.py:211-217` (`_process_symbol`'s investor branch), add new method after `_apply_canonical_decision` (after line 258)
- Test: `backend/src/tests/test_hybrid_engine.py` (add new test cases)

**Interfaces:**
- Consumes: `core.analysis_presentation.to_trade_signal` (Task 1).
- Produces: `HybridTradingEngine._apply_canonical_decision_to_investor_horizon(symbol, recommendation: InvestorRecommendation) -> InvestorRecommendation`

- [ ] **Step 1: Delete the now-contradicted pre-existing test**

`test_hybrid_engine.py` already has a test asserting the OLD behavior this task replaces — its premise becomes false once Task 3 lands, so it must be deleted, not kept alongside the new tests:

```python
def test_investor_recommendation_is_not_touched_by_the_decision_engine():
    """profile="investor" produces three independent per-horizon
    signals (see core/investor_persona.py's own docstring on why they
    may legitimately disagree) - the Decision Engine has no per-horizon
    concept, so this path is deliberately left untouched by this
    consolidation step. A FakeDecisionEngine that would raise if ever
    called proves it never is."""
    class ExplodingDecisionEngine:
        def decide(self, symbol: str) -> DecisionOutput:
            raise AssertionError("Decision Engine must not be consulted for profile='investor'")

    engine, _, _, _ = _build_engine(
        [_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=ExplodingDecisionEngine(),
    )

    result = engine.run(["AAPL"], profile="investor")

    assert isinstance(result[0], InvestorRecommendation)
```

Delete this entire function from `backend/src/tests/test_hybrid_engine.py` (it sits between the trader-profile override tests and the "profile=\"investor\" — separate persona, separate cache" section comment).

- [ ] **Step 2: Write the failing tests**

Add these two test cases to `backend/src/tests/test_hybrid_engine.py`, in the same place the deleted test was, reusing this file's own existing `_build_engine`/`FakeDecisionEngine`/`_make_decision_output`/`_make_investor_recommendation` fixtures exactly as the trader-profile tests above them already do:

```python
def test_investor_profile_1_week_horizon_is_overridden_by_the_decision_engine():
    """profile="investor" produces three independent per-horizon signals
    (see core/investor_persona.py's own docstring on why they may
    legitimately disagree) - the Decision Engine has no per-horizon
    concept, so only horizon_1_week (closest match to a current-
    conditions vote) is overridden; horizon_1_month/horizon_1_year/
    investor_commentary stay exactly as the LLM produced them."""
    decision_engine = FakeDecisionEngine(_make_decision_output("AAPL", Prediction.SELL, confidence=0.9))
    engine, _, _, _ = _build_engine(
        [_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=decision_engine,
    )

    result = engine.run(["AAPL"], profile="investor")

    assert decision_engine.calls == ["AAPL"]
    rec = result[0]
    # FakeInvestorPersona/_make_investor_recommendation said BUY/60 for
    # every horizon - the Decision Engine's SELL/0.9 must win, but only
    # for horizon_1_week.
    assert rec.horizon_1_week.signal == TradeSignal.STRONG_SELL
    assert rec.horizon_1_week.confidence_score == 90
    # horizon_1_month/horizon_1_year are untouched - still the LLM's
    # original BUY/60.
    assert rec.horizon_1_month.signal == TradeSignal.BUY
    assert rec.horizon_1_month.confidence_score == 60
    assert rec.horizon_1_year.signal == TradeSignal.BUY
    assert rec.horizon_1_year.confidence_score == 60


def test_investor_profile_falls_back_to_llm_horizon_1_week_when_decision_engine_fails():
    decision_engine = FakeDecisionEngine(raises=RuntimeError("feature store unavailable"))
    engine, _, _, _ = _build_engine(
        [_make_scanned("AAPL")], {"current_price": 100.0, "atr_daily": 2.0},
        decision_engine=decision_engine,
    )

    result = engine.run(["AAPL"], profile="investor")

    # Decision Engine blew up - horizon_1_week keeps the LLM's own
    # (uncorroborated) signal/confidence_score, same as the trader
    # profile's fallback behavior.
    assert result[0].horizon_1_week.signal == TradeSignal.BUY
    assert result[0].horizon_1_week.confidence_score == 60
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_hybrid_engine.py -k investor_profile -v`
Expected: FAIL — `horizon_1_week` still has the raw LLM signal (BUY/60), not the decision_engine override, because the investor branch doesn't call anything yet

- [ ] **Step 4: Implement the override in `core/hybrid_engine.py`**

In `_process_symbol` (around line 211-217), change:

```python
            else:
                recommendation = self.investor_persona.generate_recommendation(
                    symbol=symbol,
                    market_regime=scanned.regime,
                    analysis=analysis,
                    news_sentiment=news_sentiment,
                )
```

to:

```python
            else:
                recommendation = self.investor_persona.generate_recommendation(
                    symbol=symbol,
                    market_regime=scanned.regime,
                    analysis=analysis,
                    news_sentiment=news_sentiment,
                )
                recommendation = self._apply_canonical_decision_to_investor_horizon(symbol, recommendation)
```

Add this new method immediately after `_apply_canonical_decision` (after line 258, before `_get_or_check_alert`):

```python
    def _apply_canonical_decision_to_investor_horizon(
        self, symbol: str, recommendation: InvestorRecommendation
    ) -> InvestorRecommendation:
        """Overrides ONLY `horizon_1_week`'s signal/confidence_score with
        the Decision Engine's statistical vote - `decision_engine.decide()`
        produces one undifferentiated-by-horizon decision, closest in
        meaning to a current-conditions (short-horizon) vote, so only the
        1-week horizon is overridden (see docs/superpowers/specs/2026-10-01-
        decision-path-consolidation-design.md's Global Constraints).
        `horizon_1_month`/`horizon_1_year`/`investor_commentary` stay
        fully LLM-driven - decision_engine has no medium/long-horizon
        concept to supersede them with (see claude_build_spec.md Phase 1's
        not-yet-built models/medium_horizon, models/long_horizon).

        A Decision Engine failure falls back to the LLM's own
        horizon_1_week signal rather than dropping the recommendation -
        same resilience shape as `_apply_canonical_decision` above."""
        try:
            decision_engine = self.decision_engine
            if decision_engine is None:
                from decision_engine.service import get_default_decision_engine

                decision_engine = get_default_decision_engine()
            decision_output = decision_engine.decide(symbol)
        except Exception as exc:
            logger.error(
                f"{symbol}: decision engine yetkisi (investor 1-hafta) uygulanamadi, LLM sinyali korunuyor: {exc}"
            )
            return recommendation
        signal, confidence_score = to_trade_signal(decision_output)
        updated_horizon = recommendation.horizon_1_week.model_copy(
            update={"signal": signal, "confidence_score": confidence_score}
        )
        return recommendation.model_copy(update={"horizon_1_week": updated_horizon})
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_hybrid_engine.py -v`
Expected: all PASS, including the 2 new investor-profile tests (and the deleted `test_investor_recommendation_is_not_touched_by_the_decision_engine` no longer appears in the run at all)

- [ ] **Step 6: Commit**

```bash
cd backend && git add src/core/hybrid_engine.py src/tests/test_hybrid_engine.py
git commit -m "feat: wire investor profile's 1-week horizon to decision_engine

HybridTradingEngine's investor profile (profile=\"investor\") now overrides
horizon_1_week's signal/confidence_score with decision_engine's vote,
the same way the trader profile already does - decision_engine has no
per-horizon concept, so only the 1-week horizon (closest match to a
current-conditions vote) is overridden; horizon_1_month/horizon_1_year/
investor_commentary stay fully LLM-driven. Falls back to the LLM's own
horizon_1_week signal if decision_engine is unreachable.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Fix the 4 pre-existing flaky tests

**Files:**
- Modify: `backend/src/tests/test_core_news_analyzer_cache.py`
- Modify: `backend/src/tests/test_users_config_jwt_secret.py`
- Modify: `backend/src/ml_training/calibration/calibrator.py:72-101`
- Modify: `backend/src/tests/test_paper_trading_reports.py`

**Interfaces:** None (each fix is self-contained; no cross-task interfaces).

- [ ] **Step 1: Fix `test_no_news_result_is_also_cached`**

Root cause: `core.news_analyzer.analyze_news()` calls `_fetch_combined_news()`, which calls BOTH `_fetch_yfinance_news()` (the only function this test mocks) AND two live `_fetch_google_news_rss()` calls — unmocked, hitting real Google News RSS over the network, which can return real results for the test's placeholder symbol "ZZZZ".

In `backend/src/tests/test_core_news_analyzer_cache.py`, find `test_no_news_result_is_also_cached` and change:

```python
def test_no_news_result_is_also_cached(monkeypatch):
    calls = []
    monkeypatch.setattr("core.news_analyzer._fetch_yfinance_news", lambda symbol, max_news=15: calls.append(symbol) or [])
```

to:

```python
def test_no_news_result_is_also_cached(monkeypatch):
    calls = []
    monkeypatch.setattr("core.news_analyzer._fetch_yfinance_news", lambda symbol, max_news=15: calls.append(symbol) or [])
    # _fetch_combined_news also calls _fetch_google_news_rss (live network
    # RSS) twice - unmocked, it can return real results for "ZZZZ" and
    # break this test's "no news" premise. Mock it too.
    monkeypatch.setattr("core.news_analyzer._fetch_google_news_rss", lambda *args, **kwargs: [])
```

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_core_news_analyzer_cache.py -v`
Expected: all PASS

- [ ] **Step 2: Fix `test_generated_secret_is_stable_within_a_process_but_differs_across_processes`**

Root cause: `backend/.env` has a real `USERS_JWT_SECRET` set. The test does `monkeypatch.delenv("USERS_JWT_SECRET", raising=False)` to remove it from the process environment, but `UsersConfig.from_env()` internally calls bare `load_dotenv()` (no path, no `override=True`) — which re-reads `backend/.env` from disk and repopulates `os.environ["USERS_JWT_SECRET"]` with the REAL secret, since the key is "absent" from `monkeypatch`'s point of view. `UsersConfig.from_env()` then uses that real secret directly (`os.getenv("USERS_JWT_SECRET") or ...` short-circuits), while `UsersConfig()`'s bare constructor (which ignores env entirely) calls the ephemeral generator fresh — producing two genuinely different values.

In `backend/src/tests/test_users_config_jwt_secret.py`, update the autouse fixture to also prevent `from_env()`'s internal `load_dotenv()` from re-reading the real `.env` file:

```python
@pytest.fixture(autouse=True)
def _reset_ephemeral_secret_cache(monkeypatch):
    """users.config memoizes the generated secret at module level so
    encode/decode stay consistent within one process (see the module's
    own docstring) - reset that cache before/after each test here so
    tests don't leak their generated secret into each other or into the
    rest of the suite.

    Also no-ops users.config.load_dotenv for the duration of each test:
    UsersConfig.from_env() calls bare load_dotenv() (no override), which
    re-reads backend/.env from disk and would repopulate
    USERS_JWT_SECRET with this host's REAL configured secret right after
    a test's own monkeypatch.delenv("USERS_JWT_SECRET") removed it -
    defeating every "unset" test in this file without this guard."""
    import users.config as users_config

    monkeypatch.setattr(users_config, "_ephemeral_jwt_secret", None)
    monkeypatch.setattr(users_config, "load_dotenv", lambda *args, **kwargs: None)
    yield
    monkeypatch.setattr(users_config, "_ephemeral_jwt_secret", None)
```

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_users_config_jwt_secret.py -v`
Expected: all PASS

- [ ] **Step 3: Fix `test_run_training_job_end_to_end`**

Root cause: `ModelCalibrator.calibrate()` encodes `y_cal` via the trainer's full `_label_encoder` (fit earlier on the complete label space, e.g. 3 DIRECTION classes), but the frozen, already-trained estimator (`trainer._model`) may only have been trained on a SUBSET of those classes (e.g. 2 of 3, if the training split's small sample happened not to include the rarest class). When the calibration split then legitimately contains a row of that third, model-unseen class, `CalibratedClassifierCV`'s internal cross-validation produces a fold whose `predict_proba` output has more columns than the frozen estimator's known `classes_`, crashing deep in sklearn's fold-stitching logic (`_enforce_prediction_order`, `IndexError`).

In `backend/src/ml_training/calibration/calibrator.py`, add this guard in `calibrate()` immediately after `y_cal_encoded = trainer._encode_y(y_cal, fit_encoder=False)` (around line 86) and before the `cv = max(...)` line:

```python
        y_cal_encoded = trainer._encode_y(y_cal, fit_encoder=False)

        # A small, class-imbalanced training split can leave the frozen
        # estimator never having seen one of the full label space's
        # rarer classes (e.g. a 3-way DIRECTION label's rare middle
        # band). If the held-out *calibration* split then happens to
        # contain that class, CalibratedClassifierCV's internal cross-
        # validation produces a fold whose predict_proba output has
        # more columns than the frozen estimator's known classes_,
        # crashing in sklearn's fold-stitching logic. Calibrating
        # confidence for a class the model can never predict is
        # meaningless anyway, so those rows are dropped before fitting,
        # not worked around after.
        known_classes = set(np.asarray(trainer._model.classes_).tolist())
        mask = np.isin(y_cal_encoded, list(known_classes))
        if not mask.all():
            dropped = int((~mask).sum())
            import logging

            logging.getLogger(__name__).warning(
                "%s: calibration set contained %d sample(s) of a class the "
                "trained model never saw - dropped before calibration",
                trainer.algorithm.value, dropped,
            )
            X_cal, y_cal_encoded = X_cal[mask], y_cal_encoded[mask]
```

(Check the top of `calibrator.py` for an existing module-level `import logging` / `logger = logging.getLogger(__name__)` — if one already exists, use that instead of the inline `import logging` shown above, matching the file's existing convention rather than adding a second logger.)

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_ml_training_service.py src/tests/test_ml_training_shadow.py -v`
Expected: all PASS, including `test_run_training_job_end_to_end`

- [ ] **Step 4: Fix `test_monthly_report`**

Root cause: `core/report_periods.py::period_bounds()`'s `MONTHLY` period is a CALENDAR month (`reference.replace(day=1, ...)` through the 1st of the next month) — consistent, intentional design shared with DAILY/WEEKLY/YEARLY's own calendar-aligned semantics. The test places fills at `now - timedelta(days=10)` / `now - timedelta(days=9)` using `datetime.now()` as `now` — whenever the suite runs in the first ~10 days of a calendar month (e.g. 2026-10-01, when this was diagnosed), both fills land in the PREVIOUS calendar month, outside the report's window, making `total_trades` come back `0` instead of `1`. This is a test bug (wall-clock-date-dependent), not a production code bug.

In `backend/src/tests/test_paper_trading_reports.py`, change `test_monthly_report`:

```python
def test_monthly_report(repo, report_service):
    account = _account(repo, 3)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now - timedelta(days=10))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, now - timedelta(days=9))
    report = report_service.generate(account, ReportPeriod.MONTHLY, reference=now)
    assert report.total_trades == 1
```

to:

```python
def test_monthly_report(repo, report_service):
    account = _account(repo, 3)
    # Fixed, deterministic reference (not datetime.now()) - MONTHLY is a
    # CALENDAR month window (core/report_periods.py::period_bounds), so
    # a now()-relative "10 days ago" fill lands in the PREVIOUS calendar
    # month whenever the suite runs in the first ~10 days of a month,
    # making this test flaky by wall-clock date. A fixed mid-month
    # reference removes that dependency entirely.
    now = datetime(2026, 6, 15, tzinfo=timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now - timedelta(days=10))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, now - timedelta(days=9))
    report = report_service.generate(account, ReportPeriod.MONTHLY, reference=now)
    assert report.total_trades == 1
```

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_paper_trading_reports.py -v`
Expected: all PASS, regardless of what day of the month this runs on

- [ ] **Step 5: Run the complete backend test suite**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/ -q`
Expected: 100% pass, 0 failures (the full suite, not just the 4 fixed files — confirms no regression elsewhere from Tasks 1-4)

- [ ] **Step 6: Commit**

```bash
cd backend && git add src/tests/test_core_news_analyzer_cache.py src/tests/test_users_config_jwt_secret.py src/ml_training/calibration/calibrator.py src/tests/test_paper_trading_reports.py
git commit -m "fix: root-cause the 4 pre-existing flaky test failures

- test_no_news_result_is_also_cached: also mock _fetch_google_news_rss
  (live network RSS), not just _fetch_yfinance_news - the test only
  covered one of _fetch_combined_news's two live news sources.
- test_generated_secret_is_stable_within_a_process_but_differs_across_processes:
  no-op users.config.load_dotenv for this test file - UsersConfig.from_env()'s
  own internal load_dotenv() call was re-reading this host's real
  backend/.env and repopulating USERS_JWT_SECRET right after the test's
  own monkeypatch.delenv() removed it.
- test_run_training_job_end_to_end: ModelCalibrator.calibrate() now
  drops calibration rows whose class the frozen estimator never saw
  during training, before calling CalibratedClassifierCV.fit() - a
  small/imbalanced training split leaving a class unseen by the model
  but still present in the calibration split was crashing deep in
  sklearn's cross-validation fold-stitching.
- test_monthly_report: use a fixed mid-month reference datetime instead
  of datetime.now() - MONTHLY is a calendar-month window, so a
  now()-relative fill offset lands in the previous calendar month
  whenever the suite runs in the first ~10 days of a month.

Full backend test suite is green with zero known failures.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: ML model accuracy evaluation

**Files:**
- Create: `backend/src/scripts/evaluate_model_accuracy.py`
- Create: `docs/ml-accuracy-report-2026-10-01.md` (output of running the script)

**Interfaces:** None (standalone script, run manually, not part of the app's import graph or test suite).

- [ ] **Step 1: Write the evaluation script**

```python
"""OptiTrade — point-in-time accuracy evaluation for the legacy XGBoost
models, plus a current-state sanity check for decision_engine.

Usage (from backend/src):
  python scripts/evaluate_model_accuracy.py

Methodology:
- xgb_signal_model.joblib / v2_xgb_model.joblib: true walk-forward
  evaluation. For each symbol in SYMBOL_BASKET, fetches ~1y of daily
  OHLCV, computes the SAME feature vector each model was trained on at
  every historical bar i (using only data up to and including bar i -
  point-in-time safe), predicts, and compares the prediction's implied
  direction against the REALIZED return from bar i to bar i+FORWARD_DAYS.
  Reports accuracy/precision/recall against a naive "always predict the
  majority class" baseline.
- decision_engine: NOT walk-forward (decision_engine.decide(symbol) has
  no point-in-time parameter - it always reads the Feature Store's
  current/live state, a real limitation of this evaluation, not
  something this script can route around without decision_engine
  itself gaining historical replay support, which is out of scope for
  this plan). Reports today's live decide() output across the same
  symbol basket as a distribution/sanity check only - NOT an accuracy
  number, and the report says so explicitly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from core.indicators import (
    calculate_bollinger_bands, calculate_ema_crossover, calculate_macd,
    calculate_price_velocity, calculate_rsi, calculate_trend_strength,
    calculate_volume_ratio,
)
from data.fetcher import fetch_history
from decision_engine.service import get_default_decision_engine

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

LOOKBACK = 60
FORWARD_DAYS = 5
THRESHOLD_UP_PCT = 1.0

# Same basket research/ml_trainer.py already trains on - a representative
# mix of BIST equities and major crypto assets (the two asset classes the
# spec's dual-asset vision targets).
SYMBOL_BASKET = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "AKBNK.IS",
    "BTC-USD", "ETH-USD", "SOL-USD",
]

FEATURE_NAMES = ["rsi", "macd_diff", "bollinger_pb", "ema_signal_enc", "trend_strength", "price_velocity", "volume_ratio"]
_EMA_SIGNAL_ENC = {"GOLDEN_CROSS": 2, "BULLISH": 1, "BEARISH": -1, "DEATH_CROSS": -2, None: 0}


def _extract_features(window: pd.DataFrame) -> "list[float] | None":
    try:
        prices = window["Close"]
        current, open_p = float(prices.iloc[-1]), float(window["Open"].iloc[-1])
        vol, avg_vol = float(window["Volume"].iloc[-1]), float(window["Volume"].mean())
        rsi = calculate_rsi(prices) or 50.0
        macd, macd_sig, _ = calculate_macd(prices)
        macd_diff = (macd - macd_sig) if (macd is not None and macd_sig is not None) else 0.0
        boll = calculate_bollinger_bands(prices)
        pb = (boll.get("percent_b") if boll else None) or 0.5
        ema_enc = _EMA_SIGNAL_ENC.get(calculate_ema_crossover(prices), 0)
        trend = calculate_trend_strength(prices) or 0.0
        vel = calculate_price_velocity(current, open_p)
        vol_r = calculate_volume_ratio(vol, avg_vol)
        return [rsi, macd_diff, pb, ema_enc, trend, vel, vol_r]
    except Exception:
        return None


def walk_forward_evaluate(model_path: str, model_name: str) -> dict:
    package = joblib.load(model_path)
    model = package["model"]

    y_true, y_pred = [], []
    for symbol in SYMBOL_BASKET:
        hist = fetch_history(symbol, period="1y")
        if hist is None or len(hist) < LOOKBACK + FORWARD_DAYS + 10:
            logger.warning("%s: insufficient history, skipping", symbol)
            continue
        for i in range(LOOKBACK, len(hist) - FORWARD_DAYS):
            window = hist.iloc[i - LOOKBACK: i + 1]
            feats = _extract_features(window)
            if feats is None:
                continue
            current_p = float(hist["Close"].iloc[i])
            future_p = float(hist["Close"].iloc[i + FORWARD_DAYS])
            actual_up = 1 if ((future_p - current_p) / current_p) * 100 > THRESHOLD_UP_PCT else 0
            pred_up = int(model.predict(np.array([feats]))[0])
            y_true.append(actual_up)
            y_pred.append(pred_up)

    y_true_arr, y_pred_arr = np.array(y_true), np.array(y_pred)
    accuracy = float((y_true_arr == y_pred_arr).mean()) if len(y_true_arr) else 0.0
    majority_baseline = float(max(y_true_arr.mean(), 1 - y_true_arr.mean())) if len(y_true_arr) else 0.0
    tp = int(((y_pred_arr == 1) & (y_true_arr == 1)).sum())
    fp = int(((y_pred_arr == 1) & (y_true_arr == 0)).sum())
    fn = int(((y_pred_arr == 0) & (y_true_arr == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "model": model_name, "n_samples": len(y_true_arr), "accuracy": accuracy,
        "majority_baseline": majority_baseline, "precision": precision, "recall": recall,
    }


def decision_engine_snapshot() -> list:
    engine = get_default_decision_engine()
    rows = []
    for symbol in SYMBOL_BASKET:
        try:
            output = engine.decide(symbol)
            rows.append({
                "symbol": symbol, "decision": output.decision.value,
                "confidence": output.confidence, "data_sufficiency": output.data_sufficiency,
            })
        except Exception as exc:
            rows.append({"symbol": symbol, "decision": "ERROR", "confidence": None, "error": str(exc)})
    return rows


def main() -> None:
    results = [
        walk_forward_evaluate("model_artifacts/xgb_signal_model.joblib", "xgb_signal_model"),
        walk_forward_evaluate("model_artifacts/v2_xgb_model.joblib", "v2_xgb_model"),
    ]
    snapshot = decision_engine_snapshot()

    lines = [
        f"# ML Model Accuracy Report — {datetime.now(timezone.utc).date().isoformat()}", "",
        "## Walk-forward evaluation (XGBoost models)", "",
        "| Model | Samples | Accuracy | Majority baseline | Precision | Recall |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['model']} | {r['n_samples']} | {r['accuracy']:.3f} | "
            f"{r['majority_baseline']:.3f} | {r['precision']:.3f} | {r['recall']:.3f} |"
        )
    lines += [
        "", "## decision_engine current-state snapshot (NOT a backtest)", "",
        "`decision_engine.decide()` has no point-in-time parameter, so this is "
        "today's live decision only, not a historical accuracy figure. A proper "
        "decision_engine backtest needs historical replay support - out of scope "
        "for this evaluation.", "",
        "| Symbol | Decision | Confidence | Data sufficiency |",
        "|---|---|---|---|",
    ]
    for row in snapshot:
        if row["decision"] == "ERROR":
            lines.append(f"| {row['symbol']} | ERROR | - | {row.get('error', '')} |")
        else:
            lines.append(f"| {row['symbol']} | {row['decision']} | {row['confidence']:.2f} | {row['data_sufficiency']:.2f} |")

    report = "\n".join(lines)
    print(report)
    with open("../../docs/ml-accuracy-report-2026-10-01.md", "w") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `cd backend/src && ~/app/OptiTrade/venv/bin/python3 scripts/evaluate_model_accuracy.py`
Expected: prints a markdown report and writes it to `docs/ml-accuracy-report-2026-10-01.md`; exits 0. Review the printed accuracy/precision/recall numbers - if `accuracy` for either XGBoost model is AT OR BELOW its own `majority_baseline` row, that model is currently not beating a naive guess; this is a legitimate finding to report to the user, not a reason to modify the script or block this task (see spec's Risks section — flag for retraining is a separate, later decision).

- [ ] **Step 3: Commit**

```bash
cd backend && git add src/scripts/evaluate_model_accuracy.py ../docs/ml-accuracy-report-2026-10-01.md
git commit -m "feat: add ML model accuracy evaluation script

Walk-forward point-in-time accuracy/precision/recall for both legacy
XGBoost models (xgb_signal_model, v2_xgb_model) against a BIST+crypto
symbol basket, plus a current-state decision_engine snapshot (explicitly
NOT a backtest - decide() has no point-in-time parameter). Report
committed to docs/ml-accuracy-report-2026-10-01.md.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Live endpoint manual verification (isolated Docker)

**Files:** None modified — verification only.

- [ ] **Step 1: Build and start an isolated stack**

```bash
cd backend/..  # repo root of the worktree
docker compose -p dpc-verify build api
docker compose -p dpc-verify up -d postgres redis api
```

Wait for the `api` service to report healthy:

```bash
until [ "$(docker inspect -f '{{.State.Health.Status}}' dpc-verify-api-1 2>/dev/null)" = "healthy" ]; do sleep 3; done
```

(If `docker inspect` reports a different container name, check it with `docker compose -p dpc-verify ps` first — container_name in docker-compose.yml is hardcoded, so compose appends `-1` only when no explicit `container_name:` collision forces a rename; confirm the actual name before waiting on it.)

- [ ] **Step 2: Exercise every touched route with real symbols**

```bash
PORT=$(docker compose -p dpc-verify port api 8000 | cut -d: -f2)
BASE="http://localhost:$PORT"

curl -s -X POST "$BASE/analyze" -H 'Content-Type: application/json' -d '{"symbol":"AAPL","asset_type":"stock"}' | python3 -m json.tool
curl -s -X POST "$BASE/analyze/enhanced" -H 'Content-Type: application/json' -d '{"symbol":"AAPL","asset_type":"stock","run_monte_carlo":false}' | python3 -m json.tool
curl -s "$BASE/v2/analyze/AAPL" | python3 -m json.tool
curl -s -X POST "$BASE/quant/analyze" -H 'Content-Type: application/json' -d '{"symbol":"AAPL"}' | python3 -m json.tool
curl -s "$BASE/scan/bist" | python3 -m json.tool
curl -s "$BASE/scan/crypto" | python3 -m json.tool
```

For each response, confirm: HTTP 200, the expected field set is present (per each route's Pydantic `response_model` — `AnalysisResult`, `EngineResult`, `PipelineResponse`, `ScanResult`), and `decision`/`decision`-equivalent fields hold a plausible 5-way or BUY/HOLD/SELL value (not null, not an error string). `/api/v1/signals/analyze` needs a request body per its schema (`SignalsAnalyzeRequest` — `{"symbols": ["AAPL"], "profile": "trader"}` and again with `"profile": "investor"`) — exercise both profiles, since Task 3 changed the investor path specifically.

- [ ] **Step 3: Tear down**

```bash
docker compose -p dpc-verify down -v
```

Confirm the production stack is untouched: `docker ps --format '{{.Names}}'` still lists `optitrade-api`, `optitrade-postgres`, etc. with their original `Up <N> days` status, unaffected by this isolated verification run.

- [ ] **Step 4: Record results**

No commit for this task (verification only, no file changes) — report the manual verification results directly in the SDD ledger / final summary: which routes were exercised, with which symbols, and confirmation that each returned a plausible decision.

---

## Explicitly Out of Scope (restated from the spec)

- `decision_engine`'s own decision logic/weighting.
- Any iOS code change.
- Simplifying iOS's UI to the leaner `DecisionOutput` shape.
- The dual-asset-class advisor feature itself (sub-project 2).
- The web frontend update (sub-project 3).
- `v2/ml/predictor.py:8` and `research/train_v2.py:88`'s pre-existing CWD-relative path bugs.
- Retraining any model, even if Task 5's evaluation finds one underperforming — that's a flagged finding for a separate decision, not part of this plan's completion criteria.
