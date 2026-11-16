"""
Regression tests for core/advanced_analysis.py's compute_recommendation():
when the XGBoost model is unavailable (core.ml_predictor.get_ml_confidence
returns None - missing/corrupt artifact, or any other load/predict
failure), the function previously still claimed a 25%/30% "xgboost_ml"
weight in its returned `score_weights` breakdown, while silently
substituting the rule-based score_norm in its place for the actual
composite-score math (`ml_norm = score_norm`). This made the API's own
reported weight breakdown misleading whenever the model was simply
absent - exactly the "silently hides an infrastructure failure" class
of bug (CTO Remediation Plan Section 6.5's "the legacy XGBoost's weight
must contribute exactly 0% and reallocate to canonical score" applies
here directly, independent of the full Model Registry integration).

The fix only changes what `score_weights`/`reasons` honestly report;
the actual composite_score/action/color computed is proven unchanged
(see test_composite_score_is_unchanged_...) - this is a reporting fix,
not a trading-signal change.
"""
from core.advanced_analysis import compute_recommendation


def test_score_weights_reports_zero_percent_when_ml_confidence_is_unavailable():
    result = compute_recommendation(
        score=70, ml_confidence=None, monte_carlo=None, risk_level="Orta",
    )

    assert result["score_weights"]["xgboost_ml"] != "30%"
    assert "0%" in result["score_weights"]["xgboost_ml"]


def test_score_weights_reallocates_the_dropped_ml_weight_to_rule_based():
    result = compute_recommendation(
        score=70, ml_confidence=None, monte_carlo=None, risk_level="Orta",
    )

    # 50% + 30% (ML's dropped weight) = 80%, monte_carlo stays 20%
    assert result["score_weights"]["rule_based"] == "80%"
    assert result["score_weights"]["monte_carlo"] == "20%"


def test_score_weights_reallocates_correctly_when_chart_ai_is_present():
    result = compute_recommendation(
        score=70, ml_confidence=None, monte_carlo=None, risk_level="Orta",
        chart_ai={"signal": "BUY", "confidence": 0.8},
    )

    # 40% + 25% (ML's dropped weight) = 65%, monte_carlo and chart_ai unaffected
    assert result["score_weights"]["rule_based"] == "65%"
    assert "0%" in result["score_weights"]["xgboost_ml"]
    assert result["score_weights"]["monte_carlo"] == "20%"
    assert result["score_weights"]["chart_ai"] == "15%"


def test_score_weights_still_reports_the_real_percentage_when_ml_confidence_is_present():
    """Unchanged, existing behavior - a regression guard."""
    without_chart_ai = compute_recommendation(
        score=70, ml_confidence=0.7, monte_carlo=None, risk_level="Orta",
    )
    assert without_chart_ai["score_weights"]["rule_based"] == "50%"
    assert without_chart_ai["score_weights"]["xgboost_ml"] == "30%"

    with_chart_ai = compute_recommendation(
        score=70, ml_confidence=0.7, monte_carlo=None, risk_level="Orta",
        chart_ai={"signal": "BUY", "confidence": 0.8},
    )
    assert with_chart_ai["score_weights"]["rule_based"] == "40%"
    assert with_chart_ai["score_weights"]["xgboost_ml"] == "25%"


def test_reasons_mentions_ml_unavailability_when_ml_confidence_is_none():
    result = compute_recommendation(
        score=70, ml_confidence=None, monte_carlo=None, risk_level="Orta",
    )

    assert any("XGBoost" in reason for reason in result["reasons"])


def test_reasons_still_mentions_xgboost_confidence_when_ml_confidence_is_present():
    """Unchanged, existing behavior - a regression guard."""
    result = compute_recommendation(
        score=70, ml_confidence=0.7, monte_carlo=None, risk_level="Orta",
    )

    assert any("XGBoost modeli yukselis ihtimali" in reason for reason in result["reasons"])


def test_composite_score_is_unchanged_by_this_fix_when_ml_confidence_is_none():
    """The whole point of this fix is that it changes REPORTING only -
    the actual trading signal/composite score must be bit-for-bit
    identical to before, since `ml_weight=0.0` applied to any value of
    `ml_norm` contributes nothing either way, and the previous
    `ml_norm = score_norm` substitution was already mathematically
    equivalent to today's explicit reallocation (0.50+0.30=0.80 either
    way). Proven here by comparing against an explicit score_norm-as-
    ml_confidence call, which is what the old code effectively computed."""
    unavailable = compute_recommendation(
        score=70, ml_confidence=None, monte_carlo=None, risk_level="Orta",
    )
    explicit_equivalent = compute_recommendation(
        score=70, ml_confidence=0.70, monte_carlo=None, risk_level="Orta",
    )

    # NOT comparing against the ml_confidence=0.70 case's OWN weights
    # (that case correctly uses 50/30/20) - comparing the actual
    # composite_score number, which must match because 0.80*0.70 + 0.20*mc
    # (today's explicit path) == 0.50*0.70 + 0.30*0.70 + 0.20*mc (the old
    # ml_norm=score_norm substitution) for this specific score_norm.
    assert unavailable["composite_score"] == explicit_equivalent["composite_score"]
    assert unavailable["action_code"] == explicit_equivalent["action_code"]
