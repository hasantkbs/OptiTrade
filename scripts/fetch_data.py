import yfinance as yf
import pandas as pd
import os
import argparse

def fetch_yfinance_data(symbol: str, interval: str, period: str, output_dir: str = 'data'):
    """
    Fetches historical market data from Yahoo Finance and saves it to a CSV file.

    Args:
        symbol (str): The stock/crypto symbol (e.g., 'BTC-USD', 'AAPL').
        interval (str): The data interval (e.g., '1h', '1d', '5m').
        period (str): The time period for the data (e.g., '1y', '6mo', 'max').
        output_dir (str): The directory to save the output CSV file.
    """
    print(f"Fetching {interval} data for {symbol} over the last {period}...")
    
    try:
        # Download data from yfinance
        data = yf.download(tickers=symbol, period=period, interval=interval)

        if data.empty:
            print(f"Error: No data found for symbol {symbol}. It might be an invalid ticker or delisted.")
            return

        # Ensure the output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Create a descriptive filename
        filename = f"{symbol.replace('=', '_')}_{interval}.csv"
        output_path = os.path.join(output_dir, filename)

        # Save the data to a CSV file
        data.to_csv(output_path)
        print(f"Successfully saved data to {output_path}")

    except Exception as e:
        print(f"An error occurred while fetching or saving data: {e}")

if __name__ == "__main__":
    # --- Command-Line Argument Parsing ---
    parser = argparse.ArgumentParser(description="Fetch historical market data from Yahoo Finance.")
    
    parser.add_argument(
        "--symbol", 
        type=str, 
        required=True, 
        help="The stock/crypto symbol to fetch (e.g., 'BTC-USD')."
    )
    parser.add_argument(
        "--interval", 
        type=str, 
        default="1h", 
        help="The data interval (e.g., '1m', '15m', '1h', '1d'). Default is '1h'."
    )
    parser.add_argument(
        "--period", 
        type=str, 
        default="1y", 
        help="The time period for the data (e.g., '1mo', '1y', 'max'). Default is '1y'."
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="data",
        help="The directory to save the output CSV file. Default is 'data'."
    )

    args = parser.parse_args()

    # --- Fetch Data ---
    fetch_yfinance_data(args.symbol, args.interval, args.period, args.output_dir)
