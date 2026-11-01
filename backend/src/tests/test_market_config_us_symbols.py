"""Tests for core/market_config.py's dynamic US symbol universe -
mirrors ml/chart_model.py's get_supported_symbols() tests exactly
(test_chart_model_live_allowlist.py), same file-cache-with-fallback
pattern, different payload shape (a name dict, not a tuple)."""
import json
import logging

import core.market_config as market_config


def test_get_us_symbols_reads_from_the_json_file_when_present(tmp_path, monkeypatch):
    path = tmp_path / "sp500_symbols.json"
    path.write_text(json.dumps({"sp500_symbols": {"AAPL": "Apple", "MSFT": "Microsoft"}}))
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))

    assert market_config.get_us_symbols() == {"AAPL": "Apple", "MSFT": "Microsoft"}


def test_get_us_symbols_falls_back_to_the_snapshot_when_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(tmp_path / "does-not-exist.json"))

    assert market_config.get_us_symbols() == dict(market_config._SP500_SYMBOLS_SNAPSHOT_2026_11_01)


def test_get_us_symbols_falls_back_to_the_snapshot_on_corrupt_json(tmp_path, monkeypatch):
    path = tmp_path / "sp500_symbols.json"
    path.write_text("{not valid json")
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))

    assert market_config.get_us_symbols() == dict(market_config._SP500_SYMBOLS_SNAPSHOT_2026_11_01)


def test_get_us_symbols_picks_up_a_change_without_reimporting_the_module(tmp_path, monkeypatch):
    path = tmp_path / "sp500_symbols.json"
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))

    path.write_text(json.dumps({"sp500_symbols": {"AAPL": "Apple"}}))
    assert market_config.get_us_symbols() == {"AAPL": "Apple"}

    path.write_text(json.dumps({"sp500_symbols": {"AAPL": "Apple", "MSFT": "Microsoft"}}))
    assert market_config.get_us_symbols() == {"AAPL": "Apple", "MSFT": "Microsoft"}


def test_get_market_for_symbol_falls_through_to_us_for_any_non_tr_non_crypto_symbol():
    """Final-review fix: get_market_for_symbol's own US branch never
    actually needed get_us_symbols() - a hit returned "US" and the
    very next line (a miss) also returned "US", so the membership
    check was dead weight (now removed; see market_config.py's own
    comment there). This replaces the Task 1 test that exercised that
    now-removed branch, which asserted nothing a non-US symbol
    wouldn't also satisfy."""
    assert market_config.get_market_for_symbol("ZZZZNOTREAL") == "US"


def test_get_symbols_for_market_us_returns_the_dynamic_list(tmp_path, monkeypatch):
    path = tmp_path / "sp500_symbols.json"
    path.write_text(json.dumps({"sp500_symbols": {"ABNB": "Airbnb"}}))
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))

    assert market_config.get_symbols_for_market("US") == {"ABNB": "Airbnb"}


def test_get_us_symbols_logs_the_fallback_warning_only_once_per_failure_streak(tmp_path, monkeypatch, caplog):
    """Final-review fix: get_us_symbols() is called per news article
    (news/entity_extraction.py, core/news_analyzer.py) and per market-
    for-symbol lookup - while the cache file is missing/corrupt, the
    old code logged an identical WARNING on every single one of those
    calls, which at S&P-500 scan scale means thousands of repeated
    lines per cycle. Logs once, then stays quiet until a successful
    read resets it."""
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(tmp_path / "does-not-exist.json"))
    monkeypatch.setattr(market_config, "_us_symbols_fallback_warned", False)

    with caplog.at_level(logging.WARNING, logger="core.market_config"):
        market_config.get_us_symbols()
        market_config.get_us_symbols()
        market_config.get_us_symbols()

    assert len(caplog.records) == 1


def test_get_us_symbols_warns_again_after_a_successful_read_then_another_failure(tmp_path, monkeypatch, caplog):
    path = tmp_path / "sp500_symbols.json"
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))
    monkeypatch.setattr(market_config, "_us_symbols_fallback_warned", False)

    with caplog.at_level(logging.WARNING, logger="core.market_config"):
        market_config.get_us_symbols()  # missing file - warns, sets the flag
        path.write_text(json.dumps({"sp500_symbols": {"AAPL": "Apple"}}))
        market_config.get_us_symbols()  # success - clears the flag
        path.unlink()
        market_config.get_us_symbols()  # missing again - must warn again

    assert len(caplog.records) == 2
