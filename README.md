# OptiTrade - AI Stock & Crypto Analyzer

OptiTrade is an AI-powered analysis dashboard for stocks and cryptocurrencies. It provides a user-friendly web interface to visualize financial data, perform technical analysis, and run advanced models from the core `optitrade` library.

## 🚀 Features

-   **Dual Dashboards**: Separate, tailored dashboards for Stock Analysis and Crypto Analysis.
-   **Interactive Charts**: Visualize price data with Candlestick, Line, and Area charts.
-   **Comprehensive Technical Indicators**: A significantly expanded library of indicators, now including **MACD**, **Bollinger Bands**, **Fibonacci Retracements**, **Volume Surge Analysis**, RSI, Moving Averages, and more.
-   **Advanced Model Integration**: Run sophisticated analysis models from the core `optitrade` engine directly from the UI:
    -   Select from a dynamic list of models applicable to stocks or crypto.
    -   **Enhanced Scoring Engine**: Utilizes a dynamic, regime-based weighting system to aggregate model scores, providing a more intelligent and context-aware final analysis.
    -   Currently integrated models include `PriceTrendModel`, `SupportResistanceModel`, `DivergenceDetectionModel`, `FibonacciModel`, `FinancialRatioModel` (stocks - *placeholder*), `OnChainModel` (crypto), **MACDModel**, **BollingerBandsModel**, and **VolumeSurgeModel**.
    -   View detailed analysis and scores from each model in an organized way.
    -   Plot model results (e.g., Fibonacci levels) directly on the main price chart.
-   **AI-Powered Price Prediction**: Predict future prices using LSTM and GRU models.
-   **Robust Data Layer**: Explicit handling of asset types (stock/crypto) for reliable data fetching from `yfinance` and CoinGecko.
-   **High-Performance Caching**: Integrated **Redis** for fast, in-memory data caching, significantly improving performance for repeated data requests.

## 🛠️ Technologies & Libraries

-   **Frontend**: Streamlit, React (for OptiTrade v2.0 API client)
-   **Backend**: Python (FastAPI for API, custom `optitrade` library for core logic)
-   **Data Sources**: `yfinance` (for stocks), CoinGecko (for crypto)
-   **Caching**: Redis
-   **Charting**: Plotly, Recharts (for React frontend)
-   **Core Analysis Engine**: `optitrade` (custom library)
-   **Machine Learning**: TensorFlow, Keras, XGBoost, Scikit-learn
-   **Testing**: Pytest (for automated unit and integration tests)

## ⚙️ Setup and Usage

### 1. Prerequisites

-   Python 3.8+
-   pip
-   **Redis Server**: A running Redis instance is required for caching. Configure connection details in `.env`.

### 2. Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd OptiTradeCode
    ```

2.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Environment Variables**: Create a `.env` file in the project root and configure your API keys and Redis connection details:
    ```
    # Redis Configuration
    REDIS_HOST=localhost
    REDIS_PORT=6379
    REDIS_DB=0
    REDIS_PASSWORD=

    # Other API Keys (e.g., NewsAPI, Twitter, Alpha Vantage) if used
    # NEWS_API_KEY=your_news_api_key
    # ...
    ```

### 3. Running the Application

1.  **Start the Streamlit app:**
    ```bash
    streamlit run main.py
    ```

2.  Open your web browser and navigate to the local URL provided by Streamlit (usually `http://localhost:8501`).

## ✅ Automated Testing

To run the automated tests and ensure the core models are functioning correctly:

```bash
pytest tests/
```

## 📂 Project Structure

```
/
├── main.py                   # Main Streamlit application file
├── requirements.txt          # Python dependencies
├── pytest.ini                # Pytest configuration
├── pages/                      # Streamlit pages for each dashboard
│   ├── home.py
│   └── crypto_analysis.py
├── utils/                      # UI and analysis utilities
│   ├── dashboard.py
│   └── analysis_runner.py
├── data/                       # Data storage (raw, processed, cache - now primarily Redis)
│   └── crypto_data.py
├── tests/                      # Automated tests for models and core logic
│   └── test_models.py          # Unit tests for individual models
└── src/
    └── optitrade/            # Core analysis library
        ├── models/             # Financial models (e.g., MACD, Bollinger Bands, Fibonacci)
        ├── api/                # FastAPI server for React frontend
        ├── utils/              # Data fetching, caching, and other utilities
        └── scoring/            # Scoring engine with dynamic weighting
```