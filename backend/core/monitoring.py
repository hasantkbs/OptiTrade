import sqlite3
import os
from datetime import datetime, timedelta
import logging
import yfinance as yf
from typing import List, Dict, Optional

# Veritabanı yolu
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "monitoring.db")

logger = logging.getLogger(__name__)

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

def log_prediction(symbol: str, score: int, decision_code: str, price: float, window_days: int = 5):
    """Bir analizi veritabanına kaydeder."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        target_date = datetime.now() + timedelta(days=window_days)
        
        cursor.execute("""
            INSERT INTO predictions (symbol, score, decision_code, price_at_prediction, target_date, prediction_window_days)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (symbol, score, decision_code, price, target_date.isoformat(), window_days))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Tahmin kaydedilirken hata oluştu: {e}")

def validate_predictions():
    """Vadesi dolmuş tahminleri kontrol eder ve sonuçları günceller."""
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
            conn.close()
            return 0

        validated_count = 0
        for p_id, symbol, price_at_pred, code, window in matured:
            # Güncel fiyatı çek (veya o tarihteki fiyatı)
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if hist.empty:
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
        conn.close()
        return validated_count
    except Exception as e:
        logger.error(f"Tahminler doğrulanırken hata oluştu: {e}")
        return 0

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
