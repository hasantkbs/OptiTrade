"""
OptiTrade — Trading Session Analysis Engine
============================================
Matematiksel seans-bazlı sinyal ağırlıklandırma motoru.

Desteklenen Seans Sistemi (Türkiye Saati / UTC+3):
  • Asya   (Tokyo/HK/Sydney) : 03:00 – 12:00
  • Londra  (İngiliz)        : 10:00 – 19:00
  • New York (Amerikan)      : 15:00 – 00:00
  • Çakışma (Londra + NY)    : 15:00 – 19:00  ← en kritik
  • Kapalı                   : 00:00 – 03:00
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional, List, Dict
import pytz

# ── Türkiye zaman dilimi ───────────────────────────────────────────────────────
TZ_TR = pytz.timezone("Europe/Istanbul")


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Seans Tanımları
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradingSession:
    name: str           # "Asya", "Londra", "New York", "Cakisma", "Kapali"
    code: str           # "ASIA" | "LONDON" | "NY" | "OVERLAP" | "CLOSED"
    start: time         # Türkiye saati
    end: time           # Türkiye saati
    volatility_mult: float   # 1.0 = baz, >1.0 = yüksek volatilite
    rsi_weight: float        # RSI sinyalinin ağırlığı [0,1]
    macd_weight: float       # MACD sinyalinin ağırlığı [0,1]
    volume_weight: float     # Hacim sinyalinin ağırlığı [0,1]
    description: str
    currencies: List[str] = field(default_factory=list)

SESSIONS: List[TradingSession] = [
    TradingSession(
        name="Asya Seansı",
        code="ASIA",
        start=time(3, 0), end=time(12, 0),
        volatility_mult=0.65,
        rsi_weight=0.45,   # RSI biraz daha güvenilir (sakin trend)
        macd_weight=0.25,  # MACD crossover az güvenilir
        volume_weight=0.20,
        description="Tokyo, Hong Kong, Sydney — dar bant, sakin hareketler",
        currencies=["JPY", "AUD", "NZD", "CNY"],
    ),
    TradingSession(
        name="Londra Seansı",
        code="LONDON",
        start=time(10, 0), end=time(19, 0),
        volatility_mult=1.20,
        rsi_weight=0.30,
        macd_weight=0.38,  # MACD crossover güvenilir, trend oluşuyor
        volume_weight=0.28,
        description="Londra — trendler burada oluşur, yüksek hacim başlar",
        currencies=["EUR", "GBP", "USD"],
    ),
    TradingSession(
        name="New York Seansı",
        code="NY",
        start=time(15, 0), end=time(0, 0),   # 00:00 = gece yarısı
        volatility_mult=1.40,
        rsi_weight=0.25,
        macd_weight=0.38,
        volume_weight=0.32,
        description="New York — haberler gelir, sert hareketler olur",
        currencies=["USD", "NASDAQ", "SP500", "XAU"],
    ),
    TradingSession(
        name="Londra + New York Çakışması",
        code="OVERLAP",
        start=time(15, 0), end=time(19, 0),
        volatility_mult=1.80,  # EN YÜKSEK
        rsi_weight=0.22,
        macd_weight=0.38,
        volume_weight=0.35,   # Hacim en kritik bu saatlerde
        description="⚡ En volatil saat dilimi — büyük kırılımlar burada oluşur",
        currencies=["EUR", "GBP", "USD", "XAU", "NASDAQ"],
    ),
    TradingSession(
        name="Piyasa Kapalı",
        code="CLOSED",
        start=time(0, 0), end=time(3, 0),
        volatility_mult=0.30,
        rsi_weight=0.50,
        macd_weight=0.20,
        volume_weight=0.15,
        description="Tüm majör piyasalar kapalı — düşük güvenilirlik",
        currencies=[],
    ),
]


def get_current_session(dt: Optional[datetime] = None) -> TradingSession:
    """Verilen datetime'a (veya şimdiye) göre aktif seansı döndürür."""
    if dt is None:
        dt = datetime.now(TZ_TR)
    elif dt.tzinfo is None:
        dt = TZ_TR.localize(dt)
    else:
        dt = dt.astimezone(TZ_TR)

    t = dt.time()

    # Çakışma öncelikli kontrol
    if time(15, 0) <= t < time(19, 0):
        return next(s for s in SESSIONS if s.code == "OVERLAP")
    if time(10, 0) <= t < time(15, 0):
        return next(s for s in SESSIONS if s.code == "LONDON")
    if time(3, 0) <= t < time(10, 0):
        return next(s for s in SESSIONS if s.code == "ASIA")
    if time(19, 0) <= t or t < time(0, 30):
        return next(s for s in SESSIONS if s.code == "NY")
    return next(s for s in SESSIONS if s.code == "CLOSED")


def get_session_multiplier(dt: Optional[datetime] = None) -> float:
    """Aktif seans volatilite çarpanını döndürür."""
    return get_current_session(dt).volatility_mult


def minutes_to_next_session(dt: Optional[datetime] = None) -> Dict:
    """Bir sonraki önemli seans geçişine kalan dakika ve bilgisini döndürür."""
    if dt is None:
        dt = datetime.now(TZ_TR)

    t = dt.time()
    transitions = [
        (time(3,  0), "Asya Seansı başlıyor"),
        (time(10, 0), "Londra Seansı başlıyor"),
        (time(15, 0), "Çakışma başlıyor (EN KRİTİK)"),
        (time(19, 0), "New York tek başına devam ediyor"),
        (time(23,59), "Piyasa kapanıyor"),
    ]
    for target_time, label in transitions:
        target_dt = dt.replace(hour=target_time.hour, minute=target_time.minute, second=0)
        if target_dt > dt:
            diff = int((target_dt - dt).total_seconds() / 60)
            return {"minutes": diff, "label": label}
    # Yarın 03:00
    import datetime as _dt
    next_day = dt.replace(hour=3, minute=0, second=0) + _dt.timedelta(days=1)
    diff = int((next_day - dt).total_seconds() / 60)
    return {"minutes": diff, "label": "Asya Seansı başlıyor (yarın)"}


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Session-Adjusted Technical Scoring
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SessionSignal:
    """Tek bir teknik göstergenin seans-ağırlıklı sinyal puanı."""
    name: str
    raw_value: float
    signal: float      # [-1, +1] — negatif=SATIŞ, pozitif=ALIŞ
    weight: float      # seans ağırlığı
    contribution: float  # signal × weight


def compute_rsi_signal(rsi: Optional[float]) -> float:
    """
    RSI'yı [-1, +1] aralığına dönüştür.
    < 30 → güçlü ALIŞ  (+1)
    > 70 → güçlü SATIŞ (-1)
    50   → nötr          (0)

    Matematiksel: piecewise linear mapping
    """
    if rsi is None:
        return 0.0
    if rsi <= 20:
        return 1.0
    if rsi <= 30:
        return 0.5 + (30 - rsi) / 20   # 0.5 → 1.0
    if rsi <= 50:
        return (50 - rsi) / 40          # 0 → 0.5
    if rsi <= 70:
        return -(rsi - 50) / 40         # 0 → -0.5
    if rsi <= 80:
        return -0.5 - (rsi - 70) / 20  # -0.5 → -1.0
    return -1.0


def compute_macd_signal(macd: Optional[float], macd_signal: Optional[float],
                         macd_hist: Optional[float]) -> float:
    """
    MACD composite signal [-1, +1].
    1) Crossover: MACD > Signal → ALIŞ yönü
    2) Histogram momentum (değişim hızı)
    3) Zero-line pozisyonu

    Formül: 0.5×crossover + 0.3×histogram_norm + 0.2×zero_line
    """
    if macd is None or macd_signal is None:
        return 0.0

    # 1. Crossover sinyali
    diff = macd - macd_signal
    crossover = math.tanh(diff * 10)  # sigmoid-benzeri normalleştirme

    # 2. Histogram momentum
    hist_norm = math.tanh(macd_hist * 5) if macd_hist is not None else 0.0

    # 3. Zero-line pozisyonu (MACD > 0 = bullish territory)
    zero_line = math.tanh(macd * 5)

    return 0.50 * crossover + 0.30 * hist_norm + 0.20 * zero_line


def compute_volume_signal(volume_ratio: float, session: TradingSession) -> float:
    """
    Hacim-seans korelasyonu:
    - Aktif seansta yüksek hacim = onay sinyali (+)
    - Aktif seansta düşük hacim  = uyarı sinyali (-)
    - Kapalı seansta hacim önemi düşük

    volume_ratio = günlük_hacim / aylık_ortalama_hacim
    """
    # Seans beklenen hacim eşiği
    expected_ratio = {
        "CLOSED":  0.4,
        "ASIA":    0.7,
        "LONDON":  1.0,
        "NY":      1.2,
        "OVERLAP": 1.5,
    }.get(session.code, 1.0)

    rel = volume_ratio / expected_ratio if expected_ratio > 0 else 1.0

    # Kapalıda hacim sinyali neredeyse anlamsız
    if session.code == "CLOSED":
        return math.tanh((rel - 1) * 0.5) * 0.3

    # Aktif seans: yüksek hacim = pozitif onay, düşük hacim = negatif uyarı
    return math.tanh((rel - 1) * 1.5)


def compute_breakout_signal(
    rsi: Optional[float],
    macd_hist: Optional[float],
    volume_ratio: float,
    session: TradingSession,
) -> float:
    """
    Kırılım dedektörü — özellikle Londra/NY çakışmasında aktif.

    Kırılım koşulları (hepsi aynı anda = güçlü sinyal):
    1. RSI nötr bölgeden çıkıyor (40–60 arası → 60+ veya 40-)
    2. MACD histogramı ivme kazanıyor (|hist| artıyor)
    3. Hacim seans ortalamasının üzerinde

    Çarpan: seans volatilite multiplier
    """
    if session.code in ("CLOSED", "ASIA"):
        return 0.0  # Bu seanslarda kırılım sinyali geçersiz

    score = 0.0

    # RSI momentum (40-60 bölgesinden çıkış = kırılım başlangıcı)
    if rsi is not None:
        if 55 < rsi <= 70:
            score += 0.3   # bullish kırılım
        elif 30 <= rsi < 45:
            score -= 0.3   # bearish kırılım

    # MACD histogram ivmesi
    if macd_hist is not None:
        if macd_hist > 0.02:
            score += min(0.4, macd_hist * 5)
        elif macd_hist < -0.02:
            score += max(-0.4, macd_hist * 5)

    # Hacim onayı
    if volume_ratio > 1.5:
        score *= 1.3  # hacim onayı: sinyali güçlendir
    elif volume_ratio < 0.7:
        score *= 0.6  # hacim eksik: sinyali zayıflat

    # Seans volatilite çarpanı ile ölçekle
    return math.tanh(score * session.volatility_mult)


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Ana Seans Skoru
# ─────────────────────────────────────────────────────────────────────────────

def compute_session_score(
    rsi: Optional[float],
    macd: Optional[float],
    macd_signal_val: Optional[float],
    macd_hist: Optional[float],
    volume_ratio: float,
    base_score: int,          # mevcut teknik skor [0,100]
    dt: Optional[datetime] = None,
) -> Dict:
    """
    Ana fonksiyon: tüm göstergeleri seansla birleştirip
    seans-ağırlıklı birleşik skor döndürür.

    Formül:
      S_rsi      = rsi_signal  × session.rsi_weight
      S_macd     = macd_signal × session.macd_weight
      S_volume   = vol_signal  × session.volume_weight
      S_breakout = breakout    × 0.15  (sabit bonus)

      composite_raw = S_rsi + S_macd + S_volume + S_breakout
      composite_norm = (composite_raw + 1) / 2  →  [0, 1]

      session_adjusted_score = base_score × (0.6 + 0.4 × composite_norm)
                             × session.volatility_mult
    """
    session = get_current_session(dt)

    # Alt sinyaller
    rsi_sig    = compute_rsi_signal(rsi)
    macd_sig   = compute_macd_signal(macd, macd_signal_val, macd_hist)
    vol_sig    = compute_volume_signal(volume_ratio, session)
    break_sig  = compute_breakout_signal(rsi, macd_hist, volume_ratio, session)

    # Ağırlıklı toplam [-1, +1]
    composite_raw = (
        rsi_sig   * session.rsi_weight   +
        macd_sig  * session.macd_weight  +
        vol_sig   * session.volume_weight +
        break_sig * 0.15
    )

    # Normalize → [0, 1]
    composite_norm = (composite_raw + 1) / 2

    # Seans-ayarlı skor
    adjusted = base_score * (0.6 + 0.4 * composite_norm) * session.volatility_mult
    adjusted = max(0, min(100, adjusted))

    # Güven skoru: seans volatilitesi × abs(composite)
    confidence = min(1.0, session.volatility_mult * abs(composite_raw))

    # Sinyaller
    signals = _build_session_signals(session, rsi_sig, macd_sig, vol_sig,
                                     break_sig, rsi, volume_ratio)

    next_sess = minutes_to_next_session(dt)

    return {
        "session_code":           session.code,
        "session_name":           session.name,
        "session_description":    session.description,
        "session_currencies":     session.currencies,
        "volatility_multiplier":  round(session.volatility_mult, 2),
        "rsi_signal":             round(rsi_sig, 3),
        "macd_signal":            round(macd_sig, 3),
        "volume_signal":          round(vol_sig, 3),
        "breakout_signal":        round(break_sig, 3),
        "composite_raw":          round(composite_raw, 3),
        "composite_norm":         round(composite_norm, 3),
        "base_score":             base_score,
        "session_adjusted_score": round(adjusted, 1),
        "confidence":             round(confidence, 3),
        "session_signals":        signals,
        "next_session_minutes":   next_sess["minutes"],
        "next_session_label":     next_sess["label"],
    }


def _build_session_signals(
    session: TradingSession,
    rsi_sig: float, macd_sig: float, vol_sig: float, break_sig: float,
    rsi: Optional[float], volume_ratio: float,
) -> List[str]:
    msgs: List[str] = []

    # Seans genel
    msgs.append(f"{session.name}: Volatilite çarpanı ×{session.volatility_mult}")

    # RSI
    if rsi is not None:
        if rsi_sig >= 0.5:
            msgs.append(f"RSI {rsi:.0f} — aşırı satım bölgesi, alış sinyali güçlü")
        elif rsi_sig <= -0.5:
            msgs.append(f"RSI {rsi:.0f} — aşırı alım bölgesi, satış sinyali güçlü")
        elif abs(rsi_sig) < 0.15:
            msgs.append(f"RSI {rsi:.0f} — nötr bölge, net sinyal yok")

    # MACD
    if macd_sig >= 0.3:
        msgs.append("MACD yükseliş momentumu — trend doğrulanıyor")
    elif macd_sig <= -0.3:
        msgs.append("MACD düşüş momentumu — trend aşağı yönlü")

    # Hacim-seans
    if vol_sig >= 0.4:
        msgs.append(f"Hacim güçlü (×{volume_ratio:.1f}) — {session.name} onayı")
    elif vol_sig <= -0.4:
        msgs.append(f"Hacim zayıf (×{volume_ratio:.1f}) — {session.name} sırasında düşük hacim uyarısı")

    # Kırılım
    if break_sig >= 0.4:
        msgs.append("Yükseliş kırılımı sinyali — anlık fırsat penceresi açık")
    elif break_sig <= -0.4:
        msgs.append("Düşüş kırılımı sinyali — stop-loss seviyelerini gözden geçirin")

    # Çakışma uyarısı
    if session.code == "OVERLAP":
        msgs.append("⚡ Çakışma seansı: En yüksek volatilite — pozisyon boyutunu dikkatli belirleyin")

    return msgs
