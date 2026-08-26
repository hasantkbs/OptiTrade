import sqlite3
import os
from datetime import datetime, timedelta
import logging
import yfinance as yf
from typing import Dict, Optional

# Veritabanı yolu
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "monitoring.db")

logger = logging.getLogger(__name__)

# `predictions` is written once per scan (`log_prediction`), forever - see
# `purge_old_predictions()`. 365 days comfortably exceeds every existing
# consumer's lookback (`get_performance_stats`'s largest normal caller is
# `GET /ml/performance?days=30`).
PREDICTION_RETENTION_DAYS = int(os.getenv("MONITORING_PREDICTION_RETENTION_DAYS", "365"))

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tahminler tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            score INTEGER,
            decision_code TEXT,
            price_at_prediction REAL,
            target_date DATETIME,
            actual_price REAL,
            is_correct INTEGER, -- 1: Başarılı, 0: Başarısız, NULL: Beklemede
            prediction_window_days INTEGER DEFAULT 5
        )
    """)
    
    # Performans geçmişi tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS performance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            metric_name TEXT,
            metric_value REAL,
            period TEXT -- 'daily', 'weekly'
        )
    """)
    
    conn.commit()
    conn.close()

def validate_predictions():
    """Vadesi dolmuş tahminleri kontrol eder ve sonuçları günceller.

    Her tahmin için fiyat, ayrı bir yfinance ağ çağrısıyla çekilir - bu
    yüzden tek bir sembol geçici olarak başarısız olsa bile (rate limit,
    ağ hatası, vs.) döngünün geri kalanı etkilenmemeli ve o ana kadar
    doğrulanmış satırlar kaybedilmemelidir. connection ise her durumda
    (başarı veya hata) kapatılır."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Vadesi dolmuş ve henüz doğrulanmamış tahminleri al
        now = datetime.now().isoformat()
        cursor.execute("""
            SELECT id, symbol, price_at_prediction, decision_code, prediction_window_days
            FROM predictions
            WHERE target_date <= ? AND is_correct IS NULL
        """, (now,))

        matured = cursor.fetchall()
        if not matured:
            return 0

        validated_count = 0
        for p_id, symbol, price_at_pred, code, window in matured:
            try:
                # Güncel fiyatı çek (veya o tarihteki fiyatı)
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="1d")
                if hist.empty:
                    continue
            except Exception as e:
                logger.warning(f"{symbol} (id={p_id}) için fiyat çekilemedi, atlanıyor: {e}")
                continue

            actual_price = float(hist["Close"].iloc[-1])
            return_pct = (actual_price - price_at_pred) / price_at_pred * 100

            # Başarı kriteri:
            # STRONG_BUY/BUY ise return > +1%
            # STRONG_SELL/SELL ise return < -1%
            # NEUTRAL ise return [-1%, +1%] arası
            is_correct = 0
            if code in ["STRONG_BUY", "BUY"] and return_pct > 1.0:
                is_correct = 1
            elif code in ["STRONG_SELL", "SELL"] and return_pct < -1.0:
                is_correct = 1
            elif code == "NEUTRAL" and -1.0 <= return_pct <= 1.0:
                is_correct = 1

            cursor.execute("""
                UPDATE predictions
                SET actual_price = ?, is_correct = ?
                WHERE id = ?
            """, (actual_price, is_correct, p_id))
            validated_count += 1

        conn.commit()
        return validated_count
    except Exception as e:
        logger.error(f"Tahminler doğrulanırken hata oluştu: {e}")
        return 0
    finally:
        if conn is not None:
            conn.close()

def purge_old_predictions(retention_days: Optional[int] = None) -> int:
    """Deletes already-validated prediction rows older than the retention
    window, so `predictions` (written once per scan/analysis via
    `log_prediction`, unboundedly, forever) doesn't grow without limit.

    Only rows with `is_correct IS NOT NULL` are eligible - a row still
    `is_correct IS NULL` is awaiting `validate_predictions()` and must
    never be deleted before its target_date has even been evaluated,
    regardless of how old its `timestamp` is."""
    retention_days = retention_days if retention_days is not None else PREDICTION_RETENTION_DAYS
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        cursor.execute(
            "DELETE FROM predictions WHERE is_correct IS NOT NULL AND timestamp < ?",
            (cutoff,),
        )
        deleted = cursor.rowcount
        conn.commit()
        return deleted
    except Exception as e:
        logger.error(f"Eski tahminler temizlenirken hata olustu: {e}")
        return 0
    finally:
        if conn is not None:
            conn.close()

def get_performance_stats(days: int = 7) -> Dict:
    """Belirli bir gün sayısı için performans metriklerini döner."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        since = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            SELECT COUNT(*), SUM(is_correct) 
            FROM predictions 
            WHERE is_correct IS NOT NULL AND timestamp >= ?
        """, (since,))
        
        total, correct = cursor.fetchone()
        accuracy = (correct / total * 100) if total and total > 0 else 0
        
        conn.close()
        return {
            "total_validated": total or 0,
            "correct_predictions": correct or 0,
            "accuracy": round(accuracy, 2),
            "period_days": days
        }
    except Exception as e:
        logger.error(f"Performans istatistikleri alınırken hata oluştu: {e}")
        return {}
