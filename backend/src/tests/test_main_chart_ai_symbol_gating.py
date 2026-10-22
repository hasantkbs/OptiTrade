"""Regression test for main.py::_enrich_result's chart-AI gate.

The BTC chart model (ml/chart_model.py) is trained and validated on
BTC-USD only - its scaler and learned weights reflect BTC's own price/
volatility distribution. `_enrich_result` used to call
`predict_chart_signal()` for ANY symbol whenever a model file existed
on disk at all, with no symbol check - so the moment a BTC-specific
model became available, every other symbol's analysis (stocks, other
cryptos, BIST equities) would also run its own features through the
BTC-trained model and get a `chart_ai` signal baked into its
recommendation at 15% weight. Fixed by gating on
`ml.chart_model.MODEL_SYMBOL`."""
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


def test_chart_ai_runs_for_the_symbol_the_model_was_trained_on(monkeypatch):
    monkeypatch.setattr(chart_model, "is_model_available", lambda: True)
    calls = []
    monkeypatch.setattr(
        chart_model, "predict_chart_signal",
        lambda hist: calls.append(1) or {"signal": "BUY", "confidence": 0.9,
                                          "probabilities": {"sell": 0.05, "neutral": 0.05, "buy": 0.9},
                                          "model_available": True},
    )
    import yfinance as yf
    import pandas as pd
    monkeypatch.setattr(
        yf.Ticker, "history",
        lambda self, period=None: pd.DataFrame({"Close": [1.0]}),
    )

    main_module._enrich_result(_analysis_result(chart_model.MODEL_SYMBOL), None)

    assert calls == [1]


def test_chart_ai_is_skipped_for_a_different_symbol(monkeypatch):
    monkeypatch.setattr(chart_model, "is_model_available", lambda: True)
    calls = []
    monkeypatch.setattr(
        chart_model, "predict_chart_signal",
        lambda hist: calls.append(1),
    )

    main_module._enrich_result(_analysis_result("AAPL"), None)

    assert calls == []
