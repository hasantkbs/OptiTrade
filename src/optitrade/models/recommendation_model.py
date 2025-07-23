# src/optitrade/models/recommendation_model.py
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

class RecommendationModel:
    """
    Nihai tahmin skorunu yorumlayarak kullanıcıya alım/satım önerisi sunan model.
    """
    def __init__(self):
        pass

    def get_recommendation(self, score: float) -> str:
        """
        Verilen skora göre bir alım/satım önerisi döndürür.

        Args:
            score (float): Nihai tahmin skoru (-1.0 ile +1.0 arası).

        Returns:
            str: Yorumlayıcı bir mesaj.
        """
        if score >= 0.7:
            return "🚀 Güçlü Alım: Piyasa çok güçlü bir yükseliş potansiyeli gösteriyor."
        elif score >= 0.3:
            return "📈 Alım: Hafif yükseliş eğilimi gözleniyor, alım düşünülebilir."
        elif score > -0.3:
            return "⚖️ Nötr: Piyasa belirsiz veya yatay seyrediyor, beklemede kalınması önerilir."
        elif score > -0.7:
            return "📉 Satım: Hafif düşüş eğilimi gözleniyor, satım düşünülebilir."
        else:
            return "🔻 Güçlü Satım: Piyasa ciddi bir düşüş potansiyeli gösteriyor."

if __name__ == '__main__':
    model = RecommendationModel()

    logger.info("--- Öneri Modeli Testleri ---")
    logger.info(f"Skor 0.85: {model.get_recommendation(0.85)}")
    logger.info(f"Skor 0.50: {model.get_recommendation(0.50)}")
    logger.info(f"Skor 0.10: {model.get_recommendation(0.10)}")
    logger.info(f"Skor -0.20: {model.get_recommendation(-0.20)}")
    logger.info(f"Skor -0.55: {model.get_recommendation(-0.55)}")
    logger.info(f"Skor -0.90: {model.get_recommendation(-0.90)}")
    logger.info(f"Skor 0.00: {model.get_recommendation(0.00)}")
