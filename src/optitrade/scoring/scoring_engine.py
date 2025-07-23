import pandas as pd
import numpy as np
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

class ScoringEngine:
    """
    Tüm modüllerden gelen skorları normalize eden, ağırlıklandıran ve nihai sinyali üreten modül.
    Kullanır: Dinamik ağırlıklar (şimdilik sabit), Rule-based ensemble.
    Girdi: Her modülden gelen skorlar/sinyaller.
    Çıktı: Nihai tahmin skoru (örneğin: 0.87 = güçlü yükseliş beklentisi).
    """
    def __init__(self, weights: dict = None):
        """
        Skorlama motorunu başlatır ve ağırlıkları ayarlar.
        Ağırlıklar, her bir modelin nihai skora ne kadar katkıda bulunacağını belirler.
        """
        # Varsayılan ağırlıklar (örnek değerler, gerçek uygulamada optimize edilmelidir)
        self.weights = {
            'price_trend_score': 0.21773025243026592,
            'volume_surge_score': 0.0020709694665006113,
            'news_sentiment_score': 0.05955564025575321,
            'social_sentiment_score': 0.3155263168580502,
            'support_resistance_score': 0.122087633428514,
            'divergence_score': 0.13685878387299963,
            'event_impact_score': 0.14617040368791645,
            'scalping_score': 0.10, # Yeni eklenen scalping skoru için başlangıç ağırlığı
        }
        # market_condition_score is handled separately and should not be in weights
        if weights:
            self.weights.update(weights)
        
        # Ağırlıkların toplamı 1 olmalı, değilse normalize et
        total_weight = sum(self.weights.values())
        if total_weight != 0:
            self.weights = {k: v / total_weight for k, v in self.weights.items()}

    def generate_final_score(self, model_scores: dict) -> float:
        """
        Farklı modellerden gelen skorları birleştirerek nihai bir tahmin skoru üretir.

        Args:
            model_scores (dict): Her bir modelden gelen skorları içeren sözlük.
                                 Örnek: {'price_trend_score': 0.5, 'news_sentiment_score': -0.2, ...}
                                 'market_condition_score': 'bull'/'bear'/'sideways' de içerebilir.

        Returns:
            float: Nihai tahmin skoru (genellikle -1.0 ile 1.0 arası).
        """
        final_score = 0.0
        for score_name, weight in self.weights.items():
            score_value = model_scores.get(score_name)
            if score_value is None or not isinstance(score_value, (int, float)):
                score_value = 0.0
            final_score += float(score_value) * weight
        
        # Piyasa koşuluna göre skoru ayarla
        market_condition = model_scores.get('market_condition_score', 'sideways')
        adjustment_factor = 1.0

        if market_condition == 'bull':
            # Boğa piyasasında pozitif skorları biraz artır, negatifleri azalt
            adjustment_factor = 1.1 if final_score > 0 else 0.9
        elif market_condition == 'bear':
            # Ayı piyasasında negatif skorları biraz artır, pozitifleri azalt
            adjustment_factor = 0.9 if final_score > 0 else 1.1
        
        final_score *= adjustment_factor

        # Nihai skoru -1.0 ile 1.0 arasına sıkıştır
        return float(np.tanh(final_score)) # tanh fonksiyonu -1 ile 1 arasına sıkıştırır

if __name__ == '__main__':
    # Örnek kullanım
    # Farklı modellerden gelen varsayımsal skorlar
    example_scores = {
        'price_trend_score': 0.7,      # Yükseliş
        'volume_surge_score': 0.3,     # Hafif hacim artışı
        'news_sentiment_score': 0.8,   # Çok pozitif haberler
        'social_sentiment_score': 0.6, # Pozitif sosyal medya
        'support_resistance_score': 0.9, # Dirence çok yakın
        'divergence_score': 0.0,       # Uyumsuzluk yok
        'event_impact_score': 0.5,     # Pozitif olay etkisi
        'market_condition_score': 'bull' # Piyasa koşulu
    }

    # Varsayılan ağırlıklarla motoru başlat
    engine = ScoringEngine()
    final_prediction = engine.generate_final_score(example_scores)
    logger.info(f"--- Nihai Tahmin Skoru (Varsayılan Ağırlıklarla) ---")
    logger.info(f"Nihai Skor: {final_prediction:.2f}")

    # Özel ağırlıklarla motoru başlat
    custom_weights = {
        'price_trend_score': 0.4,
        'news_sentiment_score': 0.3,
        'social_sentiment_score': 0.2,
        'event_impact_score': 0.1,
    }
    custom_engine = ScoringEngine(weights=custom_weights)
    custom_final_prediction = custom_engine.generate_final_score(example_scores)
    logger.info(f"--- Nihai Tahmin Skoru (Özel Ağırlıklarla) ---")
    logger.info(f"Nihai Skor: {custom_final_prediction:.2f}")

    # Düşüş senaryosu
    bearish_scores = {
        'price_trend_score': -0.7,
        'volume_surge_score': -0.3,
        'news_sentiment_score': -0.8,
        'social_sentiment_score': -0.6,
        'support_resistance_score': 0.1, # Destekten uzakta
        'divergence_score': -0.5, # Ayı uyumsuzluğu
        'event_impact_score': -0.5,
        'market_condition_score': 'bear' # Piyasa koşulu
    }
    bearish_prediction = engine.generate_final_score(bearish_scores)
    logger.info(f"--- Nihai Tahmin Skoru (Düşüş Senaryosu) ---")
    logger.info(f"Nihai Skor: {bearish_prediction:.2f}")

    # Yatay senaryo
    sideways_scores = {
        'price_trend_score': 0.1,
        'volume_surge_score': 0.0,
        'news_sentiment_score': 0.0,
        'social_sentiment_score': 0.0,
        'support_resistance_score': 0.5,
        'divergence_score': 0.0,
        'event_impact_score': 0.0,
        'market_condition_score': 'sideways' # Piyasa koşulu
    }
    sideways_prediction = engine.generate_final_score(sideways_scores)
    logger.info(f"--- Nihai Tahmin Skoru (Yatay Senaryo) ---")
    logger.info(f"Nihai Skor: {sideways_prediction:.2f}")