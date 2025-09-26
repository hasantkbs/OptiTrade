
import React from 'react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ReferenceLine, ReferenceArea } from 'recharts';

// Model sınıf adlarını, grafikte gösterilecek daha okunaklı isimlerle eşleştir
const modelDisplayNameMap = {
  'MarketConditionClassifier': 'Piyasa Rejimi',
  'PriceTrendModel': 'Fiyat Trendi',
  'VolumeSurgeModel': 'Hacim Artışı',
  'NewsSentimentModel': 'Haber Sent.',
  'SocialSentimentModel': 'Sosyal Sent.',
  'SupportResistanceModel': 'Destek/Direnç',
  'DivergenceDetectionModel': 'Uyumsuzluk',
  'FormationDetectionModel': 'Formasyon',
  'MachineLearningModel': 'ML Modeli',
  'MacroEconomicModel': 'Makroekonomi',
  'OnChainModel': 'On-Chain',
  'CorrelationModel': 'Korelasyon',
  'DCFModel': 'DCF Modeli',
};

// Modelleri kategorilere ayır
const modelCategories = {
  'Trend': ['PriceTrendModel', 'MachineLearningModel'],
  'Momentum': ['VolumeSurgeModel', 'DivergenceDetectionModel'],
  'Yapı': ['SupportResistanceModel', 'FormationDetectionModel'],
  'Duyarlılık': ['NewsSentimentModel', 'SocialSentimentModel'],
  'Değerleme': ['DCFModel'],
  'Bağlam': ['MacroEconomicModel', 'OnChainModel', 'CorrelationModel'],
};

const getPredictionDirection = (score) => {
    if (score > 0.2) return 'Yükselecek';
    if (score < -0.2) return 'Düşecek';
    return 'Nötr';
};

const CryptoView = ({
  symbol,
  interval,
  analysisResult,
  chartData,
  support,
  resistance,
  formation,
  priceFlash
}) => {

  // Model çıktılarını grafik ve liste için uygun formata dönüştür
  const modelOutputsData = analysisResult && analysisResult.model_outputs ? 
    Object.entries(analysisResult.model_outputs).map(([key, value]) => ({
      name: modelDisplayNameMap[key] || key, // Eşleşme bulunamazsa sınıf adını kullan
      score: value.score,
      details: value.details
    })) : [];

  // Kategori skorlarını hesapla
  const categoryScores = Object.keys(modelCategories).map(categoryName => {
    const modelsInCat = modelCategories[categoryName];
    let totalScore = 0;
    let count = 0;
    modelsInCat.forEach(modelKey => {
      if (analysisResult && analysisResult.model_outputs && analysisResult.model_outputs[modelKey]) {
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
    <div className="results-container crypto-grid">
      <div className="grid-summary">
        <h2>Analiz Sonuçları ({symbol} - {interval})</h2>
        <div className="summary-grid">
          {analysisResult.latest_price && (
            <div className="summary-item">
              <p>Anlık Fiyat</p>
              <span className={priceFlash ? 'price-flash' : ''}>{analysisResult.latest_price.toFixed(2)}</span>
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
          {formation && (
            <div className="summary-item">
              <p>Tespit Edilen Formasyon</p>
              <span>{formation.name}: {formation.details}</span>
            </div>
          )}
        </div>
      </div>
      
      {/* Fiyat Grafiği */}
      {chartData.length > 0 && (
        <div className="grid-price-chart chart-container">
          <h3>Fiyat Geçmişi</h3>
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={chartData} margin={{ top: 5, right: 30, left: 30, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#4a4f57" />
              <XAxis dataKey="Date" stroke="#ccc" minTickGap={30} angle={-45} textAnchor="end" height={70} interval="preserveEnd" tick={{ fontSize: 10 }} />
              <YAxis 
                stroke="#ccc" 
                domain={['dataMin', 'dataMax']} 
                tickFormatter={(tick) => {
                  if (tick > 1000) return `${(tick / 1000).toFixed(1)}k`;
                  return tick.toFixed(2); // Ensure 2 decimal places for smaller numbers
                }}
                tick={{ fontSize: 10 }}
              />
              <Tooltip 
                contentStyle={{ backgroundColor: '#2a2f37', border: '1px solid #4a4f57' }} 
                labelStyle={{ color: '#eee' }} itemStyle={{ fontSize: 12 }} wrapperStyle={{ fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line 
                type="monotone" 
                dataKey="Close" 
                name="Kapanış Fiyatı" 
                stroke="#8884d8" 
                dot={false} 
                formatter={(value) => value.toFixed(2)}
              />
              {support && <ReferenceLine y={support} label="Support" stroke="green" />}
              {resistance && <ReferenceLine y={resistance} label="Resistance" stroke="red" />}
              {formation && formation.points && <ReferenceArea x1={formation.points.x1} x2={formation.points.x2} y1={formation.points.y1} y2={formation.points.y2} stroke="orange" strokeOpacity={0.3} />}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Model Skorları Radar Grafiği */}
      {categoryScores.length > 0 && (
        <div className="grid-radar-chart chart-container">
          <h3>Model Kategori Skorları (Radar)</h3>
          <ResponsiveContainer width="100%" height={300}>
            <RadarChart outerRadius={90} width={730} height={250} data={categoryScores}>
              <PolarGrid stroke="#4a4f57" />
              <PolarAngleAxis dataKey="category" stroke="#ccc" tick={{ fontSize: 12 }} />
              <PolarRadiusAxis angle={30} domain={[-1, 1]} stroke="#ccc" tick={{ fontSize: 12 }} />
              <Radar name="Kategori Skoru" dataKey="score" stroke="#8884d8" fill="#8884d8" fillOpacity={0.6} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#2a2f37', border: '1px solid #4a4f57' }} 
                labelStyle={{ color: '#eee' }} wrapperStyle={{ fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Model Skorları Çubuk Grafiği */}
      {modelOutputsData.length > 0 && (
        <div className="grid-bar-chart chart-container">
          <h3>Detaylı Model Skorları (Çubuk)</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={modelOutputsData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#4a4f57" />
              <XAxis dataKey="name" stroke="#ccc" tick={{ fontSize: 12 }} />
              <YAxis domain={[-1, 1]} stroke="#ccc" tick={{ fontSize: 12 }} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#2a2f37', border: '1px solid #4a4f57' }} 
                labelStyle={{ color: '#eee' }} wrapperStyle={{ fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="score" name="Model Skoru" fill="#82ca9d" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid-model-list model-scores">
        <h3>Tüm Model Çıktıları</h3>
        <ul>
          {modelOutputsData.map(({ name, score, details }) => (
            <li key={name}>
              <span>{name}:</span> 
              <span className={score > 0 ? 'score-positive' : 'score-negative'}>{(typeof score === 'number' ? score : 0).toFixed(3)}</span>
              {details && <span className="model-details"> ({details})</span>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default CryptoView;
