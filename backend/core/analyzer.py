from typing import Optional
import logging

from data.fetcher import fetch_history, get_balance_status
from core.indicators import (
    calculate_rsi,
    calculate_rsi_series,
    calculate_macd,
    calculate_price_velocity,
    calculate_volume_ratio,
    calculate_bollinger_bands,
    calculate_ema_crossover,
    calculate_trend_strength,
    # Yeni indikatörler
    calculate_williams_r,
    calculate_cci,
    calculate_vwap,
    calculate_roc,
    calculate_ichimoku,
    calculate_divergence,
)
from core.pattern_recognition import (
    detect_patterns,
    find_support_resistance,
    calculate_fibonacci,
    calculate_atr,
    calculate_stochastic,
    calculate_adx,
)
from core.scoring import compute_score, get_decision, get_risk_level
from core.ml_predictor import get_ml_confidence
from core.news_analyzer import analyze_news, NewsAnalysisResult
from models.schemas import AnalysisResult, TechnicalIndicators
from signals.technical import TechnicalSignalEngine
from signals.fundamental import FundamentalSignalEngine
from signals.news import NewsSignalEngine
from signals.models import SignalCollection
from data.fundamental import fetch_fundamental_data
from news.pipeline import NewsPipeline

logger = logging.getLogger(__name__)


def analyze(
    symbol: str,
    potential_price: Optional[float] = None,
    asset_type: str = "stock",
    include_news: bool = True,   # Haber analizini dahil et
    news_pipeline: Optional[NewsPipeline] = None,
    news_signal_engine: Optional[NewsSignalEngine] = None,
) -> Optional[AnalysisResult]:

    hist = fetch_history(symbol, period="6mo")   # 3mo→6mo: daha iyi Ichimoku/Fib
    if hist is None or len(hist) < 2:
        logger.warning(f"Yetersiz veri: {symbol}")
        return None

    close         = hist["Close"]
    high          = hist["High"]
    low           = hist["Low"]
    open_         = hist["Open"]
    volume        = hist["Volume"]

    current_price       = float(close.iloc[-1])
    open_price          = float(open_.iloc[-1])
    daily_volume        = float(volume.iloc[-1])
    avg_monthly_volume  = float(volume.mean())

    # ── Temel göstergeler ─────────────────────────────────────────────────────
    rsi                         = calculate_rsi(close)
    macd, macd_signal, macd_hist = calculate_macd(close)
    bollinger                   = calculate_bollinger_bands(close)
    ema_crossover               = calculate_ema_crossover(close)
    trend_strength              = calculate_trend_strength(close)
    price_velocity              = calculate_price_velocity(current_price, open_price)
    volume_ratio                = calculate_volume_ratio(daily_volume, avg_monthly_volume)
    balance_status              = get_balance_status(symbol) if asset_type == "stock" else "Notr"

    # ── Yeni göstergeler ─────────────────────────────────────────────────────
    williams_r = calculate_williams_r(high, low, close)
    cci        = calculate_cci(high, low, close)
    vwap       = calculate_vwap(high, low, close, volume)
    roc        = calculate_roc(close, period=10)
    ichimoku   = calculate_ichimoku(high, low, close)

    # Diverjans — RSI serisi gerekir
    rsi_ser   = calculate_rsi_series(close)
    divergence = calculate_divergence(close, rsi_ser)

    # ATR — risk seviyesi için
    atr_abs = calculate_atr(high, low, close)
    atr_pct = (atr_abs / current_price * 100) if (atr_abs and current_price) else None

    # ── Stochastic + ADX (Step 0.2) ───────────────────────────────────────────
    stoch     = calculate_stochastic(high, low, close)
    stoch_k   = stoch.get("stoch_k")
    stoch_d   = stoch.get("stoch_d")
    adx       = calculate_adx(high, low, close)

    # ── Skor ─────────────────────────────────────────────────────────────────
    score, long_signals, short_signals, scoring_breakdown = compute_score(
        current_price   = current_price,
        potential_price = potential_price,
        volume_ratio    = volume_ratio,
        balance_status  = balance_status,
        rsi             = rsi,
        macd            = macd,
        macd_signal     = macd_signal,
        bollinger       = bollinger,
        ema_crossover   = ema_crossover,
        trend_strength  = trend_strength,
        macd_hist       = macd_hist,
        williams_r      = williams_r,
        cci             = cci,
        ichimoku        = ichimoku,
        divergence      = divergence,
        vwap            = vwap,
        roc             = roc,
        adx             = adx,
        stoch_k         = stoch_k,
        stoch_d         = stoch_d,
    )

    # ── Signal Engines (Phase A + B1 + B2.1) ─────────────────────────────────
    # Non-blocking: any engine failure leaves that engine absent from
    # signal_details. Engines are instantiated per-call (no module-level
    # singletons) and, for News, are injectable for testing.
    tech_result = fund_result = news_signal_result = None

    # Phase A: Technical
    try:
        tech_result = TechnicalSignalEngine().generate(scoring_breakdown)
    except Exception as _se:
        logger.debug("TechnicalSignalEngine failed (non-blocking): %s", _se)

    # Phase B1: Fundamental — equities only; skipped for crypto
    if asset_type == "stock":
        try:
            fund_data = fetch_fundamental_data(symbol)
            if fund_data is not None:
                fund_result = FundamentalSignalEngine().generate(fund_data)
        except Exception as _fe:
            logger.debug("FundamentalSignalEngine failed (non-blocking): %s", _fe)

    # Phase B2.1: News — fully additive. Any failure here (provider,
    # normalization, entity extraction, sentiment, ...) is swallowed so it
    # can never affect scoring, decision, or the legacy news_analysis block
    # further below, which is entirely independent of this pipeline.
    if include_news:
        try:
            pipeline = news_pipeline or NewsPipeline()
            engine   = news_signal_engine or NewsSignalEngine()
            news_signal_result = engine.generate(pipeline.run(symbol))
        except Exception as _ne:
            logger.debug("NewsSignalEngine failed (non-blocking): %s", _ne)

    signal_collection = SignalCollection(
        technical=tech_result, fundamental=fund_result, news=news_signal_result,
    )
    signal_details = signal_collection.to_dict() if signal_collection.has_data else None

    decision, decision_code = get_decision(score)
    risk_level              = get_risk_level(price_velocity, atr_pct=atr_pct)

    # ── XGBoost ML ───────────────────────────────────────────────────────────
    ml_conf = get_ml_confidence(
        rsi            = rsi,
        macd           = macd,
        macd_signal    = macd_signal,
        bollinger_pb   = bollinger.get("percent_b") if bollinger else None,
        ema_crossover  = ema_crossover,
        trend_strength = trend_strength,
        volume_ratio   = volume_ratio,
        price_velocity = price_velocity,
    )

    # ── Pattern Recognition ───────────────────────────────────────────────────
    pattern_result = sr_result = fib_result = None
    try:
        pattern_result = detect_patterns(
            open_=open_, high=high, low=low, close=close, volume=volume
        )
        sr_result  = find_support_resistance(high, low, close)
        fib_result = calculate_fibonacci(high, low, close)

        # Formasyon skoru ana skora eklenir (±15 sınırı)
        pattern_delta = max(-15, min(15, pattern_result.get("score_delta", 0)))
        score = round(score + pattern_delta, 1)
        # Pattern sinyallerini long/short listelerine ekle
        for msg in pattern_result.get("signals", []):
            if pattern_delta >= 0:
                long_signals.append(msg)
            else:
                short_signals.append(msg)
    except Exception as _e:
        logger.debug(f"Pattern recognition hatası: {_e}")

    # ── Haber Analizi ─────────────────────────────────────────────────────────
    news_result: Optional[NewsAnalysisResult] = None
    if include_news:
        try:
            news_result = analyze_news(symbol, use_cache=True)
            news_delta  = news_result.score_delta  # [-15, +15]
            # Haber sinyallerini uygun listeye ekle
            if news_delta > 0:
                long_signals  = news_result.signals + long_signals
            elif news_delta < 0:
                short_signals = news_result.signals + short_signals
            else:
                long_signals  = long_signals + news_result.signals
            score = round(score + news_delta, 1)
        except Exception as _e:
            logger.debug(f"Haber analizi hatası: {_e}")

    # ── Indicators nesnesine ek alanlar ─────────────────────────────────────
    indicators = TechnicalIndicators(
        rsi              = rsi,
        macd             = macd,
        macd_signal      = macd_signal,
        macd_histogram   = macd_hist,
        current_price    = current_price,
        open_price       = open_price,
        price_velocity   = price_velocity,
        daily_volume     = daily_volume,
        avg_monthly_volume = avg_monthly_volume,
        volume_ratio     = volume_ratio,
    )

    return AnalysisResult(
        symbol          = symbol,
        decision        = decision,
        decision_code   = decision_code,
        score           = score,
        risk_level      = risk_level,
        balance_status  = balance_status,
        indicators      = indicators,
        long_signals    = long_signals,
        short_signals   = short_signals,
        asset_type      = asset_type,
        ml_confidence   = round(ml_conf, 3) if ml_conf is not None else None,
        patterns        = pattern_result,
        support_resistance = sr_result,
        fibonacci       = fib_result,
        scoring_breakdown = scoring_breakdown,
        signal_details   = signal_details,
        extra_indicators = {
            "williams_r":   williams_r,
            "cci":          cci,
            "vwap":         round(vwap, 6) if vwap else None,
            "roc_10d":      roc,
            "atr_pct":      round(atr_pct, 3) if atr_pct else None,
            "ichimoku":     ichimoku,
            "divergence":   divergence,
            "bb_bandwidth": bollinger.get("bandwidth") if bollinger else None,
            "adx":          adx,
            "stoch_k":      stoch_k,
            "stoch_d":      stoch_d,
        },
        news_analysis = {
            "sentiment_score":    news_result.sentiment_score   if news_result else None,
            "sentiment_label":    news_result.sentiment_label   if news_result else None,
            "score_delta":        news_result.score_delta       if news_result else 0,
            "positive_count":     news_result.positive_count    if news_result else 0,
            "negative_count":     news_result.negative_count    if news_result else 0,
            "total_news":         news_result.total_news        if news_result else 0,
            "sector":             news_result.sector            if news_result else None,
            "top_positive_title": news_result.top_positive_title if news_result else None,
            "top_negative_title": news_result.top_negative_title if news_result else None,
            "headlines": [
                {
                    "title":        item.title,
                    "sentiment":    item.sentiment_label,
                    "score":        item.sentiment_score,
                    "published_at": item.published_at.isoformat(),
                    "keywords":     item.matched_keywords[:5],
                }
                for item in sorted(
                    news_result.news_items,
                    key=lambda x: abs(x.weighted_score),
                    reverse=True,
                )[:8]
            ] if news_result else [],
        } if news_result is not None else None,
    )
