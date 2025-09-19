import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Kelly Kriteri sonucunda önerilebilecek maksimum pozisyon büyüklüğü (sermayenin yüzdesi).
# Bu, formülün çok agresif sonuçlar vermesini engeller.
MAX_POSITION_PERCENTAGE = 0.20  # %20

def calculate_position_size(final_score: float, current_price: float, target_price: Optional[float], stop_loss_price: Optional[float]) -> Dict[str, Any]:
    """
    Basitleştirilmiş Kelly Kriteri'ni kullanarak önerilen pozisyon büyüklüğünü hesaplar.

    Args:
        final_score (float): ScoringEngine'den gelen nihai skor (-1 ile 1 arası).
        current_price (float): Varlığın mevcut piyasa fiyatı.
        target_price (Optional[float]): Tahmini kar al (take-profit) seviyesi.
        stop_loss_price (Optional[float]): Tahmini zarar durdur (stop-loss) seviyesi.

    Returns:
        Dict[str, Any]: Önerilen pozisyon büyüklüğü ve hesaplama detaylarını içeren bir sözlük.
    """
    if target_price is None or stop_loss_price is None or current_price is None:
        return {
            "percentage": 0.0,
            "details": "Hedef fiyat veya zarar durdurma seviyesi hesaplanamadığı için pozisyon büyüklüğü belirlenemedi."
        }

    # Potansiyel kazanç ve kaybı hesapla
    potential_gain = abs(target_price - current_price)
    potential_loss = abs(current_price - stop_loss_price)

    if potential_loss == 0:
        return {
            "percentage": 0.0,
            "details": "Potansiyel kayıp sıfır, pozisyon büyüklüğü hesaplanamıyor (zarar durdurma seviyesi mevcut fiyata eşit)."
        }

    # 1. Kazanma Olasılığını (W) final_score'dan türet
    # final_score [-1, 1] aralığında. Bunu [0, 1] aralığına ölçeklendiriyoruz.
    # 0.5 taban olasılık (yazı-tura) olarak kabul edilir.
    win_probability = 0.5 + (final_score / 2.0)

    # 2. Kazanç/Kayıp Oranını (R) hesapla
    win_loss_ratio = potential_gain / potential_loss

    # 3. Kelly Kriteri Formülünü Uygula: K% = W - (1 - W) / R
    try:
        kelly_percentage = win_probability - ((1 - win_probability) / win_loss_ratio)
    except (ZeroDivisionError, OverflowError):
        kelly_percentage = 0.0

    # Sonuçları mantıklı sınırlar içinde tut
    if kelly_percentage > 0:
        # Agresif sonuçları engellemek için maksimum bir tavan uygula
        final_percentage = min(kelly_percentage, MAX_POSITION_PERCENTAGE)
        details = f"Kelly Kriteri'ne göre önerilen pozisyon: sermayenin %{final_percentage:.2%}'i. (Hesaplanan: %{kelly_percentage:.2%}, Tavan: %{MAX_POSITION_PERCENTAGE:.2%})"
    else:
        final_percentage = 0.0
        details = "Hesaplanan Kelly değeri pozitif değil, pozisyon önerilmiyor."

    logger.info(f"Pozisyon büyüklüğü hesaplandı: {details}")

    return {
        "percentage": final_percentage,
        "details": details
    }
