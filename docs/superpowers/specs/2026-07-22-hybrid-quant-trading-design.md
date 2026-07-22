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
