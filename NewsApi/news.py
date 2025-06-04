import requests
import json
from datetime import datetime
import argparse
import os

# Available filter options
FILTER_OPTIONS = {
    "rising": "Rising Posts",
    "hot": "Hot Posts",
    "bullish": "Bullish Posts",
    "bearish": "Bearish Posts",
    "important": "Important Posts",
    "saved": "Saved Posts",
    "lol": "Funny Posts"
}

class CryptoNewsFetcher:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://cryptopanic.com/api/developer/v2/posts/"
        self.json_dir = "Json/newsjson"
        
        # Create directory for JSON files
        os.makedirs(self.json_dir, exist_ok=True)

    def fetch_currency_news(self, filter_type="rising", currencies=None):
        """
        Fetch cryptocurrency news with specified filter
        
        Args:
            filter_type (str): Type of posts to fetch
            currencies (str): Optional, comma-separated list of currency codes
        
        Returns:
            dict: API response data
        """
        if filter_type not in FILTER_OPTIONS:
            print(f"❌ Invalid filter type. Available options: {', '.join(FILTER_OPTIONS.keys())}")
            return None

        params = [f"auth_token={self.api_key}", f"filter={filter_type}"]
        if currencies:
            params.append(f"currencies={currencies}")
        
        url = f"{self.base_url}?{'&'.join(params)}"
        
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

    def save_to_json(self, data, filter_type, currencies=None):
        """
        Save news data to a JSON file
        
        Args:
            data (dict): News data to save
            filter_type (str): Type of posts fetched
            currencies (str): Optional, currencies used for the request
        
        Returns:
            str: The full path to the saved file
        """
        if not data:
            print("❌ No data to save")
            return None

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"news-{filter_type}-{timestamp}.json"
        filepath = os.path.join(self.json_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"✅ Data saved to {filepath}")
            return filepath
        except Exception as e:
            print(f"❌ Error saving to file: {str(e)}")
            return None

def main():
    parser = argparse.ArgumentParser(description='Crypto News Fetcher')
    parser.add_argument('--filter', '-f', default='rising',
                      help=f'Filter type: {", ".join(FILTER_OPTIONS.keys())} (default: rising)')
    parser.add_argument('--currencies', '-c',
                      help='Comma-separated list of currencies (e.g., "BTC,ETH")')
    
    args = parser.parse_args()
    
    # Initialize the fetcher
    fetcher = CryptoNewsFetcher("dc861fb4aa2833fcbc76e0644aa96005371867ff")
    
    print(f"\nFetching {FILTER_OPTIONS.get(args.filter, 'Unknown')}...")
    
    # Fetch data
    data = fetcher.fetch_currency_news(args.filter, args.currencies)
    
    if not data:
        print("❌ No data received from API")
        return
    
    # Save data
    filepath = fetcher.save_to_json(data, args.filter, args.currencies)
    if filepath:
        print(f"\nData saved successfully to {filepath}")
        print("\nFirst post preview:")
        if data.get('posts'):
            print(json.dumps(data['posts'][0], indent=2))

if __name__ == "__main__":
    main()
