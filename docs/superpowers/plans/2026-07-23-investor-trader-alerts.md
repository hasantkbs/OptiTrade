# Investor/Trader Dual Profile + Market Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `HybridTradingEngine` so a caller can request either a short-term trader recommendation (existing, unchanged) or a long-term investor recommendation (new: separate 1-week/1-month/1-year buy/hold/sell calls), and add a separate market-alerts endpoint that detects sudden price/volume/news shocks.

**Architecture:** All new logic folds into the existing `core/hybrid_engine.py` orchestrator (per approved design doc `docs/superpowers/specs/2026-07-23-investor-trader-alerts-design.md`) rather than a parallel engine, so alert-checking and investor-profile generation reuse the `MultiTimeframeAnalyzer`/`NewsSentimentAdapter` data already fetched per symbol. Two new stateless/LLM classes (`InvestorPersona`, `MarketAnomalyDetector`) are added alongside the existing `AITraderPersona`.

**Tech Stack:** Python 3.13, FastAPI 0.115, Pydantic 2.7, Groq SDK (`groq`, forced tool-calling), pandas-ta 0.4.71b0, pytest, `unittest.mock`.

## Global Constraints

- **The trader path (`profile="trader"`, the default) must remain byte-for-byte behaviorally unchanged** — every existing test/assertion about `HybridTradingEngine.run()`'s trader output must still pass unmodified.
- **No changes to the existing `TradeRecommendation` schema** (`core/ai_trader_persona.py`) — iOS's `AIHubView` already decodes it.
- **Reuse `TradeSignal`** from `core/ai_trader_persona.py` for the new `InvestorRecommendation`'s horizon signals — do not define a second, duplicate enum.
- **No new pip dependencies.** `groq>=0.13.0` and `pandas-ta>=0.4.71b0` are already in `backend/requirements.txt`; both new classes use only packages already present (`groq`, `pydantic`).
- **All user-facing narrative text (LLM prompts, rationale strings, alert messages) must be Turkish-only**, matching the existing `AITraderPersona` convention.
- **No iOS changes** — this plan is backend-only, per the approved spec's explicit scope.
- **Test runner:** this session verified that neither `backend/venv` nor the system `python3` have `fastapi`/`groq`/`pandas-ta`/`pytest` installed together, but `/Users/hasantekbas/miniconda3/bin/python` does (after `pip install groq pandas-ta` this session, on top of its existing `fastapi`, `pydantic`, `pytest`, `httpx`). Run all test commands in this plan with `/Users/hasantekbas/miniconda3/bin/python -m pytest ...` from the `backend/` directory. If that environment is unavailable, install the missing packages there first: `/Users/hasantekbas/miniconda3/bin/pip install groq pandas-ta`.
- All new/modified Python files live under `backend/` and use the project's existing import style (bare `from core.xxx import ...`, not `from backend.core.xxx import ...` — see the hybrid-quant design doc's note on why `backend/` itself, not its parent, is the import root).
- Test files use the existing project convention: `sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))` at the top, then bare imports; `TestXxx` classes; plain `assert` statements (see `backend/tests/unit/test_decision_interface.py` for the reference style).

---

### Task 1: Add shock-detection fields to `MultiTimeframeAnalyzer`

**Files:**
- Modify: `backend/core/mtf_analyzer.py:87-119` (the `_analyze_macro` method)
- Test: `backend/tests/unit/test_mtf_analyzer_shock_fields.py` (new)

**Interfaces:**
- Produces: `MultiTimeframeAnalyzer._analyze_macro(df)`'s returned dict gains two new keys: `daily_return_pct: float` (last close vs. previous close, as a percentage) and `price_move_atr_multiple: float` (absolute last-day price move divided by that day's ATR). Both are read by `MarketAnomalyDetector` in Task 2 via `analysis["macro"]["daily_return_pct"]` / `analysis["macro"]["price_move_atr_multiple"]` (since `analyze()` already nests `_analyze_macro`'s return dict under the `"macro"` key — no other change needed to `analyze()` itself).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_mtf_analyzer_shock_fields.py`:

```python
"""
Unit tests for the two new shock-detection fields added to
MultiTimeframeAnalyzer._analyze_macro: daily_return_pct and
price_move_atr_multiple. Uses synthetic OHLC data (no network calls).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import numpy as np
import pandas as pd
import pytest

from core.mtf_analyzer import MultiTimeframeAnalyzer


def _make_daily_df(n: int = 260, start: float = 100.0, last_move_pct: float = None, seed: int = 7) -> pd.DataFrame:
    """Synthetic daily OHLC: a small random walk, with the LAST day's move
    forced to an exact percentage (relative to the second-to-last close) so
    tests can assert exact/comparative values without network data."""
    rng = np.random.default_rng(seed)
    closes = [start]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + rng.normal(0, 0.003)))
    closes = np.array(closes)
    if last_move_pct is not None:
        closes[-1] = closes[-2] * (1 + last_move_pct / 100)
    highs = closes * 1.01
    lows = closes * 0.99
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame({"High": highs, "Low": lows, "Close": closes}, index=idx)


ANALYZER = MultiTimeframeAnalyzer()


class TestDailyReturnPct:
    def test_matches_exact_forced_move(self):
        df = _make_daily_df(last_move_pct=3.0)
        result = ANALYZER._analyze_macro(df)
        assert abs(result["daily_return_pct"] - 3.0) < 0.01

    def test_negative_move_is_negative(self):
        df = _make_daily_df(last_move_pct=-4.0)
        result = ANALYZER._analyze_macro(df)
        assert result["daily_return_pct"] < 0
        assert abs(result["daily_return_pct"] - (-4.0)) < 0.01


class TestPriceMoveAtrMultiple:
    def test_present_and_non_negative(self):
        df = _make_daily_df(last_move_pct=1.0)
        result = ANALYZER._analyze_macro(df)
        assert "price_move_atr_multiple" in result
        assert result["price_move_atr_multiple"] >= 0

    def test_larger_move_yields_larger_multiple(self):
        small = ANALYZER._analyze_macro(_make_daily_df(last_move_pct=0.1, seed=7))
        big = ANALYZER._analyze_macro(_make_daily_df(last_move_pct=10.0, seed=7))
        assert big["price_move_atr_multiple"] > small["price_move_atr_multiple"]


class TestExistingFieldsUnaffected:
    def test_all_original_keys_still_present(self):
        df = _make_daily_df()
        result = ANALYZER._analyze_macro(df)
        for key in ("trend_direction", "ema50", "ema200", "ema_bullish_crossover",
                    "supertrend_bullish", "weekly_trend_up", "atr_daily"):
            assert key in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /Users/hasantekbas/miniconda3/bin/python -m pytest tests/unit/test_mtf_analyzer_shock_fields.py -v`
Expected: FAIL — `KeyError: 'daily_return_pct'` (or similar) in `TestDailyReturnPct`/`TestPriceMoveAtrMultiple`, since the field doesn't exist yet. `TestExistingFieldsUnaffected` should already PASS.

- [ ] **Step 3: Implement the two new fields**

In `backend/core/mtf_analyzer.py`, replace the `_analyze_macro` method:

```python
    def _analyze_macro(self, df: pd.DataFrame) -> Dict[str, Any]:
        """EMA 50/200 crossover, Supertrend ve haftalık trend yönünden makro görünüm."""
        close = df["Close"]

        ema50 = ta.ema(close, length=50)
        ema200 = ta.ema(close, length=200)
        atr = ta.atr(df["High"], df["Low"], close, length=14)
        supertrend = ta.supertrend(df["High"], df["Low"], close, length=10, multiplier=3.0)

        ema_bullish_crossover = bool(ema50.iloc[-1] > ema200.iloc[-1])

        st_direction_col = next(c for c in supertrend.columns if c.startswith("SUPERTd_"))
        supertrend_bullish = bool(supertrend[st_direction_col].iloc[-1] == 1)

        if ema_bullish_crossover and supertrend_bullish:
            trend_direction = "BULLISH"
        elif not ema_bullish_crossover and not supertrend_bullish:
            trend_direction = "BEARISH"
        else:
            trend_direction = "MIXED"

        weekly_close = close.resample("W").last().dropna()
        weekly_trend_up = bool(len(weekly_close) >= 2 and weekly_close.iloc[-1] > weekly_close.iloc[-2])

        atr_daily = float(atr.iloc[-1])
        daily_return_pct = (
            float((close.iloc[-1] / close.iloc[-2] - 1.0) * 100) if len(close) >= 2 else 0.0
        )
        price_move_atr_multiple = (
            float(abs(close.iloc[-1] - close.iloc[-2]) / atr_daily)
            if len(close) >= 2 and atr_daily > 0
            else 0.0
        )

        return {
            "trend_direction": trend_direction,
            "ema50": float(ema50.iloc[-1]),
            "ema200": float(ema200.iloc[-1]),
            "ema_bullish_crossover": ema_bullish_crossover,
            "supertrend_bullish": supertrend_bullish,
            "weekly_trend_up": weekly_trend_up,
            "atr_daily": atr_daily,
            "daily_return_pct": daily_return_pct,
            "price_move_atr_multiple": price_move_atr_multiple,
        }
```

(This is a pure addition: `atr_daily` is now computed once and reused, and two new keys are appended to the returned dict. No existing key's value or type changes.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /Users/hasantekbas/miniconda3/bin/python -m pytest tests/unit/test_mtf_analyzer_shock_fields.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/mtf_analyzer.py backend/tests/unit/test_mtf_analyzer_shock_fields.py
git commit -m "feat: add daily_return_pct and price_move_atr_multiple to MultiTimeframeAnalyzer"
```

---

### Task 2: `MarketAnomalyDetector` — sudden market change detection

**Files:**
- Create: `backend/core/market_anomaly_detector.py`
- Test: `backend/tests/unit/test_market_anomaly_detector.py`

**Interfaces:**
- Consumes: the `analysis` dict shape produced by `MultiTimeframeAnalyzer.analyze()` (specifically `analysis["micro"]["volume_ratio"]`, `analysis["macro"]["daily_return_pct"]`, `analysis["macro"]["price_move_atr_multiple"]` from Task 1) and the `news_sentiment` dict shape produced by `NewsSentimentAdapter.get_sentiment()` (`impact_level`, `sentiment_score`, `sentiment_label`) — both already exist, no changes needed to either.
- Produces: `MarketAlert` (pydantic model: `symbol: str`, `alert_type: Literal["PRICE_VOLUME_SHOCK","NEWS_SHOCK","COMBINED"]`, `severity: Literal["MEDIUM","HIGH"]`, `direction: Literal["BULLISH","BEARISH","NEUTRAL"]`, `message: str`, `details: Dict[str, Any]`, `detected_at: datetime`) and `MarketAnomalyDetector.detect(symbol: str, regime: MarketRegime, analysis: Dict[str, Any], news_sentiment: Optional[Dict[str, Any]]) -> Optional[MarketAlert]` — consumed by `HybridTradingEngine` in Task 4 via `self.anomaly_detector.detect(...)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_market_anomaly_detector.py`:

```python
"""
Unit tests for core/market_anomaly_detector.py — pure threshold logic,
no network calls, no LLM calls.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest

from core.market_anomaly_detector import MarketAlert, MarketAnomalyDetector
from core.regime_scanner import MarketRegime


def _analysis(volume_ratio=1.0, daily_return_pct=0.0, price_move_atr_multiple=0.0):
    return {
        "micro": {"volume_ratio": volume_ratio},
        "macro": {
            "daily_return_pct": daily_return_pct,
            "price_move_atr_multiple": price_move_atr_multiple,
        },
    }


def _news(impact_level=None, sentiment_score=0.0, sentiment_label="NEUTRAL"):
    if impact_level is None:
        return None
    return {
        "impact_level": impact_level,
        "sentiment_score": sentiment_score,
        "sentiment_label": sentiment_label,
    }


DETECTOR = MarketAnomalyDetector()


class TestNoTrigger:
    def test_calm_market_returns_none(self):
        result = DETECTOR.detect("AAPL", MarketRegime.RANGE_BOUND, _analysis(), None)
        assert result is None

    def test_missing_fields_default_safely(self):
        result = DETECTOR.detect("AAPL", MarketRegime.RANGE_BOUND, {}, None)
        assert result is None

    def test_low_impact_news_does_not_trigger(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.RANGE_BOUND, _analysis(),
            _news(impact_level="LOW", sentiment_score=0.1),
        )
        assert result is None


class TestPriceVolumeShock:
    def test_volume_ratio_above_threshold_triggers(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.TRENDING_BULL,
            _analysis(volume_ratio=3.5, daily_return_pct=2.0), None,
        )
        assert isinstance(result, MarketAlert)
        assert result.alert_type == "PRICE_VOLUME_SHOCK"
        assert result.severity == "MEDIUM"
        assert result.direction == "BULLISH"

    def test_atr_multiple_above_threshold_triggers_even_with_normal_volume(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.TRENDING_BEAR,
            _analysis(volume_ratio=1.0, daily_return_pct=-4.0, price_move_atr_multiple=3.0), None,
        )
        assert result is not None
        assert result.alert_type == "PRICE_VOLUME_SHOCK"
        assert result.direction == "BEARISH"

    def test_below_both_thresholds_does_not_trigger(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.RANGE_BOUND,
            _analysis(volume_ratio=1.4, daily_return_pct=0.5, price_move_atr_multiple=1.0), None,
        )
        assert result is None


class TestNewsShock:
    def test_high_impact_news_triggers(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.RANGE_BOUND, _analysis(),
            _news(impact_level="HIGH", sentiment_score=0.7, sentiment_label="POSITIVE"),
        )
        assert result is not None
        assert result.alert_type == "NEWS_SHOCK"
        assert result.severity == "MEDIUM"
        assert result.direction == "BULLISH"

    def test_high_impact_negative_news_is_bearish(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.RANGE_BOUND, _analysis(),
            _news(impact_level="HIGH", sentiment_score=-0.65, sentiment_label="NEGATIVE"),
        )
        assert result.direction == "BEARISH"


class TestCombined:
    def test_agreeing_signals_are_combined_high_severity(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.TRENDING_BULL,
            _analysis(volume_ratio=4.0, daily_return_pct=5.0),
            _news(impact_level="HIGH", sentiment_score=0.8, sentiment_label="POSITIVE"),
        )
        assert result.alert_type == "COMBINED"
        assert result.severity == "HIGH"
        assert result.direction == "BULLISH"

    def test_conflicting_signals_are_combined_neutral(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.TRENDING_BEAR,
            _analysis(volume_ratio=1.0, daily_return_pct=-3.0, price_move_atr_multiple=3.0),
            _news(impact_level="HIGH", sentiment_score=0.8, sentiment_label="POSITIVE"),
        )
        assert result.alert_type == "COMBINED"
        assert result.severity == "HIGH"
        assert result.direction == "NEUTRAL"
        assert "çelişiyor" in result.message


class TestMarketAlertShape:
    def test_details_includes_market_regime(self):
        result = DETECTOR.detect(
            "AAPL", MarketRegime.CHOPPY_NO_OPPORTUNITY,
            _analysis(volume_ratio=5.0, daily_return_pct=1.0), None,
        )
        assert result.details["market_regime"] == "CHOPPY_NO_OPPORTUNITY"

    def test_symbol_is_set(self):
        result = DETECTOR.detect(
            "BTC-USD", MarketRegime.TRENDING_BULL,
            _analysis(volume_ratio=5.0, daily_return_pct=1.0), None,
        )
        assert result.symbol == "BTC-USD"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /Users/hasantekbas/miniconda3/bin/python -m pytest tests/unit/test_market_anomaly_detector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.market_anomaly_detector'`

- [ ] **Step 3: Implement `MarketAnomalyDetector`**

Create `backend/core/market_anomaly_detector.py`:

```python
"""
OptiTrade — Market Anomaly Detector (Ani Piyasa Değişikliği Tespiti)
========================================================================
MultiTimeframeAnalyzer'ın ürettiği analiz sözlüğü ve NewsSentimentAdapter'ın
ürettiği haber özetinden, ek bir veri çekmeden (tamamen zaten hesaplanmış
metriklerden) ani piyasa değişikliği tespiti yapar. LLM çağrısı yapmaz —
saf, deterministik eşik kontrolü.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from core.regime_scanner import MarketRegime


class MarketAlert(BaseModel):
    """Tespit edilen ani piyasa değişikliği uyarısı."""

    symbol: str
    alert_type: Literal["PRICE_VOLUME_SHOCK", "NEWS_SHOCK", "COMBINED"]
    severity: Literal["MEDIUM", "HIGH"]
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MarketAnomalyDetector:
    """Fiyat/hacim şoku ve yüksek etkili haber şokunu birlikte değerlendiren, durumsuz (stateless) dedektör."""

    def __init__(
        self,
        volume_ratio_threshold: float = 3.0,
        price_move_atr_multiple_threshold: float = 2.5,
    ) -> None:
        self.volume_ratio_threshold = volume_ratio_threshold
        self.price_move_atr_multiple_threshold = price_move_atr_multiple_threshold

    def detect(
        self,
        symbol: str,
        regime: MarketRegime,
        analysis: Dict[str, Any],
        news_sentiment: Optional[Dict[str, Any]],
    ) -> Optional[MarketAlert]:
        """Verilen analiz/haber verisinden bir MarketAlert üretir; şok yoksa None döner."""
        price_volume_triggered, price_direction, pv_details = self._check_price_volume(analysis)
        news_triggered, news_direction, news_details = self._check_news(news_sentiment)

        if not price_volume_triggered and not news_triggered:
            return None

        if price_volume_triggered and news_triggered:
            alert_type = "COMBINED"
            severity = "HIGH"
            direction = price_direction if price_direction == news_direction else "NEUTRAL"
        elif price_volume_triggered:
            alert_type = "PRICE_VOLUME_SHOCK"
            severity = "MEDIUM"
            direction = price_direction
        else:
            alert_type = "NEWS_SHOCK"
            severity = "MEDIUM"
            direction = news_direction

        details = {"market_regime": regime.value, **pv_details, **news_details}
        message = self._build_message(alert_type, direction, details)

        return MarketAlert(
            symbol=symbol,
            alert_type=alert_type,
            severity=severity,
            direction=direction,
            message=message,
            details=details,
        )

    def _check_price_volume(self, analysis: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        micro = analysis.get("micro", {}) or {}
        macro = analysis.get("macro", {}) or {}

        volume_ratio = float(micro.get("volume_ratio", 0.0))
        price_move_atr_multiple = float(macro.get("price_move_atr_multiple", 0.0))
        daily_return_pct = float(macro.get("daily_return_pct", 0.0))

        triggered = (
            volume_ratio >= self.volume_ratio_threshold
            or price_move_atr_multiple >= self.price_move_atr_multiple_threshold
        )
        direction = "BULLISH" if daily_return_pct > 0 else ("BEARISH" if daily_return_pct < 0 else "NEUTRAL")
        details = {
            "volume_ratio": volume_ratio,
            "price_move_atr_multiple": price_move_atr_multiple,
            "daily_return_pct": daily_return_pct,
        }
        return triggered, direction, details

    def _check_news(self, news_sentiment: Optional[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
        if not news_sentiment:
            return False, "NEUTRAL", {}

        impact_level = news_sentiment.get("impact_level")
        sentiment_score = float(news_sentiment.get("sentiment_score", 0.0))
        sentiment_label = news_sentiment.get("sentiment_label", "NEUTRAL")

        triggered = impact_level == "HIGH"
        direction = "BULLISH" if sentiment_score > 0 else ("BEARISH" if sentiment_score < 0 else "NEUTRAL")
        details = {
            "news_impact_level": impact_level,
            "news_sentiment_score": sentiment_score,
            "news_sentiment_label": sentiment_label,
        }
        return triggered, direction, details

    @staticmethod
    def _build_message(alert_type: str, direction: str, details: Dict[str, Any]) -> str:
        if alert_type == "COMBINED" and direction == "NEUTRAL":
            return "Fiyat/hacim hareketi ile haber duygusu birbiriyle çelişiyor — yön belirsiz, dikkatli izleyin."

        direction_tr = {"BULLISH": "yükseliş yönlü", "BEARISH": "düşüş yönlü", "NEUTRAL": "yönü belirsiz"}[direction]

        if alert_type == "COMBINED":
            return (
                f"Hem fiyat/hacim hem de haber kaynaklı ani hareket tespit edildi — {direction_tr} bir gelişme. "
                "Pozisyonunuzu yeniden değerlendirin."
            )
        if alert_type == "PRICE_VOLUME_SHOCK":
            return (
                f"Anormal fiyat/hacim hareketi tespit edildi (hacim oranı: {details.get('volume_ratio')}x, "
                f"ATR katı: {details.get('price_move_atr_multiple')}) — {direction_tr} bir gelişme."
            )
        return (
            f"Yüksek etkili haber akışı tespit edildi — {direction_tr} bir gelişme. "
            "Fiyat henüz tepki vermemiş olabilir."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && /Users/hasantekbas/miniconda3/bin/python -m pytest tests/unit/test_market_anomaly_detector.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/market_anomaly_detector.py backend/tests/unit/test_market_anomaly_detector.py
git commit -m "feat: add MarketAnomalyDetector for sudden price/volume/news shock detection"
```

---

### Task 3: `InvestorPersona` — long-horizon LLM recommendation layer

**Files:**
- Create: `backend/core/investor_persona.py`
- Test: `backend/tests/unit/test_investor_persona.py`

**Interfaces:**
- Consumes: `MarketRegime` from `core/regime_scanner.py`, `TradeSignal` from `core/ai_trader_persona.py` (reused, not duplicated).
- Produces: `HorizonView` (pydantic: `signal: TradeSignal`, `confidence_score: int` 0-100, `rationale: str`), `InvestorRecommendation` (pydantic: `symbol: str`, `market_regime: str`, `horizon_1_week: HorizonView`, `horizon_1_month: HorizonView`, `horizon_1_year: HorizonView`, `investor_commentary: str`), and `InvestorPersona.generate_recommendation(symbol: str, market_regime: MarketRegime, analysis: Dict[str, Any], news_sentiment: Optional[Dict[str, Any]] = None) -> InvestorRecommendation` — consumed by `HybridTradingEngine` in Task 4.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_investor_persona.py`:

```python
"""
Unit tests for core/investor_persona.py. The Groq client is fully mocked —
no network calls, no real LLM calls.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.ai_trader_persona import TradeSignal
from core.investor_persona import HorizonView, InvestorPersona, InvestorRecommendation
from core.regime_scanner import MarketRegime


def _mock_groq_response(payload: dict):
    tool_call = SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(payload)))
    message = SimpleNamespace(tool_calls=[tool_call])
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _valid_payload(**overrides):
    payload = {
        "symbol": "AAPL",
        "market_regime": "TRENDING_BULL",
        "horizon_1_week": {"signal": "BUY", "confidence_score": 60, "rationale": "Kısa vadeli momentum olumlu."},
        "horizon_1_month": {"signal": "BUY", "confidence_score": 65, "rationale": "Haftalık trend yukarı yönlü."},
        "horizon_1_year": {"signal": "STRONG_BUY", "confidence_score": 70, "rationale": "Rejim güçlü ve kalıcı görünüyor."},
        "investor_commentary": "Genel görünüm olumlu.",
    }
    payload.update(overrides)
    return payload


def _make_persona() -> InvestorPersona:
    persona = InvestorPersona(api_key="test-key")
    persona._client = MagicMock()
    return persona


class TestInvestorPersonaGenerateRecommendation:
    def test_returns_investor_recommendation(self):
        persona = _make_persona()
        persona._client.chat.completions.create.return_value = _mock_groq_response(_valid_payload())

        result = persona.generate_recommendation(
            symbol="AAPL",
            market_regime=MarketRegime.TRENDING_BULL,
            analysis={"current_price": 180.0, "macro": {}, "micro": {}},
        )

        assert isinstance(result, InvestorRecommendation)
        assert result.symbol == "AAPL"

    def test_all_three_horizons_present(self):
        persona = _make_persona()
        persona._client.chat.completions.create.return_value = _mock_groq_response(_valid_payload())

        result = persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})

        assert isinstance(result.horizon_1_week, HorizonView)
        assert isinstance(result.horizon_1_month, HorizonView)
        assert isinstance(result.horizon_1_year, HorizonView)

    def test_horizons_can_have_different_signals(self):
        persona = _make_persona()
        payload = _valid_payload(
            horizon_1_week={"signal": "SELL", "confidence_score": 55, "rationale": "Kısa vadede aşırı alım."},
            horizon_1_year={"signal": "STRONG_BUY", "confidence_score": 80, "rationale": "Uzun vadeli rejim güçlü."},
        )
        persona._client.chat.completions.create.return_value = _mock_groq_response(payload)

        result = persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})

        assert result.horizon_1_week.signal == TradeSignal.SELL
        assert result.horizon_1_year.signal == TradeSignal.STRONG_BUY

    def test_disclaimer_always_appended(self):
        persona = _make_persona()
        persona._client.chat.completions.create.return_value = _mock_groq_response(_valid_payload())

        result = persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})

        assert "temel analiz" in result.investor_commentary.lower()

    def test_disclaimer_appended_after_custom_commentary(self):
        persona = _make_persona()
        payload = _valid_payload(investor_commentary="Özel bir yorum.")
        persona._client.chat.completions.create.return_value = _mock_groq_response(payload)

        result = persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})

        assert result.investor_commentary.startswith("Özel bir yorum.")
        assert "temel analiz" in result.investor_commentary.lower()

    def test_raises_on_empty_tool_calls(self):
        persona = _make_persona()
        message = SimpleNamespace(tool_calls=[])
        persona._client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=message)]
        )

        with pytest.raises(RuntimeError, match="tool_calls boş"):
            persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})

    def test_raises_on_invalid_schema(self):
        persona = _make_persona()
        bad_payload = _valid_payload()
        del bad_payload["horizon_1_year"]
        persona._client.chat.completions.create.return_value = _mock_groq_response(bad_payload)

        with pytest.raises(RuntimeError, match="beklenen şemaya uymuyor"):
            persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})

    def test_confidence_score_out_of_range_rejected(self):
        persona = _make_persona()
        payload = _valid_payload(
            horizon_1_week={"signal": "BUY", "confidence_score": 150, "rationale": "geçersiz"}
        )
        persona._client.chat.completions.create.return_value = _mock_groq_response(payload)

        with pytest.raises(RuntimeError, match="beklenen şemaya uymuyor"):
            persona.generate_recommendation("AAPL", MarketRegime.TRENDING_BULL, {})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /Users/hasantekbas/miniconda3/bin/python -m pytest tests/unit/test_investor_persona.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.investor_persona'`

- [ ] **Step 3: Implement `InvestorPersona`**

Create `backend/core/investor_persona.py`:

```python
"""
OptiTrade — Investor Persona (Uzun Vadeli Yatırımcı Öneri Katmanı)
======================================================================
AITraderPersona'nın kısa vadeli ticaret odaklı yaklaşımından farklı olarak,
aynı teknik analiz + piyasa rejimi + haber duygusu verisini 1 hafta / 1 ay /
1 yıl ufuklarında ayrı ayrı AL/SAT/TUT yönü ve güven skoruna dönüştürür.
Giriş/Stop-Loss/Take-Profit üretmez — yatırım bir "trade" değildir.

Bu motorda temel analiz (bilanço, büyüme oranları vb.) veri kaynağı yoktur
(core/analyzer.py'daki ayrı FundamentalSignalEngine bu motora bağlanmamıştır)
— bu nedenle 1 yıllık görüş yalnızca piyasa rejimi sürekliliği ve makro haber
bağlamına dayanır. Bu sınırlılık, investor_commentary'ye LLM çıktısından
BAĞIMSIZ, kod tarafından eklenen sabit bir uyarı cümlesiyle her zaman
belirtilir.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from groq import Groq
from pydantic import BaseModel, Field, ValidationError

from core.ai_trader_persona import TradeSignal
from core.regime_scanner import MarketRegime

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_FUNDAMENTAL_DATA_DISCLAIMER = (
    " (Not: Bu görüş temel analiz -bilanço, büyüme oranları- verisi içermez; "
    "yalnızca piyasa rejimi ve haber bağlamına dayanır.)"
)

_SYSTEM_PROMPT = (
    "Sen deneyimli, uzun vadeli bir Value Investor / Portföy Yöneticisisin. "
    "Karar vermeden önce üç farklı ufuktan SIRAYLA düşün, sonra sentezle:\n\n"
    "1. ÖNCE 1 HAFTALIK ufku değerlendir: kısa vadeli teknik momentum "
    "(RSI, MACD histogramı, hacim) ve piyasa rejiminin (market_regime) bu "
    "hafta için ima ettiği yönü yorumla. horizon_1_week alanına yaz.\n\n"
    "2. SONRA 1 AYLIK ufku değerlendir: haftalık trend yönü (weekly_trend_up), "
    "EMA50/EMA200 kesişimi ve piyasa rejiminin kalıcılığını yorumla. "
    "horizon_1_month alanına yaz.\n\n"
    "3. EN SON 1 YILLIK ufku değerlendir: piyasa rejiminin sürekliliğini ve "
    "haber duygusunun (varsa news_sentiment) makro kategorisini "
    "(news_sentiment.news_category, özellikle MACRO/REGULATORY) yorumla. "
    "Temel analiz (bilanço/büyüme) verisi SANA SAĞLANMADI — bunu tahmin etme, "
    "yalnızca elindeki rejim ve haber verisine dayan. horizon_1_year alanına "
    "yaz.\n\n"
    "Her ufuk için ayrı bir signal (STRONG_BUY/BUY/NEUTRAL/SELL/STRONG_SELL) "
    "ve confidence_score (0-100) belirle — ufuklar birbirinden FARKLI "
    "yönlerde olabilir (ör. 1 hafta SAT, 1 yıl AL), bu çelişki değil, "
    "gerçekçi bir durumdur; asla ufukları yapay olarak birbirine benzetme.\n\n"
    "investor_commentary alanına, üç ufku birlikte değerlendiren, deneyimli "
    "bir portföy yöneticisi üslubuyla 3-4 cümlelik bir sentez yaz.\n\n"
    "Cevabını MUTLAKA submit_investor_recommendation aracını çağırarak ver.\n\n"
    "Tüm metin alanları (rationale'lar ve investor_commentary) BAŞTAN SONA "
    "SADECE Türkçe olmalı — İngilizce teknik etiketleri (ör. BULLISH, MIXED) "
    "olduğu gibi ALINTILAMA, anlamını Türkçeye çevirerek yaz."
)


class HorizonView(BaseModel):
    """Belirli bir zaman ufku için AL/SAT/TUT yönü, güven skoru ve gerekçe."""

    signal: TradeSignal
    confidence_score: int = Field(..., ge=0, le=100)
    rationale: str = Field(..., description="1-2 cümlelik Türkçe gerekçe")


class InvestorRecommendation(BaseModel):
    """InvestorPersona'nın ürettiği ufuk-bazlı yapılandırılmış yatırım önerisi."""

    symbol: str
    market_regime: str
    horizon_1_week: HorizonView
    horizon_1_month: HorizonView
    horizon_1_year: HorizonView
    investor_commentary: str = Field(
        ...,
        description="Üç ufku birlikte değerlendiren 3-4 cümlelik Türkçe sentez.",
    )


_TOOL_NAME = "submit_investor_recommendation"
_HORIZON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "signal": {"type": "string", "enum": [s.value for s in TradeSignal]},
        "confidence_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "rationale": {"type": "string"},
    },
    "required": ["signal", "confidence_score", "rationale"],
}
_RECOMMENDATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "market_regime": {"type": "string"},
        "horizon_1_week": _HORIZON_SCHEMA,
        "horizon_1_month": _HORIZON_SCHEMA,
        "horizon_1_year": _HORIZON_SCHEMA,
        "investor_commentary": {"type": "string"},
    },
    "required": [
        "symbol", "market_regime",
        "horizon_1_week", "horizon_1_month", "horizon_1_year",
        "investor_commentary",
    ],
    "additionalProperties": False,
}


class InvestorPersona:
    """Teknik + rejim + (opsiyonel) haber verisini LLM'e sunup ufuk-bazlı yatırım önerisi üreten katman."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL) -> None:
        self._client = Groq(api_key=api_key) if api_key else Groq()
        self._model = model

    def generate_recommendation(
        self,
        symbol: str,
        market_regime: MarketRegime,
        analysis: Dict[str, Any],
        news_sentiment: Optional[Dict[str, Any]] = None,
    ) -> InvestorRecommendation:
        """Verilen tüm sinyalleri LLM'e sunup yapılandırılmış bir InvestorRecommendation döner."""
        prompt = self._build_prompt(symbol, market_regime, analysis, news_sentiment)

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=1536,
            temperature=0.3,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": _TOOL_NAME,
                        "description": "Yapılandırılmış yatırım önerisini gönderir.",
                        "parameters": _RECOMMENDATION_SCHEMA,
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": _TOOL_NAME}},
        )

        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            raise RuntimeError(f"{symbol}: Groq yapılandırılmış çıktı üretemedi (tool_calls boş)")

        try:
            arguments = json.loads(tool_calls[0].function.arguments)
            recommendation = InvestorRecommendation.model_validate(arguments)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(f"{symbol}: Groq çıktısı beklenen şemaya uymuyor: {exc}") from exc

        recommendation.investor_commentary += _FUNDAMENTAL_DATA_DISCLAIMER
        return recommendation

    @staticmethod
    def _build_prompt(
        symbol: str,
        market_regime: MarketRegime,
        analysis: Dict[str, Any],
        news_sentiment: Optional[Dict[str, Any]],
    ) -> str:
        payload = {
            "symbol": symbol,
            "market_regime": market_regime.value,
            "technical_analysis": analysis,
            "news_sentiment": news_sentiment or "Veri sağlanmadı",
        }
        return (
            "Aşağıdaki verilere dayanarak bu sembol için 1 hafta / 1 ay / 1 yıl "
            "ufuklarında ayrı yatırım önerileri üret:\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n\n"
            "Her ufkun signal ve confidence_score'unu, o ufka uygun veriye "
            "(kısa vade için mikro sinyaller, uzun vade için rejim/haber) "
            "dayandır — ufuklar arasında yapay bir tutarlılık zorlaması yapma."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && /Users/hasantekbas/miniconda3/bin/python -m pytest tests/unit/test_investor_persona.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/investor_persona.py backend/tests/unit/test_investor_persona.py
git commit -m "feat: add InvestorPersona for 1-week/1-month/1-year horizon recommendations"
```

---

### Task 4: Wire `profile` and `check_alerts` into `HybridTradingEngine`

**Files:**
- Modify: `backend/core/hybrid_engine.py` (full replacement — see below)
- Test: `backend/tests/unit/test_hybrid_engine.py` (new)

**Interfaces:**
- Consumes: `InvestorPersona`/`InvestorRecommendation` (Task 3), `MarketAnomalyDetector`/`MarketAlert` (Task 2).
- Produces: `HybridTradingEngine.run(symbols: List[str], profile: str = "trader") -> List[TradeRecommendation] | List[InvestorRecommendation]` (the `profile` param is new; the trader path — `profile="trader"`, the default — must behave identically to before this task) and `HybridTradingEngine.check_alerts(symbols: List[str]) -> List[MarketAlert]` (new method) — both consumed by `api/v1/endpoints/signals.py` in Task 5.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_hybrid_engine.py`:

```python
"""
Unit tests for core/hybrid_engine.py orchestration logic. All layers
(scanner, analyzer, risk_manager, ai_persona, investor_persona,
news_adapter, anomaly_detector) are injected as mocks — no network calls,
no LLM calls. Verifies profile branching, cache behavior (both the
recommendation caches and the alert cache), and error handling.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from unittest.mock import MagicMock

import pytest

from core.ai_trader_persona import TradeRecommendation, TradeSignal
from core.hybrid_engine import HybridTradingEngine
from core.investor_persona import HorizonView, InvestorRecommendation
from core.market_anomaly_detector import MarketAlert
from core.regime_scanner import MarketRegime, ScannedSymbol
from core.risk_manager import RiskLevels


def _scanned(symbol="AAPL", regime=MarketRegime.TRENDING_BULL):
    return ScannedSymbol(
        symbol=symbol, regime=regime, cumulative_return_pct=10.0,
        annualized_volatility_pct=20.0, trend_strength_r2=0.8, last_close=180.0,
    )


def _analysis():
    return {
        "symbol": "AAPL", "current_price": 180.0, "atr_daily": 2.5,
        "macro": {"trend_direction": "BULLISH", "daily_return_pct": 1.0, "price_move_atr_multiple": 0.4},
        "micro": {"volume_ratio": 1.2, "rsi_14": 55.0},
        "patterns": {},
    }


def _trade_rec(symbol="AAPL"):
    return TradeRecommendation(
        symbol=symbol, market_regime="TRENDING_BULL",
        trader_analysis="a", investor_analysis="b",
        signal=TradeSignal.BUY, confidence_score=70,
        entry_price=180.0, stop_loss=175.0, take_profit_1=185.0, take_profit_2=190.0,
        trader_commentary="c",
    )


def _investor_rec(symbol="AAPL"):
    horizon = HorizonView(signal=TradeSignal.BUY, confidence_score=60, rationale="r")
    return InvestorRecommendation(
        symbol=symbol, market_regime="TRENDING_BULL",
        horizon_1_week=horizon, horizon_1_month=horizon, horizon_1_year=horizon,
        investor_commentary="genel",
    )


def _risk():
    return RiskLevels(
        entry_price=180.0, atr=2.5, stop_loss=176.25, take_profit_1=185.0,
        take_profit_2=187.5, risk_per_unit=3.75, reward_per_unit_tp1=5.0,
        risk_reward_ratio=1.33, is_valid=False,
    )


def _make_engine(**overrides) -> HybridTradingEngine:
    defaults = dict(
        scanner=MagicMock(),
        analyzer=MagicMock(),
        risk_manager=MagicMock(),
        ai_persona=MagicMock(),
        investor_persona=MagicMock(),
        news_adapter=MagicMock(),
        anomaly_detector=MagicMock(),
    )
    defaults.update(overrides)
    return HybridTradingEngine(**defaults)


class TestRunTraderProfile:
    def test_default_profile_is_trader(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"])

        assert result == [_trade_rec()]
        engine.ai_persona.generate_recommendation.assert_called_once()
        engine.investor_persona.generate_recommendation.assert_not_called()

    def test_trader_profile_calls_risk_manager(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = None

        engine.run(["AAPL"], profile="trader")

        engine.risk_manager.calculate.assert_called_once_with(entry_price=180.0, atr=2.5)


class TestRunInvestorProfile:
    def test_investor_profile_uses_investor_persona_and_skips_risk_manager(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.investor_persona.generate_recommendation.return_value = _investor_rec()
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"], profile="investor")

        assert result == [_investor_rec()]
        engine.investor_persona.generate_recommendation.assert_called_once()
        engine.ai_persona.generate_recommendation.assert_not_called()
        engine.risk_manager.calculate.assert_not_called()

    def test_investor_cache_independent_from_trader_cache(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.investor_persona.generate_recommendation.return_value = _investor_rec()
        engine.anomaly_detector.detect.return_value = None

        trader_result = engine.run(["AAPL"], profile="trader")
        investor_result = engine.run(["AAPL"], profile="investor")

        assert isinstance(trader_result[0], TradeRecommendation)
        assert isinstance(investor_result[0], InvestorRecommendation)
        assert engine.analyzer.analyze.call_count == 2  # her profil kendi cache'inde miss oldu


class TestProcessSymbolErrorHandling:
    def test_returns_empty_list_when_analysis_is_none(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = None

        result = engine.run(["AAPL"])

        assert result == []

    def test_exception_in_persona_does_not_crash_run(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.side_effect = RuntimeError("boom")
        engine.anomaly_detector.detect.return_value = None

        result = engine.run(["AAPL"])

        assert result == []


class TestRecommendationCache:
    def test_cache_hit_skips_analyzer(self):
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = None

        engine.run(["AAPL"])
        engine.run(["AAPL"])

        assert engine.analyzer.analyze.call_count == 1


class TestCheckAlerts:
    def test_uses_unfiltered_scan(self):
        engine = _make_engine()
        engine.scanner.scan.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.anomaly_detector.detect.return_value = None

        engine.check_alerts(["AAPL"])

        engine.scanner.scan.assert_called_once_with(["AAPL"])
        engine.scanner.scan_and_filter.assert_not_called()

    def test_returns_alert_when_detector_triggers(self):
        alert = MarketAlert(
            symbol="AAPL", alert_type="PRICE_VOLUME_SHOCK", severity="MEDIUM",
            direction="BULLISH", message="test",
        )
        engine = _make_engine()
        engine.scanner.scan.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.anomaly_detector.detect.return_value = alert

        result = engine.check_alerts(["AAPL"])

        assert result == [alert]

    def test_no_alert_is_cached_and_not_rechecked(self):
        engine = _make_engine()
        engine.scanner.scan.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.anomaly_detector.detect.return_value = None

        engine.check_alerts(["AAPL"])
        engine.check_alerts(["AAPL"])

        assert engine.analyzer.analyze.call_count == 1

    def test_alert_cache_populated_as_side_effect_of_run(self):
        alert = MarketAlert(
            symbol="AAPL", alert_type="NEWS_SHOCK", severity="MEDIUM",
            direction="BEARISH", message="test",
        )
        engine = _make_engine()
        engine.scanner.scan_and_filter.return_value = [_scanned()]
        engine.scanner.scan.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = _analysis()
        engine.news_adapter.get_sentiment.return_value = None
        engine.risk_manager.calculate.return_value = _risk()
        engine.ai_persona.generate_recommendation.return_value = _trade_rec()
        engine.anomaly_detector.detect.return_value = alert

        engine.run(["AAPL"])
        result = engine.check_alerts(["AAPL"])

        assert result == [alert]
        assert engine.analyzer.analyze.call_count == 1  # run() sırasında çekilen veri yeniden kullanıldı

    def test_check_alerts_handles_missing_analysis(self):
        engine = _make_engine()
        engine.scanner.scan.return_value = [_scanned()]
        engine.analyzer.analyze.return_value = None

        result = engine.check_alerts(["AAPL"])

        assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /Users/hasantekbas/miniconda3/bin/python -m pytest tests/unit/test_hybrid_engine.py -v`
Expected: FAIL — `TypeError: HybridTradingEngine.__init__() got an unexpected keyword argument 'investor_persona'` (and `check_alerts` not existing)

- [ ] **Step 3: Implement the changes**

Replace the entire contents of `backend/core/hybrid_engine.py`:

```python
"""
OptiTrade — Hybrid Trading Engine (Orkestratör)
==================================================
Tarama (MarketRegimeScanner), Analiz (MultiTimeframeAnalyzer), Risk
(DynamicRiskManager) ve Öneri (AITraderPersona / InvestorPersona) katmanlarını
uçtan uca bağlayan ana motor. Ayrıca:

- Sembol başına üretilen öneriyi (TradeRecommendation veya
  InvestorRecommendation, ``profile``'a göre) belirli bir süre (varsayılan
  15 dakika) bellek-içi cache'te tutar; geçerli bir cache girdisi varsa
  LLM'e (Groq) tekrar istek atılmaz. Trader ve investor profilleri AYRI
  cache'lerde tutulur, aynı sembol için profil değişimi diğer profilin
  cache'ini bozmaz.
- Piyasa rejimi filtresini geçen semboller için opsiyonel olarak haber
  duygusu (``NewsSentimentAdapter``) çeker ve AI'ya sunar.
- ``check_alerts()``: verilen sembolleri (rejim filtresi UYGULANMADAN) ani
  fiyat/hacim/haber şoku için kontrol eder. Bir öneri isteği (``run()``)
  zaten bir sembol için analiz+haber verisi çekmişse, ``check_alerts()``
  bu veriyi tekrar çekmeden yeniden kullanır (kendi 2 dakikalık cache'i
  üzerinden) — ek yfinance/haber isteği yapmaz.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from core.ai_trader_persona import AITraderPersona, TradeRecommendation
from core.cache_manager import TTLCache
from core.investor_persona import InvestorPersona, InvestorRecommendation
from core.market_anomaly_detector import MarketAlert, MarketAnomalyDetector
from core.mtf_analyzer import MultiTimeframeAnalyzer
from core.news_adapter import NewsSentimentAdapter
from core.regime_scanner import MarketRegimeScanner, ScannedSymbol
from core.risk_manager import DynamicRiskManager

logger = logging.getLogger(__name__)

DEFAULT_RECOMMENDATION_CACHE_TTL_SECONDS = 15 * 60  # 15 dakika
DEFAULT_ALERT_CACHE_TTL_SECONDS = 2 * 60  # 2 dakika

# TTLCache.get() süresi dolmuş/hiç yazılmamış bir anahtar için de None döner;
# "kontrol edildi, uyarı yok" durumunu bundan ayırt etmek için sentinel.
_NO_ALERT = object()


class HybridTradingEngine:
    """Dört katmanı (Tarama → Analiz → Risk → Öneri) sırayla çalıştıran orkestratör.

    Her katman bağımsız olarak enjekte edilebilir (test/mock için); verilmezse
    varsayılan parametrelerle örneklenir.
    """

    def __init__(
        self,
        scanner: Optional[MarketRegimeScanner] = None,
        analyzer: Optional[MultiTimeframeAnalyzer] = None,
        risk_manager: Optional[DynamicRiskManager] = None,
        ai_persona: Optional[AITraderPersona] = None,
        investor_persona: Optional[InvestorPersona] = None,
        news_adapter: Optional[NewsSentimentAdapter] = None,
        anomaly_detector: Optional[MarketAnomalyDetector] = None,
        recommendation_cache_ttl_seconds: float = DEFAULT_RECOMMENDATION_CACHE_TTL_SECONDS,
        alert_cache_ttl_seconds: float = DEFAULT_ALERT_CACHE_TTL_SECONDS,
    ) -> None:
        self.scanner = scanner or MarketRegimeScanner()
        self.analyzer = analyzer or MultiTimeframeAnalyzer()
        self.risk_manager = risk_manager or DynamicRiskManager()
        self.ai_persona = ai_persona or AITraderPersona()
        self.investor_persona = investor_persona or InvestorPersona()
        self.news_adapter = news_adapter or NewsSentimentAdapter()
        self.anomaly_detector = anomaly_detector or MarketAnomalyDetector()
        self._recommendation_cache: TTLCache[TradeRecommendation] = TTLCache(
            ttl_seconds=recommendation_cache_ttl_seconds
        )
        self._investor_cache: TTLCache[InvestorRecommendation] = TTLCache(
            ttl_seconds=recommendation_cache_ttl_seconds
        )
        self._alert_cache: TTLCache = TTLCache(ttl_seconds=alert_cache_ttl_seconds)

    def run(
        self, symbols: List[str], profile: str = "trader"
    ) -> Union[List[TradeRecommendation], List[InvestorRecommendation]]:
        """Sembol listesini uçtan uca işleyip AI tarafından üretilmiş önerileri döner.

        ``profile="trader"`` (varsayılan) kısa vadeli ``TradeRecommendation``
        üretir (mevcut davranış, değişmedi). ``profile="investor"`` giriş/SL/TP
        içermeyen, 1 hafta/1 ay/1 yıl ufuklu ``InvestorRecommendation`` üretir.

        Piyasa rejimine göre fırsatsız (CHOPPY) sembolleri eler; kalanlar için
        (cache'te geçerli bir öneri yoksa) analiz + haber duygusu hesaplanır
        ve seçilen profile göre uygun persona'ya sunularak nihai öneri üretilir.
        Herhangi bir sembolde hata oluşursa o sembol atlanır, akış durmaz.
        """
        recommendations: List[Union[TradeRecommendation, InvestorRecommendation]] = []

        scanned_symbols = self.scanner.scan_and_filter(symbols)
        logger.info(f"{len(scanned_symbols)}/{len(symbols)} sembol piyasa rejimi filtresini geçti")

        for scanned in scanned_symbols:
            recommendation = self._process_symbol(scanned, profile)
            if recommendation is not None:
                recommendations.append(recommendation)

        return recommendations

    def check_alerts(self, symbols: List[str]) -> List[MarketAlert]:
        """Verilen tüm sembolleri (piyasa rejimi filtresi UYGULANMADAN) ani değişiklik için kontrol eder.

        Rejim filtresi bilerek atlanır: CHOPPY bir sembolün ani hacim/fiyat
        şoku göstermesi, tam olarak rejim değişikliğinin habercisi olabilir.
        """
        alerts: List[MarketAlert] = []
        for scanned in self.scanner.scan(symbols):
            alert = self._get_or_check_alert(scanned)
            if alert is not None:
                alerts.append(alert)
        return alerts

    def _process_symbol(
        self, scanned: ScannedSymbol, profile: str
    ) -> Optional[Union[TradeRecommendation, InvestorRecommendation]]:
        symbol = scanned.symbol
        cache = self._recommendation_cache if profile == "trader" else self._investor_cache

        cached = cache.get(symbol)
        if cached is not None:
            logger.info(f"{symbol}: geçerli cache bulundu ({profile}), LLM çağrısı atlanıyor")
            return cached

        try:
            analysis = self.analyzer.analyze(symbol)
            if analysis is None:
                logger.warning(f"{symbol}: analiz verisi yetersiz, atlanıyor")
                return None

            news_sentiment = self.news_adapter.get_sentiment(symbol)

            # Zaten çekilmiş analiz+haber verisini alert kontrolü için de kullan (ek istek yok).
            self._update_alert_cache(scanned, analysis, news_sentiment)

            if profile == "trader":
                risk = self.risk_manager.calculate(
                    entry_price=analysis["current_price"],
                    atr=analysis["atr_daily"],
                )
                recommendation: Union[TradeRecommendation, InvestorRecommendation] = (
                    self.ai_persona.generate_recommendation(
                        symbol=symbol,
                        market_regime=scanned.regime,
                        analysis=analysis,
                        risk=risk,
                        news_sentiment=news_sentiment,
                    )
                )
            else:
                recommendation = self.investor_persona.generate_recommendation(
                    symbol=symbol,
                    market_regime=scanned.regime,
                    analysis=analysis,
                    news_sentiment=news_sentiment,
                )

            cache.set(symbol, recommendation)
            return recommendation
        except Exception as exc:
            logger.error(f"{symbol}: hibrit motor hatası ({profile}): {exc}")
            return None

    def _get_or_check_alert(self, scanned: ScannedSymbol) -> Optional[MarketAlert]:
        symbol = scanned.symbol
        cached = self._alert_cache.get(symbol)
        if cached is not None:
            return None if cached is _NO_ALERT else cached

        try:
            analysis = self.analyzer.analyze(symbol)
            if analysis is None:
                return None
            news_sentiment = self.news_adapter.get_sentiment(symbol)
            return self._update_alert_cache(scanned, analysis, news_sentiment)
        except Exception as exc:
            logger.error(f"{symbol}: alert kontrolü hatası: {exc}")
            return None

    def _update_alert_cache(
        self, scanned: ScannedSymbol, analysis: Dict[str, Any], news_sentiment: Optional[Dict[str, Any]]
    ) -> Optional[MarketAlert]:
        alert = self.anomaly_detector.detect(
            symbol=scanned.symbol,
            regime=scanned.regime,
            analysis=analysis,
            news_sentiment=news_sentiment,
        )
        self._alert_cache.set(scanned.symbol, alert if alert is not None else _NO_ALERT)
        return alert
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && /Users/hasantekbas/miniconda3/bin/python -m pytest tests/unit/test_hybrid_engine.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Run the full unit test suite to confirm no regressions**

Run: `cd backend && /Users/hasantekbas/miniconda3/bin/python -m pytest tests/unit -q`
Expected: all tests PASS (existing suite + the new tests from Tasks 1-4)

- [ ] **Step 6: Commit**

```bash
git add backend/core/hybrid_engine.py backend/tests/unit/test_hybrid_engine.py
git commit -m "feat: add investor profile and check_alerts to HybridTradingEngine"
```

---

### Task 5: API — `profile` field on `/analyze` and new `POST /signals/alerts`

**Files:**
- Modify: `backend/api/v1/endpoints/signals.py` (full replacement — see below)
- Test: `backend/tests/unit/test_signals_endpoint.py` (new)

**Interfaces:**
- Consumes: `HybridTradingEngine.run(symbols, profile)` and `HybridTradingEngine.check_alerts(symbols)` (Task 4), `InvestorRecommendation` (Task 3), `MarketAlert` (Task 2).
- Produces: `POST /signals/analyze` accepts `{"symbols": [...], "profile": "trader"|"investor"}` (profile optional, defaults to `"trader"`) and returns `List[Union[TradeRecommendation, InvestorRecommendation]]`. `POST /signals/alerts` accepts the same request body shape and returns `List[MarketAlert]` (200 with `[]` when nothing triggers — not a 404).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_signals_endpoint.py`:

```python
"""
Unit tests for api/v1/endpoints/signals.py. HybridTradingEngine is replaced
via FastAPI dependency override with a MagicMock — no network calls, no
LLM calls. The shared slowapi rate limiter is reset before/after each test
to avoid cross-test bleed (it's process-global state).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.v1.endpoints import signals
from core.ai_trader_persona import TradeRecommendation, TradeSignal
from core.investor_persona import HorizonView, InvestorRecommendation
from core.market_anomaly_detector import MarketAlert
from core.rate_limiter import limiter


def _trade_rec():
    return TradeRecommendation(
        symbol="AAPL", market_regime="TRENDING_BULL",
        trader_analysis="a", investor_analysis="b",
        signal=TradeSignal.BUY, confidence_score=70,
        entry_price=180.0, stop_loss=175.0, take_profit_1=185.0, take_profit_2=190.0,
        trader_commentary="c",
    )


def _investor_rec():
    horizon = HorizonView(signal=TradeSignal.BUY, confidence_score=60, rationale="r")
    return InvestorRecommendation(
        symbol="AAPL", market_regime="TRENDING_BULL",
        horizon_1_week=horizon, horizon_1_month=horizon, horizon_1_year=horizon,
        investor_commentary="genel",
    )


@pytest.fixture
def client():
    limiter.reset()
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(signals.router)

    mock_engine = MagicMock()
    app.dependency_overrides[signals.get_engine] = lambda: mock_engine

    with TestClient(app) as test_client:
        test_client.mock_engine = mock_engine
        yield test_client

    app.dependency_overrides.clear()
    limiter.reset()


class TestAnalyzeEndpoint:
    def test_default_profile_is_trader(self, client):
        client.mock_engine.run.return_value = [_trade_rec()]

        response = client.post("/signals/analyze", json={"symbols": ["AAPL"]})

        assert response.status_code == 200
        client.mock_engine.run.assert_called_once_with(["AAPL"], profile="trader")

    def test_investor_profile_passed_through(self, client):
        client.mock_engine.run.return_value = [_investor_rec()]

        response = client.post("/signals/analyze", json={"symbols": ["AAPL"], "profile": "investor"})

        assert response.status_code == 200
        client.mock_engine.run.assert_called_once_with(["AAPL"], profile="investor")
        body = response.json()[0]
        assert "horizon_1_week" in body

    def test_trader_response_shape_preserved(self, client):
        client.mock_engine.run.return_value = [_trade_rec()]

        response = client.post("/signals/analyze", json={"symbols": ["AAPL"]})

        body = response.json()[0]
        assert body["entry_price"] == 180.0
        assert "horizon_1_week" not in body

    def test_invalid_profile_rejected(self, client):
        response = client.post("/signals/analyze", json={"symbols": ["AAPL"], "profile": "bogus"})
        assert response.status_code == 422

    def test_empty_result_returns_404(self, client):
        client.mock_engine.run.return_value = []
        response = client.post("/signals/analyze", json={"symbols": ["AAPL"]})
        assert response.status_code == 404


class TestAlertsEndpoint:
    def test_empty_alerts_returns_200(self, client):
        client.mock_engine.check_alerts.return_value = []

        response = client.post("/signals/alerts", json={"symbols": ["AAPL"]})

        assert response.status_code == 200
        assert response.json() == []

    def test_alerts_returned(self, client):
        alert = MarketAlert(
            symbol="AAPL", alert_type="PRICE_VOLUME_SHOCK", severity="MEDIUM",
            direction="BULLISH", message="test",
        )
        client.mock_engine.check_alerts.return_value = [alert]

        response = client.post("/signals/alerts", json={"symbols": ["AAPL"]})

        assert response.status_code == 200
        assert response.json()[0]["symbol"] == "AAPL"

    def test_symbols_passed_through(self, client):
        client.mock_engine.check_alerts.return_value = []

        client.post("/signals/alerts", json={"symbols": ["AAPL", "BTC-USD"]})

        client.mock_engine.check_alerts.assert_called_once_with(["AAPL", "BTC-USD"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /Users/hasantekbas/miniconda3/bin/python -m pytest tests/unit/test_signals_endpoint.py -v`
Expected: FAIL — `AttributeError` or 422/500 errors, since `profile` isn't accepted yet and `/signals/alerts` doesn't exist (404 on that route).

- [ ] **Step 3: Implement the endpoint changes**

Replace the entire contents of `backend/api/v1/endpoints/signals.py`:

```python
"""
OptiTrade — Trading Signals API Endpoint'leri
================================================
Mobil uygulamanın (Flutter/React Native) ``HybridTradingEngine`` çıktısını
tükettiği REST katmanı.

NOT: Bu dosyada bilerek ``from __future__ import annotations`` KULLANILMIYOR.
slowapi'nin ``@limiter.limit()`` dekoratörü fonksiyonu sardığında, sarmalanan
fonksiyonun ``__globals__``'ı slowapi'nin kendi modülüne işaret ediyor;
ertelenmiş (string) tip anotasyonları açıksa FastAPI/Pydantic bu isimleri
(ör. ``SignalsAnalyzeRequest``) o namespace'te bulamayıp
``PydanticUndefinedAnnotation`` hatası veriyor. Anotasyonlar burada eager
(anında) değerlendirildiği için bu sorun oluşmuyor.
"""
from functools import lru_cache
from typing import List, Literal, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from core.ai_trader_persona import TradeRecommendation
from core.hybrid_engine import HybridTradingEngine
from core.investor_persona import InvestorRecommendation
from core.market_anomaly_detector import MarketAlert
from core.rate_limiter import limiter

router = APIRouter(prefix="/signals", tags=["Trading Signals"])


class SignalsAnalyzeRequest(BaseModel):
    """``POST /analyze`` ve ``POST /alerts`` için ortak istek gövdesi."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"symbols": ["BTC-USD", "AAPL", "THYAO.IS"], "profile": "trader"}}
    )

    symbols: List[str] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Analiz edilecek sembol listesi (yfinance formatında, ör. BIST için '.IS' soneki).",
    )
    profile: Literal["trader", "investor"] = Field(
        default="trader",
        description=(
            "'trader': kısa vadeli AL/SAT önerisi (giriş/stop-loss/take-profit). "
            "'investor': 1 hafta / 1 ay / 1 yıl ufuklu, giriş/SL/TP içermeyen uzun "
            "vadeli görüş. Yalnızca /analyze tarafından kullanılır, /alerts bu alanı yok sayar."
        ),
    )


@lru_cache()
def get_engine() -> HybridTradingEngine:
    """Süreç genelinde tek bir ``HybridTradingEngine`` örneği (singleton).

    ``HybridTradingEngine`` kendi içinde sembol başına 15 dakikalık bir
    öneri cache'i (hem trader hem investor profili için ayrı ayrı) ve 2
    dakikalık bir alert cache'i tutar. Her istekte yeni bir örnek oluşturmak
    bu cache'leri sıfırlar ve asıl amaçlarını boşa çıkarır. ``lru_cache()``
    parametresiz çağrıldığından her seferinde aynı örneği döner — FastAPI'de
    tekil (singleton) bağımlılık için standart örüntü.
    """
    return HybridTradingEngine()


@router.post(
    "/analyze",
    response_model=List[Union[TradeRecommendation, InvestorRecommendation]],
    summary="Sembol listesi için hibrit AI ticaret/yatırım önerisi üret",
    description=(
        "Verilen sembolleri piyasa rejimi taramasından geçirir; geçerli "
        "olanlar için çoklu zaman dilimi teknik analiz hesaplar, haber "
        "duygusuyla birlikte Groq LLM'e sunarak yapılandırılmış bir öneri "
        "üretir.\n\n"
        "``profile=\"trader\"`` (varsayılan): kısa vadeli AL/SAT önerisi, "
        "ATR bazlı risk seviyeleri (giriş/stop-loss/take-profit) ile "
        "birlikte.\n\n"
        "``profile=\"investor\"``: giriş/SL/TP içermeyen, 1 hafta / 1 ay / "
        "1 yıl ufuklarında ayrı AL/SAT/TUT yönü ve güven skoru içeren uzun "
        "vadeli görüş.\n\n"
        "Son 15 dakika içinde aynı sembol+profil için üretilmiş bir öneri "
        "varsa, LLM'e tekrar istek atılmadan doğrudan cache'ten döner.\n\n"
        "Piyasa rejimi filtresini geçemeyen veya veri sağlanamayan "
        "semboller yanıtta yer almaz — dönen liste istekteki sembol "
        "sayısından kısa olabilir."
    ),
    responses={
        404: {"description": "Hiçbir sembol için öneri üretilemedi."},
        422: {"description": "İstek gövdesi geçersiz (ör. boş sembol listesi)."},
    },
)
@limiter.limit("20/minute")
def analyze_signals(
    request: Request,
    body: SignalsAnalyzeRequest,
    engine: HybridTradingEngine = Depends(get_engine),
):
    recommendations = engine.run(body.symbols, profile=body.profile)
    if not recommendations:
        raise HTTPException(
            status_code=404,
            detail="Hiçbir sembol için öneri üretilemedi (piyasa rejimi filtresi, veri veya AI hatası).",
        )
    return recommendations


@router.post(
    "/alerts",
    response_model=List[MarketAlert],
    summary="Sembol listesi için ani piyasa değişikliği (fiyat/hacim/haber şoku) kontrolü",
    description=(
        "Verilen sembolleri piyasa rejimi filtresi UYGULANMADAN kontrol eder "
        "(CHOPPY bir sembolün ani hacim/fiyat şoku göstermesi rejim "
        "değişikliğinin habercisi olabilir). Fiyat/hacim şoku (anormal hacim "
        "veya ATR'ye göre büyük fiyat hareketi) veya yüksek etkili haber "
        "tespit edilen semboller döner.\n\n"
        "Hiçbir uyarı tespit edilmezse boş liste döner — bu normal ve "
        "beklenen bir sonuçtur, hata değildir (``/analyze``'ın aksine 404 "
        "dönmez)."
    ),
    responses={
        422: {"description": "İstek gövdesi geçersiz (ör. boş sembol listesi)."},
    },
)
@limiter.limit("20/minute")
def check_alerts(
    request: Request,
    body: SignalsAnalyzeRequest,
    engine: HybridTradingEngine = Depends(get_engine),
) -> List[MarketAlert]:
    return engine.check_alerts(body.symbols)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && /Users/hasantekbas/miniconda3/bin/python -m pytest tests/unit/test_signals_endpoint.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the full unit test suite to confirm no regressions**

Run: `cd backend && /Users/hasantekbas/miniconda3/bin/python -m pytest tests/unit -q`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/api/v1/endpoints/signals.py backend/tests/unit/test_signals_endpoint.py
git commit -m "feat: add profile param to /signals/analyze and new /signals/alerts endpoint"
```

---

## Post-plan verification (manual, optional but recommended before considering this done)

The full pipeline (`HybridTradingEngine` → `AITraderPersona`/`InvestorPersona`, real Groq calls, real yfinance data) is not exercised by any of the above unit tests by design (all network/LLM calls are mocked). To confirm the new code paths work end-to-end against live data, once a `GROQ_API_KEY` is available:

```bash
cd backend
export GROQ_API_KEY="gsk_..."
python3 -c "
from core.hybrid_engine import HybridTradingEngine
engine = HybridTradingEngine()
print('--- TRADER ---')
for rec in engine.run(['AAPL'], profile='trader'):
    print(rec.symbol, rec.signal, rec.confidence_score)
print('--- INVESTOR ---')
for rec in engine.run(['AAPL'], profile='investor'):
    print(rec.symbol, rec.horizon_1_week.signal, rec.horizon_1_month.signal, rec.horizon_1_year.signal)
print('--- ALERTS ---')
print(engine.check_alerts(['AAPL', 'BTC-USD']))
"
```
