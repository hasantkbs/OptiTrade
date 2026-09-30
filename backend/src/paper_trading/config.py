"""OptiTrade Paper Trading & Trade Journal Platform — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from core.infra_config import postgres_settings_from_env, redis_settings_from_env


@dataclass(frozen=True)
class PaperTradingConfig:
    """Runtime settings for the Paper Trading & Trade Journal Platform."""

    # Execution simulation
    slippage_bps: float = 5.0          # basis points applied against the trader, per fill
    spread_bps: float = 10.0           # simulated bid/ask spread, split across both sides
    commission_rate: float = 0.001     # 0.1% of notional
    commission_min: float = 1.0
    tax_rate: float = 0.0              # applied to realized gains on SELL fills only
    latency_ms_min: int = 20
    latency_ms_max: int = 250

    # Market hours (non-24/7 symbols only - see execution.is_market_open)
    market_timezone: str = "Europe/Istanbul"
    market_open_hour: int = 10
    market_close_hour: int = 18
    market_trading_days: tuple = (0, 1, 2, 3, 4)  # Mon-Fri, datetime.weekday()

    # Redis cache (paper positions / analytics summaries)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    position_cache_ttl_seconds: int = 15
    analytics_cache_ttl_seconds: int = 60

    # Postgres
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "optitrade"
    postgres_user: str = "optitrade_user"
    postgres_password: str = ""

    @classmethod
    def from_env(cls) -> "PaperTradingConfig":
        load_dotenv()
        redis_host, redis_port, redis_db = redis_settings_from_env("PAPER_TRADING")
        postgres_host, postgres_port, postgres_db, postgres_user, postgres_password = postgres_settings_from_env()
        return cls(
            slippage_bps=float(os.getenv("PAPER_TRADING_SLIPPAGE_BPS", "5.0")),
            spread_bps=float(os.getenv("PAPER_TRADING_SPREAD_BPS", "10.0")),
            commission_rate=float(os.getenv("PAPER_TRADING_COMMISSION_RATE", "0.001")),
            commission_min=float(os.getenv("PAPER_TRADING_COMMISSION_MIN", "1.0")),
            tax_rate=float(os.getenv("PAPER_TRADING_TAX_RATE", "0.0")),
            latency_ms_min=int(os.getenv("PAPER_TRADING_LATENCY_MS_MIN", "20")),
            latency_ms_max=int(os.getenv("PAPER_TRADING_LATENCY_MS_MAX", "250")),
            market_timezone=os.getenv("PAPER_TRADING_MARKET_TIMEZONE", "Europe/Istanbul"),
            market_open_hour=int(os.getenv("PAPER_TRADING_MARKET_OPEN_HOUR", "10")),
            market_close_hour=int(os.getenv("PAPER_TRADING_MARKET_CLOSE_HOUR", "18")),
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            position_cache_ttl_seconds=int(os.getenv("PAPER_TRADING_POSITION_CACHE_TTL_SECONDS", "15")),
            analytics_cache_ttl_seconds=int(os.getenv("PAPER_TRADING_ANALYTICS_CACHE_TTL_SECONDS", "60")),
            postgres_host=postgres_host,
            postgres_port=postgres_port,
            postgres_db=postgres_db,
            postgres_user=postgres_user,
            postgres_password=postgres_password,
        )
