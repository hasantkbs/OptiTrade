"""
OptiTrade — Application Error Hierarchy
=========================================
All business-layer errors inherit from OptiTradeError.
The FastAPI exception handler in main.py converts them to consistent JSON responses.

Error response format (all errors):
    {
        "error":   "SYMBOL_NOT_FOUND",     # machine-readable code
        "message": "AAPL için veri yok",   # human-readable detail
        "details": {}                       # optional extra context
    }
"""
from typing import Optional


class OptiTradeError(Exception):
    """Base class for all application errors."""
    status_code: int = 500
    error_code:  str = "INTERNAL_ERROR"

    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error":   self.error_code,
            "message": self.message,
            "details": self.details,
        }


class SymbolNotFoundError(OptiTradeError):
    """Raised when a symbol has no data from the market data provider."""
    status_code = 404
    error_code  = "SYMBOL_NOT_FOUND"


class InsufficientDataError(OptiTradeError):
    """Not enough historical data to compute indicators reliably."""
    status_code = 422
    error_code  = "INSUFFICIENT_DATA"


class DataProviderError(OptiTradeError):
    """External data provider returned an error or timed out."""
    status_code = 503
    error_code  = "DATA_PROVIDER_ERROR"


class ProviderNotConfiguredError(OptiTradeError):
    """A required provider is not configured (missing API key, etc.)."""
    status_code = 503
    error_code  = "PROVIDER_NOT_CONFIGURED"


class AnalysisError(OptiTradeError):
    """Analysis pipeline failed for a recoverable reason."""
    status_code = 500
    error_code  = "ANALYSIS_ERROR"


class ValidationError(OptiTradeError):
    """Request payload is structurally valid but semantically wrong."""
    status_code = 400
    error_code  = "VALIDATION_ERROR"


class AuthenticationError(OptiTradeError):
    """Token missing, expired, or invalid."""
    status_code = 401
    error_code  = "AUTHENTICATION_ERROR"


class AuthorizationError(OptiTradeError):
    """Token valid but user lacks permission for this resource."""
    status_code = 403
    error_code  = "AUTHORIZATION_ERROR"


class RateLimitError(OptiTradeError):
    """Request rate exceeded."""
    status_code = 429
    error_code  = "RATE_LIMIT_EXCEEDED"
