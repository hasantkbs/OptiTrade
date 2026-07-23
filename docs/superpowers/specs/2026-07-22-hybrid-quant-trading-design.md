# Hybrid Quantitative Trading Engine — Design

Date: 2026-07-22

## Goal

Replace ad-hoc indicator-threshold scoring with a modular, three-layer
quantitative pipeline under `backend/core/`, independent of the existing
`core/analyzer.py`/`core/scoring.py` and `backend/v2/` code paths. No wiring
into `main.py` in this pass — modules are self-contained and importable.

## Layers & files

```
core/
  regime_scanner.py    MarketRegimeScanner   — Scanning layer
  mtf_analyzer.py       MultiTimeframeAnalyzer — Analysis layer
  risk_manager.py       DynamicRiskManager     — Risk layer
  ai_trader_persona.py  AITraderPersona        — LLM recommendation layer
  hybrid_engine.py      HybridTradingEngine    — orchestrator tying all 4 together
```

## Data flow

```
symbols: List[str]
   -> MarketRegimeScanner.scan(symbols) -> List[ScannedSymbol]
      (per-symbol regime classification; CHOPPY_NO_OPPORTUNITY symbols dropped)
   -> per scanned symbol: MultiTimeframeAnalyzer.analyze(symbol) -> Dict[str, Any]
      (macro 1D/1W trend + micro 1H entry signals, merged dict, per spec)
   -> DynamicRiskManager.calculate(entry_price, atr) -> RiskLevels (pydantic)
   -> AITraderPersona.generate_recommendation(symbol, regime, analysis, risk,
        news_sentiment=None) -> TradeRecommendation (pydantic, via Anthropic API)
   -> HybridTradingEngine.run(symbols) -> List[TradeRecommendation]
```

## Key decisions

- **Regime classification** (`MarketRegimeScanner`): per symbol, last 60
  daily closes -> cumulative return, annualized volatility, linear-regression
  R² (trend strength). Classified as `TRENDING_BULL` / `TRENDING_BEAR` /
  `RANGE_BOUND` / `CHOPPY_NO_OPPORTUNITY`. Only the last category (no
  tradable structure) is filtered out before the next stage.
- **pandas-ta compatibility shim**: PyPI `pandas-ta==0.3.14b0` imports
  `numpy.NaN`, removed in numpy>=1.24 (pinned `numpy==1.26.4` in this repo).
  `mtf_analyzer.py` sets `numpy.NaN = numpy.nan` before importing
  `pandas_ta`, guarded so it's a no-op on numpy versions where `NaN` still
  exists.
- **Risk formulas** (`DynamicRiskManager`, ATR-based): `SL = entry - 1.5*ATR`,
  `TP1 = entry + 2*ATR`, `TP2 = entry + 3*ATR`, validated against a minimum
  1:2 reward/risk ratio.
- **LLM integration** (`AITraderPersona`): Anthropic Messages API
  (`anthropic` SDK), model configurable via `ANTHROPIC_MODEL` env var
  (default `claude-sonnet-5`), key via `ANTHROPIC_API_KEY`. Structured
  output enforced via a Pydantic `TradeRecommendation` schema (symbol,
  market_regime, signal enum, confidence_score, entry/sl/tp1/tp2,
  trader_commentary in Turkish, 3-4 sentences, professional fund-manager
  tone).
- **News sentiment decoupling**: `AITraderPersona` takes an optional
  `news_sentiment: Optional[Dict[str, Any]]` parameter rather than calling
  `core/news_analyzer.py` itself — keeps the class independently testable;
  wiring an adapter to the existing news engine is left to a future pass.
- **New deps**: `pandas-ta`, `anthropic` added to `backend/requirements.txt`.

## Testing

Unit tests per layer with synthetic OHLCV DataFrames (no live network
calls): regime classification boundary cases (clear bull/bear/range/choppy),
risk math (SL/TP formulas, R:R gate), and a mocked Anthropic client for
`AITraderPersona`. `HybridTradingEngine` integration test wires mocked
layers end-to-end.

## Out of scope

- FastAPI endpoint wiring in `main.py`.
- Reusing/removing existing `core/analyzer.py`, `core/scoring.py`, or `v2/`.
- Live news sentiment adapter.

## Revision (2026-07-22): LLM provider swapped to Groq

`AITraderPersona` now calls Groq's free-tier, OpenAI-compatible Chat
Completions API (`groq` SDK, `GROQ_API_KEY` / `GROQ_MODEL` env vars,
default model `llama-3.3-70b-versatile`) instead of Anthropic. Structured
output is enforced via forced tool-calling against a hand-written JSON
schema (not Pydantic's `model_json_schema()`, to avoid `$ref`/`$defs`
resolution issues some providers have with tool parameters), then
validated into the same `TradeRecommendation` Pydantic model. `anthropic`
was dropped from `requirements.txt` in favor of `groq`.

## Revision (2026-07-22): production readiness — cache, news adapter, dashboard

- **`core/cache_manager.py`** — no shared cache utility existed in the repo
  (checked: `news_analyzer.py`/`sector_intelligence.py` each have their own
  ad-hoc module-level dict+timestamp cache). Added a small generic
  `TTLCache[V]` (thread-safe, in-memory, no persistence) following that same
  established pattern, for reuse beyond this one call site.
- **`HybridTradingEngine`** now caches each symbol's `TradeRecommendation`
  for 15 minutes (`recommendation_cache_ttl_seconds`, constructor-overridable).
  On a cache hit, `_process_symbol` returns the cached object directly and
  skips `MultiTimeframeAnalyzer.analyze`, `DynamicRiskManager.calculate`, and
  the Groq call entirely — only `MarketRegimeScanner.scan_and_filter` (cheap,
  batched) still runs every `run()` call, so regime/price context stays
  reasonably fresh even under a 60s dashboard refresh loop.
- **`core/news_adapter.py`** (`NewsSentimentAdapter`) — thin wrapper around
  the existing `core/news_analyzer.analyze_news`, converting its
  `NewsAnalysisResult` into the compact dict `AITraderPersona` already
  accepted via `news_sentiment`. Deliberately drops the verbose per-headline
  `news_items` list to keep the LLM prompt small — only aggregate
  score/label/counts + top headlines are passed through. No extra caching
  layer added since `analyze_news` already caches internally (30 min).
  `HybridTradingEngine` now wires this in by default.
- **`dashboard.py`** — full-screen `rich.live.Live` terminal dashboard,
  polling `HybridTradingEngine.run()` every 60s (cheap thanks to the cache
  above). Left panel: summary table of all scanned symbols. Right panel:
  full AI commentary + risk levels for a "selected" symbol, changeable via
  number keys (1-9) read from a background thread that puts terminal stdin
  into cbreak mode (falls back to read-only, no-selection mode when stdin
  isn't a tty). Verified via a `timeout`-bounded smoke run that it survives
  per-symbol AI failures without crashing the display loop.

## Revision (2026-07-22): REST API for mobile clients

- **`backend/api/v1/`** — new package (`endpoints/signals.py` + `router.py`),
  mirroring the FastAPI `api/v1/endpoints/` convention the user expected
  (this tree did not exist before — only `v2/api/router.py`, a flat
  single-file router, existed). `POST /api/v1/signals/analyze` takes
  `{"symbols": [...]}` (`SignalsAnalyzeRequest`, 1-20 items) and returns
  `List[TradeRecommendation]` directly (reusing the existing Pydantic model
  for Swagger/OpenAPI docs, no duplication).
- **Engine singleton**: `get_engine()` in `signals.py` uses
  `functools.lru_cache()` as the standard FastAPI singleton-dependency
  pattern. This is load-bearing, not cosmetic — `HybridTradingEngine`'s
  15-minute recommendation cache only provides cross-request value if the
  same engine instance (and thus the same cache) is reused across requests;
  a fresh instance per request would silently defeat it. Verified via a real
  HTTP round-trip: first call ~4.8s, identical second call ~0.35s.
- **`core/rate_limiter.py`** — extracted the `slowapi.Limiter` instance
  `main.py` already had inline into its own module so `signals.py` can apply
  `@limiter.limit("20/minute")` without a circular import (`main.py` → `api/v1/router.py`
  → `signals.py` → back to `main.py` would otherwise be required to reach
  the limiter). `main.py` now imports `limiter` from there instead of
  constructing it inline; behavior is unchanged for existing endpoints.
- **`from __future__ import annotations` removed from `signals.py`**:
  combined with `@limiter.limit(...)`, deferred/stringified annotations
  broke FastAPI's runtime type resolution (`PydanticUndefinedAnnotation:
  name 'SignalsAnalyzeRequest' is not defined`) because slowapi's wrapper
  function's `__globals__` points at slowapi's own module, not `signals.py`'s.
  Removing the future-import makes annotations evaluate eagerly at
  definition time, sidestepping the lookup entirely. Class ordering in the
  file was already safe for this (no forward references).
- **Two unrelated pre-existing bugs fixed to unblock testing** (`main.py`
  could not start at all before this): (1) every file under `v2/` imported
  itself as `from backend.v2....`, which only resolves if the process is
  run with the *parent* of `backend/` on the path — but the `Dockerfile`
  (`WORKDIR /app`, `COPY . .` from within `backend/`) and every manual
  invocation this session run with `backend/` itself as the root, matching
  `main.py`'s own bare `core.*`/`v2.*` imports. Stripped the `backend.`
  prefix across all 10 affected files. (2) `v2/core/engine.py` had a
  leftover duplicated tail fragment after `TradingEngineV2.analyze`'s
  `return` (stray `risk_score=risk_score, timestamp=..., )` after the
  function already returned) causing an `IndentationError`— deleted the
  dead fragment. Neither fix touches `v2/` behavior, only makes it importable.
- **`backend/.env` format bug**: the user's existing `.env` contained the
  raw key value with no `GROQ_API_KEY=` prefix (not a `KEY=VALUE` line), so
  `python-dotenv` couldn't load it. Fixed in place. Also added
  `load_dotenv()` to `main.py` (already present in `test_engine.py` /
  `dashboard.py`) so the API server picks up `backend/.env` the same way.
