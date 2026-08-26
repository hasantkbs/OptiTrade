"""Tests for portfolio/classification.py."""
from portfolio.classification import (
    UNKNOWN_SECTOR,
    country_for_symbol,
    currency_for_symbol,
    sector_for_symbol,
)


def test_us_symbol_classification():
    assert sector_for_symbol("AAPL") == "TECH"
    assert country_for_symbol("AAPL") == "US"
    assert currency_for_symbol("AAPL") == "USD"


def test_bist_symbol_classification():
    assert sector_for_symbol("GARAN.IS") == "FINANCE"
    assert country_for_symbol("GARAN.IS") == "TR"
    assert currency_for_symbol("GARAN.IS") == "TRY"


def test_crypto_symbol_classification():
    assert country_for_symbol("BTC-USD") == "CRYPTO"
    assert currency_for_symbol("BTC-USD") == "USD"


def test_unknown_symbol_gets_the_other_sector_but_still_classified_as_us():
    assert sector_for_symbol("ZZZZNOTREAL") == UNKNOWN_SECTOR
    assert country_for_symbol("ZZZZNOTREAL") == "US"
    assert currency_for_symbol("ZZZZNOTREAL") == "USD"


def test_classification_is_case_insensitive():
    assert sector_for_symbol("aapl") == "TECH"
    assert country_for_symbol("garan.is") == "TR"
