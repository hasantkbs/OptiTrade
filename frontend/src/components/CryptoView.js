
import React from 'react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ReferenceLine, ReferenceArea } from 'recharts';

// Model sınıf adlarını, grafikte gösterilecek daha okunaklı isimlerle eşleştir
const modelDisplayNameMap = {
  'MarketConditionClassifier': 'Piyasa Rejimi',
  'PriceTrendModel': 'Fiyat Trendi',
  'VolumeSurgeModel': 'Hacim Analizi',
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
  'MACDModel': 'MACD',
  'BollingerBandsModel': 'Bollinger Bantları',
  'FibonacciModel': 'Fibonacci Seviyeleri',
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
  priceFlash
}) => {

  // Model çıktılarını grafik ve liste için uygun formata dönüştür
  const modelOutputsData = analysisResult ? 
    Object.entries(analysisResult)
      .filter(([key]) => modelDisplayNameMap[key] && typeof analysisResult[key] === 'object' && analysisResult[key] !== null && 'score' in analysisResult[key])
      .map(([key, value]) => ({
        name: modelDisplayNameMap[key] || key,
        score: value.score,
        details: value.details
      })) : [];

  const fibonacciLevels = analysisResult?.FibonacciModel?.levels;
  const support = analysisResult?.SupportResistanceModel?.support;
  const resistance = analysisResult?.SupportResistanceModel?.resistance;
  const formation = analysisResult?.FormationDetectionModel;

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

      {/* Çekirdek Teknik Analiz Göstergeleri */}
      <div className="grid-core-analysis">
        <h3>Teknik Göstergeler</h3>
        <div className="summary-grid">
          {analysisResult.MACDModel && analysisResult.MACDModel.signal !== 'Neutral' && (
            <div className="summary-item tech-indicator">
              <p>MACD Sinyali</p>
              <span className={analysisResult.MACDModel.signal === 'Bullish' ? 'score-positive' : 'score-negative'}>
                {analysisResult.MACDModel.signal}
              </span>
              <small>{analysisResult.MACDModel.details}</small>
            </div>
          )}
          {analysisResult.BollingerBandsModel && analysisResult.BollingerBandsModel.signal !== 'Neutral' && (
            <div className="summary-item tech-indicator">
              <p>Bollinger Bandı</p>
              <span className={analysisResult.BollingerBandsModel.signal === 'Oversold' ? 'score-positive' : 'score-negative'}>
                {analysisResult.BollingerBandsModel.signal}
              </span>
              <small>{analysisResult.BollingerBandsModel.details}</small>
            </div>
          )}
          {analysisResult.VolumeSurgeModel && analysisResult.VolumeSurgeModel.score !== 0 && (
            <div className="summary-item tech-indicator">
              <p>Hacim Analizi</p>
              <span className={analysisResult.VolumeSurgeModel.score > 0 ? 'score-positive' : 'score-negative'}>
                {analysisResult.VolumeSurgeModel.details}
              </span>
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
                  return tick.toFixed(2);
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
              {support && <ReferenceLine y={support} label="Support" stroke="#4caf50" />}
              {resistance && <ReferenceLine y={resistance} label="Resistance" stroke="#f44336" />}
              {/* Fibonacci seviyelerini grafiğe ekle */}
              {fibonacciLevels && Object.entries(fibonacciLevels).map(([level, price]) => (
                  <ReferenceLine key={level} y={price} strokeOpacity={0.5} strokeDasharray="4 4" stroke="#ffc658">
                      <Legend value={`${level.replace('level_','')} %`}/>
                  </ReferenceLine>
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Fibonacci Seviyeleri Listesi */}
      {fibonacciLevels && (
        <div className="grid-fibonacci-levels model-scores">
            <h3>Fibonacci Seviyeleri</h3>
            <ul>
              {Object.entries(fibonacciLevels).map(([level, price]) => (
                <li key={level}>
                  <span>{level.replace('level_','').replace('_', '.')} %:</span>
                  <span>{price.toFixed(2)}</span>
                </li>
              ))}
            </ul>
        </div>
      )}

      {/* Model Skorları Çubuk Grafiği */}
      {modelOutputsData.length > 0 && (
        <div className="grid-bar-chart chart-container">
          <h3>Detaylı Model Skorları</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={modelOutputsData} layout="vertical" margin={{ top: 5, right: 20, left: 40, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#4a4f57" />
              <XAxis type="number" domain={[-1, 1]} stroke="#ccc" tick={{ fontSize: 12 }} />
              <YAxis type="category" dataKey="name" stroke="#ccc" tick={{ fontSize: 12 }} />
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

    </div>
  );
};

export default CryptoView;
