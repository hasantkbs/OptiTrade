# OptiTrade

OptiTrade is an AI-powered trading signal generation and analysis platform. It analyzes market data using various financial models, generates trading signals, and evaluates these signals through a scoring engine. The platform offers backtesting capabilities to simulate strategy performance.

## Features

- **Diverse Financial Models:** Various AI models including price trend, news sentiment, market condition classification, social sentiment, volume surge, support/resistance levels, and a new **Scalping Model** for short-term analysis.

## Debug Mode and Logging

To enable debug mode and view detailed logs, ensure your `.env` file (in the project root) contains `DEBUG=True`. Logs will be printed to the console and saved to `optitrade.log`.


- **Trading Signal Scoring Engine:** Comprehensively evaluates and scores generated signals.
- **Backtesting Simulator:** Simulates the performance of developed trading strategies on historical data.
- **Data Fetching and Processing:** Automatically fetches and processes financial data.

## Model Development & Performance

This section summarizes the iterative development and testing of the core prediction model, focusing on high-frequency data (1-minute intervals) for short-term price movement forecasting.

### Development Journey

1.  **Initial Rule-Based Model:** Started with a basic rule-based price trend model, which showed limited predictive power (~49% accuracy).
2.  **Transition to Machine Learning:** Migrated to a `RandomForestClassifier` to leverage data-driven learning.
3.  **Advanced Feature Engineering:**
    *   Incorporated **lagged features** (past values of price, RSI, MACD, etc.) to provide the model with memory and context.
    *   Added **volatility metrics** (Average True Range - ATR) and **price difference features** (`high-low`, `close-open`).
    *   Integrated **Support and Resistance levels** detection, based on multiple touches within a defined tolerance.
4.  **Target Definition Refinement:**
    *   Explored different prediction horizons (1-minute, 15-minute, 1-hour, 4-hour) and target definitions (binary vs. multi-class classification).
    *   Optimized the target to predict significant price movements (e.g., >0.2% change) within a specific timeframe.
5.  **Class Imbalance Handling:** Utilized `class_weight='balanced_subsample'` in the `RandomForestClassifier` to address imbalances between "price up" and "price down/stable" classes, ensuring the model doesn't bias towards the majority class.

### Current Best Performance (4-Hour Prediction)

After extensive iteration and optimization, the model achieved its best performance on the `BTC-2021min.csv` dataset (using the first 200,000 rows) for predicting 4-hour price movements.

*   **Prediction Horizon:** 4 hours (240 minutes)
*   **Target:** Binary classification (Price will increase by >0.2% (1) vs. Price will not increase by >0.2% (0))
*   **Overall Accuracy:** **~63.09%**

**Detailed Classification Report:**

| Class (Target)       | Precision | Recall | F1-Score | Support |
| :------------------- | :-------- | :----- | :------- | :------ |
| 0 (Down/Stable)      | 0.71      | 0.77   | 0.74     | 26941   |
| 1 (Up)               | 0.42      | 0.34   | 0.37     | 13052   |
| **Accuracy**         |           |        | **0.63** | 39993   |
| **Macro Avg**        | 0.56      | 0.55   | 0.56     | 39993   |
| **Weighted Avg**     | 0.61      | 0.63   | 0.62     | 39993   |

**Key Feature Importances:**

The model's decisions are primarily driven by:
1.  **Volatility Metrics (ATR and its lagged versions):** Indicating the importance of price fluctuation.
2.  **Raw Price Data (Open, High, Low, Close and their lagged versions):** Capturing fundamental price movements.
3.  **Technical Indicators (RSI, MACD, Trend Strength and their lagged versions):** Providing momentum and trend signals.
4.  **Support/Resistance Levels:** While included, their current contribution to feature importance is lower compared to other metrics, suggesting potential for further refinement in their detection or integration.

### Future Work & Considerations

*   **Further Optimization:** Explore more advanced models (e.g., XGBoost, LightGBM, LSTM) and hyperparameter tuning.
*   **Support/Resistance Refinement:** Investigate alternative detection algorithms or dynamic parameter tuning for support/resistance levels.
*   **Dynamic Thresholding:** Adapt the price change threshold based on market volatility.
*   **Multi-Timeframe Analysis:** Incorporate features derived from multiple timeframes (e.g., 1-hour, 4-hour data points within the 1-minute dataset).

## Setup

Follow these steps to set up and run the OptiTrade project on your local machine:

### Prerequisites

- Python 3.8+
- Conda (Anaconda or Miniconda)

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
5.  Start the React development server:
    ```bash
    npm start
    ```
    This command will automatically open `http://localhost:3000` in your web browser. If it doesn't, you can manually paste this address into your browser.

### Terminal 3: Monitor Logs (Optional)

1.  Open another new terminal window.
2.  Navigate to the project's root directory:
    ```bash
    cd /path/to/OptiTradeCode/
    ```
3.  Monitor the `optitrade.log` file in real-time:
    ```bash
    tail -f optitrade.log
    ```

### Other Usage Scripts (For Developers)

Development-oriented scripts for fetching financial data, running the main application, or running the scoring engine are still available in the `scripts/` directory. Note that the `interval` parameter now supports more granular options (e.g., `1m`, `5m`, `15m`, `30m`, `60m`, `1h`, `1d`, `1wk`, `1mo`, `3mo`). The `period` for data fetching is automatically adjusted in the frontend based on the selected `interval` to comply with `yfinance` limitations.

-   **Fetch Data:**
    ```bash
    python scripts/fetch_data.py --symbol BTC-USD --interval 1d
    ```
-   **Run Main Application (CLI):**
    ```bash
    python -m src.optitrade.main --symbol BTC-USD --interval 1d
    ```
-   **Run Scoring Engine:**
    ```bash
    python scripts/run_scoring_engine.py --symbol BTC-USD --interval 1d
    ```

## Project Structure

The main directory structure of the project is as follows:

```
OptiTrade/
├── data/                 # Raw, processed, and external data files
├── notebooks/            # Jupyter notebooks (data exploration, model development)
├── scripts/              # Utility scripts (data fetching, scoring engine execution)
└── src/                  # Main source code
    └── optitrade/        # OptiTrade package
        ├── alerting/     # Alerting systems
        ├── backtesting/  # Backtesting simulator
        ├── data/         # Data loading and processing modules
        ├── models/       # Artificial intelligence models
        ├── scoring/      # Signal scoring engine
        ├── api/          # FastAPI backend API endpoints (includes a placeholder /v1/models endpoint)
        └── utils/        # Utility functions and classes
```