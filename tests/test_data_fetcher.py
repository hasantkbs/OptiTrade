
import sys
import os
import pytest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.optitrade.utils.data_fetcher import NewsFetcher

@pytest.fixture
def news_fetcher():
    """Provides a NewsFetcher instance for tests."""
    return NewsFetcher()

def test_fetch_simulated_social_media_data_all(news_fetcher):
    """
    Tests that fetching with query='all' returns all messages.
    """
    # The simulated function returns 20 messages in total
    all_messages = news_fetcher.fetch_simulated_social_media_data(query='all')
    assert isinstance(all_messages, list)
    assert len(all_messages) == 20

def test_fetch_simulated_social_media_data_filtered(news_fetcher):
    """
    Tests that fetching with a specific query returns relevant messages.
    """
    filtered_messages = news_fetcher.fetch_simulated_social_media_data(query='bitcoin')
    assert isinstance(filtered_messages, list)
    # There are 3 messages containing "bitcoin" (case-insensitive)
    assert len(filtered_messages) == 2
    for msg in filtered_messages:
        assert 'bitcoin' in msg.lower()

def test_fetch_simulated_social_media_data_no_results(news_fetcher):
    """
    Tests that a query with no matches returns an empty list.
    """
    no_results = news_fetcher.fetch_simulated_social_media_data(query='nonexistentcoin')
    assert isinstance(no_results, list)
    assert len(no_results) == 0

def test_fetch_simulated_social_media_data_case_insensitivity(news_fetcher):
    """
    Tests that the query is case-insensitive.
    """
    lower_case = news_fetcher.fetch_simulated_social_media_data(query='bullish')
    upper_case = news_fetcher.fetch_simulated_social_media_data(query='BULLISH')
    assert len(lower_case) == len(upper_case)
    assert len(lower_case) > 0 # Ensure it found something
