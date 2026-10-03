# Pre-Deploy Stabilization — Design

## Mission

Fix every known real bug in the OptiTrade backend, redo the data work that
landed in the wrong database, get an honest test/accuracy read on the
corrected system, and only then redeploy `optitrade-api` on host
`mayasoftlnx01` — in that order. This closes out a status-check (2026-10-02)
that found the running container is 3-4 weeks stale (none of today's merged
`main` work — PR #2's decision-path consolidation, PR #3's OOS eval fix +
Feature Store backfill + ML candidate — is live yet) and surfaced several
real, previously-unknown problems that should be fixed before that redeploy
happens, not after.

## Current State (as verified 2026-10-02)

**The two-database split.** `backend/.env`'s `FEATURE_STORE_POSTGRES_HOST=localhost`
(matching `.env.example`'s documented default) points at a stale, separate
host-native Postgres on `127.0.0.1:5432`. The REAL database — the one the
running `optitrade-api` Docker container actually reads/writes via
`FEATURE_STORE_POSTGRES_HOST=postgres` (the `optitrade-postgres` Docker
service, `optitrade-net` bridge network, never published to the host) — was
queried directly and has only 1,055 `feature_store_records` rows and 0
`ml_training_model_registry` rows. Every piece of data work done earlier in
this project's session (a ~2-year, 215,580-row Feature Store backfill; a
trained and registered CANDIDATE model) exists only in the wrong, stale
database. User-confirmed: the Docker-internal one is the real one.

**SQLite permission bug (root cause found).** `core/monitoring.py`'s
`purge_old_predictions()` (and likely `validate_predictions()`, same file)
fails daily in production logs: `attempt to write a readonly database`.
Root cause, confirmed by inspecting the live container: `/app/data/monitoring.db`
and its containing directory `/app/data` are owned `root:root`; the
container actually runs as `appuser:appgroup` (uid 100, gid 101) — a user
with no write access to either the file or the directory. This is a Docker
image/ownership bug, not an application-logic bug: whatever created these
paths during the image build never `chown`'d them to the runtime user.

**`v2_xgb_model` is very likely NOT broken in production — it's
mismeasured.** `docs/ml-accuracy-report-2026-10-01.md` records `Feature
shape mismatch, expected: 5, got 7` for this model, but tracing the real
code shows: `v2/ml/predictor.py::MLPredictorV2.predict()` (the actual, live,
called-via-`v2/api/router.py:75` code path) computes its OWN 5 features
(`ema_dist`, `vwap_dist`, `rsi`, `velocity`, `range` — matching
`research/train_v2.py::extract_v2_features`, which is what the model was
trained on) and correctly subsets via `self.model_data['features']`. The
"expected 5, got 7" error instead comes from `scripts/evaluate_model_accuracy.py`,
which evaluates `v2_xgb_model.joblib` using the SAME generic 7-feature
extractor it uses for `xgb_signal_model.joblib` (`research.ml_trainer`'s
`FEATURE_NAMES`/`extract_features`) — the wrong extractor for this model.
The real predictor path has its own try/except (and the router wraps it in
a broader one too), consistent with zero "shape mismatch" log hits in 72h
of production logs. The actual fix is in the evaluation script, not a
retrain.

**Backfill crypto issues (already found, previously only documented).**
`scripts/backfill_feature_store.py` fetches ALL symbols via
`yf.Ticker(...).history(...)` directly, while live serving routes `-USD`
symbols (7 of the 22-symbol basket) through Binance via `HybridProvider` —
a train/serve data-source skew for those 7 symbols. Separately,
`trading_days_in_range` excludes Saturday/Sunday unconditionally, which is
wrong for 24/7 crypto assets — losing ~28% of available crypto history and
causing stale (up to 3-day) Monday feature lookups.

**Two more findings from today's reviews, previously parked as Minor.**
(1) `already_backfilled`'s skip-check compares `record.event_timestamp.date()`
read back from a `TIMESTAMPTZ` column against `day.date()` — correct only
because the DB session happens to be UTC today; not hardened. (2) A day
that legitimately yields fewer than all 17 features (an indicator legitimately
returning `None`, or the NaN/Inf guard skipping one) can never satisfy
`already_backfilled`'s "all 17 present" check, so it is recomputed and
re-inserted on every re-run — `insert()` has no unique constraint, so this
duplicates rows (not yet observed in practice, since every backfilled day
so far happened to produce all 17 features).

**Test suite hazard (already caused one real incident today).**
`backend/src/tests/test_ml_training_service.py`'s `_cleanup()` and
`backend/src/tests/test_ml_training_datasets.py` use unscoped `DELETE`
patterns (e.g. `DELETE FROM ml_training_model_registry WHERE engine_name
LIKE 'MLModel:%'`) that match ANY real row, not just that test's own
fixtures. Already deleted one real trained model's registry metadata today
(recovered via a genuine retrain, documented in
[[optitrade_test_suite_prod_db_hazard]]).

**No ML model currently beats its majority-class baseline out-of-sample** —
the legacy `xgb_signal_model`, its OOS-retrained variant, and the new
`ml_training`-trained CANDIDATE all honestly report an unfavorable result.
None of these models drive `decision_engine`'s actual live decisions
(Technical/Fundamental/News engines do) — `decision_engine` itself has no
backtested accuracy number; historical replay/backtesting for it remains
explicitly out of scope (deferred earlier in this project, unchanged by
this spec).

## Architecture: DB Access

Add a host port mapping for the `postgres` service in `docker-compose.yml`:
`127.0.0.1:5433:5432` (5433, not 5432 — 5432 is occupied by the stale
host-native instance; binding the same port would conflict, per the
override file's own existing comment about this). Update `backend/.env`
and `backend/.env.example`'s documented default/comment:
`FEATURE_STORE_POSTGRES_PORT=5433`, with a comment explaining why 5433 and
pointing at this spec for context. After this change, the host venv (and
every script this project's session has been running: `backfill_feature_store.py`,
`train_ml_candidate.py`, `evaluate_model_accuracy.py`, pytest) connects to
the REAL database — no `docker exec` indirection needed, no redoing of
today's work by data-migration (the old `localhost:5432` data is simply
left alone, unused; all real data work in this plan targets the DB via
port 5433 fresh).

## Scope — Five Phases

**Phase 1 — Safety first (enables everything after it to run safely):**
1. Scope every `DELETE` in `test_ml_training_service.py`'s `_cleanup()`
   and `test_ml_training_datasets.py` to that test's own
   author/model_id/symbol — eliminates the data-loss hazard before any
   more test runs happen in this plan.
2. Add the `postgres` port mapping + update `.env`/`.env.example` (the DB
   access architecture above).

**Phase 2 — Data-pipeline correctness fixes (code only, not run yet):**
3. Fix the backfill's crypto data-source skew: route `-USD` symbols
   through the same provider path live serving uses (`fetch_history` /
   `HybridProvider` → Binance), not plain `yf.Ticker`.
4. Fix the backfill's crypto weekend gap: `trading_days_in_range` must
   include all calendar days for `-USD` symbols, weekdays-only for
   everything else.
5. Harden the idempotency check's timestamp comparison to be explicit UTC,
   not dependent on the DB session's timezone setting.
6. Close the duplicate-write hole for a day that legitimately yields
   fewer than 17 features (a `UNIQUE` constraint + `ON CONFLICT DO NOTHING`
   on `feature_store_records`, or an equivalent per-day completion marker
   — implementer's call, argued in the task).

**Phase 3 — Real data work against the REAL database (one run, with every
Phase 2 fix already folded in — not two separate backfill runs):**
7. Run the corrected backfill against the real `optitrade-postgres` (via
   the new port 5433) — fresh, from scratch (the Phase 2 fixes change
   what gets written for crypto symbols specifically, so this cannot reuse
   the old wrong-DB data even if copied over).
8. Fix `evaluate_model_accuracy.py`'s `v2_xgb_model` evaluation to use
   `research.train_v2.extract_v2_features` (or equivalent — reuse, don't
   re-copy, matching this project's established "don't duplicate feature
   extraction logic" principle from PR #3's own fix) instead of the
   generic 7-feature extractor. Get a real accuracy number for this model
   for the first time.
9. Retrain the ML candidate (via `train_ml_candidate.py`, unchanged
   script) against the real, now-correctly-backfilled database. Evaluate
   out-of-sample. Success bar: beat the naive majority-class baseline. If
   it doesn't on the first try, a bounded number of reasonable fine-tuning
   attempts (hyperparameters and/or feature set — implementer's
   judgment, document what was tried) is in scope; if it still doesn't
   beat baseline after that, report the result honestly and move on — do
   NOT keep iterating indefinitely chasing a number.

**Phase 4 — Infra bug fix:**
10. Fix the Dockerfile so `/app/data` (and anything else written at
    runtime by the app) is owned by `appuser:appgroup` before the image
    switches to `USER appuser` — closes the SQLite permission bug.
    Secondary, explicitly optional consideration to flag in the task
    (not required): `monitoring.db` is not currently on a named volume,
    so a container recreation (like the one this plan ends with) loses
    its history regardless of the permission fix — worth a one-line note
    in the task about whether to also add a volume mount, but not
    mandatory for this plan.

**Phase 5 — Verification and deploy:**
11. Run the full backend test suite (now safe, Phase 1 fixed the DELETE
    hazard) as the final pre-deploy check.
12. **Stop and get the user's explicit confirmation before running the
    actual deploy command** (`docker compose build && docker compose up -d`
    or equivalent, against the running `mayasoftlnx01` containers) — this
    is the one step in this plan that touches the live, currently-serving
    container, and per this session's established working style it is
    confirmed, not assumed, regardless of how clean everything upstream
    looked.
13. Post-deploy live sanity check: confirm the container comes up healthy,
    confirm `backend/.env`'s Feature Store host/port actually resolves
    correctly from INSIDE the redeployed container too (the container
    itself should keep using `FEATURE_STORE_POSTGRES_HOST=postgres`
    internally — the port-5433 change is for host-venv access only, and
    must not leak into the container's own runtime config), spot-check a
    live `decide()` call or two.

## Global Constraints

- Every commit ends with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- No SHADOW or ACTIVE promotion of any ML model anywhere in this plan —
  unchanged from the prior plan's constraint; the candidate (retrained in
  Phase 3) stays at CANDIDATE.
- The container's own `FEATURE_STORE_POSTGRES_HOST` must remain `postgres`
  (Docker-internal) — the 5433 host port mapping is for host-side
  tooling/scripts only, never for the container's own runtime
  configuration. Verify this explicitly in Phase 5's post-deploy check.
- Phase 3's backfill is a single, fresh run against the real DB with all
  Phase 2 fixes already applied — never run the old (pre-fix) backfill
  logic against the real DB, and never attempt to migrate/copy rows from
  the stale `localhost:5432` database (it used the uncorrected crypto
  logic and would just reintroduce the same skew/gap into the real DB).
- Report the retrained candidate's real out-of-sample result honestly,
  whatever it is — an unfavorable result after a reasonable, bounded
  fine-tuning attempt is an acceptable, legitimate outcome, not something
  to hide or keep iterating on indefinitely.
- Deploy (Phase 5, step 12) requires the user's explicit go-ahead at that
  specific point in the plan, separate from this spec's own approval —
  do not fold that confirmation into this spec's approval or the
  implementation plan's approval.
- `decision_engine`'s own historical-replay/backtesting capability remains
  out of scope for this plan (an existing, previously-acknowledged
  limitation, unchanged here).

## Out of Scope

- SHADOW/ACTIVE promotion of any model.
- `decision_engine` historical-replay/backtesting infrastructure.
- Retraining or fixing `v2_xgb_model` itself — Phase 3's step 8 is a
  measurement fix only; if the resulting real accuracy number turns out
  to be unfavorable, that is reported, not treated as something this plan
  must also fix.
- Any other code area not named in the Current State section above — this
  plan fixes the specific, now-enumerated list of real problems found
  during the 2026-10-02 status check, not a general audit.

## Risks

- **Phase 3's real backfill run is a second real write against production
  data**, following today's earlier incident (an unrelated test bug
  deleted real registry rows). Mitigated by Phase 1 running first (fixes
  that exact hazard class) and by Phase 3 being a fresh run into a
  database that currently has very little real data to lose (1,055 rows,
  0 registry rows) — much lower blast radius than today's earlier
  incident was.
- **The Dockerfile ownership fix (Phase 4) changes build output for every
  future image build**, not just this one — a plausible regression
  surface if some other runtime path actually depends on root ownership
  of something under `/app`. The task must verify the full test suite
  (Phase 5) still passes and that the container starts and serves
  requests correctly after this change, not just that the one SQLite
  write succeeds.
- **The host port mapping (5433) is a new, permanent externally-reachable
  surface** on `mayasoftlnx01`, even though loopback-only
  (`127.0.0.1:5433`) — same exposure class as the existing `redis`/`api`
  loopback mappings already in `docker-compose.override.yml`, not a new
  category of risk, but worth naming explicitly since it's new.
- **Phase 2's crypto fixes change what data Phase 3 writes** compared to
  today's earlier (wrong-DB) backfill — the real, correct basket
  composition for crypto symbols will differ from what was reported in
  today's `docs/ml-candidate-report-2026-10-01.md`. That report's numbers
  are already clearly superseded by this plan; Phase 3's task should
  write a fresh, dated report rather than editing the old one in place.
