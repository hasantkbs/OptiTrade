# Pre-Deploy Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every known real bug in the OptiTrade backend, redo the Feature Store backfill and ML candidate training against the REAL database (today's earlier work landed in a stale, wrong one), get an honest test/accuracy read on the corrected system, and only then redeploy `optitrade-api` on host `mayasoftlnx01`.

**Architecture:** Five sequential phases: (1) close the test-suite data-loss hazard and fix host→real-DB access, (2) correct the backfill's crypto data-source/weekend/idempotency/duplicate-write bugs in code only, (3) run the corrected backfill once against the real DB and get honest accuracy numbers for both the new ML candidate and `v2_xgb_model`, (4) fix a Docker image ownership bug, (5) run the full test suite and — only with explicit human go-ahead — redeploy.

**Tech Stack:** Python (FastAPI backend), PostgreSQL, Docker Compose, pytest, XGBoost/yfinance/Binance REST API.

**Spec:** `docs/superpowers/specs/2026-10-02-pre-deploy-stabilization-design.md`

## Global Constraints

- Every commit ends with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- No SHADOW or ACTIVE promotion of any ML model anywhere in this plan — the candidate retrained in Task 8 stays at CANDIDATE.
- The `optitrade-api` container's own `FEATURE_STORE_POSTGRES_HOST` must remain `postgres` (Docker-internal) — the new host port mapping (Task 2) is for host-side tooling/scripts only. Verify this explicitly in Task 10's post-deploy check.
- Task 6's backfill is a single, fresh run against the real DB with Tasks 3-5's fixes already applied — never run the old (pre-fix) backfill logic against the real DB, and never migrate/copy rows from the stale `localhost:5432` database.
- Report Task 8's retrained candidate's real out-of-sample result honestly, whatever it is. Bounded fine-tuning only: if the first real run doesn't beat the majority-class baseline, a few reasonable attempts (hyperparameters and/or feature set, documented) are in scope; if it still doesn't beat baseline after that, report the result and move on — do not iterate indefinitely chasing a number.
- The actual deploy command (end of Task 10) requires the user's **explicit, separate go-ahead at that specific point** — this is not something a subagent (or the controlling session) executes autonomously under Subagent-Driven Development's "don't stop between tasks" rule. It is called out again at that step below; do not skip the stop.
- `decision_engine`'s own historical-replay/backtesting capability remains out of scope for this plan.

---

### Task 1: Scope the test-suite cleanup DELETEs to each test's own data

**Files:**
- Modify: `backend/src/tests/test_ml_training_service.py` (the `service` fixture at the point it currently reads `svc = MLTrainingService(...); yield svc`, and `_cleanup()`, and both `test_run_training_job_end_to_end`/`test_run_training_job_raises_and_archives_experiment_on_insufficient_data` signatures)
- Modify: `backend/src/tests/test_ml_training_datasets.py` (the `dataset_repository` fixture's single `DELETE` statement)
- Test: the two files above are themselves the tests — this task's "test" is confirming they still pass and that a regression test proves the new scoping actually holds

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing other tasks depend on; this is a standalone safety fix.

**Context:** `test_ml_training_service.py`'s `_cleanup()` currently deletes by generic patterns (`ml_training_model_registry WHERE engine_name LIKE 'MLModel:%'`, `ml_training_runs WHERE model_id LIKE '%d-%'`, etc.) that match ANY real row, not just this test's own. This already deleted a real trained model's registry metadata once today. `test_ml_training_datasets.py`'s dataset-version cleanup (`WHERE name LIKE 'trader-%' OR name LIKE 'investor-%'`) is equally broad and matches real dataset names like `train_ml_candidate.py`'s own `trader-2024-10-01-2026-04-04`-style versions.

- [ ] **Step 1: Read both files' current cleanup code to confirm line numbers haven't shifted**

```bash
cd backend && grep -n "_cleanup\|DELETE FROM\|^def test_\|@pytest.fixture\|^def service" src/tests/test_ml_training_service.py
grep -n "DELETE FROM\|@pytest.fixture\|def dataset_repository" src/tests/test_ml_training_datasets.py
```

- [ ] **Step 2: Rewrite `test_ml_training_service.py`'s `service` fixture, `_cleanup()`, and both affected test functions**

Replace the `service` fixture and `_cleanup` function (currently):

```python
@pytest.fixture
def service(feature_store, config):
    fs, _start, _now = feature_store
    builder = DatasetBuilder(
        feature_extractor=FeatureExtractor(feature_store=fs), config=config, price_fetcher=_oscillating,
    )
    svc = MLTrainingService(
        datasets=DatasetService(builder=builder, repository=DatasetRepository(), config=config),
        config=config,
    )
    yield svc
    _cleanup(svc)


def _cleanup(svc: MLTrainingService) -> None:
    def _exec(pool, sql, params):
        conn = pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(sql, params)
        finally:
            pool.putconn(conn)

    _exec(svc.experiments.repository._pool, "DELETE FROM research_experiments WHERE author = %s", (_AUTHOR,))
    _exec(
        svc.hypothesis.repository._pool,
        "DELETE FROM research_hypotheses WHERE statement LIKE %s",
        ("A % model trained on%",),
    )
    _exec(svc.registry.repository._pool, "DELETE FROM ml_training_model_registry WHERE engine_name LIKE %s", ("MLModel:%",))
    _exec(svc.runs.repository._pool, "DELETE FROM ml_training_runs WHERE model_id LIKE %s", ("%d-%",))
    _exec(svc.datasets.repository._pool, "DELETE FROM ml_training_dataset_versions WHERE symbols::text LIKE %s", (f"%{_SYMBOL}%",))
    _exec(svc.calibration.repository._pool, "DELETE FROM ml_training_calibration_results WHERE model_id LIKE %s", ("%d-%",))
    _exec(svc.benchmarking.repository._pool, "DELETE FROM research_benchmark_results WHERE subject_a LIKE %s", ("%:selected",))
    _exec(svc.reports.repository._pool, "DELETE FROM research_reports WHERE title LIKE %s", ("Experiment Summary: ml_training:%",))
    _exec(
        svc.importance.feature_analysis_service.repository._pool,
        "DELETE FROM research_feature_importance WHERE engine_name LIKE %s", ("MLModel:%",),
    )
    _exec(svc.importance.feature_store.offline_store._pool, "DELETE FROM feature_store_records WHERE feature_name LIKE %s", ("shap_importance:%",))
```

With this (every DELETE that previously used a generic pattern now scopes to the exact model_id(s) this specific test run actually created — `ml_training_model_registry.engine_name`/`ml_training_runs.model_id`/`ml_training_calibration_results.model_id`/`research_feature_importance.engine_name`/`research_benchmark_results.subject_a`/`research_reports.title`/`feature_store_records.symbol` all either equal or embed `model_id` exactly, traced from `ml_training/service.py::run_training_job` and `ml_training/importance/service.py`; `research_hypotheses` has no column identifying its own test — its `statement` text is a generic template shared by every real run with the same algorithm/label/horizon — so it's scoped instead by first reading this test's own `research_experiments.hypothesis_id` before those experiment rows are deleted, since that FK only exists in that direction):

```python
@pytest.fixture
def service(feature_store, config):
    fs, _start, _now = feature_store
    builder = DatasetBuilder(
        feature_extractor=FeatureExtractor(feature_store=fs), config=config, price_fetcher=_oscillating,
    )
    svc = MLTrainingService(
        datasets=DatasetService(builder=builder, repository=DatasetRepository(), config=config),
        config=config,
    )
    created_model_ids: list = []
    yield svc, created_model_ids
    _cleanup(svc, created_model_ids)


def _cleanup(svc: MLTrainingService, model_ids: list) -> None:
    def _exec(pool, sql, params):
        conn = pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(sql, params)
        finally:
            pool.putconn(conn)

    def _fetch(pool, sql, params):
        conn = pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(sql, params)
                return [row[0] for row in cur.fetchall()]
        finally:
            pool.putconn(conn)

    # research_hypotheses has no column of its own identifying which
    # test created a given row - its `statement` text is a generic
    # template shared by every real run with the same
    # algorithm/label/horizon (see ml_training/service.py:228-230), so
    # it can't be scoped by LIKE without risking a real hypothesis
    # match. Read this test's own experiments' hypothesis_id BEFORE
    # deleting those experiments (the FK only exists in that
    # direction: research_experiments.hypothesis_id -> research_hypotheses.id).
    hypothesis_ids = _fetch(
        svc.experiments.repository._pool,
        "SELECT hypothesis_id FROM research_experiments WHERE author = %s", (_AUTHOR,),
    )
    if hypothesis_ids:
        _exec(svc.hypothesis.repository._pool, "DELETE FROM research_hypotheses WHERE id = ANY(%s)", (hypothesis_ids,))
    _exec(svc.experiments.repository._pool, "DELETE FROM research_experiments WHERE author = %s", (_AUTHOR,))

    if model_ids:
        _exec(svc.registry.repository._pool, "DELETE FROM ml_training_model_registry WHERE model_id = ANY(%s)", (model_ids,))
        _exec(svc.runs.repository._pool, "DELETE FROM ml_training_runs WHERE model_id = ANY(%s)", (model_ids,))
        _exec(svc.calibration.repository._pool, "DELETE FROM ml_training_calibration_results WHERE model_id = ANY(%s)", (model_ids,))
        _exec(
            svc.importance.feature_analysis_service.repository._pool,
            "DELETE FROM research_feature_importance WHERE engine_name = ANY(%s)",
            ([f"MLModel:{mid}" for mid in model_ids],),
        )
        _exec(
            svc.benchmarking.repository._pool,
            "DELETE FROM research_benchmark_results WHERE subject_a = ANY(%s)",
            ([f"{mid}:selected" for mid in model_ids],),
        )
        _exec(
            svc.reports.repository._pool,
            "DELETE FROM research_reports WHERE title LIKE ANY(%s)",
            ([f"%{mid}" for mid in model_ids],),  # title = f"Experiment Summary: {experiment.name}", and experiment.name always ends with model_id
        )
        _exec(
            svc.importance.feature_store.offline_store._pool,
            "DELETE FROM feature_store_records WHERE symbol = ANY(%s) AND feature_name LIKE %s",
            (model_ids, "%_importance:%"),  # symbol=model_id per importance/service.py:70; matches both shap_ and permutation_ prefixes (the old code only matched shap_)
        )
    _exec(svc.datasets.repository._pool, "DELETE FROM ml_training_dataset_versions WHERE symbols::text LIKE %s", (f"%{_SYMBOL}%",))
```

Then update both test functions that use the `service` fixture to destructure the new `(svc, created_model_ids)` tuple and append the real model_id after a successful run. Replace `test_run_training_job_end_to_end` (currently uses `service.run_training_job` / `service.registry.get` directly) with:

```python
def test_run_training_job_end_to_end(service, feature_store):
    svc, created_model_ids = service
    _fs, start, now = feature_store
    result = svc.run_training_job(
        author=_AUTHOR, symbols=[_SYMBOL], dataset_type=DatasetType.TRADER, label_name=LabelName.DIRECTION,
        horizon_days=1, algorithm=ModelAlgorithm.RANDOM_FOREST, start=start, end=now,
    )
    created_model_ids.append(result.registry_entry.model_id)

    assert result.experiment.id is not None
    assert result.experiment.status == ExperimentStatus.COMPLETED
    assert result.experiment.author == _AUTHOR

    assert result.training_run.id is not None
    assert result.training_run.status.value == "completed"
    assert result.training_run.dataset_id is not None

    assert result.registry_entry.id is not None
    assert result.registry_entry.promotion_state == PromotionState.CANDIDATE
    assert result.registry_entry.algorithm == ModelAlgorithm.RANDOM_FOREST
    assert result.registry_entry.label_name == LabelName.DIRECTION
    assert len(result.registry_entry.model_id) <= 32

    assert result.hypothesis_outcome in {
        HypothesisOutcome.ACCEPTED, HypothesisOutcome.REJECTED, HypothesisOutcome.INCONCLUSIVE,
    }

    assert result.report.id is not None
    assert result.report.content["experiment_id"] == result.experiment.id
    assert result.report.content["hypothesis"]["outcome"] == result.hypothesis_outcome.value

    # The registry entry is independently readable from a fresh service.
    fetched = svc.registry.get(result.registry_entry.model_id)
    assert fetched is not None
    assert fetched.metrics is not None


def test_run_training_job_raises_and_archives_experiment_on_insufficient_data(service, feature_store):
    svc, _created_model_ids = service
    _fs, start, now = feature_store
    with pytest.raises(InsufficientDataError):
        svc.run_training_job(
            author=_AUTHOR, symbols=["MLSVCTEST-NO-SUCH-SYMBOL"], dataset_type=DatasetType.TRADER,
            label_name=LabelName.DIRECTION, horizon_days=1, algorithm=ModelAlgorithm.RANDOM_FOREST,
            start=start, end=now,
        )

    experiments = svc.experiments.list_by_status(ExperimentStatus.ARCHIVED, limit=200)
    assert any(experiment.author == _AUTHOR for experiment in experiments)
```

`test_service_defaults_to_real_dependencies` (the third test in this file) doesn't use the `service` fixture — leave it untouched.

- [ ] **Step 3: Fix `test_ml_training_datasets.py`'s dataset-version cleanup**

Replace (in the `dataset_repository` fixture):

```python
cur.execute("DELETE FROM ml_training_dataset_versions WHERE name LIKE 'trader-%' OR name LIKE 'investor-%'")
```

With (reusing the exact `symbols::text LIKE` scoping pattern `test_ml_training_service.py`'s own dataset-version cleanup already correctly uses):

```python
cur.execute(
    "DELETE FROM ml_training_dataset_versions WHERE (name LIKE 'trader-%' OR name LIKE 'investor-%') AND symbols::text LIKE %s",
    (f"%{_SYMBOL}%",),
)
```

- [ ] **Step 4: Add a regression test proving the new scoping doesn't touch unrelated rows**

Add to `test_ml_training_service.py` (needs `ModelRegistryEntry`, `PromotionState` already imported; add a direct `ModelRegistryRepository` import if not already present at the top of the file):

```python
def test_cleanup_does_not_delete_a_different_models_registry_row(service, feature_store):
    """Regression test for today's real incident: _cleanup() used to
    match ANY registry row via `engine_name LIKE 'MLModel:%'`, which
    would have deleted a decoy "real" model's row too. Now it must only
    touch the model_ids this specific test run created."""
    svc, created_model_ids = service
    decoy_model_id = "decoy-unrelated-model-id"
    svc.registry.repository.save(
        ModelRegistryEntry(
            model_id=decoy_model_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1",
            dataset_id=1, hyperparameters={}, metrics={}, feature_list=["x"],
            label_name=LabelName.DIRECTION, horizon_days=1,
            training_date=datetime.now(timezone.utc), promotion_state=PromotionState.CANDIDATE,
            engine_name=f"MLModel:{decoy_model_id}", engine_version="v1", artifact_path="/tmp/decoy.joblib",
        )
    )
    try:
        _fs, start, now = feature_store
        result = svc.run_training_job(
            author=_AUTHOR, symbols=[_SYMBOL], dataset_type=DatasetType.TRADER, label_name=LabelName.DIRECTION,
            horizon_days=1, algorithm=ModelAlgorithm.RANDOM_FOREST, start=start, end=now,
        )
        created_model_ids.append(result.registry_entry.model_id)
        _cleanup(svc, created_model_ids)

        assert svc.registry.get(decoy_model_id) is not None  # decoy survives
        assert svc.registry.get(result.registry_entry.model_id) is None  # this test's own model is gone

        created_model_ids.clear()  # already cleaned up above; the fixture's own teardown would otherwise no-op harmlessly on an empty list anyway
    finally:
        svc.registry.repository._pool  # no-op touch to keep the pool import path warm; real cleanup below
        conn = svc.registry.repository._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM ml_training_model_registry WHERE model_id = %s", (decoy_model_id,))
        finally:
            svc.registry.repository._pool.putconn(conn)
```

(Check `ModelRegistryRepository`'s actual save method name — it may be `save`, `register`, or `create`; read `backend/src/ml_training/registry/repository.py` if `svc.registry.repository.save(...)` doesn't match, and use the real method name instead. `ModelRegistryEntry`'s exact required fields are in `backend/src/ml_training/models.py` — confirm against that file too, since this plan is written from earlier analysis and small field-set differences are possible.)

- [ ] **Step 5: Run the tests**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_ml_training_service.py src/tests/test_ml_training_datasets.py -v
```

Expected: all pass, including the new regression test. **This is the ONE place in this entire plan where running these two specific files is safe and required** — they're exactly the files being fixed, and by Step 2-3 their own cleanup no longer touches unrelated rows. Do not run any OTHER test file alongside them in the same command without first confirming its own cleanup fixtures are equally safe (most already are, per the earlier review — this task only had to fix these two files).

- [ ] **Step 6: Commit**

```bash
git add backend/src/tests/test_ml_training_service.py backend/src/tests/test_ml_training_datasets.py
git commit -m "fix: scope ml_training test cleanup DELETEs to each test's own data

$(echo)
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Add a host port mapping to the real Postgres and point backend/.env at it

**Files:**
- Modify: `docker-compose.override.yml` (repo root, NOT backend/) — add a `ports:` entry to the `postgres:` service block
- Modify: `backend/.env` and `backend/.env.example` — `FEATURE_STORE_POSTGRES_PORT`

**Interfaces:**
- Produces: from this task onward, every script run from the host venv (backfill, training, evaluation, pytest) connects to the REAL `optitrade-postgres` database. Tasks 5-8 depend on this.

**Context:** `docker-compose.override.yml` already documents (in its header comment) that `postgres` is "deliberately NOT re-exposed" because `backend/.env`'s `FEATURE_STORE_POSTGRES_HOST=localhost` points at "a pre-existing, separately-managed PostgreSQL instance bound to 127.0.0.1:5432" — this turned out to be a stale, wrong database (verified: it has today's earlier backfill/candidate-model work; the REAL `optitrade-postgres` container, reached via `docker exec optitrade-api` with `host=postgres`, had only 1,055 `feature_store_records` rows and 0 `ml_training_model_registry` rows at the same point in time). The real container's Postgres password was independently verified to already match `backend/.env`'s existing `FEATURE_STORE_POSTGRES_PASSWORD` value — only host/port need to change, not credentials.

- [ ] **Step 1: Add the port mapping to `docker-compose.override.yml`**

The file's `services:` section currently has:

```yaml
services:
  redis:
    ports:
      - "127.0.0.1:6379:6379"

  api:
    ports:
      - "127.0.0.1:8000:8000"
```

Change it to:

```yaml
services:
  redis:
    ports:
      - "127.0.0.1:6379:6379"

  api:
    ports:
      - "127.0.0.1:8000:8000"

  postgres:
    ports:
      - "127.0.0.1:5433:5432"
```

Also update the file's header comment — it currently says postgres is "deliberately NOT re-exposed here" because of the pre-existing `127.0.0.1:5432` instance. Replace that paragraph with:

```
# postgres is now exposed too, but on 5433 (not 5432) - 5432 is occupied
# by a separate, stale host-native PostgreSQL instance from an earlier
# setup (see docs/superpowers/specs/2026-10-02-pre-deploy-stabilization-design.md
# for how that was discovered and confirmed to be the wrong database).
# Binding 5432 here would conflict with that instance; 5433 gives host
# tooling (backfill/training scripts, pytest) a path to the REAL
# optitrade-postgres data without disturbing it.
```

This file is still never included in a production deploy (per its own existing closing comment, unchanged by this task) — the new port stays loopback-only and dev-only, same exposure class as the existing `redis`/`api` mappings.

- [ ] **Step 2: Update `backend/.env` and `backend/.env.example`**

In both files, change:
```
FEATURE_STORE_POSTGRES_PORT=5432
```
to:
```
FEATURE_STORE_POSTGRES_PORT=5433
```

In `backend/.env.example` specifically, add a one-line comment above it:
```
# 5433, not Postgres's default 5432 - see docker-compose.override.yml's
# postgres port-mapping comment for why.
FEATURE_STORE_POSTGRES_PORT=5433
```

`FEATURE_STORE_POSTGRES_HOST` stays `localhost` in both files — only the port changes; the host was already correct for host-side tooling.

- [ ] **Step 3: Apply the Compose change and verify connectivity**

```bash
cd /home/mayasoft/app/OptiTrade && docker compose up -d postgres
```

Expected: `optitrade-postgres` recreated (brief restart) with the new port mapping, health check passes.

```bash
cd backend/src && ~/app/OptiTrade/venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from feature_store.offline_store import PostgresOfflineStore
store = PostgresOfflineStore()
conn = store._pool.getconn()
cur = conn.cursor()
cur.execute('SELECT count(*) FROM feature_store_records')
print('feature_store_records via new port 5433:', cur.fetchone()[0])
store._pool.putconn(conn)
"
```

Expected output: a row count matching what `docker exec optitrade-api`'s internal query showed earlier (around 1,055, give or take whatever real-time writes have landed since) — confirming this now reaches the REAL database, not the stale `localhost:5432` one (which would show 215,000+).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.override.yml backend/.env.example
git commit -m "fix: expose real Postgres on host port 5433 for dev tooling

$(echo)
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(`backend/.env` is gitignored — do not try to `git add` it; it was already updated on disk in Step 2 and that's sufficient.)

---

### Task 3: Fix the backfill's crypto data-source skew (yfinance vs. Binance)

**Files:**
- Modify: `backend/src/providers/binance_provider.py` — add `fetch_ohlcv_range`
- Modify: `backend/src/scripts/backfill_feature_store.py` — `backfill_symbol`'s fetch call
- Test: `backend/src/tests/test_backfill_feature_store.py` (new test(s) for the crypto routing)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `BinanceProvider.fetch_ohlcv_range(symbol: str, start: datetime, end: datetime) -> Optional[pd.DataFrame]` — a new, additive method. Task 4 and Task 5 edit the same `backfill_feature_store.py` functions; land this task first so later tasks' diffs are smaller.

**Context:** The live Technical engine fetches via `fetch_history(symbol, period=...)` → `HybridProvider`, which routes `-USD` symbols (7 of the 22-symbol basket: BTC, ETH, BNB, SOL, AVAX, XRP, DOGE) to `BinanceProvider`, not yfinance. The backfill currently fetches ALL symbols via `yf.Ticker(symbol).history(...)` unconditionally — a real train/serve data-source skew for those 7. `BinanceProvider`'s existing `fetch_ohlcv(symbol, period=...)` method CANNOT express the ~2-year range this backfill needs: its `_PERIOD_TO_KLINES` table caps out at `"1y"` → 365 daily candles, with no `startTime`/`endTime` support at all. Binance's real `/klines` REST endpoint DOES support `startTime`/`endTime` params (not currently used by this codebase) and allows up to 1000 candles per request — 1000 daily candles covers ~2.7 years in one call, comfortably enough for this backfill's typical ~730-day window.

- [ ] **Step 1: Write the failing test for `BinanceProvider.fetch_ohlcv_range`**

Add to `backend/src/tests/test_backfill_feature_store.py` (check its existing imports first — it should already import `yf`/`httpx`-related mocking patterns from other backfill tests; add `import httpx` and `from providers.binance_provider import BinanceProvider` if not already present):

```python
def test_fetch_ohlcv_range_requests_the_full_date_bounded_window(monkeypatch):
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            # Two daily candles, matching Binance's real klines array shape.
            return [
                [1700000000000, "100", "105", "95", "102", "10", 0, "0", 0, "0", "0", "0"],
                [1700086400000, "102", "108", "100", "106", "12", 0, "0", 0, "0", "0", "0"],
            ]

    def _fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse()

    monkeypatch.setattr(httpx, "get", _fake_get)

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 3, tzinfo=timezone.utc)
    result = BinanceProvider().fetch_ohlcv_range("BTC-USD", start, end)

    assert result is not None
    assert len(result) == 2
    assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert captured["params"]["symbol"] == "BTCUSDT"
    assert captured["params"]["interval"] == "1d"
    assert captured["params"]["startTime"] == int(start.timestamp() * 1000)
    assert captured["params"]["endTime"] == int(end.timestamp() * 1000)
    assert captured["params"]["limit"] == 1000


def test_fetch_ohlcv_range_returns_none_on_empty_response(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return []

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResponse())
    result = BinanceProvider().fetch_ohlcv_range("ETH-USD", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 2, tzinfo=timezone.utc))
    assert result is None
```

(Add `from datetime import datetime, timezone` to the test file's imports if not already present.)

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_backfill_feature_store.py -k fetch_ohlcv_range -v
```

Expected: FAIL with `AttributeError: 'BinanceProvider' object has no attribute 'fetch_ohlcv_range'`.

- [ ] **Step 3: Implement `fetch_ohlcv_range` in `binance_provider.py`**

Add this method to the `BinanceProvider` class, right after the existing `fetch_ohlcv` method:

```python
    def fetch_ohlcv_range(self, symbol: str, start: "datetime", end: "datetime") -> Optional[pd.DataFrame]:
        """Date-bounded daily OHLCV via Binance's startTime/endTime klines
        params - NOT exposed by fetch_ohlcv above (period-only, capped at
        365 daily candles via _PERIOD_TO_KLINES). Used by the historical
        Feature Store backfill, which needs ~2 years of crypto history
        from the SAME source (Binance) the live engine reads for these
        symbols, not yfinance - reuses _to_binance_symbol so symbol
        mapping stays identical to the live fetch_ohlcv path above.
        Binance's klines endpoint allows up to 1000 candles per request;
        1000 daily candles covers ~2.7 years, comfortably enough for this
        backfill's typical ~730-day window in a single call."""
        pair = _to_binance_symbol(symbol)
        try:
            resp = httpx.get(
                f"{_BASE_URL}/klines",
                params={
                    "symbol": pair, "interval": "1d",
                    "startTime": int(start.timestamp() * 1000),
                    "endTime": int(end.timestamp() * 1000),
                    "limit": 1000,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            raw = resp.json()
            if not raw:
                logger.warning("No Binance OHLCV range data for %s (%s)", symbol, pair)
                return None

            df = pd.DataFrame(raw, columns=[
                "open_time", "Open", "High", "Low", "Close", "Volume",
                "close_time", "quote_volume", "trades",
                "taker_base", "taker_quote", "ignore",
            ])
            df[["Open", "High", "Low", "Close", "Volume"]] = df[
                ["Open", "High", "Low", "Close", "Volume"]
            ].astype(float)
            df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            return df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as exc:
            logger.error("Binance OHLCV range fetch failed for %s (%s): %s", symbol, pair, exc)
            return None
```

Add `from datetime import datetime` to this file's imports (currently it only imports `logging`, `typing.Optional`, `httpx`, `pandas as pd` — the type hint above uses a forward-referenced string `"datetime"` specifically so this step doesn't require re-reading the exact current import block; using the real `datetime` import is preferred once you've confirmed it isn't already shadowed by anything else in the file).

- [ ] **Step 4: Run to verify the new tests pass**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_backfill_feature_store.py -k fetch_ohlcv_range -v
```

Expected: both PASS.

- [ ] **Step 5: Wire the new method into `backfill_feature_store.py`'s fetch**

Replace `backfill_symbol`'s current fetch block:

```python
    try:
        hist = yf.Ticker(symbol).history(start=fetch_start, end=fetch_end)
    except Exception as exc:
        ...
        return 0
```

With:

```python
    try:
        hist = _fetch_backfill_history(symbol, start - timedelta(days=window_days + 10), end + timedelta(days=1))
    except Exception as exc:
        # A single symbol's fetch raising (network timeout, yfinance
        # rate-limit, a delisted/renamed ticker) must not abort the
        # whole basket - log and move on to the next symbol, matching
        # research/ml_trainer.py::build_dataset's precedent of never
        # letting one symbol's failure propagate out of its fetch.
        logger.warning("%s: fetch raised %s: %s, skipping entirely", symbol, type(exc).__name__, exc)
        return 0
```

Add this new module-level helper function above `backfill_symbol`:

```python
def _fetch_backfill_history(symbol: str, fetch_start_dt: datetime, fetch_end_dt: datetime):
    """Fetches `symbol`'s OHLCV for the full backfill window from the
    SAME source the live engine would use for it - HybridProvider's own
    "-USD" routing predicate (providers/hybrid_provider.py::_route),
    duplicated here as a single `endswith` check rather than importing
    HybridProvider itself (constructing it pulls in FinnhubProvider's
    API-key check, irrelevant to this binary yfinance/Binance choice).
    Closes the train/serve data-source skew for crypto symbols: before
    this fix, ALL symbols backfilled via yfinance even though live
    serving reads the 7 "-USD" symbols from Binance. Falls back to
    yfinance on a Binance failure, matching HybridProvider.fetch_ohlcv's
    own fallback behavior for the live path."""
    fetch_start_str = fetch_start_dt.strftime("%Y-%m-%d")
    fetch_end_str = fetch_end_dt.strftime("%Y-%m-%d")
    if symbol.upper().endswith("-USD"):
        from providers.binance_provider import BinanceProvider
        hist = BinanceProvider().fetch_ohlcv_range(symbol, fetch_start_dt, fetch_end_dt)
        if hist is not None and not hist.empty:
            return hist
        logger.info("%s: Binance range fetch returned nothing, falling back to yfinance", symbol)
    return yf.Ticker(symbol).history(start=fetch_start_str, end=fetch_end_str)
```

Note `backfill_symbol` currently computes `fetch_start`/`fetch_end` as strings right before the old fetch call (`fetch_start = (start - timedelta(days=window_days + 10)).strftime("%Y-%m-%d")`) — remove those two now-unused string-computation lines since `_fetch_backfill_history` does the formatting itself (for the yfinance branch) and needs the raw `datetime` objects (for the Binance branch).

- [ ] **Step 6: Add one more test confirming the routing itself (not just the Binance method in isolation)**

Add to `test_backfill_feature_store.py`:

```python
def test_backfill_symbol_routes_crypto_through_binance_not_yfinance(monkeypatch):
    binance_called = {"was": False}
    yfinance_called = {"was": False}

    def _fake_fetch_ohlcv_range(self, symbol, start, end):
        binance_called["was"] = True
        dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
        return pd.DataFrame({"Open": 100.0, "High": 105.0, "Low": 95.0, "Close": 102.0, "Volume": 10.0}, index=dates)

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, start=None, end=None):
            yfinance_called["was"] = True
            return pd.DataFrame()

    monkeypatch.setattr(BinanceProvider, "fetch_ohlcv_range", _fake_fetch_ohlcv_range)
    monkeypatch.setattr(backfill_feature_store.yf, "Ticker", _FakeTicker)

    hist = backfill_feature_store._fetch_backfill_history(
        "BTC-USD", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 10, tzinfo=timezone.utc),
    )

    assert binance_called["was"] is True
    assert yfinance_called["was"] is False
    assert not hist.empty


def test_backfill_symbol_routes_equities_through_yfinance_not_binance(monkeypatch):
    binance_called = {"was": False}

    def _fake_fetch_ohlcv_range(self, symbol, start, end):
        binance_called["was"] = True
        return None

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, start=None, end=None):
            return pd.DataFrame({"Open": [100.0]}, index=pd.date_range("2024-01-01", periods=1, tz="UTC"))

    monkeypatch.setattr(BinanceProvider, "fetch_ohlcv_range", _fake_fetch_ohlcv_range)
    monkeypatch.setattr(backfill_feature_store.yf, "Ticker", _FakeTicker)

    hist = backfill_feature_store._fetch_backfill_history(
        "THYAO.IS", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 10, tzinfo=timezone.utc),
    )

    assert binance_called["was"] is False
    assert not hist.empty
```

(Add `import backfill_feature_store` — or whatever this test file's existing import style is for the module under test, e.g. `from scripts import backfill_feature_store` — and `from providers.binance_provider import BinanceProvider` to the test file's imports if not already present; check the file's current import block first.)

- [ ] **Step 7: Run all backfill tests**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_backfill_feature_store.py -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/providers/binance_provider.py backend/src/scripts/backfill_feature_store.py backend/src/tests/test_backfill_feature_store.py
git commit -m "fix: route backfill's crypto symbols through Binance, matching live serving

$(echo)
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Fix the backfill's crypto weekend gap

**Files:**
- Modify: `backend/src/scripts/backfill_feature_store.py` — `trading_days_in_range`, its one call site in `backfill_symbol`
- Test: `backend/src/tests/test_backfill_feature_store.py`

**Interfaces:**
- Consumes: nothing from Task 3 directly (different function), but edits the same file — land after Task 3.
- Produces: `trading_days_in_range(start, end, include_weekends: bool = False)`. Task 6 (the real backfill run) depends on `backfill_symbol` correctly passing `include_weekends=True` for crypto symbols.

**Context:** `trading_days_in_range` unconditionally excludes Saturday/Sunday — correct for BIST (`.IS`) equities, wrong for 24/7 crypto. Verified against production: BTC-USD's backfilled rows showed 0 on both Saturday and Sunday versus ~1768-1785 on each weekday — losing ~28% of available crypto history and causing a Monday sample's point-in-time lookup to resolve back to the preceding Friday's (stale, 3-day-old) features.

- [ ] **Step 1: Write the failing test**

Check the existing test for `trading_days_in_range` first (`test_trading_days_in_range_excludes_weekends` per the earlier review — this exact test asserts the CURRENT, soon-to-be-conditional behavior, so it needs updating, not just a new test added alongside it):

```bash
grep -n "trading_days_in_range" backend/src/tests/test_backfill_feature_store.py
```

Read that existing test, then add a new one for the crypto case and update the existing one to be explicit about which behavior it's testing:

```python
def test_trading_days_in_range_excludes_weekends_by_default():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)  # Monday
    end = datetime(2024, 1, 7, tzinfo=timezone.utc)    # Sunday
    days = backfill_feature_store.trading_days_in_range(start, end)
    assert all(d.weekday() < 5 for d in days)
    assert len(days) == 5


def test_trading_days_in_range_includes_weekends_for_crypto():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)  # Monday
    end = datetime(2024, 1, 7, tzinfo=timezone.utc)    # Sunday
    days = backfill_feature_store.trading_days_in_range(start, end, include_weekends=True)
    assert len(days) == 7
    assert any(d.weekday() >= 5 for d in days)
```

(If an existing test with a conflicting name already covers the default-excludes-weekends case, keep ONE canonical version of it rather than two near-duplicates — rename/merge as needed so there's exactly one test per behavior.)

- [ ] **Step 2: Run to verify the new test fails**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_backfill_feature_store.py -k "trading_days_in_range" -v
```

Expected: `test_trading_days_in_range_includes_weekends_for_crypto` FAILs with a `TypeError: trading_days_in_range() got an unexpected keyword argument 'include_weekends'`.

- [ ] **Step 3: Implement**

Replace:

```python
def trading_days_in_range(start: datetime, end: datetime) -> List[datetime]:
    """Every calendar day in [start, end] that isn't a Saturday/Sunday -
    a cheap proxy for "is this likely a trading day" that doesn't need a
    market-calendar dependency. Weekday OHLCV will simply be absent from
    yfinance's returned history for actual market holidays, which the
    per-day lookup below already handles by finding no matching row."""
    days = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:  # Monday=0 .. Friday=4
            days.append(cursor)
        cursor += timedelta(days=1)
    return days
```

With:

```python
def trading_days_in_range(start: datetime, end: datetime, include_weekends: bool = False) -> List[datetime]:
    """Every calendar day in [start, end] - weekdays only by default (a
    cheap proxy for "is this likely a trading day" for BIST/equities
    that doesn't need a market-calendar dependency; actual market
    holidays simply have no matching OHLCV row, which the per-day
    lookup below already handles). `include_weekends=True` is for 24/7
    crypto assets, which trade every calendar day - without it, ~28% of
    available crypto history was being silently skipped (verified
    against production: BTC-USD had 0 backfilled rows on Saturday/Sunday
    versus ~1768-1785 on each weekday), and a Monday sample's
    point-in-time feature lookup would resolve back to the preceding
    Friday's stale value instead of Sunday's real one."""
    days = []
    cursor = start
    while cursor <= end:
        if include_weekends or cursor.weekday() < 5:  # Monday=0 .. Friday=4
            days.append(cursor)
        cursor += timedelta(days=1)
    return days
```

Update `backfill_symbol`'s one call site:

```python
    for day in trading_days_in_range(start, end):
```

to:

```python
    for day in trading_days_in_range(start, end, include_weekends=symbol.upper().endswith("-USD")):
```

- [ ] **Step 4: Run to verify tests pass**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_backfill_feature_store.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/scripts/backfill_feature_store.py backend/src/tests/test_backfill_feature_store.py
git commit -m "fix: backfill crypto's full 7-day week, not just weekdays

$(echo)
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Harden idempotency timestamp handling and close the duplicate-write hole

**Files:**
- Modify: `backend/src/scripts/backfill_feature_store.py` — `already_backfilled`
- Modify: `backend/src/feature_store/offline_store.py` — `_CREATE_TABLE_SQL`'s companion schema statements, `PostgresOfflineStore.insert()`
- Test: `backend/src/tests/test_backfill_feature_store.py`, `backend/src/tests/test_feature_store_offline_store.py` (check this exact filename — if the offline store's existing tests live under a different name, use that one instead)

**Interfaces:**
- Consumes: nothing from Tasks 3-4 directly, but edits `backfill_feature_store.py` again — land after Task 4 so each task's diff stays focused.
- Produces: `already_backfilled` now compares in explicit UTC; `feature_store_records` gets a new unique index and `insert()` becomes conflict-safe. Task 6 (the real backfill run) relies on both.

**Context:** (1) `already_backfilled`'s `record.event_timestamp.date() != day.date()` compares a value read back from a `TIMESTAMPTZ` column — psycopg2 returns it in the DB session's timezone, not necessarily UTC. Correct only because the session happens to be UTC today; not hardened. (2) A day that legitimately yields fewer than all 17 features (an indicator returning `None`, or the NaN/Inf guard skipping one) can never satisfy the "all 17 present" check, so it's recomputed and re-inserted on every re-run — `insert()` has no unique constraint, so this would duplicate rows (not yet observed, since every backfilled day so far happened to produce all 17).

- [ ] **Step 1: Write the failing test for the UTC-explicit comparison**

```bash
grep -n "already_backfilled" backend/src/tests/test_backfill_feature_store.py
```

Read the existing tests for `already_backfilled` (there should be at least a couple from earlier work), then add:

```python
def test_already_backfilled_normalizes_non_utc_session_timezone():
    """Regression test: the DB session's timezone must not affect this
    check. A record whose event_timestamp, when read back, reports a
    DIFFERENT tzinfo than UTC (simulating a non-UTC session) but the
    SAME real instant must still match correctly."""
    from datetime import timezone as tz

    class _FakeRecord:
        def __init__(self, event_timestamp):
            self.event_timestamp = event_timestamp

    class _FakeStore:
        def __init__(self, record):
            self._record = record

        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            return self._record

    # A record whose event_timestamp is the SAME real instant as
    # 2024-06-15T23:59:59Z, but represented in a +02:00 offset (as a
    # non-UTC session timezone might return it) - the real instant is
    # the same calendar day in UTC terms, so this must still count as
    # a match.
    day = datetime(2024, 6, 15, 23, 59, 59, tzinfo=timezone.utc)
    same_instant_other_tz = day.astimezone(tz(timedelta(hours=2)))
    record = _FakeRecord(event_timestamp=same_instant_other_tz)
    store = _FakeStore(record)

    from engines.technical.config import ALL_FEATURE_NAMES
    store.get_as_of = lambda symbol, feature_name, as_of, respect_ingestion_time=False: record

    assert backfill_feature_store.already_backfilled(store, "TESTSYM", day) is True
```

- [ ] **Step 2: Run to verify it fails (or passes for the wrong reason — check the assertion logic matches what you actually wrote once the real file is open)**

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_backfill_feature_store.py -k "normalizes_non_utc" -v
```

- [ ] **Step 3: Implement the UTC-explicit fix**

In `already_backfilled`, replace:

```python
    for feature_name in ALL_FEATURE_NAMES:
        record = store.get_as_of(symbol, feature_name, day, respect_ingestion_time=False)
        if record is None or record.event_timestamp.date() != day.date():
            return False
    return True
```

With:

```python
    day_utc_date = day.astimezone(timezone.utc).date()
    for feature_name in ALL_FEATURE_NAMES:
        record = store.get_as_of(symbol, feature_name, day, respect_ingestion_time=False)
        if record is None or record.event_timestamp.astimezone(timezone.utc).date() != day_utc_date:
            return False
    return True
```

(Update the function's docstring to note the comparison is now explicit-UTC, not dependent on the DB session's timezone setting.)

- [ ] **Step 4: Add the unique index and make `insert()` conflict-safe**

In `backend/src/feature_store/offline_store.py`, add a new schema statement after `_CREATE_INDEX_SQL`:

```python
_CREATE_UNIQUE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_feature_store_dedup
    ON feature_store_records (symbol, feature_name, version, event_timestamp);
"""
```

Update the constructor's `schema_statements` list:

```python
        super().__init__(
            schema_statements=[_CREATE_TABLE_SQL, _CREATE_INDEX_SQL, _CREATE_UNIQUE_INDEX_SQL],
            ...
```

Update `insert()`'s SQL to tolerate a conflict instead of raising:

```python
                cur.execute(
                    """
                    INSERT INTO feature_store_records
                        (symbol, feature_name, value, version, event_timestamp, ingestion_timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, feature_name, version, event_timestamp) DO NOTHING
                    """,
                    (...)  # unchanged params
                )
```

Add a one-line comment above the new index explaining why: `# Closes a duplicate-write hole: a day whose feature computation legitimately yields fewer than all ALL_FEATURE_NAMES (an indicator returning None, or the NaN/Inf guard in backfill_feature_store.py skipping one) could never satisfy already_backfilled's "all present" check and would be recomputed and re-inserted on every re-run without this constraint.`

**Before this runs against the real database (Task 6), verify no existing duplicate rows would make index creation fail:**

```bash
cd backend/src && ~/app/OptiTrade/venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from feature_store.offline_store import PostgresOfflineStore
store = PostgresOfflineStore()
conn = store._pool.getconn()
cur = conn.cursor()
cur.execute('''
    SELECT symbol, feature_name, version, event_timestamp, count(*)
    FROM feature_store_records GROUP BY 1,2,3,4 HAVING count(*) > 1 LIMIT 5
''')
rows = cur.fetchall()
print('Duplicate groups found:', len(rows))
for r in rows: print(r)
store._pool.putconn(conn)
"
```

Expected: `Duplicate groups found: 0` (consistent with every empirical check so far). If this prints anything other than 0, STOP — do not proceed with Step 4 against the real DB until you've decided how to de-duplicate those existing rows first (this is NOT expected and would need its own investigation, not a judgment call for this task to make silently).

- [ ] **Step 5: Run the offline store's existing tests plus the new backfill tests**

```bash
cd backend && find src/tests -iname "*offline_store*" -o -iname "*feature_store*" | grep -v backfill
```

Run whichever file(s) that finds, plus the backfill tests:

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_backfill_feature_store.py <whatever_offline_store_test_file(s)_the_find_above_showed> -v
```

Expected: all pass. The `ON CONFLICT DO NOTHING` change must not break any existing test that relies on `insert()` succeeding for genuinely-new rows (it still does — only an EXACT duplicate tuple is now a silent no-op instead of a constraint-violation exception).

- [ ] **Step 6: Commit**

```bash
git add backend/src/scripts/backfill_feature_store.py backend/src/feature_store/offline_store.py backend/src/tests/test_backfill_feature_store.py
git commit -m "fix: UTC-explicit idempotency check, unique constraint against duplicate backfill writes

$(echo)
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Run the corrected backfill against the real database

**Files:** none created/modified — this task runs the already-fixed `backend/src/scripts/backfill_feature_store.py` for real.

**Interfaces:**
- Consumes: Task 2 (real DB access via port 5433), Tasks 3-5 (all backfill correctness fixes).
- Produces: a populated, correct `feature_store_records` table in the REAL database. Tasks 7-8 read from this.

**Context:** This is the first task in this plan that writes real data. Per the Global Constraints: fresh run only, not a migration of the stale database's data (that data was produced by the pre-fix crypto logic and would reintroduce the skew/gap this plan just fixed).

- [ ] **Step 1: Confirm you're pointed at the real database one more time**

```bash
cd backend/src && ~/app/OptiTrade/venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from feature_store.offline_store import PostgresOfflineStore
store = PostgresOfflineStore()
conn = store._pool.getconn()
cur = conn.cursor()
cur.execute('SELECT count(*) FROM feature_store_records')
print('Current row count (expect a small number, NOT 215,000+):', cur.fetchone()[0])
store._pool.putconn(conn)
"
```

If this prints a large number (six figures), STOP — you are pointed at the stale database, not the real one. Re-check Task 2's `.env` change before proceeding.

- [ ] **Step 2: Run the real backfill in the background**

```bash
cd backend/src && nohup ~/app/OptiTrade/venv/bin/python3 scripts/backfill_feature_store.py --start $(date -u -d '730 days ago' +%Y-%m-%d) --end $(date -u +%Y-%m-%d) > /tmp/backfill_real_db_run.log 2>&1 &
```

Monitor it to completion (this is a long-running real job — earlier work in this project saw it take on the order of 35-40 minutes at a comparable scale; use a background wait and periodic checks, not a blocking foreground wait). Check `/tmp/backfill_real_db_run.log` for the per-symbol progress lines and the final `Toplam: N sembol-gün yazıldı.` summary.

- [ ] **Step 3: Verify the real result**

```bash
cd backend/src && ~/app/OptiTrade/venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from feature_store.offline_store import PostgresOfflineStore
store = PostgresOfflineStore()
conn = store._pool.getconn()
cur = conn.cursor()
cur.execute('SELECT count(*) FROM feature_store_records')
print('Total rows after backfill:', cur.fetchone()[0])
cur.execute('''
    SELECT symbol, count(DISTINCT event_timestamp::date) AS days, min(event_timestamp), max(event_timestamp)
    FROM feature_store_records WHERE symbol LIKE '%-USD' GROUP BY symbol ORDER BY symbol
''')
print('Crypto symbol coverage (should now include weekends - more days than a weekdays-only run would show):')
for row in cur.fetchall(): print(' ', row)
cur.execute('''
    SELECT symbol, feature_name, version, event_timestamp, count(*)
    FROM feature_store_records GROUP BY 1,2,3,4 HAVING count(*) > 1 LIMIT 5
''')
print('Duplicate groups (expect 0, Task 5s unique index should make this structurally impossible):', cur.fetchall())
store._pool.putconn(conn)
"
```

Expected: a substantial row count (comparable in order of magnitude to the stale database's earlier 215,580, though the exact number will differ since crypto coverage is now wider); crypto symbols show weekend dates present; zero duplicate groups.

- [ ] **Step 4: No commit for this task** — it's a real data operation, not a code change. Note the real row count and date range in your task report for whoever reviews this plan's execution.

---

### Task 7: Fix `v2_xgb_model`'s evaluation (wrong feature extractor, wrong file path, wrong symbol basket)

**Files:**
- Modify: `backend/src/scripts/evaluate_model_accuracy.py`

**Interfaces:**
- Consumes: Task 6's real backfilled data is NOT required for this task (this evaluates against live yfinance/Binance history directly, same as the existing `xgb_signal_model` evaluation) — this task can in principle run independently of Task 6, but is sequenced after it here since Task 8 (candidate retrain) needs Task 6 done first, and this task is a natural, smaller companion to run right before it.
- Produces: an honest accuracy number for `v2_xgb_model` for the first time, into the same `docs/ml-accuracy-report-2026-10-01.md` this script already writes.

**Context:** Three real, separate bugs, traced precisely:
1. `model_specs`'s path for this model, `"../model_artifacts/v2_xgb_model.joblib"`, is WRONG — the real file (confirmed on both the running production container and this convention's origin, `research/train_v2.py::train_v2_model`) lives at `backend/models/v2_xgb_model.joblib`, i.e. `"../models/v2_xgb_model.joblib"` relative to `backend/src`. A copy happens to also exist at the wrong path in some local dev checkouts, which is why this script "worked" (loaded something) without erroring on a missing file — but it's not the real, live-serving artifact.
2. `walk_forward_evaluate` always calls `extract_features` (the 7-feature, `research.ml_trainer`-style extractor) on every model — but `v2_xgb_model` was trained on a DIFFERENT, 5-feature schema (`ema_dist`, `vwap_dist`, `rsi`, `velocity`, `range`, defined in `research/train_v2.py::extract_v2_features` and consumed identically by the real live predictor, `v2/ml/predictor.py::MLPredictorV2.predict()`) — this mismatch is the actual source of the "expected 5, got 7" error this script has been reporting; the real live predictor path has never actually had this bug.
3. `v2_xgb_model` was trained on a single-symbol (BTC) Kaggle CSV dataset — evaluating it against the full multi-asset `SYMBOL_BASKET` (BIST equities included) isn't a fair test of a BTC-only model's actual skill.

- [ ] **Step 1: Fix the file path**

In `main()`'s `model_specs` list, change:
```python
("../model_artifacts/v2_xgb_model.joblib", "v2_xgb_model"),
```
to (this line's shape will also change in Step 3 below to add the two new per-model fields — do both edits together):
```python
("../models/v2_xgb_model.joblib", "v2_xgb_model"),
```

- [ ] **Step 2: Add a v2-specific feature-extraction adapter**

`research.train_v2.extract_v2_features(df)` has a different calling convention than `research.ml_trainer.extract_features(window)`: it takes a WHOLE multi-row DataFrame and returns a transformed DataFrame (one row per surviving date, after `dropna()`), not a single feature-vector list for one window's last bar. The real live predictor (`MLPredictorV2.predict()`) adapts it by taking `df[self.model_data['features']].iloc[-1:]` after calling `extract_v2_features`. Add this same adaptation here, as a new module-level function near the top of the file (after the existing `extract_features` import):

```python
from research.train_v2 import extract_v2_features

_V2_FEATURE_NAMES = ["ema_dist", "vwap_dist", "rsi", "velocity", "range"]


def _extract_v2_features_for_window(window):
    """Adapts research.train_v2.extract_v2_features (which operates on
    a whole multi-row DataFrame and returns one row per surviving date)
    to walk_forward_evaluate's per-window, single-feature-vector-for-
    the-last-bar calling convention - mirrors exactly what the real live
    predictor (v2/ml/predictor.py::MLPredictorV2.predict()) does with
    this same function's output, so this evaluation exercises the same
    feature pipeline the live model actually sees, not a re-derivation
    that could itself silently drift (the same reasoning this script
    already applies to reusing research.ml_trainer.extract_features for
    the other models)."""
    try:
        feats_df = extract_v2_features(window.copy())
        if feats_df.empty:
            return None
        last_row = feats_df[_V2_FEATURE_NAMES].iloc[-1]
        if last_row.isnull().any():
            return None
        return last_row.tolist()
    except Exception:
        return None
```

- [ ] **Step 3: Make `walk_forward_evaluate` accept a feature extractor and a symbol basket override**

Replace the function signature and its two internal references:

```python
def walk_forward_evaluate(model_path: str, model_name: str) -> dict:
    package = joblib.load(model_path)
    ...
    for symbol in SYMBOL_BASKET:
        ...
            feats = extract_features(window)
```

With:

```python
def walk_forward_evaluate(model_path: str, model_name: str, symbol_basket=None, feature_extractor=extract_features) -> dict:
    basket = symbol_basket if symbol_basket is not None else SYMBOL_BASKET
    package = joblib.load(model_path)
    ...
    for symbol in basket:
        ...
            feats = feature_extractor(window)
```

(Keep everything else in the function body identical — only the `for symbol in SYMBOL_BASKET:` line changes to `for symbol in basket:`, and the one `extract_features(window)` call changes to `feature_extractor(window)`.)

- [ ] **Step 4: Update `main()`'s model_specs and the call site**

Replace:

```python
    model_specs = [
        ("../model_artifacts/xgb_signal_model.joblib", "xgb_signal_model"),
        ("../models/v2_xgb_model.joblib", "v2_xgb_model"),
    ]
    oos_path = "../model_artifacts/xgb_signal_model_oos_test.joblib"
    if os.path.exists(oos_path):
        model_specs.append((oos_path, "xgb_signal_model_oos_test"))
    results = []
    for path, name in model_specs:
        try:
            results.append(walk_forward_evaluate(path, name))
        except Exception as exc:
            logger.warning("%s: walk-forward evaluation failed: %s", name, exc)
            results.append({"model": name, "n_samples": 0, "error": str(exc)})
```

With:

```python
    # v2_xgb_model gets its own feature extractor (it has a different,
    # 5-feature schema - see _extract_v2_features_for_window above) and
    # its own symbol basket: it was trained on a single-symbol (BTC)
    # dataset, so evaluating it against the full multi-asset basket
    # (which includes BIST equities it was never trained on) wouldn't be
    # a fair test of its actual skill.
    model_specs = [
        ("../model_artifacts/xgb_signal_model.joblib", "xgb_signal_model", None, extract_features),
        ("../models/v2_xgb_model.joblib", "v2_xgb_model", ["BTC-USD"], _extract_v2_features_for_window),
    ]
    oos_path = "../model_artifacts/xgb_signal_model_oos_test.joblib"
    if os.path.exists(oos_path):
        model_specs.append((oos_path, "xgb_signal_model_oos_test", None, extract_features))
    results = []
    for path, name, basket, extractor in model_specs:
        try:
            results.append(walk_forward_evaluate(path, name, symbol_basket=basket, feature_extractor=extractor))
        except Exception as exc:
            logger.warning("%s: walk-forward evaluation failed: %s", name, exc)
            results.append({"model": name, "n_samples": 0, "error": str(exc)})
```

- [ ] **Step 5: Run it for real**

```bash
cd backend/src && ~/app/OptiTrade/venv/bin/python3 scripts/evaluate_model_accuracy.py 2>&1 | tee /tmp/evaluate_model_accuracy_run.log
```

Expected: the printed/written report's `v2_xgb_model` row now shows a real `n_samples`/`accuracy`/`majority_baseline` (no longer an ERROR row) — report whatever the real number is, honestly, in your task report. Confirm no exception was raised for this model this time.

- [ ] **Step 6: Commit**

```bash
git add backend/src/scripts/evaluate_model_accuracy.py docs/ml-accuracy-report-2026-10-01.md
git commit -m "fix: evaluate v2_xgb_model with its own feature extractor, path, and symbol basket

$(echo)
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(The committed report file will have today's date in its filename per the existing script's hardcoded output path — leave that as-is for this task; Task 8 below writes a freshly-dated candidate report separately.)

---

### Task 8: Retrain the ML candidate against the corrected real database

**Files:** none created/modified — `backend/src/scripts/train_ml_candidate.py` already exists and needs no code changes for this task, per the spec.

**Interfaces:**
- Consumes: Task 6's real, corrected backfill.
- Produces: a new real CANDIDATE model registered in the real database; a freshly-dated candidate report.

**Context:** Success bar (Global Constraints, restated here): beat the naive majority-class baseline out-of-sample. If the first real run doesn't, a BOUNDED number of reasonable fine-tuning attempts (document exactly what you tried) is in scope; if it still doesn't beat baseline after that, report the honest result and stop — do not keep iterating indefinitely.

- [ ] **Step 1: Run the real training job in the background**

```bash
cd backend/src && nohup ~/app/OptiTrade/venv/bin/python3 scripts/train_ml_candidate.py > /tmp/train_candidate_real_db_run.log 2>&1 &
```

Monitor to completion (comparable runtime to earlier runs of this same script in this project — on the order of a few minutes to tens of minutes).

- [ ] **Step 2: Verify the new model's CANDIDATE state directly against the real DB**

```bash
cd backend/src && ~/app/OptiTrade/venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from feature_store.offline_store import PostgresOfflineStore
store = PostgresOfflineStore()
conn = store._pool.getconn()
cur = conn.cursor()
cur.execute('SELECT model_id, algorithm, label_name, horizon_days, promotion_state, training_date FROM ml_training_model_registry ORDER BY training_date DESC LIMIT 1')
print(cur.fetchone())
store._pool.putconn(conn)
"
```

Expected: a new row, `promotion_state = 'candidate'`.

- [ ] **Step 3: Read the real out-of-sample result from the script's own output/report**

Report the real accuracy/precision/recall/majority_baseline numbers honestly. If accuracy beats majority_baseline, done — proceed to Step 5.

- [ ] **Step 4: If it does NOT beat baseline, make a bounded number of reasonable fine-tuning attempts**

Reasonable, in order of effort (stop as soon as one beats baseline; stop entirely after exhausting this list even if none do):
1. Try `ModelAlgorithm.LIGHTGBM` or `ModelAlgorithm.RANDOM_FOREST` instead of XGBoost (check `train_ml_candidate.py`'s `service.run_training_job(...)` call for the `algorithm=` argument and swap it) — a different algorithm is a legitimate, cheap first thing to try.
2. If that doesn't help either, try a narrower `direction_band_pct` or a different `horizon_days` IF you can justify it from the data (read `MLTrainingConfig`'s defaults first) — document your reasoning for whatever you try.
3. Do not attempt hyperparameter grid search, do not add new features, do not retrain more than 3 total times. If none of the above beats baseline, that is the honest result — write it up as such.

For whichever variant(s) you try, re-run Steps 1-3 for each, and report ALL attempts (not just the best one) in your task report.

- [ ] **Step 5: Write a fresh, dated candidate report**

Per the spec's own Risk note: today's earlier `docs/ml-candidate-report-2026-10-01.md` is now superseded (it reflects the WRONG database's data and the pre-fix crypto logic). `train_ml_candidate.py` already writes its own report file — confirm its output path and either let it write fresh (if it already dates the filename by run date) or rename/move the output so today's real run's numbers are the ones easily found, without silently overwriting the historical 2026-10-01 report that documents yesterday's (wrong-DB) incident and recovery — that file is a historical record and should NOT be deleted or edited to look like this is the same run. If `train_ml_candidate.py`'s own script hardcodes `docs/ml-candidate-report-2026-10-01.md` as its output path, update that one line to use today's real date (check the script for how it names the file and adjust minimally — this is a one-line path/date fix, not a rewrite of the reporting logic).

- [ ] **Step 6: Commit**

```bash
git add docs/ml-candidate-report-*.md backend/src/scripts/train_ml_candidate.py
git commit -m "feat: retrain ML candidate against the real, corrected Feature Store

$(echo)
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(Only include `train_ml_candidate.py` in the `git add` if Step 5 actually required a code change to it; if the report path was already date-parameterized, there's nothing to commit there.)

---

### Task 9: Fix the Dockerfile ownership bug (SQLite readonly database error)

**Files:**
- Modify: `backend/Dockerfile`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `/app/data` writable by the runtime `appuser`. Task 10's full test suite run and the final deploy both depend on this not having broken anything else under `/app`.

**Context:** Root cause, confirmed directly against the live container: `/app/data` and `/app/data/monitoring.db` are owned `root:root`; the container actually runs as `appuser:appgroup` (uid 100, gid 101) — no write access to either. `core/monitoring.py::purge_old_predictions()` fails daily in production with `attempt to write a readonly database` as a direct result. The Dockerfile already has an IDENTICAL, already-correct precedent for a different directory: `RUN chown -R appuser:appgroup model_artifacts` (added earlier for the exact same EACCES class of bug, per that line's own comment).

- [ ] **Step 1: Make the fix**

In `backend/Dockerfile`, find:

```dockerfile
# model_artifacts/ is the one directory the app legitimately writes to at
# runtime (Continuous Learning's model retrain replaces
# xgb_signal_model.joblib in place - see research/ml_trainer.py). A
# plain `COPY . .` leaves it root-owned with whatever mode bits the
# build context's files happened to have (verified in SERVER STEP 2's
# live Docker check: on this host that was `600`, unreadable by
# appuser at all - `/ml/status` reported `available: false`, and the
# in-container retrain's own write failed with EACCES). chown (not
# chmod 777, not USER root) makes ownership deterministic regardless
# of what the build context's host permissions happen to be.
RUN chown -R appuser:appgroup model_artifacts

USER appuser
```

Replace with:

```dockerfile
# model_artifacts/ and backend/data/ are the two directories the app
# legitimately writes to at runtime: model_artifacts/ for Continuous
# Learning's model retrain (research/ml_trainer.py, replaces
# xgb_signal_model.joblib in place); data/ for core/monitoring.py's
# SQLite self-evaluation prediction tracking (monitoring.db). A plain
# `COPY . .` leaves both root-owned with whatever mode bits the build
# context's files happened to have (verified in SERVER STEP 2's live
# Docker check for model_artifacts/: on this host that was `600`,
# unreadable by appuser at all; data/monitoring.db had the identical
# problem, confirmed directly against the running container on
# 2026-10-02 - root:root ownership meant every call to
# purge_old_predictions()/validate_predictions() failed with "attempt
# to write a readonly database"). chown (not chmod 777, not USER root)
# makes ownership deterministic regardless of what the build context's
# host permissions happen to be.
RUN chown -R appuser:appgroup model_artifacts data

USER appuser
```

- [ ] **Step 2: Rebuild locally and verify the fix (do NOT touch the running production container yet — build only, this is validated in Task 10's full suite run and the eventual deploy, not here)**

```bash
cd /home/mayasoft/app/OptiTrade && docker build -t optitrade-api-test-build -f backend/Dockerfile backend/
```

Expected: build succeeds.

```bash
docker run --rm optitrade-api-test-build sh -c 'ls -la /app/data/ && touch /app/data/write_test.tmp && echo WRITE_OK && rm /app/data/write_test.tmp'
```

Expected: `drwxrwxr-x ... appuser appgroup ...` (or similar, owned by `appuser`/`appgroup`, not `root`), and `WRITE_OK` printed (confirming the appuser can actually write there now).

- [ ] **Step 3: Commit**

```bash
git add backend/Dockerfile
git commit -m "fix: chown backend/data to appuser, closing the monitoring.db readonly-DB bug

$(echo)
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(Remove the local test image afterward: `docker rmi optitrade-api-test-build`.)

---

### Task 10: Full test suite, then STOP for explicit deploy confirmation

**Files:** none — this task runs the suite and, only with explicit go-ahead, deploys.

**Interfaces:**
- Consumes: every prior task in this plan.
- Produces: the actual redeployed, live `optitrade-api` container.

- [ ] **Step 1: Run the full backend test suite**

Task 1 already closed the one real data-loss hazard in this suite — running it in full is now safe.

```bash
cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests -q > /tmp/full_suite_pre_deploy.txt 2>&1; echo "EXIT CODE: $?"; tail -40 /tmp/full_suite_pre_deploy.txt
```

Do NOT pipe this through `tail` as part of the same command you check the exit code from (that masks pytest's real exit code) — redirect to a file first, check `$?` from the direct `pytest` invocation, then separately inspect the file.

Expected: exit code 0, all tests passing — including `test_ml_training_service.py` and `test_ml_training_datasets.py` this time (Task 1 made them safe to run). If anything fails, stop and fix it before proceeding — do not move on to Step 2 with a red suite.

- [ ] **Step 2: STOP — this is the explicit human-confirmation gate.**

**Do not run the commands in Step 3 without the user's explicit, separate go-ahead at this specific point**, regardless of how clean every earlier task's result looked, and regardless of whether this plan is being executed by an autonomous subagent loop that would otherwise not stop between tasks. This is the one step in the entire plan that touches the live, currently-serving `optitrade-api` container on `mayasoftlnx01`. Present a short summary of everything this plan changed (Tasks 1-9) and the full test suite's result (Step 1), then wait.

- [ ] **Step 3: Deploy (only after Step 2's explicit confirmation)**

```bash
cd /home/mayasoft/app/OptiTrade && docker compose build api && docker compose up -d api
```

- [ ] **Step 4: Post-deploy verification**

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep optitrade-api
docker logs optitrade-api --since 2m 2>&1 | tail -30
```

Expected: container `Up ... (healthy)`, no startup errors in the logs.

```bash
docker exec optitrade-api sh -c 'echo $FEATURE_STORE_POSTGRES_HOST'
```

**Expected output: exactly `postgres`** — confirming Task 2's host port mapping (for host-venv tooling only) did NOT leak into the container's own runtime configuration, which must keep using the Docker-internal hostname. If this prints anything else, STOP and investigate before considering the deploy complete.

```bash
docker exec optitrade-api sh -c 'ls -la /app/data/monitoring.db'
```

Expected: owned by `appuser`, confirming Task 9's Dockerfile fix is live in the actual running container (not just the local test build from Task 9 Step 2).

Wait a day (or check again after the next scheduled `purge_old_predictions()` run, per `core/monitoring.py`'s own scheduling) and confirm the `attempt to write a readonly database` error no longer appears in `docker logs optitrade-api`.

Finally, spot-check a couple of live decisions to confirm the service responds correctly end-to-end:

```bash
docker exec optitrade-api sh -c 'cd /app/src && python3 -c "
from decision_engine.service import get_default_decision_engine
engine = get_default_decision_engine()
for sym in [\"THYAO.IS\", \"BTC-USD\"]:
    out = engine.decide(sym)
    print(sym, out.decision.value, out.confidence, out.data_sufficiency)
"'
```

Expected: both symbols return a decision without raising.

**No commit for this task** — Steps 1 and 4 are verification; Step 3 is an infrastructure operation, not a code change.
