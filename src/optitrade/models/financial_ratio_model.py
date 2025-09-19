import logging
from typing import Dict, Any
import numpy as np
import pandas as pd
from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)

class FinancialRatioModel(BaseModel):
    """
    Hisse senetleri için temel finansal oranları (F/K, P/B, D/E, EPS Büyümesi, P/S, FAVÖK Marjı) hesaplar ve
    buna göre bir skor üretir.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)
        # Oranlar için eşik değerleri (bunlar daha sonra optimize edilebilir)
        self.pe_thresholds = {'low': 15, 'high': 25}
        self.pb_thresholds = {'low': 1.0, 'high': 3.0}
        self.de_thresholds = {'low': 0.5, 'high': 1.0} # Borç/Özkaynak
        self.eps_growth_thresholds = {'low': 0.05, 'high': 0.15} # EPS Büyümesi (%)
        self.ps_thresholds = {'low': 1.0, 'high': 2.0} # Fiyat/Satış
        self.ebitda_margin_thresholds = {'low': 0.10, 'high': 0.20} # FAVÖK Marjı (%)

    def predict(self, symbol: str, interval: str = "1d", asset_type: str = "crypto", **kwargs) -> Dict[str, Any]:
        """
        Finansal oranları hesaplar ve bir alım/satım skoru döndürür.
        """
        if asset_type != 'stock':
            return {'score': 0.0, 'details': 'Bu model sadece hisse senetleri için çalışır.'}

        try:
            # 1. Gerekli verileri çek
            ticker_info = self.data_fetcher.get_ticker_info(symbol)
            financials_json = self.data_fetcher.get_financial_statement(symbol, 'financials')
            balance_sheet_json = self.data_fetcher.get_financial_statement(symbol, 'balance_sheet')
            market_data = self.data_fetcher.get_market_data(asset_type='stock', symbol=symbol, period='1y', interval='1d')

            if not all([ticker_info, financials_json, balance_sheet_json]) or market_data.empty:
                logger.warning(f"'{symbol}' için finansal oranları hesaplamak için yeterli veri bulunamadı.")
                return {'score': 0.0, 'details': 'Gerekli finansal veriler eksik.'}

            # JSON stringleri pandas DataFrame'e çevir
            financials = pd.read_json(financials_json, orient='index')
            balance_sheet = pd.read_json(balance_sheet_json, orient='index')

            # 2. Gerekli değerleri ayıkla
            current_price = market_data['Close'].iloc[-1]
            shares_outstanding = ticker_info.get('sharesOutstanding')
            market_cap = ticker_info.get('marketCap')

            # En son yılın verilerini al
            latest_financials = financials.iloc[:, 0]
            latest_balance_sheet = balance_sheet.iloc[:, 0]

            net_income = latest_financials.get('Net Income')
            book_value = latest_balance_sheet.get('Total Stockholder Equity')
            total_liabilities = latest_balance_sheet.get('Total Liab')
            total_revenue = latest_financials.get('Total Revenue')
            ebitda = latest_financials.get('Ebitda')

            if not all([current_price, shares_outstanding, market_cap, net_income, book_value, total_liabilities, total_revenue, ebitda]):
                return {'score': 0.0, 'details': 'Oranları hesaplamak için temel değerler eksik.'}

            # 3. Oranları Hesapla
            eps = net_income / shares_outstanding
            pe_ratio = current_price / eps if eps > 0 else np.inf
            pb_ratio = market_cap / book_value if book_value > 0 else np.inf
            de_ratio = total_liabilities / book_value if book_value > 0 else np.inf
            ps_ratio = market_cap / total_revenue if total_revenue > 0 else np.inf
            ebitda_margin = ebitda / total_revenue if total_revenue > 0 else 0.0
            eps_growth = self._calculate_eps_growth(financials, shares_outstanding)

            # 4. Skorlama
            pe_score = self._calculate_pe_score(pe_ratio)
            pb_score = self._calculate_pb_score(pb_ratio)
            de_score = self._calculate_de_score(de_ratio)
            eps_growth_score = self._calculate_eps_growth_score(eps_growth)
            ps_score = self._calculate_ps_score(ps_ratio)
            ebitda_margin_score = self._calculate_ebitda_margin_score(ebitda_margin)

            # Ağırlıklı ortalama (şimdilik eşit ağırlık)
            scores = [pe_score, pb_score, de_score, eps_growth_score, ps_score, ebitda_margin_score]
            final_score = np.mean(scores)

            return {
                'score': final_score,
                'details': {
                    'P/E Ratio': pe_ratio,
                    'P/B Ratio': pb_ratio,
                    'D/E Ratio': de_ratio,
                    'EPS Growth (YoY)': eps_growth,
                    'P/S Ratio': ps_ratio,
                    'EBITDA Margin': ebitda_margin,
                    'P/E Score': pe_score,
                    'P/B Score': pb_score,
                    'D/E Score': de_score,
                    'EPS Growth Score': eps_growth_score,
                    'P/S Score': ps_score,
                    'EBITDA Margin Score': ebitda_margin_score
                }
            }

        except Exception as e:
            logger.error(f"'{symbol}' için finansal oran modeli çalıştırılırken hata: {e}", exc_info=True)
            return {'score': 0.0, 'details': f'Model çalışırken bir hata oluştu: {e}'}

    def _calculate_eps_growth(self, financials: pd.DataFrame, shares_outstanding: float) -> float:
        """Yıllık EPS büyümesini hesaplar."""
        if financials.shape[1] < 2: # En az 2 yıllık veri gerekli
            return 0.0
        
        try:
            net_income_t0 = financials.iloc[:, 0].get('Net Income') # En son yıl
            net_income_t1 = financials.iloc[:, 1].get('Net Income') # Bir önceki yıl

            if not all([net_income_t0, net_income_t1, shares_outstanding > 0]):
                return 0.0

            eps_t0 = net_income_t0 / shares_outstanding
            eps_t1 = net_income_t1 / shares_outstanding

            if eps_t1 == 0: # Bölme hatasını önle
                return np.inf if eps_t0 > 0 else 0.0
            
            return (eps_t0 - eps_t1) / abs(eps_t1)
        except (IndexError, KeyError, TypeError) as e:
            logger.warning(f"EPS büyümesi hesaplanırken veri hatası: {e}")
            return 0.0

    def _calculate_pe_score(self, pe_ratio: float) -> float:
        """F/K oranına göre bir skor (-1 ile 1 arası) hesaplar."""
        if pe_ratio <= 0:
            return -0.5
        if pe_ratio < self.pe_thresholds['low']:
            return 1.0
        elif pe_ratio < self.pe_thresholds['high']:
            return 1.0 - (pe_ratio - self.pe_thresholds['low']) / (self.pe_thresholds['high'] - self.pe_thresholds['low'])
        else:
            return -1.0

    def _calculate_pb_score(self, pb_ratio: float) -> float:
        """P/B oranına göre bir skor (-1 ile 1 arası) hesaplar."""
        if pb_ratio <= 0:
            return -0.5
        if pb_ratio < self.pb_thresholds['low']:
            return 1.0
        elif pb_ratio < self.pb_thresholds['high']:
            return 1.0 - (pb_ratio - self.pb_thresholds['low']) / (self.pb_thresholds['high'] - self.pb_thresholds['low'])
        else:
            return -1.0

    def _calculate_de_score(self, de_ratio: float) -> float:
        """Borç/Özkaynak oranına göre bir skor (-1 ile 1 arası) hesaplar."""
        if de_ratio < self.de_thresholds['low']:
            return 1.0
        elif de_ratio < self.de_thresholds['high']:
            return 1.0 - (de_ratio - self.de_thresholds['low']) / (self.de_thresholds['high'] - self.de_thresholds['low'])
        else:
            return -1.0

    def _calculate_eps_growth_score(self, eps_growth: float) -> float:
        """EPS büyüme oranına göre bir skor (-1 ile 1 arası) hesaplar."""
        if eps_growth < self.eps_growth_thresholds['low']:
            return -1.0
        elif eps_growth < self.eps_growth_thresholds['high']:
            return (eps_growth - self.eps_growth_thresholds['low']) / (self.eps_growth_thresholds['high'] - self.eps_growth_thresholds['low'])
        else:
            return 1.0

    def _calculate_ps_score(self, ps_ratio: float) -> float:
        """Fiyat/Satış oranına göre bir skor (-1 ile 1 arası) hesaplar."""
        if ps_ratio <= 0:
            return -0.5
        if ps_ratio < self.ps_thresholds['low']:
            return 1.0
        elif ps_ratio < self.ps_thresholds['high']:
            return 1.0 - (ps_ratio - self.ps_thresholds['low']) / (self.ps_thresholds['high'] - self.ps_thresholds['low'])
        else:
            return -1.0

    def _calculate_ebitda_margin_score(self, ebitda_margin: float) -> float:
        """FAVÖK marjına göre bir skor (-1 ile 1 arası) hesaplar."""
        if ebitda_margin < self.ebitda_margin_thresholds['low']:
            return -1.0
        elif ebitda_margin < self.ebitda_margin_thresholds['high']:
            return (ebitda_margin - self.ebitda_margin_thresholds['low']) / (self.ebitda_margin_thresholds['high'] - self.ebitda_margin_thresholds['low'])
        else:
            return 1.0
