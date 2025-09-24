
import pandas as pd
import numpy as np
import yfinance as yf
import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

class PortfolioOptimizer:
    """
    Optimizes a portfolio based on Modern Portfolio Theory (MPT).
    """
    def __init__(self, risk_free_rate: float = 0.02):
        self.risk_free_rate = risk_free_rate

    def get_historical_data(self, symbols: List[str], start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetches historical adjusted close prices for a list of symbols.
        """
        data = yf.download(symbols, start=start_date, end=end_date)['Adj Close']
        return data.dropna()

    def calculate_returns_and_covariance(self, data: pd.DataFrame) -> Tuple[pd.Series, pd.DataFrame]:
        """
        Calculates daily returns and the covariance matrix.
        """
        returns = data.pct_change().dropna()
        annual_returns = returns.mean() * 252
        covariance_matrix = returns.cov() * 252
        return annual_returns, covariance_matrix

    def generate_random_portfolios(self, num_portfolios: int, annual_returns: pd.Series, covariance_matrix: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Generates random portfolios and calculates their expected return, volatility, and Sharpe ratio.
        """
        num_assets = len(annual_returns)
        results = []

        for _ in range(num_portfolios):
            weights = np.random.random(num_assets)
            weights /= np.sum(weights)

            portfolio_return = np.sum(weights * annual_returns)
            portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(covariance_matrix, weights)))
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_volatility

            results.append({
                'return': portfolio_return,
                'volatility': portfolio_volatility,
                'sharpe_ratio': sharpe_ratio,
                'weights': weights
            })
        return results

    def optimize_portfolio(self, symbols: List[str], start_date: str, end_date: str, num_portfolios: int = 10000) -> Dict[str, Any]:
        """
        Performs portfolio optimization and returns the optimal portfolio.
        """
        logger.info(f"Optimizing portfolio for symbols: {symbols} from {start_date} to {end_date}...")
        data = self.get_historical_data(symbols, start_date, end_date)
        if data.empty:
            logger.error("Not enough historical data to perform portfolio optimization.")
            return {}

        annual_returns, covariance_matrix = self.calculate_returns_and_covariance(data)
        random_portfolios = self.generate_random_portfolios(num_portfolios, annual_returns, covariance_matrix)

        # Find the portfolio with the maximum Sharpe ratio
        optimal_portfolio = max(random_portfolios, key=lambda x: x['sharpe_ratio'])

        logger.info("Portfolio optimization completed.")
        return {
            'optimal_return': optimal_portfolio['return'],
            'optimal_volatility': optimal_portfolio['volatility'],
            'optimal_sharpe_ratio': optimal_portfolio['sharpe_ratio'],
            'optimal_weights': dict(zip(symbols, optimal_portfolio['weights']))
        }

if __name__ == '__main__':
    # Example Usage
    optimizer = PortfolioOptimizer()
    symbols = ['AAPL', 'MSFT', 'GOOG', 'AMZN']
    start_date = '2020-01-01'
    end_date = '2023-01-01'

    optimal_portfolio = optimizer.optimize_portfolio(symbols, start_date, end_date)

    if optimal_portfolio:
        print("Optimal Portfolio:")
        print(f"  Expected Return: {optimal_portfolio['optimal_return']:.2%}")
        print(f"  Expected Volatility: {optimal_portfolio['optimal_volatility']:.2%}")
        print(f"  Sharpe Ratio: {optimal_portfolio['optimal_sharpe_ratio']:.2f}")
        print("  Weights:")
        for symbol, weight in optimal_portfolio['optimal_weights'].items():
            print(f"    {symbol}: {weight:.2%}")
