import json

import core.market_config as market_config
from core.news_analyzer import _query_for_symbol


def test_query_for_symbol_resolves_a_name_only_in_the_dynamic_us_list(tmp_path, monkeypatch):
    path = tmp_path / "sp500_symbols.json"
    path.write_text(json.dumps({"sp500_symbols": {"ABNB": "Airbnb"}}))
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))

    assert _query_for_symbol("ABNB", "US") == "Airbnb"
