import argparse
import pandas as pd
import yfinance as yf
import logging
import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from optitrade.backtesting.simulator import BacktestSimulator
from optitrade.utils.data_fetcher import MarketDataFetcher
from optitrade.scoring.scoring_engine import ScoringEngine # ScoringEngine'i içe aktar
from optitrade.models.main import calculate_all_model_scores # calculate_all_model_scores'u içe aktar
from optitrade import config

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

def main():
    parser = argparse.ArgumentParser(description='OptiTrade Scoring Engine ve Backtest Simülatörü.')
    parser.add_argument('--symbol', type=str, default='BTC-USD', help='Hisse senedi/kripto para sembolü (örn: BTC-USD, AAPL). Varsayılan: BTC-USD')
    parser.add_argument('--period', type=str, default='max', help='Veri çekme periyodu (örn: 1y, 6mo, max). Varsayılan: max')
    parser.add_argument('--interval', type=str, default='1d', choices=['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo'], help='Veri çekme aralığı (yfinance için: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo). Varsayılan: 1d')
    parser.add_argument('--entry_threshold', type=float, default=0.5, help='Pozisyona girmek için tahmin skoru eşiği. Varsayılan: 0.5')
    parser.add_argument('--exit_threshold', type=float, default=-0.5, help='Pozisyondan çıkmak için tahmin skoru eşiği. Varsayılan: -0.5')
    parser.add_argument('--optimize_weights', action='store_true', help='ScoringEngine ağırlıklarını optimize et.')
    parser.add_argument('--num_iterations', type=int, default=100, help='Optimizasyon için iterasyon sayısı. Varsayılan: 100')
    parser.add_argument('--compare_strategies', action='store_true', help='Farklı giriş/çıkış eşikleriyle stratejileri karşılaştır.')

    args = parser.parse_args()

    logger.info(f"--- {args.symbol} için Analiz Başlatılıyor ---")

    try:
        # Veri çekme
        market_fetcher = MarketDataFetcher()
        data = market_fetcher.fetch_market_data(
            symbol=args.symbol,
            period=args.period,
            interval=args.interval,
            data_source='yfinance' # Varsayılan olarak yfinance kullan
        )

        if data.empty:
            logger.error(f"Hata: {args.symbol} için veri çekilemedi veya yeterli veri yok. Lütfen sembolü, periyodu ve aralığı kontrol edin.")
            return

        simulator = BacktestSimulator(entry_threshold=args.entry_threshold, exit_threshold=args.exit_threshold)

        if args.optimize_weights:
            best_weights, best_results = simulator.optimize_scoring_engine_weights(data, args.num_iterations)
            logger.info(f"\n--- En İyi Optimizasyon Sonuçları ---")
            logger.info(f"En İyi Ağırlıklar: {best_weights}")
            logger.info(f"En İyi Toplam Getiri: {best_results['total_return']:.2%}")
            logger.info(f"Toplam İşlem Sayısı: {best_results['num_trades']}")
            logger.info(f"Kazanan İşlem Sayısı: {best_results['winning_trades']}")
            logger.info(f"Kaybeden İşlem Sayısı: {best_results['losing_trades']}")
            logger.info(f"Kazanma Oranı: {best_results['win_rate']:.2%}")
            logger.info(f"Maksimum Düşüş (Max Drawdown): {best_results['max_drawdown']:.2%}")
            logger.info(f"Sharpe Oranı: {best_results['sharpe_ratio']:.2f}")
        elif args.compare_strategies:
            logger.info("--- Farklı Stratejiler Karşılaştırılıyor ---")
            # Karşılaştırılacak eşik kombinasyonları
            threshold_combinations = [
                (0.5, -0.5), # Varsayılan
                (0.6, -0.4), # Daha agresif giriş, daha az agresif çıkış
                (0.4, -0.6), # Daha az agresif giriş, daha agresif çıkış
                (0.7, -0.7), # Daha yüksek eşikler
            ]
            
            results_list = []
            for entry, exit in threshold_combinations:
                logger.info(f"\nStrateji: Giriş={entry:.2f}, Çıkış={exit:.2f}")
                current_simulator = BacktestSimulator(entry_threshold=entry, exit_threshold=exit)
                
                all_prediction_scores = []
                scoring_engine = ScoringEngine() # Varsayılan ağırlıklarla

                for i in range(len(data)):
                    if i < current_simulator.min_data_points_for_models:
                        all_prediction_scores.append(0.0)
                        continue
                    
                    historical_data_slice = data.iloc[:i+1]
                    # calculate_all_model_scores fonksiyonuna interval parametresini ilet
                    model_scores = calculate_all_model_scores(historical_data_slice, current_simulator.models, interval=args.interval)
                    final_score = scoring_engine.generate_final_score(model_scores)
                    all_prediction_scores.append(float(final_score))
                
                logger.debug(f"Contents of all_prediction_scores before Series conversion: {all_prediction_scores}")
                prediction_scores_series = pd.Series(all_prediction_scores, index=data.index).astype(float).fillna(0.0)
                logger.debug(f"prediction_scores_series dtype: {prediction_scores_series.dtype}, head: {prediction_scores_series.head()}")

                results = current_simulator._run_single_backtest(data['Close'].fillna(0.0), prediction_scores_series)
                results_list.append({'entry_threshold': entry, 'exit_threshold': exit, **results})

                logger.info(f"  Toplam Getiri: {results['total_return']:.2%}")
                logger.info(f"  Kazanma Oranı: {results['win_rate']:.2%}")
                logger.info(f"  Maksimum Düşüş: {results['max_drawdown']:.2%}")
                logger.info(f"  Sharpe Oranı: {results['sharpe_ratio']:.2f}")
            
            logger.info("\n--- Karşılaştırma Sonuçları Özeti ---")
            for res in results_list:
                logger.info(f"Strateji (Giriş: {res['entry_threshold']:.2f}, Çıkış: {res['exit_threshold']:.2f}): Toplam Getiri: {res['total_return']:.2%}, Kazanma Oranı: {res['win_rate']:.2%}, Max Düşüş: {res['max_drawdown']:.2%}, Sharpe Oranı: {res['sharpe_ratio']:.2f}")

        else:
            # Tekli backtest için skorları hesapla
            all_prediction_scores = []
            scoring_engine = ScoringEngine() # Varsayılan ağırlıklarla

            for i in range(len(data)):
                if i < simulator.min_data_points_for_models:
                    all_prediction_scores.append(0.0)
                    continue
                
                historical_data_slice = data.iloc[:i+1]
                # calculate_all_model_scores fonksiyonuna interval parametresini ilet
                model_scores = calculate_all_model_scores(historical_data_slice, simulator.models, interval=args.interval)
                final_score = scoring_engine.generate_final_score(model_scores)
                all_prediction_scores.append(float(final_score))
            
            prediction_scores_series = pd.Series(all_prediction_scores, index=data.index).astype(float).fillna(0.0)
            logger.debug(f"prediction_scores_series dtype: {prediction_scores_series.dtype}, head: {prediction_scores_series.head()}")

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

if __name__ == "__main__":
    main()