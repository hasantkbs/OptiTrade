import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './App.css';

// Model sınıf adlarını, grafikte gösterilecek daha okunaklı isimlerle eşleştir
const modelDisplayNameMap = {
  'PriceTrendModel': 'Fiyat Trendi',
  'VolumeSurgeModel': 'Hacim Artışı',
  'NewsSentimentModel': 'Haber Duyarlılığı',
  'SocialSentimentModel': 'Sosyal Medya',
  'SupportResistanceModel': 'Destek/Direnç',
  'DivergenceDetectionModel': 'Uyumsuzluk',
  'FormationDetectionModel': 'Formasyon Analizi',
  'MachineLearningModel': 'Makine Öğrenmesi',
  // Gelecekte eklenecek diğer modeller buraya...
};

function App() {
  const [symbol, setSymbol] = useState('BTC-USD');
  const [interval, setInterval] = useState('1d'); // Yeni state: analiz aralığı
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const getPredictionDirection = (score) => {
    if (score > 0.2) return 'Yükselecek';
    if (score < -0.2) return 'Düşecek';
    return 'Nötr';
  };

  const handleAnalyze = async () => {
    setIsLoading(true);
    setError(null);
    setAnalysisResult(null);

    try {
      // API endpoint'ine interval parametresini de ekle
      const response = await fetch(`http://127.0.0.1:8000/api/v1/signals?symbol=${symbol}&interval=${interval}`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "API'den veri alınırken bir hata oluştu.");
      }

      setAnalysisResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // Model çıktılarını grafik ve liste için uygun formata dönüştür
  const modelOutputsData = analysisResult ? 
    Object.entries(analysisResult.model_outputs).map(([key, value]) => ({
      name: modelDisplayNameMap[key] || key, // Eşleşme bulunamazsa sınıf adını kullan
      score: value.score,
      details: value.details,
    })) : [];

  return (
    <div className="App">
      <header className="App-header">
        <h1>OptiTrade v2.0</h1>
        <p className="subtitle">Dinamik Sinyal Analiz Platformu</p>
        <div className="input-container">
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="Sembol girin (örn: BTC-USD)"
          />
          <select value={interval} onChange={(e) => setInterval(e.target.value)}>
            <option value="15m">15 Dakika</option>
            <option value="4h">4 Saat</option>
            <option value="1d">1 Gün</option>
          </select>
          <button onClick={handleAnalyze} disabled={isLoading}>
            {isLoading ? 'Analiz Ediliyor...' : 'Analiz Et'}
          </button>
        </div>

        {error && <div className="error-message">Hata: {error}</div>}

        {analysisResult && (
          <div className="results-container">
            <h2>Analiz Sonuçları ({symbol})</h2>
            {analysisResult.current_market_price && (
              <div className="current-price">
                <p>{symbol} Anlık Piyasa Fiyatı:</p>
                <span>{analysisResult.current_market_price.toFixed(2)}</span>
              </div>
            )}
            <div className="final-score">
              <p>Nihai Sinyal Skoru</p>
              <span className={analysisResult.final_score > 0 ? 'score-positive' : 'score-negative'}>
                {analysisResult.final_score.toFixed(4)}
              </span>
            </div>
            <div className="prediction-direction">
              <p>Tahmin Yönü:</p>
              <span>{getPredictionDirection(analysisResult.final_score)}</span>
            </div>

            {/* Model Skorları Çubuk Grafiği */}
            {modelOutputsData.length > 0 && (
              <div className="chart-container">
                <h3>Model Skorları Dağılımı</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={modelOutputsData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#4a4f57" />
                    <XAxis dataKey="name" stroke="#ccc" />
                    <YAxis domain={[-1, 1]} stroke="#ccc" />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#2a2f37', border: '1px solid #4a4f57' }} 
                      labelStyle={{ color: '#eee' }}
                      formatter={(value, name, props) => [
                        `${value.toFixed(4)}`, 
                        `${props.payload.details || 'Detay yok'}`
                      ]} // Tooltip'te detayları göster
                    />
                    <Legend wrapperStyle={{ color: '#ccc' }}/>
                    <Bar dataKey="score" name="Model Skoru" fill="#8884d8" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            <div className="model-scores">
              <h3>Detaylı Model Skorları</h3>
              <ul>
                {modelOutputsData.map(({ name, score, details }) => (
                  <li key={name}>
                    <span>{name}:</span> 
                    <span className={score > 0 ? 'score-positive' : 'score-negative'}>{score.toFixed(4)}</span>
                    {details && <span className="model-details"> ({details})</span>}
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