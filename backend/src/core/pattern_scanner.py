"""
OptiTrade — Pattern Scanner (Grafik ve Formasyon Tarayıcısı)
================================================================
Zaten çekilmiş 1D/1H OHLC verisi üzerinde kritik mum formasyonlarını
(Bullish/Bearish Engulfing, Hammer, Shooting Star, Doji) ve Destek/Direnç
yakınlığını tespit eder.

NOT: Formasyon tespiti TA-Lib'e (``pandas_ta.cdl_pattern``) DEĞİL, ATR ile
normalize edilmiş, bağımsız geometrik kurallara dayanır. Gerekçe: TA-Lib bir
C kütüphanesi derlemesi gerektirir (bu ortamda kurulu değil, kurulumu
kırılgan ve root yetkisi ister — Docker imajını da etkiler), ve istenen 4
formasyon zaten iyi tanımlı, basit mum gövdesi/fitil oranı kurallarıyla
güvenilir şekilde tespit edilebiliyor.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

if not hasattr(np, "NaN"):
    # mtf_analyzer.py'deki aynı pandas_ta/numpy uyumluluk notu geçerli.
    np.NaN = np.nan  # type: ignore[attr-defined]

import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


class PatternScanner:
    """Hazır OHLC verisinde mum formasyonu ve Destek/Direnç yakınlığı tarayıcısı.

    Bilerek kendi veri çekmiyor: ``MultiTimeframeAnalyzer`` zaten hem günlük
    hem saatlik veriyi çekiyor; aynı DataFrame'lerin burada yeniden
    kullanılması yfinance'e (ve Yahoo'nun rate-limit'ine) gereksiz ikinci bir
    istek atılmasını önlüyor.

    Basitleştirme notu: Hammer/Shooting Star tespiti klasik tanımlardaki gibi
    önceki trend yönü şartını (ör. "düşüş sonrası Hammer") aramaz — sadece
    mumun geometrik şeklini değerlendirir. Trend bağlamı zaten
    ``MultiTimeframeAnalyzer``'ın makro/mikro trend alanlarında ayrıca
    mevcut; AI persona ikisini birlikte yorumlar.
    """

    def __init__(self, support_resistance_lookback_days: int = 30) -> None:
        self.support_resistance_lookback_days = support_resistance_lookback_days

    def scan(
        self,
        daily_df: Optional[pd.DataFrame],
        hourly_df: Optional[pd.DataFrame],
    ) -> Dict[str, Any]:
        """Günlük ve saatlik veriden formasyon + Destek/Direnç yakınlığı özeti üretir."""
        active_patterns: List[str] = []

        if daily_df is not None and len(daily_df) >= 2:
            active_patterns += [f"{p} (1D)" for p in self._detect_patterns(daily_df)]
        if hourly_df is not None and len(hourly_df) >= 2:
            active_patterns += [f"{p} (1H)" for p in self._detect_patterns(hourly_df)]

        support_pct, resistance_pct = self._support_resistance_proximity(daily_df)

        return {
            "active_patterns": active_patterns,
            "support_proximity_pct": support_pct,
            "resistance_proximity_pct": resistance_pct,
        }

    def _detect_patterns(self, df: pd.DataFrame) -> List[str]:
        """Son muma göre formasyon tespiti; birden fazla formasyon aynı anda eşleşebilir."""
        atr = ta.atr(df["High"], df["Low"], df["Close"], length=14)
        if atr is None or atr.empty or pd.isna(atr.iloc[-1]) or atr.iloc[-1] <= 0:
            return []
        last_atr = float(atr.iloc[-1])

        o, h, l, c = (float(df[col].iloc[-1]) for col in ("Open", "High", "Low", "Close"))
        body = abs(c - o)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l

        patterns: List[str] = []

        # Doji — açılış/kapanış neredeyse eşit (gövde, ATR'nin çok küçük bir parçası).
        # Diğer formasyonlarla çakışmaması için önce kontrol edilir.
        is_doji = body <= 0.1 * last_atr
        if is_doji:
            patterns.append("Doji")
        else:
            # Hammer — küçük gövde üstte; uzun alt fitil (gövdenin en az 2 katı), kısa üst fitil.
            if lower_wick >= 2 * body and upper_wick <= body:
                patterns.append("Hammer")
            # Shooting Star — küçük gövde altta; uzun üst fitil, kısa alt fitil.
            if upper_wick >= 2 * body and lower_wick <= body:
                patterns.append("Shooting Star")

        # Engulfing formasyonları için son 2 muma bakılır.
        if len(df) >= 2:
            po, pc = float(df["Open"].iloc[-2]), float(df["Close"].iloc[-2])
            prev_bearish = pc < po
            prev_bullish = pc > po
            curr_bullish = c > o
            curr_bearish = c < o

            if curr_bullish and prev_bearish and o <= pc and c >= po:
                patterns.append("Bullish Engulfing")
            if curr_bearish and prev_bullish and o >= pc and c <= po:
                patterns.append("Bearish Engulfing")

        return patterns

    def _support_resistance_proximity(
        self, daily_df: Optional[pd.DataFrame]
    ) -> Tuple[Optional[float], Optional[float]]:
        """Son N günlük Destek (min Low) ve Direnç (max High) seviyelerine yüzdesel uzaklık."""
        if daily_df is None or daily_df.empty:
            return None, None

        window = daily_df.tail(self.support_resistance_lookback_days)
        if window.empty:
            return None, None

        support = float(window["Low"].min())
        resistance = float(window["High"].max())
        current_price = float(daily_df["Close"].iloc[-1])

        if support <= 0 or resistance <= 0 or current_price <= 0:
            return None, None

        support_pct = round((current_price - support) / current_price * 100, 2)
        resistance_pct = round((resistance - current_price) / current_price * 100, 2)
        return support_pct, resistance_pct
