
import numpy as np
from transformers import pipeline
import logging
from typing import List, Dict, Any, Optional
import pandas as pd

from .base_model import BaseModel
from .. import config
from ..utils.data_fetcher import DataFetcher

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class NewsSentimentModel(BaseModel):
    """
    Generates a trading signal score by performing sentiment analysis on news headlines.
    """
    def __init__(self, data_fetcher: Optional[DataFetcher] = None):
        super().__init__(data_fetcher)
        try:
            logger.info("Loading sentiment analysis model (ProsusAI/finbert)...")
            self.sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
            logger.info("Sentiment analysis model loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading Hugging Face pipeline: {e}")
            self.sentiment_pipeline = None

    def _calculate_sentiment_score(self, text: str) -> float:
        if not self.sentiment_pipeline or not isinstance(text, str) or not text.strip():
            return 0.0

        try:
            truncated_text = text[:512]
            result = self.sentiment_pipeline(truncated_text)[0]
            label = result['label']
            score = result['score']

            if label == 'positive':
                return float(score)
            elif label == 'negative':
                return float(-score)
            else: # neutral
                return 0.0
        except Exception as e:
            logger.warning(f"An error occurred during text analysis: '{text[:50]}...'. Error: {e}")
            return 0.0

    def generate_score(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """
        Generates a sentiment score based on a list of news headlines.
        """
        if not self.sentiment_pipeline:
            logger.error("Sentiment analysis model not loaded, cannot generate score.")
            return {'score': 0.0, 'details': "Sentiment model not loaded."}

        if not self.data_fetcher:
            logger.error("Data fetcher is not available, cannot fetch news headlines.")
            return {'score': 0.0, 'details': "Data fetcher not available."}

        query = kwargs.get('symbol', 'bitcoin')
        limit = kwargs.get('limit', 20)

        logger.info(f"Fetching last {limit} news headlines for query: '{query}'...")
        headlines_df = self.data_fetcher.get_news_sentiment(query, limit=limit)
        
        if headlines_df.empty:
            logger.warning("No headlines found to analyze.")
            return {'score': 0.0, 'details': "No headlines found."}

        headlines = headlines_df['title'].tolist()
        logger.info(f"Analyzing sentiment for {len(headlines)} headlines...")

        try:
            scores = [self._calculate_sentiment_score(h) for h in headlines]
            average_score = np.mean(scores) if scores else 0.0
            details = f"Analyzed {len(headlines)} headlines. Avg Score: {average_score:.4f}"
            
            logger.info(f"News Sentiment Analysis Result: {details}")
            return {'score': float(average_score), 'details': details}

        except Exception as e:
            logger.error(f"An error occurred during news sentiment prediction: {e}", exc_info=True)
            return {'score': 0.0, 'details': f"Error during prediction: {e}"}