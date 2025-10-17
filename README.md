# OptiTrade - AI Stock & Crypto Analyzer

OptiTrade is an AI-powered analysis dashboard for stocks and cryptocurrencies. It provides a user-friendly web interface to visualize financial data, perform technical analysis, and run advanced models from the core `optitrade` library.

## 🚀 Features

-   **Dual Dashboards**: Separate, tailored dashboards for Stock Analysis and Crypto Analysis.
-   **Interactive Charts**: Visualize price data with Candlestick, Line, and Area charts.
-   **Technical Indicators**: A comprehensive library of over 10 indicators, including Moving Averages, Bollinger Bands, RSI, MACD, and more.
-   **Advanced Model Integration**: Run sophisticated analysis models from the core `optitrade` engine directly from the UI:
    -   Select from a dynamic list of models applicable to stocks or crypto.
    -   Currently integrated models include `PriceTrendModel`, `SupportResistanceModel`, `DivergenceDetectionModel`, `FibonacciModel`, `FinancialRatioModel` (stocks), and `OnChainModel` (crypto).
    -   View detailed analysis and scores from each model in an organized way.
    -   Plot model results (e.g., Fibonacci levels) directly on the main price chart.
-   **AI-Powered Price Prediction**: Predict future prices using LSTM and GRU models.

## 🛠️ Technologies & Libraries

-   **Frontend**: Streamlit
-   **Data Sources**: yfinance, ccxt, CoinGecko
-   **Charting**: Plotly
-   **Core Analysis Engine**: `optitrade` (custom library)
-   **Machine Learning**: TensorFlow, Keras, XGBoost, Scikit-learn

## ⚙️ Setup and Usage

### 1. Prerequisites

-   Python 3.8+
-   pip

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

### 3. Running the Application

1.  **Start the Streamlit app:**
    ```bash
    streamlit run main.py
    ```

2.  Open your web browser and navigate to the local URL provided by Streamlit (usually `http://localhost:8501`).

## 📂 Project Structure

```
/
├── main.py                   # Main Streamlit application file
├── requirements.txt          # Python dependencies
├── pages/                      # Streamlit pages for each dashboard
│   ├── home.py
│   └── crypto_analysis.py
├── utils/                      # UI and analysis utilities
│   ├── dashboard.py
│   └── analysis_runner.py
├── data/                       # Crypto data fetching logic
│   └── crypto_data.py
└── src/
    └── optitrade/            # Core analysis library
        ├── models/
        └── utils/
```