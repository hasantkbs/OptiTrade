
import argparse
import itertools
import json
import logging
import pandas as pd
import yfinance as yf

from src.optitrade.backtesting.simulator import BacktestSimulator
from src.optitrade.config_optimizer import OPTIMIZABLE_PARAMETERS
from src.optitrade.models import BaseModel
from src.optitrade.models.registry import initialize_models

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Optimize model parameters.")
    parser.add_argument("--symbol", type=str, required=True, help="The symbol to optimize for (e.g., 'AAPL').")
    parser.add_argument("--interval", type=str, default="1d", help="The interval to optimize for (e.g., '1d').")
    parser.add_argument("--model", type=str, required=True, help="The model to optimize (e.g., 'PriceTrendModel').")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

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
        models = initialize_models()
        model_to_optimize = models[args.model]
        for param_name, param_value in params.items():
            setattr(model_to_optimize, param_name, param_value)

        # Run the backtest
        simulator = BacktestSimulator()
        # The backtesting logic needs to be adapted to use the single model with the specified parameters
        # This is a simplified example and needs to be fleshed out.
        # For now, we'll just simulate a simple scenario where the score is based on the single model.
        scores = model_to_optimize.generate_score(data)
        results = simulator._run_single_backtest(data['Close'], scores)

        # Evaluate performance
        performance = results['total_return']
        if performance > best_performance:
            best_performance = performance
            best_params = params
            logger.info(f"New best parameters found: {best_params} (Performance: {best_performance:.2f})")

    logger.info(f"Optimization finished.")
    logger.info(f"Best parameters for {args.model} on {args.symbol} ({args.interval}): {best_params}")
    logger.info(f"Best performance (total return): {best_performance:.2f}")

    # Store the best parameters
    with open(f"optimized_parameters_{args.model}_{args.symbol}_{args.interval}.json", "w") as f:
        json.dump(best_params, f, indent=4)

if __name__ == "__main__":
    main()
