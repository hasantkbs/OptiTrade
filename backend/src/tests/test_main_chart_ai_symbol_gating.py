"""Regression test for main.py::_enrich_result's chart-AI gate.

The chart model (ml/chart_model.py) is trained and validated per
symbol - each symbol's own scaler/weights reflect only that symbol's
price/volatility distribution. `_enrich_result` used to call
`predict_chart_signal()` for ANY symbol whenever a model file existed
on disk at all, with no symbol check - so the moment a BTC-specific
model became available, every other symbol's analysis (stocks, other
cryptos, BIST equities) would also run its own features through the
BTC-trained model and get a `chart_ai` signal baked into its
recommendation at 15% weight. Fixed by gating on
`ml.chart_model.get_supported_symbols()` and passing each symbol
through to `is_model_available()`/`predict_chart_signal()` explicitly,
so each symbol uses its own file - not a hardcoded default.

Tests monkeypatch `get_supported_symbols` itself rather than relying
on the real supported_symbols.json contents - that file is live state
updated weekly by research/retrain_chart_models.py, and a test
depending on its real (growing) contents would be both slow (iterates
every live symbol) and fragile to future retraining runs."""
import main as main_module
import ml.chart_model as chart_model
from models.schemas import AnalysisResult, TechnicalIndicators


def _analysis_result(symbol: str) -> AnalysisResult:
    return AnalysisResult(
        symbol=symbol, decision="Al", decision_code="BUY", score=10,
        risk_level="Orta", balance_status="ok",
        indicators=TechnicalIndicators(
            current_price=100.0, open_price=99.0, price_velocity=0.01,
            daily_volume=1000.0, avg_monthly_volume=900.0, volume_ratio=1.1,
        ),
        asset_type="crypto",
    )


def _stub_history(monkeypatch):
    import yfinance as yf
    import pandas as pd
    monkeypatch.setattr(
        yf.Ticker, "history",
        lambda self, period=None: pd.DataFrame({"Close": [1.0]}),
    )


def test_chart_ai_runs_for_a_supported_symbol_using_its_own_model(monkeypatch):
    monkeypatch.setattr(chart_model, "get_supported_symbols", lambda: ("ETH-USD", "BTC-USD"))
    calls = []
    monkeypatch.setattr(chart_model, "is_model_available", lambda symbol: calls.append(("available", symbol)) or True)
    monkeypatch.setattr(
        chart_model, "predict_chart_signal",
        lambda hist, symbol: calls.append(("predict", symbol)) or {
            "signal": "BUY", "confidence": 0.9,
            "probabilities": {"sell": 0.05, "neutral": 0.05, "buy": 0.9},
            "model_available": True,
        },
    )
    _stub_history(monkeypatch)

    main_module._enrich_result(_analysis_result("ETH-USD"), None)

    assert ("available", "ETH-USD") in calls
    assert ("predict", "ETH-USD") in calls


def test_chart_ai_runs_for_every_supported_symbol_not_just_the_first(monkeypatch):
    fake_supported = ("ETH-USD", "BTC-USD", "THYAO.IS")
    monkeypatch.setattr(chart_model, "get_supported_symbols", lambda: fake_supported)
    calls = []
    monkeypatch.setattr(chart_model, "is_model_available", lambda symbol: True)
    monkeypatch.setattr(
        chart_model, "predict_chart_signal",
        lambda hist, symbol: calls.append(symbol) or None,
    )
    _stub_history(monkeypatch)

    for symbol in fake_supported:
        main_module._enrich_result(_analysis_result(symbol), None)

    assert calls == list(fake_supported)


def test_chart_ai_is_skipped_for_an_unsupported_symbol(monkeypatch):
    monkeypatch.setattr(chart_model, "get_supported_symbols", lambda: ("ETH-USD", "BTC-USD"))
    unsupported_symbol = "NOT-A-SUPPORTED-SYMBOL"

    monkeypatch.setattr(chart_model, "is_model_available", lambda symbol: True)
    calls = []
    monkeypatch.setattr(
        chart_model, "predict_chart_signal",
        lambda hist, symbol: calls.append(symbol),
    )

    main_module._enrich_result(_analysis_result(unsupported_symbol), None)

    assert calls == []
