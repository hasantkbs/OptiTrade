# Web Frontend Simplification — Design

## Mission

OptiTrade's web app currently has 9 nav sections and a dashboard with 8
jargon-dense panels (engine breakdowns, confidence scores, risk analytics,
portfolio management). The goal of this sub-project — the final phase of
the "model-based development, focus on accuracy" initiative — is to cut
this down to the minimum an independent retail user actually needs: pick a
stock or crypto asset, see its chart/volume/news, and see the model's plain
buy/sell/hold recommendation. No portfolio management, no engine
terminology, no raw confidence/risk numbers.

## Current State

- **Nav** (`web/src/components/layout/nav.ts`): Dashboard, Portfolio,
  Watchlist, Assets, Decisions, Alerts, AI Analyst, Learning, Research
  (unavailable).
- **`DashboardPage`** (`web/src/pages/DashboardPage.tsx`): 8 sections —
  `DashboardKpis`, `PortfolioPerformance`, `EngineIntelligence`,
  `MarketOverview`, `RecentDecisions`, `LearningOverview`,
  `WatchlistIntelligence`, `AlertsOverview`.
- **`AssetDetailPage`** (`web/src/pages/AssetDetailPage.tsx`, route
  `/assets/:symbol`): `AssetHeader` + `PriceChart` (price only, no volume,
  despite `ChartResponse.points[].volume` already being returned by
  `GET /chart/{symbol}` — confirmed in `web/src/api/types.ts:503-516`) +
  `QuantDecision` (BUY/SELL/HOLD badge, raw confidence %, expected
  return/volatility %, "N/M engines succeeded", a raw `evidence: string[]`
  list) + `EngineBreakdown` (one card per Technical/Fundamental/News
  engine, each with its own vote/confidence/evidence) + `RiskPanel` + a
  separate `ExplanationPanel` showing `PipelineResponse.explanation` — an
  **already-existing, already-plain-language LLM-generated summary** of
  the decision (`web/src/features/asset/ExplanationPanel.tsx:8-15`'s own
  docstring: "the Explanation Engine's plain-language text").
- **`src/features/portfolio/`**: a full portfolio management feature
  (positions, cash, allocation, drawdown, risk analytics, activity feed) —
  12 components, its own page, its own nav entry.
- **News**: a real, working, per-symbol endpoint already exists —
  `GET /news/{symbol}` (`backend/src/main.py:1049-1056`, calling
  `core.news_analyzer.get_news_summary`) — returning up to 8 real
  headlines with `title`/`sentiment`/`score`/`published_at`
  (`core/news_analyzer.py:858-871`). **It is never called anywhere in the
  frontend today.**
- **Market-level data**: `GET /dashboard/market`
  (`backend/src/main.py:2646-2656`, `MarketDashboardView`) returns sector
  opportunity scores and an aggregate news-sentiment summary across
  symbols, but no index-level price series (BIST100/BTC) and no crypto
  market-cap dominance figure — neither exists anywhere in the backend
  today.

## Scope

**Kept, functionally unchanged:** Watchlist, Alerts (explicit user
choice — these stay as-is; only `DashboardPage`, `AssetDetailPage`, and
nav/routing change structurally).

**Removed entirely:** `PortfolioPage` and all of
`web/src/features/portfolio/` (12 components), `AnalystPage`,
`LearningPage` and `web/src/features/learning/`, `ResearchPage`, the
current `DashboardPage` and its 8 sections (`DashboardKpis`,
`PortfolioPerformance`, `EngineIntelligence`, `MarketOverview`,
`RecentDecisions`, `LearningOverview`, `WatchlistIntelligence`,
`AlertsOverview`), and `DecisionsPage` (superseded by the simplified
per-asset recommendation — no separate decisions list page). Their nav
entries, tests, and any backend endpoints that exist *only* to serve them
(none identified yet — confirmed during planning) are removed too.

**New home page** (`MarketSnapshotPage`, replacing `DashboardPage` at
`/`): BIST100 index price chart, BTC price chart, real BTC dominance %,
and a trimmed sector/news summary (reusing `GET /dashboard/market`,
showing fewer fields than today's `MarketOverview`).

**Simplified asset page** (`AssetDetailPage` kept at `/assets/:symbol`,
restructured): price chart **with a volume sub-chart** (no new data —
`ChartPoint.volume` already exists), **one** `Recommendation` component
replacing `QuantDecision` + `EngineBreakdown` + `RiskPanel` +
`ExplanationPanel`, and a new `AssetNews` component wiring up the
already-existing `GET /news/{symbol}` endpoint for the first time.

## Architecture

### Backend: one new provider + one new endpoint, both additive

1. **New `backend/src/providers/coingecko_provider.py`** — mirrors the
   existing `BinanceProvider` pattern (`providers/binance_provider.py`:
   plain `httpx.get` calls, no SDK dependency). One function,
   `get_btc_dominance() -> Optional[float]`, calling CoinGecko's free,
   keyless `GET https://api.coingecko.com/api/v3/global` and reading
   `data.market_cap_percentage.btc`. Returns `None` on any failure
   (timeout, non-200, missing field) — logged, never raised — matching
   this project's established "degrade gracefully on an optional external
   call" convention (e.g. `BinanceProvider`'s own try/except-and-log
   shape).
2. **New `GET /market/snapshot` endpoint** in `backend/src/main.py`
   (alongside the existing `/dashboard/market`): returns BIST100
   (`XU100.IS` via the existing `yfinance_provider`/`fetch_history`, same
   function `GET /chart/{symbol}` already uses) and BTC
   (`BTC-USD`, same path) price series for a fixed short period (e.g.
   `3mo`, matching `ChartResponse`'s existing shape so the frontend reuses
   its existing chart-point types), plus `btc_dominance_pct` from the new
   provider (nullable — the frontend shows "unavailable" if `None`). Rate
   limited like every other market-data endpoint (`@limiter.limit`,
   matching `/chart/{symbol}`'s `30/minute`).
3. **No changes to `decision_engine`, any voting engine, `/quant/analyze`,
   or `/news/{symbol}`** — this sub-project only adds one new read-only
   provider and one new read-only endpoint; every existing endpoint the
   simplified frontend uses (`/chart/{symbol}`, `/quant/analyze`,
   `/news/{symbol}`, `/dashboard/market`) is consumed exactly as it already
   responds today, with zero backend changes to any of them.

### Frontend: page/nav removal + 4 new or restructured components

4. **`nav.ts`** trimmed to: Dashboard (→ `/`, the new market snapshot),
   Watchlist, Alerts. (Login/Register stay outside the nav, unchanged.)
5. **New `MarketSnapshotPage`** (`web/src/pages/MarketSnapshotPage.tsx`,
   replacing `DashboardPage.tsx`) composed of 3 small components:
   `IndexChart` (reusable, takes a symbol + label, renders a price line —
   reuses the existing chart-rendering pattern from `PriceChart.tsx` rather
   than a new charting approach) used twice (BIST100, BTC);
   `DominanceFigure` (a single large number + "unavailable" fallback); a
   trimmed `MarketSummary` (sector bars + top-5 news-sentiment rows,
   i.e. today's `MarketOverview.tsx` content, kept as one component, not
   8).
6. **`AssetDetailPage.tsx` restructured**: `PriceChart` gains a volume bar
   sub-chart (same component, extended — `ChartPoint.volume` plotted below
   the price line, same pattern already used for the sector bar chart in
   `MarketOverview.tsx`'s use of `recharts`). `QuantDecision` +
   `EngineBreakdown` + `RiskPanel` + `ExplanationPanel` are deleted; a new
   **`Recommendation`** component renders `data.decision` (BUY/SELL/HOLD
   badge, kept) + `data.explanation` (the existing plain-language LLM
   text, kept verbatim — already exactly what "remove terminology, just
   show the model's recommendation" asks for) + confidence shown as one of
   three plain words — **Yüksek güven** (`confidence >= 0.66`), **Orta
   güven** (`0.33 <= confidence < 0.66`), **Düşük güven**
   (`confidence < 0.33`) — instead of a raw percentage. `data.evidence`
   (the raw per-item string list), `expected_return`, `expected_volatility`,
   `engine_breakdown`, `risk`, and the "N/M engines succeeded"/"Degraded
   run" metadata are **not displayed** (still present in the API response,
   simply not rendered — no backend change, per constraint #3 above).
7. **New `AssetNews` component** (`web/src/features/asset/AssetNews.tsx`):
   calls `GET /news/{symbol}` (a new frontend API hook, `useAssetNews`,
   added to `web/src/features/asset/hooks.ts` alongside the existing
   `usePrice`/`useChart`/`useQuantAnalyze`), renders up to 5 headlines
   (`title`, a sentiment `Badge` reusing `MarketOverview.tsx`'s existing
   `sentimentTone()` helper, `published_at` formatted as a relative/short
   date) — a plain list, no raw `score`/`age_weight`/`keywords` fields
   shown.
8. **Deleted directories/files**: `web/src/features/portfolio/` (all 12
   components + tests), `web/src/features/learning/` (all 6 components +
   tests), `web/src/features/dashboard/sections/` (all 8 sections +
   tests) except `MarketOverview.tsx` (kept, becomes the basis for the new
   trimmed `MarketSummary`), `web/src/pages/PortfolioPage.*`,
   `AnalystPage.*`, `LearningPage.*`, `ResearchPage.*`, `DecisionsPage.*`,
   `DashboardPage.*` (all `.tsx`/`.module.css`/`.test.tsx` trios), and
   `web/src/features/asset/QuantDecision.*`, `EngineBreakdown.*`,
   `RiskPanel.*`, `ExplanationPanel.*` (replaced by `Recommendation.*`).

## Data Flow

```
MarketSnapshotPage (/)
  GET /market/snapshot          -> IndexChart x2 (BIST100, BTC) + DominanceFigure
  GET /dashboard/market         -> MarketSummary (trimmed MarketOverview)

AssetDetailPage (/assets/:symbol)
  GET /price/{symbol}           -> AssetHeader (unchanged)
  GET /chart/{symbol}           -> PriceChart (+ new volume sub-chart)
  POST /quant/analyze           -> Recommendation (decision + explanation + plain confidence word)
  GET /news/{symbol}            -> AssetNews (new - first-ever frontend use of this endpoint)

Watchlist, Alerts: unchanged, existing data flow.
```

## Error Handling

No new error-handling pattern. Every new/changed component follows this
codebase's existing convention (`EmptyState`/`ErrorState` components,
retry callbacks via React Query, already used throughout `AssetDetailPage`
and `MarketOverview`). The one new external dependency
(`coingecko_provider.get_btc_dominance`) degrades to `None` on any failure
— `DominanceFigure` renders "unavailable" rather than blocking the rest
of `/market/snapshot`'s response (the two index charts come from the
already-reliable `fetch_history`/`yfinance` path and are independent of
the dominance call failing).

## Testing

- Backend: a unit test for `coingecko_provider.get_btc_dominance` (success
  case with a mocked response, and the None-on-failure case — timeout,
  non-200, malformed JSON — matching `BinanceProvider`'s own existing test
  pattern), and an integration test for `GET /market/snapshot` (real
  `fetch_history` calls for BIST100/BTC, mocked CoinGecko call).
- Frontend: new `MarketSnapshotPage.test.tsx`, `IndexChart.test.tsx`,
  `DominanceFigure.test.tsx`, `Recommendation.test.tsx`, `AssetNews.test.tsx`
  — same React Testing Library + mocked-hook pattern already used by every
  existing component test in this codebase (e.g.
  `QuantDecision.test.tsx`, `MarketOverview`'s own tests, confirmed during
  planning). Tests for every deleted component/page are deleted alongside
  the component.
- `AssetDetailPage.test.tsx` updated to assert the new `Recommendation`/
  `AssetNews`/volume-chart presence and the absence of the old
  `QuantDecision`/`EngineBreakdown`/`RiskPanel`/`ExplanationPanel` content.

## Global Constraints

- Every commit ends with `Co-Authored-By: Claude Sonnet 5
  <noreply@anthropic.com>`.
- Zero changes to `decision_engine`, any voting engine, `/quant/analyze`,
  or `/news/{symbol}` — this is a frontend-surface and additive-backend
  sub-project, not a decision-logic change.
- `/market/snapshot` and `coingecko_provider` are strictly additive —
  no existing endpoint's response shape or behavior changes.
- The new `Recommendation` component displays only fields the backend
  already returns (`decision`, `explanation`, `confidence` mapped to a
  plain word) — nothing is fabricated, matching this project's
  "never manufacture a value the response doesn't contain" convention
  already established in `EngineBreakdown.tsx`'s own docstring.
- Confidence word thresholds (`>= 0.66` Yüksek, `0.33–0.66` Orta, `< 0.33`
  Düşük) are exact and must be used verbatim, not re-derived per
  component.
- Watchlist and Alerts pages are functionally unchanged — no restructuring,
  only incidental terminology review if a specific label is flagged during
  implementation (not a required pass).
- Honest degradation: if `btc_dominance_pct` is `None`, the UI must say so
  plainly ("unavailable"), never show a fabricated or stale-silently
  number.

## Out of Scope

- Any change to `decision_engine`'s voting/aggregation logic, or to how
  `/quant/analyze` computes its response — this sub-project only changes
  what the frontend *displays*, never what the backend *decides*.
- Portfolio data/tables are removed from the UI but the backend's
  portfolio endpoints/tables are **not deleted** — no data migration, no
  destructive backend change. (A future decision, not part of this plan.)
- A dedicated BIST/BTC dominance *history* chart (dominance over time) —
  only the current snapshot figure is in scope; CoinGecko's free tier
  doesn't offer historical dominance without a paid plan, and this wasn't
  requested.
- Re-adding Watchlist/Alerts terminology changes beyond what's incidentally
  touched — a full pass on those two pages is explicitly not requested.

## Risks

- **CoinGecko's free, keyless tier has a modest rate limit** (roughly
  10-30 calls/minute shared across all API consumers of that IP) — mitigated
  by `/market/snapshot` being a single shared endpoint all users hit (not
  one CoinGecko call per user), and by the existing `@limiter.limit`
  pattern already capping how often the frontend can even request it.
- **Deleting `web/src/features/dashboard/sections/*` except
  `MarketOverview.tsx` touches a directory with 8 previously-coupled
  components** — mitigated by each section already being an independent,
  self-contained component (confirmed during planning: `DashboardPage.tsx`
  just composes them with no shared state), so deletion is mechanical, not
  a refactor.
- **`Recommendation`'s plain-word confidence mapping is a UI-only
  simplification of a continuous number** — deliberately accepted per this
  sub-project's own mission (remove terminology/raw numbers for an
  independent retail user); the raw percentage remains available in the
  untouched API response for any future, different consumer.
