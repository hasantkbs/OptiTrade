
OPTIMIZABLE_PARAMETERS = {
    "PriceTrendModel": {
        "rsi_window": range(10, 20, 2),
        "macd_fast_window": range(10, 20, 2),
        "macd_slow_window": range(20, 30, 2),
        "macd_signal_window": range(5, 15, 2),
    },
    "VolumeSurgeModel": {
        "volume_ma_window": range(10, 30, 5),
    },
    # Add other models and their optimizable parameters here
}
