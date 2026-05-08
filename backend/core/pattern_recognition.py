"""
OptiTrade — Pattern Recognition Engine
========================================
Mum formasyonları, destek/direnç seviyeleri ve Fibonacci hesaplama.
Tüm fonksiyonlar pandas Series alır, sözlük/sayı döndürür.
"""
from __future__ import annotations
import math
from typing import Optional, List, Dict
import pandas as pd
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Mum Formasyonları  (Candlestick Patterns)
# ─────────────────────────────────────────────────────────────────────────────

def detect_patterns(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: Optional[pd.Series] = None,
) -> Dict:
    """
    Son 3 mumu inceleyerek bulunan formasyonları ve güç skorunu döndürür.
    Döndürür:
      patterns   : List[str]  — bulunan formasyon adları
      score_delta: int        — pozitif=bullish, negatif=bearish eklentisi
      signals    : List[str]  — Türkçe açıklama
    """
    if len(close) < 3:
        return {"patterns": [], "score_delta": 0, "signals": []}

    o1, o2, o3 = float(open_.iloc[-3]), float(open_.iloc[-2]), float(open_.iloc[-1])
    h1, h2, h3 = float(high.iloc[-3]),  float(high.iloc[-2]),  float(high.iloc[-1])
    l1, l2, l3 = float(low.iloc[-3]),   float(low.iloc[-2]),   float(low.iloc[-1])
    c1, c2, c3 = float(close.iloc[-3]), float(close.iloc[-2]), float(close.iloc[-1])

    body3 = abs(c3 - o3)
    range3 = h3 - l3 if h3 != l3 else 1e-9
    body_ratio3 = body3 / range3
    upper_shadow3 = h3 - max(c3, o3)
    lower_shadow3 = min(c3, o3) - l3

    patterns: List[str] = []
    signals:  List[str] = []
    delta = 0

    # ── Tek Mum Formasyonları ──────────────────────────────────────────────────

    # Doji (gövde çok küçük)
    if body_ratio3 < 0.05:
        patterns.append("DOJI")
        signals.append("Doji: Kararsızlık, trend dönüşü gözlemleyin")

    # Hammer (çekiç) — bullish
    elif (c3 > o3 and lower_shadow3 >= 2 * body3
          and upper_shadow3 <= 0.1 * range3):
        patterns.append("HAMMER")
        delta += 8
        signals.append("Çekiç (Hammer): Güçlü dip sinyali — potansiyel yükseliş")

    # Inverted Hammer — bullish
    elif (c3 > o3 and upper_shadow3 >= 2 * body3
          and lower_shadow3 <= 0.1 * range3):
        patterns.append("INVERTED_HAMMER")
        delta += 5
        signals.append("Ters Çekiç: Dip bölgede alıcı girişi sinyali")

    # Shooting Star — bearish
    elif (c3 < o3 and upper_shadow3 >= 2 * body3
          and lower_shadow3 <= 0.1 * range3):
        patterns.append("SHOOTING_STAR")
        delta -= 8
        signals.append("Düşen Yıldız (Shooting Star): Tepe bölgede satış sinyali")

    # Hanging Man — bearish
    elif (c3 < o3 and lower_shadow3 >= 2 * body3
          and upper_shadow3 <= 0.1 * range3):
        patterns.append("HANGING_MAN")
        delta -= 6
        signals.append("Asılan Adam: Yukarı trendde tehlike sinyali")

    # Marubozu (gölgesiz güçlü mum)
    elif body_ratio3 > 0.90:
        if c3 > o3:
            patterns.append("BULLISH_MARUBOZU")
            delta += 7
            signals.append("Boğa Marubozu: Güçlü alım baskısı, yükseliş momentum")
        else:
            patterns.append("BEARISH_MARUBOZU")
            delta -= 7
            signals.append("Ayı Marubozu: Güçlü satış baskısı, düşüş momentum")

    # Spinning Top (küçük gövde, iki taraflı gölge)
    elif (body_ratio3 < 0.30 and upper_shadow3 > body3 and lower_shadow3 > body3):
        patterns.append("SPINNING_TOP")
        signals.append("Dönen Tepe: Güç dengesi, yön kararı yakın")

    # ── İki Mum Formasyonları ──────────────────────────────────────────────────

    body2 = abs(c2 - o2)
    body3_v = abs(c3 - o3)

    # Bullish Engulfing
    if (c2 < o2 and c3 > o3
            and o3 <= c2 and c3 >= o2
            and body3_v > body2):
        patterns.append("BULLISH_ENGULFING")
        delta += 12
        signals.append("Yutan Boğa (Bullish Engulfing): Güçlü trend dönüşü — AL")

    # Bearish Engulfing
    elif (c2 > o2 and c3 < o3
              and o3 >= c2 and c3 <= o2
              and body3_v > body2):
        patterns.append("BEARISH_ENGULFING")
        delta -= 12
        signals.append("Yutan Ayı (Bearish Engulfing): Güçlü trend dönüşü — SAT")

    # Piercing Line (bullish)
    elif (c2 < o2 and c3 > o3
              and o3 < l2
              and c3 > (o2 + c2) / 2):
        patterns.append("PIERCING_LINE")
        delta += 8
        signals.append("Delici Çizgi: Ayı trendinde güçlü alıcı baskısı")

    # Dark Cloud Cover (bearish)
    elif (c2 > o2 and c3 < o3
              and o3 > h2
              and c3 < (o2 + c2) / 2):
        patterns.append("DARK_CLOUD_COVER")
        delta -= 8
        signals.append("Kara Bulut Örtüsü: Boğa trendinde güçlü satış baskısı")

    # ── Üç Mum Formasyonları ──────────────────────────────────────────────────

    # Morning Star (bullish)
    if (c1 < o1
            and abs(c2 - o2) < abs(c1 - o1) * 0.3
            and c3 > o3
            and c3 > (o1 + c1) / 2):
        patterns.append("MORNING_STAR")
        delta += 15
        signals.append("Sabah Yıldızı (Morning Star): Dip bölgede 3 mum dönüş formasyonu — Güçlü AL")

    # Evening Star (bearish)
    elif (c1 > o1
              and abs(c2 - o2) < abs(c1 - o1) * 0.3
              and c3 < o3
              and c3 < (o1 + c1) / 2):
        patterns.append("EVENING_STAR")
        delta -= 15
        signals.append("Akşam Yıldızı (Evening Star): Tepe bölgede 3 mum dönüş formasyonu — Güçlü SAT")

    # Three White Soldiers (güçlü yükseliş)
    if (c1 > o1 and c2 > o2 and c3 > o3
            and c2 > c1 and c3 > c2
            and o2 > o1 and o3 > o2):
        patterns.append("THREE_WHITE_SOLDIERS")
        delta += 14
        signals.append("Üç Beyaz Asker: Güçlü kademeli yükseliş trendi doğrulanıyor")

    # Three Black Crows (güçlü düşüş)
    elif (c1 < o1 and c2 < o2 and c3 < o3
              and c2 < c1 and c3 < c2
              and o2 < o1 and o3 < o2):
        patterns.append("THREE_BLACK_CROWS")
        delta -= 14
        signals.append("Üç Kara Karga: Güçlü kademeli düşüş trendi doğrulanıyor")

    return {
        "patterns":    patterns,
        "score_delta": delta,
        "signals":     signals,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Destek / Direnç Seviyeleri
# ─────────────────────────────────────────────────────────────────────────────

def find_support_resistance(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    n_levels: int = 5,
    window: int = 10,
) -> Dict:
    """
    Pivot noktaları kullanarak güçlü destek ve direnç seviyelerini bulur.
    Seviyeler yakın olanlar birleştirilir (%0.5 tolerans).
    """
    highs = high.values
    lows  = low.values
    pivot_highs: List[float] = []
    pivot_lows:  List[float] = []

    for i in range(window, len(highs) - window):
        if highs[i] == max(highs[i - window: i + window + 1]):
            pivot_highs.append(float(highs[i]))
        if lows[i] == min(lows[i - window: i + window + 1]):
            pivot_lows.append(float(lows[i]))

    def cluster(levels: List[float], tol: float = 0.005) -> List[float]:
        if not levels: return []
        sorted_lvl = sorted(levels)
        clusters: List[List[float]] = [[sorted_lvl[0]]]
        for v in sorted_lvl[1:]:
            if abs(v - clusters[-1][-1]) / clusters[-1][-1] <= tol:
                clusters[-1].append(v)
            else:
                clusters.append([v])
        return sorted([sum(c) / len(c) for c in clusters], key=lambda x: -len(
            [v for c in clusters for v in c if abs(v - x) / x <= tol
        ]))

    current = float(close.iloc[-1])
    resistance_levels = sorted(
        [r for r in cluster(pivot_highs) if r > current],
        key=lambda x: x
    )[:n_levels]
    support_levels = sorted(
        [s for s in cluster(pivot_lows) if s < current],
        key=lambda x: -x
    )[:n_levels]

    nearest_resistance = resistance_levels[0] if resistance_levels else None
    nearest_support    = support_levels[0]    if support_levels    else None

    dist_resistance = ((nearest_resistance - current) / current * 100
                       if nearest_resistance else None)
    dist_support    = ((current - nearest_support)    / current * 100
                       if nearest_support    else None)

    return {
        "current_price":       round(current, 4),
        "resistance_levels":   [round(r, 4) for r in resistance_levels],
        "support_levels":      [round(s, 4) for s in support_levels],
        "nearest_resistance":  round(nearest_resistance, 4) if nearest_resistance else None,
        "nearest_support":     round(nearest_support, 4)    if nearest_support    else None,
        "dist_to_resistance_pct": round(dist_resistance, 2) if dist_resistance else None,
        "dist_to_support_pct":    round(dist_support, 2)    if dist_support    else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Fibonacci Retracement
# ─────────────────────────────────────────────────────────────────────────────

FIB_RATIOS = [0.0, 0.236, 0.382, 0.500, 0.618, 0.786, 1.0]

def calculate_fibonacci(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int = 60,
) -> Dict:
    """
    Son `lookback` günün yüksek/düşüğünden Fibonacci seviyeleri hesaplar.
    Mevcut fiyatın hangi bölgede olduğunu ve güçlü destek/direnç konumunu döndürür.
    """
    window = high.iloc[-lookback:]
    swing_high = float(window.max())
    swing_low  = float(low.iloc[-lookback:].min())
    current    = float(close.iloc[-1])
    diff       = swing_high - swing_low

    levels = {f"fib_{int(r*1000)}": round(swing_low + diff * (1 - r), 4)
              for r in FIB_RATIOS}

    # Mevcut fiyatın hangi Fibonacci bölgesinde olduğunu bul
    level_prices = sorted(levels.values())
    zone = "Bilinmiyor"
    for i in range(len(level_prices) - 1):
        if level_prices[i] <= current <= level_prices[i + 1]:
            zone = f"{level_prices[i]:.4f} – {level_prices[i+1]:.4f}"
            break

    # En yakın Fibonacci desteği ve direnci
    below = [v for v in level_prices if v < current]
    above = [v for v in level_prices if v > current]
    fib_support    = max(below) if below else None
    fib_resistance = min(above) if above else None

    return {
        "swing_high":      round(swing_high, 4),
        "swing_low":       round(swing_low, 4),
        "levels":          levels,
        "current_zone":    zone,
        "fib_support":     round(fib_support, 4)    if fib_support    else None,
        "fib_resistance":  round(fib_resistance, 4) if fib_resistance else None,
        "dist_to_fib_support_pct":    round((current - fib_support) / current * 100, 2)    if fib_support    else None,
        "dist_to_fib_resistance_pct": round((fib_resistance - current) / current * 100, 2) if fib_resistance else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Ek Göstergeler
# ─────────────────────────────────────────────────────────────────────────────

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series,
                  period: int = 14) -> Optional[float]:
    """Average True Range — volatilite ölçüsü."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(com=period - 1, min_periods=period).mean()
    v = atr.iloc[-1]
    return float(v) if not np.isnan(v) else None


def calculate_stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
                          k_period: int = 14, d_period: int = 3
                          ) -> Dict[str, Optional[float]]:
    """Stochastic Oscillator (%K, %D)."""
    lowest  = low.rolling(k_period).min()
    highest = high.rolling(k_period).max()
    denom   = highest - lowest
    denom   = denom.replace(0, np.nan)
    k = ((close - lowest) / denom * 100).fillna(50)
    d = k.rolling(d_period).mean()
    kv = float(k.iloc[-1]) if not np.isnan(k.iloc[-1]) else None
    dv = float(d.iloc[-1]) if not np.isnan(d.iloc[-1]) else None
    return {"stoch_k": round(kv, 2) if kv else None,
            "stoch_d": round(dv, 2) if dv else None}


def calculate_obv(close: pd.Series, volume: pd.Series) -> Optional[float]:
    """On-Balance Volume — hacim momentum."""
    direction = np.sign(close.diff().fillna(0))
    obv = (direction * volume).cumsum()
    # Normalize: son değeri aylık ort. hacme oranla
    avg_vol = float(volume.mean())
    if avg_vol == 0:
        return None
    return round(float(obv.iloc[-1]) / avg_vol, 3)


def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series,
                  period: int = 14) -> Optional[float]:
    """Average Directional Index — trend gücü."""
    try:
        plus_dm  = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm  < 0] = 0
        minus_dm[minus_dm < 0] = 0
        plus_dm[plus_dm < minus_dm]  = 0
        minus_dm[minus_dm < plus_dm] = 0

        prev_close = close.shift(1)
        tr = pd.concat([high - low,
                        (high - prev_close).abs(),
                        (low  - prev_close).abs()], axis=1).max(axis=1)
        atr14    = tr.ewm(com=period - 1, min_periods=period).mean()
        plus_di  = 100 * plus_dm.ewm( com=period - 1, min_periods=period).mean() / atr14
        minus_di = 100 * minus_dm.ewm(com=period - 1, min_periods=period).mean() / atr14
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.ewm(com=period - 1, min_periods=period).mean()
        v = adx.iloc[-1]
        return round(float(v), 1) if not np.isnan(v) else None
    except Exception:
        return None
