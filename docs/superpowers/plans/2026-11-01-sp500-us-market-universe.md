# S&P 500 US Market Universe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** replace the hardcoded, 28-symbol `US_SYMBOLS` universe with a dynamically-sourced real S&P 500 constituent list, propagated to every live consumer, while keeping research scripts reproducible and the Market page's opportunities scanner from being overwhelmed.

**Architecture:** `core/market_config.py` gains `get_us_symbols()`, mirroring `ml.chart_model.get_supported_symbols()`'s exact "read a local JSON cache fresh every call, fall back to a frozen snapshot" pattern. A new daily background loop in `main.py` refreshes that cache from Wikipedia's S&P 500 table. Every live consumer switches from the static `US_SYMBOLS` dict to calling `get_us_symbols()`; research scripts pin to a new frozen copy of the original 28 symbols instead. The Market page's opportunities scanner gains a tick-gate (US refreshes every 6th tick instead of every tick) and a higher-concurrency scanner config, specifically for the now much larger US universe.

**Tech Stack:** Python, pandas + lxml (already a dependency, used here for `pandas.read_html` against Wikipedia), pytest with real file I/O (project convention: no mocking framework).

**Spec:** `docs/superpowers/specs/2026-11-01-sp500-us-market-universe-design.md`

## Global Constraints

- `get_us_symbols()` reads `model_artifacts/sp500_symbols.json` fresh on every call (no network call on the request path) and falls back to a frozen snapshot on missing/corrupt/empty file - exact pattern already proven by `ml.chart_model.get_supported_symbols()`.
- The Wikipedia fetch happens only in the new daily `sp500_refresh_loop`, never inline in a request path.
- A failed Wikipedia fetch/parse leaves the existing cache file untouched - never deletes or truncates good data.
- Research scripts under `scripts/` must keep using the exact original 28-symbol dict, never the dynamic list - re-running one today must reproduce its original universe.
- Chart-AI's own `get_supported_symbols()` allowlist is untouched by this work - a new US symbol with no trained chart-AI model renders `chart_ai: None`, the existing tested behavior.
- `get_default_watchlist("US")` (the small hardcoded 10-symbol starter list) is untouched.
- TR and CRYPTO's opportunities-scan cadence (every 300s tick) and scanner concurrency (`max_parallel_symbols=3`) are untouched - only US's cadence and concurrency change.

## Review Focus

- A ticker Wikipedia lists with dot notation for dual-class shares (e.g. `BRK.B`) must be normalized to yfinance's hyphen convention (`BRK-B`) before being cached - an unnormalized ticker would silently be unfetchable everywhere downstream.
- `get_us_symbols()` must still return a usable (if stale) universe on a completely fresh deployment with no `sp500_symbols.json` written yet - the frozen fallback snapshot covers this, not an empty dict.
- `news/entity_extraction.py`'s gazetteer must reflect a symbol added only to the new dynamic list, not just the original 28 - it currently builds its lookup table once at module-import time, which this plan must change.
- The US tick-gate must not delay TR/CRYPTO's own refresh - both must still fire every 300s tick exactly as today, confirmed by not breaking the three existing `market_opportunities_refresh_loop` tests in `test_main_background_scan_loops.py`.
- Re-running any of the 7 pinned research scripts today must produce the identical original 28-symbol universe, not the new ~500 - a regression test per script, not just a one-time manual check.

---

### Task 1: `get_us_symbols()` in `core/market_config.py`

**Files:**
- Modify: `backend/src/core/market_config.py:13-14` (imports), `:115-150` (remove `US_SYMBOLS` dict, add the function + fallback snapshot in its place), `:327-347` (`get_market_for_symbol`, `get_symbols_for_market`)
- Test: `backend/src/tests/test_market_config_us_symbols.py` (new)

**Interfaces:**
- Produces: `core.market_config.get_us_symbols() -> Dict[str, str]`, `core.market_config.SP500_SYMBOLS_PATH: str`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/src/tests/test_market_config_us_symbols.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/src && pytest tests/test_market_config_us_symbols.py -v`
Expected: FAIL with `AttributeError: module 'core.market_config' has no attribute 'SP500_SYMBOLS_PATH'` (or `get_us_symbols`).

- [ ] **Step 3: Add `get_us_symbols()` and update the two call sites**

In `backend/src/core/market_config.py:13-14`, change:

```python
from __future__ import annotations
from typing import Dict, List, Optional
```

to:

```python
from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
```

Replace the `US_SYMBOLS = { ... }` dict (lines 115-150) with:

```python
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_MODEL_ARTIFACTS_DIR = os.path.join(_BACKEND_DIR, "model_artifacts")
SP500_SYMBOLS_PATH = os.path.join(_MODEL_ARTIFACTS_DIR, "sp500_symbols.json")

# Day-one fallback - the exact 28 symbols the old hardcoded US_SYMBOLS
# dict held, captured so a fresh deployment (no sp500_symbols.json yet)
# still serves a real, if small, US universe instead of an empty one.
_SP500_SYMBOLS_SNAPSHOT_2026_11_01: Dict[str, str] = {
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "NVDA":  "NVIDIA",
    "GOOGL": "Alphabet",
    "META":  "Meta",
    "AMZN":  "Amazon",
    "TSLA":  "Tesla",
    "AMD":   "AMD",
    "INTC":  "Intel",
    "CRM":   "Salesforce",
    "JPM":   "JPMorgan",
    "BAC":   "Bank of America",
    "GS":    "Goldman Sachs",
    "MS":    "Morgan Stanley",
    "V":     "Visa",
    "MA":    "Mastercard",
    "JNJ":   "Johnson & Johnson",
    "LLY":   "Eli Lilly",
    "PFE":   "Pfizer",
    "UNH":   "UnitedHealth",
    "XOM":   "ExxonMobil",
    "CVX":   "Chevron",
    "WMT":   "Walmart",
    "HD":    "Home Depot",
    "MCD":   "McDonald's",
    "CAT":   "Caterpillar",
    "BA":    "Boeing",
    "GE":    "GE Aerospace",
}


def get_us_symbols() -> Dict[str, str]:
    """Canlı entegrasyonun kullandığı GERÇEK US sembol evreni (S&P 500).
    `sp500_refresh_loop` (main.py) günde bir SP500_SYMBOLS_PATH'teki
    JSON'u günceller - bu fonksiyon dosyayı HER ÇAĞRIDA yeniden okuyor
    (sunucu yeniden başlatılmadan güncellensin diye), dosya yoksa/
    okunamazsa sabit anlık görüntüye düşer."""
    try:
        with open(SP500_SYMBOLS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return dict(data["sp500_symbols"])
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        logger.warning(f"{SP500_SYMBOLS_PATH} okunamadı ({exc}), sabit anlık görüntüye dönülüyor.")
        return dict(_SP500_SYMBOLS_SNAPSHOT_2026_11_01)
```

Then, in `get_market_for_symbol` and `get_symbols_for_market` (around line 327-347), change:

```python
def get_market_for_symbol(symbol: str) -> str:
    """Sembole bakarak piyasayı tespit et."""
    sym = symbol.upper()
    if sym.endswith(".IS"):
        return "TR"
    if sym.endswith("-USD") or sym in CRYPTO_SYMBOLS:
        return "CRYPTO"
    if sym in US_SYMBOLS:
        return "US"
    # Fallback: yfinance suffix
    return "US"


def get_symbols_for_market(market: str) -> Dict[str, str]:
    """Piyasa kodu için sembol sözlüğünü döndür."""
    market = market.upper()
    if market == "TR":
        return BIST_SYMBOLS
    if market == "CRYPTO":
        return CRYPTO_SYMBOLS
    return US_SYMBOLS
```

to:

```python
def get_market_for_symbol(symbol: str) -> str:
    """Sembole bakarak piyasayı tespit et."""
    sym = symbol.upper()
    if sym.endswith(".IS"):
        return "TR"
    if sym.endswith("-USD") or sym in CRYPTO_SYMBOLS:
        return "CRYPTO"
    if sym in get_us_symbols():
        return "US"
    # Fallback: yfinance suffix
    return "US"


def get_symbols_for_market(market: str) -> Dict[str, str]:
    """Piyasa kodu için sembol sözlüğünü döndür."""
    market = market.upper()
    if market == "TR":
        return BIST_SYMBOLS
    if market == "CRYPTO":
        return CRYPTO_SYMBOLS
    return get_us_symbols()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/src && pytest tests/test_market_config_us_symbols.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/core/market_config.py backend/src/tests/test_market_config_us_symbols.py
git commit -m "feat: add get_us_symbols() with a file cache and frozen fallback"
```

---

### Task 2: Propagate to the News engine's symbol lookups

**Files:**
- Modify: `backend/src/core/news_analyzer.py:396-397`, `backend/src/news/entity_extraction.py:20,31-42,68-75`
- Test: `backend/src/tests/test_news_analyzer_query_for_symbol.py` (new), `backend/src/tests/test_news_entity_extraction.py` (modify if it exists, else new)

**Interfaces:**
- Consumes: `core.market_config.get_us_symbols()` (Task 1).

- [ ] **Step 1: Write the failing tests**

First check whether an entity-extraction test file already exists:

```bash
ls backend/src/tests/test_news_entity_extraction.py 2>/dev/null || echo "does not exist yet"
```

If it exists, append this test to it; otherwise create it with this content:

```python
# backend/src/tests/test_news_entity_extraction.py (append, or create with this plus any existing tests already there)
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
```

Also add, to `backend/src/tests/test_news_analyzer_query_for_symbol.py` (new file):

```python
import json

import core.market_config as market_config
from core.news_analyzer import _query_for_symbol


def test_query_for_symbol_resolves_a_name_only_in_the_dynamic_us_list(tmp_path, monkeypatch):
    path = tmp_path / "sp500_symbols.json"
    path.write_text(json.dumps({"sp500_symbols": {"ABNB": "Airbnb"}}))
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))

    assert _query_for_symbol("ABNB", "US") == "Airbnb"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/src && pytest tests/test_news_entity_extraction.py tests/test_news_analyzer_query_for_symbol.py -v`
Expected: FAIL - `ABNB` is not in the frozen 28-symbol snapshot, so neither test finds it (entity extraction's module-level gazetteer was built once from the real `US_SYMBOLS`/now-frozen-snapshot at import time; `_query_for_symbol` looks it up the same stale way).

- [ ] **Step 3: Switch both to `get_us_symbols()`, called fresh**

In `backend/src/core/news_analyzer.py:396-397`, change:

```python
    from core.market_config import BIST_SYMBOLS, US_SYMBOLS, CRYPTO_SYMBOLS
    names = {**BIST_SYMBOLS, **US_SYMBOLS, **CRYPTO_SYMBOLS}
```

to:

```python
    from core.market_config import BIST_SYMBOLS, CRYPTO_SYMBOLS, get_us_symbols
    names = {**BIST_SYMBOLS, **get_us_symbols(), **CRYPTO_SYMBOLS}
```

In `backend/src/news/entity_extraction.py:20`, change:

```python
from core.market_config import BIST_SYMBOLS, CRYPTO_SYMBOLS, US_SYMBOLS
```

to:

```python
from core.market_config import BIST_SYMBOLS, CRYPTO_SYMBOLS, get_us_symbols
```

Then, lines 31-42 (the module-level gazetteer build), change:

```python
def _build_gazetteers() -> tuple[Dict[str, str], Dict[str, str]]:
    """Return (ticker -> symbol [case-sensitive], company name -> symbol)."""
    ticker_map: Dict[str, str] = {}
    company_map: Dict[str, str] = {}
    for table in (US_SYMBOLS, BIST_SYMBOLS, CRYPTO_SYMBOLS):
        for symbol, name in table.items():
            ticker_map[symbol] = symbol
            company_map[name.lower()] = symbol
    return ticker_map, company_map


_TICKER_MAP, _COMPANY_MAP = _build_gazetteers()
```

to:

```python
def _build_gazetteers() -> tuple[Dict[str, str], Dict[str, str]]:
    """Return (ticker -> symbol [case-sensitive], company name -> symbol).
    Called fresh on every extract() call (not cached at module-import
    time) - get_us_symbols() can change without a server restart, and
    the gazetteer must reflect that."""
    ticker_map: Dict[str, str] = {}
    company_map: Dict[str, str] = {}
    for table in (get_us_symbols(), BIST_SYMBOLS, CRYPTO_SYMBOLS):
        for symbol, name in table.items():
            ticker_map[symbol] = symbol
            company_map[name.lower()] = symbol
    return ticker_map, company_map
```

(the module-level `_TICKER_MAP, _COMPANY_MAP = _build_gazetteers()` line is deleted entirely - no module-level cache remains).

Finally, in `extract()` (lines 68-75 originally), change:

```python
    def extract(self, text: str) -> List[Entity]:
        if not text:
            return []

        entities: List[Entity] = []
        seen_symbols: set = set()

        for symbol in _TICKER_MAP:
            if symbol in seen_symbols:
                continue
            if re.search(rf"\b{re.escape(symbol)}\b", text):
                seen_symbols.add(symbol)
                entities.append(Entity(text=symbol, entity_type=EntityType.TICKER, symbol=symbol))

        lower = text.lower()
        for name, symbol in _COMPANY_MAP.items():
```

to:

```python
    def extract(self, text: str) -> List[Entity]:
        if not text:
            return []

        ticker_map, company_map = _build_gazetteers()
        entities: List[Entity] = []
        seen_symbols: set = set()

        for symbol in ticker_map:
            if symbol in seen_symbols:
                continue
            if re.search(rf"\b{re.escape(symbol)}\b", text):
                seen_symbols.add(symbol)
                entities.append(Entity(text=symbol, entity_type=EntityType.TICKER, symbol=symbol))

        lower = text.lower()
        for name, symbol in company_map.items():
```

(the rest of `extract()` is unchanged - it already only referenced `_COMPANY_MAP` by the name `company_map` going forward).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/src && pytest tests/test_news_entity_extraction.py tests/test_news_analyzer_query_for_symbol.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/core/news_analyzer.py backend/src/news/entity_extraction.py backend/src/tests/test_news_entity_extraction.py backend/src/tests/test_news_analyzer_query_for_symbol.py
git commit -m "feat: resolve US symbol names dynamically in news analysis"
```

---

### Task 3: Pin research scripts to the original 28-symbol universe

**Files:**
- Create: `backend/src/scripts/_frozen_us_symbols.py`
- Modify: `backend/src/scripts/backfill_sec_fundamentals.py:65`, `backend/src/scripts/backfill_feature_store.py:46`, `backend/src/scripts/backfill_news_features.py:54`, `backend/src/scripts/train_ml_candidate_us_news.py:33`, `backend/src/scripts/train_ml_candidate_us_news_window2.py:39`, `backend/src/scripts/train_ml_candidate_us_news_control.py:44`, `backend/src/scripts/train_ml_candidate_us_fundamentals.py:53`
- Test: `backend/src/tests/test_scripts_frozen_us_symbols.py` (new)

**Interfaces:**
- Produces: `scripts._frozen_us_symbols.ORIGINAL_US_SYMBOLS_28: Dict[str, str]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/src/tests/test_scripts_frozen_us_symbols.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/src && pytest tests/test_scripts_frozen_us_symbols.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts._frozen_us_symbols'`

- [ ] **Step 3: Create the frozen module and repoint each script's import**

Create `backend/src/scripts/_frozen_us_symbols.py`:

```python
"""Frozen copy of core/market_config.py's original, pre-2026-11-01
US_SYMBOLS dict (28 symbols), for the research/backfill scripts in
this package only. core.market_config.get_us_symbols() is now dynamic
(the real, changing S&P 500 list) - these scripts already ran once
against this exact 28-symbol universe, and must keep doing so on any
future re-run, or their published results stop being reproducible."""
from typing import Dict

ORIGINAL_US_SYMBOLS_28: Dict[str, str] = {
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "NVDA":  "NVIDIA",
    "GOOGL": "Alphabet",
    "META":  "Meta",
    "AMZN":  "Amazon",
    "TSLA":  "Tesla",
    "AMD":   "AMD",
    "INTC":  "Intel",
    "CRM":   "Salesforce",
    "JPM":   "JPMorgan",
    "BAC":   "Bank of America",
    "GS":    "Goldman Sachs",
    "MS":    "Morgan Stanley",
    "V":     "Visa",
    "MA":    "Mastercard",
    "JNJ":   "Johnson & Johnson",
    "LLY":   "Eli Lilly",
    "PFE":   "Pfizer",
    "UNH":   "UnitedHealth",
    "XOM":   "ExxonMobil",
    "CVX":   "Chevron",
    "WMT":   "Walmart",
    "HD":    "Home Depot",
    "MCD":   "McDonald's",
    "CAT":   "Caterpillar",
    "BA":    "Boeing",
    "GE":    "GE Aerospace",
}
```

In each of the 7 scripts, change the single import line:

`backend/src/scripts/backfill_sec_fundamentals.py:65`, `backend/src/scripts/backfill_feature_store.py:46`, `backend/src/scripts/backfill_news_features.py:54`, `backend/src/scripts/train_ml_candidate_us_news.py:33`, `backend/src/scripts/train_ml_candidate_us_news_window2.py:39`, `backend/src/scripts/train_ml_candidate_us_news_control.py:44`, `backend/src/scripts/train_ml_candidate_us_fundamentals.py:53` - each currently reads:

```python
from core.market_config import US_SYMBOLS
```

Change every one of those 7 lines to:

```python
from scripts._frozen_us_symbols import ORIGINAL_US_SYMBOLS_28 as US_SYMBOLS
```

No other line in any of the 7 scripts changes - each already refers to the local name `US_SYMBOLS` (`US_SYMBOLS.keys()`, `len(US_SYMBOLS)`, etc.), which keeps working unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/src && pytest tests/test_scripts_frozen_us_symbols.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/scripts/_frozen_us_symbols.py backend/src/scripts/backfill_sec_fundamentals.py backend/src/scripts/backfill_feature_store.py backend/src/scripts/backfill_news_features.py backend/src/scripts/train_ml_candidate_us_news.py backend/src/scripts/train_ml_candidate_us_news_window2.py backend/src/scripts/train_ml_candidate_us_news_control.py backend/src/scripts/train_ml_candidate_us_fundamentals.py backend/src/tests/test_scripts_frozen_us_symbols.py
git commit -m "fix: pin research scripts to the original 28-symbol US universe"
```

---

### Task 4: Daily S&P 500 refresh loop

**Files:**
- Modify: `backend/src/main.py:818` (add task to the startup list), and a new section near `market_opportunities_refresh_loop` (around line 594)
- Test: `backend/src/tests/test_main_sp500_refresh_loop.py` (new)

**Interfaces:**
- Consumes: `core.market_config.SP500_SYMBOLS_PATH` (Task 1).
- Produces: `main.sp500_refresh_loop() -> None` (background coroutine), `main._fetch_sp500_symbols_from_wikipedia() -> Dict[str, str]` (the mockable fetch step), `main._SP500_REFRESH_INTERVAL_SECONDS: float`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/src/tests/test_main_sp500_refresh_loop.py
"""sp500_refresh_loop keeps core.market_config.SP500_SYMBOLS_PATH's
cache current from Wikipedia's S&P 500 constituent table, once a day -
mirrors research/retrain_chart_models.py's own "infra failure never
destroys good data" principle, and market_opportunities_refresh_loop's
own test style/_run_one_cycle helper (test_main_background_scan_loops.py)."""
import asyncio
import json

import pytest

import main as main_module


async def _run_one_cycle(loop_coro_factory, timeout: float = 0.2):
    task = asyncio.create_task(loop_coro_factory())
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_sp500_refresh_loop_writes_the_cache_file_on_a_successful_fetch(tmp_path, monkeypatch):
    import core.market_config as market_config

    path = tmp_path / "sp500_symbols.json"
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))
    monkeypatch.setattr(main_module, "_SP500_REFRESH_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(main_module, "_fetch_sp500_symbols_from_wikipedia", lambda: {"AAPL": "Apple"})

    await _run_one_cycle(main_module.sp500_refresh_loop)

    assert json.loads(path.read_text()) == {"sp500_symbols": {"AAPL": "Apple"}}


@pytest.mark.asyncio
async def test_sp500_refresh_loop_leaves_the_existing_cache_untouched_on_fetch_failure(tmp_path, monkeypatch):
    import core.market_config as market_config

    path = tmp_path / "sp500_symbols.json"
    path.write_text(json.dumps({"sp500_symbols": {"AAPL": "Apple"}}))
    monkeypatch.setattr(market_config, "SP500_SYMBOLS_PATH", str(path))
    monkeypatch.setattr(main_module, "_SP500_REFRESH_INTERVAL_SECONDS", 0.01)

    def _raise():
        raise RuntimeError("wikipedia unreachable")

    monkeypatch.setattr(main_module, "_fetch_sp500_symbols_from_wikipedia", _raise)

    await _run_one_cycle(main_module.sp500_refresh_loop)  # must not raise

    assert json.loads(path.read_text()) == {"sp500_symbols": {"AAPL": "Apple"}}


def test_fetch_sp500_symbols_from_wikipedia_normalizes_dot_tickers_to_hyphens(monkeypatch):
    """Wikipedia's table uses dot notation for dual-class shares
    (BRK.B); yfinance expects the hyphen convention (BRK-B) - an
    unnormalized ticker would be silently unfetchable everywhere
    downstream."""
    import pandas as pd

    fake_table = pd.DataFrame({
        "Symbol": ["AAPL", "BRK.B"],
        "Security": ["Apple Inc.", "Berkshire Hathaway"],
    })
    monkeypatch.setattr(main_module.pd, "read_html", lambda url: [fake_table])

    result = main_module._fetch_sp500_symbols_from_wikipedia()

    assert result["AAPL"] == "Apple Inc."
    assert result["BRK-B"] == "Berkshire Hathaway"
    assert "BRK.B" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/src && pytest tests/test_main_sp500_refresh_loop.py -v`
Expected: FAIL with `AttributeError: module 'main' has no attribute 'sp500_refresh_loop'` (or `_fetch_sp500_symbols_from_wikipedia`, or `_SP500_REFRESH_INTERVAL_SECONDS`).

- [ ] **Step 3: Add the fetch function and the loop**

Neither `json` nor `pandas` is imported at the top of `backend/src/main.py` today (confirmed: `grep -n "^import json\|^import pandas" backend/src/main.py` returns nothing). Add both next to the existing `import os` (line 10):

```python
import json
import os
import pandas as pd
```

Then, near `market_opportunities_refresh_loop` (around line 594 in `backend/src/main.py`), add:

```python
_SP500_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60  # once a day


def _fetch_sp500_symbols_from_wikipedia() -> Dict[str, str]:
    """Scrapes the current S&P 500 constituent table from Wikipedia
    (network call - only ever invoked from sp500_refresh_loop, never
    inline on a request path). Tickers are normalized from Wikipedia's
    dot notation for dual-class shares (e.g. BRK.B) to yfinance's own
    hyphen convention (BRK-B) - see this function's own test for why."""
    tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    table = tables[0]
    symbols: Dict[str, str] = {}
    for _, row in table.iterrows():
        symbol = str(row["Symbol"]).strip().replace(".", "-")
        name = str(row["Security"]).strip()
        symbols[symbol] = name
    return symbols


async def sp500_refresh_loop() -> None:
    """Keeps core.market_config.SP500_SYMBOLS_PATH's cache current from
    Wikipedia's S&P 500 table, once a day. A fetch/parse failure logs
    and leaves the existing cache file exactly as it was - never
    deletes or truncates good data (same principle as
    research/retrain_chart_models.py's own infra-failure handling)."""
    from core.market_config import SP500_SYMBOLS_PATH

    while True:
        await asyncio.sleep(_SP500_REFRESH_INTERVAL_SECONDS)
        try:
            symbols = await _run_in_executor(_fetch_sp500_symbols_from_wikipedia)
            os.makedirs(os.path.dirname(SP500_SYMBOLS_PATH), exist_ok=True)
            with open(SP500_SYMBOLS_PATH, "w", encoding="utf-8") as f:
                json.dump({"sp500_symbols": symbols}, f, ensure_ascii=False, indent=2)
            logger.info(f"S&P 500 sembol listesi güncellendi ({len(symbols)} sembol).")
        except Exception as e:
            logger.error(f"S&P 500 sembol listesi güncellenemedi, mevcut önbellek korunuyor: {e}")
```

Then, in `backend/src/main.py`'s startup task list (around line 818), change:

```python
        _background_tasks = [
            asyncio.create_task(self_evolution_loop()),
            asyncio.create_task(alert_scan_loop()),
            asyncio.create_task(paper_trading_fill_loop()),
            asyncio.create_task(retention_purge_loop()),
            asyncio.create_task(background_intelligence_scan_loop()),
            asyncio.create_task(dashboard_cache_refresh_loop()),
            asyncio.create_task(market_opportunities_refresh_loop()),
        ]
```

to:

```python
        _background_tasks = [
            asyncio.create_task(self_evolution_loop()),
            asyncio.create_task(alert_scan_loop()),
            asyncio.create_task(paper_trading_fill_loop()),
            asyncio.create_task(retention_purge_loop()),
            asyncio.create_task(background_intelligence_scan_loop()),
            asyncio.create_task(dashboard_cache_refresh_loop()),
            asyncio.create_task(market_opportunities_refresh_loop()),
            asyncio.create_task(sp500_refresh_loop()),
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/src && pytest tests/test_main_sp500_refresh_loop.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/main.py backend/src/tests/test_main_sp500_refresh_loop.py
git commit -m "feat: refresh the S&P 500 symbol cache daily from Wikipedia"
```

---

### Task 5: Opportunities scanner - US tick-gate and higher concurrency

**Files:**
- Modify: `backend/src/main.py:555` (`_MARKET_OPPORTUNITIES_MAX_RESULTS` section), `:558-588` (`_refresh_market_opportunities`), `:594-621` (`market_opportunities_refresh_loop`)
- Test: `backend/src/tests/test_main_background_scan_loops.py` (modify), `backend/src/tests/test_main_market_opportunities_endpoint.py` (modify)

**Interfaces:**
- Consumes: `intelligence.config.MarketScannerConfig` (pre-existing), `intelligence.market_scanner.MarketScanner` (pre-existing).
- Produces: `main._MARKET_OPPORTUNITIES_US_TICK_INTERVAL: int` (6), `main._market_opportunities_tick_count: int` (module-level counter).

- [ ] **Step 1: Write the failing tests**

Append to `backend/src/tests/test_main_background_scan_loops.py` (same file, same `_run_one_cycle` helper already used by the other `market_opportunities_refresh_loop` tests in it):

```python
@pytest.mark.asyncio
async def test_market_opportunities_refresh_loop_only_refreshes_us_every_sixth_tick(monkeypatch):
    calls = []
    monkeypatch.setattr(main_module, "_pipeline_service", object())
    monkeypatch.setattr(main_module, "_MARKET_OPPORTUNITIES_REFRESH_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(main_module, "_market_opportunities_tick_count", 0)
    monkeypatch.setattr(main_module, "_refresh_market_opportunities", lambda market: calls.append(market))

    # Run for a window wide enough for exactly 5 ticks (5 * 0.01s), not
    # yet the 6th - US must not have been refreshed at all.
    await _run_one_cycle(main_module.market_opportunities_refresh_loop, timeout=0.055)

    assert "US" not in calls
    assert "TR" in calls and "CRYPTO" in calls


@pytest.mark.asyncio
async def test_market_opportunities_refresh_loop_refreshes_us_on_the_sixth_tick(monkeypatch):
    calls = []
    monkeypatch.setattr(main_module, "_pipeline_service", object())
    monkeypatch.setattr(main_module, "_MARKET_OPPORTUNITIES_REFRESH_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(main_module, "_market_opportunities_tick_count", 0)
    monkeypatch.setattr(main_module, "_refresh_market_opportunities", lambda market: calls.append(market))

    # Wide enough for at least 6 ticks.
    await _run_one_cycle(main_module.market_opportunities_refresh_loop, timeout=0.09)

    assert "US" in calls
```

Append to `backend/src/tests/test_main_market_opportunities_endpoint.py` (same file, already has `OpportunityAssessment`/`OpportunityRankingResult`/etc. imported from Task... from this session's earlier chart-AI work):

```python
def test_refresh_market_opportunities_uses_higher_concurrency_for_us(monkeypatch):
    """US's symbol universe is now the full S&P 500 (~500 symbols) -
    the scanner's default concurrency (max_parallel_symbols=3) would
    make a single scan take far too long. US must get its own,
    higher-concurrency MarketScannerConfig; TR/CRYPTO keep the default."""
    import intelligence.market_scanner as market_scanner_module

    captured_configs = []
    original_init = market_scanner_module.MarketScanner.__init__

    def _capturing_init(self, pipeline_service=None, config=None):
        captured_configs.append(config)
        original_init(self, pipeline_service=pipeline_service, config=config)

    monkeypatch.setattr(market_scanner_module.MarketScanner, "__init__", _capturing_init)
    monkeypatch.setattr(main_module, "scan_and_rank", lambda scanner, symbols, config=None: OpportunityRankingResult(
        ranked=[], failed_symbols=[], unclassifiable_symbols=[], ranked_count=0, total_scanned_count=0,
    ))
    monkeypatch.setattr(main_module, "_opportunities_cache", type("C", (), {"set": staticmethod(lambda m, p: None)})())
    monkeypatch.setattr(main_module, "_pipeline_service", object())

    main_module._refresh_market_opportunities("US")
    main_module._refresh_market_opportunities("TR")

    assert captured_configs[0] is not None and captured_configs[0].max_parallel_symbols == 10
    assert captured_configs[1] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/src && pytest tests/test_main_background_scan_loops.py -k sixth_tick -v tests/test_main_market_opportunities_endpoint.py -k higher_concurrency -v`
Expected: FAIL - the tick-gate tests fail because `market_opportunities_refresh_loop` refreshes US on every tick today; the concurrency test fails because `_refresh_market_opportunities` never passes a `config` to `MarketScanner` today (`captured_configs[0]` is `None`, not a `MarketScannerConfig` with `max_parallel_symbols=10`).

- [ ] **Step 3: Add the tick-gate and the US-specific scanner config**

In `backend/src/main.py`, near `_MARKET_OPPORTUNITIES_MAX_RESULTS = 10` (around line 555), add:

```python
_MARKET_OPPORTUNITIES_US_TICK_INTERVAL = 6  # 6 * 300s = 30 minutes
_market_opportunities_tick_count = 0
```

In `_refresh_market_opportunities` (around line 558), change:

```python
def _refresh_market_opportunities(market: str) -> None:
    ...
    from core.market_config import get_symbols_for_market
    from intelligence.market_scanner import MarketScanner

    symbols = list(get_symbols_for_market(market).keys())
    scanner = MarketScanner(pipeline_service=_pipeline_service)
    result = scan_and_rank(scanner, symbols)
```

to:

```python
def _refresh_market_opportunities(market: str) -> None:
    ...
    from core.market_config import get_symbols_for_market
    from intelligence.config import MarketScannerConfig
    from intelligence.market_scanner import MarketScanner

    symbols = list(get_symbols_for_market(market).keys())
    # US's universe is now the full S&P 500 (~500 symbols, vs. TR/
    # CRYPTO's much smaller curated lists) - the scanner's default
    # concurrency (3) would make one scan take far too long; TR/CRYPTO
    # keep the default, unchanged.
    scanner_config = MarketScannerConfig(max_parallel_symbols=10) if market == "US" else None
    scanner = MarketScanner(pipeline_service=_pipeline_service, config=scanner_config)
    result = scan_and_rank(scanner, symbols)
```

(leave the function's docstring and everything after the `scanner = MarketScanner(...)` line unchanged).

In `market_opportunities_refresh_loop` (around line 594), change:

```python
    while True:
        await asyncio.sleep(_MARKET_OPPORTUNITIES_REFRESH_INTERVAL_SECONDS)
        if _pipeline_service is None:
            continue
        if _HEAVY_BACKGROUND_SCAN_LOCK.locked():
            logger.info("Piyasa fırsatları yenileme: başka bir tarama devam ediyor, bu tur atlanıyor.")
            continue
        async with _HEAVY_BACKGROUND_SCAN_LOCK:
            for market in ("TR", "US", "CRYPTO"):
                try:
                    await _run_in_executor(_refresh_market_opportunities, market)
                except Exception as e:
                    logger.error(f"Piyasa fırsatları yenileme hatası ({market}): {e}")
```

to:

```python
    global _market_opportunities_tick_count
    while True:
        await asyncio.sleep(_MARKET_OPPORTUNITIES_REFRESH_INTERVAL_SECONDS)
        if _pipeline_service is None:
            continue
        if _HEAVY_BACKGROUND_SCAN_LOCK.locked():
            logger.info("Piyasa fırsatları yenileme: başka bir tarama devam ediyor, bu tur atlanıyor.")
            continue
        async with _HEAVY_BACKGROUND_SCAN_LOCK:
            _market_opportunities_tick_count += 1
            markets = ["TR", "CRYPTO"]
            if _market_opportunities_tick_count % _MARKET_OPPORTUNITIES_US_TICK_INTERVAL == 0:
                markets.append("US")
            for market in markets:
                try:
                    await _run_in_executor(_refresh_market_opportunities, market)
                except Exception as e:
                    logger.error(f"Piyasa fırsatları yenileme hatası ({market}): {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/src && pytest tests/test_main_background_scan_loops.py tests/test_main_market_opportunities_endpoint.py -v`
Expected: PASS (all tests in both files, including the pre-existing ones from this session's earlier chart-AI/market-opportunities work - `test_market_opportunities_refresh_loop_refreshes_every_supported_market` and the two other pre-existing loop tests still pass because their test windows run far more than 6 ticks, so US's gate still fires at least once inside them).

- [ ] **Step 5: Commit**

```bash
git add backend/src/main.py backend/src/tests/test_main_background_scan_loops.py backend/src/tests/test_main_market_opportunities_endpoint.py
git commit -m "perf: gate the US opportunities scan to every 6th tick, raise its concurrency"
```
