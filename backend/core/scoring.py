"""
OptiTrade — Scoring Engine v2
================================
Kural tabanlı teknik puan hesaplama.
Tüm sinyaller [-∞, +∞] puanlar vererek 0–100 arası nihai skor üretir.

Ağırlık hiyerarşisi (toplam ~100 puan alan skor):
  RSI                : ±14
  MACD               : ±8
  Bollinger Bands    : ±10
  EMA Crossover      : ±10
  Trend Strength     : ±6
  Hacim              : ±8
  Williams %R        : ±8
  CCI                : ±8
  Ichimoku Cloud     : ±10
  Diverjans          : ±12
  Yakınsama bonusu   : ±7
  Bilanço            : ±6
  Potansiyel fiyat   : ±12
  Seans düzeltmesi   : %30 ağırlıkla karıştırılır
"""
import logging
import time
from typing import Optional, List, Tuple, Dict
from core.session_analysis import compute_session_score
from core.structured_logging import STATUS_ERROR, log_event

logger = logging.getLogger(__name__)


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
    # Yeni indikatörler
    williams_r: Optional[float] = None,
    cci: Optional[float] = None,
    ichimoku: Optional[Dict] = None,
    divergence: Optional[Dict] = None,
    vwap: Optional[float] = None,
    roc: Optional[float] = None,
) -> Tuple[int, List[str], List[str]]:

    score = 50
    long_signals:  List[str] = []
    short_signals: List[str] = []
    bull_count = 0
    bear_count = 0

    # ── Potansiyel fiyat ─────────────────────────────────────────────────────
    if potential_price and potential_price > 0:
        ratio = current_price / potential_price
        if ratio < 0.85:
            score += 12; bull_count += 1
            long_signals.append("Fiyat potansiyelin %15+ altinda (ucuz)")
        elif ratio < 0.95:
            score += 4
            long_signals.append("Fiyat potansiyelin altinda")
        elif ratio > 1.10:
            score -= 12; bear_count += 1
            short_signals.append("Fiyat potansiyelin %10+ ustunde (pahali)")
        elif ratio > 1.02:
            score -= 4
            short_signals.append("Fiyat potansiyelin ustunde")

    # ── RSI ──────────────────────────────────────────────────────────────────
    if rsi is not None:
        if rsi > 80:
            score -= 14; bear_count += 1
            short_signals.append(f"RSI cok asiri alim ({rsi:.1f})")
        elif rsi > 70:
            score -= 8; bear_count += 1
            short_signals.append(f"RSI asiri alim bolgesinde ({rsi:.1f})")
        elif rsi < 20:
            score += 14; bull_count += 1
            long_signals.append(f"RSI cok asiri satim ({rsi:.1f})")
        elif rsi < 30:
            score += 8; bull_count += 1
            long_signals.append(f"RSI asiri satim bolgesinde ({rsi:.1f})")
        elif rsi < 40:
            score += 2
        elif rsi > 60:
            score -= 2

    # ── MACD ─────────────────────────────────────────────────────────────────
    if macd is not None and macd_signal is not None:
        if macd > macd_signal:
            score += 6; bull_count += 1
            long_signals.append("MACD sinyal cizgisinin ustunde (yukselis)")
        else:
            score -= 6; bear_count += 1
            short_signals.append("MACD sinyal cizgisinin altinda (dusus)")
        # Histogram ivmesi — momentum hızlanması/yavaşlaması
        if macd_hist is not None:
            if macd_hist > 0.05 * abs(macd if macd else 0.001):
                score += 2; long_signals.append("MACD histogram ivmeleniyor")
            elif macd_hist < -0.05 * abs(macd if macd else 0.001):
                score -= 2; short_signals.append("MACD histogram yavašliyor (negatif)")

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    if bollinger is not None and bollinger.get("percent_b") is not None:
        pb = bollinger["percent_b"]
        if pb < -0.05:
            score += 10; bull_count += 1
            long_signals.append(f"Fiyat Bollinger alt bandinin altinda (%B={pb:.2f})")
        elif pb < 0.15:
            score += 4
            long_signals.append(f"Fiyat Bollinger alt bandina yakin (%B={pb:.2f})")
        elif pb > 1.05:
            score -= 10; bear_count += 1
            short_signals.append(f"Fiyat Bollinger ust bandinin ustunde (%B={pb:.2f})")
        elif pb > 0.85:
            score -= 4
            short_signals.append(f"Fiyat Bollinger ust bandina yakin (%B={pb:.2f})")
        # Bollinger sıkışması — kırılım öncesi sessizlik
        bw = bollinger.get("bandwidth")
        if bw is not None and bw < 5.0:
            long_signals.append(f"Bollinger sikismasi (%{bw:.1f}) — kirilim olasiligi yuksek")

    # ── EMA Crossover ─────────────────────────────────────────────────────────
    if ema_crossover is not None:
        if ema_crossover == "GOLDEN_CROSS":
            score += 10; bull_count += 1
            long_signals.append("EMA 20/50 Altin Kesisim — guclu yukselis sinyali")
        elif ema_crossover == "DEATH_CROSS":
            score -= 10; bear_count += 1
            short_signals.append("EMA 20/50 Olum Kesisimi — guclu dusus sinyali")
        elif ema_crossover == "BULLISH":
            score += 2
        elif ema_crossover == "BEARISH":
            score -= 2

    # ── Trend Strength ────────────────────────────────────────────────────────
    if trend_strength is not None:
        if trend_strength > 8:
            score += 6; bull_count += 1
            long_signals.append(f"Guclu yukselis trendi (EMA'dan %{trend_strength:.1f} yukarida)")
        elif trend_strength > 3:
            score += 2
        elif trend_strength < -8:
            score -= 6; bear_count += 1
            short_signals.append(f"Guclu dusus trendi (EMA'dan %{abs(trend_strength):.1f} asagida)")
        elif trend_strength < -3:
            score -= 2

    # ── Hacim ─────────────────────────────────────────────────────────────────
    if volume_ratio > 2.0:
        if bull_count >= 2:
            score += 8; long_signals.append(f"Hacim cok guclu + sinyal destegi ({volume_ratio:.1f}x)")
        elif bear_count >= 2:
            score -= 8; short_signals.append(f"Hacim guclu + dusus sinyalleri ({volume_ratio:.1f}x)")
        else:
            score += 2; long_signals.append(f"Hacim ortalamanin {volume_ratio:.1f}x ustunde")
    elif volume_ratio > 1.3:
        score += 2; long_signals.append(f"Hacim ortalamanin {volume_ratio:.1f}x ustunde")
    elif volume_ratio < 0.4:
        score -= 3; short_signals.append("Hacim cok zayif — trend onaylanmiyor")

    # ── Williams %R ───────────────────────────────────────────────────────────
    if williams_r is not None:
        if williams_r <= -80:
            score += 8; bull_count += 1
            long_signals.append(f"Williams %R asiri satim ({williams_r:.1f}) — alim firsat bolgesi")
        elif williams_r <= -60:
            score += 3
            long_signals.append(f"Williams %R dusuk ({williams_r:.1f}) — satici baskisi azaliyor")
        elif williams_r >= -10:
            score -= 8; bear_count += 1
            short_signals.append(f"Williams %R asiri alim ({williams_r:.1f}) — satis baskisi artabilir")
        elif williams_r >= -30:
            score -= 3
            short_signals.append(f"Williams %R yuksek ({williams_r:.1f}) — dikkatli olun")

    # ── CCI ───────────────────────────────────────────────────────────────────
    if cci is not None:
        if cci < -150:
            score += 8; bull_count += 1
            long_signals.append(f"CCI cok asiri satim ({cci:.0f}) — güçlü geri donüs sinyali")
        elif cci < -100:
            score += 5; bull_count += 1
            long_signals.append(f"CCI asiri satim ({cci:.0f})")
        elif cci > 200:
            score -= 8; bear_count += 1
            short_signals.append(f"CCI cok asiri alim ({cci:.0f}) — kar alma bolgesi")
        elif cci > 100:
            score -= 5; bear_count += 1
            short_signals.append(f"CCI asiri alim ({cci:.0f})")
        # Sıfır geçişi momentum sinyali
        elif -10 < cci < 10:
            long_signals.append("CCI sifir bölgesi — momentum sifirlanmis, yön belirsiz")

    # ── VWAP ──────────────────────────────────────────────────────────────────
    if vwap is not None and current_price > 0:
        vwap_diff_pct = (current_price - vwap) / vwap * 100
        if vwap_diff_pct > 3:
            score -= 3
            short_signals.append(f"Fiyat VWAP'in %{vwap_diff_pct:.1f} ustunde — ortalamaya donus riski")
        elif vwap_diff_pct < -3:
            score += 3; bull_count += 1
            long_signals.append(f"Fiyat VWAP'in %{abs(vwap_diff_pct):.1f} altinda — destek bolgesi")

    # ── Rate of Change (ROC) ──────────────────────────────────────────────────
    if roc is not None:
        if roc > 15:
            score += 4; long_signals.append(f"ROC guclu yukselis momentumu (%{roc:.1f})")
        elif roc > 5:
            score += 2
        elif roc < -15:
            score -= 4; short_signals.append(f"ROC guclu dusus momentumu (%{roc:.1f})")
        elif roc < -5:
            score -= 2

    # ── Ichimoku Cloud ────────────────────────────────────────────────────────
    if ichimoku is not None:
        cloud_sig = ichimoku.get("cloud_signal")
        tk_cross  = ichimoku.get("tk_cross")

        if cloud_sig == "ABOVE_CLOUD":
            score += 8; bull_count += 1
            long_signals.append("Ichimoku: Fiyat bulutun ustunde — guclu yukselis trendi")
        elif cloud_sig == "BELOW_CLOUD":
            score -= 8; bear_count += 1
            short_signals.append("Ichimoku: Fiyat bulutun altinda — guclu dusus trendi")
        elif cloud_sig == "INSIDE_CLOUD":
            long_signals.append("Ichimoku: Fiyat bulut icinde — kararsizlik bolgesi")

        if tk_cross == "BULLISH":
            score += 5; bull_count += 1
            long_signals.append("Ichimoku TK kesisimi (boğa): Tenkan, Kijun'u kesti — alim sinyali")
        elif tk_cross == "BEARISH":
            score -= 5; bear_count += 1
            short_signals.append("Ichimoku TK kesisimi (ayi): Tenkan, Kijun'u aşagi kesti — satis sinyali")

    # ── Diverjans ─────────────────────────────────────────────────────────────
    if divergence is not None:
        div_type = divergence.get("divergence")
        desc     = divergence.get("description", "")
        if div_type == "BULLISH_DIVERGENCE":
            score += 12; bull_count += 1
            long_signals.append(f"DIVERJANS ALIM: {desc}")
        elif div_type == "BEARISH_DIVERGENCE":
            score -= 12; bear_count += 1
            short_signals.append(f"DIVERJANS SATIS: {desc}")

    # ── Bilanço ───────────────────────────────────────────────────────────────
    if balance_status == "Pozitif":
        score += 5; long_signals.append("Bilanco pozitif (forwardEPS > trailingEPS)")
    elif balance_status == "Negatif":
        score -= 6; short_signals.append("Bilanco negatif (forwardEPS < trailingEPS)")

    # ── Yakınsama Bonusu ──────────────────────────────────────────────────────
    # 4+ boğa sinyali güçlü senaryo → ekstra puan
    if bull_count >= 5:
        score += 7; long_signals.append(f"Guclu yakinlasma: {bull_count} yukselis sinyali ayni anda")
    elif bull_count >= 4:
        score += 5; long_signals.append(f"Yakinlasma: {bull_count} yukselis sinyali")
    elif bull_count >= 3:
        score += 3
    elif bear_count >= 5:
        score -= 7; short_signals.append(f"Guclu yakinlasma: {bear_count} dusus sinyali ayni anda")
    elif bear_count >= 4:
        score -= 5; short_signals.append(f"Yakinlasma: {bear_count} dusus sinyali")
    elif bear_count >= 3:
        score -= 3

    # ── Seans Düzeltmesi ─────────────────────────────────────────────────────
    base_score_clamped = max(0, min(100, score))
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
        final_score = int(round(0.70 * base_score_clamped + 0.30 * session_adj))

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

    final_score = max(0, min(100, final_score))
    return final_score, long_signals, short_signals


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
    """ATR destekli risk seviyesi."""
    vel = abs(price_velocity)
    atr = atr_pct or 0.0
    # ATR varsa ağırlıklı değerlendirme
    risk_score = max(vel, atr)
    if risk_score > 6:
        return "Cok Yuksek"
    elif risk_score > 3.5:
        return "Yuksek"
    elif risk_score > 1.5:
        return "Orta"
    return "Dusuk"
