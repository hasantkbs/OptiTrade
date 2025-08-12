import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np
import yfinance as yf
import argparse
import random
import logging

# OptiTrade modüllerini içe aktar
from optitrade import config
from optitrade.models.registry import initialize_models
from optitrade.models.main import calculate_all_model_scores # Merkezi fonksiyon
from optitrade.scoring.scoring_engine import ScoringEngine
from optitrade.utils.data_fetcher import MarketDataFetcher

# Loglama yapılandırması
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class BacktestSimulator:
    """
    Tahmin motorunun geçmiş verilerle doğruluğunu ölçen simülatör.
    """
    def __init__(self, entry_threshold: float = 0.5, exit_threshold: float = -0.5):
        """
        Simülatörü başlatır ve strateji eşiklerini ayarlar.
        """
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.models = initialize_models()
        self.min_data_points_for_models = 60 # Geçici olarak sabit bir değer

    def _run_single_backtest(self, prices: pd.Series, prediction_scores: pd.Series) -> dict:
        """
        Basit bir alım/satım stratejisi uygulayarak tek bir backtest yapar.
        """
        # ... (içerik aynı kalır)
        if prices.empty or prediction_scores.empty:
            return {'total_return': 0.0, 'num_trades': 0, 'winning_trades': 0, 'losing_trades': 0, 'win_rate': 0.0}

        common_index = prices.index.intersection(prediction_scores.index)
        prices = prices.loc[common_index]
        prediction_scores = prediction_scores.loc[common_index]

        if prices.empty:
            return {'total_return': 0.0, 'num_trades': 0, 'winning_trades': 0, 'losing_trades': 0, 'win_rate': 0.0}

        initial_capital = 1000.0
        capital = initial_capital
        position = 0
        trade_returns = []
        entry_price = 0.0

        for i in range(1, len(prices)):
            current_price = prices.iloc[i]
            current_score = prediction_scores.iloc[i]
            logger.debug(f"BacktestSimulator: current_price={current_price}, current_score={current_score}, position={position}")

            if pd.isna(current_score):
                logger.warning(f"BacktestSimulator: current_score is NaN at index {i}. Skipping this data point.")
                continue

            if position == 0 and current_score >= self.entry_threshold:
                position = 1
                entry_price = current_price
            elif position == 1 and current_score <= self.exit_threshold:
                position = 0
                trade_return = (current_price - entry_price) / entry_price
                trade_returns.append(trade_return)
                capital *= (1 + trade_return)

        if position == 1:
            trade_return = (prices.iloc[-1] - entry_price) / entry_price
            trade_returns.append(trade_return)
            capital *= (1 + trade_return)

        total_return = (capital - initial_capital) / initial_capital
        num_trades = len(trade_returns)
        winning_trades = sum(1 for r in trade_returns if r > 0)
        losing_trades = sum(1 for r in trade_returns if r <= 0)
        win_rate = winning_trades / num_trades if num_trades > 0 else 0.0

        # Maksimum Düşüş (Max Drawdown) Hesaplaması
        if not prices.empty:
            cumulative_returns = (prices / prices.iloc[0]).cumprod()
            peak = cumulative_returns.expanding(min_periods=1).max()
            drawdown = (cumulative_returns - peak) / peak
            max_drawdown = drawdown.min() if not drawdown.empty else 0.0
        else:
            max_drawdown = 0.0

        # Sharpe Oranı Hesaplaması (Basitleştirilmiş - Risksiz oran = 0)
        sharpe_ratio = 0.0
        if trade_returns:
            returns_series = pd.Series(trade_returns)
            daily_returns_std = returns_series.std()
            if daily_returns_std != 0:
                sharpe_ratio = returns_series.mean() / daily_returns_std
                # Yıllıklandırma (örneğin, günlük veriler için sqrt(252))
                # Ancak burada trade bazında olduğu için yıllıklandırma yapmıyorum.

        return {
            'total_return': float(total_return),
            'num_trades': num_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': float(win_rate),
            'max_drawdown': float(max_drawdown),
            'sharpe_ratio': float(sharpe_ratio)
        }

    def optimize_scoring_engine_weights(self, data: pd.DataFrame, num_iterations: int = 100) -> tuple[dict, dict]:
        """
        ScoringEngine ağırlıklarını optimize etmek için rastgele arama yapar.
        """
        logger.info(f"--- ScoringEngine Ağırlık Optimizasyonu Başlatılıyor ({num_iterations} iterasyon) ---")

        best_weights = None
        best_return = -np.inf
        best_results = {}

        dummy_engine = ScoringEngine()
        score_names = list(dummy_engine.weights.keys())

        for iteration in range(num_iterations):
            random_weights_values = [random.random() for _ in score_names]
            total_random_weight = sum(random_weights_values)
            current_weights = {name: value / total_random_weight for name, value in zip(score_names, random_weights_values)}

            current_scoring_engine = ScoringEngine(weights=current_weights)

            all_prediction_scores = []
            for i in range(len(data)):
                if i < self.min_data_points_for_models:
                    all_prediction_scores.append(0.0)
                    continue
                
                historical_data_slice = data.iloc[:i+1]
                # Merkezi fonksiyonu çağır (backtest için haber/sosyal medya verisi olmadan)
                model_scores = calculate_all_model_scores(historical_data_slice, self.models)
                final_score = current_scoring_engine.generate_final_score(model_scores)
                all_prediction_scores.append(final_score)
            
            prediction_scores_series = pd.Series(all_prediction_scores, index=data.index).fillna(0.0)

            results = self._run_single_backtest(data['close'], prediction_scores_series)

            if results['total_return'] > best_return:
                best_return = results['total_return']
                best_weights = current_weights
                best_results = results
            
            if (iteration + 1) % (num_iterations // 10) == 0 or iteration == num_iterations - 1:
                logger.info(f"  İterasyon {iteration + 1}/{num_iterations} - En İyi Getiri: {best_return:.2%}")

        logger.info("--- Optimizasyon Tamamlandı ---")
        return best_weights, best_results

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Tahmin motorunun geçmiş verilerle doğruluğunu ölçen backtest simülatörü.')
    parser.add_argument('--symbol', type=str, default='AAPL', help='Hisse senedi/kripto para sembolü (örn: BTC-USD, AAPL). Varsayılan: AAPL')
    parser.add_argument('--period', type=str, default='1y', help='Veri çekme periyodu (örn: 1y, 6mo, 1mo). Varsayılan: 1y')
    parser.add_argument('--interval', type=str, default='1d', choices=['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo'], help='Veri çekme aralığı (yfinance için: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo). Varsayılan: 1d')
    parser.add_argument('--entry_threshold', type=float, default=0.5, help='Pozisyona girmek için tahmin skoru eşiği. Varsayılan: 0.5')
    parser.add_argument('--exit_threshold', type=float, default=-0.5, help='Pozisyondan çıkmak için tahmin skoru eşiği. Varsayılan: -0.5')
    parser.add_argument('--optimize_weights', action='store_true', help='ScoringEngine ağırlıklarını optimize et.')
    parser.add_argument('--num_iterations', type=int, default=100, help='Optimizasyon için iterasyon sayısı. Varsayılan: 100')
    parser.add_argument('--datafile', type=str, default=None, help='Lokal veri dosyası (CSV formatında). Eğer belirtilirse, yfinance yerine bu dosya kullanılır.')

    args = parser.parse_args()

    logger.info(f"--- Backtest Simülasyonu ---")

    data = None
    try:
        if args.datafile:
            logger.info(f"Lokal veri dosyası kullanılıyor: {args.datafile}")
            data = pd.read_csv(args.datafile)
            # Tarih sütununu Datetime formatına çevirip index olarak ayarlama
            if 'Date' in data.columns:
                data['Date'] = pd.to_datetime(data['Date'])
                data.set_index('Date', inplace=True)
            elif 'Timestamp' in data.columns: # Farklı olası sütun adları
                data['Timestamp'] = pd.to_datetime(data['Timestamp'])
                data.set_index('Timestamp', inplace=True)
            else:
                # Eğer bilinen bir tarih sütunu yoksa, ilk sütunu kullanmayı dene
                potential_date_col = data.columns[0]
                logger.warning(f"Standart 'Date' veya 'Timestamp' sütunu bulunamadı. İlk sütun olan '{potential_date_col}' tarih olarak kullanılıyor.")
                data[potential_date_col] = pd.to_datetime(data[potential_date_col])
                data.set_index(potential_date_col, inplace=True)

            # yfinance ile uyumlu olması için sütun adlarını düzenle
            data.rename(columns={c: c.lower() for c in data.columns}, inplace=True)
            if 'volume btc' in data.columns:
                data.rename(columns={'volume btc': 'volume'}, inplace=True)
            logger.debug(f"Sütunlar yüklendikten ve küçük harfe çevrildikten sonra: {data.columns.tolist()}")
            # Sadece gerekli sütunları seç
            data = data[['open', 'high', 'low', 'close', 'volume']]


        else:
            logger.info(f"yfinance üzerinden {args.symbol} için veri çekiliyor...")
            ticker = yf.Ticker(args.symbol)
            data = ticker.history(period=args.period, interval=args.interval)
            data.rename(columns={c: c.lower() for c in data.columns}, inplace=True)
            logger.debug(f"Sütunlar yfinance'ten çekildikten ve küçük harfe çevrildikten sonra: {data.columns.tolist()}")
            # Sadece gerekli sütunları seç
            data = data[['open', 'high', 'low', 'close', 'volume']]

        if data.empty:
            logger.error(f"Hata: Veri çekilemedi veya dosya boş. Lütfen girdi parametrelerini kontrol edin.")
        else:
            simulator = BacktestSimulator(entry_threshold=args.entry_threshold, exit_threshold=args.exit_threshold)

            if args.optimize_weights:
                best_weights, best_results = simulator.optimize_scoring_engine_weights(data, args.num_iterations)
                logger.info(f"--- En İyi Optimizasyon Sonuçları ---")
                logger.info(f"En İyi Ağırlıklar: {best_weights}")
                logger.info(f"En İyi Toplam Getiri: {best_results['total_return']:.2%}")
                logger.info(f"Toplam İşlem Sayısı: {best_results['num_trades']}")
                logger.info(f"Kazanan İşlem Sayısı: {best_results['winning_trades']}")
                logger.info(f"Kaybeden İşlem Sayısı: {best_results['losing_trades']}")
                logger.info(f"Kazanma Oranı: {best_results['win_rate']:.2%}")
                logger.info(f"Maksimum Düşüş (Max Drawdown): {best_results['max_drawdown']:.2%}")
                logger.info(f"Sharpe Oranı: {best_results['sharpe_ratio']:.2f}")
            else:
                # Tekli backtest için skorları hesapla
                all_prediction_scores = []
                scoring_engine = ScoringEngine() # Varsayılan ağırlıklarla

                for i in range(len(data)):
                    if i < simulator.min_data_points_for_models:
                        all_prediction_scores.append(0.0)
                        continue
                    
                    historical_data = data.iloc[:i+1]
                    model_scores = calculate_all_model_scores(historical_data, simulator.models)
                    final_score = scoring_engine.generate_final_score(model_scores)
                    all_prediction_scores.append(final_score)
                
                prediction_scores_series = pd.Series(all_prediction_scores, index=data.index)
                prediction_scores_series = prediction_scores_series.fillna(0.0)

                results = simulator._run_single_backtest(data['Close'], prediction_scores_series)

                logger.info(f"Toplam Getiri: {results['total_return']:.2%}")
                logger.info(f"Toplam İşlem Sayısı: {results['num_trades']}")
                logger.info(f"Kazanan İşlem Sayısı: {results['winning_trades']}")
                logger.info(f"Kaybeden İşlem Sayısı: {results['losing_trades']}")
                logger.info(f"Kazanma Oranı: {results['win_rate']:.2%}")
                logger.info(f"Maksimum Düşüş (Max Drawdown): {results['max_drawdown']:.2%}")
                logger.info(f"Sharpe Oranı: {results['sharpe_ratio']:.2f}")

    except Exception as e:
        logger.error(f"Veri çekme veya backtest sırasında bir hata oluştu: {e}")
