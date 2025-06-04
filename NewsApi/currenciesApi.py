import requests
import json
from datetime import datetime
import argparse
import os

class CryptoNewsFetcher:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://cryptopanic.com/api/developer/v2/posts/"
        self.json_dir = "json/currenciesJson"
        
        # Create the directory if it doesn't exist
        try:
            os.makedirs(self.json_dir, exist_ok=True)
        except Exception as e:
            print(f"❌ Error creating directory: {str(e)}")
            self.json_dir = ""  # Fallback to current directory if needed
        
    def fetch_currency_news(self, currencies):
        """
        Fetch cryptocurrency news for specific currencies
        
        Args:
            currencies (str): Comma-separated list of currency codes (e.g., "BTC,ETH")
        
        Returns:
            dict: API response data
        """
        url = f"{self.base_url}?auth_token={self.api_key}&currencies={currencies}"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ API Error: {str(e)}")
            return None
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return None

    def save_to_timestamped_json(self, data, currencies):
        """
        Save news data to a timestamped JSON file in the dedicated directory
        
        Args:
            data (dict): News data to save
            currencies (str): Currencies used for the request
            
        Returns:
            str: The full path to the saved file
        """
        if not data:
            print("❌ No data to save")
            return None

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"news-{timestamp}.json"
        filepath = os.path.join(self.json_dir, filename) if self.json_dir else filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"✅ Data saved to {filepath}")
            return filepath
        except Exception as e:
            print(f"❌ Error saving to file: {str(e)}")
            return None

    def process_with_sentiment(self, data, sentiment_model):
        """
        Process news posts with sentiment analysis
        
        Args:
            data (dict): News data from API
            sentiment_model: Pre-trained sentiment analysis model
            
        Returns:
            list: Processed posts with sentiment analysis
        """
        if not data or "posts" not in data:
            print("❌ No posts found in data")
            return None

        results = []
        for post in data["posts"]:
            try:
                sentiment = sentiment_model(post["title"])
                result = {
                    "title": post["title"],
                    "url": post["url"],
                    "published_at": post["published_at"],
                    "sentiment": sentiment
                }
                results.append(result)
            except Exception as e:
                print(f"❌ Error processing post: {str(e)}")
                continue

        return results

def main():
    parser = argparse.ArgumentParser(description='Fetch cryptocurrency news')
    parser.add_argument('--currencies', '-c', default='BTC,ETH',
                        help='Comma-separated list of currencies (default: BTC,ETH)')
    parser.add_argument('--sentiment', '-s', action='store_true',
                        help='Process news with sentiment analysis (not implemented yet)')
    
    args = parser.parse_args()
    
    # Initialize the fetcher
    fetcher = CryptoNewsFetcher("dc861fb4aa2833fcbc76e0644aa96005371867ff")
    
    print(f"Fetching news for currencies: {args.currencies}")
    
    # Fetch data
    data = fetcher.fetch_currency_news(args.currencies)
    
    if not data:
        print("❌ No data received from API")
        return
    
    # Save to timestamped JSON
    filename = fetcher.save_to_timestamped_json(data, args.currencies)
    if filename:
        print(f"\nData saved successfully to {filename}")
        print("\nFirst post preview:")
        if data.get('posts'):
            print(json.dumps(data['posts'][0], indent=2))
    
    # Process with sentiment analysis (commented out for now)
    if args.sentiment:
        print("\nProcessing with sentiment analysis (not implemented yet)")
        # TODO: Implement sentiment analysis
        # Example:
        # from transformers import pipeline
        # sentiment_model = pipeline("sentiment-analysis")
        # processed_data = fetcher.process_with_sentiment(data, sentiment_model)
        # if processed_data:
        #     print("\nProcessed posts with sentiment:")
        #     for post in processed_data[:2]:
        #         print(json.dumps(post, indent=2))

if __name__ == "__main__":
    main()