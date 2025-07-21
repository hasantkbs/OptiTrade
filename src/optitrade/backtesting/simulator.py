import pandas as pd
import numpy as np
import yfinance as yf
import argparse
import random

# Modelleri içe aktar
from optitrade.models.price_trend_model import PriceTrendModel
from optitrade.models.volume_surge_model import VolumeSurgeModel
from optitrade.models.support_resistance_model import SupportResistanceModel
from optitrade.models.divergence_detection_model import DivergenceDetectionModel
from optitrade.scoring.scoring_engine import ScoringEngine

# Diğer modeller için şimdilik yer tutucu importlar (gerçek entegrasyon daha sonra)
from optitrade.models.news_sentiment_model import NewsSentimentModel
from optitrade.models.social_sentiment_model import SocialSentimentModel
from optitrade.models.event_impact_model import EventImpactModel
from optitrade.models.market_condition_classifier import MarketConditionClassifier

class BacktestSimulator:
    """
    Tahmin motorunun geçmiş verilerle doğruluğunu ölçen simülatör.
    """
    def __init__(self, entry_threshold: float = 0.5, exit_threshold: float = -0.5):
        """
        Simülatörü başlatır ve strateji eşiklerini ayarlar.

        Args:
            entry_threshold (float): Pozisyona girmek için tahmin skoru eşiği.
            exit_threshold (float): Pozisyondan çıkmak için tahmin skoru eşiği.
        """
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

        # Modelleri bir kez başlat
        self.price_trend_model = PriceTrendModel()
        self.volume_surge_model = VolumeSurgeModel()
        self.news_sentiment_model = NewsSentimentModel() # Bu modelin init'i zaman alabilir
        self.social_sentiment_model = SocialSentimentModel() # Bu modelin init'i zaman alabilir
        self.support_resistance_model = SupportResistanceModel()
        self.divergence_detection_model = DivergenceDetectionModel()
        self.event_impact_model = EventImpactModel()
        self.market_condition_classifier = MarketConditionClassifier()

        # Modeller için minimum veri noktalarını hesapla
        self.min_data_points_for_models = max(
            self.price_trend_model.sma_long_window,
            self.volume_surge_model.volume_ma_window,
            self.divergence_detection_model.extrema_order * 2 + 1
        )

    def _run_single_backtest(self, prices: pd.Series, prediction_scores: pd.Series) -> dict:
        """
        Basit bir alım/satım stratejisi uygulayarak tek bir backtest yapar.
        """
        if prices.empty or prediction_scores.empty:
            return {'total_return': 0.0, 'num_trades': 0, 'winning_trades': 0, 'losing_trades': 0, 'win_rate': 0.0}

        # Verileri hizala
        common_index = prices.index.intersection(prediction_scores.index)
        prices = prices.loc[common_index]
        prediction_scores = prediction_scores.loc[common_index]

        if prices.empty or prediction_scores.empty:
            return {'total_return': 0.0, 'num_trades': 0, 'winning_trades': 0, 'losing_trades': 0, 'win_rate': 0.0}

        # Başlangıç sermayesi
        initial_capital = 1000.0
        capital = initial_capital
        position = 0 # 0: pozisyon yok, 1: uzun pozisyon
        trade_returns = []
        entry_price = 0.0

        for i in range(1, len(prices)):
            current_price = prices.iloc[i]
            current_score = prediction_scores.iloc[i]

            # Pozisyona girme
            if position == 0 and current_score >= self.entry_threshold:
                position = 1
                entry_price = current_price

            # Pozisyondan çıkma
            elif position == 1 and current_score <= self.exit_threshold:
                position = 0
                trade_return = (current_price - entry_price) / entry_price
                trade_returns.append(trade_return)
                capital *= (1 + trade_return)

        # Açık pozisyonu kapat (varsa)
        if position == 1:
            trade_return = (prices.iloc[-1] - entry_price) / entry_price
            trade_returns.append(trade_return)
            capital *= (1 + trade_return)

        total_return = (capital - initial_capital) / initial_capital
        num_trades = len(trade_returns)
        winning_trades = sum(1 for r in trade_returns if r > 0)
        losing_trades = sum(1 for r in trade_returns if r <= 0)
        win_rate = winning_trades / num_trades if num_trades > 0 else 0.0

        return {
            'total_return': float(total_return),
            'num_trades': num_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': float(win_rate)
        }

    def _calculate_all_model_scores_for_date(self, historical_data: pd.DataFrame) -> dict:
        """
        Belirli bir tarih için tüm modellerden skorları hesaplar.
        """
        model_scores = {}

        # PriceTrendModel
        model_scores['price_trend_score'] = self.price_trend_model.generate_score(historical_data)
        
        # VolumeSurgeModel
        volume_score, impact_score = self.volume_surge_model.generate_score(historical_data)
        model_scores['volume_surge_score'] = volume_score

        # SupportResistanceModel
        model_scores['support_resistance_score'] = self.support_resistance_model.generate_proximity_score(historical_data)

        # DivergenceDetectionModel
        divergence_result = self.divergence_detection_model.detect_divergence(historical_data, indicator_type='rsi')
        model_scores['divergence_score'] = divergence_result['score']

        # NewsSentimentModel (Gerçek entegrasyon daha sonra)
        # Bu kısım için gerçek haber metinleri çekilmeli ve analiz edilmeli.
        # Şimdilik rastgele skor kullanıyorum.
        model_scores['news_sentiment_score'] = random.uniform(-1.0, 1.0)

        # SocialSentimentModel (Gerçek entegrasyon daha sonra)
        # Bu kısım için gerçek sosyal medya metinleri çekilmeli ve analiz edilmeli.
        # Şimdilik rastgele skor kullanıyorum.
        model_scores['social_sentiment_score'] = random.uniform(-1.0, 1.0)

        # EventImpactModel (Gerçek entegrasyon daha sonra)
        # Bu kısım için güncel olay verileri çekilmeli.
        model_scores['event_impact_score'] = self.event_impact_model.calculate_impact(historical_data.index[-1])

        # MarketConditionClassifier (Gerçek entegrasyon daha sonra)
        # Bu kısım için güncel VIX, BTC Dominance, Total Market Cap verileri çekilmeli.
        # Şimdilik varsayılan veya rastgele değerler kullanıyorum.
        vix_val = random.uniform(15.0, 35.0)
        btc_dom_val = random.uniform(0.4, 0.6)
        mcap_val = random.uniform(500_000_000_000, 2_000_000_000_000)
        market_condition = self.market_condition_classifier.classify_market_condition(vix_val, btc_dom_val, mcap_val)
        model_scores['market_condition_score'] = market_condition

        return model_scores

    def optimize_scoring_engine_weights(self, data: pd.DataFrame, num_iterations: int = 100) -> tuple[dict, dict]:
        """
        ScoringEngine ağırlıklarını optimize etmek için rastgele arama yapar.

        Args:
            data (pd.DataFrame): OHLCV verilerini içeren pandas DataFrame.
            num_iterations (int): Denenecek ağırlık kombinasyonu sayısı.

        Returns:
            tuple[dict, dict]: (best_weights, best_results)
        """
        print(f"\n--- ScoringEngine Ağırlık Optimizasyonu Başlatılıyor ({num_iterations} iterasyon) ---")

        best_weights = None
        best_return = -np.inf
        best_results = {}

        # Optimize edilecek skor isimleri (ScoringEngine'in varsayılan ağırlıklarından alınır)
        dummy_engine = ScoringEngine() # Geçici bir örnek oluştur
        score_names = list(dummy_engine.weights.keys())

        for iteration in range(num_iterations):
            # Rastgele ağırlıklar oluştur
            random_weights_values = [random.random() for _ in score_names]
            total_random_weight = sum(random_weights_values)
            
            # Ağırlıkları normalize et
            current_weights = {name: value / total_random_weight for name, value in zip(score_names, random_weights_values)}

            # ScoringEngine'i mevcut ağırlıklarla başlat
            current_scoring_engine = ScoringEngine(weights=current_weights)

            all_prediction_scores = []
            for i in range(len(data)):
                if i < self.min_data_points_for_models:
                    all_prediction_scores.append(0.0)
                    continue
                
                historical_data = data.iloc[:i+1]
                model_scores = self._calculate_all_model_scores_for_date(historical_data)
                final_score = current_scoring_engine.generate_final_score(model_scores)
                all_prediction_scores.append(final_score)
            
            prediction_scores_series = pd.Series(all_prediction_scores, index=data.index)
            prediction_scores_series = prediction_scores_series.fillna(0.0)

            # Backtest'i çalıştır
            results = self._run_single_backtest(data['Close'], prediction_scores_series)

            if results['total_return'] > best_return:
                best_return = results['total_return']
                best_weights = current_weights
                best_results = results
            
            if (iteration + 1) % (num_iterations // 10) == 0 or iteration == num_iterations - 1:
                print(f"  İterasyon {iteration + 1}/{num_iterations} - En İyi Getiri: {best_return:.2%}")

        print("--- Optimizasyon Tamamlandı ---")
        return best_weights, best_results

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Tahmin motorunun geçmiş verilerle doğruluğunu ölçen backtest simülatörü.')
    parser.add_argument('--symbol', type=str, default='AAPL', help='Hisse senedi/kripto para sembolü (örn: BTC-USD, AAPL). Varsayılan: AAPL')
    parser.add_argument('--period', type=str, default='1y', help='Veri çekme periyodu (örn: 1y, 6mo, 1mo). Varsayılan: 1y')
    parser.add_argument('--interval', type=str, default='1d', help='Veri çekme aralığı (örn: 1d, 1wk, 1mo). Varsayılan: 1d')
    parser.add_argument('--entry_threshold', type=float, default=0.5, help='Pozisyona girmek için tahmin skoru eşiği. Varsayılan: 0.5')
    parser.add_argument('--exit_threshold', type=float, default=-0.5, help='Pozisyondan çıkmak için tahmin skoru eşiği. Varsayılan: -0.5')
    parser.add_argument('--optimize_weights', action='store_true', help='ScoringEngine ağırlıklarını optimize et.')
    parser.add_argument('--num_iterations', type=int, default=100, help='Optimizasyon için iterasyon sayısı. Varsayılan: 100')

    args = parser.parse_args()

    print(f"\n--- {args.symbol} için Backtest Simülasyonu ---")

    try:
        ticker = yf.Ticker(args.symbol)
        data = ticker.history(period=args.period, interval=args.interval)

        if data.empty:
            print(f"Hata: {args.symbol} için veri çekilemedi veya yeterli veri yok. Lütfen sembolü ve periyodu kontrol edin.")
        else:
            simulator = BacktestSimulator(entry_threshold=args.entry_threshold, exit_threshold=args.exit_threshold)

            if args.optimize_weights:
                best_weights, best_results = simulator.optimize_scoring_engine_weights(data, args.num_iterations)
                print(f"\n--- En İyi Optimizasyon Sonuçları ---")
                print(f"En İyi Ağırlıklar: {best_weights}")
                print(f"En İyi Toplam Getiri: {best_results['total_return']:.2%}")
                print(f"Toplam İşlem Sayısı: {best_results['num_trades']}")
                print(f"Kazanan İşlem Sayısı: {best_results['winning_trades']}")
                print(f"Kaybeden İşlem Sayısı: {best_results['losing_trades']}")
                print(f"Kazanma Oranı: {best_results['win_rate']:.2%}")
            else:
                # Tekli backtest için skorları hesapla
                all_prediction_scores = []
                scoring_engine = ScoringEngine() # Varsayılan ağırlıklarla

                for i in range(len(data)):
                    if i < simulator.min_data_points_for_models:
                        all_prediction_scores.append(0.0)
                        continue
                    
                    historical_data = data.iloc[:i+1]
                    model_scores = simulator._calculate_all_model_scores_for_date(historical_data)
                    final_score = scoring_engine.generate_final_score(model_scores)
                    all_prediction_scores.append(final_score)
                
                prediction_scores_series = pd.Series(all_prediction_scores, index=data.index)
                prediction_scores_series = prediction_scores_series.fillna(0.0)

                results = simulator._run_single_backtest(data['Close'], prediction_scores_series)

                print(f"Toplam Getiri: {results['total_return']:.2%}")
                print(f"Toplam İşlem Sayısı: {results['num_trades']}")
                print(f"Kazanan İşlem Sayısı: {results['winning_trades']}")
                print(f"Kaybeden İşlem Sayısı: {results['losing_trades']}")
                print(f"Kazanma Oranı: {results['win_rate']:.2%}")

    except Exception as e:
        print(f"Veri çekme veya backtest sırasında bir hata oluştu: {e}")
