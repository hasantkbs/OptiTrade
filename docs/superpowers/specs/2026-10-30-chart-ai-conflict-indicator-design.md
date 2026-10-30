# Chart AI Conflict Indicator — Design

## Mission

The chart AI model (CNN+LSTM, `backend/src/ml/chart_model.py`) is now
live for 61 symbols across BIST/US/CRYPTO, with its disagreement with
`decision_engine` validated against real history (not just live
opinion) - see `docs/btc-chart-model-training-2026-10-22.md`'s "Live
scan check" and "oversold regime" sections. Right now none of this
reaches an end user: chart AI only feeds the separate, older
`/analyze` → `compute_recommendation()` path (15% weight into
`RecommendationResult`), which the current, simplified web frontend
doesn't render anywhere. The asset detail page's `Recommendation`
card (`web/src/features/asset/Recommendation.tsx`) is backed by
`/quant/analyze` → `PipelineResponse` - decision_engine's
Technical/Fundamental/News vote only, with zero knowledge of chart
AI's signal.

**Goal:** when chart AI's signal for a symbol directly contradicts
`decision_engine`'s decision (one says BUY, the other SELL), the
asset detail page's `Recommendation` card shows a short, plain-
language warning line beneath the main decision - without breaking
the simplification design `docs/superpowers/specs/2026-10-05-web-simplification-design.md`
established for this exact card ("no engine terminology, no raw
confidence/risk numbers... mapped to plain language").

## Current State

- **`PipelineResponse`** (`backend/src/pipeline/models.py:75-85`):
  `symbol`, `decision: Prediction` (`BUY`/`HOLD`/`SELL`,
  `decision_engine/models.py:23-26`), `confidence`, `expected_return`,
  `expected_volatility`, `engine_breakdown: List[EngineBreakdownItem]`,
  `evidence: List[str]`, `risk`, `explanation`, `metadata`. No chart-AI
  field exists. `engine_breakdown`/`evidence` are already present in
  the real response but deliberately unrendered by `Recommendation.tsx`
  - the frontend's simplification is a display choice, not a backend
  data-minimization choice; this spec follows that same convention.
- **`POST /quant/analyze`** (`backend/src/main.py:1563-1585`): looks up
  `_QUANT_ANALYZE_CACHE` (180s TTL, `main.py:1560`, cleared per-test by
  `tests/test_main_quant_endpoint.py`'s autouse fixture), else runs
  `_pipeline_service.run(symbol)` in the executor and caches the
  result before returning. `PipelineService.run()` itself
  (`backend/src/pipeline/service.py`) owns only the decision_engine
  pipeline - Feature Store → Technical/Fundamental/News Engines →
  Decision Engine → Explanation Engine → Learning Tracker - and has no
  reason to know about chart AI.
- **Chart AI's own live-serving path** (`backend/src/main.py:1140-1158`,
  `_enrich_result`, used by the OLDER `/analyze` endpoint family, not
  `/quant/analyze`): `if result.symbol in get_supported_symbols() and
  is_model_available(result.symbol): hist = yf.Ticker(result.symbol).history(period="6mo");
  chart_ai_result = predict_chart_signal(hist, symbol=result.symbol)`.
  `predict_chart_signal()` (`ml/chart_model.py`) returns
  `{"signal": "SELL"|"NEUTRAL"|"BUY"|None, "confidence": float|None,
  "probabilities": {...}, "model_available": bool, "error"?: str}`.
  Note chart AI's own vocabulary is `SELL`/`NEUTRAL`/`BUY` - distinct
  from decision_engine's `Prediction` (`BUY`/`HOLD`/`SELL`, no
  `NEUTRAL`). `get_supported_symbols()` (`ml/chart_model.py`) reads
  `model_artifacts/supported_symbols.json` fresh on every call (updated
  weekly by `research/retrain_chart_models.py`, cron on `mayasoftlnx01`)
  - which symbols have a usable chart-AI signal changes over time
  without a deploy.
- **`Recommendation.tsx`** (`web/src/features/asset/Recommendation.tsx`):
  renders only `data.decision` (via a `BUY`/`SELL`/`HOLD` → tone +
  text badge), `confidenceWord(data.confidence)` (own three-tier
  mapping: `>=0.66` "Yüksek güven", `>=0.33` "Orta güven", else "Düşük
  güven" - exact thresholds from the web-simplification spec, used
  verbatim, never re-derived), and `data.explanation` (plain-language,
  already LLM-generated). No engine names, no raw %, no evidence list.
  Tested by `Recommendation.test.tsx` (9 cases: empty/pending/error
  states, decision rendering, each confidence-tier boundary, HOLD
  treatment).

## Scope

**Added:** one optional field on `PipelineResponse`, populated at the
`/quant/analyze` endpoint-handler level (mirroring `_enrich_result`'s
established pattern, not inside `PipelineService.run()`); one
conditional warning line in `Recommendation.tsx`, shown only on a
direct opposite-direction conflict.

**Explicitly out of scope for this round:** the market-opportunities
list view (no conflict indicator there - confirmed with the user,
asset-detail-page only); showing the "soft" divergence case
(decision_engine `HOLD` while chart AI holds a confident `BUY`/`SELL`
opinion - 21 of the 61 live symbols hit this case per the live scan in
`docs/btc-chart-model-training-2026-10-22.md`, far more often than the
11 direct conflicts - deliberately excluded so the indicator stays
rare enough to mean something, not a near-coin-flip "sometimes shown"
feature); a click-to-expand explanation referencing the oversold-regime
backtest's actual numbers (noted as a natural follow-up, not built
now); any change to `/analyze`'s existing `compute_recommendation()`
chart-AI usage (unaffected, stays exactly as-is).

## Design

### Conflict definition

A conflict exists **only** when `chart_ai.signal` and `decision` are
on strictly opposite sides:

- `decision == "BUY"` and `chart_ai.signal == "SELL"`, or
- `decision == "SELL"` and `chart_ai.signal == "BUY"`.

Every other combination (`chart_ai.signal == "NEUTRAL"` regardless of
`decision`; `decision == "HOLD"` regardless of `chart_ai.signal`; both
sides agreeing) is **not** a conflict and shows nothing extra. This
matches the live-scan numbers: of 61 symbols, 11 are direct conflicts
by this definition (`SISE.IS`, `ALBRK.IS`, `CRM`, `AMZN`, `ASELS.IS`,
`THYAO.IS`, `TTKOM.IS`, `AKBNK.IS`, `ISCTR.IS`, `SAHOL.IS`, `LOGO.IS`) -
about 18% of live symbols, rare enough that seeing the warning carries
real weight.

### Backend: `PipelineResponse.chart_ai`

New model in `backend/src/pipeline/models.py`:

```python
class ChartAISignal(BaseModel):
    signal: str   # "BUY" | "SELL" | "NEUTRAL" - chart AI's own vocabulary,
                  # deliberately NOT the Prediction enum (which has no
                  # NEUTRAL value)
    confidence: float = Field(..., ge=0.0, le=1.0)
```

`PipelineResponse` gains `chart_ai: Optional[ChartAISignal] = None`.

In `main.py`'s `quant_analyze()` handler, after `result = await
loop.run_in_executor(_executor, _pipeline_service.run, symbol)` and
before `_QUANT_ANALYZE_CACHE.set(symbol, result)`: if `symbol in
get_supported_symbols()` and `is_model_available(symbol)`, fetch
`yf.Ticker(symbol).history(period="6mo")`, call
`predict_chart_signal(hist, symbol=symbol)`, and if it returns a real
`signal` (not `None`/an error), set `result.chart_ai =
ChartAISignal(signal=..., confidence=...)` on the response before
caching - same `period="6mo"` requirement `_enrich_result` already
established (`main.py`'s own comment there explains why `3mo` was too
short), same try/except-and-skip-silently-on-any-failure shape (a
yfinance hiccup here must never break `/quant/analyze` itself - this
mirrors `_enrich_result`'s own `try/except Exception: pass`). The
180s cache TTL is fine for chart AI's own refresh cadence (model
retrains weekly; the live `predict_chart_signal()` call itself is
cheap - inference only, no training).

**Why at the endpoint-handler level, not inside `PipelineService.run()`**:
`PipelineService` owns exactly one thing - the decision_engine
pipeline - and every existing caller (tests, `/quant/analyze` itself)
expects that scope. Attaching chart AI there would make a core
service reach into an unrelated subsystem's model-serving code for a
single caller's display need. The endpoint-handler level already has
this exact precedent (`_enrich_result`, same file) for the sibling
`/analyze` family.

### Frontend: the warning line

In `Recommendation.tsx`, after computing the existing badge/confidence
row: if `data.chart_ai` is present and `isConflict(data.decision,
data.chart_ai.signal)` (a small new pure function, exported for its
own unit tests), render one additional line below the explanation
paragraph:

> ⚠ Fiyat deseni modeli farklı görüşte: **{SIGNAL_WORD}**, {confidenceWord(data.chart_ai.confidence)}

where `SIGNAL_WORD` maps chart AI's `BUY`/`SELL` to the same visual
language as the main badge (reuse `DECISION_TONE`-equivalent styling,
not a new color system) and `confidenceWord()` is the *exact same*
function already used for the main decision - no new confidence
vocabulary, no raw percentage, no mention of "chart AI", "model",
"engine", "oversold", or the backtest. `chart_ai.signal` is always
either `BUY` or `SELL` when this line renders (never `NEUTRAL`, by the
conflict definition above), so no third case needs copy.

`PipelineMetadata`'s `symbol`/`decision` fields are untouched; this is
purely an additive field plus one conditional render branch.

## Testing

**Backend** (`tests/test_main_quant_endpoint.py`, extending the
existing real-Postgres/Redis/network convention - no new mocking
framework introduced): a case using a real symbol currently in
`get_supported_symbols()` confirms `chart_ai` is populated with a real
signal/confidence; a case using a symbol NOT in `get_supported_symbols()`
(or with `get_supported_symbols` monkeypatched to an empty tuple,
matching the isolation technique `test_main_chart_ai_symbol_gating.py`
already uses for the sibling endpoint) confirms `chart_ai` stays
`None`; a case where `yf.Ticker.history` is monkeypatched to raise
confirms `/quant/analyze` still returns 200 with `chart_ai: None`
rather than failing the whole request.

**Frontend** (`Recommendation.test.tsx`, extending the existing nine
cases): `isConflict` unit-tested directly for all nine
`decision`×`chart_ai.signal` combinations (only `BUY`/`SELL` and
`SELL`/`BUY` are `true`); a rendering case with a genuine
`BUY`/`SELL` conflict shows the warning line with the right signal
word and confidence word; a rendering case with `chart_ai: { signal:
"NEUTRAL", ... }` and `decision: "BUY"` shows nothing extra; a
rendering case with `chart_ai: undefined` (today's real response
shape for any symbol without a live chart-AI model) renders exactly
as today, confirmed by reusing the existing "no engine jargon" assertion
style.

## Review Focus

- A symbol whose chart-AI model exists but `predict_chart_signal()`
  returns an `error` (insufficient yfinance data) - `chart_ai` must
  stay `None`, not surface the error string anywhere a user sees it.
- `decision == "HOLD"` with any `chart_ai.signal` - confirmed not a
  conflict by this spec's own definition; a test should pin this since
  it's the single most common disagreement shape in the live data (21
  of 61 symbols) and the easiest one to accidentally include by a
  looser `!=` check instead of the strict BUY/SELL-opposite check.
- `_QUANT_ANALYZE_CACHE`'s existing autouse-clear fixture
  (`test_main_quant_endpoint.py`) already prevents cross-test
  pollution for the new backend tests - no new fixture needed, but the
  new tests must use it (inherited automatically, same file).
- A user who already has a cached `PipelineResponse` from before this
  field existed (an old frontend build calling a new backend, or vice
  versa during a rolling deploy) - `chart_ai` being `Optional` with no
  required-field validation on either side (Pydantic default `None`,
  TypeScript optional `?`) means neither side errors on its absence;
  worth a one-line test confirming a `PipelineResponse` built without
  `chart_ai` at all still validates/renders.
