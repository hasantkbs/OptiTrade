"""OptiTrade — SEC EDGAR fundamentals backfill (free, genuinely point-in-time).

Usage (from backend/src):
  python scripts/backfill_sec_fundamentals.py

Backfills historical, point-in-time US-equity fundamental data from SEC
EDGAR's free XBRL Company Facts API into the offline Feature Store, for
core.market_config.US_SYMBOLS (28 symbols - none of this basket's prior
ML attempts had ANY fundamental feature history; those all used a
BIST+crypto-only basket). A paid data vendor search (docs/data-vendor-
research-2026-10-13.md) found no vendor offering a confirmed, clean
point-in-time solution at any price for BIST, and EODHD's free tier
blocks fundamentals entirely (confirmed: 403 "Only EOD data allowed for
free users"). For US equities specifically, SEC EDGAR *is* the actual
legal source of truth every paid vendor resells - and it's free, with
no API key.

Point-in-time correctness: every XBRL fact observation carries BOTH the
fiscal period it covers ("end") and the date it was actually FILED
("filed") - these differ by weeks to months, and a company's later
amendment (form="10-K/A") re-files a DIFFERENT value for the SAME
period under a LATER "filed" date (verified live: AAPL's FY2008 Assets
figure has three filed dates - 2009-07-22, 2009-10-27, 2010-01-25 - the
last being a 10-K/A restatement). Writing event_timestamp=filed (never
"end") for every observation, amendments included, means
FeatureExtractor's EXISTING point-in-time lookup (latest
event_timestamp <= as_of) automatically resolves to whatever was
actually public knowledge as of any given training sample's as_of -
including correctly never seeing a future amendment. This is the exact
leakage-safety property the whole ML accuracy effort has been chasing,
achieved here for free by SEC's own legally-mandated disclosure dates,
with zero ml_training package changes needed (its FeatureExtractor
auto-discovers any Feature Store feature name per symbol - see its own
docstring).

Derived (price-paired) ratios use only ANNUAL filings (form=10-K,
fp=FY) - a deliberate first-pass simplification avoiding TTM
quarter-summing; raw quarterly figures are still backfilled
individually under their own feature names, just not turned into
ratios here. Price pairing reuses the SAME historical OHLCV already
used elsewhere in this plan (yfinance), looking up the closing price on
or shortly after each 10-K's filed date - itself point-in-time
correct, since that price was equally public on that date.

SEC's fair-use policy requires a descriptive User-Agent (never a
browser-spoofing string) and recommends staying under ~10 req/sec -
both honored here (28 symbols x ~9 concepts = ~252 calls, paced well
under the limit). No API key, no cost.
"""
from __future__ import annotations

import logging
import math
import sys
import time
sys.path.insert(0, ".")

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx
import pandas as pd
import yfinance as yf

from core.market_config import US_SYMBOLS
from feature_store.models import FeatureRecord
from feature_store.offline_store import PostgresOfflineStore

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "OptiTrade ML Research research@optitrade.app"}
_REQUEST_PACE_SECONDS = 0.15  # ~6-7 req/sec, comfortably under SEC's ~10 req/sec guidance

# feature_name -> primary XBRL us-gaap concept. Values are raw dollar
# (or shares/EPS) figures as reported - never re-derived here.
RAW_CONCEPTS: Dict[str, str] = {
    "sec_total_assets": "Assets",
    "sec_total_liabilities": "Liabilities",
    "sec_stockholders_equity": "StockholdersEquity",
    "sec_revenue": "Revenues",
    "sec_net_income": "NetIncomeLoss",
    "sec_operating_income": "OperatingIncomeLoss",
    "sec_eps_diluted": "EarningsPerShareDiluted",
    "sec_shares_outstanding": "CommonStockSharesOutstanding",
    "sec_operating_cash_flow": "NetCashProvidedByUsedInOperatingActivities",
}
# Revenues was commonly replaced by this tag after ASC 606 adoption
# (~2018+) - tried only when the primary tag returns nothing.
_REVENUE_FALLBACK_CONCEPT = "RevenueFromContractWithCustomerExcludingAssessedTax"

# SEC's own ticker->CIK mapping reflects CURRENT registration, which is
# occasionally wrong for a decades-old company that went through a
# holding-company reorganization: the new shell entity inherits the
# ticker but has almost none of the original company's own filing
# history. Caught live: XOM mapped to CIK 2115436 ("ExxonMobil Holdings
# Corp", 8 observations total) instead of the real Exxon Mobil Corp
# (formerly Exxon Corp, decades of 10-Ks) at CIK 34088 - verified via
# SEC's own company search (sec.gov/cgi-bin/browse-edgar). Add further
# overrides here only when a symbol's observation count looks
# implausibly low relative to its peers, confirmed against SEC's own
# company search before overriding - never guessed.
_CIK_OVERRIDES: Dict[str, int] = {
    "XOM": 34088,
}


def _load_cik_map() -> Dict[str, int]:
    resp = httpx.get("https://www.sec.gov/files/company_tickers.json", headers=_HEADERS, timeout=20.0)
    resp.raise_for_status()
    mapping = {entry["ticker"]: entry["cik_str"] for entry in resp.json().values()}
    mapping.update(_CIK_OVERRIDES)
    return mapping


def _fetch_concept_observations(cik: int, concept: str) -> List[dict]:
    """One (cik, concept)'s full observation history, across whatever
    unit XBRL reported it in (USD, USD/shares, or shares - exactly one
    is ever populated for a given concept). Returns [] on any failure
    (missing concept for this company, network error, etc.) - never
    raises, matching this plan's established per-symbol/per-feature
    failure isolation."""
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{concept}.json"
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=20.0)
        if resp.status_code != 200:
            return []
        for unit_values in resp.json().get("units", {}).values():
            if unit_values:
                return unit_values
        return []
    except Exception as exc:
        logger.warning("concept fetch failed for CIK%s/%s: %s", cik, concept, exc)
        return []
    finally:
        time.sleep(_REQUEST_PACE_SECONDS)


def _already_have(store: PostgresOfflineStore, symbol: str, feature_name: str) -> set:
    """The set of filed-dates (UTC date) already backfilled for this
    (symbol, feature_name) - checked once per feature rather than once
    per observation, so a rerun only writes genuinely new filings."""
    very_early = datetime(1970, 1, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    try:
        history = store.get_history(symbol, feature_name, very_early, now)
    except Exception as exc:
        logger.warning("%s: could not read existing history for %s: %s", symbol, feature_name, exc)
        return set()
    return {record.event_timestamp.astimezone(timezone.utc).date() for record in history}


def _write_observations(
    store: PostgresOfflineStore, symbol: str, feature_name: str, observations: List[dict],
) -> int:
    existing = _already_have(store, symbol, feature_name)
    written = 0
    for obs in observations:
        filed = obs.get("filed")
        value = obs.get("val")
        if filed is None or value is None:
            continue
        filed_date = datetime.strptime(filed, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        if filed_date.date() in existing:
            continue
        try:
            float_value = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(float_value):
            continue
        store.insert(FeatureRecord(
            symbol=symbol, feature_name=feature_name, value=float_value, version="v1",
            event_timestamp=filed_date, ingestion_timestamp=filed_date,
        ))
        existing.add(filed_date.date())
        written += 1
    return written


def _price_on_or_after(history: pd.DataFrame, target: datetime) -> Optional[float]:
    for timestamp, row in history.iterrows():
        ts = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=timezone.utc)
        if ts >= target:
            return float(row["Close"])
    return None


def _annual_observations(observations: List[dict]) -> Dict[str, dict]:
    """Keyed by `end` (fiscal period end) -> the most-recently-filed
    10-K observation for that period, which is itself already the
    point-in-time-correct "latest known" value for that FY as of
    its own filed date (the same logic FeatureExtractor applies at
    query time, just pre-selected here for ratio computation)."""
    by_period: Dict[str, dict] = {}
    for obs in observations:
        if obs.get("form") != "10-K" or not obs.get("end") or not obs.get("filed"):
            continue
        period = obs["end"]
        if period not in by_period or obs["filed"] > by_period[period]["filed"]:
            by_period[period] = obs
    return by_period


def _write_derived_ratios(
    store: PostgresOfflineStore, symbol: str, raw: Dict[str, List[dict]], price_history: Optional[pd.DataFrame],
) -> int:
    """Price-paired ratios, FY-only (see module docstring). `raw` maps
    each RAW_CONCEPTS feature_name to its full observation list."""
    assets = _annual_observations(raw.get("sec_total_assets", []))
    liabilities = _annual_observations(raw.get("sec_total_liabilities", []))
    equity = _annual_observations(raw.get("sec_stockholders_equity", []))
    revenue = _annual_observations(raw.get("sec_revenue", []))
    net_income = _annual_observations(raw.get("sec_net_income", []))
    operating_income = _annual_observations(raw.get("sec_operating_income", []))
    eps = _annual_observations(raw.get("sec_eps_diluted", []))
    shares = _annual_observations(raw.get("sec_shares_outstanding", []))

    periods_sorted = sorted(revenue.keys())
    written = 0
    for i, period in enumerate(periods_sorted):
        rev_obs = revenue[period]
        filed_date = datetime.strptime(rev_obs["filed"], "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc,
        )
        rev_val = rev_obs["val"]
        values: Dict[str, float] = {}

        if period in liabilities and period in equity and equity[period]["val"]:
            values["sec_debt_to_equity_pct"] = liabilities[period]["val"] / equity[period]["val"] * 100
        if period in net_income and equity.get(period, {}).get("val"):
            values["sec_roe_pct"] = net_income[period]["val"] / equity[period]["val"] * 100
        if period in net_income and assets.get(period, {}).get("val"):
            values["sec_roa_pct"] = net_income[period]["val"] / assets[period]["val"] * 100
        if period in net_income and rev_val:
            values["sec_net_margin_pct"] = net_income[period]["val"] / rev_val * 100
        if period in operating_income and rev_val:
            values["sec_operating_margin_pct"] = operating_income[period]["val"] / rev_val * 100
        if i > 0:
            prior_rev = revenue[periods_sorted[i - 1]]["val"]
            if prior_rev:
                values["sec_revenue_growth_yoy_pct"] = (rev_val - prior_rev) / abs(prior_rev) * 100
        if price_history is not None and period in eps and eps[period]["val"]:
            price = _price_on_or_after(price_history, filed_date)
            if price is not None:
                values["sec_pe_ratio"] = price / eps[period]["val"]
        if price_history is not None and period in equity and period in shares and shares[period]["val"]:
            price = _price_on_or_after(price_history, filed_date)
            book_value_per_share = equity[period]["val"] / shares[period]["val"]
            if price is not None and book_value_per_share:
                values["sec_pb_ratio"] = price / book_value_per_share

        existing_by_feature = {name: _already_have(store, symbol, name) for name in values}
        for name, value in values.items():
            if not math.isfinite(value) or filed_date.date() in existing_by_feature[name]:
                continue
            store.insert(FeatureRecord(
                symbol=symbol, feature_name=name, value=float(value), version="v1",
                event_timestamp=filed_date, ingestion_timestamp=filed_date,
            ))
            written += 1
    return written


def backfill_symbol(store: PostgresOfflineStore, symbol: str, cik: int) -> int:
    raw: Dict[str, List[dict]] = {}
    written = 0
    for feature_name, concept in RAW_CONCEPTS.items():
        observations = _fetch_concept_observations(cik, concept)
        if not observations and concept == "Revenues":
            observations = _fetch_concept_observations(cik, _REVENUE_FALLBACK_CONCEPT)
        raw[feature_name] = observations
        written += _write_observations(store, symbol, feature_name, observations)

    try:
        price_history = yf.Ticker(symbol).history(period="max")
        if price_history is not None and price_history.empty:
            price_history = None
    except Exception as exc:
        logger.warning("%s: price history fetch failed, skipping derived ratios: %s", symbol, exc)
        price_history = None

    written += _write_derived_ratios(store, symbol, raw, price_history)
    return written


def main() -> None:
    print("=" * 65)
    print("OptiTrade - SEC EDGAR Fundamentals Backfill (free, point-in-time)")
    print(f"Symbols: {len(US_SYMBOLS)}")
    print("=" * 65)

    cik_map = _load_cik_map()
    store = PostgresOfflineStore()

    total_written = 0
    for symbol in US_SYMBOLS:
        cik = cik_map.get(symbol)
        if cik is None:
            print(f"  {symbol}: no CIK found, skipping")
            continue
        print(f"  {symbol} (CIK {cik})...", end=" ", flush=True)
        try:
            written = backfill_symbol(store, symbol, cik)
        except Exception as exc:
            logger.warning("%s: backfill_symbol raised %s: %s, skipping entirely", symbol, type(exc).__name__, exc)
            written = 0
        total_written += written
        print(f"{written} observations written")

    print(f"\nToplam: {total_written} gözlem yazıldı.")
    print("=" * 65)


if __name__ == "__main__":
    main()
