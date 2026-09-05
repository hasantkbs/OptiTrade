# requirements.txt pins pandas-ta>=0.4.71b0, which only publishes
# wheels for Python >=3.12 - a 3.11 base fails `pip install` outright
# on a clean build (verified: SERVER STEP 1 deployment-prep audit).
# 3.12 also matches this project's actual dev environment (venv).
FROM python:3.12-slim

# Security: no .pyc files, unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

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

# Application code
COPY . .

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Shell form so UVICORN_WORKERS (documented in .env.example, previously
# inert — this CMD always hardcoded 2 regardless of it) is actually
# honored; defaults to 2 unchanged if unset.
CMD sh -c 'exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers "${UVICORN_WORKERS:-2}" --log-level info'
