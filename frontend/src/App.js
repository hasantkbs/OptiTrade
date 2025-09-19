import React, { useState, useEffect } from 'react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from 'recharts';
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
  'MacroEconomicModel': 'Makroekonomi',
  'OnChainModel': 'On-Chain Veri',
  'CorrelationModel': 'Korelasyon',
};

// Modelleri kategorilere ayır
const modelCategories = {
  'Trend': ['PriceTrendModel', 'MachineLearningModel'],
  'Momentum': ['VolumeSurgeModel', 'DivergenceDetectionModel'],
  'Yapı': ['SupportResistanceModel', 'FormationDetectionModel'],
  'Duyarlılık': ['NewsSentimentModel', 'SocialSentimentModel'],
  'Bağlam': ['MacroEconomicModel', 'OnChainModel', 'CorrelationModel'],
};

function App() {
  const [symbol, setSymbol] = useState('BTC-USD');
  const [interval, setInterval] = useState('1d');
  const [analysisResult, setAnalysisResult] = useState(null);
  const [chartData, setChartData] = useState([]); // Fiyat grafiği için state
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const getPredictionDirection = (score) => {
    if (score > 0.2) return 'Yükselecek';
    if (score < -0.2) return 'Düşecek';
    return 'Nötr';
  };

  // Analiz sonuçlarını ve grafik verisini çeken ana fonksiyon
  const fetchData = async () => {
    setIsLoading(true);
    setError(null);
    setAnalysisResult(null);
    setChartData([]);

    try {
      // Eş zamanlı olarak iki API isteğini de yap
      const [signalsResponse, chartResponse] = await Promise.all([
        fetch(`http://127.0.0.1:8000/api/v1/signals?symbol=${symbol}&interval=${interval}`),
        fetch(`http://127.0.0.1:8000/api/v1/market_data?symbol=${symbol}&interval=${interval}`)
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
  };

  // Bileşen ilk yüklendiğinde verileri çek
  useEffect(() => {
    fetchData();
  }, []); // Sadece başlangıçta çalışır


  // Model çıktılarını grafik ve liste için uygun formata dönüştür
  const modelOutputsData = analysisResult ? 
    Object.entries(analysisResult.model_outputs).filter(([key]) => key !== 'MarketConditionClassifier').map(([key, value]) => ({
      name: modelDisplayNameMap[key] || key, // Eşleşme bulunamazsa sınıf adını kullan
      score: value.score,
      details: value.details,
    })) : [];

  // Kategori skorlarını hesapla
  const categoryScores = Object.keys(modelCategories).map(categoryName => {
    const modelsInCat = modelCategories[categoryName];
    let totalScore = 0;
    let count = 0;
    modelsInCat.forEach(modelKey => {
      if (analysisResult && analysisResult.model_outputs[modelKey] && modelKey !== 'MarketConditionClassifier') { // MarketConditionClassifier skor üretmez
        totalScore += analysisResult.model_outputs[modelKey].score;
        count++;
      }
    });
    return {
      category: categoryName,
      score: count > 0 ? totalScore / count : 0,
    };
  });

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
          <button onClick={fetchData} disabled={isLoading}>
            {isLoading ? 'Analiz Ediliyor...' : 'Analiz Et'}
          </button>
        </div>

        {error && <div className="error-message">Hata: {error}</div>}

        {analysisResult && (
          <div className="results-container">
            <h2>Analiz Sonuçları ({symbol} - {interval})</h2>
            
            {/* Fiyat Grafiği */}
            {chartData.length > 0 && (
              <div className="chart-container">
                <h3>Fiyat Geçmişi</h3>
                <ResponsiveContainer width="100%" height={400}>
                  <LineChart data={chartData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#4a4f57" />
                    <XAxis dataKey="Date" stroke="#ccc" />
                    <YAxis stroke="#ccc" domain={['dataMin', 'dataMax']} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#2a2f37', border: '1px solid #4a4f57' }} 
                      labelStyle={{ color: '#eee' }}
                    />
                    <Legend />
                    <Line type="monotone" dataKey="Close" name="Kapanış Fiyatı" stroke="#8884d8" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            <div className="summary-grid">
              {analysisResult.current_market_price && (
                <div className="summary-item">
                  <p>Anlık Fiyat</p>
                  <span>{analysisResult.current_market_price.toFixed(2)}</span>
                </div>
              )}
              <div className="summary-item">
                <p>Nihai Skor</p>
                <span className={analysisResult.final_score > 0 ? 'score-positive' : 'score-negative'}>
                  {analysisResult.final_score.toFixed(4)}
                </span>
              </div>
              <div className="summary-item">
                <p>Tahmin Yönü</p>
                <span>{getPredictionDirection(analysisResult.final_score)}</span>
              </div>
              {analysisResult.estimated_target_price && (
                <div className="summary-item">
                  <p>Tahmini Hedef Fiyat</p>
                  <span>{analysisResult.estimated_target_price.toFixed(2)}</span>
                </div>
              )}
              {analysisResult.position_sizing && analysisResult.position_sizing.percentage > 0 && (
                <div className="summary-item">
                  <p>Önerilen Pozisyon Büyüklüğü</p>
                  <span>{(analysisResult.position_sizing.percentage * 100).toFixed(2)}%</span>
                </div>
              )}
              {analysisResult.market_regime && (
                <div className="summary-item">
                  <p>Piyasa Rejimi</p>
                  <span>{analysisResult.market_regime}</span>
                </div>
              )}
            </div>

            {/* Model Skorları Radar Grafiği */}
            {categoryScores.length > 0 && (
              <div className="chart-container">
                <h3>Model Kategori Skorları (Radar)</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <RadarChart outerRadius={90} width={730} height={250} data={categoryScores}>
                    <PolarGrid stroke="#4a4f57" />
                    <PolarAngleAxis dataKey="category" stroke="#ccc" />
                    <PolarRadiusAxis angle={30} domain={[-1, 1]} stroke="#ccc" />
                    <Radar name="Kategori Skoru" dataKey="score" stroke="#8884d8" fill="#8884d8" fillOpacity={0.6} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#2a2f37', border: '1px solid #4a4f57' }} 
                      labelStyle={{ color: '#eee' }}
                    />
                    <Legend />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Model Skorları Çubuk Grafiği */}
            {modelOutputsData.length > 0 && (
              <div className="chart-container">
                <h3>Detaylı Model Skorları (Çubuk)</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={modelOutputsData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#4a4f57" />
                    <XAxis dataKey="name" stroke="#ccc" />
                    <YAxis domain={[-1, 1]} stroke="#ccc" />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#2a2f37', border: '1px solid #4a4f57' }} 
                      labelStyle={{ color: '#eee' }}
                    />
                    <Legend />
                    <Bar dataKey="score" name="Model Skoru" fill="#82ca9d" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            <div className="model-scores">
              <h3>Tüm Model Çıktıları</h3>
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