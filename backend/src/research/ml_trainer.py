"""
OptiTrade XGBoost Sinyal Sınıflandırıcı Eğitim Scripti
------------------------------------------------------
Çalıştırmak için:
  cd backend/src
  python research/ml_trainer.py [--train-end-date YYYY-MM-DD] [--output-suffix _oos_test]

Gereksinimler:
  pip install xgboost scikit-learn joblib

--train-end-date, verilen tarihte durmuş gibi davranarak eğitir: yfinance'ten
sadece o tarihe kadarki (ve ondan 2 yıl önceye kadar geriye giden) veriyi
çeker, train_end_date'i model paketinin içine kaydeder. Bu, scripts/
evaluate_model_accuracy.py'nin train_end_date'ten SONRAKİ veriyle gerçek
bir out-of-sample (gerçekten hiç görülmemiş) değerlendirme yapabilmesini
sağlar - verilmezse (varsayılan) script'in eski davranışı korunur: "şimdi"ye
kadarki en güncel 2 yıl, train_end_date paket içine kaydedilmez
(None) ve hiçbir gerçek held-out pencere garanti edilmez (bu script'in
kendi iç train_test_split'i hâlâ kronolojik değil, rastgele - ayrı,
bilinen bir sınırlama, bu değişikliğin kapsamı dışında).

--output-suffix, verilirse model_artifacts/xgb_signal_model<suffix>.joblib'e
yazar (prod'un servis ettiği xgb_signal_model.joblib'in üzerine YAZMAZ) -
yeniden eğitilmiş bir modeli canlıya almadan önce ayrı, incelenebilir bir
dosya olarak üretmek için.
"""

import argparse
import secrets
import sys
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import yfinance as yf
from typing import List, Optional, Tuple
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

from core.indicators import (
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_ema_crossover,
    calculate_trend_strength,
    calculate_price_velocity,
    calculate_volume_ratio,
)

LOOKBACK = 60
FORWARD_DAYS = 5
THRESHOLD_UP = 1.0

# A freshly retrained model is only allowed to replace the live model
# if its cross-validated accuracy isn't more than this many percentage
# points worse than the model it would replace - retraining on noisy
# daily data must never silently ship a regression to production (see
# _deploy_if_not_regressed below).
MAX_ACCURACY_REGRESSION = 0.01

SYMBOLS = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "KCHOL.IS", "EREGL.IS",
    "AKBNK.IS", "TUPRS.IS", "FROTO.IS", "SAHOL.IS", "PGSUS.IS",
    "ISCTR.IS", "SISE.IS",  "BIMAS.IS", "YKBNK.IS", "TOASO.IS",
    "BTC-USD",  "ETH-USD",  "BNB-USD",  "SOL-USD",  "AVAX-USD",
    "XRP-USD",  "DOGE-USD",
]

FEATURE_NAMES = [
    "rsi",
    "macd_diff",
    "bollinger_pb",
    "ema_signal_enc",
    "trend_strength",
    "price_velocity",
    "volume_ratio",
]

EMA_SIGNAL_ENC = {
    "GOLDEN_CROSS": 2,
    "BULLISH": 1,
    "BEARISH": -1,
    "DEATH_CROSS": -2,
    None: 0,
}


def extract_features(window: pd.DataFrame) -> Optional[List[float]]:
    try:
        prices = window["Close"]
        current = float(prices.iloc[-1])
        open_p  = float(window["Open"].iloc[-1])
        vol     = float(window["Volume"].iloc[-1])
        avg_vol = float(window["Volume"].mean())

        rsi = calculate_rsi(prices)
        if rsi is None:
            rsi = 50.0

        macd, macd_sig, _ = calculate_macd(prices)
        macd_diff = (macd - macd_sig) if (macd is not None and macd_sig is not None) else 0.0

        boll = calculate_bollinger_bands(prices)
        pb = boll.get("percent_b") if boll else None
        if pb is None:
            pb = 0.5

        ema  = calculate_ema_crossover(prices)
        ema_enc = EMA_SIGNAL_ENC.get(ema, 0)

        trend = calculate_trend_strength(prices) or 0.0
        vel   = calculate_price_velocity(current, open_p)
        vol_r = calculate_volume_ratio(vol, avg_vol)

        return [rsi, macd_diff, pb, ema_enc, trend, vel, vol_r]
    except Exception:
        return None


def build_dataset(symbol: str, train_end_date: Optional[datetime] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Never raises - a single symbol's `yfinance` fetch failing (rate
    limit, delisted ticker, network hiccup) must not abort a
    multi-symbol training run any more than "insufficient history"
    does (the pre-existing `len(hist) < ...` skip below). The failure
    is still logged, not silently discarded, so a systemic fetch
    problem (e.g. every symbol failing) remains visible.

    `train_end_date`, verilirse, yfinance'ten sadece [train_end_date -
    2 yıl, train_end_date] aralığındaki veriyi çeker - "şimdi"ye kadar
    değil, böylece bu fonksiyonun ürettiği hiçbir satır train_end_date'i
    geçmez (scripts/evaluate_model_accuracy.py'nin bu tarihten SONRAKİ
    veriyle değerlendirme yapabilmesinin ön koşulu). `None` ise (varsayılan),
    eski davranış korunur: en güncel 2 yıl."""
    try:
        ticker = yf.Ticker(symbol)
        if train_end_date is not None:
            hist = ticker.history(
                start=(train_end_date - timedelta(days=730)).strftime("%Y-%m-%d"),
                end=train_end_date.strftime("%Y-%m-%d"),
            )
        else:
            hist = ticker.history(period="2y")
    except Exception as exc:
        logger.warning(f"{symbol} için veri çekilemedi, atlanıyor: {exc}")
        return np.array([]), np.array([])
    if hist is None or len(hist) < LOOKBACK + FORWARD_DAYS + 10:
        return np.array([]), np.array([])

    X, y = [], []
    for i in range(LOOKBACK, len(hist) - FORWARD_DAYS):
        window = hist.iloc[i - LOOKBACK : i + 1]
        feats = extract_features(window)
        if feats is None:
            continue

        current_p = float(hist["Close"].iloc[i])
        future_p  = float(hist["Close"].iloc[i + FORWARD_DAYS])
        label = 1 if ((future_p - current_p) / current_p) * 100 > THRESHOLD_UP else 0

        X.append(feats)
        y.append(label)

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)


def _deploy_if_not_regressed(model_path: str, package: dict, joblib_module) -> bool:
    """Replaces the live-served model file at `model_path` with `package`
    only if doing so can't ship a silent accuracy regression, and does
    so without ever leaving a partially-written/corrupt file behind.

    - Compares `package["cv_accuracy_mean"]` against whatever model is
      currently live (if any) and refuses to deploy if the new model is
      worse by more than MAX_ACCURACY_REGRESSION.
    - Keeps a `<model_path>.bak` copy of the previous live model before
      swapping, so a bad deploy can be manually rolled back by copying
      the backup over `model_path`.
    - Writes the new model to a temp file first and `os.replace()`s it
      into place - `os.replace` is atomic on the same filesystem, so a
      reader never observes a half-written file.

    Returns True if the new model was deployed, False if it was
    rejected for regressing.
    """
    if os.path.exists(model_path):
        try:
            previous = joblib_module.load(model_path)
            previous_accuracy = previous.get("cv_accuracy_mean")
        except Exception:
            previous_accuracy = None

        if previous_accuracy is not None:
            new_accuracy = package["cv_accuracy_mean"]
            if new_accuracy < previous_accuracy - MAX_ACCURACY_REGRESSION:
                print(
                    f"[ATLANDI] Yeni model canli modelden daha kotu "
                    f"({new_accuracy*100:.1f}% < {previous_accuracy*100:.1f}% - "
                    f"{MAX_ACCURACY_REGRESSION*100:.0f}pp tolerans) - dagitim iptal edildi."
                )
                return False

        shutil.copy2(model_path, model_path + ".bak")

    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(model_path) or ".", suffix=".joblib.tmp")
    os.close(fd)
    try:
        joblib_module.dump(package, tmp_path)
        os.replace(tmp_path, model_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    return True


# Task 0.2-A (CTO Remediation Plan Revision 4, Finding A9): the
# default-output_suffix call `self_evolution_loop` makes must no longer
# reach _deploy_if_not_regressed against the live-served file at all -
# see write_candidate_artifact below. An explicit, non-empty
# output_suffix (the existing manual/research CLI usage - see this
# module's own docstring) is intentionally left untouched: it already
# targets a non-live path, so it never conflicted with "never overwrite
# the live artifact" in the first place.
_CANDIDATES_DIRNAME = "candidates"


class CandidateAlreadyExistsError(Exception):
    """Raised if a generated candidate_id collides with an already-
    written candidate artifact - see write_candidate_artifact's own
    docstring for why this is expected to never actually happen in
    practice, and why it is still guarded against explicitly rather
    than silently overwritten."""


@dataclass(frozen=True)
class CandidateArtifact:
    """What Task 0.2-B's future registry adapter needs to find and
    identify this candidate - a unique id, the file it lives at, and
    when it was written. Deliberately NOT a registry interface: no
    promotion state, no registry call, nothing beyond "a file was
    safely written and here is how to find it again"."""
    candidate_id: str
    path: str
    created_at: datetime


def _generate_candidate_id(created_at: datetime) -> str:
    """`created_at` (microsecond-precision UTC timestamp, lexically
    sortable - "deterministic enough to trace") plus an 8-hex-character
    random suffix ("unique enough to prevent collisions" even if two
    training runs started in the same microsecond - e.g. two workers
    both believing they are the self-evolution leader, a known,
    pre-existing risk this task does not fix; see
    core.infra_config.acquire_scheduler_leader_lock's own fail-open
    behavior, Task 0.2-F)."""
    return f"{created_at.strftime('%Y%m%dT%H%M%S%f')}_{secrets.token_hex(4)}"


def _candidate_artifact_path(candidates_dir: str, candidate_id: str) -> str:
    return os.path.join(candidates_dir, f"xgb_signal_model_candidate_{candidate_id}.joblib")


def write_candidate_artifact(package: dict, joblib_module, candidates_dir: Optional[str] = None) -> CandidateArtifact:
    """Writes `package` as a new, uniquely-identified candidate artifact
    under `candidates_dir` (default: model_artifacts/candidates/ - a
    dedicated subdirectory deliberately kept separate from the live-
    served xgb_signal_model.joblib and its own .bak). Never touches the
    live artifact: there is no regression check and no "replace the
    previous one" semantics here, because there is no "previous"
    candidate this one is meant to replace - each training run gets its
    own permanent, independent file. Promoting a candidate to live-
    served is Task 0.2-B/C's job (model registry registration + an
    explicit, human-gated promotion), not this function's.

    Atomic and collision-safe: writes to a temp file in the SAME
    directory first (so the finalize step below stays on one
    filesystem, matching _deploy_if_not_regressed's own existing
    convention), then finalizes with `os.link()` rather than
    `os.replace()` - unlike os.replace, os.link raises FileExistsError
    if the destination already exists instead of silently overwriting
    it, which is exactly the "never silently replace an existing
    candidate with the same identifier" guarantee this function must
    provide. The temp file is removed once a successful link means the
    data survives under the new candidate path (a second hard link to
    the same inode until that point). Any failure - including the
    collision case - removes the temp file and raises, never leaving a
    partially-written or ambiguous file where a candidate_id is
    supposed to be."""
    if candidates_dir is None:
        candidates_dir = os.path.join("..", "model_artifacts", _CANDIDATES_DIRNAME)
    os.makedirs(candidates_dir, exist_ok=True)

    created_at = datetime.now(timezone.utc)
    candidate_id = _generate_candidate_id(created_at)
    final_path = _candidate_artifact_path(candidates_dir, candidate_id)

    fd, tmp_path = tempfile.mkstemp(dir=candidates_dir, suffix=".joblib.tmp")
    os.close(fd)
    try:
        joblib_module.dump(package, tmp_path)
        try:
            os.link(tmp_path, final_path)
        except FileExistsError as exc:
            raise CandidateAlreadyExistsError(
                f"candidate artifact already exists at {final_path!r} - refusing to silently overwrite it"
            ) from exc
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    os.remove(tmp_path)

    return CandidateArtifact(candidate_id=candidate_id, path=final_path, created_at=created_at)


def train(train_end_date: Optional[datetime] = None, output_suffix: str = "") -> Optional[CandidateArtifact]:
    """Returns the written `CandidateArtifact` for the default-suffix
    (production self-evolution) path, so `main.py`'s self_evolution_loop
    can register it (Task 0.2-B) - `None` for every early-exit case
    (missing dependency, no data) and for the explicit-suffix (manual/
    research) path, which deploys via `_deploy_if_not_regressed` instead
    and has nothing for a caller to register."""
    try:
        from xgboost import XGBClassifier
    except ImportError:
        print("[HATA] XGBoost yüklü değil. Çalıştırın: pip install xgboost scikit-learn joblib")
        return None

    try:
        from sklearn.model_selection import cross_val_score, StratifiedKFold, train_test_split
        from sklearn.metrics import classification_report, confusion_matrix
        import joblib
    except ImportError:
        print("[HATA] scikit-learn / joblib yüklü değil. Çalıştırın: pip install scikit-learn joblib")
        return None

    print("=" * 65)
    print("OptiTrade - XGBoost Sinyal Sınıflandırıcı Eğitimi")
    print(f"Lookback: {LOOKBACK} gün | Forward: {FORWARD_DAYS} gün | Eşik: +%{THRESHOLD_UP}")
    if train_end_date is not None:
        print(f"Eğitim verisi kesme tarihi: {train_end_date.date().isoformat()} (bu tarihten sonraki hiçbir satır eğitime girmez)")
    print("=" * 65)

    all_X, all_y = [], []
    for sym in SYMBOLS:
        print(f"  Veri çekiliyor: {sym}...", end=" ", flush=True)
        X, y = build_dataset(sym, train_end_date=train_end_date)
        if len(X) > 0:
            all_X.append(X)
            all_y.append(y)
            print(f"{len(X)} örnek (pozitif: {y.sum()}, {y.mean()*100:.0f}%)")
        else:
            print("yetersiz veri - atlandı")

    if not all_X:
        print("[HATA] Hiç veri toplanamadı!")
        return None

    X_all = np.vstack(all_X)
    y_all = np.concatenate(all_y)

    pos_rate = y_all.mean() * 100
    print(f"\nToplam veri seti: {len(X_all)} örnek | "
          f"Pozitif (AL): {y_all.sum()} ({pos_rate:.1f}%)")

    X_train, X_test, y_train, y_test = train_test_split(
        X_all, y_all, test_size=0.2, random_state=42, stratify=y_all
    )

    model = XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        gamma=0.1,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )

    print("\nModel eğitiliyor (5-katlı çapraz doğrulama)...")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(
        model, X_train, y_train, cv=cv, scoring="accuracy", n_jobs=-1
    )
    print(f"Cross-val doğruluk: {cv_scores.mean()*100:.1f}% ± {cv_scores.std()*100:.1f}%")

    model.fit(X_train, y_train, verbose=False)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    print("\nTest seti sınıflandırma raporu:")
    print(classification_report(y_test, y_pred, target_names=["DÜŞÜŞ/NÖTR", "YUKARI"]))

    print("Karmaşıklık matrisi:")
    cm = confusion_matrix(y_test, y_pred)
    print(f"  TN={cm[0,0]:4d}  FP={cm[0,1]:4d}")
    print(f"  FN={cm[1,0]:4d}  TP={cm[1,1]:4d}")

    print("\nÖzellik önemleri:")
    for name, imp in sorted(zip(FEATURE_NAMES, model.feature_importances_), key=lambda x: -x[1]):
        bar = "█" * int(imp * 40)
        print(f"  {name:18s}: {bar} ({imp:.3f})")

    os.makedirs("../model_artifacts", exist_ok=True)
    package = {
        "model": model,
        "feature_names": FEATURE_NAMES,
        "lookback": LOOKBACK,
        "forward_days": FORWARD_DAYS,
        "threshold": THRESHOLD_UP,
        "cv_accuracy_mean": float(cv_scores.mean()),
        "cv_accuracy_std": float(cv_scores.std()),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        # None for the default (no --train-end-date) invocation - evaluate_model_
        # accuracy.py treats that as "no recorded cutoff, don't claim out-of-sample".
        "train_end_date": train_end_date.date().isoformat() if train_end_date is not None else None,
    }
    if output_suffix:
        # Unchanged, pre-existing behavior: an explicit suffix already
        # targets a non-live research file (e.g. evaluate_model_accuracy.py's
        # out-of-sample workflow), so it never conflicted with "never
        # overwrite the live artifact" - see this module's own docstring.
        model_path = os.path.join("..", "model_artifacts", f"xgb_signal_model{output_suffix}.joblib")
        if _deploy_if_not_regressed(model_path, package, joblib):
            print(f"\nModel kaydedildi: {model_path}")
        print("=" * 65)
        return None
    else:
        # Task 0.2-A: the production self-evolution path (main.py's
        # self_evolution_loop calls train() with no arguments) must
        # never write to the live-served file directly anymore - see
        # write_candidate_artifact's own docstring. Registering this
        # candidate in ml_training.registry (Task 0.2-B, via main.py -
        # see model_serving/legacy_candidate_registry_adapter.py) and
        # promoting it to live (Task 0.2-C) are explicitly out of scope
        # here - this function only ever writes the file and returns
        # where it lives.
        candidate = write_candidate_artifact(package, joblib)
        print(f"\nCandidate model kaydedildi: {candidate.path} (candidate_id={candidate.candidate_id})")
        print("=" * 65)
        return candidate


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--train-end-date", type=str, default=None, metavar="YYYY-MM-DD",
        help="Eğitim verisini bu tarihte kesin; verilmezse eski davranış (en güncel 2 yıl, kesim tarihi kaydedilmez).",
    )
    parser.add_argument(
        "--output-suffix", type=str, default="", metavar="_suffix",
        help="model_artifacts/xgb_signal_model<suffix>.joblib'e yaz - boşsa (varsayılan) prod dosyasının üzerine yazar.",
    )
    args = parser.parse_args()
    _train_end_date = (
        datetime.strptime(args.train_end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.train_end_date else None
    )
    train(train_end_date=_train_end_date, output_suffix=args.output_suffix)
