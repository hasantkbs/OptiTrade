# requirements.txt pins pandas-ta>=0.4.71b0, which only publishes
# wheels for Python >=3.12 - a 3.11 base fails `pip install` outright
# on a clean build (verified: SERVER STEP 1 deployment-prep audit).
# 3.12 also matches this project's actual dev environment (venv).
FROM python:3.12-slim

# Security: no .pyc files, unbuffered output.
# The non-root `appuser` created below has no home directory (`adduser
# --system` with no --home), so anything that writes to $HOME by
# default needs an explicit writable target instead:
#  - NUMBA_CACHE_DIR: pandas_ta (numba-jitted) tries to write its
#    compiled-function cache next to its own site-packages file (owned
#    by root from the `pip install` step below) and hard-fails at
#    import with "cannot cache function ...: no locator available"
#    instead of silently skipping the cache.
#  - MPLCONFIGDIR: matplotlib (a catboost dependency) degrades
#    gracefully on its own (falls back to a fresh temp dir + a WARNING
#    log) but does so on every process start - pointing it at a fixed
#    writable dir avoids the per-worker warning noise and repeated
#    temp-dir churn.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NUMBA_CACHE_DIR=/tmp/numba_cache \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# System deps — compile only, not needed at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps before copying application code so this layer
# is cached across code-only changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Non-root user for security - created before COPY so the chown below
# has a target, and before USER so root can still perform it.
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Application code. Left root-owned (no --chown here): the running
# appuser only ever needs to READ its own source, and a compromised
# request-handling process shouldn't be able to rewrite it.
COPY . .

# models/ is the one directory the app legitimately writes to at
# runtime (Continuous Learning's model retrain replaces
# xgb_signal_model.joblib in place - see research/ml_trainer.py). A
# plain `COPY . .` leaves it root-owned with whatever mode bits the
# build context's files happened to have (verified in SERVER STEP 2's
# live Docker check: on this host that was `600`, unreadable by
# appuser at all - `/ml/status` reported `available: false`, and the
# in-container retrain's own write failed with EACCES). chown (not
# chmod 777, not USER root) makes ownership deterministic regardless
# of what the build context's host permissions happen to be.
RUN chown -R appuser:appgroup models

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# JSON-array CMD running `sh -c '...'` explicitly - not a bare
# `CMD sh -c '...'` string, which Docker itself ALSO wraps in its own
# `/bin/sh -c "<the whole string>"` (its default behavior for any
# non-JSON-array CMD), producing sh -c "sh -c '...'": two nested
# shells, and PID 1 becomes the OUTER one, not the inner `exec`'d
# uvicorn. Plain `sh` never forwards signals to a child it's merely
# waiting on, so `docker stop`'s SIGTERM went nowhere - verified
# (SERVER STEP 3 Docker runtime check): the container never ran its
# shutdown handler and was hard SIGKILLed after the grace period on
# every stop. This form has exactly one shell, which `exec`s directly
# into uvicorn (PID 1), so it receives and acts on SIGTERM itself.
# ${UVICORN_WORKERS:-2} is still shell-expanded (documented in
# .env.example; defaults to 2 unchanged if unset).
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers \"${UVICORN_WORKERS:-2}\" --log-level info"]
