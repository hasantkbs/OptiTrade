# Crypto News API

A Python-based API client for fetching cryptocurrency news from CryptoPanic.

## Features

- Fetch cryptocurrency news with various filters
- Support for multiple currency-specific news
- JSON response formatting
- Error handling and validation

## Available Filters

- Rising Posts
- Hot Posts
- Bullish Posts
- Bearish Posts
- Important Posts
- Saved Posts
- Funny Posts

## Setup

1. Install dependencies:
```bash
pip install requests
```

2. Get your API key from CryptoPanic

3. Initialize the API client:
```python
from news import CryptoNewsFetcher

api_key = "YOUR_API_KEY"
news_fetcher = CryptoNewsFetcher(api_key)
```

## Usage

```python
# Fetch rising posts
news = news_fetcher.fetch_currency_news(filter_type="rising")

# Fetch bullish posts for specific currencies
news = news_fetcher.fetch_currency_news(
    filter_type="bullish",
    currencies="BTC,ETH"
)
```

## Error Handling

The API client includes built-in error handling. Invalid filter types will be caught and reported.

## Directory Structure

- `Json/newsjson/`: Directory for storing JSON responses

## Note

Make sure to replace `YOUR_API_KEY` with your actual CryptoPanic API key before using the API client.
