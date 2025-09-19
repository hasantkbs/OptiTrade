import sys
import os
import logging

sys.path.insert(0, '/Users/hasantekbas/Downloads/Algorix Project Doc/OptiTrade/OptiTradeCode/src')

from optitrade.models.news_sentiment_model import NewsSentimentModel
from optitrade.utils.data_fetcher import DataFetcher
from optitrade import config

# Ensure logging is configured for this script
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def test_news_sentiment_model():
    fetcher = DataFetcher()
    model = NewsSentimentModel(data_fetcher=fetcher)

    test_sentences = [
        "Bitcoin price surged by 10% today, indicating strong bullish momentum.", # Clearly positive
        "The crypto market experienced a sharp decline, leading to significant losses.", # Clearly negative
        "The price of Bitcoin remained stable over the past week.", # Neutral
        "", # Empty string
        "   ", # Whitespace string
        "This is a very good investment opportunity.", # General positive
        "This stock is going to crash hard.", # General negative
    ]

    logger.info("\n--- Direct NewsSentimentModel Test ---")
    for i, sentence in enumerate(test_sentences):
        try:
            score = model._calculate_sentiment_score(sentence)
            logger.info(f"Sentence {i+1}: '{sentence[:50]}...\n  Score: {score:.4f}")
        except Exception as e:
            logger.error(f"Error analyzing sentence '{sentence[:50]}...': {e}")

if __name__ == '__main__':
    test_news_sentiment_model()
