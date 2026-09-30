"""
Unit tests for signals/decision.py — interface and DTOs only.

Tests verify:
  - DecisionInput can be instantiated with required and optional fields
  - DecisionOutput fields are accessible and to_dict() is correct
  - DecisionEngineProtocol is a @runtime_checkable Protocol
  - NullDecisionEngine satisfies DecisionEngineProtocol
  - NullDecisionEngine.decide() returns a valid DecisionOutput
  - DecisionOutput probabilities sum to 1.0
  - A concrete class implementing decide() satisfies the Protocol
  - A class missing decide() does NOT satisfy the Protocol

No network calls, no mocks — pure interface verification.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from signals.decision import (
    DecisionInput, DecisionOutput,
    DecisionEngineProtocol, NullDecisionEngine,
)
from signals.models import SignalCollection


# ── Test helpers ──────────────────────────────────────────────────────────────

def _input(**kwargs) -> DecisionInput:
    defaults = dict(
        symbol="AAPL",
        asset_type="stock",
        signal_collection=SignalCollection(),
        current_score=55.0,
    )
    defaults.update(kwargs)
    return DecisionInput(**defaults)


# ── DecisionInput ─────────────────────────────────────────────────────────────

class TestDecisionInput:
    def test_required_fields(self):
        di = _input()
        assert di.symbol == "AAPL"
        assert di.asset_type == "stock"
        assert di.current_score == 55.0

    def test_current_price_optional(self):
        di = _input()
        assert di.current_price is None

    def test_current_price_can_be_set(self):
        di = _input(current_price=182.5)
        assert di.current_price == 182.5

    def test_signal_collection_stored(self):
        sc = SignalCollection()
        di = _input(signal_collection=sc)
        assert di.signal_collection is sc

    def test_crypto_asset_type(self):
        di = _input(symbol="BTC-USD", asset_type="crypto")
        assert di.asset_type == "crypto"


# ── DecisionOutput ────────────────────────────────────────────────────────────

class TestDecisionOutput:
    def _out(self, **kw) -> DecisionOutput:
        defaults = dict(
            buy_probability=0.6,
            sell_probability=0.1,
            hold_probability=0.3,
            confidence=0.75,
            risk_level="MEDIUM",
            expected_horizon="MEDIUM",
            dominant_direction="BULLISH",
        )
        defaults.update(kw)
        return DecisionOutput(**defaults)

    def test_probabilities_accessible(self):
        out = self._out()
        assert out.buy_probability == 0.6
        assert out.sell_probability == 0.1
        assert out.hold_probability == 0.3

    def test_probabilities_sum_to_one(self):
        out = self._out()
        total = out.buy_probability + out.sell_probability + out.hold_probability
        assert abs(total - 1.0) < 1e-9

    def test_confidence_accessible(self):
        assert self._out().confidence == 0.75

    def test_risk_level_accessible(self):
        assert self._out().risk_level == "MEDIUM"

    def test_expected_horizon_accessible(self):
        assert self._out().expected_horizon == "MEDIUM"

    def test_dominant_direction_accessible(self):
        assert self._out().dominant_direction == "BULLISH"

    def test_reasoning_defaults_empty(self):
        assert self._out().reasoning == []

    def test_contributing_engines_defaults_empty(self):
        assert self._out().contributing_engines == []

    def test_reasoning_can_be_set(self):
        out = self._out(reasoning=["RSI oversold", "Strong fundamentals"])
        assert len(out.reasoning) == 2

    def test_to_dict_has_all_keys(self):
        out = self._out()
        d = out.to_dict()
        expected = {
            "buy_probability", "sell_probability", "hold_probability",
            "confidence", "risk_level", "expected_horizon",
            "dominant_direction", "reasoning", "contributing_engines",
        }
        assert set(d.keys()) == expected

    def test_to_dict_values_match_fields(self):
        out = self._out()
        d = out.to_dict()
        assert d["buy_probability"] == 0.6
        assert d["dominant_direction"] == "BULLISH"

    def test_null_output_probabilities_sum_to_one(self):
        # NullDecisionEngine output
        null_out = NullDecisionEngine().decide(_input())
        total = null_out.buy_probability + null_out.sell_probability + null_out.hold_probability
        assert abs(total - 1.0) < 1e-9


# ── DecisionEngineProtocol ────────────────────────────────────────────────────

class TestDecisionEngineProtocol:
    def test_null_engine_satisfies_protocol(self):
        assert isinstance(NullDecisionEngine(), DecisionEngineProtocol)

    def test_concrete_class_with_decide_satisfies_protocol(self):
        class StubEngine:
            def decide(self, input: DecisionInput) -> DecisionOutput:
                return DecisionOutput(
                    buy_probability=0.0, sell_probability=0.0, hold_probability=1.0,
                    confidence=0.0, risk_level="UNKNOWN", expected_horizon="UNKNOWN",
                    dominant_direction="NEUTRAL",
                )
        assert isinstance(StubEngine(), DecisionEngineProtocol)

    def test_class_without_decide_does_not_satisfy_protocol(self):
        class NoDecide:
            pass
        assert not isinstance(NoDecide(), DecisionEngineProtocol)

    def test_plain_object_does_not_satisfy_protocol(self):
        assert not isinstance(object(), DecisionEngineProtocol)


# ── NullDecisionEngine ────────────────────────────────────────────────────────

class TestNullDecisionEngine:
    def test_decide_returns_decision_output(self):
        out = NullDecisionEngine().decide(_input())
        assert isinstance(out, DecisionOutput)

    def test_null_engine_direction_is_neutral(self):
        out = NullDecisionEngine().decide(_input())
        assert out.dominant_direction == "NEUTRAL"

    def test_null_engine_hold_probability_is_one(self):
        out = NullDecisionEngine().decide(_input())
        assert out.hold_probability == 1.0

    def test_null_engine_confidence_is_zero(self):
        out = NullDecisionEngine().decide(_input())
        assert out.confidence == 0.0

    def test_null_engine_risk_unknown(self):
        out = NullDecisionEngine().decide(_input())
        assert out.risk_level == "UNKNOWN"

    def test_null_engine_horizon_unknown(self):
        out = NullDecisionEngine().decide(_input())
        assert out.expected_horizon == "UNKNOWN"

    def test_null_engine_has_reasoning(self):
        out = NullDecisionEngine().decide(_input())
        assert len(out.reasoning) > 0

    def test_null_engine_contributing_engines_from_signal_collection(self):
        from signals.models import EngineResult
        sc = SignalCollection(
            technical=EngineResult.from_signals("TECHNICAL", []),
            fundamental=EngineResult.from_signals("FUNDAMENTAL", []),
        )
        out = NullDecisionEngine().decide(_input(signal_collection=sc))
        assert "technical" in out.contributing_engines
        assert "fundamental" in out.contributing_engines

    def test_null_engine_empty_collection_has_no_contributing_engines(self):
        out = NullDecisionEngine().decide(_input(signal_collection=SignalCollection()))
        assert out.contributing_engines == []

    def test_null_engine_never_raises(self):
        # Should not raise even with a minimal input
        NullDecisionEngine().decide(_input())

    def test_to_dict_is_serialisable(self):
        import json
        out = NullDecisionEngine().decide(_input())
        # Should not raise — all values are JSON-compatible
        json.dumps(out.to_dict())
