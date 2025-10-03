
import argparse
import itertools
import json
import logging
import pandas as pd
import yfinance as yf
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.optitrade.backtesting.simulator import Backtester
from src.optitrade.config_optimizer import OPTIMIZABLE_PARAMETERS
from src.optitrade.models.base_model import BaseModel
from src.optitrade.models.registry import initialize_models, get_model

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Optimize model parameters.")
    parser.add_argument("--symbol", type=str, required=True, help="The symbol to optimize for (e.g., 'AAPL').")
    parser.add_argument("--interval", type=str, default="1d", help="The interval to optimize for (e.g., '1d').")
    parser.add_argument("--model", type=str, required=True, help="The model to optimize (e.g., 'PriceTrendModel').")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Initialize the model registry
    initialize_models()

    if args.model not in OPTIMIZABLE_PARAMETERS:
        logger.error(f"Model '{args.model}' is not configured for optimization.")
        return

    logger.info(f"Optimizing parameters for {args.model} on {args.symbol} ({args.interval})...")

    # Load historical data
    ticker = yf.Ticker(args.symbol)
    data = ticker.history(period="5y", interval=args.interval)
    if data.empty:
        logger.error(f"Could not download data for {args.symbol}.")
        return

    data.rename(columns={c: c.lower() for c in data.columns}, inplace=True)

    # Get the parameter grid for the specified model
    param_grid = OPTIMIZABLE_PARAMETERS[args.model]
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())

    best_params = None
    best_performance = -float('inf')

    # Grid search
    for params_combination in itertools.product(*param_values):
        params = dict(zip(param_names, params_combination))
        logger.info(f"Testing parameters: {params}")

        # Initialize the model with the current parameter combination
        # No need to re-initialize all models, just get the one we need.
        model_to_optimize = get_model(args.model)
        if not model_to_optimize:
            logger.error(f"Could not initialize model '{args.model}'. Skipping... ")
            continue

        for param_name, param_value in params.items():
            setattr(model_to_optimize, param_name, param_value)

        # Run the backtest by generating a score for each point in time
        simulator = Backtester()
        all_scores = []
        min_data_points = 60 # A reasonable minimum number of points for TA indicators

        for i in range(len(data)):
            if i < min_data_points:
                all_scores.append(0.0) # Append neutral score for initial period
                continue
            
            historical_data = data.iloc[:i+1]
            score_result = model_to_optimize.generate_score(historical_data)
            all_scores.append(score_result.get('score', 0.0))

        scores_series = pd.Series(all_scores, index=data.index).fillna(0.0)

        results = simulator.run_backtest(data['close'], scores_series)

        # Evaluate performance
        # Use a composite metric like Calmar ratio or Sharpe ratio if available, otherwise total_return
        performance = results.get('calmar_ratio', results.get('total_return', 0.0))
        if performance > best_performance:
            best_performance = performance
            best_params = params
            logger.info(f"New best parameters found: {best_params} (Performance Metric: {best_performance:.4f})")

    logger.info(f"Optimization finished.")
    logger.info(f"Best parameters for {args.model} on {args.symbol} ({args.interval}): {best_params}")
    logger.info(f"Best performance (total return): {best_performance:.2f}")

    # Store the best parameters
    with open(f"optimized_parameters_{args.model}_{args.symbol}_{args.interval}.json", "w") as f:
        json.dump(best_params, f, indent=4)

if __name__ == "__main__":
    main()
