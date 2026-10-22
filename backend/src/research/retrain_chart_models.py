"""OptiTrade — weekly chart-model retraining.

Usage (from backend/src):
  python -m research.retrain_chart_models

Re-trains and re-validates every symbol CURRENTLY live
(`ml.chart_model.get_supported_symbols()`) on fresh data, using the
exact same chronological-split + second-window-validation methodology
established for every symbol trained so far
(docs/btc-chart-model-training-2026-10-22.md). A symbol is DEMOTED
(removed from the live allowlist) the moment either window no longer
clears `ml.chart_model.check_window_significance()`'s bar - the same
bar every symbol had to clear to go live in the first place, so a
model that drifts with the market gets taken out of production
automatically rather than silently staying live on a stale snapshot.

This script intentionally does NOT re-attempt symbols that are
trained but already excluded (e.g. SOL-USD, MSFT, GOOGL) - only
re-checks what's currently live. Re-attempting excluded symbols is a
separate, explicit decision (see docs), not something a periodic job
should do unprompted every week.

A symbol whose retrain fails for an INFRASTRUCTURE reason (yfinance
fetch error, network issue) is NOT demoted - its previous live status
is kept and the failure is flagged in the report, since an
infrastructure hiccup is not evidence the model itself stopped
working (same "non-fatal, bounded gap" judgment used for GS's partial
news backfill earlier in this project).

Writes:
  - Updated model/scaler files for every symbol that still passes
    (model_path_for/scaler_path_for) - same files `predict_chart_signal()`
    already reads, so a change takes effect on the next live request
    with NO server restart needed.
  - model_artifacts/supported_symbols.json (the new live allowlist -
    ml.chart_model.get_supported_symbols() reads this fresh every call).
  - model_artifacts/retrain_reports/retrain_<timestamp>.json (a full,
    auditable record of this run: what was checked, what passed/failed/
    errored, with the exact numbers).

Deliberately does NOT run `git add`/`commit`/`push` - this script is
meant to run unattended on a schedule (see the module docstring's
cron/systemd-timer example below), and an automated process rewriting
the shared main branch with zero human review is a materially
different risk than a human reviewing and pushing each change, which
is how every prior change in this project has been made. Review the
report and git-commit the result as a deliberate, separate step.

Scheduling (NOT installed by this script - a deployment decision):
  weekly, e.g. every Sunday 02:00 server time:
    0 2 * * 0 cd /path/to/backend/src && /path/to/venv/bin/python -m research.retrain_chart_models >> /var/log/optitrade-retrain.log 2>&1
  or a systemd timer with OnCalendar=Sun *-*-* 02:00:00.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from ml.chart_model import (
    SUPPORTED_SYMBOLS_PATH, MODEL_DIR, check_window_significance, get_supported_symbols,
)
from research.train_chart_model import train
from research.validate_chart_model_window2 import validate

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

REPORT_DIR = os.path.join(MODEL_DIR, "retrain_reports")


def _check_symbol(symbol: str) -> Dict:
    """Retrains + revalidates one symbol. Returns a result dict with
    `status` in {"kept", "demoted", "error"} plus the numbers behind
    that decision."""
    try:
        meta1 = train(symbol=symbol)
        passes1, p1 = check_window_significance(
            n=meta1["n_test"], baseline=meta1["test_majority_baseline"], accuracy=meta1["test_accuracy"],
        )
        result2 = validate(symbol=symbol)
    except Exception as exc:
        logger.error(f"{symbol}: yeniden eğitim hatası - canlı durumu korunuyor: {exc}")
        return {"symbol": symbol, "status": "error", "error": str(exc)}

    n2_support = int(sum(
        result2["window2_classification_report"][label]["support"]
        for label in ("SELL", "NEUTRAL", "BUY")
    ))
    passes2, p2 = check_window_significance(
        n=n2_support, baseline=result2["window2_majority_baseline"], accuracy=result2["window2_test_accuracy"],
    )

    both_pass = passes1 and passes2
    return {
        "symbol": symbol,
        "status": "kept" if both_pass else "demoted",
        "window1": {
            "accuracy": meta1["test_accuracy"], "baseline": meta1["test_majority_baseline"],
            "n": meta1["n_test"], "passes": passes1, "p_value": round(p1, 6),
        },
        "window2": {
            "accuracy": result2["window2_test_accuracy"], "baseline": result2["window2_majority_baseline"],
            "n": n2_support, "passes": passes2, "p_value": round(p2, 6),
        },
    }


def main() -> None:
    current = get_supported_symbols()
    print("=" * 65)
    print(f"Haftalık yeniden eğitim - {len(current)} canlı sembol kontrol ediliyor")
    print(f"Başlangıç: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 65)

    results: List[Dict] = []
    kept: List[str] = []
    demoted: List[str] = []
    errored: List[str] = []

    for symbol in current:
        print(f"\n--- {symbol} ---")
        result = _check_symbol(symbol)
        results.append(result)
        if result["status"] == "kept":
            kept.append(symbol)
            print(f"  TUTULDU: W1 p={result['window1']['p_value']}, W2 p={result['window2']['p_value']}")
        elif result["status"] == "demoted":
            demoted.append(symbol)
            print(f"  ÇIKARILDI (artık anlamlı değil): W1 p={result['window1']['p_value']}, "
                  f"W2 p={result['window2']['p_value']}")
        else:
            errored.append(symbol)
            kept.append(symbol)  # altyapı hatası - önceki canlı durumu koru
            print(f"  HATA (canlı durumu korundu): {result['error']}")

    os.makedirs(os.path.dirname(SUPPORTED_SYMBOLS_PATH), exist_ok=True)
    with open(SUPPORTED_SYMBOLS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "supported_symbols": sorted(kept),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": "research.retrain_chart_models",
            },
            f, indent=2, ensure_ascii=False,
        )

    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(
        REPORT_DIR, f"retrain_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
    )
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "started_symbols": list(current), "kept": sorted(kept),
                "demoted": sorted(demoted), "errored": sorted(errored),
                "results": results, "finished_at": datetime.now(timezone.utc).isoformat(),
            },
            f, indent=2, ensure_ascii=False,
        )

    print("\n" + "=" * 65)
    print(f"Tamamlandı. Tutulan: {len(kept)} | Çıkarılan: {len(demoted)} | Hata: {len(errored)}")
    if demoted:
        print(f"Çıkarılanlar: {demoted}")
    if errored:
        print(f"Hata verenler (canlı durumu korundu): {errored}")
    print(f"Rapor: {report_path}")
    print(f"Güncel allowlist: {SUPPORTED_SYMBOLS_PATH}")
    print("=" * 65)


if __name__ == "__main__":
    main()
