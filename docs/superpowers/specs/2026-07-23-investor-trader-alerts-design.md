# Investor/Trader Dual Profile + Market Alerts — Design

Date: 2026-07-23

## Context

`HybridTradingEngine` (see `2026-07-22-hybrid-quant-trading-design.md`) already
scans market regime, runs multi-timeframe technical analysis, computes
ATR-based risk levels, and calls `AITraderPersona` (Groq LLM) to produce a
single short-term `TradeRecommendation` per symbol. This is wired to
`POST /api/v1/signals/analyze` and the iOS AI Hub screen.

The product's core purpose is broader than short-term trade calls: it should
act as an investment expert for users with no market background, guiding
them differently depending on whether they trade actively or invest
long-term, and warning them when market conditions change suddenly. This
spec adds that without touching the existing trader path.

## Goal

1. Let a caller choose a `profile`: `"trader"` (today's behavior, unchanged)
   or `"investor"` (new: separate buy/hold/sell calls with confidence scores
   for 1 week / 1 month / 1 year horizons, no entry/SL/TP).
2. Detect sudden market changes (price/volume shocks, high-impact news) for
   any requested symbol and expose them via a new, separate alerts endpoint.

## Architecture

Folds into the existing engine rather than adding parallel orchestrators
(chosen over a fully separate `AlertsEngine`, to reuse data already fetched
per symbol instead of re-fetching from yfinance):

```
core/
  investor_persona.py         InvestorPersona, HorizonView, InvestorRecommendation   (NEW)
  market_anomaly_detector.py  MarketAnomalyDetector, MarketAlert                     (NEW)
  mtf_analyzer.py             + daily_return_pct, price_move_atr_multiple             (MODIFIED)
  hybrid_engine.py            + profile param, + check_alerts(), + alert cache        (MODIFIED)
api/v1/endpoints/
  signals.py                  + profile field, + POST /signals/alerts                (MODIFIED)
```

## Data flow

```
POST /signals/analyze {symbols, profile: "trader"|"investor" = "trader"}
  -> HybridTradingEngine.run(symbols, profile)
     -> scanner.scan_and_filter(symbols)                 [unchanged: drops CHOPPY]
     -> per symbol, on recommendation-cache miss:
          analysis   = analyzer.analyze(symbol)
          news       = news_adapter.get_sentiment(symbol)
          _update_alert_cache(symbol, scanned, analysis, news)   # side effect, free reuse
          profile == "trader":
            risk = risk_manager.calculate(...)
            rec  = ai_persona.generate_recommendation(..., risk, ...)
          profile == "investor":
            rec  = investor_persona.generate_recommendation(symbol, scanned.regime, analysis, news)
  -> List[TradeRecommendation] | List[InvestorRecommendation]

POST /signals/alerts {symbols}
  -> HybridTradingEngine.check_alerts(symbols)
     -> scanner.scan(symbols)   UNFILTERED — a shock is often what breaks a CHOPPY regime
     -> per symbol:
          alert-cache hit (2 min TTL) -> return cached (or None if cached "no alert" sentinel)
          else: fetch analysis + news fresh (independent of the 15-min recommendation
                cache — alerts need fresher data), run MarketAnomalyDetector.detect()
  -> List[MarketAlert]   (empty list is a normal, expected result — not a 404)
```

## Key decisions

- **Profile is a request parameter**, not a stored user preference (backend-only
  pass; the iOS side can start passing a saved preference later without any
  backend change). Default `"trader"` keeps existing callers working unchanged.
- **`HybridTradingEngine`'s trader path is byte-for-byte unchanged.** The
  investor path is purely additive: a new branch in `_process_symbol`, a new
  cache (`_investor_cache`, same 15-minute TTL, separate from the trader
  recommendation cache so switching profiles for the same symbol doesn't
  evict the other profile's cached result).
- **`InvestorRecommendation`** (`core/investor_persona.py`):
  ```
  symbol, market_regime
  horizon_1_week:  HorizonView
  horizon_1_month: HorizonView
  horizon_1_year:  HorizonView
  investor_commentary: str   # CIO-style synthesis across all three horizons
  ```
  `HorizonView = {signal: TradeSignal, confidence_score: int (0-100), rationale: str}`.
  Reuses the existing `TradeSignal` enum from `ai_trader_persona.py` (no
  duplicate enum). No entry/SL/TP fields — investing is not a timed trade.
- **`InvestorPersona` skips `DynamicRiskManager` entirely** — ATR/volatility
  context is still passed into the LLM prompt (to calibrate confidence,
  e.g. high volatility should lower short-horizon confidence) but no
  SL/TP is computed or returned.
- **System prompt follows the same "sequential expert personas, then
  synthesize" pattern** already used in `AITraderPersona` (proven to improve
  forced tool-calling quality): reason through the 1-week view first (short
  technical momentum + regime), then 1-month (regime persistence + weekly
  trend), then 1-year (macro news category + regime durability), then
  synthesize into `investor_commentary`. All narrative fields Turkish-only,
  same constraint as the existing persona.
- **Known limitation, stated explicitly, not hidden**: this pipeline has no
  fundamentals data source (P/E, earnings growth, balance sheet — those
  signal engines exist only in the older, separate `core/analyzer.py` path,
  not wired into `HybridTradingEngine`). The 1-year view therefore leans on
  regime persistence and macro news only. `InvestorPersona.generate_recommendation`
  **code-appends a fixed Turkish disclaimer sentence** to `investor_commentary`
  after the LLM call (not left to the model's discretion) — this is a
  compliance-relevant honesty requirement, not something to hope the LLM
  remembers every time.
- **Alert triggers — both numeric and news, combined per requirements**:
  - `PRICE_VOLUME_SHOCK`: `analysis["micro"]["volume_ratio"] >= 3.0` (stricter
    than the existing 1.5x `volume_spike` flag used in trade-recommendation
    prompts — an alert should mean something more unusual than a normal
    trade signal input) **OR** `price_move_atr_multiple >= 2.5` (new field,
    see below).
  - `NEWS_SHOCK`: reuses the existing `news_sentiment["impact_level"] == "HIGH"`
    (already means `abs(sentiment_score) >= 0.6`) — no new news logic needed.
  - Both firing at once -> `alert_type = "COMBINED"`, `severity = "HIGH"`.
    Either alone -> `severity = "MEDIUM"`.
  - Direction: price-move sign and news sentiment direction agree -> that
    direction; they disagree -> `"NEUTRAL"` with a message noting mixed
    signals ("yön belirsiz, dikkatli izleyin").
- **`mtf_analyzer.py` gains two fields in `_analyze_macro`'s return dict**:
  `daily_return_pct` (last close vs. previous close, %) and
  `price_move_atr_multiple` (`abs(daily_return_pct-equivalent price delta) / atr_daily`)
  — needed by `MarketAnomalyDetector`, not currently computed anywhere.
  Purely additive to the existing dict; no existing key changes shape.
- **Alerts use a separate, shorter-lived cache (2 minutes)** than the
  15-minute recommendation cache, since "sudden" by definition needs fresher
  data than a trade commentary that's still valid for 15 minutes.
  `TTLCache.get()` cannot distinguish a legitimately-cached `None` from a
  cache miss (both return `None`), so a module-level sentinel object (not
  `None`) is cached to mean "checked recently, no alert" — avoiding a
  refetch every call within the 2-minute window.
- **Alerts run over `scan()` (unfiltered), not `scan_and_filter()`** — a
  CHOPPY regime symbol suddenly showing a volume/price shock is exactly the
  kind of regime-change signal a user should be warned about; filtering it
  out before alert-checking would defeat the purpose.
- **Response typing**: `POST /signals/analyze`'s `response_model` becomes
  `List[Union[TradeRecommendation, InvestorRecommendation]]`. Pydantic v2's
  default "smart union" mode disambiguates by shape (SL/TP fields vs.
  horizon fields) without needing an explicit discriminator field — the
  existing, iOS-consumed `TradeRecommendation` model is not modified.
- **`POST /signals/alerts`** reuses `SignalsAnalyzeRequest` (same symbol-list
  body shape, no new request model) and returns `List[MarketAlert]`. Unlike
  `/analyze`, an empty list is a normal 200 response (no alerts is the common
  case), not a 404.

## Testing

- `MarketAnomalyDetector`: boundary cases for volume-only, price-only,
  news-only, combined, and no-trigger inputs; direction agreement/conflict
  cases.
- `InvestorPersona`: mocked Groq client, schema validation for all three
  horizons, disclaimer sentence always present in `investor_commentary`
  regardless of what the mocked LLM returns.
- `HybridTradingEngine`: profile branching returns the correct type and
  uses the correct cache; alert cache gets populated as a side effect of a
  recommendation-cache-miss fetch (no extra yfinance call in that path);
  `check_alerts()` works independently of `run()` ever having been called
  for that symbol; alert cache TTL (2 min) is independent of the
  recommendation cache TTL (15 min).
- API: `profile` field accepted/defaulted correctly; response validates as
  the right union member; `/signals/alerts` returns 200 with an empty list
  when nothing triggers (contrast with `/signals/analyze`'s 404-on-empty).

## Out of scope

- iOS wiring — no screen consumes `profile` or calls `/signals/alerts` yet;
  same deliberate separation as the last two specs (backend and iOS
  integration land in separate passes).
- Fundamentals data integration for the 1-year investor view (explicitly
  called out as a stated limitation above, not solved here).
- Persistent/DB-backed user profile preference (profile stays a per-request
  parameter this pass).
- Push notifications or any delivery mechanism for alerts beyond the
  `POST /signals/alerts` endpoint itself.
- Any change to the existing trader path's prompt, schema, or cache
  behavior.
