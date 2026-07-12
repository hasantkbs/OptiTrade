"""
OptiTrade Backend — Application Entry Point
=============================================
This file is responsible for:
  • Creating the FastAPI app
  • Registering middleware (CORS, request logging)
  • Registering global exception handlers
  • Mounting the versioned v1 router at both:
      /api/v1  — new versioned path (future clients)
      /        — legacy path (iOS backward compatibility)
  • Exposing /  and /health as bare infrastructure endpoints

Business logic lives in api/v1/router.py and the core/ package.
To add a new endpoint, add it to api/v1/router.py.
"""
import logging
import os
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from cache_manager import get_cache_manager
from core.errors import OptiTradeError
from core.logging_config import setup_logging
from middleware.request_logging import RequestLoggingMiddleware

# ── Logging (must be first) ────────────────────────────────────────────────────
_debug     = os.getenv("DEBUG", "False").lower() == "true"
_log_level = os.getenv("LOG_LEVEL", "INFO")
setup_logging(debug=_debug, log_level=_log_level)
logger = logging.getLogger(__name__)

# ── Firebase Admin ─────────────────────────────────────────────────────────────
_firebase_app = None
try:
    import firebase_admin
    from firebase_admin import auth as fb_auth
    from firebase_admin import credentials

    _cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json")
    if os.path.exists(_cred_path):
        cred = credentials.Certificate(_cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized.")
    else:
        logger.warning("Firebase credentials not found at %s — auth disabled.", _cred_path)
except ImportError:
    logger.warning("firebase-admin not installed — auth disabled.")

# ── Rate Limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="OptiTrade API",
    description="AI-powered investment analysis engine",
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
_default_origins = [
    "http://localhost:8000",
    "http://localhost:3000",
    "https://optitrade-fcda9.web.app",
    "https://optitrade-fcda9.firebaseapp.com",
]
_extra = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = _default_origins + [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Request Logging Middleware ────────────────────────────────────────────────
app.add_middleware(RequestLoggingMiddleware)


# ── Auth Dependency ────────────────────────────────────────────────────────────
async def verify_firebase_token(
    authorization: Optional[str] = Header(default=None),
) -> Optional[str]:
    """
    Verify Firebase ID token from Authorization: Bearer <token> header.
    Returns uid on success.
    Returns None when Firebase is not configured (dev/test mode).
    Raises 401 when Firebase is configured but token is missing or invalid.
    """
    if _firebase_app is None:
        return None
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization token missing.")
    token = authorization.split(" ", 1)[1]
    try:
        decoded = fb_auth.verify_id_token(token, app=_firebase_app)
        return decoded["uid"]
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


# Register auth dependency so api/v1/router.py can resolve it without a
# circular import.
from api.v1.auth import register_auth_dependency  # noqa: E402
register_auth_dependency(verify_firebase_token)


# ── Global Exception Handlers ─────────────────────────────────────────────────

@app.exception_handler(OptiTradeError)
async def optitrade_error_handler(request: Request, exc: OptiTradeError) -> JSONResponse:
    """Convert OptiTradeError subclasses to standardised JSON error responses."""
    request_id = getattr(request.state, "request_id", None)
    body = exc.to_dict()
    if request_id:
        body["request_id"] = request_id
    logger.warning(
        "Application error: %s — %s", exc.error_code, exc.message,
        extra={"request_id": request_id, "path": request.url.path},
    )
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors — log and return 500."""
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Unhandled exception on %s: %s", request.url.path, exc,
        extra={"request_id": request_id},
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error":      "INTERNAL_ERROR",
            "message":    "An unexpected error occurred. Please try again.",
            "request_id": request_id,
        },
    )


# ── Infrastructure Endpoints ──────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    """Root — returns runtime status. Not part of the versioned API contract."""
    return {
        "status":  "ok",
        "version": "4.0.0",
        "cache":   get_cache_manager().get_stats(),
    }


@app.get("/health", include_in_schema=False)
def health():
    """
    Health check used by Docker, load balancers, and monitoring.
    Returns 200 when the process is alive and the cache layer is reachable.
    """
    cache_stats = get_cache_manager().get_stats()
    return {
        "status":  "healthy",
        "version": "4.0.0",
        "cache":   cache_stats,
        "firebase": "enabled" if _firebase_app else "disabled",
    }


# ── Mount v1 Router ────────────────────────────────────────────────────────────
#
# The same router is mounted twice:
#   /api/v1/...  — canonical path for new integrations
#   /...         — legacy path so the iOS app needs zero changes
#
# This is intentional and explicit.  When the iOS app is updated to use
# /api/v1, we can remove the legacy mount.

from api.v1.router import router as v1_router  # noqa: E402 (after app creation)

app.include_router(v1_router, prefix="/api/v1", tags=["v1"])
app.include_router(v1_router, prefix="",        tags=["legacy"])

logger.info("OptiTrade API v4.0.0 ready. Routes mounted at / and /api/v1/")
