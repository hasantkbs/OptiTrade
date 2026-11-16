"""
OptiTrade — Canonical Instrument Identity
==========================================
Single authoritative, pure resolver from a raw symbol string (plus
optional market / quote hints) to a canonical, immutable `Instrument`.

Pure by design: standard library only, no network, filesystem,
database or environment access - safe to import anywhere.

Rules:
  - An explicit `market` hint always decides the market; legacy symbol
    notation is only used when no hint is given.
  - Legacy notation recognised without a hint: ".IS" (BIST) and
    "BASE-USD" / "BASE-USDT" (crypto), plus the explicitly known index
    symbols. A bare ticker ("AAPL") is NOT silently treated as US -
    it is UNRESOLVED until a market hint is given.
  - USD and USDT quotes are different instruments and are never
    converted into each other. A concatenated pair ("BTCUSDT") is only
    split with an explicit CRYPTO market and USDT quote hint, and a
    token ending in a quote-like code ("FDUSD", "PYUSD") is never split
    or guessed - the "BASE-QUOTE" dash notation is always unambiguous.
  - Index classification depends on the canonical (market, symbol),
    never on the input spelling, and only explicitly listed indices are
    indices - nothing is guessed to be one.
  - Known foreign exchange suffixes (".T", ".L", ".F", ".V") are
    UNSUPPORTED with or without a hint - never a US share class.
  - The legacy "TR" market code maps to canonical BIST.

`Instrument` validates its own invariants, so a directly constructed
instrument can never share an `instrument_id` with a resolver-produced
one while differing from it: asset class, quote currency and exchange
are all fully determined by (market, canonical symbol).

`provider_symbol()` maps an Instrument to a provider's ticker only
where the mapping is unambiguous, otherwise it raises
`UnsupportedProviderSymbolError`.

Used by core.market_config.resolve_legacy_symbol() (T2-B.1), the
legacy-compatibility adapter; the legacy functions in core/market_config.py
and the routing in providers/hybrid_provider.py are unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Dict, FrozenSet, Optional, Tuple, Union


# StrEnum (Python 3.11+; the project runs 3.12): str() and format() give
# the plain value ("BIST"), never "Market.BIST".
class Market(StrEnum):
    US = "US"
    BIST = "BIST"
    CRYPTO = "CRYPTO"


class AssetClass(StrEnum):
    EQUITY = "EQUITY"
    INDEX = "INDEX"
    CRYPTO = "CRYPTO"


class QuoteCurrency(StrEnum):
    TRY = "TRY"
    USD = "USD"
    USDT = "USDT"


class ResolutionMethod(StrEnum):
    MARKET_HINT = "MARKET_HINT"          # explicit market argument decided
    SYMBOL_NOTATION = "SYMBOL_NOTATION"  # legacy suffix / pair notation decided
    DIRECT = "DIRECT"                    # Instrument constructed directly


class ResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"    # ambiguous, unknown, or conflicting with a hint
    UNSUPPORTED = "UNSUPPORTED"  # recognised, but outside the supported scope
    INVALID = "INVALID"          # malformed input


class Provider(StrEnum):
    YFINANCE = "yfinance"
    BINANCE = "binance"


class UnsupportedProviderSymbolError(ValueError):
    """Raised when an Instrument has no unambiguous symbol on a provider."""


BIST_EXCHANGE = "XIST"  # ISO 10383 MIC for Borsa Istanbul
_EXCHANGES: Dict[Market, str] = {Market.BIST: BIST_EXCHANGE}

# Legacy market codes (core.market_config uses "TR") -> canonical market.
_MARKET_ALIASES: Dict[str, Market] = {"TR": Market.BIST}
_UNSUPPORTED_MARKETS = {"JP"}

_EQUITY_QUOTES = {Market.US: QuoteCurrency.USD, Market.BIST: QuoteCurrency.TRY}
_CRYPTO_QUOTES = {QuoteCurrency.USD.value, QuoteCurrency.USDT.value}
# Recognisable crypto quotes this product does not support yet.
_UNSUPPORTED_CRYPTO_QUOTES = {"EUR", "GBP", "TRY", "USDC", "BUSD", "FDUSD", "BTC", "ETH", "BNB"}
# Fiat / stablecoin codes: a bare token ending in one of these ("FDUSD",
# "BTCUSDC") is ambiguous between a base asset and a concatenated pair.
_QUOTE_LIKE_SUFFIXES = ("USDT", "USDC", "BUSD", "FDUSD", "TUSD", "USD", "EUR", "GBP", "TRY")

# Canonical (market, symbol) of every known index. Only XU100.IS and ^GSPC
# appear in core.market_config.MARKETS; XU030 (BIST 30) and XBANK (BIST
# Banks) are added explicitly. Anything else is never guessed to be an index.
_KNOWN_INDICES: FrozenSet[Tuple[Market, str]] = frozenset({
    (Market.BIST, "XU100"),
    (Market.BIST, "XU030"),
    (Market.BIST, "XBANK"),
    (Market.US, "^GSPC"),
})

# Single-letter foreign exchange suffixes that would otherwise look like a
# US dot share class ("AT.T"). Longer suffixes (".TO", ".DE") never match
# the US grammar anyway.
_FOREIGN_SUFFIXES: Dict[str, str] = {
    ".T": "JP (Tokyo)",
    ".L": "London",
    ".F": "Frankfurt",
    ".V": "TSX Venture",
}

_ALLOWED_CHARS = re.compile(r"^[A-Z0-9.\-^/]+$")
_BIST_TICKER = re.compile(r"^[A-Z][A-Z0-9]{1,5}$")
# Input form: root plus optional single-letter share class ("BRK.B", "BRK-B", "BRK/B").
_US_TICKER = re.compile(r"^([A-Z]{1,5})(?:[.\-/]([A-Z]))?$")
_US_CANONICAL = re.compile(r"^[A-Z]{1,5}(?:-[A-Z])?$")
_CRYPTO_BASE = re.compile(r"^[A-Z0-9]{2,10}$")
_CRYPTO_PAIR = re.compile(r"^([A-Z0-9]{2,10})-([A-Z]{2,5})$")
_CRYPTO_CANONICAL = re.compile(r"^[A-Z0-9]{2,10}-(USDT|USD)$")


def _expected_asset_class(market: Market, symbol: str) -> AssetClass:
    if market == Market.CRYPTO:
        return AssetClass.CRYPTO
    if (market, symbol) in _KNOWN_INDICES:
        return AssetClass.INDEX
    return AssetClass.EQUITY


def _is_canonical_symbol(market: Market, symbol: str) -> bool:
    # fullmatch: "$" with match() also accepts a trailing newline ("AAPL\n").
    if market == Market.BIST:
        return bool(_BIST_TICKER.fullmatch(symbol))
    if market == Market.US:
        return (market, symbol) in _KNOWN_INDICES or bool(_US_CANONICAL.fullmatch(symbol))
    return bool(_CRYPTO_CANONICAL.fullmatch(symbol))


def _expected_quote(market: Market, symbol: str) -> QuoteCurrency:
    if market == Market.CRYPTO:
        return QuoteCurrency(symbol.rsplit("-", 1)[1])
    return _EQUITY_QUOTES[market]


@dataclass(frozen=True)
class Instrument:
    """Canonical identity, fully determined by (market, symbol): the
    constructor rejects any asset class or quote currency that
    disagrees with them, and `exchange` is derived. `resolved_by`
    records how it was found and is excluded from equality/hashing."""

    symbol: str
    market: Market
    asset_class: AssetClass
    quote_currency: QuoteCurrency
    resolved_by: ResolutionMethod = field(default=ResolutionMethod.DIRECT, compare=False)

    def __post_init__(self) -> None:
        for name, enum_type in (
            ("market", Market), ("asset_class", AssetClass),
            ("quote_currency", QuoteCurrency), ("resolved_by", ResolutionMethod),
        ):
            if not isinstance(getattr(self, name), enum_type):
                raise TypeError(f"{name} must be a {enum_type.__name__}, got {getattr(self, name)!r}")
        if not isinstance(self.symbol, str) or not _is_canonical_symbol(self.market, self.symbol):
            raise ValueError(f"{self.symbol!r} is not a canonical {self.market} symbol")
        expected_class = _expected_asset_class(self.market, self.symbol)
        if self.asset_class != expected_class:
            raise ValueError(f"{self.market}:{self.symbol} must have asset_class {expected_class}, not {self.asset_class}")
        expected_quote = _expected_quote(self.market, self.symbol)
        if self.quote_currency != expected_quote:
            raise ValueError(f"{self.market}:{self.symbol} must have quote_currency {expected_quote}, not {self.quote_currency}")

    @property
    def instrument_id(self) -> str:
        """Deterministic, provider-independent id, e.g. "BIST:THYAO",
        "US:BRK-B", "CRYPTO:BTC-USDT"."""
        return f"{self.market}:{self.symbol}"

    @property
    def exchange(self) -> Optional[str]:
        """ISO 10383 MIC where known (BIST only today); None otherwise."""
        return _EXCHANGES.get(self.market)


@dataclass(frozen=True)
class InstrumentResolution:
    status: ResolutionStatus
    instrument: Optional[Instrument] = None
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status == ResolutionStatus.RESOLVED


def _fail(status: ResolutionStatus, reason: str) -> InstrumentResolution:
    return InstrumentResolution(status=status, reason=reason)


def resolve_instrument(
    symbol: object,
    market: Union[Market, str, None] = None,
    quote_currency: Union[QuoteCurrency, str, None] = None,
) -> InstrumentResolution:
    """Resolve `symbol` to a canonical Instrument. Never raises for bad
    input - returns a non-RESOLVED result with a reason instead."""
    if not isinstance(symbol, str) or not symbol.strip():
        return _fail(ResolutionStatus.INVALID, "symbol must be a non-empty string")
    sym = symbol.strip().upper()
    if not _ALLOWED_CHARS.match(sym):
        return _fail(ResolutionStatus.INVALID, f"symbol {sym!r} contains unsupported characters")

    market_hint, failure = _parse_market(market)
    if failure is not None:
        return failure
    quote_hint, failure = _parse_quote(quote_currency)
    if failure is not None:
        return failure

    for suffix, venue in _FOREIGN_SUFFIXES.items():
        if sym.endswith(suffix):
            return _fail(
                ResolutionStatus.UNSUPPORTED,
                f"{sym}: {venue} ({suffix}) is outside the supported markets (US, BIST, CRYPTO)",
            )

    if market_hint is None:
        return _infer_from_notation(sym, quote_hint)
    if market_hint == Market.BIST:
        return _resolve_bist(sym, quote_hint, ResolutionMethod.MARKET_HINT)
    if market_hint == Market.US:
        return _resolve_us(sym, quote_hint, ResolutionMethod.MARKET_HINT)
    return _resolve_crypto(sym, quote_hint, ResolutionMethod.MARKET_HINT)


def _parse_market(market) -> Tuple[Optional[Market], Optional[InstrumentResolution]]:
    if market is None or isinstance(market, Market):
        return market, None
    if not isinstance(market, str):
        return None, _fail(ResolutionStatus.INVALID, f"market hint {market!r} is not a string")
    code = market.strip().upper()
    if code in _MARKET_ALIASES:
        return _MARKET_ALIASES[code], None
    if code in _UNSUPPORTED_MARKETS:
        return None, _fail(ResolutionStatus.UNSUPPORTED, f"market {code} is outside the supported markets (US, BIST, CRYPTO)")
    try:
        return Market(code), None
    except ValueError:
        return None, _fail(ResolutionStatus.INVALID, f"unknown market hint {market!r}")


def _parse_quote(quote) -> Tuple[Optional[QuoteCurrency], Optional[InstrumentResolution]]:
    if quote is None or isinstance(quote, QuoteCurrency):
        return quote, None
    try:
        return QuoteCurrency(str(quote).strip().upper()), None
    except ValueError:
        return None, _fail(ResolutionStatus.INVALID, f"unknown quote currency hint {quote!r}")


def _ends_with_quote_like_code(token: str) -> bool:
    return any(token.endswith(code) and len(token) > len(code) for code in _QUOTE_LIKE_SUFFIXES)


def _infer_from_notation(sym: str, quote_hint: Optional[QuoteCurrency]) -> InstrumentResolution:
    method = ResolutionMethod.SYMBOL_NOTATION
    if sym.endswith(".IS"):
        return _resolve_bist(sym, quote_hint, method)
    pair = _CRYPTO_PAIR.match(sym)
    if pair and (pair.group(2) in _CRYPTO_QUOTES or pair.group(2) in _UNSUPPORTED_CRYPTO_QUOTES):
        return _resolve_crypto(sym, quote_hint, method)
    if sym.startswith("^"):
        return _resolve_us(sym, quote_hint, method)
    if "." in sym:
        return _fail(ResolutionStatus.UNRESOLVED, f"{sym}: unknown exchange suffix")
    if _ends_with_quote_like_code(sym):
        return _fail(
            ResolutionStatus.UNRESOLVED,
            f"{sym}: may be a concatenated crypto pair or a ticker; use BASE-QUOTE notation or pass a market hint",
        )
    return _fail(ResolutionStatus.UNRESOLVED, f"{sym}: bare ticker is ambiguous without a market hint")


def _resolve_bist(sym: str, quote_hint, method: ResolutionMethod) -> InstrumentResolution:
    base = sym[: -len(".IS")] if sym.endswith(".IS") else sym
    if not _BIST_TICKER.match(base):
        return _fail(ResolutionStatus.UNRESOLVED, f"{sym}: not a valid BIST ticker")
    return _build(base, Market.BIST, quote_hint, method)


def _resolve_us(sym: str, quote_hint, method: ResolutionMethod) -> InstrumentResolution:
    if sym.startswith("^"):
        if (Market.US, sym) not in _KNOWN_INDICES:
            return _fail(ResolutionStatus.UNRESOLVED, f"{sym}: unknown index symbol")
        return _build(sym, Market.US, quote_hint, method)
    match = _US_TICKER.match(sym)
    if not match:
        return _fail(ResolutionStatus.UNRESOLVED, f"{sym}: not a valid US ticker")
    root, share_class = match.groups()
    # Canonical US share-class separator is "-" (matches the S&P 500 cache, main.py).
    canonical = f"{root}-{share_class}" if share_class else root
    return _build(canonical, Market.US, quote_hint, method)


def _resolve_crypto(sym: str, quote_hint, method: ResolutionMethod) -> InstrumentResolution:
    pair = _CRYPTO_PAIR.match(sym)
    if pair:
        base, quote = pair.groups()
        if quote not in _CRYPTO_QUOTES:
            return _fail(ResolutionStatus.UNSUPPORTED, f"{sym}: crypto quote {quote} is not supported (USD, USDT)")
        if quote_hint is not None and quote_hint.value != quote:
            return _fail(ResolutionStatus.UNRESOLVED, f"{sym}: quote {quote} conflicts with quote hint {quote_hint}")
        return _build(f"{base}-{quote}", Market.CRYPTO, None, method)

    if quote_hint is None:
        return _fail(ResolutionStatus.UNRESOLVED, f"{sym}: crypto symbol needs a BASE-QUOTE pair or a quote_currency hint")
    if quote_hint.value not in _CRYPTO_QUOTES:
        return _fail(ResolutionStatus.UNSUPPORTED, f"{sym}: crypto quote {quote_hint} is not supported (USD, USDT)")
    base = sym
    # The only concatenated form accepted: Binance-style BASEUSDT, with the
    # USDT quote stated explicitly. A USD hint never splits anything.
    if quote_hint == QuoteCurrency.USDT and sym.endswith("USDT") and len(sym) > len("USDT"):
        base = sym[: -len("USDT")]
    if _ends_with_quote_like_code(base):
        return _fail(
            ResolutionStatus.UNRESOLVED,
            f"{sym}: ambiguous base/quote split; use BASE-QUOTE notation (e.g. {base}-{quote_hint})",
        )
    if not _CRYPTO_BASE.match(base):
        return _fail(ResolutionStatus.UNRESOLVED, f"{sym}: not a valid crypto symbol")
    return _build(f"{base}-{quote_hint}", Market.CRYPTO, None, method)


def _build(
    symbol: str,
    market: Market,
    quote_hint: Optional[QuoteCurrency],
    method: ResolutionMethod,
) -> InstrumentResolution:
    quote = _expected_quote(market, symbol)
    if quote_hint is not None and quote_hint != quote:
        return _fail(ResolutionStatus.UNRESOLVED, f"{symbol}: quote hint {quote_hint} conflicts with {market} ({quote})")
    instrument = Instrument(
        symbol=symbol, market=market, asset_class=_expected_asset_class(market, symbol),
        quote_currency=quote, resolved_by=method,
    )
    return InstrumentResolution(status=ResolutionStatus.RESOLVED, instrument=instrument)


def provider_symbol(instrument: Instrument, provider: Union[Provider, str]) -> str:
    """Provider-specific ticker for `instrument`. Raises
    UnsupportedProviderSymbolError instead of guessing - in particular
    USD and USDT pairs are never converted into each other."""
    if not isinstance(instrument, Instrument):
        raise TypeError(f"instrument must be an Instrument, got {type(instrument).__name__}")
    try:
        resolved_provider = Provider(provider.lower()) if isinstance(provider, str) else Provider(provider)
    except ValueError:
        raise UnsupportedProviderSymbolError(f"no symbol mapping for provider {provider!r}") from None

    market, quote = instrument.market, instrument.quote_currency
    if resolved_provider == Provider.YFINANCE:
        if market == Market.BIST:
            return f"{instrument.symbol}.IS"
        if market == Market.US:
            return instrument.symbol
        if quote == QuoteCurrency.USD:
            return instrument.symbol
    elif resolved_provider == Provider.BINANCE:
        if market == Market.CRYPTO and quote == QuoteCurrency.USDT:
            return instrument.symbol.replace("-", "")
    raise UnsupportedProviderSymbolError(
        f"{instrument.instrument_id} has no unambiguous {resolved_provider} symbol"
    )
