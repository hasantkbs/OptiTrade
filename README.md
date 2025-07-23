# OptiTrade

OptiTrade is an AI-powered trading signal generation and analysis platform. It analyzes market data using various financial models, generates trading signals, and evaluates these signals through a scoring engine. The platform offers backtesting capabilities to simulate strategy performance.

## Features

- **Diverse Financial Models:** Various AI models including price trend, news sentiment, market condition classification, social sentiment, volume surge, support/resistance levels, and a new **Scalping Model** for short-term analysis.

## Debug Mode and Logging

To enable debug mode and view detailed logs, ensure your `.env` file (in the project root) contains `DEBUG=True`. Logs will be printed to the console and saved to `optitrade.log`.


- **Trading Signal Scoring Engine:** Comprehensively evaluates and scores generated signals.
- **Backtesting Simulator:** Simulates the performance of developed trading strategies on historical data.
- **Data Fetching and Processing:** Automatically fetches and processes financial data.

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