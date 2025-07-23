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

class AlertSystem:
    """
    Belirli skor eşiği aşıldığında sinyal üreten sistem.
    """
    def __init__(self, 
                 bullish_threshold: float = config.ALERT_BULLISH_THRESHOLD, 
                 bearish_threshold: float = config.ALERT_BEARISH_THRESHOLD):
        """
        Uyarı sistemini başlatır ve eşikleri ayarlar.

        Args:
            bullish_threshold (float): Boğa sinyali için skor eşiği.
            bearish_threshold (float): Ayı sinyali için skor eşiği.
        """
        self.bullish_threshold = bullish_threshold
        self.bearish_threshold = bearish_threshold

    def check_for_alert(self, score: float) -> str:
        """
        Verilen skora göre uyarı sinyali kontrolü yapar.

        Args:
            score (float): Nihai tahmin skoru.

        Returns:
            str: Uyarı mesajı veya boş string.
        """
        if score >= self.bullish_threshold:
            return f"🚨 BOĞA SİNYALİ! Skor {score:.2f} (Eşik: {self.bullish_threshold:.2f})"
        elif score <= self.bearish_threshold:
            return f"🚨 AYI SİNYALİ! Skor {score:.2f} (Eşik: {self.bearish_threshold:.2f})"
        else:
            return f"Nötr. Skor {score:.2f} (Boğa Eşiği: {self.bullish_threshold:.2f}, Ayı Eşiği: {self.bearish_threshold:.2f})"

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Tahmin skoruna göre uyarı sinyali üretir.')
    parser.add_argument('--score', type=float, required=True, help='Analiz edilecek tahmin skoru.')
    parser.add_argument('--bullish_threshold', type=float, default=0.7, help='Boğa sinyali için skor eşiği. Varsayılan: 0.7')
    parser.add_argument('--bearish_threshold', type=float, default=-0.7, help='Ayı sinyali için skor eşiği. Varsayılan: -0.7')

    args = parser.parse_args()

    logger.info(f"--- Uyarı Sistemi Kontrolü ---")

    alert_system = AlertSystem(bullish_threshold=args.bullish_threshold, bearish_threshold=args.bearish_threshold)
    alert_message = alert_system.check_for_alert(args.score)

    logger.info(alert_message)

    # Örnek senaryolar
    logger.info("--- Örnek Senaryolar ---")
    logger.info(alert_system.check_for_alert(0.8)) # Güçlü boğa
    logger.info(alert_system.check_for_alert(0.5)) # Nötr
    logger.info(alert_system.check_for_alert(-0.8)) # Güçlü ayı
    logger.info(alert_system.check_for_alert(-0.5)) # Nötr
