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
