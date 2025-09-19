import logging
from typing import Dict, Any
import numpy as np
import pandas as pd
from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)

class DCFModel(BaseModel):
    """
    İndirgenmiş Nakit Akışları (DCF) değerlemesi yaparak bir hisse senedinin
    içsel değerini hesaplar ve mevcut fiyata göre bir skor üretir.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)
        # Model için varsayılan parametreler (daha sonra config'den alınabilir)
        self.projection_years = 5 # Nakit akışı tahmin yılı
        self.perpetual_growth_rate = 0.025 # Uzun vadeli büyüme oranı (enflasyon oranına yakın)
        self.market_return = 0.08 # Beklenen piyasa getirisi

import logging
from typing import Dict, Any, List
import numpy as np
import pandas as pd
from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)

class DCFModel(BaseModel):
    """
    İndirgenmiş Nakit Akışları (DCF) değerlemesi yaparak bir hisse senedinin
    içsel değerini hesaplar ve mevcut fiyata göre bir skor üretir.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)
        self.projection_years = 5
        self.perpetual_growth_rate = 0.025
        self.market_return = 0.08

    def predict(self, symbol: str, interval: str = "1d", asset_type: str = "crypto", **kwargs) -> Dict[str, Any]:
        """
        DCF analizi yapar ve hisse senedinin potansiyeline göre bir skor döndürür.
        """
        if asset_type != 'stock':
            return {'score': 0.0, 'details': 'Bu model sadece hisse senetleri için çalışır.'}

        try:
            # Adım 1: Gerekli tüm finansal verileri çek
            ticker_info = self.data_fetcher.get_ticker_info(symbol)
            cashflow_json = self.data_fetcher.get_financial_statement(symbol, 'cashflow')
            financials_json = self.data_fetcher.get_financial_statement(symbol, 'financials')
            balance_sheet_json = self.data_fetcher.get_financial_statement(symbol, 'balance_sheet')
            risk_free_rate = self.data_fetcher.get_risk_free_rate()
            market_data = self.data_fetcher.get_market_data(asset_type='stock', symbol=symbol, period='1y', interval='1d')

            if not all([ticker_info, cashflow_json, financials_json, balance_sheet_json, risk_free_rate]) or market_data.empty:
                return {'score': 0.0, 'details': 'DCF için gerekli temel veriler eksik.'}

            current_price = market_data['Close'].iloc[-1]
            
            # Adım 2: İçsel Değeri Hesapla
            intrinsic_value, details = self._calculate_intrinsic_value(
                ticker_info, cashflow_json, financials_json, balance_sheet_json, risk_free_rate
            )

            if intrinsic_value is None:
                return {'score': 0.0, 'details': details}

            # Adım 3: Skor Üret
            score = self._calculate_score(intrinsic_value, current_price)
            
            details['Intrinsic Value'] = intrinsic_value
            details['Current Price'] = current_price
            details['Upside Potential'] = (intrinsic_value - current_price) / current_price

            return {'score': score, 'details': details}

        except Exception as e:
            logger.error(f"'{symbol}' için DCF modeli çalıştırılırken hata: {e}", exc_info=True)
            return {'score': 0.0, 'details': f'Model çalışırken bir hata oluştu: {e}'}

    def _calculate_wacc(self, ticker_info: Dict, financials: pd.DataFrame, balance_sheet: pd.DataFrame, risk_free_rate: float) -> float:
        """Ağırlıklı Ortalama Sermaye Maliyetini (WACC) hesaplar."""
        # Gerekli verileri al
        market_cap = ticker_info.get('marketCap')
        beta = ticker_info.get('beta')
        total_debt = balance_sheet.iloc[0].get('Total Liab')
        interest_expense = financials.iloc[0].get('Interest Expense')
        income_before_tax = financials.iloc[0].get('Income Before Tax')

        if not all([market_cap, beta, total_debt, interest_expense, income_before_tax]):
            raise ValueError("WACC hesaplamak için veriler eksik.")

        # Özkaynak Maliyeti (Re) - CAPM
        cost_of_equity = risk_free_rate + beta * (self.market_return - risk_free_rate)

        # Borç Maliyeti (Rd)
        cost_of_debt = abs(interest_expense) / total_debt if total_debt > 0 else 0

        # Vergi Oranı (Tc)
        tax_rate = (abs(financials.iloc[0].get('Income Tax Expense', 0)) / income_before_tax) if income_before_tax > 0 else 0.21

        # WACC Hesaplaması
        equity_value = market_cap
        debt_value = total_debt
        total_value = equity_value + debt_value
        wacc = ((equity_value / total_value) * cost_of_equity) + (((debt_value / total_value) * cost_of_debt) * (1 - tax_rate))
        
        return wacc, {'WACC': wacc, 'Cost of Equity': cost_of_equity, 'Cost of Debt': cost_of_debt, 'Tax Rate': tax_rate}

    def _calculate_fcf(self, cashflow: pd.DataFrame) -> List[float]:
        """Tarihsel Serbest Nakit Akışını (FCF) hesaplar."""
        fcf_list = []
        for i in range(cashflow.shape[1]):
            op_cashflow = cashflow.iloc[:, i].get('Total Cash From Operating Activities')
            cap_ex = abs(cashflow.iloc[:, i].get('Capital Expenditures', 0))
            if op_cashflow is not None:
                fcf_list.append(op_cashflow - cap_ex)
        return fcf_list

    def _calculate_intrinsic_value(self, ticker_info, cashflow_json, financials_json, balance_sheet_json, risk_free_rate: float):
        """DCF analizi yaparak içsel değeri hesaplar."""
        # JSON'ları DataFrame'e çevir
        cashflow = pd.read_json(cashflow_json, orient='index')
        financials = pd.read_json(financials_json, orient='index')
        balance_sheet = pd.read_json(balance_sheet_json, orient='index')

        # WACC Hesapla
        wacc, wacc_details = self._calculate_wacc(ticker_info, financials, balance_sheet, risk_free_rate)

        # FCF Hesapla ve Büyüme Oranını Bul
        historical_fcf = self._calculate_fcf(cashflow)
        if len(historical_fcf) < 2:
            return None, {"Error": "FCF büyümesini hesaplamak için yeterli tarihsel veri yok."}
        
        growth_rates = [(historical_fcf[i] - historical_fcf[i+1]) / abs(historical_fcf[i+1]) for i in range(len(historical_fcf)-1)]
        fcf_growth_rate = np.mean(growth_rates) if growth_rates else 0.05
        fcf_growth_rate = max(0, min(fcf_growth_rate, 0.15)) # Büyümeyi mantıklı bir aralıkta tut

        # Gelecekteki FCF'leri Tahminle
        last_fcf = historical_fcf[0]
        projected_fcf = [last_fcf * (1 + fcf_growth_rate)**i for i in range(1, self.projection_years + 1)]

        # Terminal Değeri Hesapla
        terminal_value = (projected_fcf[-1] * (1 + self.perpetual_growth_rate)) / (wacc - self.perpetual_growth_rate)

        # İndirgeme
        dcf_values = [fcf / (1 + wacc)**(i+1) for i, fcf in enumerate(projected_fcf)]
        terminal_dcf = terminal_value / (1 + wacc)**self.projection_years

        # Şirket Değeri ve Hisse Başına Değer
        total_company_value = sum(dcf_values) + terminal_dcf
        shares_outstanding = ticker_info.get('sharesOutstanding')
        intrinsic_value = total_company_value / shares_outstanding if shares_outstanding else 0

        details = {
            **wacc_details,
            'FCF Growth Rate (used)': fcf_growth_rate,
            'Historical FCF': historical_fcf,
            'Projected FCF': projected_fcf,
            'Terminal Value': terminal_value,
            'Intrinsic Value': intrinsic_value
        }
        return intrinsic_value, details

    def _calculate_score(self, intrinsic_value: float, current_price: float) -> float:
        """İçsel değer ve mevcut fiyata göre bir skor üretir."""
        if current_price == 0: return 0.0
        upside = (intrinsic_value - current_price) / current_price
        # Skoru -1 ve 1 arasına sıkıştırmak için tanh fonksiyonunu kullan
        # 50% upside/downside sonrası skorun doygunluğa ulaşmasını sağlar (2 * 0.5 = 1)
        score = np.tanh(upside * 2)
        return score
