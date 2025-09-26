
import React from 'react';

const StockView = ({ symbol, interval }) => {
  return (
    <div className="results-container">
      <h2>Hisse Senedi Analiz Sonuçları ({symbol} - {interval})</h2>
      <p>Hisse senedi analizi için özel bileşenler ve grafikler buraya eklenecektir.</p>
      {/* Örneğin, temel analiz verileri, bilanço bilgileri, vb. */}
    </div>
  );
};

export default StockView;
