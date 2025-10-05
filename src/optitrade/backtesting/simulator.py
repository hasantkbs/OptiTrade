
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np
import yfinance as yf
import argparse
import random
import logging

# OptiTrade modüllerini içe aktar
from optitrade import config
from optitrade.models.registry import initialize_models
from optitrade.models.main import calculate_all_model_scores # Merkezi fonksiyon
from optitrade.scoring.scoring_engine import ScoringEngine
from optitrade.utils.data_fetcher import DataFetcher

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

class Backtester:
    """
    Encapsulates the backtesting logic.
    """
    def __init__(self, entry_threshold: float = 0.5, exit_threshold: float = -0.5, commission_rate: float = 0.001, slippage: float = 0.0005):
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.models = initialize_models()
        self.min_data_points_for_models = 60

    def run_backtest(self, prices: pd.Series, prediction_scores: pd.Series) -> dict:
        if prices.empty or prediction_scores.empty:
            return {}

        common_index = prices.index.intersection(prediction_scores.index)
        prices = prices.loc[common_index]
        prediction_scores = prediction_scores.loc[common_index]

        if prices.empty:
            return {}

        initial_capital = 1000.0
        
        # Create a DataFrame to hold all relevant data
        df = pd.DataFrame({
            'price': prices,
            'score': prediction_scores,
            'entry_signal': (prediction_scores >= self.entry_threshold),
            'exit_signal': (prediction_scores <= self.exit_threshold)
        })

        # Initialize columns for simulation
        df['position'] = 0 # 0: no position, 1: long position
        df['entry_price'] = np.nan
        df['exit_price'] = np.nan
        df['trade_return'] = np.nan
        df['capital'] = initial_capital

        current_position = 0
        current_entry_price = np.nan
        trades = []

        for i in range(1, len(df)):
            # Carry forward capital from previous day
            df.loc[df.index[i], 'capital'] = df.loc[df.index[i-1], 'capital']
            
            if current_position == 0 and df.loc[df.index[i], 'entry_signal']:
                # Enter position
                current_position = 1
                current_entry_price = df.loc[df.index[i], 'price'] * (1 + self.slippage)
                df.loc[df.index[i], 'capital'] *= (1 - self.commission_rate)
                df.loc[df.index[i], 'position'] = 1
                df.loc[df.index[i], 'entry_price'] = current_entry_price
                
            elif current_position == 1 and df.loc[df.index[i], 'exit_signal']:
                # Exit position
                current_position = 0
                exit_price = df.loc[df.index[i], 'price'] * (1 - self.slippage)
                df.loc[df.index[i], 'capital'] *= (1 - self.commission_rate)
                trade_return = (exit_price - current_entry_price) / current_entry_price
                df.loc[df.index[i], 'trade_return'] = trade_return
                df.loc[df.index[i], 'exit_price'] = exit_price
                df.loc[df.index[i], 'capital'] *= (1 + trade_return)
                
                trades.append({
                    'entry_date': df.index[i-1], # Assuming entry was on previous bar's close or current bar's open
                    'exit_date': df.index[i],
                    'entry_price': current_entry_price,
                    'exit_price': exit_price,
                    'return': trade_return
                })
                current_entry_price = np.nan # Reset entry price

        # Handle open position at the end of the backtest
        if current_position == 1:
            exit_price = df['price'].iloc[-1] * (1 - self.slippage)
            df['capital'].iloc[-1] *= (1 - self.commission_rate)
            trade_return = (exit_price - current_entry_price) / current_entry_price
            df['trade_return'].iloc[-1] = trade_return
            df['exit_price'].iloc[-1] = exit_price
            df['capital'].iloc[-1] *= (1 + trade_return)

            trades.append({
                'entry_date': df.index[-1],
                'exit_date': df.index[-1],
                'entry_price': current_entry_price,
                'exit_price': exit_price,
                'return': trade_return
            })

        final_capital = df['capital'].iloc[-1]
        return self.calculate_metrics(trades, prices, initial_capital, final_capital)

    def calculate_metrics(self, trades: list, prices: pd.Series, initial_capital: float, final_capital: float) -> dict:
        total_return = (final_capital - initial_capital) / initial_capital
        num_trades = len(trades)
        winning_trades = sum(1 for t in trades if t['return'] > 0)
        losing_trades = num_trades - winning_trades
        win_rate = winning_trades / num_trades if num_trades > 0 else 0.0

        if not prices.empty:
            cumulative_returns = (prices / prices.iloc[0]).cumprod()
            peak = cumulative_returns.expanding(min_periods=1).max()
            drawdown = (cumulative_returns - peak) / peak
            max_drawdown = drawdown.min() if not drawdown.empty else 0.0
        else:
            max_drawdown = 0.0

        trade_returns = [t['return'] for t in trades]
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
        if trade_returns:
            returns_series = pd.Series(trade_returns)
            daily_returns_std = returns_series.std()
            if daily_returns_std != 0:
                sharpe_ratio = returns_series.mean() / daily_returns_std
            
            negative_returns = returns_series[returns_series < 0]
            downside_std = negative_returns.std()
            if downside_std != 0:
                sortino_ratio = returns_series.mean() / downside_std

        calmar_ratio = total_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

        avg_trade_duration = pd.Series([(t['exit_date'] - t['entry_date']).days for t in trades]).mean()

        return {
            'total_return': float(total_return),
            'num_trades': num_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': float(win_rate),
            'max_drawdown': float(max_drawdown),
            'sharpe_ratio': float(sharpe_ratio),
            'sortino_ratio': float(sortino_ratio),
            'calmar_ratio': float(calmar_ratio),
            'avg_trade_duration': float(avg_trade_duration),
            'trades': trades
        }

    def generate_report(self, results: dict):
        print("--- Backtest Report ---")
        for key, value in results.items():
            if key != 'trades':
                print(f"{key.replace('_', ' ').title()}: {value:.2%}" if isinstance(value, float) and 'ratio' not in key else f"{key.replace('_', ' ').title()}: {value}")
        
        print("\n--- Trade Log ---")
        for trade in results['trades']:
            print(f"Entry: {trade['entry_date']} @ {trade['entry_price']:.2f}, Exit: {trade['exit_date']} @ {trade['exit_price']:.2f}, Return: {trade['return']:.2%}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Backtest simulator for the prediction engine.')
    parser.add_argument('--symbol', type=str, default='AAPL', help='Stock/crypto symbol (e.g., BTC-USD, AAPL). Default: AAPL')
    parser.add_argument('--period', type=str, default='1y', help='Data fetch period (e.g., 1y, 6mo, 1mo). Default: 1y')
    parser.add_argument('--interval', type=str, default='1d', help='Data fetch interval. Default: 1d')
    parser.add_argument('--entry_threshold', type=float, default=0.5, help='Prediction score threshold for entering a position. Default: 0.5')
    parser.add_argument('--exit_threshold', type=float, default=-0.5, help='Prediction score threshold for exiting a position. Default: -0.5')
    parser.add_argument('--commission_rate', type=float, default=0.001, help='Commission rate per trade. Default: 0.001 (0.1%)')
    parser.add_argument('--slippage', type=float, default=0.0005, help='Slippage per trade. Default: 0.0005 (0.05%)')
    parser.add_argument('--datafile', type=str, default=None, help='Local data file (CSV format). If specified, yfinance will not be used.')

    args = parser.parse_args()

    logger.info(f"--- Backtest Simulation ---")

    data = None
    if args.datafile:
        data = pd.read_csv(args.datafile, index_col=0, parse_dates=True)
    else:
        ticker = yf.Ticker(args.symbol)
        data = ticker.history(period=args.period, interval=args.interval)
    
    data.rename(columns={c: c.lower() for c in data.columns}, inplace=True)

    if data.empty:
        logger.error(f"Could not download or read data for {args.symbol}.")
    else:
        backtester = Backtester(
            entry_threshold=args.entry_threshold, 
            exit_threshold=args.exit_threshold,
            commission_rate=args.commission_rate,
            slippage=args.slippage
        )

        data_fetcher = DataFetcher()
        scoring_engine = ScoringEngine(data_fetcher=data_fetcher, db_handler=None)

        logger.info("Pre-calculating all individual model scores...")
        all_model_scores_df = calculate_all_model_scores(data, backtester.models, interval=args.interval)

        logger.info("Combining individual model scores into final prediction scores...")
        prediction_scores_series = scoring_engine.run_engine(
            all_model_scores_df=all_model_scores_df,
            asset_type='stock', # Assuming 'stock' for now, can be made dynamic from args
            symbol=args.symbol,
            interval=args.interval
        )
        prediction_scores_series = prediction_scores_series.fillna(0.0)

        results = backtester.run_backtest(data['close'], prediction_scores_series)
        backtester.generate_report(results)
