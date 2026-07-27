# Migration Notes

A living, factual log of implementation-level observations discovered
while characterizing existing modules during Sprint 1 (Repository
Refactoring) and later sprints. Each section documents one module: hidden
dependencies, technical debt, behavioral quirks, potential future
refactoring candidates, and risks the module poses for the upcoming
Feature Store and Decision Engine migrations.

This document is informational only. It does not propose solutions and
does not redesign anything — see `docs/architecture/gap-analysis.md` for
the approved-architecture comparison, and
`docs/superpowers/plans/2026-07-27-sprint1-repository-refactoring.md` for
what is actually being changed and when.

## cache_manager.py

Source: `backend/core/cache_manager.py` (`TTLCache`). Characterized in
`backend/tests/test_cache_manager.py` (25 tests, 100% line coverage).

**Hidden dependencies**
- Depends on the module-level `time.time()` call at every `get()`/`set()` —
  there is no injectable clock, so any future code that needs a
  reproducible/mockable time source (e.g. a Feature Store's point-in-time
  correctness guarantees) cannot get one from this class as-is.

**Technical debt**
- No proactive expiry sweep: expired entries are only removed lazily, the
  next time `get()` happens to be called on that exact key. A key that is
  set once and never read again stays in `_store` (and counted by
  `__len__`) forever, even long after it has logically expired. Under
  sustained use with many never-re-read keys, this cache can grow without
  bound.
- Zero input validation anywhere in the class. An unhashable key raises a
  raw, unwrapped `TypeError` from the underlying dict — there is no
  validation layer or custom error type.
- Key type is documented via type hints as `str` but is not enforced at
  runtime in any way; any hashable object works today.

**Behavioral quirks**
- `get()` returns `None` both for "key missing/expired" and for "key
  present with a legitimately cached value of `None`" — these two cases
  are indistinguishable from the return value alone.
- Values are stored and returned by reference, never copied or
  serialized. Mutating an object after `set()` (or mutating what `get()`
  returns) mutates the cached entry in place, since caller and cache share
  the same object.
- `ttl_seconds=0` does not mean "no caching enforced" or "cache forever" —
  because the expiry check is `elapsed >= ttl_seconds`, a TTL of exactly 0
  means every entry is already expired the instant it's read, even with
  zero elapsed time. The same applies to any negative TTL.
- Overwriting an existing key via `set()` fully resets that key's TTL
  clock to "now" — the old timestamp is discarded, not merged or extended.

**Potential future refactoring candidates** (observations only, no
solution proposed here)
- The lazy-only eviction strategy.
- The lack of a distinguishable "cached None" vs "cache miss" return
  signal.
- The lack of an injectable clock for deterministic testing/point-in-time
  behavior.

**Risks for Decision Engine migration**
- `core/hybrid_engine.py` currently uses one `TTLCache` instance per
  engine to cache whole `TradeRecommendation` objects for 15 minutes. If
  the future Decision Engine reuses this same caching pattern for decision
  outputs, the "cached `None` looks like a miss" quirk above becomes
  directly relevant: a legitimate "no decision"/"stay neutral" result
  cached as `None` would be silently recomputed every time instead of
  honoring the cache.

**Risks for Feature Store migration**
- This is exactly the kind of ad-hoc, single-process, non-persistent
  caching pattern the approved Feature Store (Redis online store +
  PostgreSQL offline store, per `docs/architecture/gap-analysis.md`
  section 3) is meant to replace. Concretely:
  - No serialization happens anywhere in `TTLCache` — values are arbitrary
    in-process Python objects. A Redis-backed online store will require
    serializing/deserializing every value, which this module gives no
    precedent or contract for.
  - No point-in-time query capability exists (no "get the value as of time
    T") — only "is the single stored value still within its TTL as of
    now."
  - No versioning of any kind — a `set()` simply overwrites whatever was
    there before, with no history retained.

## risk_manager.py

Source: `backend/core/risk_manager.py` (`DynamicRiskManager`,
`RiskLevels`). Characterized in `backend/tests/test_risk_manager.py`
(27 tests, 100% line coverage).

**Hidden runtime dependencies**
- None beyond the standard library and `pydantic` — `calculate()` is a
  pure function of its two arguments plus the four constructor-configured
  multipliers; no clock, I/O, or global state involved.

**Technical debt**
- The constructor (`stop_loss_atr_multiplier`, `take_profit_1_atr_multiplier`,
  `take_profit_2_atr_multiplier`, `min_risk_reward_ratio`) performs zero
  validation on any of the four multipliers — zero, negative, or otherwise
  nonsensical values are all accepted silently and only surface later as
  odd computed price levels (see quirks below).
- `calculate()`'s only input validation is `entry_price <= 0 or atr <= 0`.
  This check silently fails to catch `NaN` or `inf` (see numerical edge
  cases below) because IEEE-754 comparisons involving `NaN` are always
  `False`, and `inf` is not `<= 0`.
- `is_valid` is computed by comparing the *unrounded* `risk_reward_ratio`
  local variable against `min_risk_reward_ratio`, while the
  `risk_reward_ratio` field stored on the returned `RiskLevels` is
  separately rounded to 2 decimals. The two can disagree at the boundary
  (see quirks below) — a reader of only the rounded field can be misled
  about whether `is_valid` should be true.

**Behavioral quirks**
- `NaN` passed as `entry_price` or `atr` bypasses the positivity guard
  entirely (no exception) and propagates through every computed field;
  the final `risk_reward_ratio` still resolves to `0.0` and `is_valid` to
  `False`, because the `risk_per_unit > 0` check is itself always `False`
  for `NaN`.
- `inf` passed as `entry_price` similarly bypasses the guard; `stop_loss`/
  `take_profit_1`/`take_profit_2` all become `inf`, but `risk_per_unit`
  and `reward_per_unit_tp1` become `NaN` (`inf - inf` in IEEE-754), again
  silently resolving to `risk_reward_ratio=0.0`, `is_valid=False`.
- A `stop_loss_atr_multiplier` of `0.0` gives `risk_per_unit == 0.0` and a
  `stop_loss` exactly equal to `entry_price` — handled via the `else 0.0`
  fallback, not a `ZeroDivisionError`.
- A **negative** `stop_loss_atr_multiplier` places the computed stop-loss
  price *above* the entry price (nonsensical for a long-only risk model).
  Nothing detects or rejects this — it only shows up as a negative
  `risk_per_unit`, which (like the zero case) falls back to
  `risk_reward_ratio=0.0` via the same `> 0` guard, with no explicit
  signal that the stop-loss itself is placed on the wrong side of entry.
- An oversized `atr` relative to `entry_price` (e.g. `atr` >> `entry_price`)
  can drive the computed `stop_loss` to a **negative price**, which is not
  a realistic value for any real asset. `DynamicRiskManager` has no sanity
  check on the sign of any of the output price levels — only
  `risk_reward_ratio` is evaluated for validity, never whether the prices
  themselves make sense.
- `take_profit_2_atr_multiplier` has no effect on `is_valid` — validity is
  defined purely by the TP1-based ratio; TP2 is informational output only.
- Every numeric output field is independently rounded (`round(x, 4)` for
  prices/risk/reward, `round(x, 2)` for the ratio) — there is no single
  shared rounding pass, so an input value below roughly `0.00005` (e.g.
  `entry_price=1e-6`) passes the `> 0` validity check yet displays as
  exactly `0.0` in the output, indistinguishable at a glance from the
  `entry_price=0.0` case that raises `ValueError`.

**Numerical edge cases** (all verified empirically, not assumed)
- `entry_price=NaN` or `atr=NaN` → no exception, all downstream fields
  either `NaN` or the `0.0`/`False` fallback.
- `entry_price=inf` → no exception, `stop_loss`/TP fields become `inf`,
  `risk_per_unit`/`reward_per_unit_tp1` become `NaN` from `inf - inf`.
- `risk_reward_ratio` computed from an unrounded value of `1.996` (via
  `take_profit_1_atr_multiplier=1.996`, `stop_loss_atr_multiplier=1.0`)
  displays as a rounded `2.0` — equal to the default `min_risk_reward_ratio`
  — while `is_valid` is `False`, since the underlying comparison used the
  true unrounded `1.996 < 2.0`.
- Tiny positive `entry_price`/`atr` (e.g. `1e-6`) pass validation but round
  to a displayed `0.0`.

**Risks for Decision Engine migration**
- If a future Decision Engine surfaces `risk_reward_ratio` and `is_valid`
  together in any user-facing or LLM-facing output (as
  `core/ai_trader_persona.py` already does today via `RiskLevels`), the
  rounding-mismatch quirk above means the displayed ratio and the validity
  flag can appear to contradict each other with no rounding-precision
  explanation visible to the consumer.
- Nothing here validates that `entry_price`/`atr` passed in from upstream
  (regime scanner, MTF analyzer) are finite, real numbers before reaching
  `DynamicRiskManager` — a `NaN`/`inf` produced upstream (e.g. from a
  division by a zero-volume bar, or missing OHLCV data) would flow through
  silently as `is_valid=False` rather than surfacing as an explicit error
  the Decision Engine could act on or log distinctly from "reward is
  genuinely just below threshold."

**Risks for Learning Engine**
- `risk_reward_ratio` and `is_valid` are derived, deterministic functions
  of `entry_price`/`atr`/multipliers — not learned or fit from data in any
  way — so this module has no model versioning, training data, or feature
  drift concerns of its own. Its main relevance to a future Learning
  Engine is as a potential feature source: if `risk_reward_ratio` or
  `is_valid` were ever fed into a model as a feature, the NaN/inf-silent
  fallbacks above could inject silent `0.0`/`False` values into training
  data without any accompanying signal that the input was actually
  degenerate.

**Risks for Feature Store**
- `DynamicRiskManager.calculate()` is currently called fresh, per request,
  with live `entry_price`/`atr` — there is no caching, versioning, or
  point-in-time retrieval involved at all (unlike `hybrid_engine.py`'s use
  of `TTLCache` for the LLM recommendation one layer up). If risk levels
  were ever persisted as point-in-time features, the multiplier
  configuration (`stop_loss_atr_multiplier` etc.) used at calculation time
  would need to be recorded alongside the output, since the same
  `entry_price`/`atr` pair can produce different `RiskLevels` under a
  different `DynamicRiskManager` configuration, and nothing here currently
  records which configuration produced a given result.
