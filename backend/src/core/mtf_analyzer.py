"""
OptiTrade — Multi-Timeframe Analyzer (Çoklu Zaman Dilimi Analiz Katmanı)
==========================================================================
Filtrelenen semboller için makro (1D/1W) trend yönü ve mikro (1H) giriş
sinyallerini birleştiren derin teknik özellik mühendisliği (feature
engineering). yfinance + pandas-ta kullanır. Ayrıca çekilen 1D/1H veriyi
``PatternScanner``'a devrederek mum formasyonları ve Destek/Direnç
yakınlığını da analiz sözlüğüne ekler.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import numpy as np

if not hasattr(np, "NaN"):
    # pandas_ta (0.3.14b0) imports `numpy.NaN` at module load time; numpy>=1.24
    # removed that alias (only `numpy.nan` remains). Restore it before the
    # pandas_ta import below runs — no-op on numpy versions where it still exists.
    np.NaN = np.nan  # type: ignore[attr-defined]

import pandas as pd
import pandas_ta as ta
import yfinance as yf

from core.pattern_scanner import PatternScanner

logger = logging.getLogger(__name__)


class MultiTimeframeAnalyzer:
    """Makro (1D/1W) trend ve mikro (1H) giriş sinyallerini birleştiren analiz katmanı.

    Makro katman: EMA 50/200 crossover ve Supertrend ile ana trend yönü.
    Mikro katman: RSI, MACD histogram, hacim patlaması ve Bollinger Squeeze
    ile hassas giriş zamanlaması sinyalleri.
    Formasyon katmanı: mum formasyonları ve Destek/Direnç yakınlığı
    (``PatternScanner``, zaten çekilmiş 1D/1H veri üzerinde — ekstra
    yfinance isteği atmaz).
    """

    def __init__(
        self,
        macro_period: str = "2y",
        micro_period: str = "60d",
        pattern_scanner: Optional[PatternScanner] = None,
    ) -> None:
        self.macro_period = macro_period
        self.micro_period = micro_period
        self.pattern_scanner = pattern_scanner or PatternScanner()

    def analyze(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Sembol için birleşik makro+mikro+formasyon analiz sözlüğünü döner; veri yetersizse None."""
        macro_df = self._fetch(symbol, period=self.macro_period, interval="1d")
        if macro_df is None or len(macro_df) < 210:
            logger.warning(f"{symbol}: makro veri yetersiz (EMA200 için en az ~210 gün gerekli)")
            return None

        micro_df = self._fetch(symbol, period=self.micro_period, interval="1h")
        if micro_df is None or len(micro_df) < 50:
            logger.warning(f"{symbol}: mikro (1H) veri yetersiz")
            return None

        macro = self._analyze_macro(macro_df)
        micro = self._analyze_micro(micro_df)
        patterns = self.pattern_scanner.scan(daily_df=macro_df, hourly_df=micro_df)

        return {
            "symbol": symbol,
            "current_price": float(macro_df["Close"].iloc[-1]),
            "atr_daily": macro["atr_daily"],
            "macro": macro,
            "micro": micro,
            "patterns": patterns,
        }

    @staticmethod
    def _fetch(symbol: str, period: str, interval: str) -> Optional[pd.DataFrame]:
        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval)
        except Exception as exc:
            logger.error(f"{symbol}: veri çekme hatası ({interval}): {exc}")
            return None
        return df.dropna() if df is not None and not df.empty else None

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

    def _analyze_micro(self, df: pd.DataFrame) -> Dict[str, Any]:
        """RSI, MACD histogram, hacim patlaması ve Bollinger Squeeze ile mikro giriş sinyalleri."""
        close = df["Close"]
        volume = df["Volume"]

        rsi = ta.rsi(close, length=14)
        macd = ta.macd(close, fast=12, slow=26, signal=9)
        bbands = ta.bbands(close, length=20, std=2.0)

        macd_hist_col = next(c for c in macd.columns if c.startswith("MACDh_"))
        macd_histogram = float(macd[macd_hist_col].iloc[-1])

        avg_volume_20 = float(volume.tail(20).mean())
        last_volume = float(volume.iloc[-1])
        volume_spike = bool(avg_volume_20 > 0 and last_volume > avg_volume_20 * 1.5)

        bb_upper_col = next(c for c in bbands.columns if c.startswith("BBU_"))
        bb_lower_col = next(c for c in bbands.columns if c.startswith("BBL_"))
        bandwidth = (bbands[bb_upper_col] - bbands[bb_lower_col]) / close
        bollinger_squeeze = bool(bandwidth.iloc[-1] < bandwidth.tail(60).quantile(0.2))

        return {
            "rsi_14": float(rsi.iloc[-1]),
            "macd_histogram": macd_histogram,
            "volume_spike": volume_spike,
            "volume_ratio": round(last_volume / avg_volume_20, 2) if avg_volume_20 > 0 else 0.0,
            "bollinger_squeeze": bollinger_squeeze,
        }
