# Backend `src/` Layout Restructure (Phase 0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the entire `backend/` codebase into a `backend/src/` container layout with zero behavior change — every existing module keeps its name and internal shape, the full test suite keeps the same pass/fail count, and the live API keeps working, so later phases (new entities, multi-horizon models, `DecisionObject`) build directly on the target shape instead of reorganizing later.

**Architecture:** `src/` is a plain container directory, not a Python package (no `src/__init__.py`) — the interpreter's import root moves to `src/` via `pytest.ini`'s `pythonpath`/Docker's `WORKDIR`, so every existing `from core.hybrid_engine import ...`-style import keeps working unchanged. Two ML artifact directories (`models/*.joblib` → `model_artifacts/`, and `ml_training_artifacts/`, which already sits correctly outside any package) stay siblings of `src/`, not inside it, since they're binary data, not source.

**Tech Stack:** Python 3.12, pytest, Docker, Alembic, git (all already in place — this plan adds no new dependency).

**Spec:** `docs/superpowers/specs/2026-09-30-src-layout-restructure-design.md`

## Global Constraints

- Zero behavior change: no endpoint, schema, or test assertion changes anywhere in this plan.
- Every relocation uses `git mv` (never delete+recreate), so `git log --follow` keeps each file's history.
- `src/` is a container, never a package — no file's `import` statements change, only run-configuration files do.
- The full test suite's pass/fail count must match the current baseline exactly (2907 passing / 2 pre-existing, unrelated failures: `tests/test_users_config_jwt_secret.py::test_generated_secret_is_stable_within_a_process_but_differs_across_processes`, `tests/test_core_news_analyzer_cache.py::test_no_news_result_is_also_cached`) before and after every task in this plan. Any *new* failure is a bug in this plan's own work and must be fixed before moving on.
- Renaming to the build spec's semantic folders (`data/connectors/`, `features/stocks/`, `models/long_horizon/`, ...) is out of scope — deferred to a later plan.

---

## Before you start

All commands below assume a shell open at `~/app/OptiTrade/backend` unless
a step says otherwise. Activate the venv first:

```bash
cd ~/app/OptiTrade/backend
source ../venv/bin/activate
```

Record the current baseline once, so every later verification step has
something exact to diff against:

```bash
python3 -m pytest -p no:warnings -q > /tmp/src_restructure_baseline.log 2>&1
tail -5 /tmp/src_restructure_baseline.log
```

Expected tail: `2 failed, 2907 passed in ...s`, and the two `FAILED` lines
must be exactly `test_users_config_jwt_secret.py::test_generated_secret_is_stable_within_a_process_but_differs_across_processes` and `test_core_news_analyzer_cache.py::test_no_news_result_is_also_cached`. If the baseline differs from this, stop and report it before starting any task below — this plan's own verification steps compare against *this* baseline, not a written-down number.

---

### Task 1: Split `models/` into source (`schemas.py`) and artifacts (`model_artifacts/`)

This task is fully independent of the big `src/` move in Task 2 and is
its own testable, committable unit. It fixes a pre-existing problem
found while designing this restructure: `backend/models/` mixes real
Python source (`schemas.py`) with two binary ML artifacts
(`v2_xgb_model.joblib`, `xgb_signal_model.joblib`) that happen to share
a directory name — artifacts don't belong under the `src/` this plan is
about to create.

**Files:**
- Move: `models/v2_xgb_model.joblib` → `model_artifacts/v2_xgb_model.joblib`
- Move: `models/xgb_signal_model.joblib` → `model_artifacts/xgb_signal_model.joblib`
- Modify: `core/ml_predictor.py:15`
- Modify: `ml/chart_model.py:31-32`
- Modify: `scripts/ml_trainer.py:204-205`
- Modify: `research/ml_trainer.py:273-274`
- Modify: `Dockerfile` (the `chown` line only — its `WORKDIR /app/src` companion edit is Task 2)
- Test: `tests/test_ml_predictor.py` (existing, unmodified — it monkeypatches `_MODEL_PATH` per-test already, so it doesn't depend on the real file location, but re-running it here proves this task didn't break model loading)

**Interfaces:** None — this task only changes where two binary files live and the string constants that point at them. No function signature changes.

- [ ] **Step 1: Move the two artifact files with `git mv`**

```bash
mkdir -p model_artifacts
git mv models/v2_xgb_model.joblib model_artifacts/v2_xgb_model.joblib
git mv models/xgb_signal_model.joblib model_artifacts/xgb_signal_model.joblib
ls models/            # only __init__.py and schemas.py should remain
ls model_artifacts/   # both .joblib files should be here now
```

- [ ] **Step 2: Update `core/ml_predictor.py`'s model path**

Current line 15:
```python
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "xgb_signal_model.joblib")
```

Change to:
```python
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "model_artifacts", "xgb_signal_model.joblib")
```

(`core/ml_predictor.py` hasn't moved yet in this task, so this is still exactly one `..` up from `core/` to `backend/`, same as before — only the directory name changes.)

- [ ] **Step 3: Update `ml/chart_model.py`'s model directory**

Current lines 31-32:
```python
BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
MODEL_DIR   = os.path.join(BACKEND_DIR, "models")
```

Change to:
```python
BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
MODEL_DIR   = os.path.join(BACKEND_DIR, "model_artifacts")
```

- [ ] **Step 4: Update `scripts/ml_trainer.py`'s save path**

Current lines 204-205:
```python
    os.makedirs("models", exist_ok=True)
    model_path = os.path.join("models", "xgb_signal_model.joblib")
```

Change to:
```python
    os.makedirs("model_artifacts", exist_ok=True)
    model_path = os.path.join("model_artifacts", "xgb_signal_model.joblib")
```

- [ ] **Step 5: Update `research/ml_trainer.py`'s save path**

Current lines 273-274 — identical change to Step 4, same two lines, same file pattern, in `research/ml_trainer.py` instead of `scripts/ml_trainer.py`.

- [ ] **Step 6: Update the Dockerfile's `chown` target**

Find:
```dockerfile
RUN chown -R appuser:appgroup models
```

Replace with:
```dockerfile
RUN chown -R appuser:appgroup model_artifacts
```

Leave every comment above this line as-is for now (Task 2 rewrites that
comment block when it adds `WORKDIR /app/src`) — this step only fixes
the actual command so the continuous-learning retrain can still write
its output once this task lands.

- [ ] **Step 7: Verify nothing else references the old `models/` artifact path**

```bash
grep -rn '"models"\|'"'"'models'"'"'' --include="*.py" . | grep -v "/tests/\|__pycache__\|research_lab\|ml_training/"
```

Expected: no remaining hits for the artifact directory (the `models`
Python *package* name itself, e.g. in `tests/test_research_isolation.py`'s
`PRODUCTION_DIRS` list or `v2/models/schemas.py` docstring references,
is a different, correct thing — don't touch those).

- [ ] **Step 8: Run the directly affected test and the full suite**

```bash
python3 -m pytest -p no:warnings tests/test_ml_predictor.py -v
python3 -m pytest -p no:warnings -q > /tmp/src_restructure_task1.log 2>&1
tail -5 /tmp/src_restructure_task1.log
diff <(grep FAILED /tmp/src_restructure_baseline.log) <(grep FAILED /tmp/src_restructure_task1.log)
```

Expected: `tests/test_ml_predictor.py` all pass; the full-suite tail
matches the baseline's `2 failed, 2907 passed` exactly; the `diff` of
`FAILED` lines is empty (same two pre-existing failures, nothing new).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: split backend/models/ into source and model_artifacts/

backend/models/ mixed real source (schemas.py) with two binary ML
artifacts (v2_xgb_model.joblib, xgb_signal_model.joblib) that only
shared a directory name by coincidence - found while designing the
src/ layout restructure (docs/superpowers/specs/
2026-09-30-src-layout-restructure-design.md). Artifacts move to a new
backend/model_artifacts/, sibling of the future src/, since binary
data doesn't belong under a source directory. Every hardcoded
reference (core/ml_predictor.py, ml/chart_model.py, scripts/
ml_trainer.py, research/ml_trainer.py, Dockerfile's chown target)
updated accordingly. Zero behavior change - same 2907 passing / 2
pre-existing-unrelated-failing test count as before.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Move every remaining module into `src/`, flip run-configuration

This is the big mechanical move. It is deliberately **one task, one
commit**: once any module physically moves, `pytest.ini`'s old
`pythonpath = .` / `testpaths = tests` can no longer find anything, so
there is no meaningful "partially moved, still green" intermediate
state to stop at. All the `git mv` steps below happen first (in the
working tree, uncommitted), then the config/code edits, then one
full verification pass, then a single commit. Do not commit between
steps in this task.

**Files:**
- Move (via `git mv`, whole directories/files, unchanged internally): every top-level entry in `backend/` except the ones explicitly staying at `backend/` root (see Step 6's checklist) — see Steps 1-5 for the exact grouped commands.
- Delete: `admin_terminal.py` (root copy — stale duplicate of `scripts/admin_terminal.py`, confirmed superset relationship in the design spec's "Pre-existing issue" section)
- Modify: `pytest.ini`
- Modify: `Dockerfile` (add `WORKDIR /app/src`)
- Modify: `alembic.ini`
- Modify: `src/core/ml_predictor.py` (second pass — add the extra `..` now that `core/` is one level deeper)
- Modify: `src/ml/chart_model.py` (second pass, same reason)
- Modify: `src/scripts/ml_trainer.py`, `src/research/ml_trainer.py` (second pass — CWD convention becomes `backend/src/`, need `../model_artifacts`)
- Modify: `src/ml_training/config.py` (same CWD reasoning, for `ml_training_artifacts/`, which also stays a sibling of `src/`)

**Interfaces:** None — every Python import statement is unchanged by this task (that's the point of the container-not-package decision in the spec). Only file locations and the handful of path-literal strings above change.

- [ ] **Step 1: Create `src/` and move the analysis/decision-core modules**

```bash
mkdir -p src
git mv core src/core
git mv v2 src/v2
git mv decision_engine src/decision_engine
git mv feature_store src/feature_store
git mv pipeline src/pipeline
git mv engine_registry src/engine_registry
git mv engines src/engines
git mv signals src/signals
git mv providers src/providers
git mv data src/data
git mv news src/news
git mv ml src/ml
git mv ml_training src/ml_training
git mv model_serving src/model_serving
git mv research src/research
git mv research_lab src/research_lab
git mv learning src/learning
git mv explanation_engine src/explanation_engine
```

- [ ] **Step 2: Move the account/product platform modules**

```bash
git mv users src/users
git mv portfolio src/portfolio
git mv watchlist src/watchlist
git mv paper_trading src/paper_trading
git mv dashboard src/dashboard
git mv intelligence src/intelligence
```

- [ ] **Step 3: Move cross-cutting modules and root scripts**

```bash
git mv api src/api
git mv models src/models
git mv db src/db
git mv middleware src/middleware
git mv alembic src/alembic
git mv main.py src/main.py
git mv cache_manager.py src/cache_manager.py
git mv terminal_dashboard.py src/terminal_dashboard.py
git mv test_engine.py src/test_engine.py
```

- [ ] **Step 4: Remove the stale root `admin_terminal.py`, then move `scripts/`**

```bash
git rm admin_terminal.py
git mv scripts src/scripts
ls src/scripts/   # admin_terminal.py, backtest.py, backtest_advanced.py, ml_trainer.py, __init__.py
```

- [ ] **Step 5: Move `tests/`**

```bash
git mv tests src/tests
```

- [ ] **Step 6: Confirm nothing importable is left at `backend/` root**

```bash
ls ~/app/OptiTrade/backend
```

Expected remaining entries: `.env`, `.env.example`, `.env.test`,
`requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `Dockerfile`,
`.dockerignore`, `alembic.ini`, `model_artifacts/` (from Task 1),
`src/`, plus non-source artifacts this plan doesn't touch
(`backtest_results.csv`, `backtest_results.json`, `energy_news.json`,
`ml_training_artifacts/`, `.coverage`, `.pytest_cache/`) and VCS/venv
noise (`.git` is at the repo root, not here). If any `.py` file or
importable package is still sitting at `backend/` root, an earlier step
was missed — go back and move it before continuing.

- [ ] **Step 7: Update `pytest.ini`**

Current:
```ini
[pytest]
pythonpath = .
testpaths = tests
```

Change to:
```ini
[pytest]
pythonpath = src
testpaths = src/tests
```

(Leave every other line in the file — `python_files`, `python_classes`,
`python_functions`, `asyncio_mode`, `asyncio_default_fixture_loop_scope`,
`addopts` — unchanged.)

- [ ] **Step 8: Update `alembic.ini`**

Find:
```ini
script_location = alembic
```

Replace with:
```ini
script_location = src/alembic
```

- [ ] **Step 9: Update the Dockerfile's `WORKDIR`**

Find the `USER appuser` line (right after Task 1's `chown` fix) and the
`CMD` line at the end. Insert a new `WORKDIR /app/src` between `USER
appuser` and the `HEALTHCHECK`/`CMD` block, so `uvicorn main:app` in the
existing `CMD` resolves `main.py` at its new location:

```dockerfile
RUN chown -R appuser:appgroup model_artifacts

USER appuser

WORKDIR /app/src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers \"${UVICORN_WORKERS:-2}\" --proxy-headers --forwarded-allow-ips='*' --log-level info"]
```

(Only the new `WORKDIR /app/src` line is added; `EXPOSE`, `HEALTHCHECK`,
and `CMD` keep their existing content exactly as already in the file.)

- [ ] **Step 10: Second-pass fix — `src/core/ml_predictor.py`**

Task 1 already renamed the artifact directory; this step accounts for
`core/` now sitting one level deeper (`src/core/` instead of `core/`).

Current (after Task 1):
```python
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "model_artifacts", "xgb_signal_model.joblib")
```

Change to:
```python
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "model_artifacts", "xgb_signal_model.joblib")
```

- [ ] **Step 11: Second-pass fix — `src/ml/chart_model.py`**

Current (after Task 1):
```python
BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
MODEL_DIR   = os.path.join(BACKEND_DIR, "model_artifacts")
```

`BACKEND_DIR` now computes `src/` (one `dirname` too few), not
`backend/`. Change to:
```python
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
MODEL_DIR   = os.path.join(BACKEND_DIR, "model_artifacts")
```

- [ ] **Step 12: Second-pass fix — `src/scripts/ml_trainer.py` and `src/research/ml_trainer.py`**

These two use a bare, CWD-relative string (not `__file__`-relative).
With `WORKDIR /app/src` now the running convention (matching how a
local developer would also `cd backend/src` to run `uvicorn main:app`
the same way), CWD when someone runs `python research/ml_trainer.py`
is `backend/src/`, one level below where `model_artifacts/` actually
lives.

In both `src/scripts/ml_trainer.py` (lines 204-205, per Task 1's edit)
and `src/research/ml_trainer.py` (lines 273-274), change:
```python
    os.makedirs("model_artifacts", exist_ok=True)
    model_path = os.path.join("model_artifacts", "xgb_signal_model.joblib")
```
to:
```python
    os.makedirs("../model_artifacts", exist_ok=True)
    model_path = os.path.join("..", "model_artifacts", "xgb_signal_model.joblib")
```

- [ ] **Step 13: Second-pass fix — `src/ml_training/config.py`**

`ml_training_artifacts/` was never moved (it already correctly sits
outside any package, as a sibling of the new `src/`) — but the default
that points at it is a bare CWD-relative string with the same "CWD is
now `src/`" problem as Step 12.

Current lines 52 and 100:
```python
    model_artifact_dir: str = "ml_training_artifacts"
```
```python
            model_artifact_dir=os.getenv("ML_TRAINING_MODEL_ARTIFACT_DIR", "ml_training_artifacts"),
```

Change both occurrences of the bare `"ml_training_artifacts"` default to
`"../ml_training_artifacts"`:
```python
    model_artifact_dir: str = "../ml_training_artifacts"
```
```python
            model_artifact_dir=os.getenv("ML_TRAINING_MODEL_ARTIFACT_DIR", "../ml_training_artifacts"),
```

(The `ML_TRAINING_MODEL_ARTIFACT_DIR` env var name itself is unchanged —
only the fallback default string.)

- [ ] **Step 14: Verify `.env`/`.env.test` are still found correctly**

This was verified empirically in the design spec (a file two directories
deep still finds `backend/.env` via `find_dotenv()`'s upward walk), but
confirm it holds for the real, now-moved files:

```bash
cd ~/app/OptiTrade/backend
source ../venv/bin/activate
python3 -c "
from dotenv import find_dotenv
import os
os.chdir('src')
print(find_dotenv())
"
```

Expected: prints the absolute path to `backend/.env` (not
`backend/src/.env`, which doesn't exist).

- [ ] **Step 15: Run the full test suite from `backend/`**

```bash
cd ~/app/OptiTrade/backend
source ../venv/bin/activate
python3 -m pytest -p no:warnings -q > /tmp/src_restructure_task2.log 2>&1
tail -5 /tmp/src_restructure_task2.log
diff <(grep FAILED /tmp/src_restructure_baseline.log) <(grep FAILED /tmp/src_restructure_task2.log)
```

Expected: same `2 failed, 2907 passed` tail as the baseline (Task 1's
verification log works equally well as the comparison base here); empty
diff. If pytest instead reports "no tests ran" or an import error, the
most likely causes are: `pytest.ini`'s `pythonpath`/`testpaths` edit
(Step 7) wasn't saved correctly, or a module was missed in Steps 1-5 (Step
6's checklist should have already caught this, but re-run `ls
~/app/OptiTrade/backend` now to double-check nothing new appeared at
root from an interrupted `git mv`).

- [ ] **Step 16: Verify the Docker image builds and serves `/health` — via `docker compose`, in an isolated project**

`docker ps` on this host already has a **live, production** stack
running under the default compose project name from this same
directory (`optitrade-api`, `optitrade-postgres`, `optitrade-redis`,
...). Plain `docker compose up` here would reuse those exact container
names and could stop/replace them. Always pass an explicit, different
`-p` (project name) for this check, so Compose creates its own isolated
containers/network and touches nothing already running:

```bash
cd ~/app/OptiTrade/backend
docker compose -p src-restructure-check up --build -d
sleep 10
docker compose -p src-restructure-check ps   # confirm containers are "healthy"/"running", not restarting
curl -f http://localhost:8000/health
echo "exit code: $?"
docker compose -p src-restructure-check logs api --tail 80
```

(`docker-compose.override.yml`'s `127.0.0.1:8000:8000`/`127.0.0.1:6379:6379`
port bindings apply the same way here as any other local compose run —
if port 8000 is already bound by the live production stack, stop the
`curl` step and instead run `docker compose -p src-restructure-check
exec api curl -f http://localhost:8000/health` from inside the isolated
network instead.)

Expected: `ps` shows the `api` container healthy; the `curl` prints a
200 response body and `exit code: 0`. If the container fails to start,
`logs` will show either a Python import error (an unmoved/mislocated
file) or a "file not found" for `main.py` (the `WORKDIR /app/src` edit
from Step 9 didn't take, or `COPY . .` didn't include `src/` — check
`.dockerignore` doesn't accidentally exclude it; it currently doesn't
reference `src/` at all, so this would be a new problem, not a
pre-existing exclusion).

**Once verified, tear the isolated stack down completely** — it used a
fresh Postgres volume, not the real data, and must not be left running
alongside the production stack:

```bash
docker compose -p src-restructure-check down -v
docker compose -p src-restructure-check ps   # confirm empty
docker ps   # confirm the original optitrade-* containers are still up, untouched
```

- [ ] **Step 17: Verify Alembic's new `script_location`**

```bash
cd ~/app/OptiTrade/backend
source ../venv/bin/activate
alembic current
```

Expected: prints the current revision (or "no revision" on a fresh DB)
without an error about a missing `script_location` directory or a
failed import inside `src/alembic/env.py`.

- [ ] **Step 18: Commit**

```bash
git add -A
git status   # sanity check: every entry should be a rename (R), not a delete+add pair, confirming git tracked the moves as renames
git commit -m "$(cat <<'EOF'
refactor: move backend into a src/ layout (Phase 0)

Flat, behavior-preserving move of every backend module into
backend/src/, per docs/superpowers/specs/
2026-09-30-src-layout-restructure-design.md. src/ is a plain
container, not a Python package - every existing import statement is
unchanged; only run-configuration (pytest.ini, Dockerfile, alembic.ini)
and a handful of artifact-directory path literals (already touched
once in the prior models/ split commit, adjusted here for the new one-
level-deeper CWD/__file__ convention) were edited.

Renaming to claude_build_spec.md's semantic folders (data/connectors/,
features/stocks/, models/long_horizon/, ...) is deliberately deferred
to a later plan, done together with real content changes rather than
as an empty-shell rename now.

Zero behavior change verified: same 2907 passing / 2 pre-existing-
unrelated-failing test count as the pre-restructure baseline, Docker
image builds and serves /health, Alembic resolves its new
script_location.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Deliberately not touched by this plan (found while designing it, out of scope)

- `src/v2/ml/predictor.py`'s `model_path` default
  (`"backend/models/v2_xgb_model.joblib"`) was already broken before
  this plan (CWD-relative with a `backend/` prefix that never matched
  the actual process CWD in any known run mode) — `MLPredictorV2`'s
  `model_data` was already always `None` in production. This plan does
  not fix it (that would be a behavior change, not a move), only leaves
  it exactly as non-functional as it already was.
- `src/research/train_v2.py`'s `f"backend/models/{model_name}"` save
  path has the same pre-existing pattern. Not touched.
- `src/scripts/ml_trainer.py` vs `src/research/ml_trainer.py`, and
  `src/scripts/backtest_advanced.py` vs `src/research/backtest_advanced.py`:
  each pair has diverged (not simple duplicates like the deleted root
  `admin_terminal.py`) and both sides move as-is. Worth a dedicated
  cleanup pass later, not part of this mechanical move.
- `backtest_results.csv`/`backtest_results.json` (written by the
  `backtest_advanced.py` pair via a bare `"backtest_results.csv"`
  literal) will land one directory deeper than before (`backend/src/`
  instead of `backend/`) the next time either script runs, since their
  CWD convention shifts the same way Step 12/13 above describe. Nothing
  reads these files back programmatically and no test depends on their
  location, so this is a cosmetic drift, not a correctness issue -
  left alone.
