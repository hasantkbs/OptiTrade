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
    -   **Machine Learning Model (`XGBoost`):** A data-driven model trained on historical features to predict future price direction. Supports interval-specific training.
-   **Dynamic Signal Scoring Engine:** Comprehensively evaluates and combines signals from all integrated models using configurable weights to generate a final trading score.
-   **Real-time Data Capability:** Integration with Binance Futures WebSocket API for live mark price data streams.
-   **Interactive Web Interface (Frontend):**
    -   User-friendly interface for selecting symbols and analysis intervals.
    -   Displays the final signal score, current market price, and a clear prediction direction (Rise/Fall/Neutral).
    -   Provides detailed explanations for each model's individual score, offering transparency into the signal generation process.
    -   Visualizes model score distribution using interactive charts.
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
    python scripts/train_model.py --interval 1d
    python scripts/train_model.py --interval 4h
    python scripts/train_model.py --interval 15m
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

### Terminal 3: Real-time Data Stream (Optional, for live data testing)

1.  Open another new terminal window.
2.  Navigate to the project's root directory:
    ```bash
    cd /path/to/OptiTradeCode/
    ```
3.  Activate your Conda environment:
    ```bash
    conda activate optitrade_env
    ```
4.  Start the Binance Futures WebSocket stream:
    ```bash
    python scripts/run_stream.py
    ```
    This will continuously print live BTCUSDT mark price updates to your console.

## Project Structure

The main directory structure of the project is as follows:

```
OptiTrade/
├── data/                 # Raw, processed, and external data files
├── notebooks/            # Jupyter notebooks (data exploration, model development)
├── scripts/              # Utility scripts (data fetching, scoring engine execution, model training, real-time stream)
├── docs/                 # Project documentation (e.g., formasyon.txt, yapilacaklar.txt)
└── src/                  # Main source code
    └── optitrade/        # OptiTrade package
        ├── alerting/     # Alerting systems
        ├── backtesting/  # Backtesting simulator
        ├── data/         # Data loading and processing modules
        ├── models/       # Artificial intelligence models (including trained_models/)
        ├── realtime/     # Real-time data streaming handlers
        ├── scoring/      # Signal scoring engine
        ├── api/          # FastAPI backend API endpoints
        └── utils/        # Utility functions and classes
```
