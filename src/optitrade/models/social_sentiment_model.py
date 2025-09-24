
import numpy as np
from transformers import pipeline
import logging
from typing import List, Dict, Any, Optional
import pandas as pd

from .base_model import BaseModel

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class SocialSentimentModel(BaseModel):
    """
    Generates a score by performing sentiment analysis on social media posts (e.g., Reddit).
    """
    def __init__(self):
        super().__init__()
        try:
            logger.info("Loading sentiment analysis model (ProsusAI/finbert) for Social Media...")
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

    def generate_score(self, data: pd.DataFrame, posts: Optional[List[str]] = None) -> float:
        """
        Generates a sentiment score based on a list of social media posts.

        Args:
            data (pd.DataFrame): Price data (not directly used by this model, but required by the base class).
            posts (Optional[List[str]], optional): A list of social media posts. Defaults to None.

        Returns:
            float: The average sentiment score.
        """
        if not self.sentiment_pipeline:
            logger.error("Sentiment analysis model not loaded, cannot generate score.")
            return 0.0

        if not posts:
            logger.warning("No posts provided to analyze.")
            return 0.0

        logger.info(f"Analyzing sentiment for {len(posts)} posts...")

        try:
            scores = [self._calculate_sentiment_score(post) for post in posts]
            average_score = np.mean(scores) if scores else 0.0
            
            logger.info(f"Social Media Sentiment Analysis Result: Average Score={average_score:.4f}")
            return float(average_score)

        except Exception as e:
            logger.error(f"An error occurred during social media sentiment prediction: {e}", exc_info=True)
            return 0.0