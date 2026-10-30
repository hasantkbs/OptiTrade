# Chart AI Conflict Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** show a short warning line on the asset detail page's `Recommendation` card when the chart AI model's signal directly contradicts `decision_engine`'s decision (one says BUY, the other SELL).

**Architecture:** `PipelineResponse` gains an optional `chart_ai` field, populated inside `main.py`'s `/quant/analyze` endpoint handler (mirroring the existing `_enrich_result` pattern used by the sibling `/analyze` endpoint) - never inside `PipelineService.run()`, which owns only the decision_engine pipeline. `Recommendation.tsx` renders one extra line, reusing its existing `confidenceWord()` mapping and `Badge` component, only when `decision` and `chart_ai.signal` are on strictly opposite BUY/SELL sides.

**Tech Stack:** FastAPI + Pydantic (backend), React + TypeScript + Vitest/React Testing Library (frontend), pytest with real Postgres/Redis (no mocking framework, project convention).

**Spec:** `docs/superpowers/specs/2026-10-30-chart-ai-conflict-indicator-design.md`

## Global Constraints

- No engine terminology, no raw confidence/risk numbers anywhere in `Recommendation.tsx` - only `confidenceWord()`'s three-tier mapping (`>=0.66` "Yüksek güven", `>=0.33` "Orta güven", else "Düşük güven"), per `docs/superpowers/specs/2026-10-05-web-simplification-design.md`.
- A conflict is **only** `decision=="BUY" && chart_ai.signal=="SELL"` or `decision=="SELL" && chart_ai.signal=="BUY"`. Every other combination (including `chart_ai.signal=="NEUTRAL"`, and `decision=="HOLD"` with any `chart_ai.signal`) is not a conflict and renders nothing extra.
- `chart_ai` is populated in `main.py`'s `/quant/analyze` endpoint handler, never inside `pipeline/service.py::PipelineService.run()`.
- A chart-AI/yfinance failure must never break `/quant/analyze` - always caught, `chart_ai` defaults to `None`.
- The yfinance history pull uses `period="6mo"` (not `3mo` - too short for a 5-day trading week, see `_enrich_result`'s own comment in `main.py`).
- `chart_ai` is `Optional` on both sides (Pydantic default `None` in Python, `?` in TypeScript) - a response or cached entry without it must validate/render exactly as before this change.
- Market-opportunities list view is explicitly out of scope - asset detail page only.

## Review Focus

- `predict_chart_signal()` returns an `error` key (insufficient yfinance data) - `chart_ai` must stay `None`, the error string must never reach a response field a user sees.
- `decision=="HOLD"` with any `chart_ai.signal` - must never be treated as a conflict; this is the single most common disagreement shape in the live data (21 of 61 symbols per the spec) and the easiest one to wrongly include with a looser `!=` check instead of the strict opposite-sides check.
- A `PipelineResponse` built without `chart_ai` at all (an old cached entry from before this field existed, or a request for a symbol with no live chart-AI model) - both backend validation and frontend rendering must behave exactly as they did before this change.
- A symbol with a trained-but-excluded chart-AI model (not in `get_supported_symbols()`, e.g. `MSFT`) - `chart_ai` stays `None`, not an error.
- `_QUANT_ANALYZE_CACHE`'s existing 180s-TTL autouse-clear fixture (`tests/test_main_quant_endpoint.py`) must keep preventing cross-test pollution for every new test added here - no new fixture needed, just use the existing one (automatic for any test in that file).

---

### Task 1: `ChartAISignal` model and the `PipelineResponse.chart_ai` field

**Files:**
- Modify: `backend/src/pipeline/models.py`
- Modify: `backend/src/pipeline/__init__.py`
- Test: `backend/src/tests/test_pipeline_models_chart_ai.py` (new)

**Interfaces:**
- Produces: `pipeline.models.ChartAISignal(signal: str, confidence: float)` (importable as `from pipeline import ChartAISignal`), `PipelineResponse.chart_ai: Optional[ChartAISignal] = None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/src/tests/test_pipeline_models_chart_ai.py
"""Unit tests for pipeline/models.py's ChartAISignal and
PipelineResponse.chart_ai - no network, no database, pure model
construction. The full end-to-end population of this field (a real
chart-AI prediction attached to a real /quant/analyze response) is
covered by tests/test_main_quant_endpoint.py instead."""
import pytest
from pydantic import ValidationError

from pipeline.models import ChartAISignal, PipelineMetadata, PipelineResponse, RiskAssessment


def _response(**overrides) -> PipelineResponse:
    defaults = dict(
        symbol="AAPL", decision="BUY", confidence=0.7, expected_return=0.02, expected_volatility=0.1,
        risk=RiskAssessment(risk_level="LOW", expected_volatility=0.1, data_sufficiency=0.9),
        explanation="test",
        metadata=PipelineMetadata(
            pipeline_version="1.0.0", total_duration_ms=1.0,
            engines_available=3, engines_succeeded=3, degraded=False,
        ),
    )
    defaults.update(overrides)
    return PipelineResponse(**defaults)


def test_chart_ai_defaults_to_none():
    assert _response().chart_ai is None


def test_chart_ai_accepts_a_valid_signal():
    response = _response(chart_ai=ChartAISignal(signal="SELL", confidence=0.8))
    assert response.chart_ai.signal == "SELL"
    assert response.chart_ai.confidence == 0.8


def test_chart_ai_confidence_must_be_between_zero_and_one():
    with pytest.raises(ValidationError):
        ChartAISignal(signal="BUY", confidence=1.5)


def test_chart_ai_signal_can_be_set_after_construction():
    """main.py's enrichment helper (Task 2) sets this as a post-
    construction mutation, not at __init__ time - PipelineResponse
    must not be a frozen/immutable model."""
    response = _response()
    response.chart_ai = ChartAISignal(signal="NEUTRAL", confidence=0.5)
    assert response.chart_ai.signal == "NEUTRAL"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/src && pytest tests/test_pipeline_models_chart_ai.py -v`
Expected: FAIL with `ImportError: cannot import name 'ChartAISignal' from 'pipeline.models'`

- [ ] **Step 3: Add `ChartAISignal` and the `chart_ai` field**

In `backend/src/pipeline/models.py`, add the new model directly above `PipelineResponse` (after `PipelineMetadata`):

```python
class ChartAISignal(BaseModel):
    """ml.chart_model.predict_chart_signal()'s own vocabulary - NOT
    the Prediction enum (decision_engine/models.py), which has no
    NEUTRAL value. Populated outside this module entirely (see
    main.py's _attach_chart_ai) - PipelineService.run() never touches
    this field."""
    signal: str  # "BUY" | "SELL" | "NEUTRAL"
    confidence: float = Field(..., ge=0.0, le=1.0)
```

Then add one field to `PipelineResponse` (after `metadata: PipelineMetadata`):

```python
class PipelineResponse(BaseModel):
    symbol: str
    decision: Prediction
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_return: float
    expected_volatility: float
    engine_breakdown: List[EngineBreakdownItem] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    risk: RiskAssessment
    explanation: str
    metadata: PipelineMetadata
    chart_ai: Optional[ChartAISignal] = None
```

In `backend/src/pipeline/__init__.py`:

```python
from pipeline.models import ChartAISignal, PipelineResponse, QuantAnalysisRequest
from pipeline.service import PipelineService

__all__ = ["PipelineService", "PipelineResponse", "QuantAnalysisRequest", "ChartAISignal"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/src && pytest tests/test_pipeline_models_chart_ai.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/pipeline/models.py backend/src/pipeline/__init__.py backend/src/tests/test_pipeline_models_chart_ai.py
git commit -m "feat: add ChartAISignal and PipelineResponse.chart_ai field"
```

---

### Task 2: Populate `chart_ai` in `/quant/analyze`

**Files:**
- Modify: `backend/src/main.py:80` (import line), `backend/src/main.py:1563-1587` (`quant_analyze` endpoint, new `_attach_chart_ai` helper placed just above it)
- Test: `backend/src/tests/test_main_quant_endpoint.py`

**Interfaces:**
- Consumes: `pipeline.ChartAISignal` (Task 1), `ml.chart_model.get_supported_symbols()`, `ml.chart_model.is_model_available(symbol)`, `ml.chart_model.predict_chart_signal(hist, symbol=...) -> dict` (all pre-existing).
- Produces: `_attach_chart_ai(result: PipelineResponse) -> None` (mutates `result.chart_ai` in place; never raises).

- [ ] **Step 1: Write the failing tests**

Append to `backend/src/tests/test_main_quant_endpoint.py` (same file, same `client`/`_cleanup` fixtures already used by every other test in it):

```python
def test_quant_analyze_populates_chart_ai_for_a_supported_symbol(client):
    """AAPL is live in ml.chart_model.get_supported_symbols() as of
    2026-10-22 (docs/btc-chart-model-training-2026-10-22.md). If this
    ever changes, pick another symbol from that doc's live list
    instead of weakening this test."""
    response = client.post("/quant/analyze", json={"symbol": "AAPL"})
    assert response.status_code == 200
    chart_ai = response.json()["chart_ai"]
    assert chart_ai is not None
    assert chart_ai["signal"] in ("BUY", "SELL", "NEUTRAL")
    assert 0.0 <= chart_ai["confidence"] <= 1.0
    _cleanup("AAPL")


def test_quant_analyze_chart_ai_is_none_for_an_unsupported_symbol(client):
    """MSFT was trained but excluded from SUPPORTED_SYMBOLS (window 2
    failed significance - docs/btc-chart-model-training-2026-10-22.md)
    - a real symbol with a real decision_engine result, just no live
    chart-AI model."""
    response = client.post("/quant/analyze", json={"symbol": "MSFT"})
    assert response.status_code == 200
    assert response.json()["chart_ai"] is None
    _cleanup("MSFT")


def test_quant_analyze_chart_ai_failure_does_not_break_the_request(client, monkeypatch):
    import yfinance as yf

    def _raise(self, period=None):
        raise RuntimeError("yfinance unavailable")

    monkeypatch.setattr(yf.Ticker, "history", _raise)

    response = client.post("/quant/analyze", json={"symbol": "AAPL"})
    assert response.status_code == 200
    assert response.json()["chart_ai"] is None
    _cleanup("AAPL")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/src && pytest tests/test_main_quant_endpoint.py -k chart_ai -v`
Expected: FAIL - `chart_ai` key missing from the response body (`KeyError` or `None` where a real signal was expected for AAPL).

- [ ] **Step 3: Add `_attach_chart_ai` and wire it into the endpoint**

In `backend/src/main.py:80`, change:

```python
from pipeline import PipelineResponse, PipelineService, QuantAnalysisRequest
```

to:

```python
from pipeline import ChartAISignal, PipelineResponse, PipelineService, QuantAnalysisRequest
```

Immediately above the `@app.post("/quant/analyze", ...)` line (currently line 1563), add:

```python
def _attach_chart_ai(result: PipelineResponse) -> None:
    """Mutates `result.chart_ai` in place when a live chart-AI model
    exists for this symbol - mirrors _enrich_result's own established
    pattern (same file, /analyze endpoint family) so the two live
    chart-AI call sites stay consistent. Never raises: any failure
    here (no model, insufficient yfinance history, a network error)
    must not break /quant/analyze itself - the endpoint still returns
    the real decision_engine result with chart_ai left at its default
    None."""
    try:
        from ml.chart_model import get_supported_symbols, is_model_available, predict_chart_signal
        if result.symbol in get_supported_symbols() and is_model_available(result.symbol):
            import yfinance as yf
            # Same period="6mo" requirement _enrich_result already
            # established - "3mo" is too short for a 5-day trading
            # week (see that function's own comment, same file).
            hist_ai = yf.Ticker(result.symbol).history(period="6mo")
            if not hist_ai.empty:
                chart_ai_result = predict_chart_signal(hist_ai, symbol=result.symbol)
                if chart_ai_result and chart_ai_result.get("signal"):
                    result.chart_ai = ChartAISignal(
                        signal=chart_ai_result["signal"],
                        confidence=chart_ai_result["confidence"],
                    )
    except Exception:
        pass
```

Then change the body of `quant_analyze` (currently lines 1580-1587) from:

```python
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, _pipeline_service.run, symbol)
        _QUANT_ANALYZE_CACHE.set(symbol, result)
        return result
    except Exception as e:
        logger.error(f"Quant pipeline hatasi ({body.symbol}): {e}")
        raise HTTPException(status_code=500, detail=f"{body.symbol} icin analiz calistirilamadi.")
```

to:

```python
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, _pipeline_service.run, symbol)
        _attach_chart_ai(result)
        _QUANT_ANALYZE_CACHE.set(symbol, result)
        return result
    except Exception as e:
        logger.error(f"Quant pipeline hatasi ({body.symbol}): {e}")
        raise HTTPException(status_code=500, detail=f"{body.symbol} icin analiz calistirilamadi.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/src && pytest tests/test_main_quant_endpoint.py -v`
Expected: PASS (all tests in the file, including the 3 new ones and every pre-existing one - `test_quant_analyze_returns_the_full_new_schema`'s field-presence loop does not need updating since it doesn't assert the field SET is exhaustive, only that each named field is present).

- [ ] **Step 5: Commit**

```bash
git add backend/src/main.py backend/src/tests/test_main_quant_endpoint.py
git commit -m "feat: populate chart_ai in /quant/analyze"
```

---

### Task 3: Frontend `ChartAISignal` type and the `isConflict()` helper

**Files:**
- Modify: `web/src/api/types.ts`
- Create: `web/src/features/asset/chartAiConflict.ts`
- Test: `web/src/features/asset/chartAiConflict.test.ts` (new)

**Interfaces:**
- Produces: `ChartAISignal` type (`web/src/api/types.ts`), `PipelineResponse.chart_ai?: ChartAISignal`, `isConflict(decision: Prediction, chartAiSignal: ChartAISignal['signal']): boolean` (`web/src/features/asset/chartAiConflict.ts`).

- [ ] **Step 1: Write the failing test**

```typescript
// web/src/features/asset/chartAiConflict.test.ts
import { describe, expect, it } from 'vitest'
import { isConflict } from './chartAiConflict'

describe('isConflict', () => {
  it('is a conflict when decision is BUY and chart AI says SELL', () => {
    expect(isConflict('BUY', 'SELL')).toBe(true)
  })

  it('is a conflict when decision is SELL and chart AI says BUY', () => {
    expect(isConflict('SELL', 'BUY')).toBe(true)
  })

  it('is NOT a conflict when both sides agree on BUY', () => {
    expect(isConflict('BUY', 'BUY')).toBe(false)
  })

  it('is NOT a conflict when both sides agree on SELL', () => {
    expect(isConflict('SELL', 'SELL')).toBe(false)
  })

  it('is NOT a conflict when chart AI is NEUTRAL, regardless of decision', () => {
    expect(isConflict('BUY', 'NEUTRAL')).toBe(false)
    expect(isConflict('SELL', 'NEUTRAL')).toBe(false)
    expect(isConflict('HOLD', 'NEUTRAL')).toBe(false)
  })

  it('is NOT a conflict when decision is HOLD, regardless of chart AI signal', () => {
    expect(isConflict('HOLD', 'BUY')).toBe(false)
    expect(isConflict('HOLD', 'SELL')).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/features/asset/chartAiConflict.test.ts`
Expected: FAIL - `Failed to resolve import "./chartAiConflict"`

- [ ] **Step 3: Add the type and the implementation**

In `web/src/api/types.ts`, immediately after `export interface PipelineMetadata { ... }` and before `export interface PipelineResponse { ... }` (currently around line 549-551):

```typescript
export interface ChartAISignal {
  signal: 'BUY' | 'SELL' | 'NEUTRAL'
  confidence: number
}
```

Then add one field to `PipelineResponse` (after `metadata: PipelineMetadata`, currently the last line of that interface):

```typescript
export interface PipelineResponse {
  symbol: string
  decision: Prediction
  confidence: number
  expected_return: number
  expected_volatility: number
  engine_breakdown: EngineBreakdownItem[]
  evidence: string[]
  risk: QuantRiskAssessment
  explanation: string
  metadata: PipelineMetadata
  chart_ai?: ChartAISignal
}
```

Create `web/src/features/asset/chartAiConflict.ts`:

```typescript
import type { ChartAISignal, Prediction } from '../../api/types'

/** A conflict is strictly BUY-vs-SELL in either direction - NEUTRAL
 * chart-AI signals and HOLD decisions never count, by design (see
 * docs/superpowers/specs/2026-10-30-chart-ai-conflict-indicator-design.md's
 * "Conflict definition" - this is deliberately the rarer, stricter
 * reading so the indicator stays meaningful rather than showing on
 * roughly half of all live symbols). */
export function isConflict(decision: Prediction, chartAiSignal: ChartAISignal['signal']): boolean {
  return (
    (decision === 'BUY' && chartAiSignal === 'SELL') ||
    (decision === 'SELL' && chartAiSignal === 'BUY')
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run src/features/asset/chartAiConflict.test.ts`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add web/src/api/types.ts web/src/features/asset/chartAiConflict.ts web/src/features/asset/chartAiConflict.test.ts
git commit -m "feat: add ChartAISignal type and isConflict() helper"
```

---

### Task 4: Render the conflict line in `Recommendation.tsx`

**Files:**
- Modify: `web/src/features/asset/Recommendation.tsx`
- Test: `web/src/features/asset/Recommendation.test.tsx`

**Interfaces:**
- Consumes: `isConflict` (Task 3, `./chartAiConflict`), `ChartAISignal` (Task 3, `../../api/types`), `data.chart_ai: ChartAISignal | undefined` (Task 1+2, already present on `PipelineResponse` by this point), existing `confidenceWord()` and `Badge` (no changes to either).

- [ ] **Step 1: Write the failing tests**

Append to `web/src/features/asset/Recommendation.test.tsx` (the existing `response` fixture at the top of that file is reused as-is, by spreading `chart_ai` into it per case - it already has no `chart_ai` key, matching the "no live model" case by default):

```typescript
describe('Recommendation - chart AI conflict', () => {
  it('shows the warning line when decision is BUY and chart AI says SELL', () => {
    render(
      <Recommendation
        data={{ ...response, decision: 'BUY', chart_ai: { signal: 'SELL', confidence: 0.72 } }}
        isPending={false} isError={false} onAnalyze={vi.fn()}
      />,
    )
    expect(screen.getByText('SELL')).toBeInTheDocument()
    expect(screen.getByText(/disagrees/i)).toBeInTheDocument()
    expect(screen.getByText('Yüksek güven')).toBeInTheDocument()
  })

  it('shows nothing extra when decision and chart AI agree', () => {
    render(
      <Recommendation
        data={{ ...response, decision: 'BUY', chart_ai: { signal: 'BUY', confidence: 0.72 } }}
        isPending={false} isError={false} onAnalyze={vi.fn()}
      />,
    )
    expect(screen.queryByText(/disagrees/i)).not.toBeInTheDocument()
  })

  it('shows nothing extra when chart AI is NEUTRAL', () => {
    render(
      <Recommendation
        data={{ ...response, decision: 'BUY', chart_ai: { signal: 'NEUTRAL', confidence: 0.5 } }}
        isPending={false} isError={false} onAnalyze={vi.fn()}
      />,
    )
    expect(screen.queryByText(/disagrees/i)).not.toBeInTheDocument()
  })

  it('shows nothing extra when decision is HOLD, even if chart AI has a strong opposite opinion', () => {
    render(
      <Recommendation
        data={{ ...response, decision: 'HOLD', chart_ai: { signal: 'SELL', confidence: 0.9 } }}
        isPending={false} isError={false} onAnalyze={vi.fn()}
      />,
    )
    expect(screen.queryByText(/disagrees/i)).not.toBeInTheDocument()
  })

  it('renders exactly as before when chart_ai is absent (today\'s shape for any symbol with no live model)', () => {
    render(<Recommendation data={response} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.queryByText(/disagrees/i)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/features/asset/Recommendation.test.tsx`
Expected: FAIL on the first new test - no "disagrees" text anywhere yet.

- [ ] **Step 3: Render the conflict line**

In `web/src/features/asset/Recommendation.tsx`, add the import:

```typescript
import { isConflict } from './chartAiConflict'
```

Then, inside the `{data ? (...) : null}` block, immediately after the existing `{data.explanation ? ... : null}` line and before the `{isError ? ... : null}` line:

```tsx
{data.chart_ai && isConflict(data.decision, data.chart_ai.signal) ? (
  <div className={styles.row}>
    <Badge tone="warning" className={styles.badge}>{data.chart_ai.signal}</Badge>
    <span className={styles.confidence}>
      Chart pattern model disagrees · {confidenceWord(data.chart_ai.confidence)}
    </span>
  </div>
) : null}
```

(Reuses the existing `.row`/`.badge`/`.confidence` CSS classes already defined in `Recommendation.module.css` and the `Badge` component's existing `'warning'` tone - no new CSS or component props needed.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/features/asset/Recommendation.test.tsx`
Expected: PASS (all 14 tests - 9 pre-existing + 5 new)

- [ ] **Step 5: Commit**

```bash
git add web/src/features/asset/Recommendation.tsx web/src/features/asset/Recommendation.test.tsx
git commit -m "feat: show chart-AI conflict warning on the Recommendation card"
```
