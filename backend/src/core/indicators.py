"""
OptiTrade — Technical Indicators
==================================
Tüm hesaplamalar saf pandas/numpy ile, harici TA kütüphanesi yok.
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Mevcut Temel Göstergeler
# ─────────────────────────────────────────────────────────────────────────────

def calculate_rsi(prices: pd.Series, period: int = 14) -> Optional[float]:
    if len(prices) < period + 1:
        return None
    delta    = prices.diff()
    gain     = delta.where(delta > 0, 0.0)
    loss     = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    rsi      = 100 - (100 / (1 + rs))
    v = rsi.iloc[-1]
    return float(v) if not pd.isna(v) else None


def calculate_macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if len(prices) < slow + signal:
        return None, None, None
    ema_fast    = prices.ewm(span=fast, adjust=False).mean()
    ema_slow    = prices.ewm(span=slow, adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram   = macd_line - signal_line
    return (
        float(macd_line.iloc[-1]),
        float(signal_line.iloc[-1]),
        float(histogram.iloc[-1]),
    )


def calculate_bollinger_bands(
    prices: pd.Series, period: int = 20, std_dev: float = 2.0
) -> Dict[str, Optional[float]]:
    if len(prices) < period:
        return {"upper": None, "middle": None, "lower": None, "percent_b": None, "bandwidth": None}
    sma        = prices.rolling(window=period).mean()
    std        = prices.rolling(window=period).std()
    upper      = sma + (std * std_dev)
    lower      = sma - (std * std_dev)
    current    = float(prices.iloc[-1])
    upper_val  = float(upper.iloc[-1])
    lower_val  = float(lower.iloc[-1])
    middle_val = float(sma.iloc[-1])
    band_width = upper_val - lower_val
    percent_b  = (current - lower_val) / band_width if band_width > 0 else 0.5
    # Bandwidth — Bollinger sıkışması tespiti
    bandwidth  = (band_width / middle_val * 100) if middle_val != 0 else None
    return {
        "upper":     upper_val,
        "middle":    middle_val,
        "lower":     lower_val,
        "percent_b": percent_b,
        "bandwidth": round(bandwidth, 3) if bandwidth else None,
    }


def calculate_ema_crossover(
    prices: pd.Series, fast: int = 20, slow: int = 50
) -> Optional[str]:
    if len(prices) < slow:
        return None
    ema_fast     = prices.ewm(span=fast, adjust=False).mean()
    ema_slow     = prices.ewm(span=slow, adjust=False).mean()
    current_diff = float(ema_fast.iloc[-1] - ema_slow.iloc[-1])
    prev_diff    = float(ema_fast.iloc[-2] - ema_slow.iloc[-2])
    if current_diff > 0 and prev_diff <= 0:
        return "GOLDEN_CROSS"
    elif current_diff < 0 and prev_diff >= 0:
        return "DEATH_CROSS"
    elif current_diff > 0:
        return "BULLISH"
    else:
        return "BEARISH"


def calculate_trend_strength(prices: pd.Series, period: int = 20) -> Optional[float]:
    if len(prices) < period:
        return None
    ema     = prices.ewm(span=period, adjust=False).mean()
    current = float(prices.iloc[-1])
    ema_val = float(ema.iloc[-1])
    if ema_val == 0:
        return 0.0
    return ((current - ema_val) / ema_val) * 100


def calculate_price_velocity(current: float, open_price: float) -> float:
    if open_price == 0:
        return 0.0
    return ((current - open_price) / open_price) * 100


def calculate_volume_ratio(current_volume: float, avg_volume: float) -> float:
    if avg_volume == 0:
        return 1.0
    return current_volume / avg_volume


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Yeni Göstergeler
# ─────────────────────────────────────────────────────────────────────────────

def calculate_williams_r(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> Optional[float]:
    """
    Williams %R  ∈ [-100, 0]
    -80 ile -100 arası → aşırı satım (ALIŞ)
    -20 ile  0   arası → aşırı alım  (SATIŞ)
    """
    if len(close) < period:
        return None
    highest_high = high.rolling(period).max()
    lowest_low   = low.rolling(period).min()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    wr    = ((highest_high - close) / denom * -100)
    v = wr.iloc[-1]
    return round(float(v), 2) if not np.isnan(v) else None


def calculate_cci(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
) -> Optional[float]:
    """
    Commodity Channel Index
    > +100 → aşırı alım (SATIŞ)
    < -100 → aşırı satım (ALIŞ)
    """
    if len(close) < period:
        return None
    typical = (high + low + close) / 3
    sma     = typical.rolling(period).mean()
    mad     = typical.rolling(period).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    cci     = (typical - sma) / (0.015 * mad.replace(0, np.nan))
    v = cci.iloc[-1]
    return round(float(v), 2) if not np.isnan(v) else None


def calculate_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> Optional[float]:
    """
    VWAP (Volume Weighted Average Price) — intraday proxy kullanır.
    Fiyatın VWAP'a göre pozisyonu trend teyidi sağlar.
    Döndürür: vwap değeri ve fiyat farkı %
    """
    if len(close) < 2 or volume.sum() == 0:
        return None
    typical = (high + low + close) / 3
    cum_vp  = (typical * volume).cumsum()
    cum_v   = volume.cumsum().replace(0, np.nan)
    vwap    = cum_vp / cum_v
    v = vwap.iloc[-1]
    return round(float(v), 6) if not np.isnan(v) else None


def calculate_roc(prices: pd.Series, period: int = 10) -> Optional[float]:
    """
    Rate of Change (%)  = (close - close_n) / close_n × 100
    Momentum ölçüsü: yükseliş ivmesi tespiti.
    """
    if len(prices) < period + 1:
        return None
    current = float(prices.iloc[-1])
    past    = float(prices.iloc[-period - 1])
    if past == 0:
        return None
    return round((current - past) / past * 100, 3)


def calculate_ichimoku(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> Dict[str, Optional[float]]:
    """
    Ichimoku Kinkō Hyō — temel bileşenler:
      tenkan_sen  : (9-günlük max + min) / 2  → Dönüş Çizgisi
      kijun_sen   : (26-günlük max + min) / 2 → Temel Çizgi
      senkou_a    : (tenkan + kijun) / 2       → Bulut üst sınırı (26 gün ileri)
      senkou_b    : (52-günlük max + min) / 2  → Bulut alt sınırı (26 gün ileri)
      chikou_span : mevcut kapanış 26 gün geri

    Döndürür: mevcut değerler + sinyal durumu
    """
    result: Dict[str, Optional[float]] = {
        "tenkan_sen": None,
        "kijun_sen":  None,
        "senkou_a":   None,
        "senkou_b":   None,
        "cloud_signal": None,   # "ABOVE_CLOUD" | "BELOW_CLOUD" | "INSIDE_CLOUD"
        "tk_cross":    None,    # "BULLISH" | "BEARISH" | "NEUTRAL"
    }
    if len(close) < 52:
        return result

    def midpoint(s_high, s_low, n):
        return (s_high.rolling(n).max() + s_low.rolling(n).min()) / 2

    tenkan = midpoint(high, low, 9)
    kijun  = midpoint(high, low, 26)
    span_a = (tenkan + kijun) / 2
    span_b = midpoint(high, low, 52)

    tenkan_v = float(tenkan.iloc[-1]) if not np.isnan(tenkan.iloc[-1]) else None
    kijun_v  = float(kijun.iloc[-1])  if not np.isnan(kijun.iloc[-1])  else None
    span_a_v = float(span_a.iloc[-1]) if not np.isnan(span_a.iloc[-1]) else None
    span_b_v = float(span_b.iloc[-1]) if not np.isnan(span_b.iloc[-1]) else None

    result["tenkan_sen"] = round(tenkan_v, 6) if tenkan_v else None
    result["kijun_sen"]  = round(kijun_v, 6)  if kijun_v  else None
    result["senkou_a"]   = round(span_a_v, 6) if span_a_v else None
    result["senkou_b"]   = round(span_b_v, 6) if span_b_v else None

    # Fiyatın bulut konumu
    current = float(close.iloc[-1])
    if span_a_v and span_b_v:
        cloud_top    = max(span_a_v, span_b_v)
        cloud_bottom = min(span_a_v, span_b_v)
        if current > cloud_top:
            result["cloud_signal"] = "ABOVE_CLOUD"    # güçlü yükseliş
        elif current < cloud_bottom:
            result["cloud_signal"] = "BELOW_CLOUD"    # güçlü düşüş
        else:
            result["cloud_signal"] = "INSIDE_CLOUD"   # kararsızlık

    # TK Cross
    if tenkan_v and kijun_v:
        if len(tenkan) >= 2 and len(kijun) >= 2:
            prev_t = float(tenkan.iloc[-2])
            prev_k = float(kijun.iloc[-2])
            if tenkan_v > kijun_v and prev_t <= prev_k:
                result["tk_cross"] = "BULLISH"   # altın kesişim (küçük)
            elif tenkan_v < kijun_v and prev_t >= prev_k:
                result["tk_cross"] = "BEARISH"   # ölüm kesişimi (küçük)
            else:
                result["tk_cross"] = "NEUTRAL"

    return result


def calculate_divergence(
    prices: pd.Series,
    rsi_series: pd.Series,
    lookback: int = 20,
) -> Dict[str, Optional[str]]:
    """
    Fiyat–RSI Diverjans Tespiti (son lookback mum).
    Bullish Divergence  : fiyat düşük dip yaparken RSI yüksek dip → potansiyel dönüş yukarı
    Bearish Divergence  : fiyat yüksek tepe yaparken RSI düşük tepe → potansiyel dönüş aşağı
    """
    result = {"divergence": None, "description": None}
    if len(prices) < lookback or len(rsi_series) < lookback:
        return result

    p   = prices.iloc[-lookback:].values
    r   = rsi_series.iloc[-lookback:].values
    n   = len(p)

    # Son iki dip/tepe noktası bul (basit yerel ekstremum)
    def local_mins(arr):
        idx = [i for i in range(1, n-1) if arr[i] < arr[i-1] and arr[i] < arr[i+1]]
        return idx

    def local_maxs(arr):
        idx = [i for i in range(1, n-1) if arr[i] > arr[i-1] and arr[i] > arr[i+1]]
        return idx

    price_mins = local_mins(p)
    price_maxs = local_maxs(p)
    rsi_mins   = local_mins(r)
    rsi_maxs   = local_maxs(r)

    # Bullish: son 2 fiyat dibi düşüyor, son 2 RSI dibi yükseliyor
    if len(price_mins) >= 2 and len(rsi_mins) >= 2:
        pm1, pm2 = price_mins[-2], price_mins[-1]
        rm1, rm2 = rsi_mins[-2],   rsi_mins[-1]
        if p[pm2] < p[pm1] and r[rm2] > r[rm1]:
            result["divergence"]   = "BULLISH_DIVERGENCE"
            result["description"]  = "Boğa diverjansı: fiyat yeni dip yaparken RSI yüksek dip — potansiyel yukarı dönüş"

    # Bearish: son 2 fiyat tepesi yükseliyor, son 2 RSI tepesi düşüyor
    if len(price_maxs) >= 2 and len(rsi_maxs) >= 2:
        pm1, pm2 = price_maxs[-2], price_maxs[-1]
        rm1, rm2 = rsi_maxs[-2],   rsi_maxs[-1]
        if p[pm2] > p[pm1] and r[rm2] < r[rm1]:
            result["divergence"]   = "BEARISH_DIVERGENCE"
            result["description"]  = "Ayı diverjansı: fiyat yeni tepe yaparken RSI düşük tepe — potansiyel aşağı dönüş"

    return result


def calculate_rsi_series(prices: pd.Series, period: int = 14) -> pd.Series:
    """Diverjans hesabı için tam RSI serisi döndür."""
    delta    = prices.diff()
    gain     = delta.where(delta > 0, 0.0)
    loss     = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))
