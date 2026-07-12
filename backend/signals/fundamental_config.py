"""
Configuration constants for the Fundamental Signal Engine.

All thresholds, max contributions, confidence values, and level scale
factors are defined here so they can be tuned without touching business
logic in signals/fundamental.py.

Naming convention:
  {METRIC}_{LEVEL}_THRESHOLD  — boundary value (inclusive on the better side)
  {METRIC}_MAX_CONTRIBUTION   — |contribution| at the extreme level
  {METRIC}_CONFIDENCE         — base reliability weight [0, 1]

Contribution scale by level (fraction of max):
  STRONG   (level 4 / 0): 1.0  × max
  MODERATE (level 3 / 1): 0.6  × max
  NEUTRAL  (level 2):     0.0
"""

# ── PE Ratio (trailing P/E) ───────────────────────────────────────────────────
# Lower P/E is bullish for value investors.
# Negative P/E (loss-making) is skipped — not comparable.
PE_STRONG_BULL_THRESHOLD =  10.0   # < 10   → STRONG BULLISH
PE_BULL_THRESHOLD        =  15.0   # 10–15  → BULLISH
PE_BEAR_THRESHOLD        =  25.0   # 15–25  → NEUTRAL; 25–35 → BEARISH
PE_STRONG_BEAR_THRESHOLD =  35.0   # > 35   → STRONG BEARISH
PE_MAX_CONTRIBUTION      =  10.0
PE_CONFIDENCE            =   0.65

# ── Forward PE trend (forward vs trailing) ───────────────────────────────────
# forward < trailing  → expected earnings growth → BULLISH
# forward > trailing  → expected earnings contraction → BEARISH
# Ratio threshold: how much smaller/larger forward must be to signal
FORWARD_PE_BULL_RATIO       = 0.90  # forward < trailing × 0.90 → BULLISH
FORWARD_PE_BEAR_RATIO       = 1.10  # forward > trailing × 1.10 → BEARISH
FORWARD_PE_MAX_CONTRIBUTION =  5.0
FORWARD_PE_CONFIDENCE       =  0.55

# ── PB Ratio (price-to-book) ──────────────────────────────────────────────────
PB_STRONG_BULL_THRESHOLD =  1.0   # < 1    → STRONG BULLISH (below book)
PB_BULL_THRESHOLD        =  2.0   # 1–2    → BULLISH
PB_BEAR_THRESHOLD        =  3.5   # 2–3.5  → NEUTRAL; 3.5–5 → BEARISH
PB_STRONG_BEAR_THRESHOLD =  5.0   # > 5    → STRONG BEARISH
PB_MAX_CONTRIBUTION      =  8.0
PB_CONFIDENCE            =  0.60

# ── Return on Equity (decimal, e.g. 0.20 = 20%) ──────────────────────────────
ROE_STRONG_BULL_THRESHOLD =  0.20  # > 20%  → STRONG BULLISH
ROE_BULL_THRESHOLD        =  0.15  # 15–20% → BULLISH
ROE_BEAR_THRESHOLD        =  0.08  # 8–15%  → NEUTRAL; 3–8% → BEARISH
ROE_STRONG_BEAR_THRESHOLD =  0.03  # < 3%   → STRONG BEARISH
ROE_MAX_CONTRIBUTION      =  8.0
ROE_CONFIDENCE            =  0.70

# ── Net Profit Margin (decimal) ───────────────────────────────────────────────
MARGIN_STRONG_BULL_THRESHOLD =  0.20  # > 20%  → STRONG BULLISH
MARGIN_BULL_THRESHOLD        =  0.10  # 10–20% → BULLISH
MARGIN_BEAR_THRESHOLD        =  0.05  # 5–10%  → NEUTRAL; 1–5% → BEARISH
MARGIN_STRONG_BEAR_THRESHOLD =  0.01  # < 1%   → STRONG BEARISH
MARGIN_MAX_CONTRIBUTION      =  8.0
MARGIN_CONFIDENCE            =  0.65

# ── Revenue Growth YoY (decimal) ─────────────────────────────────────────────
REV_STRONG_BULL_THRESHOLD =  0.20   # > 20%   → STRONG BULLISH
REV_BULL_THRESHOLD        =  0.10   # 10–20%  → BULLISH
REV_BEAR_THRESHOLD        =  0.0    # 0–10%   → NEUTRAL; -5–0% → BEARISH
REV_STRONG_BEAR_THRESHOLD = -0.05   # < -5%   → STRONG BEARISH
REV_MAX_CONTRIBUTION      = 10.0
REV_CONFIDENCE            =  0.70

# ── Earnings Growth YoY (decimal) ────────────────────────────────────────────
EPS_STRONG_BULL_THRESHOLD =  0.20
EPS_BULL_THRESHOLD        =  0.10
EPS_BEAR_THRESHOLD        =  0.0
EPS_STRONG_BEAR_THRESHOLD = -0.05
EPS_MAX_CONTRIBUTION      = 10.0
EPS_CONFIDENCE            =  0.70

# ── Debt-to-Equity ────────────────────────────────────────────────────────────
# Lower is more bullish (less financial risk).
DE_STRONG_BULL_THRESHOLD =  0.3    # < 0.3   → STRONG BULLISH
DE_BULL_THRESHOLD        =  0.8    # 0.3–0.8 → BULLISH
DE_BEAR_THRESHOLD        =  1.5    # 0.8–1.5 → NEUTRAL; 1.5–2.5 → BEARISH
DE_STRONG_BEAR_THRESHOLD =  2.5    # > 2.5   → STRONG BEARISH
DE_MAX_CONTRIBUTION      =  8.0
DE_CONFIDENCE            =  0.65

# ── Current Ratio ─────────────────────────────────────────────────────────────
CR_STRONG_BULL_THRESHOLD =  2.5    # > 2.5   → STRONG BULLISH
CR_BULL_THRESHOLD        =  1.5    # 1.5–2.5 → BULLISH
CR_BEAR_THRESHOLD        =  1.0    # 1.0–1.5 → NEUTRAL; 0.7–1.0 → BEARISH
CR_STRONG_BEAR_THRESHOLD =  0.7    # < 0.7   → STRONG BEARISH
CR_MAX_CONTRIBUTION      =  6.0
CR_CONFIDENCE            =  0.65

# ── Dividend Yield (decimal) ──────────────────────────────────────────────────
# Only generates BULLISH signals (no dividend is not bearish, just neutral).
DIV_STRONG_BULL_THRESHOLD =  0.05  # > 5%   → STRONG BULLISH
DIV_BULL_THRESHOLD        =  0.02  # 2–5%   → BULLISH
DIV_WEAK_THRESHOLD        =  0.005 # 0.5–2% → NEUTRAL (skipped — not signal-worthy)
DIV_MAX_CONTRIBUTION      =  5.0
DIV_CONFIDENCE            =  0.55

# ── Contribution scale factors ────────────────────────────────────────────────
SCALE_STRONG   = 1.0
SCALE_MODERATE = 0.6

# ── Normalized value by level ─────────────────────────────────────────────────
# Maps discrete direction level to [0, 1].
# 0 = max bearish, 0.5 = neutral, 1.0 = max bullish.
NORM_STRONG_BULLISH = 0.90
NORM_BULLISH        = 0.70
NORM_NEUTRAL        = 0.50
NORM_BEARISH        = 0.30
NORM_STRONG_BEARISH = 0.10
