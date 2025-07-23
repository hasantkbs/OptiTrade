# src/optitrade/models/registry.py

"""
Bu modül, projede kullanılan tüm finansal modelleri kaydeder ve yönetir.
Merkezi bir noktadan modellere erişim sağlayarak modülerliği artırır.
"""
import logging
from .. import config

from .price_trend_model import PriceTrendModel
from .volume_surge_model import VolumeSurgeModel
from .news_sentiment_model import NewsSentimentModel
from .social_sentiment_model import SocialSentimentModel
from .support_resistance_model import SupportResistanceModel
from .divergence_detection_model import DivergenceDetectionModel
from .event_impact_model import EventImpactModel
from .market_condition_classifier import MarketConditionClassifier
from .recommendation_model import RecommendationModel
from .scalping_model import ScalpingModel # Yeni model eklendi

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

# Modelleri bir sözlükte (dictionary) kaydedelim.
# Anahtar: modelin adı (küçük harf), Değer: modelin sınıfı.
MODEL_REGISTRY = {
    "price_trend": PriceTrendModel,
    "volume_surge": VolumeSurgeModel,
    "news_sentiment": NewsSentimentModel,
    "social_sentiment": SocialSentimentModel,
    "support_resistance": SupportResistanceModel,
    "divergence_detection": DivergenceDetectionModel,
    "event_impact": EventImpactModel,
    "market_condition": MarketConditionClassifier,
    "recommendation": RecommendationModel,
    "scalping": ScalpingModel, # Yeni model eklendi
}

def initialize_models() -> dict:
    """
    Kayıt defterindeki tüm modelleri başlatır ve bir sözlük olarak döndürür.

    Returns:
        dict: Başlatılmış model nesnelerini içeren bir sözlük.
              Örnek: {'price_trend': PriceTrendModel(), ...}
    """
    logger.info("Kayıt defterindeki tüm modeller başlatılıyor...")
    initialized_models = {name: model_class() for name, model_class in MODEL_REGISTRY.items()}
    logger.info("Tüm modeller başarıyla başlatıldı.")
    return initialized_models

def get_model(name: str):
    """
    Kayıtlı adı kullanarak tek bir modelin bir örneğini döndürür.

    Args:
        name (str): Kayıt defterindeki modelin adı.

    Returns:
        İstenen modelin bir örneği veya bulunamazsa None.
    """
    model_class = MODEL_REGISTRY.get(name)
    if model_class:
        return model_class()
    logger.error(f"Model '{name}' kayıt defterinde bulunamadı.")
    return None
