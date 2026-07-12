from pydantic import BaseModel
from typing import Optional, List, Dict


class AnalysisRequest(BaseModel):
    symbol: str
    potential_price: Optional[float] = None
    asset_type: str = "stock"  # "stock" | "crypto"


class TechnicalIndicators(BaseModel):
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    current_price: float
    open_price: float
    price_velocity: float
    daily_volume: float
    avg_monthly_volume: float
    volume_ratio: float


class MonteCarloResult(BaseModel):
    current_price: float
    expected_price_30d: float
    expected_return_pct: float
    std_return_pct: Optional[float] = None
    prob_profit_pct: float
    var_95_pct: float
    cvar_95_pct: float
    pct10_return: Optional[float] = None
    pct90_return: Optional[float] = None
    upside_95_price: float
    downside_5_price: float
    daily_volatility_pct: float
    annual_return_pct: Optional[float] = None
    annual_sharpe: float
    sortino_ratio: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    calmar_ratio: Optional[float] = None
    sim_max_drawdown_median: Optional[float] = None
    n_simulations: int
    n_days: int


class RecommendationResult(BaseModel):
    action: str
    action_code: str
    composite_score: float
    confidence_pct: float
    color: str
    suggested_position_pct: float
    reasons: List[str]
    score_weights: Optional[Dict[str, str]] = None


class AnalysisResult(BaseModel):
    symbol: str
    decision: str
    decision_code: str  # "STRONG_BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG_SELL"
    score: int
    risk_level: str
    balance_status: str
    indicators: TechnicalIndicators
    short_signals: List[str] = []
    long_signals: List[str] = []
    asset_type: str
    ml_confidence: Optional[float] = None
    patterns: Optional[dict] = None
    support_resistance: Optional[dict] = None
    fibonacci: Optional[dict] = None
    extra_indicators: Optional[dict] = None
    news_analysis: Optional[dict] = None
    scoring_breakdown: Optional[List[dict]] = None
    signal_details: Optional[dict] = None     # structured signal engine output (Phase A+)
    monte_carlo: Optional[MonteCarloResult] = None
    recommendation: Optional[RecommendationResult] = None


class ScanResult(BaseModel):
    top_buys: List[AnalysisResult]
    top_sells: List[AnalysisResult]
    neutral: List[AnalysisResult]
    total_scanned: int


class ScanRequest(BaseModel):
    symbols: List[str]
    asset_type: str = "stock"


class ChartPoint(BaseModel):
    date: str
    close: float
    volume: float
    rsi: Optional[float] = None


class ChartResponse(BaseModel):
    symbol: str
    period: str
    points: List[ChartPoint]
    change_pct: float
    high: float
    low: float


# ── Portfolio Optimization ────────────────────────────────────────────────────

class PortfolioOptRequest(BaseModel):
    symbols: List[str]
    risk_tolerance: float = 0.5   # 0=min-variance, 1=max-sharpe


class PortfolioOptResult(BaseModel):
    symbols: List[str]
    weights: Dict[str, float]
    expected_annual_return_pct: float
    annual_volatility_pct: float
    sharpe_ratio: float
    risk_tolerance: float
    efficient_frontier_samples: int


# ── Enhanced Analyze (with Monte Carlo + Recommendation) ──────────────────────

class EnhancedAnalysisRequest(BaseModel):
    symbol: str
    potential_price: Optional[float] = None
    asset_type: str = "stock"
    run_monte_carlo: bool = True
    n_simulations: int = 1000
    n_days: int = 30


# ── Session Info ──────────────────────────────────────────────────────────────

class SessionInfo(BaseModel):
    session_code: str
    session_name: str
    session_description: str
    session_currencies: List[str]
    volatility_multiplier: float
    rsi_signal: float
    macd_signal: float
    volume_signal: float
    breakout_signal: float
    composite_raw: float
    composite_norm: float
    base_score: int
    session_adjusted_score: float
    confidence: float
    session_signals: List[str]
    next_session_minutes: int
    next_session_label: str
