"""
OptiTrade — Scoring Engine v3
================================
Kural tabanlı teknik puan hesaplama.

All numeric weights and thresholds are imported from scoring_config.py.
Never write a numeric literal for a weight here — change scoring_config.py instead.

compute_score() returns a 4-tuple:
    (score, long_signals, short_signals, contributions)

contributions is a list of dicts — one per indicator that fired — in the format:
    {
        "name":           str,    # human-readable label ("RSI")
        "indicator_key":  str,    # machine-readable key ("rsi")
        "value":          float|None,  # raw indicator value (28.4)
        "score_delta":    int,    # contribution to score (+8, -12, …)
        "reason":         str,    # why this delta was applied
        "direction":      str,    # "BULLISH" | "BEARISH" | "NEUTRAL"
        "max_bullish":    int,    # theoretical max positive contribution
        "max_bearish":    int,    # theoretical max negative contribution
    }
"""
import logging
import time
from typing import Optional, List, Tuple, Dict
from core.structured_logging import STATUS_ERROR, log_event

logger = logging.getLogger(__name__)

from core.session_analysis import compute_session_score
from core.scoring_config import (
    WEIGHTS,
    SCORE_BASE, SCORE_MIN, SCORE_MAX,
    # Potential price
    POTENTIAL_PRICE_STRONG_CHEAP_DELTA, POTENTIAL_PRICE_CHEAP_DELTA,
    POTENTIAL_PRICE_EXPENSIVE_DELTA, POTENTIAL_PRICE_STRONG_EXPENSIVE_DELTA,
    POTENTIAL_PRICE_STRONG_CHEAP_THRESHOLD, POTENTIAL_PRICE_CHEAP_THRESHOLD,
    POTENTIAL_PRICE_EXPENSIVE_THRESHOLD, POTENTIAL_PRICE_STRONG_EXPENSIVE_THRESHOLD,
    # RSI
    RSI_EXTREME_OVERSOLD_DELTA, RSI_OVERSOLD_DELTA,
    RSI_MILD_OVERSOLD_DELTA, RSI_MILD_OVERBOUGHT_DELTA,
    RSI_OVERBOUGHT_DELTA, RSI_EXTREME_OVERBOUGHT_DELTA,
    RSI_EXTREME_OVERSOLD_THRESHOLD, RSI_OVERSOLD_THRESHOLD,
    RSI_MILD_OVERSOLD_THRESHOLD, RSI_MILD_OVERBOUGHT_THRESHOLD,
    RSI_OVERBOUGHT_THRESHOLD, RSI_EXTREME_OVERBOUGHT_THRESHOLD,
    # MACD
    MACD_BULLISH_DELTA, MACD_BEARISH_DELTA,
    MACD_HIST_BULLISH_DELTA, MACD_HIST_BEARISH_DELTA, MACD_HIST_MOMENTUM_RATIO,
    # Bollinger
    BB_BELOW_BAND_STRONG_DELTA, BB_BELOW_BAND_MILD_DELTA,
    BB_ABOVE_BAND_MILD_DELTA, BB_ABOVE_BAND_STRONG_DELTA,
    BB_BELOW_STRONG_THRESHOLD, BB_BELOW_MILD_THRESHOLD,
    BB_ABOVE_MILD_THRESHOLD, BB_ABOVE_STRONG_THRESHOLD, BB_SQUEEZE_THRESHOLD,
    # EMA
    EMA_GOLDEN_CROSS_DELTA, EMA_DEATH_CROSS_DELTA,
    EMA_BULLISH_DELTA, EMA_BEARISH_DELTA,
    # Trend
    TREND_STRONG_BULLISH_DELTA, TREND_MILD_BULLISH_DELTA,
    TREND_MILD_BEARISH_DELTA, TREND_STRONG_BEARISH_DELTA,
    TREND_STRONG_THRESHOLD, TREND_MILD_THRESHOLD,
    # Volume
    VOLUME_STRONG_BULL_DELTA, VOLUME_STRONG_BEAR_DELTA,
    VOLUME_STRONG_NEUTRAL_DELTA, VOLUME_ABOVE_AVG_DELTA, VOLUME_WEAK_DELTA,
    VOLUME_STRONG_THRESHOLD, VOLUME_ABOVE_THRESHOLD, VOLUME_WEAK_THRESHOLD,
    # Williams %R
    WILLIAMS_EXTREME_OVERSOLD_DELTA, WILLIAMS_OVERSOLD_DELTA,
    WILLIAMS_OVERBOUGHT_DELTA, WILLIAMS_EXTREME_OVERBOUGHT_DELTA,
    WILLIAMS_EXTREME_OVERSOLD_THRESHOLD, WILLIAMS_OVERSOLD_THRESHOLD,
    WILLIAMS_OVERBOUGHT_THRESHOLD, WILLIAMS_EXTREME_OVERBOUGHT_THRESHOLD,
    # CCI
    CCI_EXTREME_OVERSOLD_DELTA, CCI_OVERSOLD_DELTA,
    CCI_OVERBOUGHT_DELTA, CCI_EXTREME_OVERBOUGHT_DELTA,
    CCI_EXTREME_OVERSOLD_THRESHOLD, CCI_OVERSOLD_THRESHOLD,
    CCI_OVERBOUGHT_THRESHOLD, CCI_EXTREME_OVERBOUGHT_THRESHOLD, CCI_ZERO_BAND,
    # VWAP
    VWAP_ABOVE_DELTA, VWAP_BELOW_DELTA, VWAP_THRESHOLD_PCT,
    # ROC
    ROC_STRONG_BULLISH_DELTA, ROC_MILD_BULLISH_DELTA,
    ROC_MILD_BEARISH_DELTA, ROC_STRONG_BEARISH_DELTA,
    ROC_STRONG_THRESHOLD, ROC_MILD_THRESHOLD,
    # Ichimoku
    ICHIMOKU_ABOVE_CLOUD_DELTA, ICHIMOKU_BELOW_CLOUD_DELTA,
    ICHIMOKU_TK_BULLISH_DELTA, ICHIMOKU_TK_BEARISH_DELTA,
    # Divergence
    DIVERGENCE_BULLISH_DELTA, DIVERGENCE_BEARISH_DELTA,
    # Balance
    BALANCE_POSITIVE_DELTA, BALANCE_NEGATIVE_DELTA,
    # Convergence
    CONVERGENCE_STRONG_DELTA, CONVERGENCE_MEDIUM_DELTA, CONVERGENCE_MILD_DELTA,
    CONVERGENCE_STRONG_THRESHOLD, CONVERGENCE_MEDIUM_THRESHOLD, CONVERGENCE_MILD_THRESHOLD,
    # ADX
    ADX_WEAK_TREND_DELTA, ADX_MEDIUM_TREND_DELTA, ADX_STRONG_TREND_DELTA,
    ADX_WEAK_THRESHOLD, ADX_MEDIUM_THRESHOLD, ADX_STRONG_THRESHOLD,
    # Stochastic
    STOCH_EXTREME_OVERSOLD_DELTA, STOCH_OVERSOLD_DELTA,
    STOCH_OVERBOUGHT_DELTA, STOCH_EXTREME_OVERBOUGHT_DELTA,
    STOCH_KD_BULLISH_DELTA, STOCH_KD_BEARISH_DELTA,
    STOCH_EXTREME_OVERSOLD_THRESHOLD, STOCH_OVERSOLD_THRESHOLD,
    STOCH_OVERBOUGHT_THRESHOLD, STOCH_EXTREME_OVERBOUGHT_THRESHOLD,
    # Session blend
    SESSION_BASE_WEIGHT, SESSION_SESSION_WEIGHT,
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _contrib(key: str, value, delta: int, reason: str) -> dict:
    """Build a standardised scoring-contribution record."""
    w = WEIGHTS[key]
    return {
        "name":           w.name,
        "indicator_key":  key,
        "value":          round(float(value), 4) if isinstance(value, (int, float)) else value,
        "score_delta":    delta,
        "reason":         reason,
        "direction":      "BULLISH" if delta > 0 else ("BEARISH" if delta < 0 else "NEUTRAL"),
        "max_bullish":    w.max_bullish,
        "max_bearish":    w.max_bearish,
    }


# ── Main scoring function ─────────────────────────────────────────────────────

def compute_score(
    current_price: float,
    potential_price: Optional[float],
    volume_ratio: float,
    balance_status: str,
    rsi: Optional[float],
    macd: Optional[float],
    macd_signal: Optional[float],
    bollinger: Optional[Dict[str, Optional[float]]] = None,
    ema_crossover: Optional[str] = None,
    trend_strength: Optional[float] = None,
    macd_hist: Optional[float] = None,
    williams_r: Optional[float] = None,
    cci: Optional[float] = None,
    ichimoku: Optional[Dict] = None,
    divergence: Optional[Dict] = None,
    vwap: Optional[float] = None,
    roc: Optional[float] = None,
    # ── New in Step 0.2 ──────────────────────────────────────────────────────
    adx: Optional[float] = None,
    stoch_k: Optional[float] = None,
    stoch_d: Optional[float] = None,
) -> Tuple[int, List[str], List[str], List[dict]]:
    """
    Compute a 0-100 rule-based score and return explainable contributions.

    Returns:
        score          — final integer score [0, 100]
        long_signals   — bullish signal messages (Turkish)
        short_signals  — bearish signal messages (Turkish)
        contributions  — per-indicator breakdown for explainability
    """
    score: int = SCORE_BASE
    long_signals:  List[str] = []
    short_signals: List[str] = []
    bull_count = 0
    bear_count = 0
    contributions: List[dict] = []

    # ── Potansiyel fiyat ─────────────────────────────────────────────────────
    if potential_price and potential_price > 0:
        ratio = current_price / potential_price
        if ratio < POTENTIAL_PRICE_STRONG_CHEAP_THRESHOLD:
            delta = POTENTIAL_PRICE_STRONG_CHEAP_DELTA
            msg   = "Fiyat potansiyelin %15+ altinda (ucuz)"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("potential_price", ratio, delta, msg))
        elif ratio < POTENTIAL_PRICE_CHEAP_THRESHOLD:
            delta = POTENTIAL_PRICE_CHEAP_DELTA
            msg   = "Fiyat potansiyelin altinda"
            score += delta; long_signals.append(msg)
            contributions.append(_contrib("potential_price", ratio, delta, msg))
        elif ratio > POTENTIAL_PRICE_STRONG_EXPENSIVE_THRESHOLD:
            delta = POTENTIAL_PRICE_STRONG_EXPENSIVE_DELTA
            msg   = "Fiyat potansiyelin %10+ ustunde (pahali)"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("potential_price", ratio, delta, msg))
        elif ratio > POTENTIAL_PRICE_EXPENSIVE_THRESHOLD:
            delta = POTENTIAL_PRICE_EXPENSIVE_DELTA
            msg   = "Fiyat potansiyelin ustunde"
            score += delta; short_signals.append(msg)
            contributions.append(_contrib("potential_price", ratio, delta, msg))

    # ── RSI ──────────────────────────────────────────────────────────────────
    if rsi is not None:
        if rsi > RSI_EXTREME_OVERBOUGHT_THRESHOLD:
            delta = RSI_EXTREME_OVERBOUGHT_DELTA
            msg   = f"RSI cok asiri alim ({rsi:.1f})"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("rsi", rsi, delta, msg))
        elif rsi > RSI_OVERBOUGHT_THRESHOLD:
            delta = RSI_OVERBOUGHT_DELTA
            msg   = f"RSI asiri alim bolgesinde ({rsi:.1f})"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("rsi", rsi, delta, msg))
        elif rsi < RSI_EXTREME_OVERSOLD_THRESHOLD:
            delta = RSI_EXTREME_OVERSOLD_DELTA
            msg   = f"RSI cok asiri satim ({rsi:.1f})"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("rsi", rsi, delta, msg))
        elif rsi < RSI_OVERSOLD_THRESHOLD:
            delta = RSI_OVERSOLD_DELTA
            msg   = f"RSI asiri satim bolgesinde ({rsi:.1f})"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("rsi", rsi, delta, msg))
        elif rsi < RSI_MILD_OVERSOLD_THRESHOLD:
            delta = RSI_MILD_OVERSOLD_DELTA
            msg   = f"RSI hafif alim bolgesi ({rsi:.1f})"
            score += delta
            contributions.append(_contrib("rsi", rsi, delta, msg))
        elif rsi > RSI_MILD_OVERBOUGHT_THRESHOLD:
            delta = RSI_MILD_OVERBOUGHT_DELTA
            msg   = f"RSI hafif satis bolgesi ({rsi:.1f})"
            score += delta
            contributions.append(_contrib("rsi", rsi, delta, msg))

    # ── MACD ─────────────────────────────────────────────────────────────────
    if macd is not None and macd_signal is not None:
        if macd > macd_signal:
            delta = MACD_BULLISH_DELTA
            msg   = "MACD sinyal cizgisinin ustunde (yukselis)"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("macd", macd, delta, msg))
        else:
            delta = MACD_BEARISH_DELTA
            msg   = "MACD sinyal cizgisinin altinda (dusus)"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("macd", macd, delta, msg))

        if macd_hist is not None:
            threshold = MACD_HIST_MOMENTUM_RATIO * abs(macd if macd else 0.001)
            if macd_hist > threshold:
                delta = MACD_HIST_BULLISH_DELTA
                msg   = "MACD histogram ivmeleniyor"
                score += delta; long_signals.append(msg)
                contributions.append(_contrib("macd_histogram", macd_hist, delta, msg))
            elif macd_hist < -threshold:
                delta = MACD_HIST_BEARISH_DELTA
                msg   = "MACD histogram yavasliyor (negatif)"
                score += delta; short_signals.append(msg)
                contributions.append(_contrib("macd_histogram", macd_hist, delta, msg))

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    if bollinger is not None and bollinger.get("percent_b") is not None:
        pb = bollinger["percent_b"]
        if pb < BB_BELOW_STRONG_THRESHOLD:
            delta = BB_BELOW_BAND_STRONG_DELTA
            msg   = f"Fiyat Bollinger alt bandinin altinda (%B={pb:.2f})"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("bollinger", pb, delta, msg))
        elif pb < BB_BELOW_MILD_THRESHOLD:
            delta = BB_BELOW_BAND_MILD_DELTA
            msg   = f"Fiyat Bollinger alt bandina yakin (%B={pb:.2f})"
            score += delta; long_signals.append(msg)
            contributions.append(_contrib("bollinger", pb, delta, msg))
        elif pb > BB_ABOVE_STRONG_THRESHOLD:
            delta = BB_ABOVE_BAND_STRONG_DELTA
            msg   = f"Fiyat Bollinger ust bandinin ustunde (%B={pb:.2f})"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("bollinger", pb, delta, msg))
        elif pb > BB_ABOVE_MILD_THRESHOLD:
            delta = BB_ABOVE_BAND_MILD_DELTA
            msg   = f"Fiyat Bollinger ust bandina yakin (%B={pb:.2f})"
            score += delta; short_signals.append(msg)
            contributions.append(_contrib("bollinger", pb, delta, msg))

        bw = bollinger.get("bandwidth")
        if bw is not None and bw < BB_SQUEEZE_THRESHOLD:
            msg = f"Bollinger sikismasi (%{bw:.1f}) — kirilim olasiligi yuksek"
            long_signals.append(msg)
            contributions.append(_contrib("bollinger", bw, 0, msg))

    # ── EMA Crossover ─────────────────────────────────────────────────────────
    if ema_crossover is not None:
        if ema_crossover == "GOLDEN_CROSS":
            delta = EMA_GOLDEN_CROSS_DELTA
            msg   = "EMA 20/50 Altin Kesisim — guclu yukselis sinyali"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("ema_crossover", None, delta, msg))
        elif ema_crossover == "DEATH_CROSS":
            delta = EMA_DEATH_CROSS_DELTA
            msg   = "EMA 20/50 Olum Kesisimi — guclu dusus sinyali"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("ema_crossover", None, delta, msg))
        elif ema_crossover == "BULLISH":
            delta = EMA_BULLISH_DELTA
            msg   = "EMA 20/50 yukselis pozisyonu"
            score += delta
            contributions.append(_contrib("ema_crossover", None, delta, msg))
        elif ema_crossover == "BEARISH":
            delta = EMA_BEARISH_DELTA
            msg   = "EMA 20/50 dusus pozisyonu"
            score += delta
            contributions.append(_contrib("ema_crossover", None, delta, msg))

    # ── Trend Strength ────────────────────────────────────────────────────────
    if trend_strength is not None:
        if trend_strength > TREND_STRONG_THRESHOLD:
            delta = TREND_STRONG_BULLISH_DELTA
            msg   = f"Guclu yukselis trendi (EMA'dan %{trend_strength:.1f} yukarida)"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("trend_strength", trend_strength, delta, msg))
        elif trend_strength > TREND_MILD_THRESHOLD:
            delta = TREND_MILD_BULLISH_DELTA
            msg   = f"Hafif yukselis trendi (%{trend_strength:.1f})"
            score += delta
            contributions.append(_contrib("trend_strength", trend_strength, delta, msg))
        elif trend_strength < -TREND_STRONG_THRESHOLD:
            delta = TREND_STRONG_BEARISH_DELTA
            msg   = f"Guclu dusus trendi (EMA'dan %{abs(trend_strength):.1f} asagida)"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("trend_strength", trend_strength, delta, msg))
        elif trend_strength < -TREND_MILD_THRESHOLD:
            delta = TREND_MILD_BEARISH_DELTA
            msg   = f"Hafif dusus trendi (%{abs(trend_strength):.1f})"
            score += delta
            contributions.append(_contrib("trend_strength", trend_strength, delta, msg))

    # ── Hacim ─────────────────────────────────────────────────────────────────
    if volume_ratio > VOLUME_STRONG_THRESHOLD:
        if bull_count >= 2:
            delta = VOLUME_STRONG_BULL_DELTA
            msg   = f"Hacim cok guclu + sinyal destegi ({volume_ratio:.1f}x)"
            score += delta; long_signals.append(msg)
            contributions.append(_contrib("volume", volume_ratio, delta, msg))
        elif bear_count >= 2:
            delta = VOLUME_STRONG_BEAR_DELTA
            msg   = f"Hacim guclu + dusus sinyalleri ({volume_ratio:.1f}x)"
            score += delta; short_signals.append(msg)
            contributions.append(_contrib("volume", volume_ratio, delta, msg))
        else:
            delta = VOLUME_STRONG_NEUTRAL_DELTA
            msg   = f"Hacim ortalamanin {volume_ratio:.1f}x ustunde"
            score += delta; long_signals.append(msg)
            contributions.append(_contrib("volume", volume_ratio, delta, msg))
    elif volume_ratio > VOLUME_ABOVE_THRESHOLD:
        delta = VOLUME_ABOVE_AVG_DELTA
        msg   = f"Hacim ortalamanin {volume_ratio:.1f}x ustunde"
        score += delta; long_signals.append(msg)
        contributions.append(_contrib("volume", volume_ratio, delta, msg))
    elif volume_ratio < VOLUME_WEAK_THRESHOLD:
        delta = VOLUME_WEAK_DELTA
        msg   = "Hacim cok zayif — trend onaylanmiyor"
        score += delta; short_signals.append(msg)
        contributions.append(_contrib("volume", volume_ratio, delta, msg))

    # ── Williams %R ───────────────────────────────────────────────────────────
    if williams_r is not None:
        if williams_r <= WILLIAMS_EXTREME_OVERSOLD_THRESHOLD:
            delta = WILLIAMS_EXTREME_OVERSOLD_DELTA
            msg   = f"Williams %R asiri satim ({williams_r:.1f}) — alim firsat bolgesi"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("williams_r", williams_r, delta, msg))
        elif williams_r <= WILLIAMS_OVERSOLD_THRESHOLD:
            delta = WILLIAMS_OVERSOLD_DELTA
            msg   = f"Williams %R dusuk ({williams_r:.1f}) — satici baskisi azaliyor"
            score += delta; long_signals.append(msg)
            contributions.append(_contrib("williams_r", williams_r, delta, msg))
        elif williams_r >= WILLIAMS_EXTREME_OVERBOUGHT_THRESHOLD:
            delta = WILLIAMS_EXTREME_OVERBOUGHT_DELTA
            msg   = f"Williams %R asiri alim ({williams_r:.1f}) — satis baskisi artabilir"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("williams_r", williams_r, delta, msg))
        elif williams_r >= WILLIAMS_OVERBOUGHT_THRESHOLD:
            delta = WILLIAMS_OVERBOUGHT_DELTA
            msg   = f"Williams %R yuksek ({williams_r:.1f}) — dikkatli olun"
            score += delta; short_signals.append(msg)
            contributions.append(_contrib("williams_r", williams_r, delta, msg))

    # ── CCI ───────────────────────────────────────────────────────────────────
    if cci is not None:
        if cci < CCI_EXTREME_OVERSOLD_THRESHOLD:
            delta = CCI_EXTREME_OVERSOLD_DELTA
            msg   = f"CCI cok asiri satim ({cci:.0f}) — guclu geri donus sinyali"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("cci", cci, delta, msg))
        elif cci < CCI_OVERSOLD_THRESHOLD:
            delta = CCI_OVERSOLD_DELTA
            msg   = f"CCI asiri satim ({cci:.0f})"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("cci", cci, delta, msg))
        elif cci > CCI_EXTREME_OVERBOUGHT_THRESHOLD:
            delta = CCI_EXTREME_OVERBOUGHT_DELTA
            msg   = f"CCI cok asiri alim ({cci:.0f}) — kar alma bolgesi"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("cci", cci, delta, msg))
        elif cci > CCI_OVERBOUGHT_THRESHOLD:
            delta = CCI_OVERBOUGHT_DELTA
            msg   = f"CCI asiri alim ({cci:.0f})"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("cci", cci, delta, msg))
        elif abs(cci) < CCI_ZERO_BAND:
            msg = "CCI sifir bolgesi — momentum sifirlanmis, yon belirsiz"
            long_signals.append(msg)
            contributions.append(_contrib("cci", cci, 0, msg))

    # ── VWAP ──────────────────────────────────────────────────────────────────
    if vwap is not None and current_price > 0:
        vwap_diff_pct = (current_price - vwap) / vwap * 100
        if vwap_diff_pct > VWAP_THRESHOLD_PCT:
            delta = VWAP_ABOVE_DELTA
            msg   = f"Fiyat VWAP'in %{vwap_diff_pct:.1f} ustunde — ortalamaya donus riski"
            score += delta; short_signals.append(msg)
            contributions.append(_contrib("vwap", vwap_diff_pct, delta, msg))
        elif vwap_diff_pct < -VWAP_THRESHOLD_PCT:
            delta = VWAP_BELOW_DELTA
            msg   = f"Fiyat VWAP'in %{abs(vwap_diff_pct):.1f} altinda — destek bolgesi"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("vwap", vwap_diff_pct, delta, msg))

    # ── Rate of Change (ROC) ──────────────────────────────────────────────────
    if roc is not None:
        if roc > ROC_STRONG_THRESHOLD:
            delta = ROC_STRONG_BULLISH_DELTA
            msg   = f"ROC guclu yukselis momentumu (%{roc:.1f})"
            score += delta; long_signals.append(msg)
            contributions.append(_contrib("roc", roc, delta, msg))
        elif roc > ROC_MILD_THRESHOLD:
            delta = ROC_MILD_BULLISH_DELTA
            msg   = f"ROC yukselis momentumu (%{roc:.1f})"
            score += delta
            contributions.append(_contrib("roc", roc, delta, msg))
        elif roc < -ROC_STRONG_THRESHOLD:
            delta = ROC_STRONG_BEARISH_DELTA
            msg   = f"ROC guclu dusus momentumu (%{roc:.1f})"
            score += delta; short_signals.append(msg)
            contributions.append(_contrib("roc", roc, delta, msg))
        elif roc < -ROC_MILD_THRESHOLD:
            delta = ROC_MILD_BEARISH_DELTA
            msg   = f"ROC dusus momentumu (%{roc:.1f})"
            score += delta
            contributions.append(_contrib("roc", roc, delta, msg))

    # ── Ichimoku Cloud ────────────────────────────────────────────────────────
    if ichimoku is not None:
        cloud_sig = ichimoku.get("cloud_signal")
        tk_cross  = ichimoku.get("tk_cross")

        if cloud_sig == "ABOVE_CLOUD":
            delta = ICHIMOKU_ABOVE_CLOUD_DELTA
            msg   = "Ichimoku: Fiyat bulutun ustunde — guclu yukselis trendi"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("ichimoku", None, delta, msg))
        elif cloud_sig == "BELOW_CLOUD":
            delta = ICHIMOKU_BELOW_CLOUD_DELTA
            msg   = "Ichimoku: Fiyat bulutun altinda — guclu dusus trendi"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("ichimoku", None, delta, msg))
        elif cloud_sig == "INSIDE_CLOUD":
            msg = "Ichimoku: Fiyat bulut icinde — kararsizlik bolgesi"
            long_signals.append(msg)
            contributions.append(_contrib("ichimoku", None, 0, msg))

        if tk_cross == "BULLISH":
            delta = ICHIMOKU_TK_BULLISH_DELTA
            msg   = "Ichimoku TK kesisimi (boga): Tenkan, Kijun'u kesti — alim sinyali"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("ichimoku", None, delta, msg))
        elif tk_cross == "BEARISH":
            delta = ICHIMOKU_TK_BEARISH_DELTA
            msg   = "Ichimoku TK kesisimi (ayi): Tenkan, Kijun'u asagi kesti — satis sinyali"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("ichimoku", None, delta, msg))

    # ── Diverjans ─────────────────────────────────────────────────────────────
    if divergence is not None:
        div_type = divergence.get("divergence")
        desc     = divergence.get("description", "")
        if div_type == "BULLISH_DIVERGENCE":
            delta = DIVERGENCE_BULLISH_DELTA
            msg   = f"DIVERJANS ALIM: {desc}"
            score += delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("divergence", None, delta, msg))
        elif div_type == "BEARISH_DIVERGENCE":
            delta = DIVERGENCE_BEARISH_DELTA
            msg   = f"DIVERJANS SATIS: {desc}"
            score += delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("divergence", None, delta, msg))

    # ── Bilanço ───────────────────────────────────────────────────────────────
    if balance_status == "Pozitif":
        delta = BALANCE_POSITIVE_DELTA
        msg   = "Bilanco pozitif (forwardEPS > trailingEPS)"
        score += delta; long_signals.append(msg)
        contributions.append(_contrib("balance", None, delta, msg))
    elif balance_status == "Negatif":
        delta = BALANCE_NEGATIVE_DELTA
        msg   = "Bilanco negatif (forwardEPS < trailingEPS)"
        score += delta; short_signals.append(msg)
        contributions.append(_contrib("balance", None, delta, msg))

    # ── Stochastic (Step 0.2) ─────────────────────────────────────────────────
    # Placed before ADX so that ADX can read the bull/bear counts that include
    # the stochastic signal, making the ADX direction judgment more accurate.
    if stoch_k is not None:
        stoch_delta = 0
        if stoch_k < STOCH_EXTREME_OVERSOLD_THRESHOLD:
            stoch_delta = STOCH_EXTREME_OVERSOLD_DELTA
            msg = f"Stochastic aşırı satım (%K={stoch_k:.0f}) — alım fırsatı"
            score += stoch_delta; bull_count += 1; long_signals.append(msg)
            contributions.append(_contrib("stochastic", stoch_k, stoch_delta, msg))
        elif stoch_k < STOCH_OVERSOLD_THRESHOLD:
            stoch_delta = STOCH_OVERSOLD_DELTA
            msg = f"Stochastic satım bölgesi (%K={stoch_k:.0f})"
            score += stoch_delta; long_signals.append(msg)
            contributions.append(_contrib("stochastic", stoch_k, stoch_delta, msg))
        elif stoch_k > STOCH_EXTREME_OVERBOUGHT_THRESHOLD:
            stoch_delta = STOCH_EXTREME_OVERBOUGHT_DELTA
            msg = f"Stochastic aşırı alım (%K={stoch_k:.0f}) — satış baskısı"
            score += stoch_delta; bear_count += 1; short_signals.append(msg)
            contributions.append(_contrib("stochastic", stoch_k, stoch_delta, msg))
        elif stoch_k > STOCH_OVERBOUGHT_THRESHOLD:
            stoch_delta = STOCH_OVERBOUGHT_DELTA
            msg = f"Stochastic alım bölgesi (%K={stoch_k:.0f})"
            score += stoch_delta; short_signals.append(msg)
            contributions.append(_contrib("stochastic", stoch_k, stoch_delta, msg))

        # %K/%D momentum crossover — only when not already in extreme zone
        if stoch_d is not None and stoch_delta == 0:
            if stoch_k > stoch_d:
                delta = STOCH_KD_BULLISH_DELTA
                msg   = f"Stochastic %K > %D ({stoch_k:.0f} > {stoch_d:.0f}) — yükselen momentum"
                score += delta; long_signals.append(msg)
                contributions.append(_contrib("stochastic", stoch_k, delta, msg))
            elif stoch_k < stoch_d:
                delta = STOCH_KD_BEARISH_DELTA
                msg   = f"Stochastic %K < %D ({stoch_k:.0f} < {stoch_d:.0f}) — düşen momentum"
                score += delta; short_signals.append(msg)
                contributions.append(_contrib("stochastic", stoch_k, delta, msg))

    # ── ADX (Step 0.2) ────────────────────────────────────────────────────────
    # ADX scores AFTER all directional indicators have been tallied so that
    # bull_count / bear_count reflect the full signal picture.
    if adx is not None:
        if adx < ADX_WEAK_THRESHOLD:
            delta = ADX_WEAK_TREND_DELTA
            msg   = f"ADX trend zayif ({adx:.0f}) — sinyal güvenilirliği düsük"
            score += delta; short_signals.append(msg)
            contributions.append(_contrib("adx", adx, delta, msg))
        elif adx >= ADX_STRONG_THRESHOLD:
            if bull_count > bear_count:
                delta = ADX_STRONG_TREND_DELTA
                msg   = f"ADX cok guclu trend ({adx:.0f}) — yukselis sinyallerini dogrular"
                score += delta; long_signals.append(msg)
                contributions.append(_contrib("adx", adx, delta, msg))
            elif bear_count > bull_count:
                delta = -ADX_STRONG_TREND_DELTA
                msg   = f"ADX cok guclu trend ({adx:.0f}) — dusus sinyallerini dogrular"
                score += delta; short_signals.append(msg)
                contributions.append(_contrib("adx", adx, delta, msg))
            else:
                msg = f"ADX cok guclu trend ({adx:.0f}) ancak yon belirsiz"
                contributions.append(_contrib("adx", adx, 0, msg))
        elif adx >= ADX_MEDIUM_THRESHOLD:
            if bull_count > bear_count:
                delta = ADX_MEDIUM_TREND_DELTA
                msg   = f"ADX trend guclu ({adx:.0f}) — yukselis momentum onaylandi"
                score += delta; long_signals.append(msg)
                contributions.append(_contrib("adx", adx, delta, msg))
            elif bear_count > bull_count:
                delta = -ADX_MEDIUM_TREND_DELTA
                msg   = f"ADX trend guclu ({adx:.0f}) — dusus momentum onaylandi"
                score += delta; short_signals.append(msg)
                contributions.append(_contrib("adx", adx, delta, msg))
            else:
                msg = f"ADX orta gucte trend ({adx:.0f}) — yon dengeli"
                contributions.append(_contrib("adx", adx, 0, msg))
        else:
            # ADX_WEAK_THRESHOLD <= adx < ADX_MEDIUM_THRESHOLD — uncertain zone
            msg = f"ADX belirsiz bölge ({adx:.0f}) — trend henuz olusmuyor"
            contributions.append(_contrib("adx", adx, 0, msg))

    # ── Yakınsama Bonusu ──────────────────────────────────────────────────────
    if bull_count >= CONVERGENCE_STRONG_THRESHOLD:
        delta = CONVERGENCE_STRONG_DELTA
        msg   = f"Guclu yakinlasma: {bull_count} yukselis sinyali ayni anda"
        score += delta; long_signals.append(msg)
        contributions.append(_contrib("convergence", bull_count, delta, msg))
    elif bull_count >= CONVERGENCE_MEDIUM_THRESHOLD:
        delta = CONVERGENCE_MEDIUM_DELTA
        msg   = f"Yakinlasma: {bull_count} yukselis sinyali"
        score += delta; long_signals.append(msg)
        contributions.append(_contrib("convergence", bull_count, delta, msg))
    elif bull_count >= CONVERGENCE_MILD_THRESHOLD:
        delta = CONVERGENCE_MILD_DELTA
        msg   = f"Hafif yakinlasma: {bull_count} yukselis sinyali"
        score += delta
        contributions.append(_contrib("convergence", bull_count, delta, msg))
    elif bear_count >= CONVERGENCE_STRONG_THRESHOLD:
        delta = -CONVERGENCE_STRONG_DELTA
        msg   = f"Guclu yakinlasma: {bear_count} dusus sinyali ayni anda"
        score += delta; short_signals.append(msg)
        contributions.append(_contrib("convergence", bear_count, delta, msg))
    elif bear_count >= CONVERGENCE_MEDIUM_THRESHOLD:
        delta = -CONVERGENCE_MEDIUM_DELTA
        msg   = f"Yakinlasma: {bear_count} dusus sinyali"
        score += delta; short_signals.append(msg)
        contributions.append(_contrib("convergence", bear_count, delta, msg))
    elif bear_count >= CONVERGENCE_MILD_THRESHOLD:
        delta = -CONVERGENCE_MILD_DELTA
        msg   = f"Hafif yakinlasma: {bear_count} dusus sinyali"
        score += delta
        contributions.append(_contrib("convergence", bear_count, delta, msg))

    # ── Seans Düzeltmesi ─────────────────────────────────────────────────────
    base_score_clamped = max(SCORE_MIN, min(SCORE_MAX, score))
    _session_step_started_at = time.perf_counter()
    try:
        session_data = compute_session_score(
            rsi=rsi,
            macd=macd,
            macd_signal_val=macd_signal,
            macd_hist=macd_hist,
            volume_ratio=volume_ratio,
            base_score=base_score_clamped,
        )
        session_adj = session_data["session_adjusted_score"]
        final_score = int(round(
            SESSION_BASE_WEIGHT    * base_score_clamped +
            SESSION_SESSION_WEIGHT * session_adj
        ))

        sess_signals = session_data.get("session_signals", [])
        if session_data.get("session_code") == "OVERLAP":
            long_signals = sess_signals + long_signals
        else:
            long_signals = long_signals + sess_signals

    except Exception as exc:
        final_score = base_score_clamped
        log_event(
            logger,
            component="scoring_engine",
            module="core.scoring",
            operation="session_adjustment",
            status=STATUS_ERROR,
            error_type=type(exc).__name__,
            execution_time_ms=(time.perf_counter() - _session_step_started_at) * 1000,
            fallback_score=final_score,
            level=logging.WARNING,
        )

    final_score = max(SCORE_MIN, min(SCORE_MAX, final_score))
    return final_score, long_signals, short_signals, contributions


# ── Decision and risk helpers ─────────────────────────────────────────────────

def get_decision(score: int) -> Tuple[str, str]:
    if score >= 78:
        return "GUCLU AL (LONG)", "STRONG_BUY"
    elif score >= 63:
        return "AL", "BUY"
    elif score <= 22:
        return "GUCLU SAT (SHORT)", "STRONG_SELL"
    elif score <= 37:
        return "SAT", "SELL"
    else:
        return "NOTR / IZLE", "NEUTRAL"


def get_risk_level(price_velocity: float, atr_pct: Optional[float] = None) -> str:
    """ATR-backed risk level."""
    vel = abs(price_velocity)
    atr = atr_pct or 0.0
    risk_score = max(vel, atr)
    if risk_score > 6:
        return "Cok Yuksek"
    elif risk_score > 3.5:
        return "Yuksek"
    elif risk_score > 1.5:
        return "Orta"
    return "Dusuk"
