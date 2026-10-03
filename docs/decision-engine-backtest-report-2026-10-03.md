# decision_engine Point-in-Time Backtest — 2026-10-03

**Technical voting engine ONLY — NOT the full 3-engine live decision.**
Fundamental and News engines cannot be backfilled with current data
sources (see docs/superpowers/specs/2026-10-03-decision-engine-backtest-design.md) and are excluded from this backtest's own engine registry entirely.

## Result

| Samples | Directional samples | HOLD (abstentions) | Accuracy | Majority baseline | Precision | Recall |
|---|---|---|---|---|---|---|
| 12859 | 4257 | 8602 | 0.492 | 0.588 | 0.395 | 0.438 |

Per-symbol sample counts: {'THYAO.IS': 518, 'GARAN.IS': 518, 'ASELS.IS': 518, 'KCHOL.IS': 518, 'EREGL.IS': 518, 'AKBNK.IS': 518, 'TUPRS.IS': 518, 'FROTO.IS': 518, 'SAHOL.IS': 518, 'PGSUS.IS': 518, 'ISCTR.IS': 518, 'SISE.IS': 518, 'BIMAS.IS': 518, 'YKBNK.IS': 518, 'TOASO.IS': 518, 'BTC-USD': 727, 'ETH-USD': 727, 'BNB-USD': 727, 'SOL-USD': 727, 'AVAX-USD': 727, 'XRP-USD': 727, 'DOGE-USD': 727}

## Known limitations and disclosures (added post-review, 2026-10-03)

The following limitations were identified during final review of this backtest. None of them change the reported numbers above (accuracy 0.492, majority baseline 0.588, precision 0.395, recall 0.438) — those are all computed strictly from the 4,257 directional samples, which are unaffected by every point below. They are recorded here for anyone interpreting or building on this result.

**1. The HOLD count conflates two different situations.** The 8,602 HOLD samples (~67% of all 12,859 samples) are excluded from the accuracy calculation, but the current implementation cannot distinguish between two meaningfully different causes:

- **Genuine abstention** — the Technical engine had real backfilled features for that symbol/day and its voting logic concluded there was no clear directional signal, so it returned HOLD on purpose.
- **Data-coverage gap** — the historical day had little or no backfilled feature data at all, and the engine returned HOLD by default because it had nothing to vote on, not because it evaluated the evidence and abstained.

These two cases look identical in the current HOLD count. They imply very different next steps: a high rate of (1) suggests the decision threshold may need tuning, while a high rate of (2) suggests a data-coverage/backfill gap needs fixing instead. Splitting the HOLD count into these two categories, and reporting per-day feature-coverage counts (how many of `ALL_FEATURE_NAMES` were actually present per symbol/day), is left to a follow-up piece of work. It is not retrofitted into this report because doing so correctly requires re-deriving per-day coverage data this fix round was not scoped to produce.

**2. A historical gap day may carry forward a stale feature value rather than being skipped.** `TechnicalFeatureAdapter._resolve_as_of` reads features via `PostgresOfflineStore.get_as_of`, whose query (`event_timestamp <= as_of ORDER BY event_timestamp DESC LIMIT 1`) has no lower bound on how far back it can look. Concretely: if a given day has no backfilled row at all for a feature (e.g. a date before any data exists), the feature is correctly missing. But if at least one earlier row exists, a short data gap on `as_of` itself (a holiday, a backfill pause) is silently bridged by returning the most recent prior value, however old it is, rather than treating the feature as missing for that day. **This is not a leakage bug** — the returned value is still strictly from before `as_of`, so no future information crosses into the past — but it is a staleness characteristic: some samples counted as "having data" may actually be using a feature value carried forward from several days earlier. This is a known, accepted characteristic of the current implementation (not a bug), and is worth keeping in mind when interpreting the 0.492/0.588 result and in particular when designing the HOLD-breakdown follow-up in point 1.

**3. `respect_ingestion_time=True` does no additional filtering on this specific dataset.** Every historical feature read in this backtest uses `respect_ingestion_time=True` as a leakage guard. For this backfilled dataset specifically, that flag does not exclude anything beyond what event-time filtering alone would already exclude, because the backfill script set `ingestion_timestamp == event_timestamp` for every backfilled row — so the ingestion-time check and the event-time check are checking the same condition here. The real protection against lookahead in this backtest comes entirely from the backfill's own trailing-window-per-historical-day computation (each day's features were computed using only OHLCV data up to and including that day), not from `respect_ingestion_time` doing extra work on top of that. `respect_ingestion_time=True` remains the semantically correct and intentional choice — it is still necessary and correct for any future backfill that might not preserve this exact `ingestion_timestamp == event_timestamp` property — but for this dataset specifically it is not doing additional work beyond event-time filtering.
