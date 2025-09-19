import sqlite3
import pandas as pd
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional

from .. import config

logger = logging.getLogger(__name__)

class DatabaseHandler:
    """
    SQLite veritabanı ile ilgili tüm işlemleri yönetir.
    """
    def __init__(self, db_path: str = config.DATABASE_FILE):
        self.db_path = db_path
        self.connection = None
        try:
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            logger.info(f"Veritabanı bağlantısı başarıyla kuruldu: {self.db_path}")
            self._initialize_db()
        except sqlite3.Error as e:
            logger.error(f"Veritabanı hatası: {e}", exc_info=True)

    def _initialize_db(self):
        """Veritabanı tablolarını (eğer yoksa) oluşturur."""
        if not self.connection:
            return
        try:
            cursor = self.connection.cursor()
            # Gelecekteki analizler için sinyal tablosu
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS generated_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    final_score REAL NOT NULL,
                    current_market_price REAL,
                    estimated_target_price REAL,
                    position_sizing_details TEXT,
                    model_outputs_json TEXT
                )
            ''')
            self.connection.commit()
            logger.info("'generated_signals' tablosu başarıyla oluşturuldu veya zaten mevcut.")
        except sqlite3.Error as e:
            logger.error(f"Tablo oluşturulurken hata: {e}", exc_info=True)

    def save_signal(self, analysis_result: Dict[str, Any], symbol: str, interval: str):
        """
        Üretilen bir sinyali veritabanına kaydeder.
        """
        if not self.connection:
            logger.error("Veritabanı bağlantısı yok, sinyal kaydedilemedi.")
            return

        query = '''
            INSERT INTO generated_signals (
                timestamp, symbol, interval, final_score, current_market_price, 
                estimated_target_price, position_sizing_details, model_outputs_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        '''
        try:
            cursor = self.connection.cursor()
            params = (
                datetime.now(),
                symbol,
                interval,
                analysis_result.get('final_score'),
                analysis_result.get('current_market_price'),
                analysis_result.get('estimated_target_price'),
                analysis_result.get('position_sizing', {}).get('details'),
                json.dumps(analysis_result.get('model_outputs', {})) # dict'i JSON string'e çevir
            )
            cursor.execute(query, params)
            self.connection.commit()
            logger.info(f"'{symbol}' için yeni sinyal başarıyla veritabanına kaydedildi.")
        except sqlite3.Error as e:
            logger.error(f"Sinyal veritabanına kaydedilirken hata: {e}", exc_info=True)

    def close_connection(self):
        """Veritabanı bağlantısını kapatır."""
        if self.connection:
            self.connection.close()
            logger.info("Veritabanı bağlantısı kapatıldı.")
