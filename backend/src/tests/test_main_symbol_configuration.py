"""
Tests for main.py's BIST_SYMBOLS/CRYPTO_SYMBOLS (production audit LOW
batch: "hardcoded public-symbol assumptions"). These were plain
hardcoded module-level lists with no way to change the covered symbol
universe without a code change. `_symbols_from_env` makes them
operator-configurable via BIST_SYMBOLS/CRYPTO_SYMBOLS env vars while
preserving today's lists as the exact default (module-level constants
are resolved once at import time, so the override itself is exercised
directly against the helper function rather than by re-importing
main.py under a monkeypatched environment).
"""
import main


def test_default_bist_symbols_are_preserved_exactly():
    assert main.BIST_SYMBOLS == main._DEFAULT_BIST_SYMBOLS
    assert main._DEFAULT_BIST_SYMBOLS == [
        "THYAO.IS", "GARAN.IS", "ASELS.IS", "KCHOL.IS", "SISE.IS",
        "EREGL.IS", "BIMAS.IS", "AKBNK.IS", "YKBNK.IS", "TUPRS.IS",
        "TOASO.IS", "FROTO.IS", "SAHOL.IS", "PGSUS.IS", "TAVHL.IS",
    ]


def test_default_crypto_symbols_are_preserved_exactly():
    assert main.CRYPTO_SYMBOLS == main._DEFAULT_CRYPTO_SYMBOLS
    assert main._DEFAULT_CRYPTO_SYMBOLS == [
        "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "AVAX-USD",
        "XRP-USD", "ADA-USD", "DOT-USD", "LINK-USD", "DOGE-USD",
    ]


def test_symbols_from_env_falls_back_to_default_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_SYMBOLS_VAR", raising=False)
    default = ["AAPL", "MSFT"]
    assert main._symbols_from_env("SOME_SYMBOLS_VAR", default) == default


def test_symbols_from_env_falls_back_to_default_when_set_empty(monkeypatch):
    monkeypatch.setenv("SOME_SYMBOLS_VAR", "   ")
    default = ["AAPL", "MSFT"]
    assert main._symbols_from_env("SOME_SYMBOLS_VAR", default) == default


def test_symbols_from_env_parses_a_comma_separated_override(monkeypatch):
    monkeypatch.setenv("SOME_SYMBOLS_VAR", "aapl, msft ,nvda")
    assert main._symbols_from_env("SOME_SYMBOLS_VAR", ["DEFAULT"]) == ["AAPL", "MSFT", "NVDA"]


def test_symbols_bist_endpoint_still_returns_the_default_list(client):
    response = client.get("/symbols/bist")
    assert response.status_code == 200
    assert response.json() == main._DEFAULT_BIST_SYMBOLS


def test_symbols_crypto_endpoint_still_returns_the_default_list(client):
    response = client.get("/symbols/crypto")
    assert response.status_code == 200
    assert response.json() == main._DEFAULT_CRYPTO_SYMBOLS
