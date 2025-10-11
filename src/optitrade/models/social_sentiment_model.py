
import numpy as np
import torch
from transformers import pipeline
import logging
from typing import List, Dict, Any, Optional
import pandas as pd

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class SocialSentimentModel(BaseModel):
    """
    Generates a score by performing sentiment analysis on social media posts (e.g., Reddit).
    """
    def __init__(self, data_fetcher: Optional[DataFetcher] = None):
        super().__init__(data_fetcher)
        try:
            import torch
            logger.info("Loading sentiment analysis model (ProsusAI/finbert) for Social Media...")
            self.sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
            logger.info("Sentiment analysis model loaded successfully.")
        except ImportError:
            logger.error("PyTorch (torch) kütüphanesi bulunamadı. SocialSentimentModel devre dışı bırakıldı.")
            self.sentiment_pipeline = None
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

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        """
        Generates a sentiment score based on a list of social media posts.
        """
        if not self.sentiment_pipeline:
            logger.error("Sentiment analysis model not loaded, cannot generate score.")
            return {'score': 0.0, 'details': "Sentiment model not loaded."}

        if not self.data_fetcher:
            logger.error("Data fetcher is not available, cannot fetch social media posts.")
            return {'score': 0.0, 'details': "Data fetcher not available."}

        # kwargs'tan sembolü al, yoksa genel bir anahtar kelime kullan
        query = kwargs.get('symbol', 'bitcoin') # Varsayılan olarak 'bitcoin'
        limit = kwargs.get('limit', 25) # Analiz edilecek gönderi sayısı

        logger.info(f"Fetching last {limit} social media posts for query: '{query}'...")
        posts = self.data_fetcher.get_social_media_sentiment(query, limit=limit)

        if not posts:
            logger.warning("No posts found to analyze.")
            return {'score': 0.0, 'details': "No posts found."}

        logger.info(f"Analyzing sentiment for {len(posts)} posts...")

        try:
            scores = [self._calculate_sentiment_score(post['title']) for post in posts]
            average_score = np.mean(scores) if scores else 0.0
            details = f"Analyzed {len(posts)} posts. Avg Score: {average_score:.4f}"
            
            logger.info(f"Social Media Sentiment Analysis Result: {details}")
            return {'score': float(average_score), 'details': details}

        except Exception as e:
            logger.error(f"An error occurred during social media sentiment prediction: {e}", exc_info=True)
            return {'score': 0.0, 'details': f"Error during prediction: {e}"}