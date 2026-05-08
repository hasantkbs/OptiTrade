"""
OptiTrade Advanced Analysis Module v2
---------------------------------------
Monte Carlo (GBM, 1000 sim) + Markowitz + Gelişmiş Risk Metrikleri
+ Sortino Oranı + Max Drawdown + Calmar Oranı + Enhanced Recommendation
"""
from __future__ import annotations

import math
import logging
from typing import Optional, List, Dict, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Monte Carlo Simulation  (Geometric Brownian Motion)
# ─────────────────────────────────────────────────────────────────────────────

def run_monte_carlo(
    prices: pd.Series,
    n_simulations: int = 1000,
    n_days: int = 30,
    confidence_level: float = 0.95,
) -> Dict:
    if len(prices) < 20:
        return _empty_mc()

    log_returns = np.log(prices / prices.shift(1)).dropna()
    mu    = float(log_returns.mean())
    sigma = float(log_returns.std())
    S0    = float(prices.iloc[-1])

    rng = np.random.default_rng(42)
    Z   = rng.standard_normal((n_simulations, n_days))
    daily_ret = np.exp((mu - 0.5 * sigma**2) + sigma * Z)

    paths        = np.empty((n_simulations, n_days + 1))
    paths[:, 0]  = S0
    for t in range(1, n_days + 1):
        paths[:, t] = paths[:, t-1] * daily_ret[:, t-1]

    final_prices  = paths[:, -1]
    total_returns = (final_prices - S0) / S0

    # VaR & CVaR
    var_pct  = float(np.percentile(total_returns, (1 - confidence_level) * 100))
    below    = total_returns[total_returns <= var_pct]
    cvar_pct = float(below.mean()) if len(below) > 0 else var_pct

    # Yüzde dilimler
    pct_10 = float(np.percentile(total_returns, 10))
    pct_90 = float(np.percentile(total_returns, 90))

    # Sharpe (risk-free %5)
    rf_daily = 0.05 / 252
    excess   = mu - rf_daily
    sharpe   = float((excess / sigma) * math.sqrt(252)) if sigma > 0 else 0.0

    # Sortino (sadece negatif sapma)
    negative_ret = log_returns[log_returns < rf_daily]
    downside_std = float(negative_ret.std()) if len(negative_ret) > 1 else sigma
    sortino      = float((excess / downside_std) * math.sqrt(252)) if downside_std > 0 else 0.0

    # Tarihsel Max Drawdown
    cumulative  = (1 + log_returns).cumprod()
    rolling_max = cumulative.cummax()
    drawdown    = (cumulative - rolling_max) / rolling_max
    max_dd      = float(drawdown.min())

    # Calmar = Yıllık getiri / |Max Drawdown|
    annual_return = float(np.exp(mu * 252) - 1)
    calmar        = annual_return / abs(max_dd) if max_dd != 0 else 0.0

    # Simüle edilmiş max drawdown (medyan)
    mc_mdd_list = []
    for path in paths:
        pk   = np.maximum.accumulate(path)
        mdd  = float(np.min((path - pk) / pk))
        mc_mdd_list.append(mdd)
    sim_mdd_median = float(np.median(mc_mdd_list))

    return {
        "current_price":          round(S0, 6),
        "expected_price_30d":     round(float(np.mean(final_prices)), 6),
        "expected_return_pct":    round(float(np.mean(total_returns)) * 100, 2),
        "std_return_pct":         round(float(np.std(total_returns)) * 100, 2),
        "prob_profit_pct":        round(float(np.mean(total_returns > 0)) * 100, 1),
        "var_95_pct":             round(var_pct * 100, 2),
        "cvar_95_pct":            round(cvar_pct * 100, 2),
        "pct10_return":           round(pct_10 * 100, 2),
        "pct90_return":           round(pct_90 * 100, 2),
        "upside_95_price":        round(float(np.percentile(final_prices, 95)), 6),
        "downside_5_price":       round(float(np.percentile(final_prices, 5)), 6),
        "daily_volatility_pct":   round(sigma * 100, 3),
        "annual_return_pct":      round(annual_return * 100, 2),
        "annual_sharpe":          round(sharpe, 3),
        "sortino_ratio":          round(sortino, 3),
        "max_drawdown_pct":       round(max_dd * 100, 2),
        "calmar_ratio":           round(calmar, 3),
        "sim_max_drawdown_median":round(sim_mdd_median * 100, 2),
        "n_simulations":          n_simulations,
        "n_days":                 n_days,
    }


def _empty_mc() -> Dict:
    keys = [
        "current_price","expected_price_30d","expected_return_pct","std_return_pct",
        "prob_profit_pct","var_95_pct","cvar_95_pct","pct10_return","pct90_return",
        "upside_95_price","downside_5_price","daily_volatility_pct","annual_return_pct",
        "annual_sharpe","sortino_ratio","max_drawdown_pct","calmar_ratio",
        "sim_max_drawdown_median","n_simulations","n_days",
    ]
    return {k: 0.0 for k in keys}


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Markowitz Mean-Variance Portfolio Optimization
# ─────────────────────────────────────────────────────────────────────────────

def optimize_portfolio(
    price_data: Dict[str, pd.Series],
    risk_tolerance: float = 0.5,
    rf_rate: float = 0.05,
) -> Dict:
    symbols = list(price_data.keys())
    n = len(symbols)
    if n < 2:
        return {"error": "Portfolio optimizasyonu icin en az 2 sembol gereklidir."}

    df = pd.DataFrame(price_data).dropna()
    if len(df) < 30:
        return {"error": "Yetersiz veri (min 30 gun gerekli)."}

    log_returns = np.log(df / df.shift(1)).dropna()
    mu  = log_returns.mean().values * 252
    cov = log_returns.cov().values * 252

    n_samples = 3000
    rng = np.random.default_rng(0)
    best_sharpe = -np.inf
    best_minvar = np.inf
    w_sharpe = np.ones(n) / n
    w_minvar = np.ones(n) / n

    for _ in range(n_samples):
        w      = rng.dirichlet(np.ones(n))
        ret    = float(np.dot(w, mu))
        vol    = float(math.sqrt(max(0, np.dot(w, np.dot(cov, w)))))
        sharpe = (ret - rf_rate) / vol if vol > 0 else 0.0
        if sharpe > best_sharpe:
            best_sharpe = sharpe; w_sharpe = w.copy()
        if vol < best_minvar:
            best_minvar = vol; w_minvar = w.copy()

    rt    = max(0.0, min(1.0, risk_tolerance))
    w_opt = (1 - rt) * w_minvar + rt * w_sharpe
    w_opt = w_opt / w_opt.sum()

    port_ret  = float(np.dot(w_opt, mu))
    port_vol  = float(math.sqrt(max(0, np.dot(w_opt, np.dot(cov, w_opt)))))
    port_sh   = (port_ret - rf_rate) / port_vol if port_vol > 0 else 0.0

    # Portföy max drawdown (tarihsel)
    port_rets = log_returns.values @ w_opt
    cum = (1 + port_rets).cumprod()
    pk  = np.maximum.accumulate(cum)
    mdd = float(np.min((cum - pk) / pk))

    return {
        "symbols":                    symbols,
        "weights":                    {sym: round(float(w), 4) for sym, w in zip(symbols, w_opt)},
        "expected_annual_return_pct": round(port_ret * 100, 2),
        "annual_volatility_pct":      round(port_vol * 100, 2),
        "sharpe_ratio":               round(port_sh, 3),
        "max_drawdown_pct":           round(mdd * 100, 2),
        "risk_tolerance":             rt,
        "efficient_frontier_samples": n_samples,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Enhanced Recommendation Engine v2
# ─────────────────────────────────────────────────────────────────────────────

def compute_recommendation(
    score: int,
    ml_confidence: Optional[float],
    monte_carlo: Optional[Dict],
    risk_level: str,
    chart_ai: Optional[Dict] = None,   # CNN/LSTM sonucu varsa
) -> Dict:
    """
    Çok katmanlı öneri motoru:
      • Kural tabanlı skor         : %40 ağırlık
      • XGBoost ML güven puanı     : %25 ağırlık
      • Monte Carlo beklenen getiri: %20 ağırlık
      • Chart AI (CNN/LSTM)        : %15 ağırlık (model varsa)

    Model yoksa ağırlıklar yeniden normalize edilir.
    """
    score_norm = score / 100.0
    ml_norm    = ml_confidence if ml_confidence is not None else score_norm

    # Monte Carlo normalize
    mc_norm = 0.5
    if monte_carlo and monte_carlo.get("expected_return_pct") is not None:
        exp_ret = monte_carlo["expected_return_pct"]
        mc_norm = 1 / (1 + math.exp(-exp_ret / 5))
        # Sharpe düzeltmesi
        sharpe  = monte_carlo.get("annual_sharpe", 0)
        mc_norm = mc_norm * 0.75 + min(1.0, max(0.0, (sharpe + 1) / 4)) * 0.25

    # Chart AI normalize
    ai_norm = None
    if chart_ai and chart_ai.get("signal") and chart_ai.get("confidence"):
        sig  = chart_ai["signal"]
        conf = float(chart_ai["confidence"])
        if sig == "BUY":
            ai_norm = 0.5 + conf * 0.5
        elif sig == "SELL":
            ai_norm = 0.5 - conf * 0.5
        else:
            ai_norm = 0.5

    # Ağırlıklı bileşik skor
    if ai_norm is not None:
        composite = (0.40 * score_norm +
                     0.25 * ml_norm   +
                     0.20 * mc_norm   +
                     0.15 * ai_norm)
    else:
        composite = (0.50 * score_norm +
                     0.30 * ml_norm   +
                     0.20 * mc_norm)

    # Risk cezası
    risk_penalty = {"Dusuk": 0.0, "Orta": 0.03, "Yuksek": 0.07, "Cok Yuksek": 0.13}
    composite -= risk_penalty.get(risk_level, 0.0)
    composite  = max(0.0, min(1.0, composite))

    # Max Drawdown cezası
    if monte_carlo:
        mdd = abs(monte_carlo.get("max_drawdown_pct", 0))
        if mdd > 30:
            composite = max(0, composite - 0.05)
        elif mdd > 50:
            composite = max(0, composite - 0.10)

    # Karar
    if composite >= 0.76:
        action, code, color = "GUCLU AL", "STRONG_BUY", "green"
    elif composite >= 0.59:
        action, code, color = "AL", "BUY", "lightgreen"
    elif composite <= 0.24:
        action, code, color = "GUCLU SAT", "STRONG_SELL", "red"
    elif composite <= 0.41:
        action, code, color = "SAT", "SELL", "orange"
    else:
        action, code, color = "NOTR / IZLE", "NEUTRAL", "gray"

    # Kelly yarı fraksiyonu (pozisyon boyutu)
    edge      = composite - 0.5
    win_prob  = composite
    loss_prob = 1 - composite
    kelly = edge / (win_prob / loss_prob) if (loss_prob > 0 and win_prob > 0) else 0.0
    kelly = max(0.0, min(0.20, kelly * 0.5))  # yarı-Kelly, max %20

    reasons = _build_reasons(score, ml_confidence, monte_carlo, risk_level, composite, chart_ai)

    return {
        "action":                 action,
        "action_code":            code,
        "composite_score":        round(composite * 100, 1),
        "confidence_pct":         round(composite * 100, 1),
        "color":                  color,
        "suggested_position_pct": round(kelly * 100, 1),
        "reasons":                reasons,
        "score_weights": {
            "rule_based":   "40%" if ai_norm is not None else "50%",
            "xgboost_ml":   "25%" if ai_norm is not None else "30%",
            "monte_carlo":  "20%",
            "chart_ai":     "15%" if ai_norm is not None else "—",
        },
    }


def _build_reasons(
    score: int,
    ml_confidence: Optional[float],
    monte_carlo: Optional[Dict],
    risk_level: str,
    composite: float,
    chart_ai: Optional[Dict] = None,
) -> List[str]:
    reasons: List[str] = []

    # Kural tabanlı
    if score >= 70:
        reasons.append(f"Teknik puan guclu ({score}/100)")
    elif score <= 35:
        reasons.append(f"Teknik puan dusuk ({score}/100) — zayif gorulum")
    else:
        reasons.append(f"Teknik puan nötr ({score}/100)")

    # XGBoost
    if ml_confidence is not None:
        pct = round(ml_confidence * 100)
        if ml_confidence >= 0.65:
            reasons.append(f"XGBoost modeli yukselis ihtimali %{pct}")
        elif ml_confidence <= 0.40:
            reasons.append(f"XGBoost modeli dusus ihtimali %{100 - pct}")
        else:
            reasons.append(f"XGBoost modeli notr (%{pct} yukselis olasiligi)")

    # Chart AI (CNN/LSTM)
    if chart_ai and chart_ai.get("signal"):
        sig  = chart_ai["signal"]
        conf = chart_ai.get("confidence", 0)
        reasons.append(f"Chart AI ({sig}, güven: %{conf*100:.0f})")

    # Monte Carlo
    if monte_carlo:
        exp_ret = monte_carlo.get("expected_return_pct", 0)
        prob    = monte_carlo.get("prob_profit_pct", 0)
        var     = monte_carlo.get("var_95_pct", 0)
        sortino = monte_carlo.get("sortino_ratio", 0)
        mdd     = monte_carlo.get("max_drawdown_pct", 0)
        if exp_ret > 2:
            reasons.append(f"MC: 30g beklenen getiri %{exp_ret:.1f}, kar olasılığı %{prob:.0f}")
        elif exp_ret < -2:
            reasons.append(f"MC: 30g beklenen kayip %{abs(exp_ret):.1f}, VaR(%95)=%{abs(var):.1f}")
        if sortino > 1.5:
            reasons.append(f"Sortino orani guclu ({sortino:.2f}) — asagı yonlu risk düşük")
        elif sortino < 0:
            reasons.append(f"Sortino orani negatif ({sortino:.2f}) — riske gore getiri yetersiz")
        if mdd < -25:
            reasons.append(f"Tarihsel max dusus %{abs(mdd):.1f} — yuksek volatilite gecmisi")

    # Risk
    if risk_level in ("Yuksek", "Cok Yuksek"):
        reasons.append(f"Risk seviyesi {risk_level} — pozisyon buyuklugunu sinirli tutun")

    return reasons
