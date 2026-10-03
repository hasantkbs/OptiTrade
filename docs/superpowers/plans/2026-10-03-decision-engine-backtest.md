# decision_engine Point-in-Time Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `decision_engine.decide()` a genuine point-in-time replay capability (`as_of`), then use it to measure, for the first time ever, how accurate the Technical-only decision path actually would have been over the already-backfilled 2-year history.

**Architecture:** Thread an optional `as_of: Optional[datetime] = None` parameter through the real `decide()` call chain down to the Technical engine's Feature Store read — reusing the real live code for replay, never a parallel reimplementation. A key simplification found during planning (see Task 1): because `decide()` only passes `as_of` to `engine.vote()` when it is actually given, and the backtest's own registry contains only the Technical engine, **none of the other 24 `vote()` implementations found elsewhere in the codebase (pipeline/learning/shadow tests, `ml_training/shadow/adapter.py`, fixture fakes) need any change at all** — they keep satisfying the Protocol exactly as today, unmodified.

**Tech Stack:** Python, PostgreSQL (Feature Store), the existing `decision_engine`/`engines.technical` packages, yfinance/Binance for realized-return calculation (reusing the stabilization plan's provider-routing additions).

**Spec:** `docs/superpowers/specs/2026-10-03-decision-engine-backtest-design.md`

## Global Constraints

- Every commit ends with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Zero change to any existing caller's behavior: every current call site of `decide()`/`vote()`/`analyze()`/`get_features()` omits `as_of` and must continue behaving exactly as today — proven by tests, not just asserted.
- `as_of` replay must never call `self._persist()` — zero rows written to `decision_engine_executions` for historical replay.
- Fundamental and News engines are NOT touched in this plan at all — they are simply never registered in the backtest's own Technical-only registry, so they never receive an `as_of` call.
- `respect_ingestion_time=True` on every historical feature read — the leakage guard; a value must not be visible to a replay dated before it was actually known/ingested.
- `FORWARD_DAYS=5`, `THRESHOLD_UP=1.0` (imported from `research.ml_trainer`, not redefined) for the backtest's own direction-labeling, matching the existing ML evaluation scripts' convention for direct comparability.
- Report the real result honestly, whatever it is.
- Reuse the real `decide()`/engine code for the replay — no parallel reimplementation of Technical's voting or aggregation logic.

## Review Focus

- **A day/symbol with a `HOLD` decision gets silently counted as a directional miss.** `Prediction` is 3-way (BUY/HOLD/SELL); the existing ML eval scripts score a binary up/down classifier. A naive binary mapping would either crash on `HOLD` or wrongly force it into "predicted down," corrupting the accuracy number. Task 3's tests must exercise a `HOLD` decision and confirm it's excluded from the accuracy/precision/recall denominator, counted separately as an abstention rate instead.
- **`as_of` silently reaches an engine that doesn't accept it.** If a future engine change (or a bug in this plan) causes `_collect_valid_votes` to unconditionally pass `as_of=as_of` to every engine, any of the 24 other `vote()` implementations found in this codebase would raise `TypeError` the next time anything constructs a decision engine with them registered. Task 1's tests must prove the conditional-call design (only passed when not `None`) explicitly, not just that the Technical-only path works.
- **A historical `as_of` that falls on a real calendar day with NO backfilled data at all (a gap, a holiday, a symbol added later) silently produces a confident-looking `HOLD` instead of a visibly-low-confidence/zero-data result.** Task 2's tests must cover the all-features-missing case and confirm `data_sufficiency`/`confidence` honestly reflect "nothing was found," not a default that could be mistaken for a real neutral call.
- **The backtest script double-counts or skips a symbol/day silently on a transient fetch failure**, inflating or deflating the sample size without saying so. Task 3/4 must log and report skip counts explicitly, the same honesty standard already established for `evaluate_model_accuracy.py`/`backfill_feature_store.py`.
- **`output.timestamp` during replay is left at real wall-clock "now" instead of `as_of`**, which would make a backtest's returned `DecisionOutput` objects look like they all happened in the same instant (unusable for any time-series inspection of the results) even though nothing is persisted. Task 1 must set `timestamp=as_of` when replaying, verified by a test.

---

### Task 1: Thread `as_of` through `DecisionEngine.decide()`, skip persistence on replay

**Files:**
- Modify: `backend/src/decision_engine/interfaces.py` (`VotingEngineProtocol.vote()` type stub)
- Modify: `backend/src/decision_engine/service.py` (`DecisionEngine.decide()`, `_collect_valid_votes()`)
- Modify: `backend/src/tests/test_decision_engine_service.py` (`FakeVotingEngine`, new tests)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `DecisionEngine.decide(self, symbol: str, strict: bool = False, as_of: Optional[datetime] = None) -> DecisionOutput`. Task 2 and Task 3 both call `decide(symbol, as_of=...)`.

**Context:** Current `decide()` (service.py:60-112) always calls `engine.vote(symbol)` (no `as_of`) and always calls `self._persist(output)`. The codebase has 24 OTHER `vote()` implementations beyond the 3 real engines (pipeline/learning/shadow test fakes, `ml_training/shadow/adapter.py`, `tests/fixtures/fake_engines/*.py`) — none of them need to change, because this task's design only ever passes `as_of` to an engine when `as_of is not None`, and none of those 24 are ever registered into a replay-mode `decide()` call in this plan's scope.

- [ ] **Step 1: Write the failing tests**

Add to `backend/src/tests/test_decision_engine_service.py`. First, update `FakeVotingEngine` to optionally accept `as_of` WITHOUT changing its existing `self.calls` list's shape (every existing test asserts `engines[0].calls == ["BTC-USD"]` — that must keep working unmodified):

```python
class FakeVotingEngine:
    def __init__(self, engine_name, prediction=Prediction.BUY, confidence=0.8,
                 expected_return=1.0, volatility=1.0, evidence=None,
                 engine_version="v1", raises=False):
        self.engine_name = engine_name
        self.engine_version = engine_version
        self._prediction = prediction
        self._confidence = confidence
        self._expected_return = expected_return
        self._volatility = volatility
        self._evidence = evidence or []
        self._raises = raises
        self.calls: List[str] = []
        self.as_of_calls: List[Optional[datetime]] = []  # NEW - tracked separately so existing `self.calls == [...]` assertions never need to change

    def vote(self, symbol: str, as_of: Optional[datetime] = None) -> EngineVote:
        self.calls.append(symbol)
        self.as_of_calls.append(as_of)
        if self._raises:
            raise RuntimeError("simulated engine failure")
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version,
            prediction=self._prediction, confidence=self._confidence,
            expected_return=self._expected_return, volatility=self._volatility,
            evidence=self._evidence,
        )
```

Then add these new tests (after the existing `test_decide_result_reflects_aggregation_strategy_version_from_config`, before the end-to-end section):

```python
def test_decide_without_as_of_calls_vote_with_no_as_of_kwarg():
    """Regression test: decide(symbol) with no as_of must call
    engine.vote(symbol) exactly as before this feature existed - proven
    by checking the fake's as_of_calls list recorded None, not by
    inspecting call signatures (which can't detect a kwarg that was
    simply never passed vs. passed as None)."""
    engines = [FakeVotingEngine("TechnicalEngine")]
    engine = _build_engine(engines)
    engine.decide("BTC-USD")
    assert engines[0].as_of_calls == [None]


def test_decide_with_as_of_passes_it_to_every_registered_engine():
    engines = [FakeVotingEngine("TechnicalEngine"), FakeVotingEngine("FundamentalEngine")]
    engine = _build_engine(engines)
    as_of = datetime(2025, 6, 15, 23, 59, 59, tzinfo=timezone.utc)
    engine.decide("BTC-USD", as_of=as_of)
    assert engines[0].as_of_calls == [as_of]
    assert engines[1].as_of_calls == [as_of]


def test_decide_with_as_of_does_not_persist():
    repo = FakeExecutionRepository()
    engine = _build_engine([FakeVotingEngine("TechnicalEngine")], repo=repo)
    as_of = datetime(2025, 6, 15, 23, 59, 59, tzinfo=timezone.utc)
    output = engine.decide("BTC-USD", as_of=as_of)
    assert output.decision == Prediction.BUY  # still returns a real result
    assert repo.saved == []  # but nothing was persisted


def test_decide_without_as_of_still_persists_unchanged():
    """Regression test: the as_of feature must not affect the default
    (as_of=None) persistence behavior at all."""
    repo = FakeExecutionRepository()
    engine = _build_engine([FakeVotingEngine("TechnicalEngine")], repo=repo)
    output = engine.decide("BTC-USD")
    assert repo.saved == [output]


def test_decide_with_as_of_sets_output_timestamp_to_as_of():
    engine = _build_engine([FakeVotingEngine("TechnicalEngine")])
    as_of = datetime(2025, 6, 15, 23, 59, 59, tzinfo=timezone.utc)
    output = engine.decide("BTC-USD", as_of=as_of)
    assert output.timestamp == as_of


def test_decide_without_as_of_sets_output_timestamp_to_now():
    """Regression test: the default must still stamp real wall-clock
    time, not silently default to None or epoch."""
    before = datetime.now(timezone.utc)
    engine = _build_engine([FakeVotingEngine("TechnicalEngine")])
    output = engine.decide("BTC-USD")
    after = datetime.now(timezone.utc)
    assert before <= output.timestamp <= after


class _LegacyVotingEngineWithoutAsOf:
    """Simulates one of the 24+ OTHER vote() implementations found
    elsewhere in this codebase (pipeline/learning/shadow test fakes,
    ml_training/shadow/adapter.py) that only implement vote(self,
    symbol) - no as_of parameter at all, and are NOT modified by this
    plan. This class is the core safety proof for the whole design."""
    engine_name = "LegacyEngine"
    engine_version = "v1"

    def vote(self, symbol: str) -> EngineVote:
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version,
            prediction=Prediction.BUY, confidence=0.7, expected_return=1.0,
            volatility=1.0, evidence=[],
        )


def test_decide_without_as_of_works_with_an_engine_that_has_no_as_of_parameter_at_all():
    """Proves every one of the 24+ other vote() implementations in this
    codebase needs ZERO changes: a plain vote(self, symbol) engine works
    exactly as before when as_of is omitted (the overwhelming majority
    of all real calls, today and after this change)."""
    engine = _build_engine([_LegacyVotingEngineWithoutAsOf()])
    output = engine.decide("BTC-USD")  # no as_of - must not raise
    assert output.decision == Prediction.BUY


def test_decide_with_as_of_gracefully_skips_an_engine_without_as_of_support():
    """A replay call against an engine that was never updated for as_of
    raises TypeError inside engine.vote(symbol, as_of=as_of) - decide()'s
    EXISTING per-engine exception isolation (the same mechanism that
    already handles any other engine failure, see
    test_decide_ignores_an_engine_that_raises above) catches this and
    simply excludes that engine's vote, rather than crashing the whole
    replay. This is why the backtest script only ever registers
    TechnicalEngine into its own replay-mode registry - any engine not
    updated for as_of degrades gracefully if it's ever accidentally
    included, it doesn't blow up the call."""
    engine = _build_engine([_LegacyVotingEngineWithoutAsOf()])
    as_of = datetime(2025, 6, 15, 23, 59, 59, tzinfo=timezone.utc)
    output = engine.decide("BTC-USD", as_of=as_of)  # must not raise
    assert output.engine_results == []
    assert output.data_sufficiency == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_decision_engine_service.py -k "as_of" -v
```

Expected: FAIL — `FakeVotingEngine.vote()` (before your edit) doesn't accept `as_of`, and `DecisionEngine.decide()` doesn't accept it either.

- [ ] **Step 3: Implement**

First, document the capability on the Protocol itself (zero functional effect — Python's `@runtime_checkable Protocol` only checks that a `vote` attribute/method exists via `isinstance()`, never its exact parameter list, so this change requires no update to any of the 24+ other `vote()` implementations found in this codebase; it exists purely so a future reader of `VotingEngineProtocol` can see this capability is supported). In `backend/src/decision_engine/interfaces.py`, add `from datetime import datetime` and `Optional` to the `typing` import, then replace:

```python
    def vote(self, symbol: str) -> EngineVote: ...
```

With:

```python
    def vote(self, symbol: str, as_of: Optional[datetime] = None) -> EngineVote: ...
```

Now, in `backend/src/decision_engine/service.py`, add `from typing import ... Optional` is already imported; add `from datetime import datetime, timezone` is already imported. Replace:

```python
    def decide(self, symbol: str, strict: bool = False) -> DecisionOutput:
        """Runs every registered voting engine for `symbol` and returns a
        single aggregated `DecisionOutput`.

        With `strict=False` (the default), a symbol with zero valid votes
        still produces a DecisionOutput — a neutral HOLD with
        confidence=0.0 and data_sufficiency=0.0 — rather than raising, so
        one badly-behaved or not-yet-registered engine can never crash a
        caller. With `strict=True`, `NoValidVotesError` is raised instead,
        for callers (e.g. a future monitoring/learning job) that need to
        detect a total voting failure explicitly.
        """
        started_at = time.perf_counter()
        registered = self.registry.all()
        votes = self._collect_valid_votes(symbol, registered)

        if not votes and strict:
            raise NoValidVotesError(symbol)

        weights = {vote.engine_name: self.weight_provider.get_weight(vote.engine_name) for vote in votes}
        aggregation = aggregate_votes(votes, weights)

        data_sufficiency = (len(votes) / len(registered)) if registered else 0.0

        output = DecisionOutput(
            symbol=symbol,
            decision=aggregation.decision,
            confidence=aggregation.confidence,
            expected_return=aggregation.expected_return,
            expected_volatility=aggregation.expected_volatility,
            aggregation_strategy_version=self.config.aggregation_strategy_version,
            data_sufficiency=data_sufficiency,
            evidence=aggregation.evidence,
            engine_results=votes,
            timestamp=datetime.now(timezone.utc),
        )

        self._persist(output)

        log_event(
            logger,
            component="decision_engine",
            module="decision_engine.service",
            operation="decide",
            status=STATUS_SUCCESS,
            symbol=symbol,
            decision=output.decision.value,
            confidence=output.confidence,
            valid_votes=len(votes),
            registered_engines=len(registered),
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return output

    def _collect_valid_votes(self, symbol: str, engines: list) -> List[EngineVote]:
        votes: List[EngineVote] = []
        for engine in engines:
            engine_name = getattr(engine, "engine_name", type(engine).__name__)
            try:
                vote = engine.vote(symbol)
            except Exception as exc:
```

With:

```python
    def decide(self, symbol: str, strict: bool = False, as_of: Optional[datetime] = None) -> DecisionOutput:
        """Runs every registered voting engine for `symbol` and returns a
        single aggregated `DecisionOutput`.

        With `strict=False` (the default), a symbol with zero valid votes
        still produces a DecisionOutput — a neutral HOLD with
        confidence=0.0 and data_sufficiency=0.0 — rather than raising, so
        one badly-behaved or not-yet-registered engine can never crash a
        caller. With `strict=True`, `NoValidVotesError` is raised instead,
        for callers (e.g. a future monitoring/learning job) that need to
        detect a total voting failure explicitly.

        `as_of`, when given, replays what this decision would have been
        on that historical date instead of "now": it is passed to
        `engine.vote(symbol, as_of=as_of)` ONLY when not None (every live
        caller omits it, so every engine currently registered anywhere in
        this codebase - including the 24+ test fakes/adapters that only
        implement `vote(self, symbol)` - is completely unaffected; only
        an engine actually registered into a replay call needs to accept
        this kwarg, which today is just `TechnicalEngine`). A replay call
        also skips `self._persist()` entirely (a backtest can run
        thousands of calls; persisting synthetic historical decisions
        into `decision_engine_executions` would pollute the same table
        real live decisions are monitored through) and stamps
        `output.timestamp` with `as_of` itself rather than real
        wall-clock time, so a caller inspecting a batch of replayed
        DecisionOutputs can tell which historical date each one
        represents.
        """
        started_at = time.perf_counter()
        registered = self.registry.all()
        votes = self._collect_valid_votes(symbol, registered, as_of=as_of)

        if not votes and strict:
            raise NoValidVotesError(symbol)

        weights = {vote.engine_name: self.weight_provider.get_weight(vote.engine_name) for vote in votes}
        aggregation = aggregate_votes(votes, weights)

        data_sufficiency = (len(votes) / len(registered)) if registered else 0.0

        output = DecisionOutput(
            symbol=symbol,
            decision=aggregation.decision,
            confidence=aggregation.confidence,
            expected_return=aggregation.expected_return,
            expected_volatility=aggregation.expected_volatility,
            aggregation_strategy_version=self.config.aggregation_strategy_version,
            data_sufficiency=data_sufficiency,
            evidence=aggregation.evidence,
            engine_results=votes,
            timestamp=as_of if as_of is not None else datetime.now(timezone.utc),
        )

        if as_of is None:
            self._persist(output)

        log_event(
            logger,
            component="decision_engine",
            module="decision_engine.service",
            operation="decide",
            status=STATUS_SUCCESS,
            symbol=symbol,
            decision=output.decision.value,
            confidence=output.confidence,
            valid_votes=len(votes),
            registered_engines=len(registered),
            as_of=as_of.isoformat() if as_of is not None else None,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return output

    def _collect_valid_votes(
        self, symbol: str, engines: list, as_of: Optional[datetime] = None
    ) -> List[EngineVote]:
        votes: List[EngineVote] = []
        for engine in engines:
            engine_name = getattr(engine, "engine_name", type(engine).__name__)
            try:
                vote = engine.vote(symbol, as_of=as_of) if as_of is not None else engine.vote(symbol)
            except Exception as exc:
```

(The rest of `_collect_valid_votes`'s body — the `validate_vote`/append logic after the `except` block — is unchanged; only the one `try:` line and the method's own signature change.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_decision_engine_service.py -v
```

Expected: ALL tests in this file pass (the new ones, and every pre-existing one — this is the proof that zero existing behavior changed).

- [ ] **Step 5: Commit**

```bash
git add backend/src/decision_engine/interfaces.py backend/src/decision_engine/service.py backend/src/tests/test_decision_engine_service.py
git commit -m "feat: thread as_of through DecisionEngine.decide() for point-in-time replay

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Technical engine's point-in-time feature read path

**Files:**
- Modify: `backend/src/engines/technical/feature_adapter.py` (`TechnicalFeatureAdapter.get_features`, new `_resolve_as_of`)
- Modify: `backend/src/engines/technical/engine.py` (`TechnicalEngine.analyze`, `TechnicalEngine.vote`)
- Test: find and modify the existing test file for `TechnicalFeatureAdapter` (search: `grep -rln "TechnicalFeatureAdapter" backend/src/tests/`) and/or `TechnicalEngine` (search: `grep -rln "class TechnicalEngine\b" backend/src/tests/` won't work since that's not a test — search `grep -rln "TechnicalEngine(" backend/src/tests/`)

**Interfaces:**
- Consumes: Task 1's `decide(symbol, as_of=...)` — this task is what makes the Technical engine actually respond correctly when called that way.
- Produces: `TechnicalEngine.vote(self, symbol: str, as_of: Optional[datetime] = None) -> EngineVote`, satisfying what Task 1's `_collect_valid_votes` now calls conditionally. Task 3/4 depend on this working correctly end-to-end.

**Context:** Live reads go through `resolve_features()` → `feature_store.get_latest_feature()` (always "now") with a compute-fresh fallback. For a historical replay, compute-fresh is meaningless (you can't "freshly compute" what RSI was on a date two years ago from today's live OHLCV) — the as_of path must query ONLY the already-backfilled historical data via `feature_store.get_feature_as_of(..., respect_ingestion_time=True)`, and simply report whatever is missing as missing (no fallback).

- [ ] **Step 1: Write the failing tests**

First find the existing test file(s):

```bash
cd backend && grep -rln "TechnicalFeatureAdapter\|TechnicalEngine(" src/tests/
```

Read whichever file(s) that finds to confirm their current fixture/import style, then add tests following that same style. In the feature-adapter test file, add:

```python
def test_get_features_with_as_of_queries_point_in_time_with_ingestion_guard(monkeypatch):
    calls = []

    class _FakeFeatureStore:
        def get_feature_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            calls.append((symbol, feature_name, as_of, respect_ingestion_time))
            return None  # nothing found - the "all missing" case, tested separately below

        def get_latest_feature(self, symbol, feature_name):
            raise AssertionError("get_latest_feature must never be called when as_of is given")

    adapter = TechnicalFeatureAdapter(feature_store=_FakeFeatureStore(), config=TechnicalEngineConfig.from_env())
    as_of = datetime(2025, 6, 15, 23, 59, 59, tzinfo=timezone.utc)

    adapter.get_features("THYAO.IS", as_of=as_of)

    assert len(calls) == len(ALL_FEATURE_NAMES)
    for symbol, feature_name, called_as_of, respect_ingestion_time in calls:
        assert symbol == "THYAO.IS"
        assert called_as_of == as_of
        assert respect_ingestion_time is True
    assert {name for _, name, _, _ in calls} == set(ALL_FEATURE_NAMES)


def test_get_features_with_as_of_returns_only_found_values(monkeypatch):
    as_of = datetime(2025, 6, 15, 23, 59, 59, tzinfo=timezone.utc)
    found_name = ALL_FEATURE_NAMES[0]

    class _FakeRecord:
        def __init__(self, value):
            self.value = value

    class _FakeFeatureStore:
        def get_feature_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            return _FakeRecord(42.0) if feature_name == found_name else None

        def get_latest_feature(self, symbol, feature_name):
            raise AssertionError("must not be called")

    adapter = TechnicalFeatureAdapter(feature_store=_FakeFeatureStore(), config=TechnicalEngineConfig.from_env())
    resolution = adapter.get_features("THYAO.IS", as_of=as_of)

    assert resolution.values == {found_name: 42.0}
    assert found_name in resolution.from_cache


def test_get_features_with_as_of_all_missing_returns_empty_resolution():
    """Review Focus: a historical date with zero backfilled data must
    produce an honestly-empty resolution (and therefore, downstream,
    confidence=0.0/HOLD), never a confident-looking result."""
    as_of = datetime(2020, 1, 1, tzinfo=timezone.utc)  # before any real history exists

    class _FakeFeatureStore:
        def get_feature_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            return None

        def get_latest_feature(self, symbol, feature_name):
            raise AssertionError("must not be called")

    adapter = TechnicalFeatureAdapter(feature_store=_FakeFeatureStore(), config=TechnicalEngineConfig.from_env())
    resolution = adapter.get_features("THYAO.IS", as_of=as_of)

    assert resolution.values == {}
    assert resolution.from_cache == []
    assert resolution.computed_fresh == []


def test_get_features_without_as_of_still_uses_the_live_path_unchanged():
    """Regression test: confirm the existing live resolve_features()
    code path is still reached when as_of is omitted - read whichever
    existing test(s) in this file already cover resolve_features()
    being called; if one exists, it already proves this. If not, add:"""
    # (Only add this test if no existing test in this file already proves
    # get_features(symbol) with no as_of calls resolve_features/
    # get_latest_feature - check first before duplicating coverage.)
```

Also add, in whichever test file covers `TechnicalEngine` (not just the feature adapter):

```python
def test_vote_with_as_of_passes_it_through_to_get_features(monkeypatch):
    captured = {}

    class _FakeAdapter:
        def get_features(self, symbol, as_of=None):
            captured["symbol"] = symbol
            captured["as_of"] = as_of
            return FeatureResolution(values={}, from_cache=[], computed_fresh=[])

    engine = TechnicalEngine(feature_adapter=_FakeAdapter())
    as_of = datetime(2025, 6, 15, 23, 59, 59, tzinfo=timezone.utc)
    engine.vote("THYAO.IS", as_of=as_of)

    assert captured["as_of"] == as_of


def test_vote_without_as_of_still_calls_get_features_with_none():
    """Regression test."""
    captured = {}

    class _FakeAdapter:
        def get_features(self, symbol, as_of=None):
            captured["as_of"] = as_of
            return FeatureResolution(values={}, from_cache=[], computed_fresh=[])

    engine = TechnicalEngine(feature_adapter=_FakeAdapter())
    engine.vote("THYAO.IS")

    assert captured["as_of"] is None
```

(Check the exact existing imports in each test file before adding — `FeatureResolution`, `TechnicalFeatureAdapter`, `TechnicalEngine`, `TechnicalEngineConfig`, `ALL_FEATURE_NAMES`, `datetime`/`timezone` may already be imported, or may need adding.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/ -k "as_of and (technical or feature_adapter)" -v
```

Expected: FAIL — `get_features`/`analyze`/`vote` don't accept `as_of` yet.

- [ ] **Step 3: Implement**

In `backend/src/engines/technical/feature_adapter.py`, add `from datetime import datetime` to imports, then replace:

```python
    def get_features(self, symbol: str) -> FeatureResolution:
        resolution = resolve_features(
            self.feature_store, symbol, ALL_FEATURE_NAMES, self.config.max_feature_age_seconds, self._compute_all,
        )
        log_event(
            logger, component="technical_engine", module="engines.technical.feature_adapter",
            operation="get_features", status=STATUS_SUCCESS, symbol=symbol,
            features_from_cache=len(resolution.from_cache),
            features_computed_fresh=len(resolution.computed_fresh),
        )
        return resolution
```

With:

```python
    def get_features(self, symbol: str, as_of: Optional[datetime] = None) -> FeatureResolution:
        if as_of is not None:
            resolution = self._resolve_as_of(symbol, as_of)
            log_event(
                logger, component="technical_engine", module="engines.technical.feature_adapter",
                operation="get_features", status=STATUS_SUCCESS, symbol=symbol,
                as_of=as_of.isoformat(), features_found=len(resolution.values),
            )
            return resolution

        resolution = resolve_features(
            self.feature_store, symbol, ALL_FEATURE_NAMES, self.config.max_feature_age_seconds, self._compute_all,
        )
        log_event(
            logger, component="technical_engine", module="engines.technical.feature_adapter",
            operation="get_features", status=STATUS_SUCCESS, symbol=symbol,
            features_from_cache=len(resolution.from_cache),
            features_computed_fresh=len(resolution.computed_fresh),
        )
        return resolution

    def _resolve_as_of(self, symbol: str, as_of: datetime) -> FeatureResolution:
        """Point-in-time resolution for historical replay (decision_engine
        backtesting) - queries ONLY the already-backfilled historical
        Feature Store via get_feature_as_of(respect_ingestion_time=True),
        with no live-compute fallback: "freshly computing" a historical
        date's RSI from today's live OHLCV would be meaningless. A
        feature with no backfilled row for this exact date stays
        missing, honestly - it is never silently filled in."""
        resolution = FeatureResolution()
        for name in ALL_FEATURE_NAMES:
            record = self.feature_store.get_feature_as_of(symbol, name, as_of, respect_ingestion_time=True)
            if record is not None:
                resolution.values[name] = record.value
                resolution.from_cache.append(name)
        return resolution
```

In `backend/src/engines/technical/engine.py`, add `from datetime import datetime` to imports, then replace:

```python
    def analyze(self, symbol: str) -> TechnicalAnalysisResult:
        started_at = time.perf_counter()
        resolution = self.feature_adapter.get_features(symbol)
```

With:

```python
    def analyze(self, symbol: str, as_of: Optional[datetime] = None) -> TechnicalAnalysisResult:
        started_at = time.perf_counter()
        resolution = self.feature_adapter.get_features(symbol, as_of=as_of)
```

And replace:

```python
    def vote(self, symbol: str) -> EngineVote:
        analysis = self.analyze(symbol)
```

With:

```python
    def vote(self, symbol: str, as_of: Optional[datetime] = None) -> EngineVote:
        analysis = self.analyze(symbol, as_of=as_of)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/ -k "technical or feature_adapter" -v
```

Expected: all pass, including every pre-existing test in both files (proving zero behavior change for the no-`as_of` path).

- [ ] **Step 5: Commit**

```bash
git add backend/src/engines/technical/feature_adapter.py backend/src/engines/technical/engine.py backend/src/tests/
git commit -m "feat: give TechnicalEngine a point-in-time (as_of) feature read path

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Backtest script

**Files:**
- Create: `backend/src/scripts/backtest_decision_engine.py`
- Test: `backend/src/tests/test_backtest_decision_engine.py`

**Interfaces:**
- Consumes: `decide(symbol, as_of=...)` (Task 1), the Technical engine's working `as_of` path (Task 2), `research.ml_trainer.SYMBOLS`/`FORWARD_DAYS`/`THRESHOLD_UP` (existing, unchanged), `scripts.backfill_feature_store.trading_days_in_range(start, end, include_weekends=False)` (existing, unchanged), `providers.binance_provider.BinanceProvider.fetch_ohlcv_range` (existing, from the stabilization plan).
- Produces: a report file and console output; no interface other tasks depend on (Task 4 just runs this script for real).

**Context:** This script must NOT reimplement Technical's voting logic — it only supplies `as_of` to the real `decide()` and interprets the real `DecisionOutput`. It needs each symbol's REAL historical closing prices (not stored in the Feature Store, which only holds derived indicator values) to compute realized forward returns — fetched once per symbol for the whole backtest window, reusing the exact crypto/equity routing the stabilization plan already built (`BinanceProvider.fetch_ohlcv_range` for `-USD` symbols, `yf.Ticker(...).history()` for everything else), not yfinance's period-only interface.

Per the Review Focus: `Prediction.HOLD` is not a directional call and must be excluded from accuracy/precision/recall — but counted and reported as an abstention rate.

- [ ] **Step 1: Write the failing tests**

Create `backend/src/tests/test_backtest_decision_engine.py`:

```python
"""Tests for scripts/backtest_decision_engine.py's core evaluation loop.
Uses a fake DecisionEngine (never a real decide() call) so this suite
never touches Postgres/Redis - it tests the backtest's OWN logic
(direction-labeling, HOLD exclusion, accuracy/baseline math), not
decision_engine's, which Tasks 1-2's own tests already cover."""
from datetime import datetime, timezone

import pytest

from decision_engine.models import DecisionOutput, Prediction
from scripts.backtest_decision_engine import evaluate_decisions


def _output(decision, day):
    return DecisionOutput(
        symbol="TEST", decision=decision, confidence=0.8, expected_return=0.0,
        expected_volatility=0.0, aggregation_strategy_version="v1",
        data_sufficiency=1.0, evidence=[], engine_results=[], timestamp=day,
    )


def test_evaluate_decisions_excludes_hold_from_accuracy_but_counts_it():
    decisions = [
        (_output(Prediction.BUY, datetime(2025, 1, 1, tzinfo=timezone.utc)), True),   # correct BUY
        (_output(Prediction.HOLD, datetime(2025, 1, 2, tzinfo=timezone.utc)), True),  # abstention - excluded
        (_output(Prediction.SELL, datetime(2025, 1, 3, tzinfo=timezone.utc)), True),  # wrong SELL (actual was up)
    ]
    result = evaluate_decisions(decisions)
    assert result["n_directional_samples"] == 2          # BUY + SELL only, HOLD excluded
    assert result["n_hold"] == 1
    assert result["accuracy"] == pytest.approx(0.5)       # 1 correct of 2 directional


def test_evaluate_decisions_all_hold_reports_zero_directional_samples_not_an_error():
    decisions = [(_output(Prediction.HOLD, datetime(2025, 1, 1, tzinfo=timezone.utc)), True)]
    result = evaluate_decisions(decisions)
    assert result["n_directional_samples"] == 0
    assert result["n_hold"] == 1
    assert result["accuracy"] == 0.0  # honest zero, not a crash/NaN


def test_evaluate_decisions_majority_baseline_matches_actual_distribution():
    decisions = [
        (_output(Prediction.BUY, datetime(2025, 1, 1, tzinfo=timezone.utc)), True),
        (_output(Prediction.BUY, datetime(2025, 1, 2, tzinfo=timezone.utc)), True),
        (_output(Prediction.SELL, datetime(2025, 1, 3, tzinfo=timezone.utc)), False),
    ]
    result = evaluate_decisions(decisions)
    # 2 of 3 actual outcomes were "up" (True) - majority baseline = 2/3
    assert result["majority_baseline"] == pytest.approx(2 / 3)
```

(`evaluate_decisions(decisions: List[Tuple[DecisionOutput, bool]]) -> dict` takes a list of (decision, actual_was_up) pairs — this signature keeps the function pure and trivially testable without any real fetching, matching the pattern the rest of the script's main loop feeds into it.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_backtest_decision_engine.py -v
```

Expected: FAIL — `scripts.backtest_decision_engine` doesn't exist yet.

- [ ] **Step 3: Implement**

Create `backend/src/scripts/backtest_decision_engine.py`:

```python
"""OptiTrade — decision_engine point-in-time backtest (Technical-only).

Usage (from backend/src):
  python scripts/backtest_decision_engine.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]

Measures decision_engine's own historical decision quality for the
FIRST TIME - using ONLY the Technical voting engine, replayed via
decide(symbol, as_of=historical_day) against the already-backfilled
Feature Store (see docs/superpowers/specs/2026-10-03-decision-engine-
backtest-design.md). This is NOT the full 3-engine live decision:
Fundamental and News cannot be backfilled with current data sources
(yfinance .info/news have no historical query capability) and are
deliberately excluded from this backtest's own engine registry.

Reuses the real decide()/TechnicalEngine code for the replay - this
script supplies as_of and interprets the real DecisionOutput it gets
back, never reimplementing voting/aggregation logic itself.

Direction-labeling matches research/ml_trainer.py's own convention
(FORWARD_DAYS, THRESHOLD_UP) for direct comparability with this
project's existing ML accuracy reports.
"""
from __future__ import annotations

import argparse
import logging
import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

from decision_engine.models import DecisionOutput, Prediction
from decision_engine.registry import VotingEngineRegistry
from decision_engine.service import DecisionEngine
from engines.technical.engine import TechnicalEngine
from providers.binance_provider import BinanceProvider
from research.ml_trainer import FORWARD_DAYS, SYMBOLS, THRESHOLD_UP
from scripts.backfill_feature_store import trading_days_in_range

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def _fetch_symbol_history(symbol: str, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
    """Real historical closing prices for computing realized forward
    returns - NOT stored in the Feature Store (which only holds derived
    indicator values). Reuses the exact crypto/equity routing
    scripts/backfill_feature_store.py already established: Binance's
    date-bounded range fetch for -USD symbols (yfinance's period-only
    interface can't express this range), yfinance directly otherwise."""
    if symbol.upper().endswith("-USD"):
        hist = BinanceProvider().fetch_ohlcv_range(symbol, start, end)
        if hist is not None and not hist.empty:
            return hist
        logger.warning("%s: Binance range fetch failed, falling back to yfinance", symbol)
    try:
        return yf.Ticker(symbol).history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
    except Exception as exc:
        logger.warning("%s: yfinance fetch failed: %s", symbol, exc)
        return None


def evaluate_decisions(decisions: List[Tuple[DecisionOutput, bool]]) -> dict:
    """Pure evaluation: given (DecisionOutput, actual_was_up) pairs,
    computes accuracy/precision/recall against a naive majority-class
    baseline - EXCLUDING HOLD decisions from the directional count
    (HOLD is an abstention, not a directional prediction; scoring it as
    a miss would corrupt the accuracy number for a system that is
    supposed to be rewarded for correctly declining to call an
    ambiguous day, not punished for it)."""
    directional = [(o, actual) for o, actual in decisions if o.decision != Prediction.HOLD]
    n_hold = len(decisions) - len(directional)

    if not directional:
        return {
            "n_samples": len(decisions), "n_directional_samples": 0, "n_hold": n_hold,
            "accuracy": 0.0, "majority_baseline": 0.0, "precision": 0.0, "recall": 0.0,
        }

    y_true = [1 if actual else 0 for _, actual in directional]
    y_pred = [1 if o.decision == Prediction.BUY else 0 for o, _ in directional]

    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    accuracy = correct / len(directional)
    up_fraction = sum(y_true) / len(y_true)
    majority_baseline = max(up_fraction, 1 - up_fraction)

    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    return {
        "n_samples": len(decisions), "n_directional_samples": len(directional), "n_hold": n_hold,
        "accuracy": accuracy, "majority_baseline": majority_baseline,
        "precision": precision, "recall": recall,
    }


def backtest_symbol(engine: DecisionEngine, symbol: str, days: List[datetime]) -> List[Tuple[DecisionOutput, bool]]:
    """Fetches `symbol`'s real history once, then for each day in `days`
    replays decide(symbol, as_of=day_end_utc) and pairs it with the
    REALIZED direction from day to day+FORWARD_DAYS."""
    fetch_start = days[0] - timedelta(days=5)
    fetch_end = days[-1] + timedelta(days=FORWARD_DAYS + 5)
    hist = _fetch_symbol_history(symbol, fetch_start, fetch_end)
    if hist is None or hist.empty:
        logger.warning("%s: no history available, skipping entirely", symbol)
        return []

    results: List[Tuple[DecisionOutput, bool]] = []
    for day in days:
        day_end_utc = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)
        try:
            future_rows = hist[hist.index.date > day.date()]
            if len(future_rows) < FORWARD_DAYS:
                continue  # not enough real future data yet to score this day
            current_rows = hist[hist.index.date <= day.date()]
            if current_rows.empty:
                continue
            current_price = float(current_rows["Close"].iloc[-1])
            future_price = float(future_rows["Close"].iloc[FORWARD_DAYS - 1])
            actual_up = ((future_price - current_price) / current_price) * 100 > THRESHOLD_UP

            output = engine.decide(symbol, as_of=day_end_utc)
            results.append((output, actual_up))
        except Exception as exc:
            logger.warning("%s: failed to backtest %s (%s: %s), skipping this day", symbol, day.date(), type(exc).__name__, exc)
            continue
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=str, default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, metavar="YYYY-MM-DD")
    args = parser.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc) if args.end else datetime.now(timezone.utc)
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc) if args.start else end - timedelta(days=730)

    registry = VotingEngineRegistry()
    registry.register(TechnicalEngine())
    engine = DecisionEngine(registry=registry)

    print("=" * 70)
    print("OptiTrade - decision_engine Point-in-Time Backtest (Technical-only)")
    print(f"Range: {start.date().isoformat()} .. {end.date().isoformat()} | Symbols: {len(SYMBOLS)}")
    print("NOTE: this measures ONLY the Technical voting engine's historical")
    print("decisions - NOT the full 3-engine live decision (Fundamental/News")
    print("cannot be backfilled with current data sources - see the design spec).")
    print("=" * 70)

    all_results: List[Tuple[DecisionOutput, bool]] = []
    per_symbol_counts: Dict[str, int] = {}
    for symbol in SYMBOLS:
        days = trading_days_in_range(start, end, include_weekends=symbol.upper().endswith("-USD"))
        print(f"  Backtesting: {symbol}...", end=" ", flush=True)
        try:
            results = backtest_symbol(engine, symbol, days)
        except Exception as exc:
            logger.warning("%s: backtest_symbol raised %s: %s, skipping entirely", symbol, type(exc).__name__, exc)
            results = []
        per_symbol_counts[symbol] = len(results)
        all_results.extend(results)
        print(f"{len(results)} days evaluated")

    evaluation = evaluate_decisions(all_results)

    lines = [
        f"# decision_engine Point-in-Time Backtest — {datetime.now(timezone.utc).date().isoformat()}", "",
        "**Technical voting engine ONLY — NOT the full 3-engine live decision.**",
        "Fundamental and News engines cannot be backfilled with current data",
        "sources (see docs/superpowers/specs/2026-10-03-decision-engine-backtest-design.md) and are excluded from this backtest's own engine registry entirely.",
        "", "## Result", "",
        "| Samples | Directional samples | HOLD (abstentions) | Accuracy | Majority baseline | Precision | Recall |",
        "|---|---|---|---|---|---|---|",
        f"| {evaluation['n_samples']} | {evaluation['n_directional_samples']} | {evaluation['n_hold']} | "
        f"{evaluation['accuracy']:.3f} | {evaluation['majority_baseline']:.3f} | "
        f"{evaluation['precision']:.3f} | {evaluation['recall']:.3f} |",
        "", f"Per-symbol sample counts: {per_symbol_counts}",
    ]
    report = "\n".join(lines)
    print(report)
    with open(f"../../docs/decision-engine-backtest-report-{datetime.now(timezone.utc).date().isoformat()}.md", "w") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_backtest_decision_engine.py -v
```

Expected: all pass. This test run does NOT touch Postgres/Redis/yfinance — it only exercises `evaluate_decisions`, a pure function.

- [ ] **Step 5: Commit**

```bash
git add backend/src/scripts/backtest_decision_engine.py backend/src/tests/test_backtest_decision_engine.py
git commit -m "feat: add decision_engine Technical-only point-in-time backtest script

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Run the real backtest and report honestly

**Files:** none created/modified — this task runs the already-built `backend/src/scripts/backtest_decision_engine.py` for real.

**Interfaces:**
- Consumes: Tasks 1-3, the already-backfilled real Feature Store (from the earlier stabilization plan).
- Produces: a real, dated report with decision_engine's first-ever measured historical accuracy.

- [ ] **Step 1: Confirm you're pointed at the real database**

```bash
cd backend/src && ~/app/OptiTrade/venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from feature_store.offline_store import PostgresOfflineStore
store = PostgresOfflineStore()
conn = store._pool.getconn()
cur = conn.cursor()
cur.execute('SELECT count(*) FROM feature_store_records')
print('Current row count (expect six figures - the real backfilled data):', cur.fetchone())
store._pool.putconn(conn)
"
```

- [ ] **Step 2: Run the real backtest in the background**

```bash
cd backend/src && nohup ~/app/OptiTrade/venv/bin/python3 scripts/backtest_decision_engine.py --start 2024-10-02 --end 2026-10-02 > /tmp/backtest_decision_engine_run.log 2>&1 &
```

Monitor to completion — this makes real `decide()` calls (real Feature Store reads, no writes since `as_of` skips persistence) for ~16,000 symbol/day combinations plus per-symbol real OHLCV fetches; poll patiently rather than blocking, matching this project's established pattern for long-running real operations. If per-symbol progress logging shows every symbol returning 0 evaluated days, STOP and investigate (likely a bug) rather than letting the full run complete on a silently-broken path.

- [ ] **Step 3: Verify the result file was written and read it**

```bash
cat docs/decision-engine-backtest-report-*.md
```

Report the REAL accuracy/majority_baseline/precision/recall/n_hold numbers honestly in your task report — an unfavorable result (decision_engine's Technical-only historical accuracy also doesn't beat its own majority baseline) is a legitimate, acceptable, and valuable outcome, exactly like every other honest evaluation in this project so far.

- [ ] **Step 4: Confirm zero live-system side effects**

```bash
cd backend/src && ~/app/OptiTrade/venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from feature_store.offline_store import PostgresOfflineStore
store = PostgresOfflineStore()
conn = store._pool.getconn()
cur = conn.cursor()
cur.execute('SELECT count(*) FROM decision_engine_executions WHERE timestamp > now() - interval \'1 hour\'')
print('Real decision_engine_executions rows written in the last hour (expect 0 - the backtest must never persist):', cur.fetchone())
store._pool.putconn(conn)
"
```

Expected: `0`. If this is nonzero, STOP — it means Task 1's persistence-skip isn't actually working in the real deployed code path, a real bug to fix before this task is considered done.

- [ ] **Step 5: Commit the report**

```bash
git add docs/decision-engine-backtest-report-*.md
git commit -m "docs: first real decision_engine point-in-time backtest result

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

No code changes in this task — only the real data operation and its honest, committed report.
