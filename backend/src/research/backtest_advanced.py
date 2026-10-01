"""
OptiTrade - Gelişmiş Backtest Motoru
-------------------------------------
Şu metrikleri hesaplar:
  - Doğruluk oranı (AL / SAT / Toplam)
  - Sharpe Ratio (yıllıklandırılmış)
  - Maksimum düşüş (Max Drawdown)
  - Ortalama kazanç / kayıp
  - Win rate (% kazanan işlemler)
  - Portföy son değeri

Çalıştırmak için:
  cd backend
  python research/backtest_advanced.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import yfinance as yf
import json
from typing import Dict, List

from core.indicators import (
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_ema_crossover,
    calculate_trend_strength,
    calculate_price_velocity,
    calculate_volume_ratio,
)
from core.scoring import compute_score, get_decision

LOOKBACK = 60
FORWARD_DAYS = 5
THRESHOLD_UP = 1.0
THRESHOLD_DOWN = -1.0

SYMBOLS = {
    "stock": [
        "THYAO.IS", "GARAN.IS", "ASELS.IS", "KCHOL.IS", "EREGL.IS",
        "AKBNK.IS", "TUPRS.IS", "FROTO.IS", "SAHOL.IS", "PGSUS.IS",
    ],
    "crypto": [
        "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "AVAX-USD",
    ],
}


def _sharpe(returns: List[float], rf: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    arr = np.array(returns)
    excess = arr - rf
    std = np.std(excess)
    if std == 0:
        return 0.0
    return float(np.mean(excess) / std * np.sqrt(252 / FORWARD_DAYS))


def _max_drawdown(equity_curve: List[float]) -> float:
    if len(equity_curve) < 2:
        return 0.0
    arr = np.array(equity_curve)
    peak = np.maximum.accumulate(arr)
    drawdown = (arr - peak) / np.where(peak > 0, peak, 1e-10)
    return float(drawdown.min() * 100)


def _win_rate(returns: List[float], threshold: float = 0.0) -> float:
    if not returns:
        return 0.0
    wins = sum(1 for r in returns if r > threshold)
    return wins / len(returns) * 100


def backtest_symbol(symbol: str, asset_type: str) -> dict:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1y")
    if hist is None or len(hist) < LOOKBACK + FORWARD_DAYS + 10:
        return {"symbol": symbol, "error": "Yetersiz veri"}

    total = correct = 0
    buy_total = buy_correct = 0
    sell_total = sell_correct = 0
    neutral_total = 0

    buy_returns: List[float] = []
    sell_returns: List[float] = []
    all_trade_returns: List[float] = []
    equity_curve: List[float] = [1.0]

    for i in range(LOOKBACK, len(hist) - FORWARD_DAYS):
        window = hist.iloc[:i + 1]
        prices = window["Close"]
        current_p = float(prices.iloc[-1])
        open_p    = float(window["Open"].iloc[-1])
        daily_vol = float(window["Volume"].iloc[-1])
        avg_vol   = float(window["Volume"].iloc[-LOOKBACK:].mean())

        rsi      = calculate_rsi(prices.iloc[-LOOKBACK:])
        macd, ms, mh = calculate_macd(prices.iloc[-LOOKBACK:])
        boll     = calculate_bollinger_bands(prices.iloc[-LOOKBACK:])
        ema_x    = calculate_ema_crossover(prices.iloc[-LOOKBACK:])
        trend    = calculate_trend_strength(prices.iloc[-LOOKBACK:])
        vel      = calculate_price_velocity(current_p, open_p)
        vol_r    = calculate_volume_ratio(daily_vol, avg_vol)

        score, _, _ = compute_score(
            current_price=current_p,
            potential_price=None,
            volume_ratio=vol_r,
            balance_status="Notr",
            rsi=rsi,
            macd=macd,
            macd_signal=ms,
            bollinger=boll,
            ema_crossover=ema_x,
            trend_strength=trend,
        )
        _, code = get_decision(score)

        future_p      = float(hist["Close"].iloc[i + FORWARD_DAYS])
        actual_return = ((future_p - current_p) / current_p) * 100

        if code in ("STRONG_BUY", "BUY"):
            buy_total += 1
            total += 1
            buy_returns.append(actual_return)
            all_trade_returns.append(actual_return)
            equity_curve.append(equity_curve[-1] * (1 + actual_return / 100))
            if actual_return > THRESHOLD_UP:
                correct += 1
                buy_correct += 1

        elif code in ("STRONG_SELL", "SELL"):
            sell_total += 1
            total += 1
            short_ret = -actual_return
            sell_returns.append(short_ret)
            all_trade_returns.append(short_ret)
            equity_curve.append(equity_curve[-1] * (1 + short_ret / 100))
            if actual_return < THRESHOLD_DOWN:
                correct += 1
                sell_correct += 1
        else:
            neutral_total += 1

    accuracy = correct / total * 100 if total > 0 else 0.0
    buy_acc  = buy_correct / buy_total * 100 if buy_total > 0 else 0.0
    sell_acc = sell_correct / sell_total * 100 if sell_total > 0 else 0.0

    return {
        "symbol": symbol,
        "asset_type": asset_type,
        "total_signals": total,
        "correct": correct,
        "accuracy_pct": round(accuracy, 1),
        "buy_signals": buy_total,
        "buy_correct": buy_correct,
        "buy_accuracy_pct": round(buy_acc, 1),
        "sell_signals": sell_total,
        "sell_correct": sell_correct,
        "sell_accuracy_pct": round(sell_acc, 1),
        "neutral_count": neutral_total,
        "sharpe_ratio": round(_sharpe(all_trade_returns), 2),
        "max_drawdown_pct": round(_max_drawdown(equity_curve), 1),
        "win_rate_pct": round(_win_rate(all_trade_returns), 1),
        "avg_trade_return_pct": round(float(np.mean(all_trade_returns)) if all_trade_returns else 0.0, 2),
        "avg_buy_return_pct": round(float(np.mean(buy_returns)) if buy_returns else 0.0, 2),
        "avg_sell_return_pct": round(float(np.mean(sell_returns)) if sell_returns else 0.0, 2),
        "best_trade_pct": round(float(max(all_trade_returns)) if all_trade_returns else 0.0, 2),
        "worst_trade_pct": round(float(min(all_trade_returns)) if all_trade_returns else 0.0, 2),
        "final_portfolio_value": round(equity_curve[-1], 4),
        "total_return_pct": round((equity_curve[-1] - 1.0) * 100, 1),
    }


def run_backtest() -> List[dict]:
    print("=" * 70)
    print("OptiTrade - Gelişmiş Backtest Raporu")
    print(f"Lookback: {LOOKBACK} gün | Forward: {FORWARD_DAYS} gün")
    print(f"AL kriteri: >+%{THRESHOLD_UP} | SAT kriteri: <-%{abs(THRESHOLD_DOWN)}")
    print("=" * 70)

    all_results: List[dict] = []

    for asset_type, symbols in SYMBOLS.items():
        print(f"\n--- {asset_type.upper()} ---")
        for sym in symbols:
            print(f"  {sym}...", end=" ", flush=True)
            r = backtest_symbol(sym, asset_type)
            if "error" in r:
                print(f"HATA: {r['error']}")
            else:
                all_results.append(r)
                print(
                    f"Doğruluk: %{r['accuracy_pct']:5.1f} | "
                    f"Sharpe: {r['sharpe_ratio']:+.2f} | "
                    f"MaxDD: %{r['max_drawdown_pct']:5.1f} | "
                    f"WinRate: %{r['win_rate_pct']:.0f} | "
                    f"Toplam Getiri: %{r['total_return_pct']:+.1f}"
                )

    return all_results


def print_summary(results: List[dict]):
    if not results:
        print("\nSonuç yok.")
        return

    total_s = sum(r["total_signals"] for r in results)
    total_c = sum(r["correct"] for r in results)
    avg_sharpe = float(np.mean([r["sharpe_ratio"] for r in results]))
    worst_dd   = float(min(r["max_drawdown_pct"] for r in results))
    avg_win    = float(np.mean([r["win_rate_pct"] for r in results]))
    avg_ret    = float(np.mean([r["avg_trade_return_pct"] for r in results]))

    buy_total = sum(r["buy_signals"] for r in results)
    buy_corr  = sum(r["buy_correct"] for r in results)
    sell_total= sum(r["sell_signals"] for r in results)
    sell_corr = sum(r["sell_correct"] for r in results)

    print("\n" + "=" * 70)
    print("GENEL ÖZET")
    print("=" * 70)
    print(f"Toplam Sembol:          {len(results)}")
    print(f"Toplam Sinyal:          {total_s}")
    print(f"Genel Doğruluk:        %{total_c/total_s*100:.1f}" if total_s > 0 else "  Sinyal yok")
    print(f"  AL  Doğruluk:        %{buy_corr/buy_total*100:.1f} ({buy_corr}/{buy_total})" if buy_total > 0 else "")
    print(f"  SAT Doğruluk:        %{sell_corr/sell_total*100:.1f} ({sell_corr}/{sell_total})" if sell_total > 0 else "")
    print(f"Ort. Sharpe Ratio:      {avg_sharpe:.2f}")
    print(f"En Kötü Max Drawdown:  %{worst_dd:.1f}")
    print(f"Ort. Win Rate:         %{avg_win:.1f}")
    print(f"Ort. İşlem Getirisi:   %{avg_ret:+.2f}")
    print("=" * 70)


if __name__ == "__main__":
    results = run_backtest()
    print_summary(results)

    if results:
        df = pd.DataFrame(results)
        df = df.sort_values("accuracy_pct", ascending=False)
        output_path = "backtest_results.csv"
        df.to_csv(output_path, index=False)
        print(f"\nDetaylı sonuçlar kaydedildi: {output_path}")

        json_path = "backtest_results.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"JSON formatında kaydedildi: {json_path}")
