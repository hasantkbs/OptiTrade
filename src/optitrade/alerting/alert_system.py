import argparse
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any

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
    Belirli skor eşiği aşıldığında sinyal üreten ve bildirim gönderen sistem.
    """
    def __init__(self, 
                 bullish_threshold: float = config.ALERT_BULLISH_THRESHOLD, 
                 bearish_threshold: float = config.ALERT_BEARISH_THRESHOLD):
        self.bullish_threshold = bullish_threshold
        self.bearish_threshold = bearish_threshold

    def send_email_alert(self, subject: str, body: str):
        """Belirtilen konu ve içerik ile bir e-posta gönderir."""
        if not all([config.SMTP_SERVER, config.SMTP_USERNAME, config.SMTP_PASSWORD, config.ALERT_RECIPIENT_EMAIL]):
            logger.warning("SMTP e-posta ayarları eksik. .env dosyasını kontrol edin. E-posta gönderilmeyecek.")
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = config.SMTP_USERNAME
            msg['To'] = config.ALERT_RECIPIENT_EMAIL
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
            server.starttls()
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
            logger.info(f"Uyarı e-postası başarıyla gönderildi: {config.ALERT_RECIPIENT_EMAIL}")
        except Exception as e:
            logger.error(f"E-posta gönderilirken bir hata oluştu: {e}", exc_info=True)

    def check_and_dispatch_alert(self, symbol: str, analysis_result: Dict[str, Any]):
        """
        Analiz sonucunu kontrol eder ve gerekirse uyarı gönderir.
        """
        score = analysis_result.get("final_score", 0.0)
        alert_type = None

        if score >= self.bullish_threshold:
            alert_type = "BOĞA SİNYALİ"
        elif score <= self.bearish_threshold:
            alert_type = "AYI SİNYALİ"

        if alert_type:
            subject = f"OptiTrade Uyarısı: {symbol} için {alert_type}"
            body = (
                f"Otomatik uyarı sistemi tarafından bir sinyal tespit edildi.\n\n"
                f"Sembol: {symbol}\n"
                f"Sinyal Türü: {alert_type}\n"
                f"Nihai Skor: {score:.4f}\n\n"
                f"--- Detaylar ---\n"
                f"Anlık Fiyat: {analysis_result.get('current_market_price', 'N/A')}\n"
                f"Tahmini Hedef Fiyat: {analysis_result.get('estimated_target_price', 'N/A')}\n"
                f"Önerilen Pozisyon Büyüklüğü: {analysis_result.get('position_sizing', {}).get('details', 'N/A')}\n\n"
                f"Bu otomatik bir bildirimdir. Lütfen kendi araştırmanızı yapınız."
            )
            logger.info(f"{symbol} için uyarı durumu: {alert_type}. E-posta gönderiliyor...")
            self.send_email_alert(subject, body)
        else:
            logger.info(f"{symbol} için önemli bir sinyal bulunamadı (Skor: {score:.4f}).")


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
