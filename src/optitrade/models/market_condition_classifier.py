import pandas as pd
import numpy as np
import yfinance as yf
import argparse
import logging
from .. import config

# Loglama yapılandırması
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class MarketConditionClassifier:
    """
    Genel piyasa yapısını tanımlayan model: Boğa / Ayı / Yatay.
    Kullanır: VIX, Bitcoin Dominance, Total Market Cap (basitleştirilmiş).
    Girdi: Küresel ve sektörel veriler.
    Çıktı: Market regime (bull/bear/sideways).
    """
    def __init__(self):
        """
        Modeli başlatır.
        """
        pass

    def classify_market_condition(self, vix_value: float, btc_dominance: float, total_market_cap_usd: float) -> str:
        """
        Piyasa koşullarını sınıflandırır.

        Args:
            vix_value (float): VIX endeksi değeri.
            btc_dominance (float): Bitcoin Dominance değeri (örneğin, 0.45 = %45).
            total_market_cap_usd (float): Toplam piyasa değeri (USD).

        Returns:
            str: Piyasa rejimi ('bull', 'bear', 'sideways').
        """
        # VIX eşikleri (genel kabul görmüş değerler)
        # 20 altı: Düşük volatilite, genellikle boğa piyasası
        # 20-30 arası: Orta volatilite, belirsizlik
        # 30 üstü: Yüksek volatilite, genellikle ayı piyasası/panik

        # BTC Dominance eşikleri (kripto piyasası için)
        # Yüksek dominans (örn. >%50) genellikle altcoinler için ayı, BTC için boğa
        # Düşük dominans (örn. <%40) genellikle altcoin sezonu

        # Toplam Piyasa Değeri eşikleri (kripto piyasası için, örnek değerler)
        # 1 Trilyon USD üstü: Genellikle boğa
        # 500 Milyar - 1 Trilyon USD: Yatay/Belirsiz
        # 500 Milyar USD altı: Genellikle ayı

        market_regime = "sideways"

        # VIX'e göre ilk değerlendirme
        if vix_value < 20:
            market_regime = "bull"
        elif vix_value > 30:
            market_regime = "bear"
        else:
            market_regime = "sideways"

        # Bitcoin Dominance ve Total Market Cap ile ince ayar (kripto özelinde)
        if total_market_cap_usd > 1_000_000_000_000: # 1 Trilyon USD
            if market_regime == "sideways": # Eğer VIX nötrse, piyasa değerine bak
                market_regime = "bull"
            if btc_dominance < 0.45: # Altcoin sezonu
                market_regime = "bull" # Altcoinler için boğa

        elif total_market_cap_usd < 500_000_000_000: # 500 Milyar USD
            if market_regime == "sideways": # Eğer VIX nötrse, piyasa değerine bak
                market_regime = "bear"
            if btc_dominance > 0.55: # BTC dominansı yüksek, altcoinler için ayı
                market_regime = "bear" # Altcoinler için ayı

        return market_regime

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Genel piyasa koşullarını sınıflandırır.')
    parser.add_argument('--vix', type=float, help='VIX endeksi değeri.')
    parser.add_argument('--btc_dom', type=float, help='Bitcoin Dominance değeri (örn: 0.45 = %45).')
    parser.add_argument('--mcap', type=float, help='Toplam piyasa değeri (USD).')

    args = parser.parse_args()

    model = MarketConditionClassifier()

    # Varsayılan değerler veya yfinance ile çekilen VIX
    vix_val = args.vix
    if vix_val is None:
        try:
            vix_data = yf.download('^VIX', period='5d', interval='1d', auto_adjust=True) # auto_adjust eklendi
            if not vix_data.empty:
                vix_val = float(vix_data['Close'].iloc[-1]) # float dönüşümü eklendi
                logger.info(f"Güncel VIX değeri: {vix_val:.2f}")
            else:
                logger.warning("VIX verisi çekilemedi, varsayılan 20.0 kullanılıyor.")
                vix_val = 20.0
        except Exception as e:
            logger.error(f"VIX verisi çekilirken hata oluştu: {e}. Varsayılan 20.0 kullanılıyor.")
            vix_val = 20.0

    # BTC Dominance ve Total Market Cap için varsayılan değerler (gerçek uygulamada API'den çekilmeli)
    btc_dom_val = args.btc_dom if args.btc_dom is not None else 0.50 # %50
    mcap_val = args.mcap if args.mcap is not None else 1_500_000_000_000 # 1.5 Trilyon USD

    logger.info(f"--- Piyasa Koşulu Sınıflandırması ---")
    logger.info(f"Girdiler: VIX={vix_val:.2f}, BTC Dominance={btc_dom_val:.2f}, Toplam Piyasa Değeri={mcap_val / 1_000_000_000_000:.2f} Trilyon USD")

    market_condition = model.classify_market_condition(vix_val, btc_dom_val, mcap_val)
    logger.info(f"Piyasa Koşulu: {market_condition.upper()}")

    # Örnek senaryolar
    logger.info("--- Örnek Senaryolar ---")
    logger.info(f"Senaryo 1 (Boğa): VIX=15, BTC_DOM=0.40, MCAP=2T -> {model.classify_market_condition(15, 0.40, 2_000_000_000_000).upper()}")
    logger.info(f"Senaryo 2 (Ayı): VIX=35, BTC_DOM=0.60, MCAP=400B -> {model.classify_market_condition(35, 0.60, 400_000_000_000).upper()}")
    logger.info(f"Senaryo 3 (Yatay): VIX=25, BTC_DOM=0.50, MCAP=800B -> {model.classify_market_condition(25, 0.50, 800_000_000_000).upper()}")