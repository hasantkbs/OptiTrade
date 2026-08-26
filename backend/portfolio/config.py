"""OptiTrade Portfolio Intelligence Platform — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from core.infra_config import redis_settings_from_env


@dataclass(frozen=True)
class PortfolioConfig:
    """Runtime settings for the Portfolio Intelligence Platform."""

    default_base_currency: str = "USD"
    benchmark_symbol: str = "^GSPC"

    # Risk analytics
    risk_free_rate: float = 0.05
    var_confidence_level: float = 0.95
    lookback_days: int = 252
    trading_days_per_year: int = 252

    # Portfolio Cache (Redis-backed current-price cache - never a
    # source of truth, just avoids re-fetching the same symbol's price
    # multiple times within one dashboard/analytics call)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    price_cache_ttl_seconds: int = 60

    # Rebalancing
    default_rebalance_threshold_pct: float = 5.0
    default_rebalance_interval_days: int = 30
    default_fee_rate_pct: float = 0.1

    # Optimization / scenarios
    efficient_frontier_points: int = 20
    monte_carlo_simulations: int = 2000
    monte_carlo_horizon_days: int = 30
    prediction_view_blend_weight: float = 0.3  # how much a Pipeline view tilts the historical mean return

    @classmethod
    def from_env(cls) -> "PortfolioConfig":
        load_dotenv()
        redis_host, redis_port, redis_db = redis_settings_from_env("PORTFOLIO")
        return cls(
            default_base_currency=os.getenv("PORTFOLIO_DEFAULT_BASE_CURRENCY", "USD"),
            benchmark_symbol=os.getenv("PORTFOLIO_BENCHMARK_SYMBOL", "^GSPC"),
            risk_free_rate=float(os.getenv("PORTFOLIO_RISK_FREE_RATE", "0.05")),
            var_confidence_level=float(os.getenv("PORTFOLIO_VAR_CONFIDENCE_LEVEL", "0.95")),
            lookback_days=int(os.getenv("PORTFOLIO_LOOKBACK_DAYS", "252")),
            trading_days_per_year=int(os.getenv("PORTFOLIO_TRADING_DAYS_PER_YEAR", "252")),
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            price_cache_ttl_seconds=int(os.getenv("PORTFOLIO_PRICE_CACHE_TTL_SECONDS", "60")),
            default_rebalance_threshold_pct=float(os.getenv("PORTFOLIO_DEFAULT_REBALANCE_THRESHOLD_PCT", "5.0")),
            default_rebalance_interval_days=int(os.getenv("PORTFOLIO_DEFAULT_REBALANCE_INTERVAL_DAYS", "30")),
            default_fee_rate_pct=float(os.getenv("PORTFOLIO_DEFAULT_FEE_RATE_PCT", "0.1")),
            efficient_frontier_points=int(os.getenv("PORTFOLIO_EFFICIENT_FRONTIER_POINTS", "20")),
            monte_carlo_simulations=int(os.getenv("PORTFOLIO_MONTE_CARLO_SIMULATIONS", "2000")),
            monte_carlo_horizon_days=int(os.getenv("PORTFOLIO_MONTE_CARLO_HORIZON_DAYS", "30")),
            prediction_view_blend_weight=float(os.getenv("PORTFOLIO_PREDICTION_VIEW_BLEND_WEIGHT", "0.3")),
        )
