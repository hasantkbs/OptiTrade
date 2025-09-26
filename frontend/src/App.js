import React, { useState, useEffect, useCallback } from 'react';
import './App.css';
import CryptoView from './components/CryptoView';
import StockView from './components/StockView';

function App() {
  const [symbol, setSymbol] = useState('BTC-USD');
  const [interval, setInterval] = useState('1d');
  const [rsiPeriod, setRsiPeriod] = useState(21); // Varsayılan olarak uzun vade RSI
  const [view, setView] = useState('crypto'); // 'crypto' or 'stock'
  const [analysisResult, setAnalysisResult] = useState(null);
  const [chartData, setChartData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [support, setSupport] = useState(null);
  const [resistance, setResistance] = useState(null);
  const [formation, setFormation] = useState(null);
  const [priceFlash, setPriceFlash] = useState(false); // Fiyat güncellemesi için flash efekti

  // Interval değiştikçe RSI periyodunu otomatik ayarla
  useEffect(() => {
    const shortTermIntervals = ['15m', '4h'];
    if (shortTermIntervals.includes(interval)) {
      setRsiPeriod(14);
    } else {
      setRsiPeriod(21);
    }
  }, [interval]);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setAnalysisResult(null);
    setChartData([]);

    const assetType = view;

    try {
      const [signalsResponse, chartResponse] = await Promise.all([
        fetch(`/api/v1/signals?symbol=${symbol}&interval=${interval}&rsi_period=${rsiPeriod}&asset_type=${assetType}`),
        fetch(`/api/v1/market_data?symbol=${symbol}&interval=${interval}&asset_type=${assetType}`)
      ]);

      const signalsData = await signalsResponse.json();
      const chartData = await chartResponse.json();

      if (!signalsResponse.ok) {
        throw new Error(signalsData.detail || "Sinyal API'sinden veri alınamadı.");
      }
      if (!chartResponse.ok) {
        throw new Error(chartData.detail || "Grafik verisi API'sinden veri alınamadı.");
      }

      setAnalysisResult(signalsData);
      setChartData(chartData);

    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [symbol, interval, rsiPeriod, view]);

  // WebSocket connection
  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.host}/ws/${view}/${symbol}`);
    let titleInterval = null;

    ws.onopen = () => {
      console.log("WebSocket connected");
      document.title = "OptiTrade"; // Sayfa yüklendiğinde başlığı sıfırla
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setChartData(prevData => [...prevData, { Date: new Date().toLocaleDateString(), Close: data.latest_price }]);
      setAnalysisResult(data);
      if (data.support_resistance) {
        setSupport(data.support_resistance.support);
        setResistance(data.support_resistance.resistance);
      }
      if (data.formation) {
        setFormation(data.formation);
      }

      // Fiyat güncellemesi flash efekti
      setPriceFlash(true);
      setTimeout(() => setPriceFlash(false), 500);

      // Sayfa gizliyse başlığı güncelle
      if (document.hidden && data.latest_price) {
        document.title = `${symbol}: ${data.latest_price.toFixed(2)}`;
      }
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected");
      clearInterval(titleInterval);
      document.title = "OptiTrade";
    };

    // Sayfa görünürlüğü değiştiğinde başlığı güncelle
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // Sayfa gizlendiğinde, fiyat güncellemelerini başlığa yansıt
        if (analysisResult && analysisResult.latest_price) {
          document.title = `${symbol}: ${analysisResult.latest_price.toFixed(2)}`;
        }
      } else {
        // Sayfa görünür olduğunda başlığı sıfırla
        document.title = "OptiTrade";
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      ws.close();
      clearInterval(titleInterval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      document.title = "OptiTrade";
    };
  }, [symbol, view, analysisResult]); // analysisResult bağımlılığı eklendi

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="App">
      <header className="App-header">
        <h1>OptiTrade v2.0</h1>
        <p className="subtitle">Dinamik Sinyal Analiz Platformu</p>
        
        <div className="view-selector">
          <button onClick={() => setView('crypto')} className={view === 'crypto' ? 'active' : ''}>Kripto Analizi</button>
          <button onClick={() => setView('stock')} className={view === 'stock' ? 'active' : ''}>Hisse Senedi Analizi</button>
        </div>

        <div className="input-container">
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder={view === 'crypto' ? "Sembol girin (örn: BTC-USD)" : "Sembol girin (örn: AAPL)"}
          />
          <select value={interval} onChange={(e) => setInterval(e.target.value)}>
            <option value="15m">15 Dakika</option>
            <option value="4h">4 Saat</option>
            <option value="1d">1 Gün</option>
            <option value="1w">1 Hafta</option>
            <option value="1mo">1 Ay</option>
          </select>
          <button onClick={fetchData} disabled={isLoading}>
            {isLoading ? 'Analiz Ediliyor...' : 'Analiz Et'}
          </button>
        </div>

        {error && <div className="error-message">Hata: {error}</div>}

        {analysisResult && view === 'crypto' && (
          <CryptoView 
            symbol={symbol}
            interval={interval}
            analysisResult={analysisResult}
            chartData={chartData}
            support={support}
            resistance={resistance}
            formation={formation}
          />
        )}

        {analysisResult && view === 'stock' && (
          <StockView 
            symbol={symbol}
            interval={interval}
          />
        )}

      </header>
    </div>
  );
}

export default App;