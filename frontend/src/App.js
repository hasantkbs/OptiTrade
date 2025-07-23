import React, { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar } from 'recharts';
import './App.css';

// Tarih formatlama fonksiyonu
const formatDate = (dateString) => {
  const options = { day: '2-digit', month: '2-digit', year: 'numeric' };
  return new Date(dateString).toLocaleDateString('tr-TR', options);
};

// Özel Tooltip Bileşeni (Geçmiş Fiyatlar Grafiği için)
const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="custom-tooltip">
        <p className="label">{`Tarih: ${formatDate(label)}`}</p>
        <p className="intro">{`Kapanış Fiyatı: ${payload[0].value.toFixed(2)}`}</p>
      </div>
    );
  }
  return null;
};

// Model skorları için daha açıklayıcı isimler
const modelDisplayNameMap = {
  'price_trend_score': 'Fiyat Trendi',
  'volume_surge_score': 'Hacim Artışı',
  'news_sentiment_score': 'Haber Duyarlılığı',
  'social_sentiment_score': 'Sosyal Duyarlılık',
  'support_resistance_score': 'Destek/Direnç',
  'divergence_score': 'Uyumsuzluk Tespiti',
  'event_impact_score': 'Olay Etkisi',
  'scalping_score': 'Scalping Skoru',
};

// Grafikte gösterilecek model anahtarlarının sırası
const chartModelKeys = [
  'price_trend_score',
  'volume_surge_score',
  'news_sentiment_score',
  'social_sentiment_score',
  'support_resistance_score',
  'divergence_score',
  'event_impact_score',
  'scalping_score',
];

function App() {
  const [symbol, setSymbol] = useState('BTC-USD');
  const [interval, setInterval] = useState('1d'); // Varsayılan aralık
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleAnalyze = async () => {
    setIsLoading(true);
    setError(null);
    setAnalysisResult(null);

    let selectedPeriod = 'max';
    if (interval === '1m') {
      selectedPeriod = '7d';
    } else if (['5m', '15m', '30m', '60m', '1h'].includes(interval)) {
      selectedPeriod = '60d';
    }

    try {
      const response = await fetch('http://127.0.0.1:8000/api/v1/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ symbol, period: selectedPeriod, interval }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Bir hata oluştu.');
      }

      setAnalysisResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // Model skorlarını grafik için uygun formata dönüştür
  const modelScoresData = analysisResult ? 
    chartModelKeys.map(key => ({
      name: modelDisplayNameMap[key] || key.replace(/_/g, ' ').replace('score', '').trim(),
      score: typeof analysisResult.model_scores[key] === 'number' ? analysisResult.model_scores[key] : 0
    })) : [];

  return (
    <div className="App">
      <header className="App-header">
        <h1>OptiTrade</h1>
        <div className="input-container">
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="Sembol girin (örn: AAPL, BTC-USD)"
          />
          <select value={interval} onChange={(e) => setInterval(e.target.value)}>
            <option value="1m">1 Dakika</option>
            <option value="5m">5 Dakika</option>
            <option value="15m">15 Dakika</option>
            <option value="30m">30 Dakika</option>
            <option value="60m">60 Dakika (1 Saat)</option>
            <option value="1h">1 Saat</option>
            <option value="1d">1 Gün</option>
            <option value="1wk">1 Hafta</option>
            <option value="1mo">1 Ay</option>
          </select>
          <button onClick={handleAnalyze} disabled={isLoading}>
            {isLoading ? 'Analiz Ediliyor...' : 'Analiz Et'}
          </button>
        </div>

        {error && <div className="error-message">Hata: {error}</div>}

        {analysisResult && (
          <div className="results-container">
            <h2>Analiz Sonuçları ({analysisResult.symbol})</h2>
            <div className="final-score">
              <p>Nihai Skor</p>
              <span>{analysisResult.final_score.toFixed(2)}</span>
            </div>
            <div className="recommendation-message">
              <p>{analysisResult.recommendation_message}</p>
            </div>
            <div className="alert-message">
              <p>{analysisResult.alert_message}</p>
            </div>

            {/* Geçmiş Fiyat Grafiği */}
            {analysisResult.historical_prices && analysisResult.historical_prices.length > 0 && (
              <div className="chart-container">
                <h3>Geçmiş Fiyatlar</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={analysisResult.historical_prices}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#4a4f57" />
                    <XAxis dataKey="date" tickFormatter={formatDate} stroke="#999" />
                    <YAxis stroke="#999" />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend />
                    <Line type="monotone" dataKey="price" stroke="#8884d8" activeDot={{ r: 8 }} name="Kapanış Fiyatı" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Model Skorları Çubuk Grafiği */}
            {modelScoresData.length > 0 && (
              <div className="chart-container">
                <h3>Model Skorları Dağılımı</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={modelScoresData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#4a4f57" />
                    <XAxis dataKey="name" stroke="#999" interval="preserveStartEnd" angle={-45} textAnchor="end" height={80} />
                    <YAxis domain={[-1, 1]} stroke="#999" />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="score" fill="#82ca9d" />
                  </BarChart>
                </ResponsiveContainer>
                <p className="chart-description">
                  Bu grafik, her bir modelin nihai skora katkısını gösterir. Skorlar -1.0 (güçlü negatif etki) ile +1.0 (güçlü pozitif etki) arasında değişir.
                </p>
              </div>
            )}

            <div className="model-scores">
              <h3>Model Skorları</h3>
              <ul>
                {Object.entries(analysisResult.model_scores).map(([key, value]) => (
                  <li key={key}>
                    <span>{modelDisplayNameMap[key] || key.replace(/_/g, ' ')}:</span> 
                    <span>{typeof value === 'number' ? value.toFixed(2) : value}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </header>
    </div>
  );
}

export default App;