# OptiTrade Backend — `src/` Layout Restructure (Phase 0)

Date: 2026-09-30
Status: Design — approved in brainstorming, not yet planned/implemented.

## Context

`investment_ai_system_schema.md` and `claude_build_spec.md` (project root)
describe a much larger "Finance AI Analysis Platform" architecture — a
multi-horizon (long/medium/short) research and decision engine with its
own entity model (`Asset`, `MarketBar`, `NewsEvent`, `DecisionObject`,
...), feature namespaces, point-in-time data rules, and a phased build
plan (`claude_build_spec.md`'s Phase 1–10).

That plan is too large for one spec or one implementation pass. This
document covers only the first, deliberately narrow sub-project agreed
in brainstorming: **move the existing backend into a `src/` layout with
zero behavior change**, so every later phase (new entities, multi-horizon
models, `DecisionObject`, ...) lands on the target directory shape from
day one instead of being built once and reorganized later.

**Decided in brainstorming (do not re-litigate here):**

1. The existing backend is migrated into the new shape, not rebuilt from
   scratch — `decision_engine/`, `feature_store/`, `pipeline/`,
   `engines/`, `users/`, `portfolio/`, `watchlist/`, `paper_trading/`,
   `dashboard/`, etc. all keep working; the live API and ~2900-test suite
   stay green throughout.
2. `investment_ai_system_schema.md`/`claude_build_spec.md` only describe
   the analysis/decision "brain" of the system. The account/product layer
   (`users`, `portfolio`, `watchlist`, `paper_trading`, `dashboard`,
   `organizations`) has no equivalent in those documents and is *not*
   dropped — it moves into `src/` alongside the brain, under its own
   area (see Target Tree).
3. The `src/` layout is applied **literally** (matches
   `claude_build_spec.md`'s suggested tree, including `tests/` living
   inside `src/`), not approximated.
4. Phase 0 is a **flat move only**: every existing module keeps its
   current name and internal shape, just physically relocated under
   `src/`. Renaming/remapping modules onto the build spec's semantic
   folders (`data/connectors/`, `features/stocks/`,
   `models/long_horizon/`, ...) is explicitly deferred to Phase 1+, done
   together with the real content changes those folders imply — not as
   an empty-shell rename now.

## Goal

After Phase 0:
- Every backend module lives under `backend/src/`.
- The full test suite (`backend/src/tests/`) passes with the same pass
  count as today (2907/2909, the 2 pre-existing unrelated failures
  unchanged).
- `docker-compose up` builds and serves `/health` successfully.
- No Python import statement changes, because `src/` is a plain
  container directory, not an importable package (see Key Decision
  below) — only run-configuration (pytest, Docker, Alembic) points at
  the new root.
- No behavior, endpoint, schema, or test assertion changes anywhere.

## Key decision: `src/` is a container, not a package

Two ways to do a Python "src layout":
- **(a) Container:** `src/` holds top-level packages directly
  (`src/core/`, `src/users/`, ...); the *interpreter's* import root is
  set to `src/` (via `PYTHONPATH=src`, pytest's `pythonpath = src`,
  Docker's `WORKDIR`/`CMD`). Code keeps writing `from core.hybrid_engine
  import ...` exactly as today.
- **(b) Package:** `src/` is itself a package (`src/__init__.py`
  exists); every import becomes `from src.core.hybrid_engine import
  ...`.

**Decision: (a), the container form.** It is the only option consistent
with "flat move, zero behavior change" — it touches zero `.py` import
lines across the ~250 source files and ~250 test files, only the small
set of files listed in "Run-configuration changes" below. Option (b)
would touch every import in the codebase for no functional benefit and
is rejected for this phase.

## Target tree

Every existing top-level module/package under `backend/` moves under
`backend/src/`, keeping its current name and internal structure
unchanged:

```
backend/src/
  # Analysis / decision core (what claude_build_spec.md's Phase 1+
  # will progressively reshape into data/, features/, models/, decision/,
  # llm/, evidence/, registry/, risk/, backtest/, monitoring/)
  core/               core/analyzer.py, hybrid_engine.py, ai_trader_persona.py, etc.
  v2/                 legacy v2 engine (pinned for iOS compat)
  decision_engine/
  feature_store/
  pipeline/
  engine_registry/
  engines/            technical/ fundamental/ news/
  signals/
  providers/
  data/               fetcher.py, fundamental.py (today's backend/data/)
  news/
  ml/
  ml_training/
  model_serving/
  research/
  research_lab/
  learning/
  explanation_engine/

  # Account / product platform (no equivalent in the new schema docs -
  # moves as-is, unchanged internally)
  users/
  portfolio/
  watchlist/
  paper_trading/
  dashboard/
  intelligence/

  # Cross-cutting
  api/                main.py's routers (api/v1)
  models/             schemas.py ONLY - see "models/ split" below
  db/
  middleware/
  alembic/
  main.py
  cache_manager.py
  terminal_dashboard.py
  scripts/            backtest.py, backtest_advanced.py, ml_trainer.py, admin_terminal.py
                      (the root's OWN admin_terminal.py is a stale duplicate - deleted,
                      not moved; see "Pre-existing issues" below)

  tests/              full existing tests/ tree, unchanged internally
```

Stays at `backend/` root (**not** moved into `src/` — these are
project/run configuration, not source code):

```
backend/
  .env  .env.example  .env.test
  requirements.txt  requirements-dev.txt
  pytest.ini
  Dockerfile  .dockerignore
  model_artifacts/    ← NEW, see "models/ split" below
  src/                ← everything above
```

### `models/` split

`backend/models/` today mixes real source (`schemas.py`) with two
binary ML artifacts (`v2_xgb_model.joblib`, `xgb_signal_model.joblib`)
that happen to share the directory name. These are not source code and
don't belong under `src/`:

- `models/schemas.py` → `src/models/schemas.py` (moves normally).
- `models/*.joblib` → `backend/model_artifacts/*.joblib` (new directory,
  sibling of `src/`). Every hardcoded path to these two files (at least
  `core/ml_predictor.py`; the implementation plan must grep for all
  references) is updated accordingly.

### Pre-existing issue found while planning this move

`backend/admin_terminal.py` (Aug 23) and `backend/scripts/admin_terminal.py`
(Sep 5, newer) are near-duplicates — the `scripts/` copy is a strict
superset (more imports, an `ml.train_chart_model` reference instead of
the root copy's stale `research.train_chart_model`, Firebase support).
The root copy is dead weight. Phase 0 deletes `backend/admin_terminal.py`
and moves `backend/scripts/` (as a whole, unchanged internally -
`admin_terminal.py`, `__init__.py`, `backtest.py`, `backtest_advanced.py`,
`ml_trainer.py`) → `src/scripts/`, consistent with "flat move, no
remapping": `scripts/` keeps existing as its own subdirectory, it just
loses the one duplicate file that never belonged there.

## Run-configuration changes

The only files Phase 0 edits outside pure file moves:

- **`pytest.ini`**: `pythonpath = .` → `pythonpath = src`, **and**
  `testpaths = tests` → `testpaths = src/tests` (easy to miss: without
  this second edit pytest would still run from `backend/` as rootdir,
  find nothing under the now-nonexistent `backend/tests/`, and silently
  collect zero tests instead of erroring).
- **`Dockerfile`**: `COPY . .` (build context is `./backend`, unchanged)
  already lands both `src/` and `model_artifacts/` under `/app/`, so:
  - Add `WORKDIR /app/src` right before the `CMD`/`HEALTHCHECK` section
    (after the existing `RUN chown ...` step, which needs an absolute or
    `/app`-relative path regardless of where `WORKDIR` ends up) so
    `uvicorn main:app` resolves `main.py` at its new location without
    becoming a `src.main:app`-style package import (rejected above).
  - `RUN chown -R appuser:appgroup models` **must change to
    `RUN chown -R appuser:appgroup model_artifacts`**: this line exists
    specifically so the in-container Continuous Learning retrain
    (`research/ml_trainer.py`, moving to `src/research/ml_trainer.py`)
    can overwrite `xgb_signal_model.joblib` in place at runtime (see this
    line's own comment in the current Dockerfile) — after the `models/`
    split above, that writable artifact lives in `model_artifacts/`, not
    in `src/models/` (which becomes read-only source, same as every
    other file under `src/`). Missing this edit would silently break the
    retrain the same way the original `chown` bug this comment describes
    did (`/ml/status` reporting `available: false`).
- **`alembic.ini`**: `script_location = alembic` → `script_location =
  src/alembic`.
- **`.env`/`.env.test` loading**: `load_dotenv()` (no path argument) walks
  upward from the *calling file's* directory looking for `.env`. Every
  caller (`main.py`, `users/config.py`, `decision_engine/config.py`, ...)
  moves one directory deeper (`backend/src/...` instead of
  `backend/...`), so the upward walk still reaches `backend/.env`/
  `backend/.env.test` correctly with no path change needed — verified
  empirically before writing this spec, not assumed.
- **`docker-compose.yml`**: no path changes expected (it only references
  `./backend` as the build context and `.env` files at `backend/`, both
  unaffected), but the implementation plan verifies this rather than
  assuming it.
- **Any `sys.path.insert(...)` test-file hack** (e.g.
  `tests/unit/test_hybrid_engine.py`,
  `tests/unit/test_signals_endpoint.py`, both currently doing
  `sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))`):
  unaffected, since `tests/` moves together with everything else — "two
  directories up from `tests/unit/`" still resolves to the new `src/`
  root after the move.

## Testing / verification

- Full backend suite (`pytest` run from `backend/`, where `pytest.ini`
  still lives - it picks up `pythonpath = src` and `testpaths =
  src/tests` from there) passes with the same 2907 passing / 2
  pre-existing-unrelated-failing count as the current baseline
  (`test_users_config_jwt_secret.py`, `test_core_news_analyzer_cache.py`)
  — any *new* failure is a Phase 0 bug, not pre-existing debt, and must
  be fixed before this phase is done.
- `docker compose build` and `docker compose up` succeed; `GET /health`
  responds 200 through the built image, not just the local venv.
- `alembic upgrade head` (or `alembic check`, whichever this repo already
  uses) runs cleanly against the new `script_location`.
- `git mv` is used for every relocation (not delete+recreate), so `git
  log --follow` keeps each file's history intact.

## Explicitly out of scope for this phase

- Any renaming to the build spec's semantic folders (`data/connectors/`,
  `features/stocks/`, `models/long_horizon/`, `decision/`, `llm/`,
  `evidence/`, `registry/`, `risk/`, `backtest/`, `monitoring/`).
- Any new entity (`Asset`, `MarketBar`, `NewsEvent`, ...), new model
  (long/medium/short horizon, regime detector), or `DecisionObject`
  contract work.
- Retiring `core/analyzer.py`/`v2/`/`core/hybrid_engine.py` (the three
  legacy decision paths) — they move as-is, pinned for iOS compatibility
  exactly as before.
- `ruff`/`mypy` adoption (`claude_build_spec.md` Phase 1 also asks for
  this; deferred to a later spec since it's independent of where files
  live).

## Risks

- **Mechanical but wide-reaching**: touches nearly every file in the
  repository (a `git mv`, not a content edit, for ~250+ files) — the
  risk is entirely in *completeness* (a forgotten hardcoded path, a
  missed config file) rather than logic. Mitigated by the verification
  list above running against the real Docker build, not just the local
  venv, since `python-dotenv`/relative-path bugs often only surface
  there.
- **Docker layer cache invalidation**: this is a large, one-time
  rebuild; not a concern for behavior, only for CI/deploy time on this
  one change.
