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

    def decide(self, symbol, strict=False):
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
    # score is scaled WITHIN the STRONG_BUY band (78-100), using the
    # fraction of confidence WITHIN the strong tier's sub-range
    # [0.75, 1.0] for continuity across the strong-signal threshold (see
    # core.analysis_presentation.to_analysis_decision): fraction =
    # (0.9-0.75)/0.25 = 0.6, 78 + round(0.6 * 22) == 91.
    assert result.score == 91


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


@patch("core.analyzer.to_analysis_decision")
@patch("core.analyzer.fetch_history", return_value=_fake_history())
@patch("decision_engine.service.get_default_decision_engine")
def test_analyze_falls_back_to_local_score_when_data_sufficiency_too_low(
    mock_get_engine, _mock_history, mock_to_analysis_decision
):
    """A successful-but-low-data_sufficiency DecisionOutput (e.g. only 1
    of 5 engines voted) must be treated the same as the exception
    fallback - the local/legacy score is kept, not silently overridden
    by a low-confidence-input decision (Finding 3). Proven directly by
    asserting `to_analysis_decision` (the function that would perform
    the override) is never even called, not just by checking the
    resulting decision_code is in-vocabulary."""
    low_sufficiency_output = DecisionOutput(
        symbol="AAPL", decision=Prediction.SELL, confidence=0.95,
        expected_return=0.0, expected_volatility=0.1,
        aggregation_strategy_version="test", data_sufficiency=0.2,
    )
    mock_get_engine.return_value = _FakeDecisionEngine(low_sufficiency_output)
    from core.analyzer import analyze

    result = analyze(symbol="AAPL", asset_type="stock", include_news=False)
    assert result is not None
    mock_to_analysis_decision.assert_not_called()
    # Fallback still produces a valid 5-way decision_code from the
    # local get_decision(score) path.
    assert result.decision_code in {"STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"}
