"""
OptiTrade — Scoring Configuration
===================================
All scoring weights and thresholds live here.

Rules:
- scoring.py references ONLY these constants — no numeric literals.
- To tune any weight, change only this file.
- Never import scoring.py from here (keep the dependency unidirectional).
- Every constant maps to exactly one scoring decision in scoring.py.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorWeight:
    """Documents the theoretical max contribution of a single indicator."""
    name: str
    max_bullish: int    # max points added (strongest bullish condition)
    max_bearish: int    # max points subtracted — stored as positive int
    description: str


# ── Indicator registry ────────────────────────────────────────────────────────
# Source of truth for what each indicator can contribute at maximum.
# Used by the explainability layer to provide context ("this indicator
# can move the score by at most ±N points").

WEIGHTS: dict[str, IndicatorWeight] = {
    "potential_price": IndicatorWeight("Potansiyel Fiyat", 12, 12,
        "Mevcut fiyat ile hedef fiyat arasındaki sapma"),
    "rsi":             IndicatorWeight("RSI", 14, 14,
        "Relative Strength Index — aşırı alım/satım tespiti"),
    "macd":            IndicatorWeight("MACD", 6, 6,
        "MACD çizgisi ile sinyal çizgisi karşılaştırması"),
    "macd_histogram":  IndicatorWeight("MACD Histogram", 2, 2,
        "MACD histogram ivmesi — momentum hızlanması/yavaşlaması"),
    "bollinger":       IndicatorWeight("Bollinger Bands", 10, 10,
        "Fiyatın Bollinger Bandı içindeki konumu (%B)"),
    "ema_crossover":   IndicatorWeight("EMA Crossover", 10, 10,
        "EMA 20/50 Altın Kesişim / Ölüm Kesişimi"),
    "trend_strength":  IndicatorWeight("Trend Strength", 6, 6,
        "Fiyatın EMA'ya göre yüzdeli sapması"),
    "volume":          IndicatorWeight("Hacim", 8, 8,
        "Günlük hacim / aylık ortalama oranı ve yön onayı"),
    "williams_r":      IndicatorWeight("Williams %R", 8, 8,
        "Williams %R osilatörü — aşırı alım/satım"),
    "cci":             IndicatorWeight("CCI", 8, 8,
        "Commodity Channel Index — fiyat momentum ölçümü"),
    "vwap":            IndicatorWeight("VWAP", 3, 3,
        "Hacim ağırlıklı ortalama fiyata göre konumu"),
    "roc":             IndicatorWeight("ROC", 4, 4,
        "Rate of Change — 10 günlük fiyat değişim hızı"),
    "ichimoku":        IndicatorWeight("Ichimoku", 13, 13,
        "Ichimoku bulut konumu (±8) + TK kesişimi (±5)"),
    "divergence":      IndicatorWeight("Diverjans", 12, 12,
        "Fiyat-RSI uyumsuzluğu — güçlü dönüş sinyali"),
    "balance":         IndicatorWeight("Bilanço", 5, 6,
        "forwardEPS / trailingEPS karşılaştırması"),
    "convergence":     IndicatorWeight("Yakınsama Bonusu", 7, 7,
        "Birden fazla sinyalin aynı yönü göstermesi"),
    # ── Added in Step 0.2 ────────────────────────────────────────────────────
    "adx":             IndicatorWeight("ADX", 6, 6,
        "Average Directional Index — trend gücü onayı veya zayıflık cezası"),
    "stochastic":      IndicatorWeight("Stochastic", 8, 8,
        "Stochastic Oscillator (%K/%D) — aşırı alım/satım ve çaprazlama"),
}


# ══════════════════════════════════════════════════════════════════════════════
# Score deltas — one constant per scoring condition.
#
# Naming convention:
#   INDICATOR_CONDITION_DELTA  (positive = bullish, negative = bearish)
#   INDICATOR_CONDITION_THRESHOLD  (the boundary value that triggers the delta)
# ══════════════════════════════════════════════════════════════════════════════

# ── Score base and clamp ──────────────────────────────────────────────────────
SCORE_BASE = 50
SCORE_MIN  =  0
SCORE_MAX  = 100

# ── Potential Price ───────────────────────────────────────────────────────────
POTENTIAL_PRICE_STRONG_CHEAP_DELTA          =  12   # price/potential < 0.85
POTENTIAL_PRICE_CHEAP_DELTA                 =   4   # price/potential < 0.95
POTENTIAL_PRICE_EXPENSIVE_DELTA             =  -4   # price/potential > 1.02
POTENTIAL_PRICE_STRONG_EXPENSIVE_DELTA      = -12   # price/potential > 1.10

POTENTIAL_PRICE_STRONG_CHEAP_THRESHOLD      = 0.85
POTENTIAL_PRICE_CHEAP_THRESHOLD             = 0.95
POTENTIAL_PRICE_EXPENSIVE_THRESHOLD         = 1.02
POTENTIAL_PRICE_STRONG_EXPENSIVE_THRESHOLD  = 1.10

# ── RSI ───────────────────────────────────────────────────────────────────────
RSI_EXTREME_OVERSOLD_DELTA          =  14   # RSI < 20
RSI_OVERSOLD_DELTA                  =   8   # RSI < 30
RSI_MILD_OVERSOLD_DELTA             =   2   # RSI < 40
RSI_MILD_OVERBOUGHT_DELTA           =  -2   # RSI > 60
RSI_OVERBOUGHT_DELTA                =  -8   # RSI > 70
RSI_EXTREME_OVERBOUGHT_DELTA        = -14   # RSI > 80

RSI_EXTREME_OVERSOLD_THRESHOLD      =  20
RSI_OVERSOLD_THRESHOLD              =  30
RSI_MILD_OVERSOLD_THRESHOLD         =  40
RSI_MILD_OVERBOUGHT_THRESHOLD       =  60
RSI_OVERBOUGHT_THRESHOLD            =  70
RSI_EXTREME_OVERBOUGHT_THRESHOLD    =  80

# ── MACD ──────────────────────────────────────────────────────────────────────
MACD_BULLISH_DELTA          =   6
MACD_BEARISH_DELTA          =  -6
MACD_HIST_BULLISH_DELTA     =   2
MACD_HIST_BEARISH_DELTA     =  -2
MACD_HIST_MOMENTUM_RATIO    = 0.05   # histogram must exceed 5% of |macd| to fire

# ── Bollinger Bands ───────────────────────────────────────────────────────────
BB_BELOW_BAND_STRONG_DELTA  =  10   # %B < -0.05
BB_BELOW_BAND_MILD_DELTA    =   4   # %B <  0.15
BB_ABOVE_BAND_MILD_DELTA    =  -4   # %B >  0.85
BB_ABOVE_BAND_STRONG_DELTA  = -10   # %B >  1.05

BB_BELOW_STRONG_THRESHOLD   = -0.05
BB_BELOW_MILD_THRESHOLD     =  0.15
BB_ABOVE_MILD_THRESHOLD     =  0.85
BB_ABOVE_STRONG_THRESHOLD   =  1.05
BB_SQUEEZE_THRESHOLD        =  5.0   # bandwidth < this → squeeze alert

# ── EMA Crossover ─────────────────────────────────────────────────────────────
EMA_GOLDEN_CROSS_DELTA  =  10
EMA_DEATH_CROSS_DELTA   = -10
EMA_BULLISH_DELTA       =   2
EMA_BEARISH_DELTA       =  -2

# ── Trend Strength ────────────────────────────────────────────────────────────
TREND_STRONG_BULLISH_DELTA  =   6   # trend > 8
TREND_MILD_BULLISH_DELTA    =   2   # trend > 3
TREND_MILD_BEARISH_DELTA    =  -2   # trend < -3
TREND_STRONG_BEARISH_DELTA  =  -6   # trend < -8

TREND_STRONG_THRESHOLD  =  8
TREND_MILD_THRESHOLD    =  3

# ── Volume ────────────────────────────────────────────────────────────────────
VOLUME_STRONG_BULL_DELTA    =   8   # ratio > 2.0 + bull majority
VOLUME_STRONG_BEAR_DELTA    =  -8   # ratio > 2.0 + bear majority
VOLUME_STRONG_NEUTRAL_DELTA =   2   # ratio > 2.0, no clear direction
VOLUME_ABOVE_AVG_DELTA      =   2   # ratio > 1.3
VOLUME_WEAK_DELTA           =  -3   # ratio < 0.4

VOLUME_STRONG_THRESHOLD  = 2.0
VOLUME_ABOVE_THRESHOLD   = 1.3
VOLUME_WEAK_THRESHOLD    = 0.4

# ── Williams %R ───────────────────────────────────────────────────────────────
WILLIAMS_EXTREME_OVERSOLD_DELTA     =   8   # %R <= -80
WILLIAMS_OVERSOLD_DELTA             =   3   # %R <= -60
WILLIAMS_OVERBOUGHT_DELTA           =  -3   # %R >= -30
WILLIAMS_EXTREME_OVERBOUGHT_DELTA   =  -8   # %R >= -10

WILLIAMS_EXTREME_OVERSOLD_THRESHOLD     = -80
WILLIAMS_OVERSOLD_THRESHOLD             = -60
WILLIAMS_OVERBOUGHT_THRESHOLD           = -30
WILLIAMS_EXTREME_OVERBOUGHT_THRESHOLD   = -10

# ── CCI ───────────────────────────────────────────────────────────────────────
CCI_EXTREME_OVERSOLD_DELTA      =   8   # CCI < -150
CCI_OVERSOLD_DELTA              =   5   # CCI < -100
CCI_OVERBOUGHT_DELTA            =  -5   # CCI >  100
CCI_EXTREME_OVERBOUGHT_DELTA    =  -8   # CCI >  200

CCI_EXTREME_OVERSOLD_THRESHOLD  = -150
CCI_OVERSOLD_THRESHOLD          = -100
CCI_OVERBOUGHT_THRESHOLD        =  100
CCI_EXTREME_OVERBOUGHT_THRESHOLD =  200
CCI_ZERO_BAND                   =   10   # ±10 around zero → zero-cross note

# ── VWAP ──────────────────────────────────────────────────────────────────────
VWAP_ABOVE_DELTA        =  -3   # price > VWAP_THRESHOLD_PCT above VWAP
VWAP_BELOW_DELTA        =   3   # price > VWAP_THRESHOLD_PCT below VWAP
VWAP_THRESHOLD_PCT      =   3.0

# ── ROC ───────────────────────────────────────────────────────────────────────
ROC_STRONG_BULLISH_DELTA  =   4   # ROC > 15
ROC_MILD_BULLISH_DELTA    =   2   # ROC > 5
ROC_MILD_BEARISH_DELTA    =  -2   # ROC < -5
ROC_STRONG_BEARISH_DELTA  =  -4   # ROC < -15

ROC_STRONG_THRESHOLD  =  15
ROC_MILD_THRESHOLD    =   5

# ── Ichimoku ──────────────────────────────────────────────────────────────────
ICHIMOKU_ABOVE_CLOUD_DELTA  =   8
ICHIMOKU_BELOW_CLOUD_DELTA  =  -8
ICHIMOKU_TK_BULLISH_DELTA   =   5
ICHIMOKU_TK_BEARISH_DELTA   =  -5

# ── Divergence ────────────────────────────────────────────────────────────────
DIVERGENCE_BULLISH_DELTA  =  12
DIVERGENCE_BEARISH_DELTA  = -12

# ── Balance ───────────────────────────────────────────────────────────────────
BALANCE_POSITIVE_DELTA  =   5
BALANCE_NEGATIVE_DELTA  =  -6

# ── Convergence Bonus ─────────────────────────────────────────────────────────
CONVERGENCE_STRONG_DELTA  =   7   # >= 5 aligned signals
CONVERGENCE_MEDIUM_DELTA  =   5   # >= 4 aligned signals
CONVERGENCE_MILD_DELTA    =   3   # >= 3 aligned signals

CONVERGENCE_STRONG_THRESHOLD  = 5
CONVERGENCE_MEDIUM_THRESHOLD  = 4
CONVERGENCE_MILD_THRESHOLD    = 3

# ── ADX (Step 0.2) ────────────────────────────────────────────────────────────
# ADX measures trend STRENGTH, not direction.
# Low ADX → trend is weak → existing directional signals are less reliable.
# High ADX + dominant direction → amplify the dominant signals.

ADX_WEAK_TREND_DELTA    =  -4   # ADX < ADX_WEAK_THRESHOLD  — no trend, reduce conviction
ADX_MEDIUM_TREND_DELTA  =   3   # ADX >= ADX_MEDIUM_THRESHOLD, direction confirmed
ADX_STRONG_TREND_DELTA  =   6   # ADX >= ADX_STRONG_THRESHOLD, very strong trend

ADX_WEAK_THRESHOLD      =  20   # below = weak / ranging
ADX_MEDIUM_THRESHOLD    =  25   # above = established trend
ADX_STRONG_THRESHOLD    =  40   # above = very strong trend

# ── Stochastic (Step 0.2) ─────────────────────────────────────────────────────
# %K oversold/overbought levels and %K/%D momentum crossover signal.
# Weights deliberately match Williams %R (same oscillator family, same max).

STOCH_EXTREME_OVERSOLD_DELTA    =   8   # %K <  20
STOCH_OVERSOLD_DELTA            =   4   # %K <  30
STOCH_OVERBOUGHT_DELTA          =  -4   # %K >  70
STOCH_EXTREME_OVERBOUGHT_DELTA  =  -8   # %K >  80
STOCH_KD_BULLISH_DELTA          =   2   # %K > %D (positive momentum)
STOCH_KD_BEARISH_DELTA          =  -2   # %K < %D (negative momentum)

STOCH_EXTREME_OVERSOLD_THRESHOLD    =  20
STOCH_OVERSOLD_THRESHOLD            =  30
STOCH_OVERBOUGHT_THRESHOLD          =  70
STOCH_EXTREME_OVERBOUGHT_THRESHOLD  =  80

# ── Session blend ─────────────────────────────────────────────────────────────
SESSION_BASE_WEIGHT     = 0.70
SESSION_SESSION_WEIGHT  = 0.30
