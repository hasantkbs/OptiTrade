"""Tests for the legacy -> canonical instrument adapter in
core/market_config.py (T2-B.1, provenance added in T2-B.1.1):
`resolve_legacy_symbol()`, `LegacyResolution`, `MarketProvenance` and
`LEGACY_MARKET_CODES`.

The adapter resolves a symbol through core.instruments so that a
resolved instrument always agrees with the LEGACY market classification
unless the caller passes a market explicitly, and it records where the
market came from:
  - EXPLICIT_HINT:   the caller passed `market`;
  - SYMBOL_DERIVED:  the symbol's own notation, no hint at all;
  - LEGACY_INFERRED: get_market_for_symbol(), including its bare-ticker
                     -> US default (core.instruments itself still leaves
                     bare tickers UNRESOLVED).
Where the legacy classification has no valid canonical identity (e.g.
"BTC-USDT", which legacy calls US) the result is not RESOLVED.

The legacy functions themselves are unchanged and stay pinned by
tests/test_legacy_market_config_characterization.py.

Pure: no file, network, database or environment access."""
import dataclasses

import pytest

import core.market_config as market_config
from core.instruments import (
    AssetClass,
    InstrumentResolution,
    Market,
    QuoteCurrency,
    ResolutionMethod,
    ResolutionStatus,
    resolve_instrument,
)
from core.market_config import LEGACY_MARKET_CODES, LegacyResolution, MarketProvenance, resolve_legacy_symbol

EXPLICIT = MarketProvenance.EXPLICIT_HINT
SYMBOL = MarketProvenance.SYMBOL_DERIVED
LEGACY = MarketProvenance.LEGACY_INFERRED


def _resolved(symbol, **kwargs):
    result = resolve_legacy_symbol(symbol, **kwargs)
    assert result.status == ResolutionStatus.RESOLVED, result.reason
    return result.instrument


# ── Market code mapping ─────────────────────────────────────────────────────

def test_legacy_market_codes_cover_every_canonical_market():
    assert LEGACY_MARKET_CODES == {Market.BIST: "TR", Market.US: "US", Market.CRYPTO: "CRYPTO"}


def test_every_legacy_market_code_is_a_configured_market():
    # MARKETS also has "JP", which has no canonical market (UNSUPPORTED).
    assert set(LEGACY_MARKET_CODES.values()) <= set(market_config.MARKETS)
    assert "JP" not in LEGACY_MARKET_CODES.values()


# ── Result type ─────────────────────────────────────────────────────────────

def test_result_exposes_the_underlying_resolution_unchanged():
    result = resolve_legacy_symbol("THYAO.IS")

    assert isinstance(result, LegacyResolution)
    assert isinstance(result.resolution, InstrumentResolution)
    assert (result.status, result.instrument, result.reason, result.ok) == (
        result.resolution.status, result.resolution.instrument, result.resolution.reason, result.resolution.ok,
    )


def test_result_is_immutable():
    result = resolve_legacy_symbol("THYAO.IS")

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.provenance = EXPLICIT


def test_provenance_values_are_plain_strings():
    assert [str(p) for p in MarketProvenance] == ["EXPLICIT_HINT", "SYMBOL_DERIVED", "LEGACY_INFERRED"]


# ── Provenance ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("symbol, market, status, instrument_id, provenance", [
    # The symbol's own notation decides, and agrees with legacy.
    ("THYAO.IS", None, ResolutionStatus.RESOLVED, "BIST:THYAO", SYMBOL),
    ("XU100.IS", None, ResolutionStatus.RESOLVED, "BIST:XU100", SYMBOL),
    ("BTC-USD", None, ResolutionStatus.RESOLVED, "CRYPTO:BTC-USD", SYMBOL),
    ("^GSPC", None, ResolutionStatus.RESOLVED, "US:^GSPC", SYMBOL),
    # Bare tickers: only the legacy US default gives them a market.
    ("GARAN", None, ResolutionStatus.RESOLVED, "US:GARAN", LEGACY),
    ("AAPL", None, ResolutionStatus.RESOLVED, "US:AAPL", LEGACY),
    ("BRK.B", None, ResolutionStatus.RESOLVED, "US:BRK-B", LEGACY),
    # The symbol alone says CRYPTO / BIST, legacy says US: the legacy
    # market is tried, and fails - never resolved as CRYPTO / BIST.
    ("BTC-USDT", None, ResolutionStatus.UNRESOLVED, None, LEGACY),
    ("THYAO.IS ", None, ResolutionStatus.UNRESOLVED, None, LEGACY),
    # Foreign suffix: unsupported under the legacy market too.
    ("THYAO.T", None, ResolutionStatus.UNSUPPORTED, None, LEGACY),
    # Unsupported crypto quote alone; legacy says US -> not a US ticker.
    ("BTC-EUR", None, ResolutionStatus.UNRESOLVED, None, LEGACY),
    # Malformed symbol: decided by the symbol alone, no market involved.
    ("AAPL; DROP", None, ResolutionStatus.INVALID, None, SYMBOL),
    (None, None, ResolutionStatus.INVALID, None, SYMBOL),
    # Explicit hints, including ones that contradict legacy or fail.
    ("GARAN", "US", ResolutionStatus.RESOLVED, "US:GARAN", EXPLICIT),
    ("GARAN", "TR", ResolutionStatus.RESOLVED, "BIST:GARAN", EXPLICIT),
    ("THYAO.IS", "US", ResolutionStatus.UNRESOLVED, None, EXPLICIT),
    ("THYAO.IS", "TR", ResolutionStatus.RESOLVED, "BIST:THYAO", EXPLICIT),
])
def test_status_instrument_and_provenance(symbol, market, status, instrument_id, provenance):
    result = resolve_legacy_symbol(symbol, market=market)

    assert result.status == status, result.reason
    assert (result.instrument.instrument_id if result.instrument else None) == instrument_id
    assert result.provenance == provenance
    assert result.ok or result.reason


def test_legacy_inference_and_explicit_hint_differ_only_in_provenance():
    inferred = resolve_legacy_symbol("GARAN")
    explicit = resolve_legacy_symbol("GARAN", "US")

    assert inferred.instrument == explicit.instrument
    assert inferred.provenance == LEGACY
    assert explicit.provenance == EXPLICIT


def test_symbol_derived_result_keeps_the_resolvers_own_method():
    # The resolver's notation-based result is returned as-is, not
    # re-resolved under a hint.
    assert resolve_legacy_symbol("THYAO.IS").instrument.resolved_by == ResolutionMethod.SYMBOL_NOTATION
    assert resolve_legacy_symbol("GARAN").instrument.resolved_by == ResolutionMethod.MARKET_HINT


# ── No market: agreement with the legacy classification ─────────────────────

@pytest.mark.parametrize("symbol, instrument_id, asset_class, quote", [
    ("THYAO.IS", "BIST:THYAO", AssetClass.EQUITY, QuoteCurrency.TRY),
    ("thyao.is", "BIST:THYAO", AssetClass.EQUITY, QuoteCurrency.TRY),
    ("XU100.IS", "BIST:XU100", AssetClass.INDEX, QuoteCurrency.TRY),
    # Not an explicitly known index: never guessed to be one.
    ("XU050.IS", "BIST:XU050", AssetClass.EQUITY, QuoteCurrency.TRY),
    ("BTC-USD", "CRYPTO:BTC-USD", AssetClass.CRYPTO, QuoteCurrency.USD),
    ("btc-usd", "CRYPTO:BTC-USD", AssetClass.CRYPTO, QuoteCurrency.USD),
    ("ETH-USD", "CRYPTO:ETH-USD", AssetClass.CRYPTO, QuoteCurrency.USD),
    ("AAPL", "US:AAPL", AssetClass.EQUITY, QuoteCurrency.USD),
    ("MSFT", "US:MSFT", AssetClass.EQUITY, QuoteCurrency.USD),
    ("BRK-B", "US:BRK-B", AssetClass.EQUITY, QuoteCurrency.USD),
    ("BRK.B", "US:BRK-B", AssetClass.EQUITY, QuoteCurrency.USD),
    ("^GSPC", "US:^GSPC", AssetClass.INDEX, QuoteCurrency.USD),
])
def test_resolves_to_the_canonical_instrument_for_the_legacy_market(symbol, instrument_id, asset_class, quote):
    instrument = _resolved(symbol)

    assert instrument.instrument_id == instrument_id
    assert instrument.asset_class == asset_class
    assert instrument.quote_currency == quote
    assert LEGACY_MARKET_CODES[instrument.market] == market_config.get_market_for_symbol(symbol)


@pytest.mark.parametrize("symbol, status", [
    # Legacy calls these US, but they are not valid US tickers: refused,
    # never re-interpreted as crypto and never given a US identity.
    ("BTC-USDT", ResolutionStatus.UNRESOLVED),
    ("ETH-USDT", ResolutionStatus.UNRESOLVED),
    ("BTCUSDT", ResolutionStatus.UNRESOLVED),
    ("ZZZZNOTREAL", ResolutionStatus.UNRESOLVED),
    # Legacy calls this US because it ends in neither ".IS" nor "-USD".
    ("THYAO.IS ", ResolutionStatus.UNRESOLVED),
    # Foreign suffixes are never treated as US tickers.
    ("THYAO.T", ResolutionStatus.UNSUPPORTED),
    ("7203.T", ResolutionStatus.UNSUPPORTED),
    ("VOD.L", ResolutionStatus.UNSUPPORTED),
    # Legacy calls these TR / CRYPTO by suffix, but they are malformed.
    ("X.IS", ResolutionStatus.UNRESOLVED),
    ("A-USD", ResolutionStatus.UNRESOLVED),
])
def test_legacy_classification_without_a_valid_identity_is_not_resolved(symbol, status):
    result = resolve_legacy_symbol(symbol)

    assert result.status == status
    assert result.instrument is None
    assert result.reason


def test_bare_ticker_gets_the_legacy_us_default_explicitly():
    # Legacy classifies a bare BIST ticker as US; the adapter applies that
    # default as a market hint and reports it as a legacy inference.
    result = resolve_legacy_symbol("GARAN")

    assert result.instrument.instrument_id == "US:GARAN"
    assert result.instrument.resolved_by == ResolutionMethod.MARKET_HINT
    assert result.provenance == LEGACY


# ── Explicit market ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("symbol, market, instrument_id", [
    ("GARAN", "TR", "BIST:GARAN"),
    ("GARAN.IS", "TR", "BIST:GARAN"),
    ("GARAN", "tr", "BIST:GARAN"),
    ("AAPL", "US", "US:AAPL"),
    ("AAPL", " us ", "US:AAPL"),
    ("AAPL", Market.US, "US:AAPL"),
    ("ETH-USD", "CRYPTO", "CRYPTO:ETH-USD"),
    # Explicit CRYPTO resolves the USDT pair legacy calls US.
    ("BTC-USDT", "CRYPTO", "CRYPTO:BTC-USDT"),
])
def test_explicit_market_decides_the_market(symbol, market, instrument_id):
    result = resolve_legacy_symbol(symbol, market=market)

    assert result.status == ResolutionStatus.RESOLVED, result.reason
    assert result.instrument.instrument_id == instrument_id
    assert result.provenance == EXPLICIT


@pytest.mark.parametrize("symbol, market, status", [
    ("THYAO.IS", "US", ResolutionStatus.UNRESOLVED),
    ("BTC-USD", "TR", ResolutionStatus.UNRESOLVED),
    # A bare crypto base needs a quote, which the adapter never guesses.
    ("BTC", "CRYPTO", ResolutionStatus.UNRESOLVED),
    ("7203", "JP", ResolutionStatus.UNSUPPORTED),
    ("AAPL", "MARS", ResolutionStatus.INVALID),
    # An empty market is an (invalid) explicit hint, not "no market".
    ("AAPL", "", ResolutionStatus.INVALID),
    ("AAPL", 123, ResolutionStatus.INVALID),
])
def test_explicit_market_that_does_not_fit_is_not_resolved(symbol, market, status):
    result = resolve_legacy_symbol(symbol, market=market)

    assert result.status == status
    assert result.instrument is None
    assert result.provenance == EXPLICIT


@pytest.mark.parametrize("symbol", [None, 123, "", "   "])
def test_invalid_symbol_is_invalid_not_an_exception(symbol):
    # get_market_for_symbol(None) would raise; the adapter never does.
    result = resolve_legacy_symbol(symbol)

    assert result.status == ResolutionStatus.INVALID
    assert result.provenance == SYMBOL


# ── Sweeps ──────────────────────────────────────────────────────────────────

_SWEEP_SYMBOLS = [
    "AAPL", "MSFT", "GARAN", "ZZZZ", "ZZZZNOTREAL", "BRK-B", "BRK.B", "BRK/B", "^GSPC", "^N225",
    "THYAO.IS", "thyao.is", "THYAO.IS ", " THYAO.IS", "XU100.IS", "XU050.IS", "X.IS", "TOOLONGNAME.IS",
    "BTC-USD", "btc-usd", "ETH-USD", "USDT-USD", "BTC-USDT", "ETH-USDT", "BTCUSDT", "BTC-EUR", "BTC-TRY",
    "A-USD", "1INCH-USD", "THYAO.T", "7203.T", "VOD.L", "ABC.XYZ", "-", "^", ".IS", "AAPL; DROP", "A" * 64,
]


def test_no_market_status_and_instrument_match_the_legacy_hinted_resolution():
    # Compatibility with T2-B.1: without a market, status and instrument
    # are exactly those of resolving under the legacy market code.
    mismatches = []
    for symbol in _SWEEP_SYMBOLS:
        result = resolve_legacy_symbol(symbol)
        legacy = resolve_instrument(symbol, market=market_config.get_market_for_symbol(symbol))
        if (result.status, result.instrument) != (legacy.status, legacy.instrument):
            mismatches.append((symbol, result.status, legacy.status))

    assert mismatches == []


def test_no_market_provenance_is_consistent_with_the_instrument():
    for symbol in _SWEEP_SYMBOLS:
        result = resolve_legacy_symbol(symbol)
        assert result.provenance in (SYMBOL, LEGACY), symbol
        if result.ok:
            expected = ResolutionMethod.SYMBOL_NOTATION if result.provenance == SYMBOL else ResolutionMethod.MARKET_HINT
            assert result.instrument.resolved_by == expected, symbol
            assert LEGACY_MARKET_CODES[result.instrument.market] == market_config.get_market_for_symbol(symbol)


def test_resolve_legacy_symbol_never_raises():
    symbols = _SWEEP_SYMBOLS + [None, 7, 1.5, b"AAPL", "", "   ", "AAPL\n", "ışctr"]
    markets = [None, "TR", "tr", " us ", "US", "CRYPTO", "JP", "MARS", "", 123, Market.BIST, Market.CRYPTO]
    raised = []
    for symbol in symbols:
        for market in markets:
            try:
                result = resolve_legacy_symbol(symbol, market=market)
            except Exception as exc:
                raised.append((symbol, market, type(exc).__name__))
                continue
            assert isinstance(result, LegacyResolution)
            assert isinstance(result.status, ResolutionStatus)
            assert (result.instrument is not None) == result.ok, (symbol, market)
            assert result.ok or result.reason, (symbol, market)
            assert (result.provenance == EXPLICIT) == (market is not None), (symbol, market)

    assert raised == []


def test_every_curated_symbol_resolves_in_its_legacy_market():
    curated = sorted(
        set(market_config.BIST_SYMBOLS)
        | set(market_config.CRYPTO_SYMBOLS)
        | set(market_config._SP500_SYMBOLS_SNAPSHOT_2026_11_01)
        | {s for m in ("TR", "US", "CRYPTO") for s in market_config.get_default_watchlist(m)}
        | {market_config.MARKETS[m]["index_symbol"] for m in ("TR", "US", "CRYPTO")}
    )
    failures = []
    for symbol in curated:
        result = resolve_legacy_symbol(symbol)
        legacy = market_config.get_market_for_symbol(symbol)
        if not result.ok or LEGACY_MARKET_CODES[result.instrument.market] != legacy:
            failures.append((symbol, legacy, result.status, result.reason))

    assert failures == []
