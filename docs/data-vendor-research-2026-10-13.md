# Fundamental/News Data Vendor Research — Cost and Feasibility (2026-10-13)

## Why this exists

The consolidated ML accuracy summary (`docs/ml-accuracy-consolidated-summary-2026-10-13.md`)
identified Fundamental and News features as the one genuinely
unexhausted direction after five attempts on pure price/volume
technicals all converged on no reliable signal. That direction is
blocked today because yfinance only gives current-snapshot
fundamentals/live news, not genuine point-in-time (PIT) historical
data needed to backtest without lookahead leakage. This researches
what it would actually cost to unblock it.

## Important finding that changes the calculus

**The current ML training basket (`research/ml_trainer.py::SYMBOLS`) is
15 BIST equities + 7 crypto — zero US equities.** Most of the
well-documented, affordably-priced vendors below (Polygon, EODHD,
Intrinio, Sharadar) are US-centric. For this specific basket:

- **Crypto (7/22 symbols)** has no "fundamentals" in the traditional
  sense (no P/E, balance sheet) — only News coverage matters, and that
  is only partially confirmed below.
- **BIST (15/22 symbols, the majority)** is exactly the segment where
  no vendor researched offers a clean, affordable, *point-in-time*
  fundamentals API. Paying for data does not, by itself, solve this
  for the majority of the basket.

If the basket is ever expanded to US equities (relevant to the live
app's broader Recommendation/Top-Opportunities features even if not
to the current ML training set), that side of the problem is well
served at reasonable cost — see below.

## Global / US-equity + crypto vendors

| Vendor | Point-in-time fundamentals? | Historical news archive? | Relevant pricing | Caveats |
|---|---|---|---|---|
| **Nasdaq Data Link (Sharadar SF1)** | Strongest PIT reputation in the quant community specifically for avoiding restatement lookahead bias; purpose-built for backtesting | None — fundamentals/alt-data only | ~$39/mo (10yr) to ~$399/yr (full history), per third-party trackers, not Nasdaq's own page | No news at all — must pair with a separate news vendor. Verify pricing directly before committing. |
| **EODHD** | Not a true PIT system (no as-of-date query found); "Equity Analyst" tier | **Yes, with sentiment** | **Equity Analyst $59.99/mo** (fundamentals + sentiment news), **All-In-One $99.99/mo** adds crypto | Best single-vendor bundle for simplicity; crypto OHLCV covered (2,600+ pairs) but crypto *news* specifically unconfirmed |
| **Intrinio** | Best-documented explicit PIT language of any vendor researched (balance-sheet periods explicitly tied to PIT semantics) | NewsEdge: up to 10yr history, 200+ sources — **Enterprise tier only** | Individual $150/mo (fundamentals only) → ~$999/mo to add NewsEdge → Enterprise $1,250+/mo custom | Getting both fundamentals + news pushes to ~$1,000+/mo within a year |
| **Finnhub** (already used, free tier) | Fundamental-1 $50/mo / Fundamental-2 $200/mo add institutional fundamentals; PIT claim unverified | Company-news on free tier already; sentiment is a separate paid add-on | $50-200/mo per market; reported enterprise bundle ~$3,500/mo | Pricing fragmented across add-ons; **Finnhub moved even US historical candles behind a paid plan in 2025** — our existing free-tier price history may already be at risk |
| **Benzinga** | N/A (news-only) | Yes — explicit historical news archive + sentiment, deep coverage advertised | Pro tiers $99-457/mo (terminal product); API-only pricing unconfirmed | Needs direct sales confirmation of REST-API-only pricing |
| **Polygon.io** (now Massive.com) | No explicit PIT guarantee found | Yes, ticker news exists | $29-199/mo, **billed per asset class** (stocks and crypto separately) | Mid-rebrand (Oct 2025), documentation in flux |
| Alpha Vantage, Tiingo, FMP | Not confirmed as true PIT | Weak/short (Tiingo: 3mo only) or unconfirmed depth | $0-250/mo range | None meet the 2-year PIT bar cleanly as researched |

**For US equities/crypto, the practical answer**: EODHD's All-In-One
($99.99/mo) is the most practical single-vendor bundle; Sharadar +
Benzinga is the more rigorous two-vendor combination if true PIT
correctness matters more than convenience.

## Turkish / BIST-specific vendors

| Vendor | BIST coverage | PIT fundamentals | News/disclosure archive | Pricing |
|---|---|---|---|---|
| **Foreks** | Yes, major Turkish vendor (~40% terminal market share) | No public API spec found | Foreks Haber is a real, long-running wire (since 1996) | **No public pricing — sales quote required** |
| **Matriks** | Yes | Terminal pricing published (Gold 515 TL/mo, DLL/API 568 TL/mo) but PIT semantics unconfirmed | Unverified | Terminal prices public; **API/fundamentals pricing requires a quote** |
| **Finnet** | Could not confirm this vendor currently exists under this name | — | — | — |
| **Bloomberg Terminal** | Yes (global coverage, no Turkey limit) | Yes, but priced as the whole Terminal | Yes | ~$24,000-32,000/user/year |
| **LSEG/Refinitiv Eikon** | Likely yes for large caps; smaller BIST100 names unconfirmed | Yes in principle | Yes in principle | Reported $300-1,830/user/year range, highly customized; Turkey-specific quote not found |
| **Borsa Istanbul DataStore** (official) | Price/volume only — **not fundamentals, not news** | No | No | EOD data 40-50 TL/mo, intraday 150 TL/mo; 90% academic discount available | Doesn't address the actual requirement |
| **KAP** (kap.org.tr, the official disclosure venue) | Yes — authoritative source | **Genuinely free, genuinely historical** (back to Nov 2015) | **Yes — the real substitute for a BIST news archive**, raw text, not sentiment-scored | Free, but **no official REST API** — only unofficial community wrappers (e.g. `pykap`) against undocumented endpoints |
| **İş Yatırım** (bonus find) | Yes | Undocumented but functional `MaliTablo` endpoint (balance sheet/income/cash flow by period) | No | Free, unofficial/undocumented |
| **Twelve Data** (bonus find) | **Explicitly confirmed** (official docs list Borsa Istanbul/XIST with Income Statement, Balance Sheet, Cash Flow, Dividends, Earnings) | Tier-gated, PIT semantics not verified — needs a trial check | Not a news product | **Public self-serve pricing**: Free Basic → Grow $948/yr → Pro $2,748/yr → Ultra $11,988/yr |
| EODHD, Finnhub, Polygon, etc. | **Unconfirmed/unlikely** — US-centric vendors, no documented BIST/XIST fundamentals coverage | — | — | — |

## The honest bottom line

Genuine point-in-time BIST fundamentals **do not exist as a clean,
affordable, self-serve product anywhere researched.** Every real
institutional Turkish vendor (Foreks, Matriks) and every global
terminal (Bloomberg, Refinitiv) is quote-only with no published
self-serve API pricing — standard for this market, but it means no
firm number exists without a sales call. The one vendor with
*confirmed* BIST coverage and *public* pricing (Twelve Data,
$948-11,988/year) has not confirmed true point-in-time semantics — it
may just be "latest restated," the same leakage risk as yfinance with
more history.

For the **news/disclosure** half specifically, KAP itself is the
authoritative and genuinely free source — but only reachable through
unofficial scraping wrappers against undocumented endpoints, not a
documented API with an SLA. Fine for a research backtest; a real
maintenance and reliability risk for anything production-grade.

**Realistically, paying a vendor does not buy a turnkey point-in-time
BIST dataset.** The practical path, if this is pursued, is: Twelve
Data (or a Matriks/Foreks sales quote, cost unknown) for current
fundamentals, KAP's free disclosure archive (via an unofficial
wrapper) for news/disclosures, **and real engineering time to
construct point-in-time correctness ourselves** — snapshotting each
quarter's figures as of its actual filing/disclosure date, rather than
relying on a vendor's native "as-of" query, because no vendor
researched advertises that capability for BIST specifically.

## Recommendation

Given 15 of our 22 training symbols are BIST equities, and BIST is
exactly the segment with no clean paid solution, **this is not a
"subscribe and the data problem goes away" decision** — it's
"subscribe (or get a quote) *and* budget real engineering time to
build point-in-time correctness from free-but-unofficial sources,
with residual data-quality risk either way." That materially changes
the cost-benefit versus how the question was originally framed. Two
honest paths from here:

1. **Narrow scope first**: since the US-equity/crypto side of this
   problem *is* well-served (EODHD $99.99/mo for a clean bundle, or
   Sharadar+Benzinga for rigor), consider testing the Fundamental/News
   hypothesis on a US-equity basket first — cheap, fast, and would
   tell us whether Fundamental/News features carry signal at all
   before committing to the much harder BIST data-engineering problem.
2. **Commit to BIST properly**: get real sales quotes from Twelve
   Data (self-serve, start here), Matriks, and Foreks; prototype a
   point-in-time snapshot layer against KAP's free disclosure archive
   in parallel, since that engineering work is needed regardless of
   which paid vendor (if any) is chosen.

Either path is a real, scoped piece of work, not a quick follow-up —
worth a decision on which one (or whether to do this at all right
now) before any implementation starts.
