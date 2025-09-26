# OptiTrade Analysis Models Detailed Documentation

This document details the financial analysis models used in the OptiTrade platform, their purposes, key parameters, and how their scores should be interpreted.

---

## 1. Market Condition Classifier (MarketConditionClassifier)

*   **Purpose:** To classify current market conditions (strong bull trend, weak bear trend, ranging market, etc.). This classification is used to dynamically weight other models.
*   **Key Parameters:**
    *   `adx_window`: Window size for ADX indicator calculation (default: 14).
    *   `adx_threshold`: ADX value threshold for a trend to be considered strong (default: 25).
*   **Score Interpretation:** This model does not directly generate a buy/sell score. Instead, it returns a `regime` value indicating the market condition. The score value is always 0.0.
*   **Special Considerations:** Critically important for dynamically adjusting the weights of other models.

---

## 2. Price Trend Model (PriceTrendModel)

*   **Purpose:** To determine the direction and strength of the price trend using technical indicators such as RSI, MACD, SMA, and ADX.
*   **Key Parameters:**
    *   `rsi_window`: RSI period (default: 14).
    *   `macd_fast`, `macd_slow`, `macd_sign`: Window sizes for the MACD indicator.
    *   `sma_short`, `sma_long`: Window sizes for short and long-term Simple Moving Averages.
    *   `adx_window`: ADX period.
*   **Score Interpretation:** Generates a score between -1.0 (Strong Sell) and +1.0 (Strong Buy). A positive score indicates an uptrend, and a negative score indicates a downtrend.

---

## 3. Volume Surge Model (VolumeSurgeModel)

*   **Purpose:** To analyze abnormal increases or decreases in volume and their potential impact on price.
*   **Key Parameters:**
    *   `volume_ma_window`: Window size for volume moving average.
    *   `deviation_scale`: Factor scaling the impact of volume deviation on the score.
    *   `obv_influence`: Contribution of the OBV (On-Balance Volume) trend to the score.
*   **Score Interpretation:** Generates a score between -1.0 (Strong Sell) and +1.0 (Strong Buy). High positive scores indicate potential volume-backed upside, while high negative scores indicate potential volume-backed downside.

---

## 4. News Sentiment Model (NewsSentimentModel)

*   **Purpose:** To measure the potential impact of financial news headlines on the market by performing sentiment analysis.
*   **Key Parameters:**
    *   `limit`: Number of news headlines to analyze (default: 20).
*   **Score Interpretation:** Generates a score between -1.0 (Very Negative) and +1.0 (Very Positive). Positive scores indicate positive news flow, and negative scores indicate negative news flow.
*   **Special Considerations:** Fetches news headlines via `DataFetcher`. Uses a pre-trained sentiment analysis model like FinBERT.

---

## 5. Social Media Sentiment Model (SocialSentimentModel)

*   **Purpose:** To measure the potential impact of social media (e.g., Reddit) posts on the market by performing sentiment analysis.
*   **Key Parameters:**
    *   `limit`: Number of social media posts to analyze (default: 25).
*   **Score Interpretation:** Generates a score between -1.0 (Very Negative) and +1.0 (Very Positive). Positive scores indicate positive social media perception, and negative scores indicate negative social media perception.
*   **Special Considerations:** Fetches social media posts via `DataFetcher`. Uses a pre-trained sentiment analysis model like FinBERT.

---

## 6. Support/Resistance Model (SupportResistanceModel)

*   **Purpose:** To identify significant support and resistance levels in price charts and generate a score based on the current price's proximity to these levels.
*   **Key Parameters:**
    *   `order`: Window size for fractal detection (default: 2).
    *   `tolerance`: Percentage-based tolerance defining how close the price needs to be to S/R levels (default: 0.01).
    *   `atr_tolerance_multiplier`: Multiplier for ATR-based dynamic tolerance calculation (default: 1.5). The model uses dynamic tolerance based on market volatility.
*   **Score Interpretation:** Generates a score between -1.0 (Strong Sell) and +1.0 (Strong Buy). Proximity to support generates a positive score, while proximity to resistance generates a negative score.

---

## 7. Divergence Detection Model (DivergenceDetectionModel)

*   **Purpose:** To detect divergences between price action and momentum indicators like RSI. These divergences can often signal trend reversals.
*   **Key Parameters:**
    *   `rsi_window`: RSI period (default: 14).
    *   `extrema_order`: Window size used to find local extrema (peaks/troughs).
    *   `lookback_period`: Historical period (in days) to look back for divergences.
*   **Score Interpretation:** Generates a score between -1.0 (Bearish Divergence) and +1.0 (Bullish Divergence). Bullish divergence yields a positive score, bearish divergence a negative score.

---

## 8. Formation Detection Model (FormationDetectionModel)

*   **Purpose:** To identify classic technical analysis chart patterns (Head & Shoulders, Triangles, Double Top/Bottom, etc.) in price data.
*   **Key Parameters:**
    *   `extrema_order`: Window size to find local extrema.
    *   `tolerance`: Price deviation tolerance for pattern detection.
    *   `required_data_points`: Minimum number of data points required for the model to run.
*   **Score Interpretation:** Generates a score between -1.0 (Bearish Formation) and +1.0 (Bullish Formation). Returns a score and detailed information based on the type of formation detected. Returns 0.0 if no formation is detected or if a breakout is pending.

---

## 9. Financial Ratio Model (FinancialRatioModel)

*   **Purpose:** To analyze key financial ratios (P/E, P/B, Debt/Equity, etc.) for stocks and generate a score.
*   **Key Parameters:** None (ratios are fetched directly from `yfinance`).
*   **Score Interpretation:** Generates a score between -1.0 (Weak Fundamentals) and +1.0 (Strong Fundamentals). Scores are based on whether ratios are favorable compared to industry averages or historical data.
*   **Special Considerations:** **Applicable only to stocks.** Not run for cryptocurrencies and returns a 0.0 score in such cases.

---

## 10. Machine Learning Model (MachineLearningModel)

*   **Purpose:** To use machine learning algorithms like XGBoost to predict future price movements based on historical data.
*   **Key Parameters:** Uses hyperparameters and features determined during model training.
*   **Score Interpretation:** Generates a score between -1.0 (Bearish Prediction) and +1.0 (Bullish Prediction). Scores are based on the model's prediction confidence.
*   **Special Considerations:** Requires separate training for each analysis period and asset.

---

## 11. Macro Economic Model (MacroEconomicModel)

*   **Purpose:** To analyze the impact of macroeconomic indicators such as inflation, interest rates, and GDP on the market.
*   **Key Parameters:** None (typically fetches data from external APIs).
*   **Score Interpretation:** Generates a score between -1.0 (Negative Impact) and +1.0 (Positive Impact). Scores are based on the impact of macroeconomic data on market sentiment.

---

## 12. On-Chain Data Model (OnChainModel)

*   **Purpose:** To generate signals for cryptocurrencies by analyzing on-chain data (transaction volume, active addresses, exchange inflows/outflows, etc.).
*   **Key Parameters:**
    *   `short_window`, `long_window`: Moving average windows.
*   **Score Interpretation:** Generates a score between -1.0 (Bearish Signal) and +1.0 (Bullish Signal). Scores are based on anomalies or trends in on-chain data.
*   **Special Considerations:** **Applicable only to cryptocurrencies.**

---

## 13. Correlation Model (CorrelationModel)

*   **Purpose:** To analyze correlations between different assets to provide insights for portfolio diversification or risk management.
*   **Key Parameters:**
    *   `window`: Window size for correlation calculation.
    *   `assets`: List of assets to compare.
*   **Score Interpretation:** Generates a score between -1.0 (Negative Correlation) and +1.0 (Positive Correlation). Typically used in conjunction with other models and does not directly generate buy/sell signals.

---

## 14. Dividend Discount Model (DCFModel)

*   **Purpose:** To estimate the intrinsic value of dividend-paying stocks by discounting future dividend streams.
*   **Key Parameters:**
    *   `growth_rate`: Dividend growth rate.
    *   `required_rate_of_return`: Required rate of return.
*   **Score Interpretation:** Generates a score based on whether the estimated intrinsic value is lower or higher than the current market price. A positive score indicates that the stock is undervalued.
*   **Special Considerations:** **Applicable only to dividend-paying stocks.**
