"""
Shared FastAPI middleware package.
"""

from shared.middleware.rate_limit import RateLimitMiddleware

__all__ = ["RateLimitMiddleware"]
