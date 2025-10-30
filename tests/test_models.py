import pytest
import pandas as pd
import numpy as np
import ta.trend
import ta.volatility

from src.optitrade.models.macd_model import MACDModel
from src.optitrade.models.bollinger_bands_model import BollingerBandsModel

# --- MACD Model Tests ---

def test_macd_model_bullish_signal(monkeypatch):
    """MACDModel'in yükseliş sinyalini doğru tespit edip etmediğini test eder."""
    # Arrange
    fake_macd_series = pd.Series([10, 9, 12])
    fake_signal_series = pd.Series([11, 10, 11])

    def mock_macd(*args, **kwargs):
        return fake_macd_series

    def mock_macd_signal(*args, **kwargs):
        return fake_signal_series

    monkeypatch.setattr(ta.trend, "macd", mock_macd)
    monkeypatch.setattr(ta.trend, "macd_signal", mock_macd_signal)

    dummy_data = pd.DataFrame({'Close': range(40)})
    model = MACDModel()
    
    # Act
    result = model.predict(data=dummy_data)
    
    # Assert
    assert result['signal'] == 'Bullish', f"Expected 'Bullish', but got {result['signal']}"
    assert 'Yükseliş Sinyali' in result['details']

def test_macd_model_bearish_signal(monkeypatch):
    """MACDModel'in düşüş sinyalini doğru tespit edip etmediğini test eder."""
    # Arrange
    fake_macd_series = pd.Series([13, 12, 9])
    fake_signal_series = pd.Series([12, 11, 10])

    def mock_macd(*args, **kwargs):
        return fake_macd_series

    def mock_macd_signal(*args, **kwargs):
        return fake_signal_series

    monkeypatch.setattr(ta.trend, "macd", mock_macd)
    monkeypatch.setattr(ta.trend, "macd_signal", mock_macd_signal)

    dummy_data = pd.DataFrame({'Close': range(40)})
    model = MACDModel()
    
    # Act
    result = model.predict(data=dummy_data)
    
    # Assert
    assert result['signal'] == 'Bearish', f"Expected 'Bearish', but got {result['signal']}"
    assert 'Düşüş Sinyali' in result['details']

# --- Bollinger Bands Model Tests ---

class MockBollingerBands:
    def __init__(self, high_band_val, low_band_val, mid_band_val, size):
        # Create a series of a specific size, with the critical value at the end.
        self._high_band = pd.Series([high_band_val - 1] * (size - 1) + [high_band_val], index=range(size))
        self._low_band = pd.Series([low_band_val + 1] * (size - 1) + [low_band_val], index=range(size))
        self._mid_band = pd.Series([mid_band_val] * size, index=range(size))

    def bollinger_hband(self): return self._high_band
    def bollinger_lband(self): return self._low_band
    def bollinger_mavg(self): return self._mid_band

def test_bollinger_bands_overbought_signal(monkeypatch):
    """BollingerBandsModel'in 'Aşırı Alım' (Overbought) sinyalini test eder."""
    # Arrange
    data_size = 30
    dummy_data = pd.DataFrame({'Close': np.linspace(98, 101, data_size).tolist()}) # Son fiyat 101
    # Sahte bantların son değeri 100 olacak, böylece fiyat (101) üst bandı (100) aşar.
    mock_bb = MockBollingerBands(high_band_val=100, low_band_val=90, mid_band_val=95, size=data_size)
    monkeypatch.setattr(ta.volatility, "BollingerBands", lambda *args, **kwargs: mock_bb)
    
    model = BollingerBandsModel()

    # Act
    result = model.predict(data=dummy_data)

    # Assert
    assert result['signal'] == 'Overbought'
    assert 'aştı' in result['details']

def test_bollinger_bands_oversold_signal(monkeypatch):
    """BollingerBandsModel'in 'Aşırı Satım' (Oversold) sinyalini test eder."""
    # Arrange
    data_size = 30
    dummy_data = pd.DataFrame({'Close': np.linspace(102, 89, data_size).tolist()}) # Son fiyat 89
    # Sahte bantların son değeri 90 olacak, böylece fiyat (89) alt bandın (90) altına düşer.
    mock_bb = MockBollingerBands(high_band_val=110, low_band_val=90, mid_band_val=100, size=data_size)
    monkeypatch.setattr(ta.volatility, "BollingerBands", lambda *args, **kwargs: mock_bb)
    
    model = BollingerBandsModel()

    # Act
    result = model.predict(data=dummy_data)

    # Assert
    assert result['signal'] == 'Oversold'
    assert 'altına düştü' in result['details']

def test_bollinger_bands_neutral_signal(monkeypatch):
    """BollingerBandsModel'in 'Nötr' (Neutral) sinyalini test eder."""
    # Arrange
    data_size = 30
    dummy_data = pd.DataFrame({'Close': np.linspace(98, 95, data_size).tolist()}) # Son fiyat 95
    # Fiyat (95), alt (90) ve üst (100) bantların arasında kalır.
    mock_bb = MockBollingerBands(high_band_val=100, low_band_val=90, mid_band_val=95, size=data_size)
    monkeypatch.setattr(ta.volatility, "BollingerBands", lambda *args, **kwargs: mock_bb)
    
    model = BollingerBandsModel()

    # Act
    result = model.predict(data=dummy_data)

    # Assert
    assert result['signal'] == 'Neutral'
