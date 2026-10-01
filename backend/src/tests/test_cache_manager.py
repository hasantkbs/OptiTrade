"""
Characterization tests for core/cache_manager.py (TTLCache).

These document the CURRENT behavior of TTLCache exactly as implemented
today. Several things below look questionable (no distinction between a
cached None and a cache miss, no proactive expiry sweep, values stored by
reference rather than copied, zero input validation) - per project
instruction these are preserved and documented with a comment at the
assertion that exercises them, not "fixed". See
docs/architecture/migration-notes.md for the consolidated list of risks
these create for the future Feature Store / Decision Engine work.

TTL/expiration tests use a fake clock (monkeypatching the module-level
`time.time` that core.cache_manager calls) instead of real `time.sleep()`,
so the exact `>=` boundary in TTLCache.get() can be tested precisely and
deterministically without flakiness or slow tests. One smoke test at the
end uses a real, short `time.sleep()` to confirm the class behaves the
same way against the real clock.
"""
import threading
import time as real_time

import pytest

from core.cache_manager import TTLCache


class FakeClock:
    """Controllable stand-in for time.time(), advanced explicitly by tests."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self._now = start

    def time(self) -> float:
        return self._now

    def advance(self, delta: float) -> None:
        self._now += delta


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr("core.cache_manager.time.time", fake.time)
    return fake


# ─────────────────────────────────────────────────────────────────────────
# Normal scenarios
# ─────────────────────────────────────────────────────────────────────────

def test_set_then_get_returns_the_value(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=60)
    cache.set("k", "v")
    assert cache.get("k") == "v"


def test_get_missing_key_returns_none(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=60)
    assert cache.get("missing") is None


def test_multiple_keys_are_independent(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=60)
    cache.set("a", "1")
    cache.set("b", "2")
    assert cache.get("a") == "1"
    assert cache.get("b") == "2"


def test_overwriting_a_key_replaces_value_and_resets_its_ttl_clock(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=10)
    cache.set("k", "first")
    clock.advance(9)  # nearly expired
    cache.set("k", "second")  # overwrite resets the stored timestamp
    clock.advance(9)  # would have expired the *original* entry, not this one
    assert cache.get("k") == "second"


def test_invalidate_removes_a_key(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=60)
    cache.set("k", "v")
    cache.invalidate("k")
    assert cache.get("k") is None


def test_invalidate_missing_key_does_not_raise(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=60)
    cache.invalidate("does-not-exist")  # no exception


def test_clear_empties_the_cache(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=60)
    cache.set("a", "1")
    cache.set("b", "2")
    cache.clear()
    assert len(cache) == 0
    assert cache.get("a") is None


def test_clear_on_empty_cache_does_not_raise(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=60)
    cache.clear()
    assert len(cache) == 0


def test_len_reflects_stored_entry_count(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=60)
    assert len(cache) == 0
    cache.set("a", "1")
    assert len(cache) == 1
    cache.set("b", "2")
    assert len(cache) == 2


# ─────────────────────────────────────────────────────────────────────────
# TTL / expiration
# ─────────────────────────────────────────────────────────────────────────

def test_value_available_right_up_to_the_ttl_boundary(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=10)
    cache.set("k", "v")
    clock.advance(9.999)
    assert cache.get("k") == "v"


def test_value_expires_at_exactly_ttl_seconds_elapsed(clock):
    # get() uses `time.time() - cached_at >= self._ttl_seconds`, an inclusive
    # `>=` - so an entry is already considered expired the instant elapsed
    # time equals the TTL exactly, not strictly after it.
    cache: TTLCache[str] = TTLCache(ttl_seconds=10)
    cache.set("k", "v")
    clock.advance(10.0)  # exactly the TTL, not one tick past it
    assert cache.get("k") is None


def test_expired_get_deletes_the_entry(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=10)
    cache.set("k", "v")
    clock.advance(11)
    assert cache.get("k") is None
    assert len(cache) == 0  # the lazy expiry in get() also removed the entry


def test_len_counts_expired_entries_that_have_not_been_accessed_yet(clock):
    # There is no background sweep/eviction thread - an expired entry is
    # only removed when something calls get() on that specific key. Until
    # then, __len__ (a raw `len(self._store)`) still counts it as present,
    # even though it is logically dead. This is a real memory-growth risk
    # for keys that are set-and-forget and never read again.
    cache: TTLCache[str] = TTLCache(ttl_seconds=10)
    cache.set("k", "v")
    clock.advance(100)  # long expired
    assert len(cache) == 1  # still counted - nothing has touched "k" yet
    cache.get("k")  # now it gets lazily evicted
    assert len(cache) == 0


def test_ttl_zero_expires_immediately_even_with_no_elapsed_time(clock):
    # With ttl_seconds=0, `elapsed >= 0` is true even when elapsed is 0.0
    # (no simulated time has passed at all) - so a TTL of 0 means "never
    # actually retrievable", not "no expiration".
    cache: TTLCache[str] = TTLCache(ttl_seconds=0)
    cache.set("k", "v")
    assert cache.get("k") is None


def test_negative_ttl_always_expires(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=-5)
    cache.set("k", "v")
    assert cache.get("k") is None


def test_large_ttl_survives_a_long_simulated_duration(clock):
    cache: TTLCache[str] = TTLCache(ttl_seconds=10**9)
    cache.set("k", "v")
    clock.advance(10**6)
    assert cache.get("k") == "v"


def test_real_clock_smoke_test_expiry_actually_works_without_a_fake_clock():
    """One test against the real `time` module (no fake clock fixture), to
    confirm the fake-clock tests above are actually representative and not
    an artifact of monkeypatching."""
    cache: TTLCache[str] = TTLCache(ttl_seconds=0.05)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    real_time.sleep(0.15)
    assert cache.get("k") is None


# ─────────────────────────────────────────────────────────────────────────
# Edge cases / questionable behavior (preserved, documented)
# ─────────────────────────────────────────────────────────────────────────

def test_a_cached_none_value_is_indistinguishable_from_a_cache_miss(clock):
    # get() returns None both when a key was never set/has expired AND when
    # a key was explicitly cached with the value None - there is no way for
    # a caller to tell these two situations apart from the return value
    # alone. Any future caller that legitimately wants to cache "no result"
    # as a value (e.g. "we checked and there's no recommendation for this
    # symbol") cannot distinguish that from "not cached yet, please compute
    # it" using this API.
    cache: TTLCache[object] = TTLCache(ttl_seconds=60)
    cache.set("k", None)
    assert cache.get("k") is None  # same return value as a genuine miss
    assert len(cache) == 1  # ... even though the key IS actually present


def test_values_are_stored_by_reference_not_copied(clock):
    # set()/get() never serialize or deep-copy the value - the exact same
    # object is stored and returned. Mutating the object after set() (or
    # mutating what get() returned) mutates the cached entry too, since
    # there is only ever one shared object.
    cache: TTLCache[list] = TTLCache(ttl_seconds=60)
    original = [1, 2, 3]
    cache.set("k", original)
    original.append(4)  # mutate the caller's reference after caching
    assert cache.get("k") == [1, 2, 3, 4]  # the cache saw the mutation
    assert cache.get("k") is original  # literally the same object, not a copy


def test_key_type_is_not_validated_at_runtime(clock):
    # The type hints say keys are `str`, but nothing enforces that -
    # TTLCache is a thin wrapper over a plain dict, so any hashable object
    # works as a key in practice.
    cache: TTLCache[str] = TTLCache(ttl_seconds=60)
    cache.set(42, "v")            # int key
    cache.set(("a", "b"), "w")    # tuple key
    assert cache.get(42) == "v"
    assert cache.get(("a", "b")) == "w"


def test_unhashable_key_raises_a_raw_uncaught_typeerror(clock):
    # There is no input validation or error handling anywhere in this class
    # - an unhashable key (e.g. a list) bubbles up as Python's native
    # TypeError from the underlying dict, uncaught and unwrapped.
    cache: TTLCache[str] = TTLCache(ttl_seconds=60)
    with pytest.raises(TypeError):
        cache.set(["not", "hashable"], "v")


# ─────────────────────────────────────────────────────────────────────────
# Concurrency
# ─────────────────────────────────────────────────────────────────────────

def test_concurrent_sets_to_distinct_keys_all_survive(clock):
    """Many threads each set their own unique key; afterward every single
    one must be readable with the correct value - characterizes that the
    lock prevents lost writes for the common case of independent keys."""
    cache: TTLCache[int] = TTLCache(ttl_seconds=60)
    n_threads = 20
    writes_per_thread = 50

    def worker(thread_id: int) -> None:
        for i in range(writes_per_thread):
            cache.set(f"t{thread_id}-{i}", thread_id * 1000 + i)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(cache) == n_threads * writes_per_thread
    for thread_id in range(n_threads):
        for i in range(writes_per_thread):
            assert cache.get(f"t{thread_id}-{i}") == thread_id * 1000 + i


def test_concurrent_readers_and_writers_on_a_shared_key_do_not_crash(clock):
    """Many threads hammering get()/set()/invalidate() on the SAME key
    concurrently must not raise or corrupt the cache's internal state -
    this doesn't prove linearizability, only that the lock is sufficient
    to avoid crashes/corruption under contention."""
    cache: TTLCache[int] = TTLCache(ttl_seconds=60)
    stop = threading.Event()
    errors = []

    def writer() -> None:
        i = 0
        while not stop.is_set():
            try:
                cache.set("shared", i)
                i += 1
            except Exception as exc:  # pragma: no cover - failure path only
                errors.append(exc)

    def reader() -> None:
        while not stop.is_set():
            try:
                cache.get("shared")
                cache.invalidate("shared")
            except Exception as exc:  # pragma: no cover - failure path only
                errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(5)] + [
        threading.Thread(target=reader) for _ in range(5)
    ]
    for t in threads:
        t.start()
    real_time.sleep(0.2)
    stop.set()
    for t in threads:
        t.join()

    assert errors == []


# ─────────────────────────────────────────────────────────────────────────
# Serialization — not applicable
# ─────────────────────────────────────────────────────────────────────────

def test_no_serialization_occurs_arbitrary_objects_pass_through_unchanged(clock):
    # TTLCache never serializes/deserializes anything (no pickle, no JSON) -
    # it is a pure in-process object cache. Any hashable-keyed, arbitrary
    # Python object is accepted as a value and returned unchanged. This is
    # a relevant fact for a future Redis-backed online store, which WILL
    # require serialization where this in-memory version needs none - see
    # docs/architecture/migration-notes.md.
    class Unserializable:
        def __eq__(self, other):
            return self is other

    cache: TTLCache[Unserializable] = TTLCache(ttl_seconds=60)
    obj = Unserializable()
    cache.set("k", obj)
    assert cache.get("k") is obj


# ─────────────────────────────────────────────────────────────────────────
# Backward compatibility — public API shape guard
# ─────────────────────────────────────────────────────────────────────────

def test_public_api_surface_is_unchanged():
    """Locks down the method names and parameter names that later sprints
    (e.g. swapping in a Redis-backed implementation) must preserve for
    existing callers (core.hybrid_engine, core.news_analyzer pattern,
    core.sector_intelligence pattern) to keep working unmodified."""
    import inspect

    assert set(inspect.signature(TTLCache.__init__).parameters) == {"self", "ttl_seconds"}
    assert set(inspect.signature(TTLCache.get).parameters) == {"self", "key"}
    assert set(inspect.signature(TTLCache.set).parameters) == {"self", "key", "value"}
    assert set(inspect.signature(TTLCache.invalidate).parameters) == {"self", "key"}
    assert set(inspect.signature(TTLCache.clear).parameters) == {"self"}
    assert set(inspect.signature(TTLCache.__len__).parameters) == {"self"}
