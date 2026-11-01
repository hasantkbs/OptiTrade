"""These 7 research scripts already ran against the original 28-symbol
US_SYMBOLS universe before it became dynamic (core/market_config.py's
get_us_symbols()) - they must keep using that exact original universe
so a future re-run stays reproducible, not silently widen to the new
~500-symbol S&P 500 list."""
from scripts._frozen_us_symbols import ORIGINAL_US_SYMBOLS_28


def test_frozen_us_symbols_has_exactly_the_original_28():
    assert len(ORIGINAL_US_SYMBOLS_28) == 28
    assert ORIGINAL_US_SYMBOLS_28["AAPL"] == "Apple"
    assert ORIGINAL_US_SYMBOLS_28["GE"] == "GE Aerospace"


def test_backfill_sec_fundamentals_imports_the_frozen_list():
    import scripts.backfill_sec_fundamentals as mod
    assert mod.US_SYMBOLS is ORIGINAL_US_SYMBOLS_28


def test_backfill_feature_store_imports_the_frozen_list():
    import scripts.backfill_feature_store as mod
    assert mod.US_SYMBOLS is ORIGINAL_US_SYMBOLS_28


def test_backfill_news_features_imports_the_frozen_list():
    import scripts.backfill_news_features as mod
    assert mod.US_SYMBOLS is ORIGINAL_US_SYMBOLS_28


def test_train_ml_candidate_us_news_imports_the_frozen_list():
    import scripts.train_ml_candidate_us_news as mod
    assert mod.US_SYMBOLS is ORIGINAL_US_SYMBOLS_28


def test_train_ml_candidate_us_news_window2_imports_the_frozen_list():
    import scripts.train_ml_candidate_us_news_window2 as mod
    assert mod.US_SYMBOLS is ORIGINAL_US_SYMBOLS_28


def test_train_ml_candidate_us_news_control_imports_the_frozen_list():
    import scripts.train_ml_candidate_us_news_control as mod
    assert mod.US_SYMBOLS is ORIGINAL_US_SYMBOLS_28


def test_train_ml_candidate_us_fundamentals_imports_the_frozen_list():
    import scripts.train_ml_candidate_us_fundamentals as mod
    assert mod.US_SYMBOLS is ORIGINAL_US_SYMBOLS_28
