"""OptiTrade Watchlist & Alert Platform — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class WatchlistConfig:
    """Runtime settings for the Watchlist & Alert Platform."""

    # Persistence / cache
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # Technical alert defaults
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    bollinger_upper_percent_b: float = 1.0
    bollinger_lower_percent_b: float = 0.0
    volume_spike_ratio: float = 2.0
    atr_expansion_ratio: float = 1.5
    atr_history_lookback: int = 14
    feature_max_age_seconds: int = 3600

    # Decision Engine alert defaults
    confidence_change_threshold: float = 0.15
    expected_return_change_threshold_pct: float = 3.0
    risk_change_threshold_pct: float = 5.0

    # News alert defaults
    news_high_impact_threshold: float = 0.6
    news_breaking_max_age_minutes: int = 120
    news_sector_impact_threshold: float = 0.5
    news_cache_ttl_seconds: int = 300

    # Portfolio alert defaults
    portfolio_allocation_threshold_pct: float = 25.0
    portfolio_var_threshold_pct: float = -5.0
    portfolio_drawdown_threshold_pct: float = -15.0
    portfolio_concentration_threshold: float = 0.5

    # Scheduler
    min_check_interval_seconds: int = 60
    default_cooldown_minutes: int = 60
    max_parallel_workers: int = 8
    alert_timeout_seconds: float = 8.0
    max_retries: int = 1
    dedup_window_seconds: int = 300
    scan_batch_size: int = 200

    @classmethod
    def from_env(cls) -> "WatchlistConfig":
        load_dotenv()
        return cls(
            redis_host=os.getenv("WATCHLIST_REDIS_HOST", os.getenv("FEATURE_STORE_REDIS_HOST", "localhost")),
            redis_port=int(os.getenv("WATCHLIST_REDIS_PORT", os.getenv("FEATURE_STORE_REDIS_PORT", "6379"))),
            redis_db=int(os.getenv("WATCHLIST_REDIS_DB", os.getenv("FEATURE_STORE_REDIS_DB", "0"))),
            rsi_overbought=float(os.getenv("WATCHLIST_RSI_OVERBOUGHT", "70.0")),
            rsi_oversold=float(os.getenv("WATCHLIST_RSI_OVERSOLD", "30.0")),
            bollinger_upper_percent_b=float(os.getenv("WATCHLIST_BOLLINGER_UPPER_PERCENT_B", "1.0")),
            bollinger_lower_percent_b=float(os.getenv("WATCHLIST_BOLLINGER_LOWER_PERCENT_B", "0.0")),
            volume_spike_ratio=float(os.getenv("WATCHLIST_VOLUME_SPIKE_RATIO", "2.0")),
            atr_expansion_ratio=float(os.getenv("WATCHLIST_ATR_EXPANSION_RATIO", "1.5")),
            atr_history_lookback=int(os.getenv("WATCHLIST_ATR_HISTORY_LOOKBACK", "14")),
            feature_max_age_seconds=int(os.getenv("WATCHLIST_FEATURE_MAX_AGE_SECONDS", "3600")),
            confidence_change_threshold=float(os.getenv("WATCHLIST_CONFIDENCE_CHANGE_THRESHOLD", "0.15")),
            expected_return_change_threshold_pct=float(
                os.getenv("WATCHLIST_EXPECTED_RETURN_CHANGE_THRESHOLD_PCT", "3.0")
            ),
            risk_change_threshold_pct=float(os.getenv("WATCHLIST_RISK_CHANGE_THRESHOLD_PCT", "5.0")),
            news_high_impact_threshold=float(os.getenv("WATCHLIST_NEWS_HIGH_IMPACT_THRESHOLD", "0.6")),
            news_breaking_max_age_minutes=int(os.getenv("WATCHLIST_NEWS_BREAKING_MAX_AGE_MINUTES", "120")),
            news_sector_impact_threshold=float(os.getenv("WATCHLIST_NEWS_SECTOR_IMPACT_THRESHOLD", "0.5")),
            news_cache_ttl_seconds=int(os.getenv("WATCHLIST_NEWS_CACHE_TTL_SECONDS", "300")),
            portfolio_allocation_threshold_pct=float(
                os.getenv("WATCHLIST_PORTFOLIO_ALLOCATION_THRESHOLD_PCT", "25.0")
            ),
            portfolio_var_threshold_pct=float(os.getenv("WATCHLIST_PORTFOLIO_VAR_THRESHOLD_PCT", "-5.0")),
            portfolio_drawdown_threshold_pct=float(os.getenv("WATCHLIST_PORTFOLIO_DRAWDOWN_THRESHOLD_PCT", "-15.0")),
            portfolio_concentration_threshold=float(os.getenv("WATCHLIST_PORTFOLIO_CONCENTRATION_THRESHOLD", "0.5")),
            min_check_interval_seconds=int(os.getenv("WATCHLIST_MIN_CHECK_INTERVAL_SECONDS", "60")),
            default_cooldown_minutes=int(os.getenv("WATCHLIST_DEFAULT_COOLDOWN_MINUTES", "60")),
            max_parallel_workers=int(os.getenv("WATCHLIST_MAX_PARALLEL_WORKERS", "8")),
            alert_timeout_seconds=float(os.getenv("WATCHLIST_ALERT_TIMEOUT_SECONDS", "8.0")),
            max_retries=int(os.getenv("WATCHLIST_MAX_RETRIES", "1")),
            dedup_window_seconds=int(os.getenv("WATCHLIST_DEDUP_WINDOW_SECONDS", "300")),
            scan_batch_size=int(os.getenv("WATCHLIST_SCAN_BATCH_SIZE", "200")),
        )
