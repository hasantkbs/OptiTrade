"""
OptiTrade — Auth Dependency Resolver
======================================
Breaks the circular import between main.py and api/v1/router.py.

Flow:
  1. main.py creates verify_firebase_token()
  2. main.py calls register_auth_dependency(verify_firebase_token)
  3. api/v1/router.py calls get_auth_dependency() to retrieve it
"""
from typing import Callable, Optional

_auth_dependency: Optional[Callable] = None


def register_auth_dependency(dep: Callable) -> None:
    """Called by main.py after creating verify_firebase_token."""
    global _auth_dependency
    _auth_dependency = dep


def get_auth_dependency() -> Callable:
    """
    Return the registered auth dependency.
    Falls back to a no-op (returns None) if not registered yet,
    which handles tests and import-time resolution.
    """
    if _auth_dependency is not None:
        return _auth_dependency

    async def _noop_auth(authorization: Optional[str] = None) -> Optional[str]:
        return None

    return _noop_auth
