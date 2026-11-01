import json

import core.market_config as market_config
from news.entity_extraction import DeterministicEntityExtractor


def test_extract_recognizes_a_ticker_only_in_the_dynamic_us_list(tmp_path, monkeypatch):
    """ABNB is not in the frozen 28-symbol fallback - only visible via
    get_us_symbols()'s (mocked) cache file. Proves entity extraction
    rebuilds its gazetteer per call instead of freezing it at module-
    import time."""
    path = tmp_path / "sp500_symbols.json"
    path.write_text(json.dumps({"sp500_symbols": {"ABNB": "Airbnb"}}))
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))

    entities = DeterministicEntityExtractor().extract("ABNB shares rose today.")

    assert any(e.symbol == "ABNB" for e in entities)
