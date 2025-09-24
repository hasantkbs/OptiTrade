# OptiTrade

OptiTrade is an AI-powered trading signal generation and analysis platform. It analyzes market data using various financial models, generates trading signals, and evaluates these signals through a scoring engine. The platform offers backtesting capabilities to simulate strategy performance.

## Key Features & Enhancements

-   **Modular & Extensible Architecture:** Core components (Data Fetching, Models, Scoring Engine, API) are designed for modularity, allowing easy integration of new models and data sources.
-   **Centralized Data Fetching (`DataFetcher`):** A unified service for fetching market data (historical via yfinance, real-time via Binance WebSocket), news, and social media sentiment.
-   **Diverse & Standardized Financial Models:**
    -   **Price Trend Model:** Analyzes price movements using RSI, MACD, SMA, and ADX.
    -   **Volume Surge Model:** Detects anomalies in trading volume and their impact.
    -   **News Sentiment Model:** Analyzes news headlines using FinBERT for sentiment.
    -   **Social Sentiment Model:** Analyzes social media (Reddit) posts using FinBERT for sentiment.
    -   **Support/Resistance Model:** Identifies key support and resistance levels.
    -   **Divergence Detection Model:** Detects bullish/bearish divergences between price and indicators (e.g., RSI).
    -   **Advanced Chart Pattern Recognition (`FormationDetectionModel`):** Identifies classic chart patterns like Head & Shoulders, Inverse Head & Shoulders, Double Top/Bottom, Ascending Triangle, and Descending Triangle.
    -   **Machine Learning Model (`XGBoost`):** A data-driven model trained on historical features to predict future price direction. Supports interval-specific training, now enhanced with financial ratios for stock analysis.
    -   **Financial Ratio Model:** Calculates and scores various financial ratios (P/E, P/B, D/E, EPS Growth, P/S, EBITDA Margin) for stock fundamental analysis.
    -   **Dividend Discount Model (DDM):** Estimates the intrinsic value of dividend-paying stocks.
-   **Dynamic Signal Scoring Engine:** Comprehensively evaluates and combines signals from all integrated models using configurable weights to generate a final trading score.
-   **Real-time Data Capability:** Integration with Binance Futures WebSocket API for live crypto data streams and Alpha Vantage for real-time stock data polling, enabling continuous analysis and visualization.
-   **Parameter Optimization Framework:** Automates the optimization of model parameters (e.g., window sizes, thresholds) for each asset type and time interval.
-   **Enhanced Backtesting Module:** Provides advanced backtesting capabilities, measuring strategy performance with metrics like total return, Sharpe ratio, Sortino ratio, Calmar ratio, max drawdown, and detailed trade logs.
-   **Portfolio Optimization:** Suggests optimized portfolios based on the user's risk profile using Modern Portfolio Theory.
-   **Interactive Web Interface (Frontend):**
    -   User-friendly interface for selecting symbols and analysis intervals.
    -   Displays the final signal score, current market price, and a clear prediction direction (Rise/Fall/Neutral).
    -   Provides detailed explanations for each model's individual score, offering transparency into the signal generation process.
    -   Visualizes model score distribution using interactive charts.
    -   Real-time visualization of support/resistance levels and detected chart formations.
-   **Configurable Analysis Intervals:** Users can select analysis intervals (15m, 4h, 1d). **Important Note:** While the system can fetch data and run models at different intervals, the internal parameters of rule-based models are heuristically scaled, and the Machine Learning model requires separate training for each interval. For optimal performance, each model's parameters should be specifically optimized (e.g., via backtesting) for each desired interval.

## Setup

Follow these steps to set up and run the OptiTrade project on your local machine:

### Prerequisites

-   Python 3.8+
-   Conda (Anaconda or Miniconda)
-   Node.js & npm (for frontend)

### Steps

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/hasantkbs/OptiTrade.git
    cd OptiTrade
    ```

2.  **Create and Activate Conda Environment:**
    Use the `environment.yml` file to create a Conda environment with all necessary dependencies for the project:
    ```bash
    conda env create -f environment.yml
    conda activate optitrade_env
    ```

3.  **Install Required Python Packages:**
    Install additional packages specified in `requirements.txt`:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Train Machine Learning Models (Crucial for ML Model Functionality):**
    The Machine Learning model needs to be trained for each desired analysis interval. Run the following commands:
    ```bash
    python scripts/train_model.py --interval 1d --symbol BTC-USD
    python scripts/train_model.py --interval 4h --symbol BTC-USD
    python scripts/train_model.py --interval 15m --symbol BTC-USD
    python scripts/train_model.py --interval 1d --symbol AAPL
    ```

## Usage

The OptiTrade application includes both a backend API server and a frontend web interface. To run the application, you need to use two separate terminal windows.

After activating your Conda environment (see setup steps above), follow these steps:

### Terminal 1: Backend (API Server)

1.  Open a new terminal window.
2.  Navigate to the project's root directory:
    ```bash
    cd /path/to/OptiTradeCode/
    ```
3.  Activate your Conda environment:
    ```bash
    conda activate optitrade_env
    ```
4.  Start the FastAPI server:
    ```bash
    uvicorn src.optitrade.api.server:app --reload
    ```
    Keep this terminal window open. The server will continue to run.

### Terminal 2: Frontend (Web Interface)

1.  Open another new terminal window.
2.  Navigate to the project's root directory:
    ```bash
    cd /path/to/OptiTradeCode/
    ```
3.  Activate your Conda environment:
    ```bash
    conda activate optitrade_env
    ```
4.  Navigate to the frontend folder:
    ```bash
    cd frontend
    ```
5.  Install Node.js dependencies:
    ```bash
    npm install
    ```
6.  Start the React development server:
    ```bash
    npm start
    ```
    This command will automatically open `http://localhost:3000` in your web browser. If it doesn't, you can manually paste this address into your browser.

### Terminal 3: Real-time Data Stream & Analysis

1.  Open another new terminal window.
2.  Navigate to the project's root directory:
    ```bash
    cd /path/to/OptiTradeCode/
    ```
3.  Activate your Conda environment:
    ```bash
    conda activate optitrade_env
    ```
4.  Start the real-time analysis for crypto (e.g., BTCUSDT):
    ```bash
    python scripts/run_realtime_analysis.py --source crypto --symbol btcusdt@markPrice@1s
    ```
    Or for stocks (e.g., IBM):
    ```bash
    python scripts/run_realtime_analysis.py --source stock --symbol IBM
    ```
    This will continuously stream live data and perform real-time analysis.

### Terminal 4: Automatic Model Training (Optional)

To ensure the machine learning models adapt to new market data, you can run the training scheduler. This script will automatically retrain the models for all intervals (1d, 4h, 15m) every Sunday at 02:00.

1.  Open a new terminal window.
2.  Navigate to the project's root directory:
    ```bash
    cd /path/to/OptiTradeCode/
    ```
3.  Activate your Conda environment:
    ```bash
    conda activate optitrade_env
    ```
4.  Start the training scheduler:
    ```bash
    python scripts/run_training_scheduler.py
    ```
    Keep this terminal running in the background (e.g., using `screen` or `tmux` on a server) for the scheduler to work continuously.

### Parameter Optimization

To optimize model parameters for a specific model, symbol, and interval:

1.  Open a new terminal window.
2.  Navigate to the project's root directory:
    ```bash
    cd /path/to/OptiTradeCode/
    ```
3.  Activate your Conda environment:
    ```bash
    conda activate optitrade_env
    ```
4.  Run the optimization script (e.g., for PriceTrendModel on AAPL with 1d interval):
    ```bash
    python scripts/optimize_parameters.py --model PriceTrendModel --symbol AAPL --interval 1d
    ```
    Optimized parameters will be saved in a JSON file (e.g., `optimized_parameters_PriceTrendModel_AAPL_1d.json`).

### Portfolio Optimization

To get an optimized portfolio for a set of symbols:

1.  Access the API endpoint (e.g., via browser or `curl`):
    ```
    http://127.0.0.1:8000/api/v1/portfolio/optimize?symbols=AAPL,MSFT,GOOG&start_date=2020-01-01&end_date=2023-01-01
    ```

## Project Structure

The main directory structure of the project is as follows:

```
OptiTrade/
├── data/                 # Raw, processed, and external data files
├── notebooks/            # Jupyter notebooks (data exploration, model development)
├── scripts/              # Utility scripts (data fetching, scoring engine execution, model training, real-time stream, parameter optimization)
├── docs/                 # Project documentation (e.g., formasyon.txt, yapilacaklar.txt)
└── src/                  # Main source code
    └── optitrade/        # OptiTrade package
        ├── alerting/     # Alerting systems
        ├── backtesting/  # Backtesting simulator and enhanced backtesting module
        ├── data/         # Data loading and processing modules
        ├── models/       # Artificial intelligence models (including trained_models/, financial ratio models, and valuation models like DDM)
        ├── realtime/     # Real-time data streaming handlers and processors
        ├── risk/         # Risk management and portfolio optimization modules
        ├── scoring/      # Signal scoring engine
        ├── api/          # FastAPI backend API endpoints
        └── utils/        # Utility functions and classes
```