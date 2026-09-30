"""
OptiTrade — Market Regime Scanner (Tarama Katmanı)
====================================================
Verilen sembol listesini tarar, her sembol için son N günlük getiri ve
volatilite verisinden bir piyasa rejimi (TRENDING_BULL / TRENDING_BEAR /
RANGE_BOUND / CHOPPY_NO_OPPORTUNITY) belirler ve fırsat barındırmayan
sembolleri bir sonraki aşamaya geçmeden eler.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    RANGE_BOUND = "RANGE_BOUND"
    CHOPPY_NO_OPPORTUNITY = "CHOPPY_NO_OPPORTUNITY"


@dataclass
class ScannedSymbol:
    """Tek bir sembol için rejim tespiti sonucu."""

    symbol: str
    regime: MarketRegime
    cumulative_return_pct: float
    annualized_volatility_pct: float
    trend_strength_r2: float
    last_close: float


class MarketRegimeScanner:
    """Sembol listesini tarayıp piyasa rejimini belirleyen ve filtreleyen katman.

    Sınıflandırma, son ``lookback_days`` günlük kapanış fiyatlarından türetilen
    üç metriğe dayanır:

    - **Kümülatif getiri**: dönem başı/sonu kapanış farkı (%).
    - **Yıllıklaştırılmış volatilite**: günlük getirilerin std sapması * sqrt(252).
    - **Trend gücü (R²)**: kapanış fiyatlarına uydurulan lineer regresyonun
      belirlilik katsayısı — 1'e yakınsa net bir trend, düşükse yatay/gürültülü
      hareket anlamına gelir.

    Bu üçünün birleşimiyle her sembol dört rejimden birine atanır; sadece
    ``CHOPPY_NO_OPPORTUNITY`` (net yön yok + düşük volatilite → tradable
    olmayan gürültü) sonraki aşamadan elenir.
    """

    def __init__(
        self,
        lookback_days: int = 60,
        trend_return_threshold_pct: float = 8.0,
        trend_r2_threshold: float = 0.5,
        min_volatility_pct: float = 5.0,
    ) -> None:
        self.lookback_days = lookback_days
        self.trend_return_threshold_pct = trend_return_threshold_pct
        self.trend_r2_threshold = trend_r2_threshold
        self.min_volatility_pct = min_volatility_pct

    def scan(self, symbols: List[str]) -> List[ScannedSymbol]:
        """Tüm sembolleri tarar ve rejim etiketiyle birlikte döner (fırsatsız olanlar dahil)."""
        history = self._fetch_batch_history(symbols)
        results: List[ScannedSymbol] = []

        for symbol in symbols:
            closes = self._extract_closes(history, symbol)
            min_required = max(20, self.lookback_days // 2)
            if closes is None or len(closes) < min_required:
                logger.warning(f"{symbol}: yetersiz veri, taramadan atlanıyor")
                continue
            results.append(self._classify_symbol(symbol, closes))

        return results

    def scan_and_filter(self, symbols: List[str]) -> List[ScannedSymbol]:
        """``scan()`` sonucundan fırsat barındırmayan (CHOPPY) sembolleri eler."""
        return [s for s in self.scan(symbols) if s.regime != MarketRegime.CHOPPY_NO_OPPORTUNITY]

    def _fetch_batch_history(self, symbols: List[str]) -> pd.DataFrame:
        period_days = max(self.lookback_days * 2, 90)
        return yf.download(
            tickers=" ".join(symbols),
            period=f"{period_days}d",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

    @staticmethod
    def _extract_closes(history: pd.DataFrame, symbol: str) -> Optional[pd.Series]:
        try:
            closes = (
                history[symbol]["Close"].dropna()
                if isinstance(history.columns, pd.MultiIndex)
                else history["Close"].dropna()
            )
        except (KeyError, TypeError):
            return None
        return closes if not closes.empty else None

    def _classify_symbol(self, symbol: str, closes: pd.Series) -> ScannedSymbol:
        closes = closes.tail(self.lookback_days)
        cumulative_return_pct = float((closes.iloc[-1] / closes.iloc[0] - 1.0) * 100)

        daily_returns = closes.pct_change().dropna()
        annualized_volatility_pct = (
            float(daily_returns.std() * np.sqrt(252) * 100) if not daily_returns.empty else 0.0
        )

        r2 = self._trend_strength_r2(closes)

        if r2 >= self.trend_r2_threshold and abs(cumulative_return_pct) >= self.trend_return_threshold_pct:
            regime = MarketRegime.TRENDING_BULL if cumulative_return_pct > 0 else MarketRegime.TRENDING_BEAR
        elif annualized_volatility_pct >= self.min_volatility_pct:
            regime = MarketRegime.RANGE_BOUND
        else:
            regime = MarketRegime.CHOPPY_NO_OPPORTUNITY

        return ScannedSymbol(
            symbol=symbol,
            regime=regime,
            cumulative_return_pct=round(cumulative_return_pct, 2),
            annualized_volatility_pct=round(annualized_volatility_pct, 2),
            trend_strength_r2=round(r2, 3),
            last_close=float(closes.iloc[-1]),
        )

    @staticmethod
    def _trend_strength_r2(closes: pd.Series) -> float:
        """Kapanış serisine uydurulan lineer regresyonun R² (belirlilik katsayısı) değeri."""
        y = closes.to_numpy(dtype=float)
        if len(y) < 3 or np.all(y == y[0]):
            return 0.0

        x = np.arange(len(y), dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        y_pred = slope * x + intercept

        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        return float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
