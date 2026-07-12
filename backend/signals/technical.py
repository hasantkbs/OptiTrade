"""
Technical Signal Engine — Phase A
===================================
Transforms scoring contributions from compute_score() into structured
Signal objects.  This is a **read-only transformation**: it never
recomputes indicators or modifies score values.  The scoring engine in
core/scoring.py remains the authoritative source for all numeric values.

Usage
-----
    from signals.technical import TechnicalSignalEngine

    score, long, short, contributions = compute_score(...)
    engine_result = TechnicalSignalEngine().generate(contributions)
    signal_details = {"technical": engine_result.to_dict()}

The contributions list is the same list that is stored in
AnalysisResult.scoring_breakdown — no extra computation needed.
"""
from typing import Dict, List, Optional

from signals.models import EngineResult, Signal


class TechnicalSignalEngine:
    """
    Converts a scoring-contribution list into an EngineResult of Signal objects.

    Each contribution dict (produced by core.scoring._contrib) maps to exactly
    one Signal.  Indicators that can fire multiple times (Ichimoku cloud + TK
    cross, Bollinger band + squeeze) get disambiguated via a per-key sequence
    counter appended to the signal_id.
    """

    # ── Per-indicator base confidence ─────────────────────────────────────────
    # Reflects empirical reliability at default parameter settings.
    # Phase B will allow runtime calibration via historical back-tests.
    _CONFIDENCE: Dict[str, float] = {
        "rsi":            0.75,
        "macd":           0.70,
        "macd_histogram": 0.60,
        "bollinger":      0.65,
        "ema_crossover":  0.75,
        "trend_strength": 0.70,
        "williams_r":     0.65,
        "cci":            0.65,
        "vwap":           0.65,
        "roc":            0.60,
        "ichimoku":       0.72,
        "divergence":     0.80,
        "balance":        0.65,
        "convergence":    0.70,
        "adx":            0.80,
        "stochastic":     0.70,
        "potential_price": 0.55,
    }

    # ── Per-indicator dominant timeframe ─────────────────────────────────────
    _TIMEFRAME: Dict[str, str] = {
        "rsi":            "SHORT",
        "stochastic":     "SHORT",
        "williams_r":     "SHORT",
        "roc":            "SHORT",
        "volume":         "SHORT",
        "vwap":           "SHORT",
        "cci":            "SHORT",
        "macd":           "MEDIUM",
        "macd_histogram": "SHORT",
        "bollinger":      "MEDIUM",
        "ema_crossover":  "MEDIUM",
        "trend_strength": "MEDIUM",
        "adx":            "MEDIUM",
        "divergence":     "MEDIUM",
        "convergence":    "MEDIUM",
        "potential_price": "MEDIUM",
        "ichimoku":       "LONG",
        "balance":        "LONG",
    }

    # ── Per-indicator signal category ─────────────────────────────────────────
    # Phase B will move VOLUME and FUNDAMENTAL contributions to their own engines.
    _CATEGORY: Dict[str, str] = {
        "rsi":            "TECHNICAL",
        "macd":           "TECHNICAL",
        "macd_histogram": "TECHNICAL",
        "bollinger":      "TECHNICAL",
        "ema_crossover":  "TECHNICAL",
        "trend_strength": "TECHNICAL",
        "williams_r":     "TECHNICAL",
        "cci":            "TECHNICAL",
        "vwap":           "TECHNICAL",
        "roc":            "TECHNICAL",
        "ichimoku":       "TECHNICAL",
        "divergence":     "TECHNICAL",
        "adx":            "TECHNICAL",
        "stochastic":     "TECHNICAL",
        "potential_price": "TECHNICAL",
        "volume":         "VOLUME",
        "balance":        "FUNDAMENTAL",
        "convergence":    "META",
    }

    # ── Strength thresholds (fraction of max possible contribution) ───────────
    _STRONG_THRESHOLD   = 0.70
    _MODERATE_THRESHOLD = 0.35

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate(self, contributions: List[dict]) -> EngineResult:
        """
        Transform a contributions list from compute_score() into an EngineResult.

        Parameters
        ----------
        contributions : list of dicts — each produced by core.scoring._contrib()
            Keys: name, indicator_key, value, score_delta, reason, direction,
                  max_bullish, max_bearish

        Returns
        -------
        EngineResult  with one Signal per contribution
        """
        signals: List[Signal] = []
        key_sequence: Dict[str, int] = {}

        for contrib in contributions:
            key = contrib["indicator_key"]
            key_sequence[key] = key_sequence.get(key, 0) + 1
            seq = key_sequence[key]

            signals.append(self._to_signal(contrib, seq))

        return self._aggregate(signals)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _to_signal(self, contrib: dict, seq: int) -> Signal:
        key       = contrib["indicator_key"]
        delta     = float(contrib["score_delta"])
        max_bull  = int(contrib["max_bullish"])
        max_bear  = int(contrib["max_bearish"])
        direction = contrib["direction"]

        base_id   = f"{key}_{direction.lower()}"
        signal_id = base_id if seq == 1 else f"{base_id}_{seq}"

        return Signal(
            signal_id        = signal_id,
            indicator        = contrib["name"],
            value            = contrib["value"],
            normalized_value = self._normalized(delta, max_bull, max_bear),
            direction        = direction,
            strength         = self._strength(delta, max_bull, max_bear),
            confidence       = self._CONFIDENCE.get(key, 0.60),
            contribution     = delta,
            reason           = contrib["reason"],
            timeframe        = self._TIMEFRAME.get(key, "MEDIUM"),
            category         = self._CATEGORY.get(key, "TECHNICAL"),
        )

    @staticmethod
    def _normalized(delta: float, max_bull: int, max_bear: int) -> float:
        """
        Map score_delta to [0.0, 1.0]:
          delta = +max_bull  →  1.0  (maximum bullish)
          delta =  0         →  0.5  (neutral)
          delta = -max_bear  →  0.0  (maximum bearish)

        Formula: (delta + max_range) / (2 × max_range)
        where max_range = max(|max_bull|, |max_bear|)
        """
        max_range = max(abs(max_bull), abs(max_bear))
        if max_range == 0:
            return 0.5
        return round(max(0.0, min(1.0, (delta + max_range) / (2.0 * max_range))), 4)

    @classmethod
    def _strength(cls, delta: float, max_bull: int, max_bear: int) -> str:
        """
        Classify signal strength by fraction of maximum possible contribution.
          ≥ 70%  → STRONG
          ≥ 35%  → MODERATE
          < 35%  → WEAK
        """
        max_range = max(abs(max_bull), abs(max_bear))
        if max_range == 0:
            return "WEAK"
        ratio = abs(delta) / max_range
        if ratio >= cls._STRONG_THRESHOLD:
            return "STRONG"
        if ratio >= cls._MODERATE_THRESHOLD:
            return "MODERATE"
        return "WEAK"

    @staticmethod
    def _aggregate(signals: List[Signal]) -> EngineResult:
        return EngineResult.from_signals("TECHNICAL", signals)
