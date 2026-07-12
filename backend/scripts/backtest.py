import sys
sys.path.insert(0, ".")

import pandas as pd
import numpy as np
import yfinance as yf
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
    "stock": ["THYAO.IS", "GARAN.IS", "ASELS.IS", "KCHOL.IS", "EREGL.IS",
              "AKBNK.IS", "TUPRS.IS", "FROTO.IS", "SAHOL.IS", "PGSUS.IS"],
    "crypto": ["BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "AVAX-USD"],
}


def backtest_symbol(symbol: str, asset_type: str) -> dict:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1y")
    if hist is None or len(hist) < LOOKBACK + FORWARD_DAYS + 10:
        return {"symbol": symbol, "error": "Yetersiz veri"}

    total = 0
    correct = 0
    buy_correct = 0
    buy_total = 0
    sell_correct = 0
    sell_total = 0
    neutral_total = 0
    details = []

    for i in range(LOOKBACK, len(hist) - FORWARD_DAYS):
        window = hist.iloc[:i+1]
        prices = window["Close"]
        current_price = float(prices.iloc[-1])
        open_price = float(window["Open"].iloc[-1])
        daily_volume = float(window["Volume"].iloc[-1])
        avg_volume = float(window["Volume"].iloc[-LOOKBACK:].mean())

        rsi = calculate_rsi(prices.iloc[-LOOKBACK:])
        macd, macd_sig, macd_hist = calculate_macd(prices.iloc[-LOOKBACK:])
        bollinger = calculate_bollinger_bands(prices.iloc[-LOOKBACK:])
        ema_cross = calculate_ema_crossover(prices.iloc[-LOOKBACK:])
        trend_str = calculate_trend_strength(prices.iloc[-LOOKBACK:])
        price_vel = calculate_price_velocity(current_price, open_price)
        vol_ratio = calculate_volume_ratio(daily_volume, avg_volume)

        score, long_s, short_s = compute_score(
            current_price=current_price,
            potential_price=None,
            volume_ratio=vol_ratio,
            balance_status="Notr",
            rsi=rsi,
            macd=macd,
            macd_signal=macd_sig,
            bollinger=bollinger,
            ema_crossover=ema_cross,
            trend_strength=trend_str,
        )
        decision, code = get_decision(score)

        future_price = float(hist["Close"].iloc[i + FORWARD_DAYS])
        actual_change = ((future_price - current_price) / current_price) * 100

        if code in ("STRONG_BUY", "BUY"):
            buy_total += 1
            total += 1
            if actual_change > THRESHOLD_UP:
                correct += 1
                buy_correct += 1
        elif code in ("STRONG_SELL", "SELL"):
            sell_total += 1
            total += 1
            if actual_change < THRESHOLD_DOWN:
                correct += 1
                sell_correct += 1
        else:
            neutral_total += 1

    accuracy = (correct / total * 100) if total > 0 else 0.0

    return {
        "symbol": symbol,
        "total_signals": total,
        "correct": correct,
        "accuracy": round(accuracy, 1),
        "buy_signals": buy_total,
        "buy_correct": buy_correct,
        "buy_accuracy": round(buy_correct / buy_total * 100, 1) if buy_total > 0 else 0.0,
        "sell_signals": sell_total,
        "sell_correct": sell_correct,
        "sell_accuracy": round(sell_correct / sell_total * 100, 1) if sell_total > 0 else 0.0,
        "neutral_count": neutral_total,
    }


if __name__ == "__main__":
    print("=" * 70)
    print("OptiTrade Analiz Motoru - Backtest Raporu")
    print(f"Lookback: {LOOKBACK} gun | Forward: {FORWARD_DAYS} gun")
    print(f"AL basari kriteri: >{THRESHOLD_UP}% | SAT basari kriteri: <{THRESHOLD_DOWN}%")
    print("=" * 70)

    all_results = []

    for asset_type, symbols in SYMBOLS.items():
        print(f"\n--- {asset_type.upper()} ---")
        for sym in symbols:
            print(f"  Taranıyor: {sym}...", end=" ", flush=True)
            r = backtest_symbol(sym, asset_type)
            if "error" in r:
                print(f"HATA: {r['error']}")
            else:
                all_results.append(r)
                print(f"Dogruluk: %{r['accuracy']} ({r['correct']}/{r['total_signals']} sinyal)")
                print(f"    AL: %{r['buy_accuracy']} ({r['buy_correct']}/{r['buy_signals']})", end="")
                print(f" | SAT: %{r['sell_accuracy']} ({r['sell_correct']}/{r['sell_signals']})", end="")
                print(f" | NOTR: {r['neutral_count']}")

    if all_results:
        total_s = sum(r["total_signals"] for r in all_results)
        total_c = sum(r["correct"] for r in all_results)
        total_buy_s = sum(r["buy_signals"] for r in all_results)
        total_buy_c = sum(r["buy_correct"] for r in all_results)
        total_sell_s = sum(r["sell_signals"] for r in all_results)
        total_sell_c = sum(r["sell_correct"] for r in all_results)

        print("\n" + "=" * 70)
        print("GENEL SONUC")
        print("=" * 70)
        print(f"Toplam Sembol: {len(all_results)}")
        print(f"Toplam Sinyal: {total_s}")
        print(f"Dogru Tahmin:  {total_c}")
        print(f"GENEL DOGRULUK: %{total_c / total_s * 100:.1f}" if total_s > 0 else "Sinyal yok")
        print(f"  AL Dogruluk:  %{total_buy_c / total_buy_s * 100:.1f} ({total_buy_c}/{total_buy_s})" if total_buy_s > 0 else "  AL sinyal yok")
        print(f"  SAT Dogruluk: %{total_sell_c / total_sell_s * 100:.1f} ({total_sell_c}/{total_sell_s})" if total_sell_s > 0 else "  SAT sinyal yok")
        print("=" * 70)
