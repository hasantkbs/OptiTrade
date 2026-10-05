# Web Frontend Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut OptiTrade's web app down to the minimum an independent retail user needs — pick a stock or crypto asset, see its chart/volume/news, see the model's plain buy/sell/hold recommendation, plus a simple market-context home page — removing portfolio management and all engine/terminology jargon.

**Architecture:** One new backend provider (CoinGecko BTC dominance) + one new additive backend endpoint (`/market/snapshot`, reusing the existing chart-building logic via a small extracted helper) feed a new, small home page. The asset page gains a volume sub-chart and a real-headline news panel (wiring up an already-existing but unused `/news/{symbol}` endpoint), and collapses 4 jargon-heavy components into one plain-language `Recommendation`. A final deletion task removes Portfolio/AI-Analyst/Learning/Research/Decisions/old-Dashboard entirely.

**Tech Stack:** FastAPI/Pydantic (backend), React + TypeScript + React Query + recharts + Vitest/RTL (frontend) — all already in use, no new frontend libraries.

**Spec:** `docs/superpowers/specs/2026-10-05-web-simplification-design.md`

## Global Constraints

- Every commit ends with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Zero changes to `decision_engine`, any voting engine, `/quant/analyze`, or `/news/{symbol}` — this plan only changes what the frontend displays and adds two new, additive, read-only backend surfaces.
- `/market/snapshot` and `coingecko_provider` are strictly additive — `/chart/{symbol}`'s existing behavior must be byte-for-byte unchanged after the shared-logic extraction (Task 1's own regression test proves this).
- The `Recommendation` component displays only fields the backend already returns (`decision`, `explanation`, `confidence` mapped to a plain word) — nothing fabricated.
- Confidence word thresholds are exact and used verbatim in exactly one place: `confidence >= 0.66` → `"Yüksek güven"`, `0.33 <= confidence < 0.66` → `"Orta güven"`, `confidence < 0.33` → `"Düşük güven"`.
- Watchlist and Alerts pages are functionally unchanged — no restructuring. In particular, `usePortfolioList`/`portfolioApi` (in `dashboard/hooks.ts`/`api/endpoints.ts`) are **not deleted** — `features/alerts/CreateAlertForm.tsx`'s portfolio-type alert depends on `usePortfolioList`, and that dependency must keep working even though the standalone Portfolio *page/feature-directory* is removed.
- `btc_dominance_pct` degrades honestly to `None`/"unavailable" on any CoinGecko failure — never a fabricated or silently-stale number.

## Review Focus

- A symbol with an empty `headlines` array from `GET /news/{symbol}` (a real, valid response shape per `core/news_analyzer.py::get_news_summary` — `headlines` can legitimately be `[]`) must render `AssetNews` as a clean "no news" state, not a crash or a blank gap. Covered in Task 4.
- `GET /market/snapshot` when CoinGecko fails but BIST100/BTC succeed must return `200` with `btc_dominance_pct: null`, never a `500` — and symmetrically, if one index chart fails while the other two succeed, the response must still be `200` with that one field `null`. Covered in Task 1.
- The deletion task (Task 5) must leave zero dangling imports — confirmed by an explicit `npm run typecheck` + `npm run build` + `npm run test` pass, not just by the grep performed during planning.
- A user with a bookmarked, now-removed route (`/portfolio`, `/decisions`, `/ai-analyst`, `/learning`, `/research`) must land somewhere sane. Confirmed during planning: `App.tsx`'s existing catch-all (`<Route path="*" element={<Navigate to="/" replace />} />`) already handles this — no new code needed, just confirmed as the covering behavior in Task 5.
- `CreateAlertForm.tsx`'s portfolio-type alert must still work after Task 5's deletion — it depends on `usePortfolioList` (`dashboard/hooks.ts`), which lives outside `features/portfolio/` and must NOT be deleted. Covered in Task 5's own explicit check.

---

### Task 1: CoinGecko provider + `/market/snapshot` endpoint

**Files:**
- Create: `backend/src/providers/coingecko_provider.py`
- Create: `backend/src/tests/test_coingecko_provider.py`
- Modify: `backend/src/models/schemas.py` (add `MarketSnapshotResponse`, after `ChartResponse` at line 107)
- Modify: `backend/src/main.py:1904-1950` (extract `_build_chart_response` helper from `get_chart`'s body; add `GET /market/snapshot`)
- Create: `backend/src/tests/test_main_market_snapshot_endpoint.py`

**Interfaces:**
- Consumes: `data.fetcher.fetch_history(symbol: str, period: str = "1mo") -> Optional[pd.DataFrame]` (unchanged); `models.schemas.ChartResponse`/`ChartPoint` (unchanged).
- Produces (for the frontend, Task 2): `GET /market/snapshot` → `MarketSnapshotResponse` JSON: `{bist100: ChartResponse | null, btc: ChartResponse | null, btc_dominance_pct: float | null, generated_at: str}`.

- [ ] **Step 1: Write the failing tests for `coingecko_provider.get_btc_dominance`**

```python
# backend/src/tests/test_coingecko_provider.py
from unittest.mock import MagicMock, patch

import httpx

from providers.coingecko_provider import get_btc_dominance


def test_get_btc_dominance_returns_value_on_success():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"data": {"market_cap_percentage": {"btc": 54.32, "eth": 17.1}}}
    with patch("providers.coingecko_provider.httpx.get", return_value=mock_response) as mock_get:
        result = get_btc_dominance()
    assert result == 54.32
    mock_get.assert_called_once()


def test_get_btc_dominance_returns_none_on_http_error():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=MagicMock(),
    )
    with patch("providers.coingecko_provider.httpx.get", return_value=mock_response):
        result = get_btc_dominance()
    assert result is None


def test_get_btc_dominance_returns_none_on_timeout():
    with patch("providers.coingecko_provider.httpx.get", side_effect=httpx.TimeoutException("timed out")):
        result = get_btc_dominance()
    assert result is None


def test_get_btc_dominance_returns_none_on_malformed_json():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"data": {}}  # missing market_cap_percentage entirely
    with patch("providers.coingecko_provider.httpx.get", return_value=mock_response):
        result = get_btc_dominance()
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_coingecko_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'providers.coingecko_provider'`.

- [ ] **Step 3: Implement `coingecko_provider.py`**

```python
# backend/src/providers/coingecko_provider.py
"""
OptiTrade — CoinGecko BTC dominance provider
================================================
Calls CoinGecko's free, keyless /api/v3/global endpoint for BTC's
share of total crypto market cap. Mirrors BinanceProvider's own
"return None on any failure, never raise" convention
(providers/binance_provider.py) - this is an optional market-context
figure for the simplified home page, never a value any decision logic
depends on.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"


def get_btc_dominance() -> Optional[float]:
    """BTC's percentage share of total crypto market cap, or None on
    any failure (timeout, non-200, missing field) - logged, never
    raised."""
    try:
        resp = httpx.get(_GLOBAL_URL, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        value = data["data"]["market_cap_percentage"]["btc"]
        return float(value)
    except Exception as exc:
        logger.warning("CoinGecko BTC dominance fetch failed: %s", exc)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_coingecko_provider.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Add `MarketSnapshotResponse` to `models/schemas.py`**

Add after `ChartResponse` (currently ending at line 106) in `backend/src/models/schemas.py`:

```python
class MarketSnapshotResponse(BaseModel):
    bist100: Optional[ChartResponse] = None
    btc: Optional[ChartResponse] = None
    btc_dominance_pct: Optional[float] = None
    generated_at: str
```

- [ ] **Step 6: Write the failing tests for `/market/snapshot` and the `/chart/{symbol}` regression**

```python
# backend/src/tests/test_main_market_snapshot_endpoint.py
"""Integration tests for GET /market/snapshot and the zero-behavior-
change extraction of _build_chart_response from GET /chart/{symbol}.
Uses the shared `client` fixture (real main.app - see conftest.py).
No auth required on either endpoint, matching GET /chart/{symbol}'s
existing convention."""
from unittest.mock import patch


def test_chart_endpoint_unchanged_after_extraction(client):
    """The single most important test in this task: GET /chart/{symbol}
    must behave byte-for-byte identically to before the
    _build_chart_response extraction."""
    r = client.get("/chart/AAPL?period=1mo")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "AAPL"
    assert body["period"] == "1mo"
    assert isinstance(body["points"], list)
    assert len(body["points"]) > 0
    assert "close" in body["points"][0]
    assert "volume" in body["points"][0]


def test_chart_endpoint_still_404s_for_unknown_symbol(client):
    r = client.get("/chart/NOT-A-REAL-SYMBOL-XYZ?period=1mo")
    assert r.status_code == 404


def test_market_snapshot_returns_both_indices_and_dominance(client):
    with patch("main.get_btc_dominance", return_value=54.3):
        r = client.get("/market/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["bist100"] is not None
    assert body["btc"] is not None
    assert body["btc_dominance_pct"] == 54.3
    assert "generated_at" in body


def test_market_snapshot_degrades_to_null_dominance_on_coingecko_failure(client):
    """GET /market/snapshot when CoinGecko fails but BIST100/BTC
    succeed must return 200 with btc_dominance_pct: null, never a 500."""
    with patch("main.get_btc_dominance", return_value=None):
        r = client.get("/market/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["btc_dominance_pct"] is None
    assert body["bist100"] is not None
    assert body["btc"] is not None


def test_market_snapshot_degrades_to_null_bist100_when_that_fetch_fails(client):
    """Symmetric case: if one index chart's own fetch_history call
    fails while the other index and CoinGecko both succeed, the
    response must still be 200 with that one field null, never a 500."""
    with patch("main._build_chart_response", side_effect=[None, {"symbol": "BTC-USD", "period": "3mo", "points": [], "change_pct": 0.0, "high": 0.0, "low": 0.0}]), \
         patch("main.get_btc_dominance", return_value=54.3):
        r = client.get("/market/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["bist100"] is None
    assert body["btc"] is not None
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_main_market_snapshot_endpoint.py -v`
Expected: FAIL — `test_market_snapshot_*` fail with `404 Not Found` (route doesn't exist yet); `test_chart_endpoint_*` should already PASS (they test current, unmodified behavior) — confirm they pass BEFORE Step 8 changes anything, so you have a true before/after comparison.

- [ ] **Step 8: Extract `_build_chart_response` and add `GET /market/snapshot`**

In `backend/src/main.py`, replace the full body of `get_chart` (currently lines ~1904-1950, from `@app.get("/chart/{symbol}"...)` through the final `return ChartResponse(...)`) with:

```python
def _build_chart_response(symbol: str, period: str) -> Optional[ChartResponse]:
    """Extracted from get_chart's own body (zero behavior change) so
    GET /market/snapshot can reuse the exact same chart-building logic
    for its two index series, rather than a parallel reimplementation."""
    import numpy as np
    hist = fetch_history(symbol.upper(), period=period)
    if hist is None or hist.empty:
        return None

    prices = hist["Close"]
    rsi_series = None
    if len(prices) >= 15:
        delta    = prices.diff()
        gain     = delta.where(delta > 0, 0.0)
        loss     = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=13, min_periods=14).mean()
        avg_loss = loss.ewm(com=13, min_periods=14).mean()
        rs       = avg_gain / avg_loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))

    points: List[ChartPoint] = []
    for i, (idx, row) in enumerate(hist.iterrows()):
        rsi_val = None
        if rsi_series is not None:
            v = rsi_series.iloc[i]
            if v == v:  # NaN kontrolü
                rsi_val = float(v)
        points.append(ChartPoint(
            date=idx.strftime("%Y-%m-%d"),
            close=round(float(row["Close"]), 4),
            volume=float(row["Volume"]),
            rsi=round(rsi_val, 1) if rsi_val is not None else None,
        ))

    first_close = float(hist["Close"].iloc[0])
    last_close  = float(hist["Close"].iloc[-1])
    change_pct  = ((last_close - first_close) / first_close) * 100 if first_close > 0 else 0.0
    return ChartResponse(
        symbol=symbol.upper(), period=period, points=points,
        change_pct=round(change_pct, 2),
        high=round(float(hist["High"].max()), 4),
        low=round(float(hist["Low"].min()),  4),
    )


@app.get("/chart/{symbol}", response_model=ChartResponse)
@limiter.limit("30/minute")
def get_chart(
    request: Request,
    symbol: str,
    period: str = Query(default="3mo", pattern="^(1mo|3mo|6mo|1y)$"),
) -> ChartResponse:
    chart = _build_chart_response(symbol, period)
    if chart is None:
        raise HTTPException(status_code=404, detail=f"{symbol} icin grafik verisi bulunamadi.")
    return chart


@app.get("/market/snapshot", response_model=MarketSnapshotResponse)
@limiter.limit("30/minute")
def get_market_snapshot(request: Request) -> MarketSnapshotResponse:
    return MarketSnapshotResponse(
        bist100=_build_chart_response("XU100.IS", "3mo"),
        btc=_build_chart_response("BTC-USD", "3mo"),
        btc_dominance_pct=get_btc_dominance(),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
```

Add the import `from providers.coingecko_provider import get_btc_dominance` near `main.py`'s other `providers`/`data.fetcher` imports. Add `MarketSnapshotResponse` to the existing `from models.schemas import (...)` block. `datetime`/`timezone` are already imported in `main.py` (used throughout) — do not add a duplicate import; if a check shows they are NOT already imported at the top of the file, add `from datetime import datetime, timezone` there.

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_main_market_snapshot_endpoint.py -v`
Expected: PASS (4 tests)

- [ ] **Step 10: Run the full backend test suite to confirm zero regressions**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests -q`
Expected: same pre-existing failure count as before this task (the 5 Groq-API-key failures and the `test_purge_old_audit_history_uses_configured_default_when_no_argument_given` row-count failure, both already confirmed unrelated to any work this session) — no NEW failures.

- [ ] **Step 11: Commit**

```bash
git add backend/src/providers/coingecko_provider.py backend/src/tests/test_coingecko_provider.py backend/src/models/schemas.py backend/src/main.py backend/src/tests/test_main_market_snapshot_endpoint.py
git commit -m "$(cat <<'EOF'
feat: add CoinGecko BTC dominance provider and GET /market/snapshot

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Frontend data layer — types, API functions, hooks

**Files:**
- Modify: `web/src/api/types.ts` (append new types at end of file)
- Modify: `web/src/api/endpoints.ts` (add `marketApi.snapshot`, `newsApi.get`)
- Modify: `web/src/features/dashboard/hooks.ts` (add `useMarketSnapshot`)
- Modify: `web/src/features/asset/hooks.ts` (add `useAssetNews`)
- Test: `web/src/features/dashboard/hooks.test.ts` (create if it doesn't exist, or add to existing — check first), `web/src/features/asset/hooks.test.ts` (same check)

**Interfaces:**
- Consumes: Task 1's `GET /market/snapshot` (`MarketSnapshotResponse` JSON shape) and the already-existing `GET /news/{symbol}` (`core/news_analyzer.py::get_news_summary`'s exact return keys, confirmed during planning: `symbol, sector, market, total_news, analyzed_news, sentiment_score, sentiment_label, score_delta, positive_count, negative_count, neutral_count, signals, top_positive_title, top_negative_title, fetched_at, headlines, error`, where each `headlines` item is `{title, sentiment, score, age_weight, keywords, published_at}`).
- Produces (for Tasks 3-4): `marketApi.snapshot(): Promise<MarketSnapshotResponse>`; `newsApi.get(symbol: string): Promise<NewsSummaryResponse>`; `useMarketSnapshot()` (React Query hook); `useAssetNews(symbol: string)` (React Query hook).

- [ ] **Step 1: Add the new types to `web/src/api/types.ts`**

Append at the end of the file (after `ApiErrorBody`):

```typescript
// ── Market Snapshot (GET /market/snapshot) ─────────────────────────────

export interface MarketSnapshotResponse {
  bist100: ChartResponse | null
  btc: ChartResponse | null
  btc_dominance_pct: number | null
  generated_at: string
}

// ── News (GET /news/{symbol}) ───────────────────────────────────────────

export interface NewsHeadline {
  title: string
  sentiment: string
  score: number
  age_weight: number
  keywords: string[]
  published_at: string
}

export interface NewsSummaryResponse {
  symbol: string
  sector: string
  market: string
  total_news: number
  analyzed_news: number
  sentiment_score: number
  sentiment_label: string
  score_delta: number
  positive_count: number
  negative_count: number
  neutral_count: number
  signals: string[]
  top_positive_title: string | null
  top_negative_title: string | null
  fetched_at: string
  headlines: NewsHeadline[]
  error: string | null
}
```

- [ ] **Step 2: Add `marketApi` and `newsApi` to `web/src/api/endpoints.ts`**

Add `MarketSnapshotResponse` and `NewsSummaryResponse` to the existing `import type { ... } from './types'` block (alphabetical, matching the existing list's ordering convention). Add this new section after the existing `chartApi`/`quantApi` block (after line ~148):

```typescript
export const marketApi = {
  snapshot: () => apiClient.get<MarketSnapshotResponse>('/market/snapshot').then((r) => r.data),
}

export const newsApi = {
  get: (symbol: string) => apiClient.get<NewsSummaryResponse>(`/news/${encodeURIComponent(symbol)}`).then((r) => r.data),
}
```

- [ ] **Step 3: Write the failing test for `useMarketSnapshot`**

First check whether `web/src/features/dashboard/hooks.test.ts` already exists (`ls web/src/features/dashboard/hooks.test.ts`). If it exists, add this test to it; if not, create it with this content and the necessary imports mirrored from an existing hook test file (e.g. check `web/src/features/asset/` for a `hooks.test.ts` first, to match the established mocking pattern for this hooks file — use the same `vi.mock('../../api/endpoints', ...)` + `renderHook` + `QueryClientProvider` wrapper pattern already used in `MarketOverview.test.tsx` for mocking `dashboardApi`, adapted for a hook rather than a component):

```typescript
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useMarketSnapshot } from './hooks'
import { marketApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/endpoints')>()
  return { ...actual, marketApi: { snapshot: vi.fn() } }
})

const mockedMarketApi = vi.mocked(marketApi)

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useMarketSnapshot', () => {
  it('fetches the market snapshot', async () => {
    mockedMarketApi.snapshot.mockResolvedValueOnce({
      bist100: null, btc: null, btc_dominance_pct: 54.1, generated_at: '2026-01-01T00:00:00Z',
    })
    const { result } = renderHook(() => useMarketSnapshot(), { wrapper })
    await waitFor(() => expect(result.current.data?.btc_dominance_pct).toBe(54.1))
  })
})
```

If this new test file needs a `.tsx` extension instead of `.ts` to support JSX in `wrapper` (check the project's existing convention — `MarketOverview.test.tsx` uses `.tsx` for JSX; a pure-hook test file wrapping with JSX also needs `.tsx`), name it `hooks.test.tsx` instead of `hooks.test.ts`.

- [ ] **Step 4: Run test to verify it fails**

Run: `cd web && npm run test -- hooks.test --run` (or the exact path to the new test file)
Expected: FAIL — `useMarketSnapshot` is not exported from `./hooks` yet.

- [ ] **Step 5: Implement `useMarketSnapshot`**

Add to `web/src/features/dashboard/hooks.ts` (alongside the other hooks, using the same `STALE.scheduled` constant already defined there):

```typescript
export function useMarketSnapshot() {
  return useQuery({ queryKey: ['dashboard', 'market-snapshot'], queryFn: marketApi.snapshot, staleTime: STALE.scheduled })
}
```

Add `marketApi` to this file's existing `import { alertsApi, dashboardApi, portfolioApi, watchlistApi } from '../../api/endpoints'` line (alphabetical).

- [ ] **Step 6: Run test to verify it passes**

Run: `cd web && npm run test -- hooks.test --run`
Expected: PASS

- [ ] **Step 7: Write the failing test for `useAssetNews`**

Check whether `web/src/features/asset/hooks.test.ts`/`.tsx` already exists; if not, create it (same pattern as Step 3, mocking `newsApi` instead):

```typescript
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useAssetNews } from './hooks'
import { newsApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/endpoints')>()
  return { ...actual, newsApi: { get: vi.fn() } }
})

const mockedNewsApi = vi.mocked(newsApi)

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useAssetNews', () => {
  it('fetches news for the given symbol', async () => {
    mockedNewsApi.get.mockResolvedValueOnce({
      symbol: 'AAPL', sector: 'Technology', market: 'US', total_news: 1, analyzed_news: 1,
      sentiment_score: 0.5, sentiment_label: 'Positive', score_delta: 0, positive_count: 1,
      negative_count: 0, neutral_count: 0, signals: [], top_positive_title: 'Good news',
      top_negative_title: null, fetched_at: '2026-01-01T00:00:00Z',
      headlines: [{ title: 'Good news', sentiment: 'Positive', score: 0.5, age_weight: 1, keywords: [], published_at: '2026-01-01T00:00:00Z' }],
      error: null,
    })
    const { result } = renderHook(() => useAssetNews('AAPL'), { wrapper })
    await waitFor(() => expect(result.current.data?.headlines).toHaveLength(1))
  })
})
```

- [ ] **Step 8: Run test to verify it fails**

Run: `cd web && npm run test -- hooks.test --run`
Expected: FAIL — `useAssetNews` is not exported from `./hooks` yet.

- [ ] **Step 9: Implement `useAssetNews`**

Add to `web/src/features/asset/hooks.ts` (alongside `usePrice`/`useChart`):

```typescript
const NEWS_STALE_MS = 5 * 60_000

export function useAssetNews(symbol: string) {
  return useQuery({
    queryKey: ['asset', symbol, 'news'],
    queryFn: () => newsApi.get(symbol),
    staleTime: NEWS_STALE_MS,
  })
}
```

Add `newsApi` to this file's existing `import { chartApi, priceApi, quantApi, watchlistApi } from '../../api/endpoints'` line (alphabetical).

- [ ] **Step 10: Run test to verify it passes**

Run: `cd web && npm run test -- hooks.test --run`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add web/src/api/types.ts web/src/api/endpoints.ts web/src/features/dashboard/hooks.ts web/src/features/asset/hooks.ts web/src/features/dashboard/hooks.test.tsx web/src/features/asset/hooks.test.tsx
git commit -m "$(cat <<'EOF'
feat: add market snapshot and asset news data-layer hooks

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: New simplified home page

**Files:**
- Create: `web/src/features/market/IndexChart.tsx`, `IndexChart.module.css`, `IndexChart.test.tsx`
- Create: `web/src/features/market/DominanceFigure.tsx`, `DominanceFigure.module.css`, `DominanceFigure.test.tsx`
- Modify: `web/src/features/dashboard/sections/MarketOverview.tsx` → rename/move to `web/src/features/market/MarketSummary.tsx` (trim, don't rewrite from scratch)
- Modify: `web/src/features/dashboard/sections/MarketOverview.test.tsx` → rename/move to `web/src/features/market/MarketSummary.test.tsx`
- Create: `web/src/pages/MarketSnapshotPage.tsx`, `MarketSnapshotPage.module.css`, `MarketSnapshotPage.test.tsx`

**Interfaces:**
- Consumes: Task 2's `useMarketSnapshot()` (returns `{data?: MarketSnapshotResponse, isLoading, isError, error, refetch}`), `useMarketDashboard` (unchanged, already exists in `dashboard/hooks.ts`).
- Produces: `IndexChart({ title, chart, isLoading, isError, errorMessage }: {title: string; chart: ChartResponse | null; isLoading: boolean; isError: boolean; errorMessage?: string}) -> JSX.Element`; `DominanceFigure({ value, isLoading }: {value: number | null; isLoading: boolean}) -> JSX.Element`; `MarketSummary() -> JSX.Element` (no props — owns its own `useMarketDashboard` call, same as today's `MarketOverview`); `MarketSnapshotPage() -> JSX.Element` (no props, the new route element for `/`).

- [ ] **Step 1: Write the failing test for `IndexChart`**

```typescript
// web/src/features/market/IndexChart.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { IndexChart } from './IndexChart'
import type { ChartResponse } from '../../api/types'

const chart: ChartResponse = {
  symbol: 'BTC-USD', period: '3mo', change_pct: 5.2, high: 70000, low: 60000,
  points: [
    { date: '2026-01-01', close: 65000, volume: 1000, rsi: null },
    { date: '2026-01-02', close: 66000, volume: 1100, rsi: null },
  ],
}

describe('IndexChart', () => {
  it('shows a loading state', () => {
    render(<IndexChart title="Bitcoin" chart={null} isLoading isError={false} />)
    expect(screen.getByText('Bitcoin')).toBeInTheDocument()
  })

  it('shows an error state with the given message', () => {
    render(<IndexChart title="Bitcoin" chart={null} isLoading={false} isError errorMessage="network error" />)
    expect(screen.getByText('network error')).toBeInTheDocument()
  })

  it('renders the real chart data, including the change percentage', () => {
    render(<IndexChart title="Bitcoin" chart={chart} isLoading={false} isError={false} />)
    expect(screen.getByText('Bitcoin')).toBeInTheDocument()
    expect(screen.getByText('+5.20%')).toBeInTheDocument()
  })

  it('shows an unavailable state when chart is null and not loading/error', () => {
    render(<IndexChart title="Bitcoin" chart={null} isLoading={false} isError={false} />)
    expect(screen.getByText('unavailable')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm run test -- IndexChart.test --run`
Expected: FAIL — `./IndexChart` module doesn't exist yet.

- [ ] **Step 3: Implement `IndexChart`**

```typescript
// web/src/features/market/IndexChart.tsx
import { Area, AreaChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import { Card, CardHeader, CardTitle } from '../../components/ui/Card'
import { ChartContainer } from '../../components/ui/ChartContainer'
import { useChartColors } from '../../components/ui/useChartColors'
import type { ChartResponse } from '../../api/types'
import styles from './IndexChart.module.css'

interface IndexChartProps {
  title: string
  chart: ChartResponse | null
  isLoading: boolean
  isError: boolean
  errorMessage?: string
}

/**
 * A plain price-line chart for a single market-context index
 * (BIST100 or BTC) on the simplified home page. Reuses PriceChart's
 * own charting approach (AreaChart via recharts) rather than a new
 * charting pattern - just without the period tabs or RSI sub-chart,
 * since this is a fixed-period context chart, not the full asset
 * price history view.
 */
export function IndexChart({ title, chart, isLoading, isError, errorMessage }: IndexChartProps) {
  const colors = useChartColors()
  const points = chart?.points ?? []

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{title}</CardTitle>
          {chart ? (
            <span className={styles.changePct}>
              {chart.change_pct >= 0 ? '+' : ''}
              {chart.change_pct.toFixed(2)}%
            </span>
          ) : null}
        </div>
      </CardHeader>

      <ChartContainer
        label={`${title} price`}
        height={160}
        isLoading={isLoading}
        error={isError ? errorMessage ?? 'unavailable' : null}
        onRetry={() => undefined}
        isEmpty={!isLoading && !isError && points.length === 0}
        emptyTitle="unavailable"
        emptyDescription="This chart isn't available right now."
      >
        <AreaChart data={points}>
          <defs>
            <linearGradient id={`indexFill-${title}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={colors.accent} stopOpacity={0.25} />
              <stop offset="100%" stopColor={colors.accent} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} minTickGap={40} />
          <YAxis stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} width={56} domain={['auto', 'auto']} />
          <RechartsTooltip
            contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
            formatter={(value) => [Number(value).toLocaleString(), 'Close']}
          />
          <Area type="monotone" dataKey="close" stroke={colors.accent} strokeWidth={2} fill={`url(#indexFill-${title})`} />
        </AreaChart>
      </ChartContainer>
    </Card>
  )
}
```

Create `web/src/features/market/IndexChart.module.css` with one class:

```css
.changePct {
  font-size: 13px;
  color: var(--text-secondary);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm run test -- IndexChart.test --run`
Expected: PASS (4 tests)

- [ ] **Step 5: Write the failing test for `DominanceFigure`**

```typescript
// web/src/features/market/DominanceFigure.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DominanceFigure } from './DominanceFigure'

describe('DominanceFigure', () => {
  it('renders the real percentage when available', () => {
    render(<DominanceFigure value={54.3} isLoading={false} />)
    expect(screen.getByText('54.3%')).toBeInTheDocument()
  })

  it('shows "unavailable" rather than a fabricated number when value is null', () => {
    render(<DominanceFigure value={null} isLoading={false} />)
    expect(screen.getByText('unavailable')).toBeInTheDocument()
  })

  it('shows a loading state', () => {
    render(<DominanceFigure value={null} isLoading />)
    expect(screen.queryByText('unavailable')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd web && npm run test -- DominanceFigure.test --run`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 7: Implement `DominanceFigure`**

```typescript
// web/src/features/market/DominanceFigure.tsx
import { Card, CardHeader, CardTitle } from '../../components/ui/Card'
import { SkeletonCard } from '../../components/ui/Skeleton'
import styles from './DominanceFigure.module.css'

interface DominanceFigureProps {
  value: number | null
  isLoading: boolean
}

/**
 * The current BTC dominance percentage (BTC's share of total crypto
 * market cap), from GET /market/snapshot's btc_dominance_pct field -
 * a real CoinGecko figure, never fabricated. `value === null` means
 * the CoinGecko call failed this time; shown honestly as
 * "unavailable", never a stale or made-up number.
 */
export function DominanceFigure({ value, isLoading }: DominanceFigureProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>BTC Dominance</CardTitle>
      </CardHeader>
      {isLoading ? (
        <SkeletonCard />
      ) : (
        <p className={styles.value}>{value != null ? `${value.toFixed(1)}%` : 'unavailable'}</p>
      )}
    </Card>
  )
}
```

Create `web/src/features/market/DominanceFigure.module.css`:

```css
.value {
  font-size: 32px;
  font-weight: 600;
  margin: 8px 0 0;
}
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd web && npm run test -- DominanceFigure.test --run`
Expected: PASS (3 tests)

- [ ] **Step 9: Move and trim `MarketOverview` into `MarketSummary`**

Move `web/src/features/dashboard/sections/MarketOverview.module.css` to `web/src/features/market/MarketSummary.module.css` unchanged (`git mv`, no content edit — the `.viewAll` class becomes unused dead CSS, harmless). Replace `web/src/features/dashboard/sections/MarketOverview.tsx` with `web/src/features/market/MarketSummary.tsx` (new path, one directory shallower, so `../../../` becomes `../../`; the `Link`/`.viewAll` row is dropped since this is a context panel on the home page, not a navigation hub):

```typescript
// web/src/features/market/MarketSummary.tsx
import { Bar, BarChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { ChartContainer } from '../../components/ui/ChartContainer'
import { useChartColors } from '../../components/ui/useChartColors'
import { useMarketDashboard } from '../dashboard/hooks'
import { apiErrorMessage } from '../../api/client'
import styles from './MarketSummary.module.css'

function sentimentTone(label: string): 'positive' | 'negative' | 'neutral' {
  const lower = label.toLowerCase()
  if (lower.includes('pos') || lower.includes('bull')) return 'positive'
  if (lower.includes('neg') || lower.includes('bear')) return 'negative'
  return 'neutral'
}

/**
 * Backed by GET /dashboard/market (dashboard/models.py::MarketDashboardView).
 * A compact market-context summary for the simplified home page - a
 * trimmed version of the original MarketOverview (no "View all" link
 * to the Assets page, since this is a context panel, not a
 * navigation hub).
 */
export function MarketSummary() {
  const { data, isLoading, isError, error, refetch } = useMarketDashboard()
  const colors = useChartColors()

  const sectorData = [...(data?.sector_heatmap ?? [])]
    .sort((a, b) => b.opportunity_score - a.opportunity_score)
    .slice(0, 6)
  const news = data?.news_impact_summary.slice(0, 5) ?? []

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Market</CardTitle>
          <CardSubtitle>Sector opportunity &amp; news sentiment</CardSubtitle>
        </div>
      </CardHeader>

      <ChartContainer
        label="Top sectors by opportunity score"
        height={180}
        isLoading={isLoading}
        error={isError ? apiErrorMessage(error) : null}
        onRetry={() => void refetch()}
        isEmpty={sectorData.length === 0}
        emptyTitle="No sector data yet"
        emptyDescription="Sector opportunity scores will appear here once available."
      >
        <BarChart data={sectorData} layout="vertical" margin={{ left: 8, right: 24 }}>
          <XAxis type="number" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="sector" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} width={80} />
          <RechartsTooltip
            formatter={(value) => Number(value).toFixed(1)}
            contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
          />
          <Bar dataKey="opportunity_score" fill={colors.accent} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ChartContainer>

      {!isLoading && !isError && news.length > 0 ? (
        <div className={styles.newsSection}>
          <span className={styles.sectionLabel}>News sentiment</span>
          <ul className={styles.newsList}>
            {news.map((item) => (
              <li key={item.symbol} className={styles.newsRow}>
                <span className={`num ${styles.symbol}`}>{item.symbol}</span>
                <span className={styles.headlineCount}>{item.headline_count} headlines</span>
                <Badge tone={sentimentTone(item.sentiment_label)}>{item.sentiment_label}</Badge>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  )
}
```

Replace `web/src/features/dashboard/sections/MarketOverview.test.tsx` with `web/src/features/market/MarketSummary.test.tsx` (same move-one-level-shallower path fix; the third test, `'links to the full Assets page'`, is dropped since that link no longer exists):

```typescript
// web/src/features/market/MarketSummary.test.tsx
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MarketSummary } from './MarketSummary'
import { dashboardApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  dashboardApi: { market: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MarketSummary />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const marketView = {
  regime_distribution: { bull: 5 },
  volatility_map: { AAPL: 0.2 },
  sector_heatmap: [
    { sector: 'Technology', opportunity_score: 8.2, avg_change_pct: 1.4, trend: 'up' },
    { sector: 'Energy', opportunity_score: 3.1, avg_change_pct: -0.5, trend: 'down' },
  ],
  news_impact_summary: [{ symbol: 'AAPL', sentiment_score: 0.6, sentiment_label: 'Positive', headline_count: 12 }],
  generated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('MarketSummary', () => {
  it('shows an honest empty state when no sector data is available', async () => {
    mockedDashboardApi.market.mockResolvedValueOnce({ ...marketView, sector_heatmap: [], news_impact_summary: [] })
    renderWithClient()
    await waitFor(() => expect(screen.getByText('No sector data yet')).toBeInTheDocument())
  })

  it('renders real sector opportunity and news sentiment data, never a fabricated market status', async () => {
    mockedDashboardApi.market.mockResolvedValueOnce(marketView)
    renderWithClient()
    await waitFor(() => expect(screen.getByLabelText('Top sectors by opportunity score')).toBeInTheDocument())
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('12 headlines')).toBeInTheDocument()
    expect(screen.getByText('Positive')).toBeInTheDocument()
  })
})
```

- [ ] **Step 10: Run the moved test to verify it passes**

Run: `cd web && npm run test -- MarketSummary.test --run`
Expected: PASS (2 tests)

- [ ] **Step 11: Write the failing test for `MarketSnapshotPage`**

```typescript
// web/src/pages/MarketSnapshotPage.test.tsx
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { MarketSnapshotPage } from './MarketSnapshotPage'
import { marketApi, dashboardApi } from '../api/endpoints'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/endpoints')>()
  return { ...actual, marketApi: { snapshot: vi.fn() }, dashboardApi: { ...actual.dashboardApi, market: vi.fn() } }
})

const mockedMarketApi = vi.mocked(marketApi)
const mockedDashboardApi = vi.mocked(dashboardApi)

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MarketSnapshotPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedDashboardApi.market.mockResolvedValue({
    regime_distribution: {}, volatility_map: {}, sector_heatmap: [], news_impact_summary: [], generated_at: '2026-01-01T00:00:00Z',
  })
})

describe('MarketSnapshotPage', () => {
  it('renders both index charts and the dominance figure', async () => {
    mockedMarketApi.snapshot.mockResolvedValueOnce({
      bist100: { symbol: 'XU100.IS', period: '3mo', change_pct: 1.1, high: 100, low: 90, points: [] },
      btc: { symbol: 'BTC-USD', period: '3mo', change_pct: 2.2, high: 70000, low: 60000, points: [] },
      btc_dominance_pct: 54.3,
      generated_at: '2026-01-01T00:00:00Z',
    })
    renderPage()
    await waitFor(() => expect(screen.getByText('BTC Dominance')).toBeInTheDocument())
    expect(screen.getByText('54.3%')).toBeInTheDocument()
  })
})
```

- [ ] **Step 12: Run test to verify it fails**

Run: `cd web && npm run test -- MarketSnapshotPage.test --run`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 13: Implement `MarketSnapshotPage`**

```typescript
// web/src/pages/MarketSnapshotPage.tsx
import { apiErrorMessage } from '../api/client'
import { useMarketSnapshot } from '../features/dashboard/hooks'
import { IndexChart } from '../features/market/IndexChart'
import { DominanceFigure } from '../features/market/DominanceFigure'
import { MarketSummary } from '../features/market/MarketSummary'
import styles from './MarketSnapshotPage.module.css'

export function MarketSnapshotPage() {
  const snapshot = useMarketSnapshot()

  return (
    <div className={styles.page}>
      <div className={styles.chartsRow}>
        <IndexChart
          title="BIST 100"
          chart={snapshot.data?.bist100 ?? null}
          isLoading={snapshot.isLoading}
          isError={snapshot.isError}
          errorMessage={snapshot.isError ? apiErrorMessage(snapshot.error) : undefined}
        />
        <IndexChart
          title="Bitcoin"
          chart={snapshot.data?.btc ?? null}
          isLoading={snapshot.isLoading}
          isError={snapshot.isError}
          errorMessage={snapshot.isError ? apiErrorMessage(snapshot.error) : undefined}
        />
        <DominanceFigure value={snapshot.data?.btc_dominance_pct ?? null} isLoading={snapshot.isLoading} />
      </div>

      <MarketSummary />
    </div>
  )
}
```

Create `web/src/pages/MarketSnapshotPage.module.css`:

```css
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chartsRow {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 16px;
}
```

- [ ] **Step 14: Run test to verify it passes**

Run: `cd web && npm run test -- MarketSnapshotPage.test --run`
Expected: PASS

- [ ] **Step 15: Commit**

```bash
git add web/src/features/market/ web/src/pages/MarketSnapshotPage.tsx web/src/pages/MarketSnapshotPage.module.css web/src/pages/MarketSnapshotPage.test.tsx
git rm web/src/features/dashboard/sections/MarketOverview.tsx web/src/features/dashboard/sections/MarketOverview.module.css web/src/features/dashboard/sections/MarketOverview.test.tsx
git commit -m "$(cat <<'EOF'
feat: add simplified market snapshot home page

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Simplify the asset detail page

**Files:**
- Modify: `web/src/features/asset/PriceChart.tsx` (add volume sub-chart)
- Modify: `web/src/features/asset/PriceChart.test.tsx` (add volume-chart test)
- Create: `web/src/features/asset/Recommendation.tsx`, `Recommendation.module.css`, `Recommendation.test.tsx`
- Create: `web/src/features/asset/AssetNews.tsx`, `AssetNews.module.css`, `AssetNews.test.tsx`
- Modify: `web/src/pages/AssetDetailPage.tsx`
- Modify: `web/src/pages/AssetDetailPage.test.tsx`

**Interfaces:**
- Consumes: Task 2's `useAssetNews(symbol)`; existing `PipelineResponse` (`decision`, `confidence`, `explanation` fields — unchanged); existing `ChartResponse.points[].volume` (already present, unused until now).
- Produces: `Recommendation({ data, isPending, isError, errorMessage, onAnalyze }) -> JSX.Element` (same prop shape as the `QuantDecision` it replaces, for a drop-in swap in `AssetDetailPage`); `AssetNews({ news, isLoading, isError, errorMessage }: {news?: NewsSummaryResponse; isLoading: boolean; isError: boolean; errorMessage?: string}) -> JSX.Element`.

- [ ] **Step 1: Write the failing test for `PriceChart`'s new volume sub-chart**

Add to `web/src/features/asset/PriceChart.test.tsx` (check this file's current content first — if it doesn't exist yet, create it with this plus a basic smoke test mirroring `QuantDecision.test.tsx`'s render pattern):

```typescript
it('renders a volume sub-chart from the real chart data', () => {
  const chart = {
    symbol: 'AAPL', period: '3mo', change_pct: 1.5, high: 200, low: 150,
    points: [
      { date: '2026-01-01', close: 180, volume: 1_200_000, rsi: null },
      { date: '2026-01-02', close: 182, volume: 1_500_000, rsi: null },
    ],
  }
  render(
    <PriceChart chart={chart} isLoading={false} isError={false} onRetry={vi.fn()} period="3mo" onPeriodChange={vi.fn()} />,
  )
  expect(screen.getByLabelText('AAPL volume, 3mo')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm run test -- PriceChart.test --run`
Expected: FAIL — no element with that `aria-label` exists yet.

- [ ] **Step 3: Add the volume sub-chart to `PriceChart`**

In `web/src/features/asset/PriceChart.tsx`, add `Bar, BarChart` to the existing `import { Area, AreaChart, Line, LineChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'` line. After the existing RSI section (the `{hasRsi ? (...) : null}` block, ending at the current line 99, just before the closing `</Card>`), add:

```typescript
      <div className={styles.volumeSection}>
        <span className={styles.rsiLabel}>Volume</span>
        <ChartContainer label={`${chart?.symbol ?? ''} volume, ${period}`} height={90} isEmpty={false}>
          <BarChart data={points}>
            <XAxis dataKey="date" hide />
            <YAxis hide />
            <RechartsTooltip
              contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
              formatter={(value) => [Number(value).toLocaleString(), 'Volume']}
            />
            <Bar dataKey="volume" fill={colors.textSecondary} radius={[2, 2, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </div>
```

Reuse the existing `.rsiLabel` CSS class for the new `volumeSection`'s label (add a `.volumeSection { margin-top: 12px; }` rule to `PriceChart.module.css`, mirroring the existing `.rsiSection` rule there).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm run test -- PriceChart.test --run`
Expected: PASS

- [ ] **Step 5: Write the failing tests for `Recommendation`**

```typescript
// web/src/features/asset/Recommendation.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Recommendation } from './Recommendation'
import type { PipelineResponse } from '../../api/types'

const response: PipelineResponse = {
  symbol: 'AAPL', decision: 'BUY', confidence: 0.72, expected_return: 0.034, expected_volatility: 0.18,
  engine_breakdown: [], evidence: ['Aggregate confidence above threshold'],
  risk: { risk_level: 'MEDIUM', expected_volatility: 0.18, data_sufficiency: 0.9 },
  explanation: 'Technical momentum outweighs neutral fundamentals.',
  metadata: { pipeline_version: '1.0.0', total_duration_ms: 120, stage_durations_ms: {}, engines_available: 3, engines_succeeded: 2, degraded: true, timestamp: '2026-01-01T20:00:00Z' },
}

describe('Recommendation', () => {
  it('prompts the user to run the analysis when nothing has happened yet', () => {
    render(<Recommendation isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Analyze' })).toBeInTheDocument()
  })

  it('renders the real decision and the plain-language explanation, with no engine jargon', () => {
    render(<Recommendation data={response} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('BUY')).toBeInTheDocument()
    expect(screen.getByText('Technical momentum outweighs neutral fundamentals.')).toBeInTheDocument()
    expect(screen.queryByText(/engines succeeded/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Expected return/)).not.toBeInTheDocument()
  })

  it('maps confidence 0.72 to "Yüksek güven"', () => {
    render(<Recommendation data={{ ...response, confidence: 0.72 }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('Yüksek güven')).toBeInTheDocument()
  })

  it('maps confidence exactly 0.66 to "Yüksek güven" (boundary, inclusive)', () => {
    render(<Recommendation data={{ ...response, confidence: 0.66 }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('Yüksek güven')).toBeInTheDocument()
  })

  it('maps confidence 0.65 to "Orta güven" (just below the high boundary)', () => {
    render(<Recommendation data={{ ...response, confidence: 0.65 }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('Orta güven')).toBeInTheDocument()
  })

  it('maps confidence exactly 0.33 to "Orta güven" (boundary, inclusive)', () => {
    render(<Recommendation data={{ ...response, confidence: 0.33 }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('Orta güven')).toBeInTheDocument()
  })

  it('maps confidence 0.32 to "Düşük güven" (just below the mid boundary)', () => {
    render(<Recommendation data={{ ...response, confidence: 0.32 }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('Düşük güven')).toBeInTheDocument()
  })

  it('shows a HOLD decision with neutral treatment', () => {
    render(<Recommendation data={{ ...response, decision: 'HOLD' }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('HOLD')).toBeInTheDocument()
  })
})
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd web && npm run test -- Recommendation.test --run`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 7: Implement `Recommendation`**

```typescript
// web/src/features/asset/Recommendation.tsx
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card, CardHeader, CardTitle } from '../../components/ui/Card'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import type { PipelineResponse, Prediction } from '../../api/types'
import styles from './Recommendation.module.css'

const DECISION_TONE: Record<Prediction, 'positive' | 'negative' | 'neutral'> = {
  BUY: 'positive',
  SELL: 'negative',
  HOLD: 'neutral',
}

/** Exact thresholds per this plan's Global Constraints - used verbatim,
 * nowhere else re-derived. */
function confidenceWord(confidence: number): string {
  if (confidence >= 0.66) return 'Yüksek güven'
  if (confidence >= 0.33) return 'Orta güven'
  return 'Düşük güven'
}

interface RecommendationProps {
  data?: PipelineResponse
  isPending: boolean
  isError: boolean
  errorMessage?: string
  onAnalyze: () => void
}

/**
 * Backed entirely by POST /quant/analyze (pipeline/models.py::
 * PipelineResponse), same as the QuantDecision/EngineBreakdown/
 * RiskPanel/ExplanationPanel components this replaces - but shows only
 * `decision`, `explanation` (already plain-language - see
 * ExplanationPanel's own prior docstring), and confidence mapped to a
 * plain word via confidenceWord(). No engine names, no raw confidence
 * %, no expected return/volatility, no "N/M engines succeeded", no
 * evidence list - nothing here is fabricated, every value shown is
 * already in the real response.
 */
export function Recommendation({ data, isPending, isError, errorMessage, onAnalyze }: RecommendationProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recommendation</CardTitle>
        <Button size="sm" onClick={onAnalyze} isLoading={isPending} disabled={isPending}>
          {data ? 'Refresh analysis' : 'Analyze'}
        </Button>
      </CardHeader>

      {isPending && !data ? <SkeletonCard /> : null}

      {isError && !data ? <ErrorState message={errorMessage ?? "Couldn't run the analysis"} onRetry={onAnalyze} /> : null}

      {!isPending && !data && !isError ? (
        <p className={styles.prompt}>Run the analysis to see a recommendation for this symbol.</p>
      ) : null}

      {data ? (
        <div className={styles.body}>
          <div className={styles.row}>
            <Badge tone={DECISION_TONE[data.decision]} className={styles.badge}>
              {data.decision}
            </Badge>
            <span className={styles.confidence}>{confidenceWord(data.confidence)}</span>
          </div>
          {data.explanation ? <p className={styles.explanation}>{data.explanation}</p> : null}
          {isError ? <p className={styles.staleNote}>The last refresh failed - showing the previous result above.</p> : null}
        </div>
      ) : null}
    </Card>
  )
}
```

Create `web/src/features/asset/Recommendation.module.css`:

```css
.prompt {
  color: var(--text-secondary);
  padding: 16px 0;
}

.body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.badge {
  font-size: 14px;
}

.confidence {
  color: var(--text-secondary);
  font-size: 13px;
}

.explanation {
  margin: 0;
  line-height: 1.5;
}

.staleNote {
  color: var(--text-secondary);
  font-size: 12px;
  margin: 0;
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd web && npm run test -- Recommendation.test --run`
Expected: PASS (8 tests)

- [ ] **Step 9: Write the failing tests for `AssetNews`**

```typescript
// web/src/features/asset/AssetNews.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AssetNews } from './AssetNews'
import type { NewsSummaryResponse } from '../../api/types'

const news: NewsSummaryResponse = {
  symbol: 'AAPL', sector: 'Technology', market: 'US', total_news: 2, analyzed_news: 2,
  sentiment_score: 0.4, sentiment_label: 'Positive', score_delta: 0.1, positive_count: 2,
  negative_count: 0, neutral_count: 0, signals: [], top_positive_title: 'Great quarter', top_negative_title: null,
  fetched_at: '2026-01-01T00:00:00Z',
  headlines: [
    { title: 'Great quarter', sentiment: 'Positive', score: 0.6, age_weight: 1, keywords: [], published_at: '2026-01-01T00:00:00Z' },
    { title: 'New product launch', sentiment: 'Positive', score: 0.3, age_weight: 0.8, keywords: [], published_at: '2025-12-30T00:00:00Z' },
  ],
  error: null,
}

describe('AssetNews', () => {
  it('shows a loading state', () => {
    render(<AssetNews isLoading isError={false} />)
    expect(screen.getByText('News')).toBeInTheDocument()
  })

  it('shows a clean "no news" state for an empty headlines list', () => {
    render(<AssetNews news={{ ...news, headlines: [] }} isLoading={false} isError={false} />)
    expect(screen.getByText('No recent news for this symbol.')).toBeInTheDocument()
  })

  it('renders real headlines with sentiment, never fabricated ones', () => {
    render(<AssetNews news={news} isLoading={false} isError={false} />)
    expect(screen.getByText('Great quarter')).toBeInTheDocument()
    expect(screen.getByText('New product launch')).toBeInTheDocument()
    expect(screen.getAllByText('Positive')).toHaveLength(2)
  })

  it('shows a retryable error state', () => {
    render(<AssetNews isLoading={false} isError errorMessage="network error" />)
    expect(screen.getByText('network error')).toBeInTheDocument()
  })
})
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `cd web && npm run test -- AssetNews.test --run`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 11: Implement `AssetNews`**

```typescript
// web/src/features/asset/AssetNews.tsx
import { Badge } from '../../components/ui/Badge'
import { Card, CardHeader, CardTitle } from '../../components/ui/Card'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import type { NewsSummaryResponse } from '../../api/types'
import styles from './AssetNews.module.css'

function sentimentTone(label: string): 'positive' | 'negative' | 'neutral' {
  const lower = label.toLowerCase()
  if (lower.includes('pos') || lower.includes('bull')) return 'positive'
  if (lower.includes('neg') || lower.includes('bear')) return 'negative'
  return 'neutral'
}

interface AssetNewsProps {
  news?: NewsSummaryResponse
  isLoading: boolean
  isError: boolean
  errorMessage?: string
}

/**
 * Backed entirely by GET /news/{symbol} (core/news_analyzer.py::
 * get_news_summary) - a real, already-existing endpoint never called
 * from the frontend until now. Shows up to 5 real headlines with
 * their real sentiment label; raw score/age_weight/keywords fields
 * are not displayed.
 */
export function AssetNews({ news, isLoading, isError, errorMessage }: AssetNewsProps) {
  const headlines = news?.headlines.slice(0, 5) ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle>News</CardTitle>
      </CardHeader>

      {isLoading ? <SkeletonCard /> : null}
      {isError ? <ErrorState message={errorMessage ?? "Couldn't load news"} onRetry={() => undefined} /> : null}

      {!isLoading && !isError && headlines.length === 0 ? (
        <p className={styles.empty}>No recent news for this symbol.</p>
      ) : null}

      {!isLoading && !isError && headlines.length > 0 ? (
        <ul className={styles.list}>
          {headlines.map((item, index) => (
            <li key={index} className={styles.row}>
              <span className={styles.title}>{item.title}</span>
              <Badge tone={sentimentTone(item.sentiment)}>{item.sentiment}</Badge>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  )
}
```

Create `web/src/features/asset/AssetNews.module.css`:

```css
.empty {
  color: var(--text-secondary);
  padding: 16px 0;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.title {
  font-size: 13px;
}
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `cd web && npm run test -- AssetNews.test --run`
Expected: PASS (4 tests)

- [ ] **Step 13: Wire `Recommendation` and `AssetNews` into `AssetDetailPage`, remove the old 4 components**

Replace the full content of `web/src/pages/AssetDetailPage.tsx` with:

```typescript
import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { EmptyState } from '../components/ui/EmptyState'
import { apiErrorMessage, isNotFoundError } from '../api/client'
import { useChart, usePrice, useQuantAnalyze, useAssetWatchlistState, useAssetNews } from '../features/asset/hooks'
import { AssetHeader } from '../features/asset/AssetHeader'
import { PriceChart } from '../features/asset/PriceChart'
import { Recommendation } from '../features/asset/Recommendation'
import { AssetNews } from '../features/asset/AssetNews'
import type { ChartPeriod } from '../api/types'
import styles from './AssetDetailPage.module.css'

/**
 * /assets/:symbol - the canonical asset page every symbol link in the
 * app points to. `symbol` comes only from the URL, never hardcoded.
 * If GET /price/{symbol} 404s, the backend has no market data for it
 * at all - treated as "unknown symbol" for the whole page.
 */
export function AssetDetailPage() {
  const { symbol = '' } = useParams<{ symbol: string }>()
  const normalizedSymbol = symbol.toUpperCase()
  const [period, setPeriod] = useState<ChartPeriod>('3mo')

  const price = usePrice(normalizedSymbol)
  const chart = useChart(normalizedSymbol, period)
  const quant = useQuantAnalyze(normalizedSymbol)
  const watchlist = useAssetWatchlistState(normalizedSymbol)
  const news = useAssetNews(normalizedSymbol)

  const autoRunSymbol = useRef<string | null>(null)
  useEffect(() => {
    if (price.isSuccess && autoRunSymbol.current !== normalizedSymbol) {
      autoRunSymbol.current = normalizedSymbol
      quant.mutate()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalizedSymbol, price.isSuccess])

  function refreshAll() {
    void price.refetch()
    void chart.refetch()
  }

  if (price.isError && isNotFoundError(price.error)) {
    return (
      <div className={styles.page}>
        <EmptyState
          variant="unavailable"
          title={`"${normalizedSymbol}" not found`}
          description="The backend has no market data for this symbol."
        />
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <AssetHeader
        symbol={normalizedSymbol}
        price={price.data}
        isLoading={price.isLoading}
        isError={price.isError}
        errorMessage={price.isError ? apiErrorMessage(price.error) : undefined}
        onRetry={() => void price.refetch()}
        onRefresh={refreshAll}
        isRefreshing={price.isFetching || chart.isFetching}
        watchlist={watchlist}
      />

      <div className={styles.grid}>
        <div className={styles.chart}>
          <PriceChart
            chart={chart.data}
            isLoading={chart.isLoading}
            isError={chart.isError}
            errorMessage={chart.isError ? apiErrorMessage(chart.error) : undefined}
            onRetry={() => void chart.refetch()}
            period={period}
            onPeriodChange={setPeriod}
          />
        </div>

        <div className={styles.recommendation}>
          <Recommendation
            data={quant.data}
            isPending={quant.isPending}
            isError={quant.isError}
            errorMessage={quant.isError ? apiErrorMessage(quant.error) : undefined}
            onAnalyze={() => quant.mutate()}
          />
        </div>

        <div className={styles.news}>
          <AssetNews
            news={news.data}
            isLoading={news.isLoading}
            isError={news.isError}
            errorMessage={news.isError ? apiErrorMessage(news.error) : undefined}
          />
        </div>
      </div>
    </div>
  )
}
```

In `web/src/pages/AssetDetailPage.module.css`, remove the `.decision`, `.engines`, `.risk`, `.explanation` grid-area rules and add `.recommendation`/`.news` ones in their place (same grid structure, 2 fewer cells).

- [ ] **Step 14: Update `AssetDetailPage.test.tsx`**

`AssetDetailPage.test.tsx` doesn't reference `QuantDecision`/`EngineBreakdown`/`RiskPanel`/`ExplanationPanel` by name at all (it only asserts against the rendered output of whatever `AssetDetailPage` composes), so no import changes are needed there. The only required change is adding a mock for the new `newsApi.get` call this page now makes (via `useAssetNews`), since the existing `vi.mock('../api/endpoints', ...)` factory (lines 10-15) replaces the whole module and currently has no `newsApi` key — every test in this file would otherwise fail with "newsApi.get is not a function."

Replace lines 8-20 (the imports, mock factory, and `mocked*` consts) with:

```typescript
import { chartApi, priceApi, quantApi, watchlistApi, newsApi } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  priceApi: { get: vi.fn() },
  chartApi: { get: vi.fn() },
  quantApi: { analyze: vi.fn() },
  watchlistApi: { list: vi.fn(), items: vi.fn(), addItem: vi.fn(), removeItem: vi.fn() },
  newsApi: { get: vi.fn() },
}))

const mockedPriceApi = vi.mocked(priceApi)
const mockedChartApi = vi.mocked(chartApi)
const mockedQuantApi = vi.mocked(quantApi)
const mockedWatchlistApi = vi.mocked(watchlistApi)
const mockedNewsApi = vi.mocked(newsApi)
```

Add a `newsResponse` fixture alongside the existing `pipelineResponse`/`watchlist` consts (after line 64):

```typescript
const newsResponse = {
  symbol: 'AAPL', sector: 'Technology', market: 'US', total_news: 0, analyzed_news: 0,
  sentiment_score: 0, sentiment_label: 'Neutral', score_delta: 0, positive_count: 0,
  negative_count: 0, neutral_count: 0, signals: [], top_positive_title: null, top_negative_title: null,
  fetched_at: '2026-01-01T00:00:00Z', headlines: [], error: null,
}
```

In the `beforeEach` block (currently lines 72-78), add one line so every test in this file gets a resolved (not pending) news response by default:

```typescript
beforeEach(() => {
  vi.clearAllMocks()
  mockedChartApi.get.mockResolvedValue(chartResponse)
  mockedQuantApi.analyze.mockResolvedValue(pipelineResponse)
  mockedWatchlistApi.list.mockResolvedValue([watchlist])
  mockedWatchlistApi.items.mockResolvedValue([])
  mockedNewsApi.get.mockResolvedValue(newsResponse)
})
```

No other test in this file needs to change: none of the 7 existing tests assert on `QuantDecision`/`EngineBreakdown`/`RiskPanel`/`ExplanationPanel`-specific text (they assert `'BUY'`, `'189.5'`, `'Price history'`, button names, watchlist state — all still true verbatim with `Recommendation` in place, since `Recommendation` also renders `data.decision` as plain text `'BUY'`). The test at line 125 (`'Refresh re-fetches price and chart'`) clicks the button named `'Refresh'` — this still resolves unambiguously to `AssetHeader`'s refresh button, since `Recommendation`'s own button is named `'Analyze'`/`'Refresh analysis'` (Step 7's exact text), not `'Refresh'` — confirmed no collision.

- [ ] **Step 15: Delete the 4 replaced components**

```bash
git rm web/src/features/asset/QuantDecision.tsx web/src/features/asset/QuantDecision.module.css web/src/features/asset/QuantDecision.test.tsx
git rm web/src/features/asset/EngineBreakdown.tsx web/src/features/asset/EngineBreakdown.module.css web/src/features/asset/EngineBreakdown.test.tsx
git rm web/src/features/asset/RiskPanel.tsx web/src/features/asset/RiskPanel.module.css web/src/features/asset/RiskPanel.test.tsx
git rm web/src/features/asset/ExplanationPanel.tsx web/src/features/asset/ExplanationPanel.module.css web/src/features/asset/ExplanationPanel.test.tsx
```

(These 4 components' only other importers — `DecisionsPage.tsx` and `AnalystPage.tsx` — are deleted in Task 5; until Task 5 runs, those two files will fail to typecheck. This task's own test run below only exercises `web/src/features/asset/` and `AssetDetailPage` in isolation via Vitest, which does not typecheck the whole project, so this is expected and resolved by Task 5 — do not attempt to fix `DecisionsPage.tsx`/`AnalystPage.tsx` in this task.)

- [ ] **Step 16: Run the asset-feature and page tests to verify they pass**

Run: `cd web && npm run test -- AssetDetailPage.test PriceChart.test Recommendation.test AssetNews.test --run`
Expected: PASS (full typecheck/build happens in Task 5, after `DecisionsPage`/`AnalystPage` are also removed)

- [ ] **Step 17: Commit**

```bash
git add -A web/src/features/asset/ web/src/pages/AssetDetailPage.tsx web/src/pages/AssetDetailPage.module.css web/src/pages/AssetDetailPage.test.tsx
git commit -m "$(cat <<'EOF'
feat: simplify asset detail page - volume chart, plain recommendation, real news

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Remove Portfolio/AI-Analyst/Learning/Research/Decisions/old-Dashboard, update nav/routes, verify the build

**Files:**
- Delete: `web/src/features/portfolio/` (entire directory), `web/src/features/learning/` (entire directory), `web/src/features/dashboard/sections/` (all remaining files — `DashboardKpis.*`, `PortfolioPerformance.*`, `EngineIntelligence.*`, `RecentDecisions.*`, `LearningOverview.*`, `WatchlistIntelligence.*`, `AlertsOverview.*` — `MarketOverview.*` was already moved in Task 3), `web/src/features/decision/` (entire directory — `DecisionHeader.*`, `SymbolPicker.*`, `SystemEngineStatus.*`, `HistoricalDecisionsUnavailable.*`)
- Delete: `web/src/pages/PortfolioPage.*`, `AnalystPage.*`, `LearningPage.*`, `ResearchPage.*`, `DecisionsPage.*`, `DashboardPage.*` (each `.tsx`/`.module.css`/`.test.tsx` trio)
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/layout/nav.ts`
- Modify: `web/src/App.test.tsx` (check its current content for references to removed routes)

**Interfaces:**
- Consumes: Task 3's `MarketSnapshotPage` (replaces `DashboardPage` at route `/`).
- Produces: a trimmed `App.tsx` with exactly 5 authenticated routes (`/`, `/watchlist`, `/assets`, `/assets/:symbol`, `/alerts`) plus `/login`/`/register`/the catch-all; a trimmed `NAV_ITEMS` array.

- [ ] **Step 1: Confirm no other importer depends on anything about to be deleted**

Run these checks (from `web/`) and confirm each returns ONLY files that are themselves being deleted in this task or were already deleted in earlier tasks:

```bash
grep -rl "features/portfolio\|PortfolioPage" src --include="*.tsx" --include="*.ts" | grep -v -E "PortfolioPerformance|portfolioApi|usePortfolioList|usePortfolioDashboard"
grep -rl "features/learning\|LearningPage" src --include="*.tsx" --include="*.ts"
grep -rl "AnalystPage\|ResearchPage\|DecisionsPage\|DashboardPage" src --include="*.tsx" --include="*.ts"
grep -rl "features/decision/" src --include="*.tsx" --include="*.ts"
```

**Critical check — do NOT delete these:** confirm `web/src/features/dashboard/hooks.ts` (`usePortfolioList`, `usePortfolioDashboard`) and `web/src/api/endpoints.ts`'s `portfolioApi` are NOT in your deletion list — `web/src/features/alerts/CreateAlertForm.tsx` depends on `usePortfolioList` for its portfolio-type alert, and Alerts must stay functionally unchanged per this plan's Global Constraints. Only `web/src/features/portfolio/` (the directory) and `PortfolioPage.*` are deleted; `dashboard/hooks.ts` and `api/endpoints.ts` are **modified only by Task 2's earlier additions**, never touched by this deletion.

- [ ] **Step 2: Delete the feature directories and pages**

```bash
git rm -r web/src/features/portfolio
git rm -r web/src/features/learning
git rm -r web/src/features/decision
git rm web/src/features/dashboard/sections/DashboardKpis.tsx web/src/features/dashboard/sections/DashboardKpis.module.css web/src/features/dashboard/sections/DashboardKpis.test.tsx
git rm web/src/features/dashboard/sections/PortfolioPerformance.tsx web/src/features/dashboard/sections/PortfolioPerformance.module.css web/src/features/dashboard/sections/PortfolioPerformance.test.tsx
git rm web/src/features/dashboard/sections/EngineIntelligence.tsx web/src/features/dashboard/sections/EngineIntelligence.module.css web/src/features/dashboard/sections/EngineIntelligence.test.tsx
git rm web/src/features/dashboard/sections/RecentDecisions.tsx web/src/features/dashboard/sections/RecentDecisions.module.css web/src/features/dashboard/sections/RecentDecisions.test.tsx
git rm web/src/features/dashboard/sections/LearningOverview.tsx web/src/features/dashboard/sections/LearningOverview.module.css web/src/features/dashboard/sections/LearningOverview.test.tsx
git rm web/src/features/dashboard/sections/WatchlistIntelligence.tsx web/src/features/dashboard/sections/WatchlistIntelligence.module.css web/src/features/dashboard/sections/WatchlistIntelligence.test.tsx
git rm web/src/features/dashboard/sections/AlertsOverview.tsx web/src/features/dashboard/sections/AlertsOverview.module.css web/src/features/dashboard/sections/AlertsOverview.test.tsx
git rm web/src/pages/PortfolioPage.tsx web/src/pages/PortfolioPage.module.css web/src/pages/PortfolioPage.test.tsx
git rm web/src/pages/AnalystPage.tsx web/src/pages/AnalystPage.module.css web/src/pages/AnalystPage.test.tsx
git rm web/src/pages/LearningPage.tsx web/src/pages/LearningPage.module.css web/src/pages/LearningPage.test.tsx
git rm web/src/pages/ResearchPage.tsx web/src/pages/ResearchPage.module.css web/src/pages/ResearchPage.test.tsx
git rm web/src/pages/DecisionsPage.tsx web/src/pages/DecisionsPage.module.css web/src/pages/DecisionsPage.test.tsx
git rm web/src/pages/DashboardPage.tsx web/src/pages/DashboardPage.module.css
```

(`DashboardPage.test.tsx` — check if it exists; the earlier file listing during planning did not show one, so it may not exist. If `ls web/src/pages/DashboardPage.test.tsx` shows a file, `git rm` it too.)

- [ ] **Step 3: Update `web/src/App.tsx`**

Replace the full content with:

```typescript
import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { AppShell } from './components/layout/AppShell'
import { FullPageSpinner } from './components/ui/FullPageSpinner'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'

// Route-level code splitting: MarketSnapshotPage pulls in recharts, by
// far the heaviest dependency in this app - no reason to make /login
// pay for it. Every other authenticated page splits the same way.
const MarketSnapshotPage = lazy(() => import('./pages/MarketSnapshotPage').then((m) => ({ default: m.MarketSnapshotPage })))
const WatchlistPage = lazy(() => import('./pages/WatchlistPage').then((m) => ({ default: m.WatchlistPage })))
const AssetsPage = lazy(() => import('./pages/AssetsPage').then((m) => ({ default: m.AssetsPage })))
const AssetDetailPage = lazy(() => import('./pages/AssetDetailPage').then((m) => ({ default: m.AssetDetailPage })))
const AlertsPage = lazy(() => import('./pages/AlertsPage').then((m) => ({ default: m.AlertsPage })))

function Shell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <ProtectedRoute>
      <AppShell title={title}>
        <Suspense fallback={<FullPageSpinner />}>{children}</Suspense>
      </AppShell>
    </ProtectedRoute>
  )
}

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        <Route
          path="/"
          element={
            <Shell title="Market">
              <MarketSnapshotPage />
            </Shell>
          }
        />
        <Route
          path="/watchlist"
          element={
            <Shell title="Watchlist">
              <WatchlistPage />
            </Shell>
          }
        />
        <Route
          path="/assets"
          element={
            <Shell title="Assets">
              <AssetsPage />
            </Shell>
          }
        />
        <Route
          path="/assets/:symbol"
          element={
            <Shell title="Asset">
              <AssetDetailPage />
            </Shell>
          }
        />
        <Route
          path="/alerts"
          element={
            <Shell title="Alerts">
              <AlertsPage />
            </Shell>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
```

- [ ] **Step 4: Update `web/src/components/layout/nav.ts`**

Replace the `NAV_ITEMS` array with:

```typescript
export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Market', available: true },
  { to: '/watchlist', label: 'Watchlist', available: true },
  { to: '/assets', label: 'Assets', available: true },
  { to: '/alerts', label: 'Alerts', available: true },
]
```

- [ ] **Step 5: Fix `App.test.tsx`**

`web/src/App.test.tsx` contains only unauthenticated-redirect smoke tests (no page content is ever asserted, since `AuthProvider` redirects to `/login` before any protected page mounts) — so no test actually breaks: `renderAppAt('/portfolio')`'s assertion (`'Sign in'` button appears) still holds, since `/portfolio` is now simply unmatched and falls through the same catch-all → `/` → `/login` redirect chain as any other unknown path. The one change needed is cosmetic accuracy, not a fix: the test named `'redirects an unauthenticated visitor from a protected route to /login'` (currently testing `/portfolio`, a route this task removes) should test a route that still genuinely is a dedicated protected route, so its name stays true. Change line 45 from `renderAppAt('/portfolio')` to `renderAppAt('/watchlist')` — `/watchlist` remains a real protected route after this task's changes, and the test's existing assertion and surrounding code need no other edit.

- [ ] **Step 6: Run the full frontend verification**

Run, from `web/`:
```bash
npm run typecheck
npm run build
npm run test -- --run
```
Expected: all three succeed with zero errors. This is the deletion task's equivalent of the backend plans' "zero regression" proof — a clean `tsc -b` confirms no dangling import survived the deletions in Steps 1-2, and the full test suite confirms every remaining page/component (including `Watchlist`/`Alerts`/`CreateAlertForm`'s portfolio-alert path) still passes.

If `npm run typecheck` reports any error referencing a file this task deleted, that means Step 1's grep missed an importer — find and fix it (either delete the stray reference if it belongs to already-removed code, or restore the import if it was a false positive) before proceeding.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: remove Portfolio/AI-Analyst/Learning/Research/Decisions, trim nav to Market/Watchlist/Assets/Alerts

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
