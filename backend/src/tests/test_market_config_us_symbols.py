"""Tests for core/market_config.py's dynamic US symbol universe -
mirrors ml/chart_model.py's get_supported_symbols() tests exactly
(test_chart_model_live_allowlist.py), same file-cache-with-fallback
pattern, different payload shape (a name dict, not a tuple)."""
import json

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


def test_get_market_for_symbol_recognizes_a_symbol_only_in_the_dynamic_list(tmp_path, monkeypatch):
    """A symbol NOT in the frozen 28-symbol fallback, present only via
    the (mocked) dynamic cache file - proves get_market_for_symbol no
    longer references the old static US_SYMBOLS dict directly."""
    path = tmp_path / "sp500_symbols.json"
    path.write_text(json.dumps({"sp500_symbols": {"ABNB": "Airbnb"}}))
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))

    assert market_config.get_market_for_symbol("ABNB") == "US"


def test_get_symbols_for_market_us_returns_the_dynamic_list(tmp_path, monkeypatch):
    path = tmp_path / "sp500_symbols.json"
    path.write_text(json.dumps({"sp500_symbols": {"ABNB": "Airbnb"}}))
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))

    assert market_config.get_symbols_for_market("US") == {"ABNB": "Airbnb"}
